"""Familias de evento. Hoy una sola: la desviación colectiva sutil.

## Qué distingue a esta familia

El generador que ya trae el simulador produce anomalías **independientes**
por medidor: sube el voltaje a 243–250 V con probabilidad 1 %. Medido sobre
`ami_telemetry`, eso está a +6σ de la media, así que cualquier umbral lo
separa sin error y no sirve para evaluar detección colectiva.

Esta familia hace lo contrario. Cada medidor queda dentro de su variación
normal —individualmente indistinguible— y lo anómalo es que un grupo
conectado del grafo se mueve **junto**. Un umbral por medidor no puede
verlo por construcción; un detector definido sobre la vecindad, en
principio sí. Ésa es la afirmación que la tercera hipótesis tiene que
poder poner a prueba.

## Dónde se enchufan las demás

El perfil temporal está factorizado (`TemporalProfile`): decide cuánto pesa
la desviación en cada instante de la ventana. La familia de hoy usa un
escalón. Una deriva gradual cambia sólo esa función, no la forma espacial
ni la interfaz. Una familia de dipolo cambia sólo el signo por nodo, que ya
es un vector y no un escalar.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Final, Literal

import numpy as np
import numpy.typing as npt
from urbia_monitor_gsp.graph import ZoneGraph

from .neighborhood import boundary_edges, connected_subgraph, k_hop
from .profile import SignalProfile
from .types import (
    BoundsViolationError,
    CollectiveDeviationSpec,
    InjectedEvent,
    SignalBounds,
    UnknownDeviceError,
    device_type_of,
)

FAMILY_COLLECTIVE: Final = "desviacion_colectiva"

TemporalProfile = Callable[[int, int], float]
"""Peso de la desviación en cada instante: `(offset, duration) -> peso`."""


def step_profile(offset: int, duration: int) -> float:
    """Escalón: la desviación entra completa y se mantiene.

    Args:
        offset: Posición dentro de la ventana del evento.
        duration: Largo de la ventana.

    Returns:
        Siempre `1.0`.
    """
    del offset, duration
    return 1.0


def _resolve_seed(
    zone: ZoneGraph,
    spec: CollectiveDeviationSpec,
    rng: np.random.Generator,
) -> int:
    """Determina el nodo semilla del evento.

    Sortearlo es lo preferible: elegirlo a mano permitiría acomodar el
    resultado, que es exactamente lo que una verdad de referencia no puede
    permitir.

    Args:
        zone: Subgrafo zonal.
        spec: Especificación del evento.
        rng: Generador ya sembrado.

    Returns:
        Posición de la semilla en el orden canónico del grafo.

    Raises:
        UnknownDeviceError: Si el `device_id` pedido no está en la zona.
    """
    if spec.seed_device_id is None:
        return int(rng.integers(zone.n_meters))
    try:
        return zone.device_ids.index(spec.seed_device_id)
    except ValueError:
        raise UnknownDeviceError(
            f"'{spec.seed_device_id}' no pertenece a la zona '{zone.zona}', que tiene "
            f"{zone.n_meters} medidores"
        ) from None


def _grupo(
    zone: ZoneGraph,
    semilla: int,
    spec: CollectiveDeviationSpec,
    rng: np.random.Generator,
) -> tuple[int, ...]:
    """Nodos afectados, por el eje que declare la especificación.

    Args:
        zone: Subgrafo zonal.
        semilla: Posición del nodo semilla.
        spec: Especificación del evento.
        rng: Generador ya sembrado.

    Returns:
        Posiciones del grupo, en orden creciente.
    """
    if spec.size_target is not None:
        return connected_subgraph(
            zone.adjacency, semilla, spec.size_target, shape=spec.shape, rng=rng
        )
    assert spec.depth is not None  # __post_init__ garantiza uno de los dos ejes
    return k_hop(zone.adjacency, semilla, spec.depth)


def _base_delta(
    zone: ZoneGraph,
    values: npt.NDArray[np.float64],
    nodes: tuple[int, ...],
    spec: CollectiveDeviationSpec,
    profile: SignalProfile,
    temporal: TemporalProfile,
) -> npt.NDArray[np.float64]:
    """Desviación pedida, antes de verificar los límites del esquema.

    Args:
        zone: Subgrafo zonal.
        values: Valores actuales `(duration, len(nodes))` de los nodos afectados.
        nodes: Posiciones de los nodos afectados.
        spec: Especificación del evento.
        profile: Perfil de señal medido.
        temporal: Perfil temporal de la desviación.

    Returns:
        Matriz `(duration, len(nodes))` con la desviación pedida.
    """
    pesos = np.array(
        [temporal(offset, spec.duration) for offset in range(spec.duration)],
        dtype=np.float64,
    ).reshape(-1, 1)

    if spec.sigma_multiple is not None:
        sigmas = np.array(
            [
                profile.sigma_spatial(spec.magnitude, device_type_of(zone.device_ids[i]))
                for i in nodes
            ],
            dtype=np.float64,
        )
        base = spec.sign * spec.sigma_multiple * sigmas
        return np.asarray(pesos * base, dtype=np.float64)

    assert spec.fraction is not None  # __post_init__ garantiza uno de los dos
    return np.asarray(pesos * spec.sign * spec.fraction * values, dtype=np.float64)


def _scale_for_bounds(
    values: npt.NDArray[np.float64],
    delta: npt.NDArray[np.float64],
    bounds: SignalBounds,
) -> float:
    """Mayor factor en `(0, 1]` que mantiene todo dentro del rango.

    Args:
        values: Valores actuales de los nodos afectados.
        delta: Desviación pedida, misma forma.
        bounds: Límites del esquema.

    Returns:
        El factor de escala. Vale `1.0` si la desviación ya cabe.
    """
    margen = np.where(delta > 0.0, bounds.maximum - values, values - bounds.minimum)
    con_desviacion = np.abs(delta) > 0.0
    if not con_desviacion.any():
        return 1.0
    permitido = np.divide(
        np.maximum(margen, 0.0),
        np.abs(delta),
        out=np.full_like(delta, np.inf),
        where=con_desviacion,
    )
    return float(min(1.0, permitido.min()))


def apply_collective_deviation(
    zone: ZoneGraph,
    working: npt.NDArray[np.float64],
    spec: CollectiveDeviationSpec,
    *,
    profile: SignalProfile,
    bounds: SignalBounds,
    rng: np.random.Generator,
    event_id: str,
    on_violation: Literal["raise", "scale"] = "raise",
    temporal: TemporalProfile = step_profile,
) -> InjectedEvent:
    """Aplica una desviación colectiva y devuelve su verdad de referencia.

    Modifica `working` en el lugar. La verdad registra la desviación
    **realmente aplicada**, de modo que restar `delta` reconstruye la señal
    original exactamente.

    Args:
        zone: Subgrafo zonal sobre el que se define la vecindad.
        working: Señal `(T, n)`, modificada en el lugar.
        spec: Especificación del evento.
        profile: Perfil de señal medido, para traducir σ a unidades.
        bounds: Límites del esquema para esta magnitud.
        rng: Generador ya sembrado.
        event_id: Identificador del evento dentro de la corrida.
        on_violation: `"raise"` aborta si la desviación saca a algún medidor
            del rango; `"scale"` la reduce al mayor valor que sí cabe y lo
            deja registrado en la verdad.
        temporal: Perfil temporal de la desviación.

    Returns:
        La verdad de referencia del evento aplicado.

    Raises:
        BoundsViolationError: Si `on_violation="raise"` y la desviación no
            cabe en el rango del esquema.
        UnknownDeviceError: Si la semilla pedida no está en la zona.
        ValueError: Si la ventana del evento excede el largo de la señal.
    """
    fin = spec.start + spec.duration
    if fin > working.shape[0]:
        raise ValueError(
            f"el evento cubre los instantes [{spec.start}, {fin}) pero la señal tiene "
            f"{working.shape[0]}: la ventana no puede exceder la señal"
        )

    semilla = _resolve_seed(zone, spec, rng)
    nodos = _grupo(zone, semilla, spec, rng)
    columnas = list(nodos)
    valores = working[spec.start : fin][:, columnas]

    delta = _base_delta(zone, valores, nodos, spec, profile, temporal)
    escala = _scale_for_bounds(valores, delta, bounds)
    escalado = escala < 1.0

    if escalado and on_violation == "raise":
        fuera = bounds.violations(valores + delta)
        culpables = tuple(
            zone.device_ids[nodos[j]]
            for j in sorted({int(j) for _, j in zip(*np.nonzero(fuera), strict=False)})
        )
        peor = (valores + delta).ravel()[np.argmax(np.abs((valores + delta).ravel()))]
        raise BoundsViolationError(
            spec.magnitude, culpables, float(peor), bounds.minimum, bounds.maximum
        )

    delta = delta * escala
    working[spec.start : fin, columnas] = valores + delta

    return InjectedEvent(
        event_id=event_id,
        family=FAMILY_COLLECTIVE,
        zona=zone.zona,
        magnitude=spec.magnitude,
        seed_device_id=zone.device_ids[semilla],
        device_ids=tuple(zone.device_ids[i] for i in nodos),
        node_indices=nodos,
        start=spec.start,
        duration=spec.duration,
        depth=spec.depth,
        size_target=spec.size_target,
        shape=(None if spec.size_target is None else spec.shape),
        n_nodes=len(nodos),
        boundary_edges=boundary_edges(zone.adjacency, nodos),
        zone_size=zone.n_meters,
        sigma_multiple=(None if spec.sigma_multiple is None else spec.sigma_multiple * escala),
        fraction=(None if spec.fraction is None else spec.fraction * escala),
        delta=tuple(tuple(float(v) for v in fila) for fila in delta),
        scaled=escalado,
        expected_detectable=(
            len(nodos) < zone.n_meters
            if spec.expected_detectable is None
            else spec.expected_detectable
        ),
    )
