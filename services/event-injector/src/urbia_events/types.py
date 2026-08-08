"""Contrato del inyector: magnitudes, límites, perfil, especificación y verdad.

Estas estructuras son lo que separa "se inyectó un evento" de "se puede
evaluar un detector con él". La verdad de referencia (`GroundTruth`) es
tan parte del entregable como la señal modificada: sin ella no hay forma
de contar aciertos ni errores.

Ninguna de estas estructuras sabe de MQTT, de PostgreSQL ni del detector.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Final, Literal

import numpy as np
import numpy.typing as npt

Magnitude = Literal["voltaje_v", "corriente_a", "potencia_kw"]
DeviceType = Literal["mono", "trifasico"]
Direction = Literal["up", "down"]

MAGNITUDES: Final[tuple[Magnitude, ...]] = ("voltaje_v", "corriente_a", "potencia_kw")
DEVICE_TYPES: Final[tuple[DeviceType, ...]] = ("mono", "trifasico")

_DEVICE_ID_RE: Final = re.compile(r"^urbia-(?:cen|chi|ena|pal|pgr|uni)-(mon|tri)-\d{4}$")
_TOKEN_A_TIPO: Final[dict[str, DeviceType]] = {"mon": "mono", "tri": "trifasico"}


class EventInjectorError(Exception):
    """Error base del inyector de eventos."""


class InvalidSpecError(EventInjectorError, ValueError):
    """La especificación del evento es inconsistente o incompleta."""


class UnknownDeviceError(EventInjectorError, ValueError):
    """Un `device_id` no pertenece al grafo o no tiene el formato del esquema."""


class BoundsViolationError(EventInjectorError, ValueError):
    """La desviación sacaría a algún medidor del rango del esquema.

    Es un error y no un recorte silencioso: si la magnitud pedida no cabe,
    el evento deja de ser sutil y el resultado dejaría de significar lo que
    el experimento afirma. Quien quiera recortar lo pide explícitamente con
    `on_violation="scale"`.
    """

    def __init__(
        self,
        magnitude: Magnitude,
        device_ids: tuple[str, ...],
        worst_value: float,
        minimum: float,
        maximum: float,
    ) -> None:
        """Inicializa el error con los medidores culpables.

        Args:
            magnitude: Magnitud desviada.
            device_ids: Medidores que cruzarían el límite.
            worst_value: El valor más alejado del rango.
            minimum: Límite inferior del esquema.
            maximum: Límite superior del esquema.
        """
        self.magnitude = magnitude
        self.device_ids = device_ids
        self.worst_value = worst_value
        super().__init__(
            f"la desviación en '{magnitude}' saca del rango [{minimum}, {maximum}] a "
            f"{len(device_ids)} medidor(es) ({', '.join(device_ids[:5])}): el peor valor "
            f"queda en {worst_value:.4f}. Bajá la magnitud, elegí otra semilla, o pasá "
            f"on_violation='scale' si querés que se ajuste sola"
        )


def device_type_of(device_id: str) -> DeviceType:
    """Deduce el tipo de medidor de su identificador.

    El `device_id` codifica el tipo en su tercer token (`mon`/`tri`).
    Medido sobre `ami_telemetry`: los 150 medidores tienen `device_type`
    coherente con ese token, sin excepciones.

    Args:
        device_id: Identificador con el formato del esquema del productor.

    Returns:
        `"mono"` o `"trifasico"`.

    Raises:
        UnknownDeviceError: Si el identificador no sigue el formato.
    """
    coincidencia = _DEVICE_ID_RE.match(device_id)
    if coincidencia is None:
        raise UnknownDeviceError(
            f"'{device_id}' no sigue el formato del esquema "
            f"urbia-<zona>-<mon|tri>-NNNN, así que no se puede deducir su tipo"
        )
    return _TOKEN_A_TIPO[coincidencia.group(1)]


@dataclass(frozen=True, slots=True)
class SignalBounds:
    """Rango admisible de una magnitud, según el contrato del productor.

    Es el **límite duro**: fuera de él el mensaje no existe, porque el
    `PayloadValidator` del simulador lo rechaza antes de publicar. No es
    lo mismo que el rango donde la señal vive en la práctica, que es lo
    que describe `MagnitudeProfile`.

    Attributes:
        magnitude: Magnitud a la que aplica.
        minimum: Valor mínimo admisible.
        maximum: Valor máximo admisible.
    """

    magnitude: Magnitude
    minimum: float
    maximum: float

    def __post_init__(self) -> None:
        """Valida el orden de los límites.

        Raises:
            InvalidSpecError: Si el mínimo no es menor que el máximo.
        """
        if not self.minimum < self.maximum:
            raise InvalidSpecError(
                f"rango inválido en '{self.magnitude}': "
                f"minimum={self.minimum} debe ser < maximum={self.maximum}"
            )

    def violations(self, values: npt.NDArray[np.float64]) -> npt.NDArray[np.bool_]:
        """Marca qué valores caen fuera del rango.

        Args:
            values: Valores a verificar, de cualquier forma.

        Returns:
            Máscara booleana de la misma forma, `True` donde hay violación.
        """
        return np.asarray((values < self.minimum) | (values > self.maximum), dtype=np.bool_)


@dataclass(frozen=True, slots=True)
class MagnitudeProfile:
    """Cómo se comporta una magnitud en operación normal, para un tipo de medidor.

    `sigma_spatial` es la cantidad que importa: la dispersión **entre
    medidores en un mismo instante**, que es la que ve un detector
    definido sobre el grafo. La dispersión temporal incluye la curva de
    carga diaria, que todos los medidores comparten y que por lo tanto no
    produce desacuerdo entre vecinos.

    Attributes:
        magnitude: Magnitud descrita.
        device_type: Tipo de medidor.
        mean: Media observada.
        sigma_spatial: Desviación entre medidores en un mismo instante.
        sigma_pooled: Desviación sobre todas las lecturas, temporal incluida.
        p1: Percentil 1 observado.
        p99: Percentil 99 observado.
        minimum_observed: Mínimo observado.
        maximum_observed: Máximo observado.
    """

    magnitude: Magnitude
    device_type: DeviceType
    mean: float
    sigma_spatial: float
    sigma_pooled: float
    p1: float
    p99: float
    minimum_observed: float
    maximum_observed: float

    def __post_init__(self) -> None:
        """Valida que la dispersión sea utilizable.

        Raises:
            InvalidSpecError: Si `sigma_spatial` no es finita y positiva.
        """
        if not np.isfinite(self.sigma_spatial) or self.sigma_spatial <= 0.0:
            raise InvalidSpecError(
                f"sigma_spatial de '{self.magnitude}'/{self.device_type} debe ser "
                f"finita y > 0, recibido {self.sigma_spatial}: sin dispersión no hay "
                f"forma de expresar una desviación en múltiplos de sigma"
            )

    @property
    def relative_spread(self) -> float:
        """Cociente `sigma_spatial / mean`, adimensional."""
        return self.sigma_spatial / self.mean


@dataclass(frozen=True, slots=True)
class CollectiveDeviationSpec:
    """Desviación colectiva sutil sobre un vecindario del grafo.

    Un nodo semilla y sus vecinos hasta cierta profundidad se desvían en la
    misma dirección, con una magnitud lo bastante chica para que ningún
    medidor salga del rango del esquema — y, lo que importa más, para que
    ninguno se distinga individualmente de su propia variación normal. Lo
    anómalo es la **coherencia del grupo**, no el valor de ningún medidor.

    La magnitud se declara de una de dos formas, y exactamente una:

    * `sigma_multiple`: desplazamiento absoluto de `k · σ_espacial`, igual
      para todo el grupo. Es la forma por defecto y la comparable entre
      magnitudes y entre tipos de medidor.
    * `fraction`: desplazamiento relativo al valor de cada nodo. Más
      natural para potencia, donde un consumo mayor implica una desviación
      mayor en términos absolutos.

    **Sobre `depth`.** Medido sobre la topología de los 150 con k-NN k=4:
    la profundidad 1 alcanza el 20–27 % de la zona y la 2 el 40–55 %. En
    profundidad 3 el vecindario cubre el 63–85 % y prácticamente no queda
    vecindario sano contra el cual contrastar: el evento deja de ser una
    discordancia local y se vuelve un corrimiento de zona entera. El rango
    útil en esta topología es `{0, 1, 2}`; `depth=0` afecta sólo a la
    semilla y sirve como caso de control individual.

    Attributes:
        magnitude: Magnitud a desviar.
        depth: Profundidad del vecindario en saltos del grafo.
        sigma_multiple: Magnitud en múltiplos de la dispersión espacial.
        fraction: Magnitud como fracción del valor de cada nodo.
        direction: Sentido de la desviación.
        seed_device_id: Nodo semilla. Si es `None` se sortea con la semilla
            del inyector, que es lo preferible: elegirlo a mano permite
            acomodar el resultado.
        start: Primer instante afectado.
        duration: Cantidad de instantes consecutivos afectados.
        expected_detectable: Si el evento *debe* ser detectado. Está acá
            para las familias de control —un corrimiento de zona completa
            es un modo común y el detector no debería dispararse— que
            necesitan entrar a la verdad de referencia como casos
            negativos.
    """

    magnitude: Magnitude
    depth: int
    sigma_multiple: float | None = None
    fraction: float | None = None
    direction: Direction = "up"
    seed_device_id: str | None = None
    start: int = 0
    duration: int = 1
    expected_detectable: bool = True

    def __post_init__(self) -> None:
        """Valida la coherencia interna de la especificación.

        Raises:
            InvalidSpecError: Si falta la magnitud, si se declaran las dos
                formas a la vez, o si algún parámetro es negativo.
        """
        declaradas = [v for v in (self.sigma_multiple, self.fraction) if v is not None]
        if len(declaradas) != 1:
            raise InvalidSpecError(
                "hay que declarar exactamente uno de sigma_multiple o fraction: "
                "el porcentaje crudo no es comparable entre magnitudes (5 % es 2,5σ "
                "en voltaje y 0,14σ en corriente), así que declarar los dos o "
                "ninguno esconde un malentendido"
            )
        if declaradas[0] <= 0.0:
            raise InvalidSpecError(
                f"la magnitud de la desviación debe ser > 0, recibida {declaradas[0]}: "
                f"el sentido se declara en `direction`, no con el signo"
            )
        if self.depth < 0:
            raise InvalidSpecError(f"depth debe ser >= 0, recibido {self.depth}")
        if self.start < 0:
            raise InvalidSpecError(f"start debe ser >= 0, recibido {self.start}")
        if self.duration < 1:
            raise InvalidSpecError(f"duration debe ser >= 1, recibido {self.duration}")

    @property
    def sign(self) -> float:
        """Signo de la desviación: `+1` hacia arriba, `−1` hacia abajo."""
        return 1.0 if self.direction == "up" else -1.0


@dataclass(frozen=True, slots=True)
class InjectedEvent:
    """Verdad de referencia de un evento efectivamente aplicado.

    Es lo que después permite contar aciertos y errores. Registra no sólo
    lo que se pidió sino **lo que se aplicó**: `delta` guarda la desviación
    real por nodo y por instante, de modo que la señal original se
    reconstruye exactamente restándola.

    Attributes:
        event_id: Identificador único dentro de la corrida.
        family: Nombre de la familia de evento.
        zona: Zona sobre la que se aplicó.
        magnitude: Magnitud desviada.
        seed_device_id: Nodo semilla.
        device_ids: Nodos afectados, en el orden canónico del grafo.
        node_indices: Posiciones de esos nodos en el grafo.
        start: Primer instante afectado.
        duration: Instantes afectados.
        depth: Profundidad del vecindario usada.
        sigma_multiple: Magnitud efectiva en múltiplos de σ, si aplica.
        fraction: Magnitud efectiva como fracción, si aplica.
        delta: Desviación aplicada, forma `(duration, len(device_ids))`.
        scaled: Si hubo que reducir la magnitud para respetar los límites.
        expected_detectable: Si el evento debe ser detectado.
    """

    event_id: str
    family: str
    zona: str
    magnitude: Magnitude
    seed_device_id: str
    device_ids: tuple[str, ...]
    node_indices: tuple[int, ...]
    start: int
    duration: int
    depth: int
    sigma_multiple: float | None
    fraction: float | None
    delta: tuple[tuple[float, ...], ...]
    scaled: bool
    expected_detectable: bool

    @property
    def instants(self) -> range:
        """Instantes afectados por el evento."""
        return range(self.start, self.start + self.duration)

    @property
    def max_abs_delta(self) -> float:
        """Mayor desviación aplicada en valor absoluto."""
        return max(abs(v) for fila in self.delta for v in fila)

    def to_dict(self) -> dict[str, Any]:
        """Serializa el evento a tipos JSON.

        Returns:
            Diccionario serializable, con `delta` como listas anidadas.
        """
        return {
            "event_id": self.event_id,
            "family": self.family,
            "zona": self.zona,
            "magnitude": self.magnitude,
            "seed_device_id": self.seed_device_id,
            "device_ids": list(self.device_ids),
            "node_indices": list(self.node_indices),
            "start": self.start,
            "duration": self.duration,
            "depth": self.depth,
            "sigma_multiple": self.sigma_multiple,
            "fraction": self.fraction,
            "delta": [list(fila) for fila in self.delta],
            "max_abs_delta": self.max_abs_delta,
            "scaled": self.scaled,
            "expected_detectable": self.expected_detectable,
        }


@dataclass(frozen=True, slots=True)
class GroundTruth:
    """Verdad de referencia de una corrida completa.

    Attributes:
        events: Eventos aplicados, en orden de aplicación.
        device_ids: Orden canónico de los nodos del grafo.
        n_instants: Instantes de la señal.
        seed: Semilla con la que se generó todo.
        zona: Zona del grafo.
    """

    events: tuple[InjectedEvent, ...]
    device_ids: tuple[str, ...]
    n_instants: int
    seed: int
    zona: str
    _index: dict[str, int] = field(default_factory=dict, repr=False, compare=False)

    def __post_init__(self) -> None:
        """Precalcula el índice de `device_id` a posición."""
        self._index.update({d: i for i, d in enumerate(self.device_ids)})

    def node_mask(self, instant: int) -> npt.NDArray[np.bool_]:
        """Nodos anómalos en un instante dado.

        Args:
            instant: Índice temporal.

        Returns:
            Máscara booleana alineada a `device_ids`, `True` donde hay
            evento activo en ese instante.
        """
        mascara = np.zeros(len(self.device_ids), dtype=np.bool_)
        for evento in self.events:
            if instant in evento.instants:
                mascara[list(evento.node_indices)] = True
        return mascara

    def instant_mask(self) -> npt.NDArray[np.bool_]:
        """Matriz `(n_instants, n_nodos)` con los nodos anómalos por instante."""
        return np.array([self.node_mask(t) for t in range(self.n_instants)], dtype=np.bool_)

    def to_dict(self) -> dict[str, Any]:
        """Serializa la verdad de referencia a tipos JSON.

        Returns:
            Diccionario serializable.
        """
        return {
            "zona": self.zona,
            "seed": self.seed,
            "n_instants": self.n_instants,
            "device_ids": list(self.device_ids),
            "events": [e.to_dict() for e in self.events],
        }
