"""Métricas Prometheus del monitor.

## Para qué están, más allá de mirar un panel

Estas series son **la línea base contra la cual se va a medir H1**. La
primera línea de contribución del doctorado es bajar el monitor del
datacenter al nodo de borde, y esa afirmación sólo se puede sostener
comparando el mismo servicio corriendo en los dos lados. Sin instrumentar,
la comparación sería anecdótica.

Por eso la métrica que más importa no es el contador de detecciones sino
`urbia_monitor_ciclo_segundos`: es la que dice cuánto cuesta el método, y la
que va a cambiar cuando el proceso se mude a ARM.

## Las dos que hay que vigilar

* **`urbia_monitor_bins_saltados`** distinto de cero significa que el ciclo
  tarda más que el bin y el servicio se atrasa **de forma acumulativa**. No
  se recupera solo. `experiments/ciclo-deteccion/` midió 430× de margen
  sobre neusi-stage; si esto sube, ese margen se acabó.
* **`urbia_monitor_sin_ventana`** cuenta las zonas que no produjeron
  resultado por falta de datos. No es un error del servicio: es la
  consecuencia declarada de no imputar. Pero si crece, el panel de esa zona
  está en blanco y hay que saberlo sin abrir los logs.

## Sobre la cardinalidad

Todo va etiquetado por `zona` y nada por `device_id`. Son seis zonas contra
150 medidores, y los medidores crecen con el despliegue mientras las zonas
no. Un contador por medidor multiplicaría las series por 25 sin responder
ninguna pregunta que el payload publicado no responda mejor.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Final, Protocol

if TYPE_CHECKING:  # pragma: no cover
    # Sólo para anotar: `prometheus_client` es el extra `[service]` y el
    # núcleo no lo necesita. Con `from __future__ import annotations` la
    # anotación no se evalúa en tiempo de ejecución.
    from wsgiref.simple_server import WSGIServer

    from prometheus_client import CollectorRegistry

from ..stream.window import BinIncompleteError, Window

_NAMESPACE: Final = "urbia_monitor"

_BUCKETS_CICLO: Final = (
    0.0005,
    0.001,
    0.002,
    0.005,
    0.01,
    0.05,
    0.1,
    0.5,
    1.0,
    3.0,
    6.0,
)
"""Bordes centrados en lo medido y extendidos hasta donde duele.

El p99 medido es 1,39 ms, así que la resolución fina va entre 0,5 y 5 ms.
Los últimos dos bordes son los que importan operativamente: 3 s es el
intervalo del ciclo y 6 s el ancho del bin. Un ciclo que caiga en el último
bucket es un servicio que ya está perdiendo bins.
"""


class MonitorMetrics(Protocol):
    """Lo que el ciclo necesita poder registrar.

    Es un `Protocol` y no una clase concreta para que los tests puedan
    correr el ciclo sin `prometheus_client` instalado y sin registro
    global, que es estado compartido entre tests.
    """

    def observe_cycle(self, seconds: float) -> None:
        """Registra la duración de un ciclo completo."""
        ...

    def observe_window(self, window: Window, statistic: float, threshold: float) -> None:
        """Registra una ventana que sí se produjo."""
        ...

    def observe_detection(self, zona: str) -> None:
        """Registra una detección emitida."""
        ...

    def observe_missing(self, motivo: BinIncompleteError, n_meters: int) -> None:
        """Registra una zona que no produjo resultado por falta de datos."""
        ...

    def observe_ingest(self, aceptados: int, descartados: dict[str, int]) -> None:
        """Registra el resultado de la ingesta acumulada."""
        ...

    def observe_publish_failure(self) -> None:
        """Registra una publicación que no salió."""
        ...

    def set_connected(self, conectado: bool) -> None:
        """Refleja el estado de la conexión al broker."""
        ...

    def observe_topology_check(self, ok: bool) -> None:
        """Registra una reverificación de la topología."""
        ...


class NullMetrics:
    """Implementación que no registra nada.

    Para los tests del ciclo y para correr el núcleo sin el extra
    `[service]` instalado.
    """

    def observe_cycle(self, seconds: float) -> None:
        """No hace nada."""

    def observe_window(self, window: Window, statistic: float, threshold: float) -> None:
        """No hace nada."""

    def observe_detection(self, zona: str) -> None:
        """No hace nada."""

    def observe_missing(self, motivo: BinIncompleteError, n_meters: int) -> None:
        """No hace nada."""

    def observe_ingest(self, aceptados: int, descartados: dict[str, int]) -> None:
        """No hace nada."""

    def observe_publish_failure(self) -> None:
        """No hace nada."""

    def set_connected(self, conectado: bool) -> None:
        """No hace nada."""

    def observe_topology_check(self, ok: bool) -> None:
        """No hace nada."""


class PrometheusMetrics:
    """Métricas reales, sobre un registro de `prometheus_client`.

    Args:
        registry: Registro donde declarar las series. `None` usa el global.
            Los tests pasan uno propio: el global es estado compartido y
            redeclarar una serie en él revienta.
        info: Pares clave-valor que describen la configuración con la que
            corre el proceso —versión de calibración, topología, intervalo—.
            Van como etiquetas de una serie `_info` porque son lo que
            permite leer el resto sin adivinar bajo qué punto de operación
            se produjo.

    Raises:
        ImportError: Si `prometheus_client` no está instalado. Es el extra
            `[service]`; el núcleo no lo necesita.
    """

    def __init__(
        self,
        registry: CollectorRegistry | None = None,
        info: dict[str, str] | None = None,
    ) -> None:
        """Declara las series."""
        from prometheus_client import REGISTRY, Counter, Gauge, Histogram, Info

        reg = REGISTRY if registry is None else registry

        self._ciclo = Histogram(
            f"{_NAMESPACE}_ciclo_segundos",
            "Duración de un ciclo de detección sobre todas las zonas.",
            buckets=_BUCKETS_CICLO,
            registry=reg,
        )
        self._ventanas = Counter(
            f"{_NAMESPACE}_ventanas",
            "Ventanas densas producidas y analizadas.",
            ["zona"],
            registry=reg,
        )
        self._detecciones = Counter(
            f"{_NAMESPACE}_detecciones",
            "Ventanas en las que el estadístico superó el umbral.",
            ["zona"],
            registry=reg,
        )
        self._sin_ventana = Counter(
            f"{_NAMESPACE}_sin_ventana",
            "Ventanas no producidas por falta de datos, por motivo.",
            ["zona", "motivo"],
            registry=reg,
        )
        self._bins_saltados = Counter(
            f"{_NAMESPACE}_bins_saltados",
            "Bins que se cerraron sin que el servicio los mirara. Debe ser cero.",
            ["zona"],
            registry=reg,
        )
        self._medidores_presentes = Gauge(
            f"{_NAMESPACE}_medidores_presentes",
            "Medidores con dato en la última ventana intentada.",
            ["zona"],
            registry=reg,
        )
        self._medidores_esperados = Gauge(
            f"{_NAMESPACE}_medidores_esperados",
            "Medidores que la zona necesita para producir una ventana.",
            ["zona"],
            registry=reg,
        )
        self._estadistico = Gauge(
            f"{_NAMESPACE}_estadistico",
            "Mayor contraste de la última ventana, en unidades de σ.",
            ["zona"],
            registry=reg,
        )
        self._umbral = Gauge(
            f"{_NAMESPACE}_umbral",
            "Corte congelado con el que se comparó.",
            ["zona"],
            registry=reg,
        )
        self._mensajes = Counter(
            f"{_NAMESPACE}_mensajes",
            "Lecturas procesadas por la ingesta, por resultado.",
            ["resultado"],
            registry=reg,
        )
        self._publicaciones_fallidas = Counter(
            f"{_NAMESPACE}_publicaciones_fallidas",
            "Publicaciones que el broker no aceptó.",
            registry=reg,
        )
        self._conectado = Gauge(
            f"{_NAMESPACE}_broker_conectado",
            "1 si la conexión con el broker MQTT está viva.",
            registry=reg,
        )
        self._verificaciones = Counter(
            f"{_NAMESPACE}_verificaciones_topologia",
            "Reverificaciones de la topología viva contra la calibrada.",
            ["resultado"],
            registry=reg,
        )
        self._info = Info(
            f"{_NAMESPACE}_configuracion",
            "Punto de operación con el que corre este proceso.",
            registry=reg,
        )
        if info:
            self._info.info(info)

    def observe_cycle(self, seconds: float) -> None:
        """Registra la duración de un ciclo completo.

        Args:
            seconds: Duración de reloj.
        """
        self._ciclo.observe(seconds)

    def observe_window(self, window: Window, statistic: float, threshold: float) -> None:
        """Registra una ventana producida.

        Args:
            window: La ventana densa.
            statistic: Mayor contraste hallado.
            threshold: Corte con el que se comparó.
        """
        zona = window.zona
        self._ventanas.labels(zona=zona).inc()
        self._estadistico.labels(zona=zona).set(statistic)
        self._umbral.labels(zona=zona).set(threshold)
        presentes = int(window.matrix.shape[1])
        self._medidores_presentes.labels(zona=zona).set(presentes)
        self._medidores_esperados.labels(zona=zona).set(presentes)
        if window.skipped_bins:
            self._bins_saltados.labels(zona=zona).inc(window.skipped_bins)

    def observe_detection(self, zona: str) -> None:
        """Registra una detección emitida.

        Args:
            zona: Zona que la produjo.
        """
        self._detecciones.labels(zona=zona).inc()

    def observe_missing(self, motivo: BinIncompleteError, n_meters: int) -> None:
        """Registra una zona sin resultado por falta de datos.

        Args:
            motivo: El error con su detalle.
            n_meters: Medidores que la zona necesita.
        """
        self._sin_ventana.labels(zona=motivo.zona, motivo=motivo.motivo).inc()
        self._medidores_esperados.labels(zona=motivo.zona).set(n_meters)
        self._medidores_presentes.labels(zona=motivo.zona).set(
            n_meters - len(motivo.missing_device_ids)
        )

    def observe_ingest(self, aceptados: int, descartados: dict[str, int]) -> None:
        """Registra el resultado acumulado de la ingesta.

        Args:
            aceptados: Lecturas que ocuparon una celda desde la última vez.
            descartados: Lecturas descartadas por motivo.
        """
        if aceptados:
            self._mensajes.labels(resultado="aceptado").inc(aceptados)
        for motivo, cuantos in descartados.items():
            if cuantos:
                self._mensajes.labels(resultado=motivo).inc(cuantos)

    def observe_publish_failure(self) -> None:
        """Registra una publicación fallida."""
        self._publicaciones_fallidas.inc()

    def set_connected(self, conectado: bool) -> None:
        """Refleja el estado de la conexión al broker.

        Args:
            conectado: Si la conexión está viva.
        """
        self._conectado.set(1.0 if conectado else 0.0)

    def observe_topology_check(self, ok: bool) -> None:
        """Registra una reverificación de la topología.

        Args:
            ok: Si la topología viva sigue siendo la calibrada.
        """
        self._verificaciones.labels(resultado="ok" if ok else "fallo").inc()


def start_metrics_server(
    host: str,
    port: int,
    registry: CollectorRegistry | None = None,
) -> tuple[WSGIServer, threading.Thread]:
    """Levanta el exportador HTTP que Prometheus va a raspar.

    El servidor corre en un hilo demonio. Se devuelve junto con su hilo en
    vez de descartarlos: sin una referencia no hay forma de apagarlo, y un
    test que lo levantara dejaría el puerto ocupado para los siguientes.

    Args:
        host: Interfaz en la que escuchar.
        port: Puerto. `0` toma uno libre, que es lo que hacen los tests.
        registry: Registro a exponer. `None` usa el global.

    Returns:
        El servidor y el hilo que lo atiende.

    Raises:
        ImportError: Si `prometheus_client` no está instalado.
    """
    from prometheus_client import REGISTRY, start_http_server

    return start_http_server(port, addr=host, registry=REGISTRY if registry is None else registry)
