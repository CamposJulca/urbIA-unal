"""Tests de las series de Prometheus.

Estas series son **la línea base contra la que se va a medir H1**: bajar el
monitor al nodo de borde sólo se puede sostener comparando el mismo servicio
en los dos lados. Un contador que no se incrementa arruina la comparación
sin que nada falle, así que lo que se verifica acá es que cada suceso del
ciclo llegue de verdad al registro.

Cada test usa **su propio `CollectorRegistry`**. El registro global es
estado compartido entre tests y redeclarar una serie en él revienta.
"""

from __future__ import annotations

import urllib.request
from datetime import UTC, datetime

import numpy as np
import pytest
from prometheus_client import CollectorRegistry

from conftest_service import calibracion_versionada, despues_de_la_ventana, llenar_ventana
from urbia_monitor_gsp.graph.builder import build_ami_graph
from urbia_monitor_gsp.graph.types import AmiGraph, GraphConfig, MeterNode
from urbia_monitor_gsp.service.calibration import Calibration
from urbia_monitor_gsp.service.metrics import (
    NullMetrics,
    PrometheusMetrics,
    start_metrics_server,
)
from urbia_monitor_gsp.service.runtime import build_runtime
from urbia_monitor_gsp.stream.window import BinIncompleteError, Window


@pytest.fixture(scope="module")
def grafo(manizales: list[MeterNode]) -> AmiGraph:
    return build_ami_graph(manizales, GraphConfig())


@pytest.fixture(scope="module")
def calibracion() -> Calibration:
    return calibracion_versionada()


@pytest.fixture
def registro() -> CollectorRegistry:
    return CollectorRegistry()


@pytest.fixture
def metricas(registro: CollectorRegistry) -> PrometheusMetrics:
    return PrometheusMetrics(registro)


def valor(registro: CollectorRegistry, nombre: str, **etiquetas: str) -> float | None:
    """Lee una muestra del registro.

    Args:
        registro: Registro a consultar.
        nombre: Nombre completo de la serie.
        etiquetas: Etiquetas que la identifican.

    Returns:
        El valor, o `None` si la serie no existe todavía.
    """
    return registro.get_sample_value(nombre, etiquetas or None)


def falta_uno(zona: str) -> BinIncompleteError:
    """Construye el motivo de una zona a la que le falta un medidor.

    Args:
        zona: Zona afectada.

    Returns:
        El motivo, ya formado.
    """
    momento = datetime(2026, 8, 9, 12, 0, 0, tzinfo=UTC)
    return BinIncompleteError(
        zona=zona,
        motivo="bins_incompletos",
        first_bin=0,
        last_bin=15,
        start_utc=momento,
        end_utc=momento,
        incomplete_bins=3,
        missing_device_ids=("urbia-cen-mon-0007",),
    )


# ────────────────────────────────────────────────────── el ciclo


def test_la_duracion_del_ciclo_se_registra(
    metricas: PrometheusMetrics, registro: CollectorRegistry
) -> None:
    """La duración del ciclo se acumula en el histograma.

    Es la métrica que más importa: la que dice cuánto cuesta el método, y la
    que va a cambiar cuando el proceso se mude a ARM.
    """
    metricas.observe_cycle(0.0012)
    metricas.observe_cycle(0.0018)

    assert valor(registro, "urbia_monitor_ciclo_segundos_count") == 2.0
    assert valor(registro, "urbia_monitor_ciclo_segundos_sum") == pytest.approx(0.0030)


def test_los_buckets_dan_resolucion_donde_se_midio(
    metricas: PrometheusMetrics, registro: CollectorRegistry
) -> None:
    """Los bordes dan resolución donde está lo medido.

    El p99 medido es 1,39 ms, así que el bucket de 2 ms tiene que separarlo
    del de 1 ms; si no, la serie no distingue nada en el rango que importa.
    """
    metricas.observe_cycle(0.00139)

    assert valor(registro, "urbia_monitor_ciclo_segundos_bucket", le="0.001") == 0.0
    assert valor(registro, "urbia_monitor_ciclo_segundos_bucket", le="0.002") == 1.0


def test_un_ciclo_que_pasa_del_bin_cae_en_el_ultimo_bucket(
    metricas: PrometheusMetrics, registro: CollectorRegistry
) -> None:
    """6 s es el ancho del bin: un ciclo ahí ya está perdiendo bins."""
    metricas.observe_cycle(7.0)

    assert valor(registro, "urbia_monitor_ciclo_segundos_bucket", le="6.0") == 0.0
    assert valor(registro, "urbia_monitor_ciclo_segundos_bucket", le="+Inf") == 1.0


# ─────────────────────────────────────── ventanas y detecciones


def test_una_ventana_registra_su_estadistico_y_su_umbral(
    grafo: AmiGraph, calibracion: Calibration, registro: CollectorRegistry
) -> None:
    metricas = PrometheusMetrics(registro)
    runtime = build_runtime(grafo, calibracion, None, metricas)
    llenar_ventana(runtime, grafo)
    runtime.run_cycle(despues_de_la_ventana())

    assert valor(registro, "urbia_monitor_ventanas_total", zona="centro") == 1.0
    assert valor(registro, "urbia_monitor_umbral", zona="centro") is not None
    assert valor(registro, "urbia_monitor_estadistico", zona="centro") is not None


def test_una_deteccion_incrementa_su_contador(
    metricas: PrometheusMetrics, registro: CollectorRegistry
) -> None:
    metricas.observe_detection("palermo")
    metricas.observe_detection("palermo")

    assert valor(registro, "urbia_monitor_detecciones_total", zona="palermo") == 2.0


def test_una_zona_sin_datos_se_cuenta_por_motivo(
    metricas: PrometheusMetrics, registro: CollectorRegistry
) -> None:
    """Una zona sin datos se cuenta separada por motivo.

    No es un error del servicio: es la consecuencia declarada de no imputar.
    Pero si crece, el panel de esa zona está en blanco y hay que saberlo sin
    abrir los logs.
    """
    metricas.observe_missing(falta_uno("chipre"), n_meters=25)

    assert (
        valor(registro, "urbia_monitor_sin_ventana_total", zona="chipre", motivo="bins_incompletos")
        == 1.0
    )
    assert valor(registro, "urbia_monitor_medidores_esperados", zona="chipre") == 25.0
    assert valor(registro, "urbia_monitor_medidores_presentes", zona="chipre") == 24.0


def test_un_bin_saltado_se_registra(
    metricas: PrometheusMetrics, registro: CollectorRegistry
) -> None:
    """Es la serie que hay que vigilar.

    Distinta de cero significa que el ciclo tarda más que el bin y que el
    atraso se acumula. No se recupera solo.
    """
    momento = datetime(2026, 8, 9, 12, 0, 0, tzinfo=UTC)
    ventana = Window(
        zona="centro",
        matrix=np.zeros((16, 25)),
        first_bin=0,
        last_bin=15,
        start_utc=momento,
        end_utc=momento,
        skipped_bins=2,
    )
    metricas.observe_window(ventana, statistic=1.0, threshold=3.0)

    assert valor(registro, "urbia_monitor_bins_saltados_total", zona="centro") == 2.0


def test_el_exportador_http_se_levanta_y_se_puede_raspar(
    registro: CollectorRegistry,
) -> None:
    """Prometheus raspa este endpoint cada 15 s.

    Si no levanta, no hay línea
    base contra la que medir H1.
    """
    PrometheusMetrics(registro).observe_cycle(0.001)
    servidor, hilo = start_metrics_server("127.0.0.1", 0, registro)
    try:
        puerto = servidor.server_port
        with urllib.request.urlopen(f"http://127.0.0.1:{puerto}/metrics", timeout=5) as r:
            cuerpo = r.read().decode("utf-8")
    finally:
        servidor.shutdown()
        hilo.join(timeout=5.0)

    assert "urbia_monitor_ciclo_segundos_count" in cuerpo


def test_los_bins_saltados_arrancan_ausentes_y_deben_quedarse_asi(
    grafo: AmiGraph, calibracion: Calibration, registro: CollectorRegistry
) -> None:
    """Distinto de cero significa atraso acumulativo, que no se recupera solo."""
    metricas = PrometheusMetrics(registro)
    runtime = build_runtime(grafo, calibracion, None, metricas)
    llenar_ventana(runtime, grafo)
    runtime.run_cycle(despues_de_la_ventana())

    assert valor(registro, "urbia_monitor_bins_saltados_total", zona="centro") is None


# ────────────────────────────────────────────────────── la ingesta


def test_la_ingesta_se_cuenta_por_resultado(
    metricas: PrometheusMetrics, registro: CollectorRegistry
) -> None:
    metricas.observe_ingest(120, {"tarde": 3, "desconocido": 0, "futuro": 1, "superado": 0})

    assert valor(registro, "urbia_monitor_mensajes_total", resultado="aceptado") == 120.0
    assert valor(registro, "urbia_monitor_mensajes_total", resultado="tarde") == 3.0
    assert valor(registro, "urbia_monitor_mensajes_total", resultado="futuro") == 1.0


def test_un_motivo_sin_descartes_no_crea_serie(
    metricas: PrometheusMetrics, registro: CollectorRegistry
) -> None:
    """Series en cero que nadie miró son ruido en el panel."""
    metricas.observe_ingest(10, {"tarde": 0})

    assert valor(registro, "urbia_monitor_mensajes_total", resultado="tarde") is None


def test_un_ciclo_sin_lecturas_no_incrementa_nada(
    metricas: PrometheusMetrics, registro: CollectorRegistry
) -> None:
    metricas.observe_ingest(0, {"tarde": 0})

    assert valor(registro, "urbia_monitor_mensajes_total", resultado="aceptado") is None


# ───────────────────────────────────────── conexión y topología


def test_el_estado_del_broker_se_refleja(
    metricas: PrometheusMetrics, registro: CollectorRegistry
) -> None:
    metricas.set_connected(True)
    assert valor(registro, "urbia_monitor_broker_conectado") == 1.0

    metricas.set_connected(False)
    assert valor(registro, "urbia_monitor_broker_conectado") == 0.0


def test_las_verificaciones_de_topologia_se_separan_por_desenlace(
    metricas: PrometheusMetrics, registro: CollectorRegistry
) -> None:
    """Los dos desenlaces de la verificación van en etiquetas distintas.

    Una base inalcanzable no es una topología cambiada, y la serie tiene que
    poder separarlas: la primera se reintenta, la segunda tumba el servicio.
    """
    metricas.observe_topology_check(True)
    metricas.observe_topology_check(False)

    assert valor(registro, "urbia_monitor_verificaciones_topologia_total", resultado="ok") == 1.0
    assert valor(registro, "urbia_monitor_verificaciones_topologia_total", resultado="fallo") == 1.0


def test_las_publicaciones_fallidas_se_cuentan(
    metricas: PrometheusMetrics, registro: CollectorRegistry
) -> None:
    metricas.observe_publish_failure()
    assert valor(registro, "urbia_monitor_publicaciones_fallidas_total") == 1.0


# ─────────────────────────────────────── el punto de operación


def test_la_configuracion_viaja_como_etiquetas(registro: CollectorRegistry) -> None:
    """El punto de operación viaja como etiquetas de una serie `_info`.

    Sin esto habría que adivinar bajo qué configuración se produjo el resto
    de las series, que es exactamente el error de `ESTADO.md` §5.3.
    """
    PrometheusMetrics(registro, info={"calibracion": "manizales-scan-v1", "magnitud": "voltaje_v"})

    assert (
        valor(
            registro,
            "urbia_monitor_configuracion_info",
            calibracion="manizales-scan-v1",
            magnitud="voltaje_v",
        )
        == 1.0
    )


def test_sin_info_las_series_se_declaran_igual(registro: CollectorRegistry) -> None:
    PrometheusMetrics(registro)
    assert valor(registro, "urbia_monitor_ciclo_segundos_count") == 0.0


def test_la_cardinalidad_va_por_zona_y_no_por_medidor(
    grafo: AmiGraph, calibracion: Calibration, registro: CollectorRegistry
) -> None:
    """Nada se etiqueta por medidor.

    Seis zonas contra 150 medidores, y los medidores crecen con el despliegue
    mientras las zonas no. Un contador por medidor multiplicaría las series
    por 25 sin responder nada que el payload publicado no responda mejor.
    """
    metricas = PrometheusMetrics(registro)
    runtime = build_runtime(grafo, calibracion, None, metricas)
    llenar_ventana(runtime, grafo)
    runtime.run_cycle(despues_de_la_ventana())

    muestras = [s for familia in registro.collect() for s in familia.samples]
    assert muestras, "el registro quedó vacío: el ciclo no registró nada"

    zonas_vistas = {s.labels["zona"] for s in muestras if "zona" in s.labels}
    assert zonas_vistas == set(runtime.zonas)
    assert not any("device_id" in s.labels for s in muestras)


# ──────────────────────────────────────────────── la implementación nula


def test_la_implementacion_nula_acepta_todo_sin_registrar() -> None:
    """Existe para correr el núcleo sin el extra `[service]` instalado."""
    nula = NullMetrics()
    nula.observe_cycle(1.0)
    nula.observe_detection("centro")
    nula.observe_missing(falta_uno("centro"), 25)
    nula.observe_ingest(5, {"tarde": 1})
    nula.observe_publish_failure()
    nula.set_connected(True)
    nula.observe_topology_check(False)
