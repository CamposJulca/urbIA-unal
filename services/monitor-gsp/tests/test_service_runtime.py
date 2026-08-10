"""Tests del ciclo de detección, sin broker ni base.

El ciclo es lo que se va a mudar al nodo de borde para medir H1, así que
tiene que poder correrse —y probarse— sin nada del andamiaje que lo rodea.
Estos tests son la prueba de que esa separación existe de verdad: ninguno
importa paho, prometheus ni psycopg.
"""

from __future__ import annotations

from datetime import timedelta

import numpy as np
import pytest

from conftest_service import (
    BASE,
    calibracion_versionada,
    despues_de_la_ventana,
    llenar_ventana,
)
from urbia_monitor_gsp.graph.builder import build_ami_graph
from urbia_monitor_gsp.graph.types import AmiGraph, GraphConfig, MeterNode
from urbia_monitor_gsp.service.calibration import Calibration, TopologyMismatchError
from urbia_monitor_gsp.service.metrics import NullMetrics
from urbia_monitor_gsp.service.runtime import (
    MonitorRuntime,
    RuntimeSetupError,
    build_runtime,
)
from urbia_monitor_gsp.stream.window import WindowConfig


@pytest.fixture(scope="module")
def grafo(manizales: list[MeterNode]) -> AmiGraph:
    return build_ami_graph(manizales, GraphConfig())


@pytest.fixture(scope="module")
def calibracion() -> Calibration:
    return calibracion_versionada()


@pytest.fixture
def runtime(grafo: AmiGraph, calibracion: Calibration) -> MonitorRuntime:
    return build_runtime(grafo, calibracion)


class MetricasEspia:
    """Cuenta llamadas en vez de registrar, para verificar que se registró."""

    def __init__(self) -> None:
        self.ciclos: list[float] = []
        self.ventanas: list[str] = []
        self.detecciones: list[str] = []
        self.faltantes: list[tuple[str, str]] = []
        self.ingesta: list[tuple[int, dict[str, int]]] = []
        self.conectado: list[bool] = []
        self.verificaciones: list[bool] = []
        self.fallos = 0

    def observe_cycle(self, seconds: float) -> None:
        self.ciclos.append(seconds)

    def observe_window(self, window: object, statistic: float, threshold: float) -> None:
        self.ventanas.append(window.zona)  # type: ignore[attr-defined]

    def observe_detection(self, zona: str) -> None:
        self.detecciones.append(zona)

    def observe_missing(self, motivo: object, n_meters: int) -> None:
        self.faltantes.append((motivo.zona, motivo.motivo))  # type: ignore[attr-defined]

    def observe_ingest(self, aceptados: int, descartados: dict[str, int]) -> None:
        self.ingesta.append((aceptados, descartados))

    def observe_publish_failure(self) -> None:
        self.fallos += 1

    def set_connected(self, conectado: bool) -> None:
        self.conectado.append(conectado)

    def observe_topology_check(self, ok: bool) -> None:
        self.verificaciones.append(ok)


# ─────────────────────────────────────────────────────────────── armado


def test_build_runtime_arma_todas_las_zonas(runtime: MonitorRuntime) -> None:
    assert len(runtime.zonas) == 6
    assert runtime.n_meters == 150


def test_build_runtime_rechaza_una_topologia_que_no_es_la_calibrada(
    calibracion: Calibration, manizales: list[MeterNode]
) -> None:
    """Es la negativa de arranque que más importa.

    Sin ella el servicio detectaría sobre un grafo que ya no existe, y los
    números saldrían con la misma pinta de siempre.
    """
    otro = build_ami_graph(manizales, GraphConfig(k=6))
    with pytest.raises(TopologyMismatchError):
        build_runtime(otro, calibracion)


def test_build_runtime_rechaza_una_ventana_que_no_es_la_del_umbral(
    grafo: AmiGraph, calibracion: Calibration
) -> None:
    """El umbral se calibró sobre 16 bins; armar 8 lo dejaría sin sentido."""
    with pytest.raises(RuntimeSetupError, match="bins"):
        build_runtime(grafo, calibracion, WindowConfig(window_bins=8))


def test_monitor_sin_zonas_es_error() -> None:
    with pytest.raises(RuntimeSetupError, match="ninguna zona"):
        MonitorRuntime({})


def test_cada_zona_lleva_la_huella_con_la_que_se_calibro(
    runtime: MonitorRuntime, calibracion: Calibration
) -> None:
    for nombre in runtime.zonas:
        assert nombre in calibracion.zones


# ─────────────────────────────────────────────────────────────── ingesta


def test_observe_enruta_por_el_padron_del_grafo(runtime: MonitorRuntime, grafo: AmiGraph) -> None:
    """La zona sale del grafo y no del payload: el grafo es la autoridad."""
    device_id = grafo.zones["centro"].device_ids[0]
    assert runtime.observe(device_id, BASE, 220.0)


def test_observe_descarta_un_medidor_ajeno(runtime: MonitorRuntime) -> None:
    assert not runtime.observe("urbia-xxx-mon-9999", BASE, 220.0)
    assert runtime.ajenos == 1


# ───────────────────────────────────────────────── los tres desenlaces


def test_el_monitor_recien_armado_no_dice_sin_bin_sino_calentamiento(
    runtime: MonitorRuntime,
) -> None:
    """La rejilla de bins es absoluta, no relativa al arranque del proceso.

    Un monitor recién armado ya encuentra bins cerrados —la rejilla está
    anclada a la época— y ninguno tiene dato. Eso **no** es "todavía no
    cerró nada": es una zona sin datos, y el motivo la separa de un medidor
    que dejó de publicar.
    """
    ciclo = runtime.run_cycle(BASE)

    assert ciclo.windows == ()
    assert len(ciclo.missing) == 6
    for resultado in ciclo.missing:
        assert resultado.missing is not None
        assert resultado.missing.motivo == "calentamiento"


def test_un_ciclo_que_no_cierra_bin_nuevo_no_produce_nada(
    runtime: MonitorRuntime, grafo: AmiGraph
) -> None:
    """Un ciclo dentro del bin ya emitido no produce nada.

    El servicio despierta cada 3 s y el bin dura 6, así que la mitad de los
    ciclos cae acá. Es el caso normal, no un fallo.
    """
    llenar_ventana(runtime, grafo)
    momento = despues_de_la_ventana()

    assert len(runtime.run_cycle(momento).windows) == 6
    siguiente = runtime.run_cycle(momento + timedelta(seconds=3))
    assert all(r.status == "sin_bin" for r in siguiente.results)


def test_ventana_completa_produce_resultado_en_las_seis_zonas(
    runtime: MonitorRuntime, grafo: AmiGraph
) -> None:
    llenar_ventana(runtime, grafo)
    ciclo = runtime.run_cycle(despues_de_la_ventana())

    assert len(ciclo.windows) == 6
    for resultado in ciclo.windows:
        assert resultado.detection is not None
        assert resultado.window is not None
        assert resultado.window.matrix.shape[0] == 16
        assert resultado.window.skipped_bins == 0


def test_una_ventana_sin_evento_no_dispara(runtime: MonitorRuntime, grafo: AmiGraph) -> None:
    """Ruido con la σ del perfil: el umbral está calibrado justo para esto."""
    llenar_ventana(runtime, grafo)
    ciclo = runtime.run_cycle(despues_de_la_ventana())
    assert ciclo.detections == ()


def test_un_medidor_que_no_publica_deja_la_zona_sin_deteccion(
    runtime: MonitorRuntime, grafo: AmiGraph
) -> None:
    """No se imputa ni se excluye: la zona no produce resultado y dice por qué."""
    ausente = grafo.zones["chipre"].device_ids[3]
    llenar_ventana(runtime, grafo, omitir={"chipre": (ausente,)})
    ciclo = runtime.run_cycle(despues_de_la_ventana())

    (falta,) = ciclo.missing
    assert falta.zona == "chipre"
    assert falta.missing is not None
    assert falta.missing.motivo == "bins_incompletos"
    assert falta.missing.missing_device_ids == (ausente,)
    assert falta.missing.incomplete_bins == 16
    # Las otras cinco siguen produciendo: la falta es por zona.
    assert len(ciclo.windows) == 5


def test_una_ventana_a_medio_llenar_todavia_es_calentamiento(
    runtime: MonitorRuntime, grafo: AmiGraph
) -> None:
    """Una ventana a medio llenar todavía es calentamiento.

    Con cuatro bins vistos, la ventana de 16 alcanza hacia atrás hasta antes
    de que el proceso existiera. Eso es historia que nunca hubo, no un
    medidor caído, y el motivo tiene que distinguirlos: el panel de una zona
    que arranca no puede verse igual que el de una zona con un medidor
    muerto.

    El contraste está en `test_un_medidor_que_no_publica_...`, donde la
    ventana sí cae entera dentro de lo observado y el motivo pasa a ser
    `bins_incompletos`.
    """
    parcial = WindowConfig(window_bins=4)
    llenar_ventana(runtime, grafo, config=parcial)
    ciclo = runtime.run_cycle(despues_de_la_ventana(parcial))

    assert len(ciclo.missing) == 6
    for resultado in ciclo.missing:
        assert resultado.missing is not None
        assert resultado.missing.motivo == "calentamiento"


def test_un_grupo_conectado_corrido_dispara_la_deteccion(
    runtime: MonitorRuntime, grafo: AmiGraph
) -> None:
    """El caso que el método existe para detectar: discordancia de un grupo."""
    zona = grafo.zones["palermo"]
    vecinos = tuple(zona.device_ids[i] for i in np.flatnonzero(zona.adjacency[0] > 0.0).tolist())
    grupo = (zona.device_ids[0], *vecinos)

    llenar_ventana(runtime, grafo, desplazar={"palermo": (grupo, 12.0)})
    ciclo = runtime.run_cycle(despues_de_la_ventana())

    detectadas = {r.zona for r in ciclo.detections}
    assert "palermo" in detectadas
    (marcada,) = [r for r in ciclo.detections if r.zona == "palermo"]
    assert marcada.detection is not None
    assert marcada.detection.statistic > marcada.detection.threshold
    assert set(marcada.detection.device_ids) & set(grupo)


def test_la_deteccion_publica_el_ranking_completo(runtime: MonitorRuntime, grafo: AmiGraph) -> None:
    llenar_ventana(runtime, grafo)
    ciclo = runtime.run_cycle(despues_de_la_ventana())
    for resultado in ciclo.windows:
        assert resultado.detection is not None
        assert len(resultado.detection.ranking) > 1


# ─────────────────────────────────────────────────────────────── métricas


def test_el_ciclo_registra_lo_que_pasa(grafo: AmiGraph, calibracion: Calibration) -> None:
    espia = MetricasEspia()
    runtime = build_runtime(grafo, calibracion, None, espia)
    llenar_ventana(runtime, grafo)
    runtime.run_cycle(despues_de_la_ventana())

    assert len(espia.ciclos) == 1
    assert espia.ciclos[0] > 0.0
    assert sorted(espia.ventanas) == sorted(runtime.zonas)
    assert sum(a for a, _ in espia.ingesta) == 150 * 16


def test_una_zona_sin_datos_queda_registrada_con_su_motivo(
    grafo: AmiGraph, calibracion: Calibration
) -> None:
    espia = MetricasEspia()
    runtime = build_runtime(grafo, calibracion, None, espia)
    llenar_ventana(runtime, grafo, omitir={"la_enea": (grafo.zones["la_enea"].device_ids[0],)})
    runtime.run_cycle(despues_de_la_ventana())

    assert ("la_enea", "bins_incompletos") in espia.faltantes


def test_la_ingesta_se_registra_incremental_y_no_acumulada(
    grafo: AmiGraph, calibracion: Calibration
) -> None:
    """Los contadores de la ventana son acumulados; Prometheus quiere deltas."""
    espia = MetricasEspia()
    runtime = build_runtime(grafo, calibracion, None, espia)

    llenar_ventana(runtime, grafo)
    runtime.run_cycle(despues_de_la_ventana())
    primero = sum(a for a, _ in espia.ingesta)

    runtime.run_cycle(despues_de_la_ventana())
    total = sum(a for a, _ in espia.ingesta)
    assert primero == 150 * 16
    assert total == primero, "el segundo ciclo no recibió lecturas y no debe sumar nada"


def test_los_descartes_se_registran_por_motivo(grafo: AmiGraph, calibracion: Calibration) -> None:
    espia = MetricasEspia()
    runtime = build_runtime(grafo, calibracion, None, espia)
    device_id = grafo.zones["centro"].device_ids[0]

    llenar_ventana(runtime, grafo)
    runtime.run_cycle(despues_de_la_ventana())
    # Una lectura de un bin ya emitido: llega tarde y no puede corregir nada.
    runtime.observe(device_id, BASE, 220.0)
    runtime.run_cycle(despues_de_la_ventana())

    tardias = sum(d.get("tarde", 0) for _, d in espia.ingesta)
    assert tardias == 1


def test_sin_metricas_el_ciclo_corre_igual(grafo: AmiGraph, calibracion: Calibration) -> None:
    runtime = build_runtime(grafo, calibracion, None, NullMetrics())
    llenar_ventana(runtime, grafo)
    assert len(runtime.run_cycle(despues_de_la_ventana()).windows) == 6


# ─────────────────────────────────────────────────────── forma del ciclo


def test_el_ciclo_reporta_su_duracion(runtime: MonitorRuntime, grafo: AmiGraph) -> None:
    llenar_ventana(runtime, grafo)
    ciclo = runtime.run_cycle(despues_de_la_ventana())
    assert ciclo.seconds > 0.0
    assert ciclo.started_utc == despues_de_la_ventana()


def test_un_bin_no_se_reintenta_con_lecturas_atrasadas(
    runtime: MonitorRuntime, grafo: AmiGraph
) -> None:
    """Reintentar publicaría dos resultados distintos del mismo tramo."""
    llenar_ventana(runtime, grafo)
    primero = runtime.run_cycle(despues_de_la_ventana())
    segundo = runtime.run_cycle(despues_de_la_ventana())

    assert len(primero.windows) == 6
    assert all(r.status == "sin_bin" for r in segundo.results)
