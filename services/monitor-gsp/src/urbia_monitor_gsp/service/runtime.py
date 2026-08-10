"""El ciclo de detección: de lecturas sueltas a resultados por zona.

Este módulo **no sabe de MQTT ni de PostgreSQL**. Recibe lecturas por
`observe` y produce resultados por `run_cycle`. Quién le trae las lecturas y
qué se hace con los resultados es problema de `source` y de `publisher`.

La separación no es estética: es lo que permite probar el ciclo entero sin
broker, y es lo que se va a mudar al nodo de borde para medir H1. Lo que se
mide allá tiene que ser el detector, no el andamiaje.

## Las tres cosas que puede pasarle a una zona en un ciclo

1. **No cerró ningún bin nuevo.** Con el intervalo de 3 s y bins de 6 s,
   esto pasa en aproximadamente la mitad de los ciclos y es lo normal.
2. **Se produjo una ventana.** Se escanea y sale un resultado, haya o no
   detección. La ventana sin detección también se publica: el estadístico y
   su ranking son lo que permite reconstruir el punto de operación después.
3. **No se produjo por falta de datos.** No se imputa ni se excluye a nadie:
   la zona no produce resultado y publica el motivo. Imputar inventaría el
   dato que el estadístico va a contrastar, y excluir cambiaría el grafo,
   cuyo espectro está calculado sobre la topología completa.

## Concurrencia

`observe` corre en el hilo de red de paho y `run_cycle` en el hilo
principal, sobre los mismos diccionarios de `ZoneWindow`. El candado se
toma sólo alrededor de `observe` y de `emit` —no del escaneo, que trabaja
sobre una matriz ya desprendida—, así que la ingesta queda bloqueada unos
pocos cientos de microsegundos por ciclo. Medido en
`experiments/ciclo-deteccion/`: `emit` son 309 µs de p50 para las seis
zonas, contra 3,33 µs que cuesta un mensaje.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Final, Literal

from ..detector.detector import CollectiveScanDetector
from ..detector.types import Detection
from ..graph.types import AmiGraph, MonitorGspError
from ..stream.window import BinIncompleteError, Window, WindowConfig, ZoneWindow
from .calibration import Calibration, ZoneCalibration
from .fingerprint import graph_fingerprints
from .metrics import MonitorMetrics, NullMetrics

logger: Final = logging.getLogger(__name__)

ZoneStatus = Literal["ventana", "sin_datos", "sin_bin"]
"""Los tres desenlaces posibles de una zona en un ciclo."""


class RuntimeSetupError(MonitorGspError, ValueError):
    """El grafo, la calibración y la configuración no encajan entre sí."""


@dataclass(frozen=True, slots=True)
class ZoneResult:
    """Lo que una zona produjo en un ciclo.

    Attributes:
        zona: Nombre de la zona.
        status: Cuál de los tres desenlaces ocurrió.
        window: La ventana densa, si se produjo.
        detection: El resultado del escaneo, si hubo ventana.
        missing: El motivo, si no se produjo por falta de datos.
    """

    zona: str
    status: ZoneStatus
    window: Window | None = None
    detection: Detection | None = None
    missing: BinIncompleteError | None = None

    @property
    def detected(self) -> bool:
        """Si el estadístico superó el umbral."""
        return self.detection is not None and self.detection.detected


@dataclass(frozen=True, slots=True)
class CycleResult:
    """Lo que produjo un ciclo completo.

    Attributes:
        started_utc: Instante con el que se corrió el ciclo.
        seconds: Duración de reloj.
        results: Resultado de cada zona, en el orden del grafo.
    """

    started_utc: datetime
    seconds: float
    results: tuple[ZoneResult, ...] = field(default_factory=tuple)

    @property
    def windows(self) -> tuple[ZoneResult, ...]:
        """Zonas que produjeron ventana."""
        return tuple(r for r in self.results if r.status == "ventana")

    @property
    def detections(self) -> tuple[ZoneResult, ...]:
        """Zonas en las que el estadístico superó el corte."""
        return tuple(r for r in self.results if r.detected)

    @property
    def missing(self) -> tuple[ZoneResult, ...]:
        """Zonas que no produjeron resultado por falta de datos."""
        return tuple(r for r in self.results if r.status == "sin_datos")


class ZoneRuntime:
    """Ventana y detector de una zona, con su candado.

    Args:
        zone_window: Acumulador de lecturas de la zona.
        detector: Detector con el umbral congelado ya cargado.
        fingerprint: Huella de la topología con la que se calibró.
    """

    def __init__(
        self,
        zone_window: ZoneWindow,
        detector: CollectiveScanDetector,
        fingerprint: str,
    ) -> None:
        """Guarda las piezas de la zona."""
        self.window = zone_window
        self.detector = detector
        self.fingerprint = fingerprint
        self.lock = threading.Lock()
        self._ingesta_previa = self._contadores()

    @property
    def zona(self) -> str:
        """Zona que atiende."""
        return self.window.zona

    def _contadores(self) -> dict[str, int]:
        """Contadores acumulados de la ingesta.

        Returns:
            Aceptados y descartados por motivo.
        """
        return {
            "aceptado": self.window.accepted_count,
            "desconocido": self.window.unknown_device_count,
            "tarde": self.window.late_count,
            "futuro": self.window.future_count,
            "superado": self.window.superseded_count,
        }

    def drain_ingest(self) -> tuple[int, dict[str, int]]:
        """Diferencia de la ingesta desde la última vez que se preguntó.

        Los contadores de `ZoneWindow` son acumulados y las métricas de
        Prometheus son incrementales; acá se hace la resta.

        Returns:
            Par `(aceptados, descartados por motivo)`.
        """
        actuales = self._contadores()
        delta = {k: actuales[k] - self._ingesta_previa[k] for k in actuales}
        self._ingesta_previa = actuales
        return delta.pop("aceptado"), delta


class MonitorRuntime:
    """Las zonas monitoreadas y el ciclo que las recorre.

    Args:
        zones: Runtime de cada zona, en el orden en que se recorren.
        metrics: Dónde registrar lo que pasa. `None` no registra nada.

    Raises:
        RuntimeSetupError: Si no hay ninguna zona.
    """

    def __init__(
        self,
        zones: dict[str, ZoneRuntime],
        metrics: MonitorMetrics | None = None,
    ) -> None:
        """Indexa las zonas y los medidores."""
        if not zones:
            raise RuntimeSetupError("el monitor no tiene ninguna zona que atender")
        self._zones = zones
        self._metrics = metrics if metrics is not None else NullMetrics()
        self._zona_de: dict[str, str] = {
            device_id: nombre
            for nombre, runtime in zones.items()
            for device_id in runtime.window.device_ids
        }
        self.ajenos = 0

    @property
    def zonas(self) -> tuple[str, ...]:
        """Zonas atendidas, en orden de recorrido."""
        return tuple(self._zones)

    @property
    def n_meters(self) -> int:
        """Medidores que el monitor espera en total."""
        return len(self._zona_de)

    def observe(self, device_id: str, timestamp_utc: datetime, value: float) -> bool:
        """Incorpora una lectura a la zona que le corresponde.

        La zona sale del padrón del grafo y **no del topic ni del campo
        `zona` del payload**: el grafo es la autoridad sobre a qué subgrafo
        pertenece cada medidor, y un payload que dijera otra cosa metería
        una lectura en una zona cuyo espectro no la contempla.

        Args:
            device_id: Medidor que publica.
            timestamp_utc: Instante de la lectura, con zona horaria.
            value: Valor de la magnitud monitoreada.

        Returns:
            `True` si ocupó una celda.
        """
        nombre = self._zona_de.get(device_id)
        if nombre is None:
            self.ajenos += 1
            return False
        runtime = self._zones[nombre]
        with runtime.lock:
            return runtime.window.observe(device_id, timestamp_utc, value, now=None)

    def _run_zone(self, runtime: ZoneRuntime, now: datetime) -> ZoneResult:
        """Corre una zona: cierra el bin, escanea si hay ventana.

        Args:
            runtime: Zona a correr.
            now: Instante con el que se cierra el bin.

        Returns:
            El desenlace de la zona.
        """
        try:
            with runtime.lock:
                ventana = runtime.window.emit(now)
        except BinIncompleteError as falta:
            self._metrics.observe_missing(falta, runtime.window.n_meters)
            logger.info("%s", falta)
            return ZoneResult(zona=runtime.zona, status="sin_datos", missing=falta)

        if ventana is None:
            return ZoneResult(zona=runtime.zona, status="sin_bin")

        (deteccion,) = runtime.detector.detect(ventana.matrix)
        self._metrics.observe_window(ventana, deteccion.statistic, deteccion.threshold)
        if deteccion.detected:
            self._metrics.observe_detection(runtime.zona)
            logger.warning(
                "detección en '%s': estadístico %.4f > umbral %.4f, %d medidores "
                "en la bola de radio %s centrada en %s",
                runtime.zona,
                deteccion.statistic,
                deteccion.threshold,
                len(deteccion.device_ids),
                deteccion.radius,
                deteccion.seed_device_id,
            )
        if ventana.skipped_bins:
            logger.error(
                "'%s' saltó %d bin(s): el ciclo tarda más que el bin y el atraso se "
                "acumula. Ver experiments/ciclo-deteccion/",
                runtime.zona,
                ventana.skipped_bins,
            )
        return ZoneResult(
            zona=runtime.zona,
            status="ventana",
            window=ventana,
            detection=deteccion,
        )

    def run_cycle(self, now: datetime) -> CycleResult:
        """Recorre todas las zonas una vez.

        Args:
            now: Instante con el que se cierran los bins. Se pasa en vez de
                leerlo adentro para que un test pueda mover el reloj y para
                que todas las zonas del mismo ciclo usen el mismo instante.

        Returns:
            El resultado del ciclo.
        """
        inicio = time.perf_counter()
        resultados = tuple(self._run_zone(runtime, now) for runtime in self._zones.values())
        duracion = time.perf_counter() - inicio

        self._metrics.observe_cycle(duracion)
        for runtime in self._zones.values():
            aceptados, descartados = runtime.drain_ingest()
            self._metrics.observe_ingest(aceptados, descartados)

        return CycleResult(started_utc=now, seconds=duracion, results=resultados)


def build_runtime(
    graph: AmiGraph,
    calibration: Calibration,
    window_config: WindowConfig | None = None,
    metrics: MonitorMetrics | None = None,
) -> MonitorRuntime:
    """Arma el monitor a partir del grafo vivo y la calibración congelada.

    **Verifica la topología antes de armar nada.** Si el grafo vivo no es el
    que se calibró, esto levanta `TopologyMismatchError` y el servicio no
    arranca: un umbral calibrado sobre otra topología produce detecciones
    que no corresponden al sistema real, y no hay forma de notarlo mirando
    la salida.

    Args:
        graph: Grafo AMI construido desde el padrón vivo.
        calibration: Calibración versionada.
        window_config: Parámetros de la ventana. `None` usa los medidos en
            `experiments/ventana-viva/`.
        metrics: Dónde registrar. `None` no registra nada.

    Returns:
        El monitor listo para recibir lecturas.

    Raises:
        TopologyMismatchError: Si el grafo vivo no es el calibrado.
        RuntimeSetupError: Si una zona del grafo no tiene calibración.
    """
    calibration.verify_topology(graph_fingerprints(graph))
    config = window_config if window_config is not None else WindowConfig()

    zonas: dict[str, ZoneRuntime] = {}
    for nombre in graph.zone_order or sorted(graph.zones):
        zona = graph.zones[nombre]
        cal = calibration.zones.get(nombre)
        if cal is None:  # pragma: no cover — verify_topology ya lo habría rechazado
            raise RuntimeSetupError(f"la zona '{nombre}' no tiene calibración")

        detector = CollectiveScanDetector(zona, cal.frozen.sigma_spatial, cal.frozen.config)
        detector.load_threshold(cal.frozen)
        _verify_window_fits(nombre, config, cal)

        zonas[nombre] = ZoneRuntime(
            zone_window=ZoneWindow(nombre, zona.device_ids, config),
            detector=detector,
            fingerprint=cal.fingerprint,
        )

    logger.info(
        "monitor armado: %d zona(s), %d medidores, calibración %s",
        len(zonas),
        sum(z.window.n_meters for z in zonas.values()),
        calibration.version,
    )
    return MonitorRuntime(zonas, metrics)


def _verify_window_fits(zona: str, config: WindowConfig, cal: ZoneCalibration) -> None:
    """Exige que la ventana que se arma sea la que el umbral supone.

    `WindowConfig.window_bins` decide cuántos bins trae la matriz y
    `DetectorConfig.window` sobre cuántos integra el detector. Si difieren,
    `detect` recorrería más de una ventana o ninguna, y el umbral congelado
    —calibrado para una ventana de N bins— dejaría de corresponder.

    Args:
        zona: Nombre de la zona, para el mensaje.
        config: Parámetros de la ventana en uso.
        cal: Calibración de la zona.

    Raises:
        RuntimeSetupError: Si los dos anchos no coinciden.
    """
    esperado = cal.frozen.config.window
    if config.window_bins != esperado:
        raise RuntimeSetupError(
            f"'{zona}' arma ventanas de {config.window_bins} bins y su umbral se "
            f"calibró sobre {esperado}: el corte dejaría de corresponder a la "
            f"distribución del máximo"
        )
