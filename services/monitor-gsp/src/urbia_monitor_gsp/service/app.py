"""El servicio: armado, bucle y apagado.

## El arranque es una secuencia de negativas

El servicio se niega a arrancar antes que arrancar mal, y en este orden:

1. **Sin calibración congelada no arranca.** Calibrar en caliente sobre
   datos vivos haría que una anomalía persistente se volviera parte de la
   hipótesis nula: el umbral subiría hasta acomodarla y el detector dejaría
   de verla. Cuanto peor la anomalía, más normal parecería.
2. **Si el grafo vivo no es el calibrado, no arranca.** Un umbral calibrado
   sobre otra topología produce detecciones que no corresponden al sistema
   real, y los números siguen saliendo con la misma pinta de siempre.
3. **Si la ventana que arma no es la que el umbral supone, no arranca.**
4. **Si el intervalo no cabe en el bin, no arranca.**

Ninguna de las cuatro se puede notar mirando la salida una vez que el
proceso anda. Por eso son todas de arranque y todas ruidosas.

## La verificación no termina al arrancar

El padrón puede cambiar con el proceso vivo: un alta, una baja, una
coordenada corregida. Cada `topology_check_seconds` el servicio relee
`ami_meters`, reconstruye el grafo y recontrasta las huellas. Si cambió,
**se cae**, y volverá a caerse al arrancar hasta que alguien recalibre. Es
lo buscado: seguir andando con el umbral viejo sería peor que no andar.

Una base **inalcanzable** no es lo mismo que una topología cambiada, y no
tumba el servicio: queda como aviso y como métrica. Confundir las dos cosas
haría que un corte de red apagara el monitor.

## El reloj

El ciclo se agenda contra un instante monótono y no acumula deriva: cada
despertar se calcula desde el arranque, no sumando el intervalo al anterior.
Si un ciclo se pasa de largo, el siguiente sale antes en vez de correrse
para siempre.
"""

from __future__ import annotations

import logging
import signal
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from types import FrameType
from typing import Final

from ..db.config import DatabaseSettings
from ..db.meters import load_ami_graph
from ..graph.types import AmiGraph, GraphConfig, MonitorGspError
from ..stream.window import WindowConfig
from .calibration import Calibration, load_calibration
from .fingerprint import graph_fingerprints
from .metrics import MonitorMetrics, NullMetrics
from .mqtt import MqttPublisher, TelemetrySource
from .publisher import CycleDispatcher, DetectionPayload, Publisher
from .runtime import MonitorRuntime, build_runtime
from .settings import MonitorSettings

logger: Final = logging.getLogger(__name__)


class MonitorService:
    """El monitor corriendo: ingesta, ciclo, publicación y verificación.

    Args:
        settings: Configuración del servicio.
        runtime: Ciclo ya armado y verificado.
        dispatcher: Reparto de resultados a los topics.
        source: Ingesta de telemetría, o `None` para alimentarlo a mano.
        metrics: Dónde registrar.
        graph_config: Cómo se construye el grafo en la reverificación. Tiene
            que ser el mismo con el que se armó, o las huellas diferirían
            por la construcción y no por el padrón.
        db_settings: Conexión para releer el padrón.
    """

    def __init__(
        self,
        settings: MonitorSettings,
        runtime: MonitorRuntime,
        dispatcher: CycleDispatcher,
        calibration: Calibration,
        source: TelemetrySource | None = None,
        metrics: MonitorMetrics | None = None,
        graph_config: GraphConfig | None = None,
        db_settings: DatabaseSettings | None = None,
    ) -> None:
        """Guarda las piezas y prepara la señal de parada."""
        self._settings = settings
        self._runtime = runtime
        self._dispatcher = dispatcher
        self._calibration = calibration
        self._source = source
        self._metrics = metrics if metrics is not None else NullMetrics()
        self._graph_config = graph_config
        self._db_settings = db_settings

        self._parar = threading.Event()
        self.cycles = 0
        self.published = 0

    def request_stop(self) -> None:
        """Pide el apagado ordenado. Seguro desde un manejador de señal."""
        self._parar.set()

    def tick(self, now: datetime | None = None) -> int:
        """Corre un ciclo y publica lo que produzca.

        Args:
            now: Instante con el que se cierran los bins. `None` usa el
                reloj.

        Returns:
            Mensajes publicados.
        """
        momento = now if now is not None else datetime.now(UTC)
        ciclo = self._runtime.run_cycle(momento)
        enviados = self._dispatcher.dispatch(ciclo, momento)
        self.cycles += 1
        self.published += enviados
        return enviados

    def verify_topology(self) -> bool:
        """Recontrasta el padrón vivo contra el calibrado.

        Returns:
            `True` si la topología sigue siendo la calibrada, `False` si no
            se pudo verificar porque la base no respondió.

        Raises:
            TopologyMismatchError: Si el grafo vivo cambió. **Es
                bloqueante**: el servicio no puede seguir con el umbral
                viejo.
        """
        try:
            grafo = load_ami_graph(
                self._graph_config,
                self._db_settings,
                zonas=self._settings.zone_filter(),
            )
        except (MonitorGspError, OSError) as exc:
            # Una base inalcanzable no es evidencia de que la topología
            # cambió. Se avisa y se reintenta al siguiente turno.
            self._metrics.observe_topology_check(False)
            logger.warning("no se pudo reverificar la topología: %s", exc)
            return False

        self._calibration.verify_topology(graph_fingerprints(grafo))
        self._metrics.observe_topology_check(True)
        logger.debug("topología reverificada: sigue siendo la calibrada")
        return True

    def run(self) -> None:
        """Bucle principal. Vuelve cuando se pide el apagado.

        Raises:
            TopologyMismatchError: Si el padrón cambia mientras corre.
        """
        if self._source is not None:
            self._source.start()

        intervalo = self._settings.cycle_seconds
        arranque = time.monotonic()
        proxima_verificacion = arranque + self._settings.topology_check_seconds
        n = 0

        logger.info(
            "monitor en marcha: ciclo cada %g s, verificación de topología cada %g s",
            intervalo,
            self._settings.topology_check_seconds,
        )

        # El `finally` cubre la salida por topología cambiada, que es una
        # excepción y no un apagado pedido. Sin él, el proceso se iría
        # dejando el hilo de red de paho vivo y la sesión colgada en el
        # broker hasta que venciera el keepalive.
        try:
            while not self._parar.is_set():
                self.tick()
                if self._source is not None:
                    self._metrics.set_connected(self._source.is_connected)

                ahora = time.monotonic()
                if ahora >= proxima_verificacion:
                    self.verify_topology()
                    proxima_verificacion = ahora + self._settings.topology_check_seconds

                # Contra el arranque y no contra el ciclo anterior: sumar el
                # intervalo al anterior acumularía la duración de cada ciclo
                # como deriva.
                n += 1
                espera = arranque + n * intervalo - time.monotonic()
                if espera > 0:
                    self._parar.wait(espera)
        finally:
            logger.info("monitor detenido tras %d ciclos, %d mensajes", self.cycles, self.published)
            if self._source is not None:
                self._source.stop()


def _resolve(path: Path) -> Path:
    """Resuelve una ruta relativa contra la raíz del repositorio.

    El servicio corre tanto desde un contenedor —con la raíz montada— como
    desde el repositorio, y el defecto de `calibration_path` es relativo.

    Args:
        path: Ruta configurada.

    Returns:
        Ruta absoluta.
    """
    if path.is_absolute():
        return path
    # Seis niveles: service → urbia_monitor_gsp → src → monitor-gsp →
    # services → raíz. Hay un test que lo fija contra el archivo real, y no
    # es paranoia: con `parents[4]` el defecto caía en `services/data/` y el
    # servicio se negaba a arrancar con su propia configuración de fábrica.
    repo = Path(__file__).resolve().parents[5]
    return repo / path


def build_service(
    settings: MonitorSettings,
    publisher: Publisher,
    metrics: MonitorMetrics | None = None,
    graph_config: GraphConfig | None = None,
    window_config: WindowConfig | None = None,
    db_settings: DatabaseSettings | None = None,
    graph: AmiGraph | None = None,
) -> MonitorService:
    """Arma el servicio entero, negándose a arrancar mal.

    Args:
        settings: Configuración del servicio.
        publisher: Adónde van los resultados.
        metrics: Dónde registrar.
        graph_config: Cómo construir el grafo.
        window_config: Parámetros de la ventana.
        db_settings: Conexión a PostgreSQL para leer el padrón.
        graph: Grafo ya construido. Si es `None` se lee de la base. Existe
            para poder armar el servicio en un test sin base.

    Returns:
        El servicio listo para `run()`.

    Raises:
        CalibrationError: Si no hay calibración congelada.
        TopologyMismatchError: Si el grafo vivo no es el calibrado.
        MonitorSettingsError: Si el intervalo no cabe en el bin.
        RuntimeSetupError: Si la ventana no es la que el umbral supone.
    """
    ventana = window_config if window_config is not None else WindowConfig()
    settings.validate_coherence(ventana.bin_seconds)

    calibracion = load_calibration(_resolve(settings.calibration_path))
    if graph is None:
        graph = load_ami_graph(graph_config, db_settings, zonas=settings.zone_filter())

    runtime = build_runtime(graph, calibracion, ventana, metrics)
    dispatcher = CycleDispatcher(
        DetectionPayload(calibracion, graph_fingerprints(graph), settings.top_k),
        publisher,
        settings.mqtt_topic_prefix,
        metrics,
    )
    source = TelemetrySource(
        settings,
        runtime,
        on_connection_change=(metrics.set_connected if metrics is not None else None),
    )

    return MonitorService(
        settings=settings,
        runtime=runtime,
        dispatcher=dispatcher,
        calibration=calibracion,
        source=source,
        metrics=metrics,
        graph_config=graph_config,
        db_settings=db_settings,
    )


def install_signal_handlers(service: MonitorService) -> None:
    """Hace que SIGTERM y SIGINT pidan el apagado ordenado.

    Sin esto `docker stop` mataría el proceso a mitad de un ciclo y dejaría
    la conexión al broker colgando hasta el keepalive.

    Args:
        service: Servicio a detener.
    """

    def _manejar(numero: int, _marco: FrameType | None) -> None:
        logger.info("señal %s recibida, apagando", signal.Signals(numero).name)
        service.request_stop()

    signal.signal(signal.SIGTERM, _manejar)
    signal.signal(signal.SIGINT, _manejar)


def main() -> int:
    """Punto de entrada del proceso.

    Returns:
        Código de salida. Distinto de cero si el servicio se negó a
        arrancar o si la topología cambió mientras corría.
    """
    settings = MonitorSettings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)-8s %(name)s %(message)s",
    )

    from .metrics import PrometheusMetrics, start_metrics_server

    calibracion_path = _resolve(settings.calibration_path)
    metrics = PrometheusMetrics(
        info={
            "calibracion": str(calibracion_path),
            "magnitud": settings.magnitude,
            "ciclo_segundos": f"{settings.cycle_seconds:g}",
            "top_k": "completo" if settings.top_k is None else str(settings.top_k),
        }
    )
    start_metrics_server(settings.metrics_host, settings.metrics_port)
    logger.info("métricas en http://%s:%d/metrics", settings.metrics_host, settings.metrics_port)

    publisher = MqttPublisher(settings)
    try:
        servicio = build_service(settings, publisher, metrics)
    except MonitorGspError:
        logger.exception("el monitor se niega a arrancar")
        return 1

    publisher.start()
    install_signal_handlers(servicio)
    try:
        servicio.run()
    except MonitorGspError:
        logger.exception("el monitor se detuvo")
        return 2
    finally:
        publisher.stop()
    return 0
