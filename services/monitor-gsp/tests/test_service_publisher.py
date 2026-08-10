"""Tests de qué publica el monitor y en qué forma.

Sin broker: `CollectingPublisher` acumula en memoria lo que se mandaría.
Lo que se verifica acá es el **contrato con el consumidor** —el backend que
va a leer estos topics, y el panel Edge que va a mostrarlos—, así que los
tests miran la forma del payload y no sólo que no explote.

Dos cosas se prueban con más insistencia que el resto, porque las dos son
decisiones que el ciclo podría desandar sin que nada avise:

* que la zona **sin datos publique su motivo**, en vez de callarse;
* que cada mensaje lleve la **procedencia del umbral**, que es lo que
  permite auditar después bajo qué condiciones se decidió (`ESTADO.md` §5.3).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import numpy as np
import pytest

from conftest_service import (
    calibracion_versionada,
    despues_de_la_ventana,
    llenar_ventana,
)
from urbia_monitor_gsp.graph.builder import build_ami_graph
from urbia_monitor_gsp.graph.types import AmiGraph, GraphConfig, MeterNode
from urbia_monitor_gsp.service.calibration import Calibration
from urbia_monitor_gsp.service.fingerprint import graph_fingerprints
from urbia_monitor_gsp.service.publisher import (
    CollectingPublisher,
    CycleDispatcher,
    DetectionPayload,
    Publisher,
    PublishError,
    encode,
)
from urbia_monitor_gsp.service.runtime import (
    CycleResult,
    MonitorRuntime,
    ZoneResult,
    build_runtime,
)

EMITIDO = datetime(2026, 8, 9, 12, 5, 0, tzinfo=UTC)
PREFIJO = "urbia/manizales/monitor"


@pytest.fixture(scope="module")
def grafo(manizales: list[MeterNode]) -> AmiGraph:
    return build_ami_graph(manizales, GraphConfig())


@pytest.fixture(scope="module")
def calibracion() -> Calibration:
    return calibracion_versionada()


@pytest.fixture
def runtime(grafo: AmiGraph, calibracion: Calibration) -> MonitorRuntime:
    return build_runtime(grafo, calibracion)


@pytest.fixture
def payload(grafo: AmiGraph, calibracion: Calibration) -> DetectionPayload:
    return DetectionPayload(calibracion, graph_fingerprints(grafo))


def repartir(ciclo: CycleResult, payload: DetectionPayload) -> CollectingPublisher:
    """Reparte un ciclo a un publicador en memoria.

    Args:
        ciclo: Resultado a repartir.
        payload: Constructor de cuerpos.

    Returns:
        El publicador con lo que se habría mandado.
    """
    recolector = CollectingPublisher()
    CycleDispatcher(payload, recolector, PREFIJO).dispatch(ciclo, EMITIDO)
    return recolector


class PublicadorRoto(Publisher):
    """Falla siempre, como un broker caído."""

    def __init__(self) -> None:
        self.intentos = 0

    def publish(self, topic: str, payload: dict[str, object]) -> None:
        self.intentos += 1
        raise PublishError(f"el broker no aceptó {topic}")


class ContadorDeFallos:
    """Registra sólo las publicaciones fallidas; el resto no hace nada."""

    def __init__(self) -> None:
        self.fallos = 0

    def observe_cycle(self, seconds: float) -> None: ...
    def observe_window(self, window: object, statistic: float, threshold: float) -> None: ...
    def observe_detection(self, zona: str) -> None: ...
    def observe_missing(self, motivo: object, n_meters: int) -> None: ...
    def observe_ingest(self, aceptados: int, descartados: dict[str, int]) -> None: ...
    def set_connected(self, conectado: bool) -> None: ...
    def observe_topology_check(self, ok: bool) -> None: ...

    def observe_publish_failure(self) -> None:
        self.fallos += 1


# ────────────────────────────────────────────────── la ventana analizada


def test_cada_ventana_se_publica_aunque_no_haya_deteccion(
    runtime: MonitorRuntime, grafo: AmiGraph, payload: DetectionPayload
) -> None:
    """La ventana se publica haya o no detección.

    Publicar sólo las detecciones dejaría un registro en el que "no pasó
    nada" y "el detector estaba mirando para otro lado" se ven igual: las
    dos cosas son silencio.
    """
    llenar_ventana(runtime, grafo)
    ciclo = runtime.run_cycle(despues_de_la_ventana())
    assert ciclo.detections == ()

    topics = repartir(ciclo, payload).topics()
    assert len(topics) == 6
    assert all(t.startswith(f"{PREFIJO}/ventana/") for t in topics)


def test_el_cuerpo_de_la_ventana_trae_la_ventana_y_el_estadistico(
    runtime: MonitorRuntime, grafo: AmiGraph, payload: DetectionPayload
) -> None:
    llenar_ventana(runtime, grafo)
    ciclo = runtime.run_cycle(despues_de_la_ventana())
    _, cuerpo = repartir(ciclo, payload).messages[0]

    assert cuerpo["schema"] == "urbia-monitor-ventana-v1"
    assert cuerpo["emitido_utc"] == EMITIDO.isoformat()
    assert cuerpo["ventana"]["bins"] == 16
    assert cuerpo["ventana"]["skipped_bins"] == 0

    deteccion = cuerpo["deteccion"]
    assert deteccion["zona"] == cuerpo["zona"]
    assert deteccion["detected"] is False
    assert deteccion["statistic"] < deteccion["threshold"]
    assert deteccion["candidatas_evaluadas"] == len(deteccion["ranking"])


def test_cada_mensaje_trae_la_procedencia_del_umbral(
    runtime: MonitorRuntime, grafo: AmiGraph, payload: DetectionPayload, calibracion: Calibration
) -> None:
    """Un corte sin procedencia no se puede auditar después.

    Es la trampa de
    `ESTADO.md` §5.3: la cifra viaja pegada a su configuración o no viaja.
    """
    llenar_ventana(runtime, grafo)
    ciclo = runtime.run_cycle(despues_de_la_ventana())
    _, cuerpo = repartir(ciclo, payload).messages[0]

    procedencia = cuerpo["procedencia"]
    assert procedencia["calibracion"] == calibracion.version
    assert procedencia["magnitud"] == calibracion.magnitude
    assert procedencia["topologia"] == calibracion.topology
    assert procedencia["fpr_target"] > 0.0
    assert procedencia["sigma_spatial"] > 0.0
    assert len(procedencia["fingerprint"]) > 8


def test_la_huella_publicada_es_la_del_grafo_vivo(
    runtime: MonitorRuntime, grafo: AmiGraph, payload: DetectionPayload
) -> None:
    """La huella publicada es la del grafo vivo, no la que el archivo declara.

    Si difirieran, el servicio no habría arrancado; publicar la viva es lo
    que permite comprobarlo desde afuera.
    """
    huellas = graph_fingerprints(grafo)
    llenar_ventana(runtime, grafo)
    ciclo = runtime.run_cycle(despues_de_la_ventana())

    for topic, cuerpo in repartir(ciclo, payload).messages:
        zona = topic.rsplit("/", 1)[1]
        assert cuerpo["procedencia"]["fingerprint"] == huellas[zona]


# ────────────────────────────────────────────────────────── la detección


def test_una_deteccion_sale_por_los_dos_topics(
    runtime: MonitorRuntime, grafo: AmiGraph, payload: DetectionPayload
) -> None:
    """Quien alerta no debería parsear 5 kB/s para hallar un evento por hora."""
    zona = grafo.zones["palermo"]
    vecinos = tuple(zona.device_ids[i] for i in np.flatnonzero(zona.adjacency[0] > 0.0).tolist())
    grupo = (zona.device_ids[0], *vecinos)

    llenar_ventana(runtime, grafo, desplazar={"palermo": (grupo, 12.0)})
    ciclo = runtime.run_cycle(despues_de_la_ventana())
    topics = repartir(ciclo, payload).topics()

    assert f"{PREFIJO}/ventana/palermo" in topics
    assert f"{PREFIJO}/deteccion/palermo" in topics


def test_los_dos_topics_llevan_el_mismo_cuerpo(
    runtime: MonitorRuntime, grafo: AmiGraph, payload: DetectionPayload
) -> None:
    zona = grafo.zones["palermo"]
    vecinos = tuple(zona.device_ids[i] for i in np.flatnonzero(zona.adjacency[0] > 0.0).tolist())
    grupo = (zona.device_ids[0], *vecinos)

    llenar_ventana(runtime, grafo, desplazar={"palermo": (grupo, 12.0)})
    ciclo = runtime.run_cycle(despues_de_la_ventana())
    mensajes = dict(repartir(ciclo, payload).messages)

    assert mensajes[f"{PREFIJO}/ventana/palermo"] == mensajes[f"{PREFIJO}/deteccion/palermo"]


# ──────────────────────────────────────────────────── la zona sin datos


def test_una_zona_sin_datos_publica_el_motivo(
    runtime: MonitorRuntime, grafo: AmiGraph, payload: DetectionPayload
) -> None:
    """La zona sin datos publica por qué no produjo resultado.

    Su silencio es indistinguible del silencio de una zona tranquila.
    Publicar el motivo es lo que vuelve visible el problema en vez de
    esconderlo detrás de una detección degradada.
    """
    ausente = grafo.zones["chipre"].device_ids[3]
    llenar_ventana(runtime, grafo, omitir={"chipre": (ausente,)})
    ciclo = runtime.run_cycle(despues_de_la_ventana())

    mensajes = dict(repartir(ciclo, payload).messages)
    cuerpo = mensajes[f"{PREFIJO}/sin-ventana/chipre"]

    assert cuerpo["schema"] == "urbia-monitor-sin-ventana-v1"
    assert cuerpo["sin_ventana"]["motivo"] == "bins_incompletos"
    assert cuerpo["sin_ventana"]["medidores_faltantes"] == [ausente]
    assert "procedencia" in cuerpo


def test_una_zona_sin_datos_no_publica_deteccion(
    runtime: MonitorRuntime, grafo: AmiGraph, payload: DetectionPayload
) -> None:
    """No se imputa ni se excluye: no hay resultado que publicar."""
    ausente = grafo.zones["chipre"].device_ids[3]
    llenar_ventana(runtime, grafo, omitir={"chipre": (ausente,)})
    ciclo = runtime.run_cycle(despues_de_la_ventana())

    topics = repartir(ciclo, payload).topics()
    assert f"{PREFIJO}/ventana/chipre" not in topics
    assert f"{PREFIJO}/deteccion/chipre" not in topics


def test_un_ciclo_sin_bin_nuevo_no_publica_nada(
    runtime: MonitorRuntime, grafo: AmiGraph, payload: DetectionPayload
) -> None:
    llenar_ventana(runtime, grafo)
    momento = despues_de_la_ventana()
    runtime.run_cycle(momento)
    assert repartir(runtime.run_cycle(momento), payload).messages == []


# ─────────────────────────────────────────────────────────── el ranking


def test_el_defecto_publica_el_ranking_completo(
    runtime: MonitorRuntime, grafo: AmiGraph, payload: DetectionPayload
) -> None:
    """Guardar sólo la ganadora impide reconstruir el punto de operación."""
    llenar_ventana(runtime, grafo)
    ciclo = runtime.run_cycle(despues_de_la_ventana())
    _, cuerpo = repartir(ciclo, payload).messages[0]
    assert len(cuerpo["deteccion"]["ranking"]) > 10


def test_top_k_recorta_el_ranking_sin_tocar_el_resto(
    runtime: MonitorRuntime, grafo: AmiGraph, calibracion: Calibration
) -> None:
    """Recortar el ranking no altera nada más del cuerpo.

    `top_k` existe para cuando la topología crezca —el tamaño está medido en
    `experiments/ciclo-deteccion/` §6— y no es una decisión del detector.
    """
    llenar_ventana(runtime, grafo)
    ciclo = runtime.run_cycle(despues_de_la_ventana())
    huellas = graph_fingerprints(grafo)

    completo = repartir(ciclo, DetectionPayload(calibracion, huellas, None)).messages[0][1]
    recortado = repartir(ciclo, DetectionPayload(calibracion, huellas, 3)).messages[0][1]

    assert len(recortado["deteccion"]["ranking"]) == 3
    assert len(completo["deteccion"]["ranking"]) > 3
    assert recortado["deteccion"]["ranking"] == completo["deteccion"]["ranking"][:3]
    assert recortado["procedencia"] == completo["procedencia"]
    assert recortado["ventana"] == completo["ventana"]


def test_top_k_cero_deja_el_cuerpo_sin_ranking(
    runtime: MonitorRuntime, grafo: AmiGraph, calibracion: Calibration
) -> None:
    llenar_ventana(runtime, grafo)
    ciclo = runtime.run_cycle(despues_de_la_ventana())
    payload = DetectionPayload(calibracion, graph_fingerprints(grafo), 0)
    _, cuerpo = repartir(ciclo, payload).messages[0]
    assert cuerpo["deteccion"]["ranking"] == []


# ──────────────────────────────────────────────── el broker que se cae


def test_un_broker_caido_no_tumba_el_ciclo(
    runtime: MonitorRuntime, grafo: AmiGraph, payload: DetectionPayload
) -> None:
    """La ventana siguiente llega en 6 s: propagar el fallo acumularía atraso."""
    llenar_ventana(runtime, grafo)
    ciclo = runtime.run_cycle(despues_de_la_ventana())

    roto = PublicadorRoto()
    contador = ContadorDeFallos()
    dispatcher = CycleDispatcher(payload, roto, PREFIJO, contador)  # type: ignore[arg-type]
    enviados = dispatcher.dispatch(ciclo, EMITIDO)

    assert enviados == 6
    assert roto.intentos == 6
    assert dispatcher.failures == 6


def test_una_publicacion_fallida_queda_en_las_metricas(
    runtime: MonitorRuntime, grafo: AmiGraph, payload: DetectionPayload
) -> None:
    """La publicación fallida llega a las métricas.

    Un monitor que dejó de publicar se ve desde afuera igual que uno que no
    tiene nada que decir. La métrica es lo único que los separa.
    """
    llenar_ventana(runtime, grafo)
    ciclo = runtime.run_cycle(despues_de_la_ventana())

    contador = ContadorDeFallos()
    CycleDispatcher(payload, PublicadorRoto(), PREFIJO, contador).dispatch(ciclo, EMITIDO)  # type: ignore[arg-type]
    assert contador.fallos == 6


def test_sin_metricas_el_dispatcher_reparte_igual(
    runtime: MonitorRuntime, grafo: AmiGraph, payload: DetectionPayload
) -> None:
    llenar_ventana(runtime, grafo)
    ciclo = runtime.run_cycle(despues_de_la_ventana())
    recolector = CollectingPublisher()
    assert CycleDispatcher(payload, recolector, PREFIJO).dispatch(ciclo) == 6


# ───────────────────────────────────────────── errores de construcción


def test_una_zona_sin_ventana_no_puede_publicarse_como_ventana(
    payload: DetectionPayload,
) -> None:
    vacio = ZoneResult(zona="centro", status="sin_bin")
    with pytest.raises(PublishError, match="no produjo ventana"):
        payload.ventana(vacio, EMITIDO)


def test_una_zona_sin_motivo_no_puede_publicarse_como_faltante(
    payload: DetectionPayload,
) -> None:
    vacio = ZoneResult(zona="centro", status="sin_bin")
    with pytest.raises(PublishError, match="no declara motivo"):
        payload.sin_ventana(vacio, EMITIDO)


# ────────────────────────────────────────────────────── serialización


def test_el_cuerpo_publicado_es_json_valido(
    runtime: MonitorRuntime, grafo: AmiGraph, payload: DetectionPayload
) -> None:
    """Todo lo que sale tiene que sobrevivir el viaje por el broker."""
    llenar_ventana(runtime, grafo)
    ciclo = runtime.run_cycle(despues_de_la_ventana())

    for _, cuerpo in repartir(ciclo, payload).messages:
        assert json.loads(encode(cuerpo).decode("utf-8")) == cuerpo


def test_los_acentos_viajan_legibles_y_no_escapados() -> None:
    """`ensure_ascii=False`: los nombres de zona y los motivos son español."""
    crudo = encode({"motivo": "calentamiento en la periferia — sin señal"})
    assert "señal" in crudo.decode("utf-8")


def test_el_prefijo_no_duplica_la_barra(payload: DetectionPayload) -> None:
    ciclo = CycleResult(started_utc=EMITIDO, seconds=0.0)
    dispatcher = CycleDispatcher(payload, CollectingPublisher(), f"{PREFIJO}/")
    assert dispatcher.dispatch(ciclo, EMITIDO) == 0
