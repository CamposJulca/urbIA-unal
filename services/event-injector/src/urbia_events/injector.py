"""Orquestador: aplica especificaciones a una señal y devuelve la verdad.

El inyector no sabe de MQTT ni de PostgreSQL. Recibe un `ZoneGraph`, una
señal y una lista de especificaciones, y devuelve la señal modificada junto
con la verdad de referencia de lo que hizo. Todo lo aleatorio pasa por una
semilla explícita.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence

import numpy as np
import numpy.typing as npt
from urbia_monitor_gsp.graph import ZoneGraph

from .families import FAMILY_COLLECTIVE, TemporalProfile, apply_collective_deviation, step_profile
from .profile import SignalProfile
from .types import (
    CollectiveDeviationSpec,
    GroundTruth,
    InvalidSpecError,
    Magnitude,
    SignalBounds,
)


def _zone_key(zona: str) -> int:
    """Entero estable derivado del nombre de la zona.

    Se usa `blake2b` y no `hash()`, que en Python está aleatorizado por
    proceso: dos corridas del mismo experimento tienen que producir los
    mismos eventos.

    Args:
        zona: Nombre de la zona.

    Returns:
        Entero de 32 bits, determinista entre procesos y máquinas.
    """
    digest = hashlib.blake2b(zona.encode("utf-8"), digest_size=4).digest()
    return int.from_bytes(digest, "big")


def _as_matrix(
    signal: npt.ArrayLike,
    n_meters: int,
    zona: str,
) -> npt.NDArray[np.float64]:
    """Normaliza la señal a una matriz `(T, n)` de trabajo.

    Args:
        signal: Señal `(n,)` de un instante o `(T, n)` de varios.
        n_meters: Nodos que tiene el grafo.
        zona: Nombre de la zona, para el mensaje de error.

    Returns:
        Copia de la señal como matriz `(T, n)`, propiedad del inyector.

    Raises:
        InvalidSpecError: Si la forma no encaja con el grafo o si la señal
            tiene valores no finitos.
    """
    x = np.array(signal, dtype=np.float64, copy=True)
    if x.ndim == 1:
        x = x.reshape(1, -1)
    if x.ndim != 2 or x.shape[1] != n_meters:
        raise InvalidSpecError(
            f"la señal de la zona '{zona}' debe tener forma (n,) o (T, n) con "
            f"n={n_meters} medidores en el orden de device_ids; recibida {x.shape}"
        )
    if not np.isfinite(x).all():
        malos = int((~np.isfinite(x)).sum())
        raise InvalidSpecError(
            f"la señal de '{zona}' tiene {malos} valor(es) no finito(s): un NaN se "
            f"propagaría a la verdad de referencia sin que nada avise"
        )
    return x


class EventInjector:
    """Inyecta eventos correlacionados sobre la señal de una zona.

    Args:
        profile: Perfil de señal medido, que traduce múltiplos de σ a
            unidades físicas.
        bounds: Límites duros del esquema, por magnitud.
        seed: Semilla base. Combinada con el nombre de la zona y el índice
            del evento, fija toda la aleatoriedad de la corrida.
    """

    def __init__(
        self,
        profile: SignalProfile,
        bounds: Mapping[Magnitude, SignalBounds],
        seed: int,
    ) -> None:
        """Configura el inyector. Ver la documentación de la clase."""
        self._profile = profile
        self._bounds = dict(bounds)
        self._seed = int(seed)

    @property
    def seed(self) -> int:
        """Semilla base de la corrida."""
        return self._seed

    def _bounds_for(self, magnitude: Magnitude) -> SignalBounds:
        """Límites de una magnitud.

        Args:
            magnitude: Magnitud buscada.

        Returns:
            Los límites declarados.

        Raises:
            InvalidSpecError: Si no hay límites para esa magnitud.
        """
        try:
            return self._bounds[magnitude]
        except KeyError:
            raise InvalidSpecError(
                f"no hay límites declarados para '{magnitude}': sin ellos no se puede "
                f"garantizar que el evento respete el contrato del productor"
            ) from None

    def inject(
        self,
        zone: ZoneGraph,
        signal: npt.ArrayLike,
        specs: Sequence[CollectiveDeviationSpec],
        *,
        on_violation: str = "raise",
        temporal: TemporalProfile = step_profile,
    ) -> tuple[npt.NDArray[np.float64], GroundTruth]:
        """Aplica las especificaciones y devuelve la señal y su verdad.

        Los eventos se aplican en orden. Si dos afectan al mismo nodo en el
        mismo instante, sus desviaciones se acumulan y cada uno queda
        registrado por separado en la verdad.

        Args:
            zone: Subgrafo zonal que define la vecindad.
            signal: Señal `(n,)` o `(T, n)`, alineada a `zone.device_ids`.
            specs: Eventos a inyectar.
            on_violation: `"raise"` o `"scale"`. Ver
                `apply_collective_deviation`.
            temporal: Perfil temporal común a todos los eventos.

        Returns:
            Par `(señal_modificada, verdad)`. La señal conserva la forma
            `(T, n)` aunque la entrada haya sido `(n,)`.

        Raises:
            InvalidSpecError: Si la señal o `on_violation` son inválidos.
        """
        if on_violation not in ("raise", "scale"):
            raise InvalidSpecError(
                f"on_violation debe ser 'raise' o 'scale', recibido {on_violation!r}"
            )

        working = _as_matrix(signal, zone.n_meters, zone.zona)
        eventos = []
        for indice, spec in enumerate(specs):
            rng = np.random.default_rng([self._seed, _zone_key(zone.zona), indice])
            eventos.append(
                apply_collective_deviation(
                    zone,
                    working,
                    spec,
                    profile=self._profile,
                    bounds=self._bounds_for(spec.magnitude),
                    rng=rng,
                    event_id=f"{FAMILY_COLLECTIVE}-{zone.zona}-{indice:03d}",
                    on_violation="scale" if on_violation == "scale" else "raise",
                    temporal=temporal,
                )
            )

        verdad = GroundTruth(
            events=tuple(eventos),
            device_ids=zone.device_ids,
            n_instants=working.shape[0],
            seed=self._seed,
            zona=zone.zona,
        )
        return working, verdad
