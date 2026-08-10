"""Tests del servicio como proceso: arranque, bucle y apagado.

El grafo se pasa ya construido (`build_service(..., graph=...)`), así que
nada de acá toca PostgreSQL. Lo que se verifica son las decisiones que el
proceso toma **y que no se pueden notar mirando su salida una vez que anda**:

* las cuatro negativas de arranque, cada una por su lado;
* que la topología cambiada **tumbe** el servicio y una base inalcanzable
  **no**, porque confundirlas haría que un corte de red apagara el monitor;
* que el reloj no acumule deriva.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from conftest_service import (
    CALIBRACION,
    calibracion_versionada,
    despues_de_la_ventana,
    llenar_ventana,
)
from urbia_monitor_gsp.graph.builder import build_ami_graph
from urbia_monitor_gsp.graph.types import AmiGraph, GraphConfig, MeterNode
from urbia_monitor_gsp.service import app as app_mod
from urbia_monitor_gsp.service import metrics as metrics_mod
from urbia_monitor_gsp.service.app import (
    MonitorService,
    _resolve,
    build_service,
    install_signal_handlers,
)
from urbia_monitor_gsp.service.calibration import CalibrationError, TopologyMismatchError
from urbia_monitor_gsp.service.metrics import NullMetrics
from urbia_monitor_gsp.service.publisher import CollectingPublisher
from urbia_monitor_gsp.service.runtime import RuntimeSetupError
from urbia_monitor_gsp.service.settings import MonitorSettings, MonitorSettingsError
from urbia_monitor_gsp.stream.window import WindowConfig


@pytest.fixture(scope="module")
def grafo(manizales: list[MeterNode]) -> AmiGraph:
    return build_ami_graph(manizales, GraphConfig())


@pytest.fixture
def settings() -> MonitorSettings:
    return MonitorSettings(calibration_path=CALIBRACION)


def armar(
    settings: MonitorSettings,
    grafo: AmiGraph,
    publisher: CollectingPublisher | None = None,
    window_config: WindowConfig | None = None,
) -> MonitorService:
    """Arma el servicio sin base de datos.

    Args:
        settings: Configuración.
        grafo: Grafo ya construido.
        publisher: Adónde van los mensajes.
        window_config: Parámetros de la ventana.

    Returns:
        El servicio armado.
    """
    servicio = build_service(
        settings,
        publisher if publisher is not None else CollectingPublisher(),
        window_config=window_config,
        graph=grafo,
    )
    # `build_service` arma siempre la ingesta MQTT; ningún test de acá la
    # arranca, y dejarla puesta haría que `run()` intentara conectarse.
    servicio._source = None
    return servicio


# ────────────────────────────── las cuatro negativas de arranque


def test_sin_calibracion_no_arranca(grafo: AmiGraph, tmp_path: Path) -> None:
    """Sin calibración congelada el servicio no arranca.

    Calibrar en caliente haría que una anomalía persistente se volviera parte
    de la hipótesis nula: cuanto peor la anomalía, más normal parecería.
    """
    settings = MonitorSettings(calibration_path=tmp_path / "no-existe.json")
    with pytest.raises(CalibrationError):
        armar(settings, grafo)


def test_con_una_topologia_que_no_es_la_calibrada_no_arranca(
    settings: MonitorSettings, manizales: list[MeterNode]
) -> None:
    otro = build_ami_graph(manizales, GraphConfig(k=6))
    with pytest.raises(TopologyMismatchError):
        armar(settings, otro)


def test_con_una_ventana_que_no_es_la_del_umbral_no_arranca(
    settings: MonitorSettings, grafo: AmiGraph
) -> None:
    with pytest.raises(RuntimeSetupError, match="bins"):
        armar(settings, grafo, window_config=WindowConfig(window_bins=8))


def test_con_un_intervalo_que_no_cabe_en_el_bin_no_arranca(grafo: AmiGraph) -> None:
    settings = MonitorSettings(calibration_path=CALIBRACION, cycle_seconds=10.0)
    with pytest.raises(MonitorSettingsError, match="mitad del bin"):
        armar(settings, grafo)


def test_con_todo_en_orden_arranca(settings: MonitorSettings, grafo: AmiGraph) -> None:
    servicio = armar(settings, grafo)
    assert servicio.cycles == 0
    assert servicio.published == 0


# ─────────────────────────────────────────────────────── el tick


def test_un_tick_corre_el_ciclo_y_publica(settings: MonitorSettings, grafo: AmiGraph) -> None:
    recolector = CollectingPublisher()
    servicio = armar(settings, grafo, recolector)

    llenar_ventana(servicio._runtime, grafo)
    enviados = servicio.tick(despues_de_la_ventana())

    assert enviados == 6
    assert servicio.cycles == 1
    assert servicio.published == 6
    assert len(recolector.messages) == 6


def test_un_tick_sin_bin_nuevo_no_publica(settings: MonitorSettings, grafo: AmiGraph) -> None:
    recolector = CollectingPublisher()
    servicio = armar(settings, grafo, recolector)

    llenar_ventana(servicio._runtime, grafo)
    momento = despues_de_la_ventana()
    servicio.tick(momento)
    assert servicio.tick(momento) == 0
    assert servicio.cycles == 2


def test_los_contadores_del_servicio_acumulan(settings: MonitorSettings, grafo: AmiGraph) -> None:
    servicio = armar(settings, grafo)
    llenar_ventana(servicio._runtime, grafo)

    momento = despues_de_la_ventana()
    servicio.tick(momento)
    servicio.tick(momento + timedelta(seconds=3))

    assert servicio.cycles == 2
    assert servicio.published == 6


def test_sin_instante_el_tick_usa_el_reloj(settings: MonitorSettings, grafo: AmiGraph) -> None:
    """Sin instante explícito el tick usa el reloj.

    Con el reloj real y sin ninguna lectura, las seis zonas publican su
    motivo. Que el primer tick diga "no tengo datos" en vez de callarse es lo
    que hace visible un monitor recién arrancado.
    """
    recolector = CollectingPublisher()
    servicio = armar(settings, grafo, recolector)

    assert servicio.tick() == 6
    assert servicio.cycles == 1
    assert all("/sin-ventana/" in t for t in recolector.topics())


# ─────────────────────────── la verificación periódica de topología


class BaseFalsa:
    """Sustituye a `load_ami_graph` sin PostgreSQL."""

    def __init__(self, grafo: AmiGraph | None, error: Exception | None = None) -> None:
        self.grafo = grafo
        self.error = error
        self.llamadas = 0

    def __call__(self, *_args: object, **_kwargs: object) -> AmiGraph:
        self.llamadas += 1
        if self.error is not None:
            raise self.error
        assert self.grafo is not None
        return self.grafo


def test_una_topologia_intacta_verifica_bien(
    settings: MonitorSettings, grafo: AmiGraph, monkeypatch: pytest.MonkeyPatch
) -> None:
    servicio = armar(settings, grafo)
    monkeypatch.setattr(app_mod, "load_ami_graph", BaseFalsa(grafo))

    assert servicio.verify_topology() is True


def test_una_topologia_cambiada_tumba_el_servicio(
    settings: MonitorSettings,
    grafo: AmiGraph,
    manizales: list[MeterNode],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Una topología cambiada es bloqueante a propósito.

    Seguir con el umbral viejo produciría detecciones que no corresponden al
    sistema real, y los números seguirían saliendo con la misma pinta de
    siempre.
    """
    servicio = armar(settings, grafo)
    otro = build_ami_graph(manizales[:-1], GraphConfig())
    monkeypatch.setattr(app_mod, "load_ami_graph", BaseFalsa(otro))

    with pytest.raises(TopologyMismatchError):
        servicio.verify_topology()


def test_una_base_inalcanzable_no_tumba_el_servicio(
    settings: MonitorSettings, grafo: AmiGraph, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No es evidencia de que la topología cambió.

    Confundirlas haría que un
    corte de red apagara el monitor.
    """
    servicio = armar(settings, grafo)
    monkeypatch.setattr(app_mod, "load_ami_graph", BaseFalsa(None, OSError("sin ruta al host")))

    assert servicio.verify_topology() is False


def test_una_base_inalcanzable_se_reintenta_al_turno_siguiente(
    settings: MonitorSettings, grafo: AmiGraph, monkeypatch: pytest.MonkeyPatch
) -> None:
    servicio = armar(settings, grafo)
    caida = BaseFalsa(None, OSError("sin ruta al host"))
    monkeypatch.setattr(app_mod, "load_ami_graph", caida)

    servicio.verify_topology()
    servicio.verify_topology()
    assert caida.llamadas == 2


# ──────────────────────────────────────────────── el bucle y el apagado


def test_el_bucle_para_cuando_se_lo_pide(
    settings: MonitorSettings, grafo: AmiGraph, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app_mod, "load_ami_graph", BaseFalsa(grafo))
    rapido = MonitorSettings(
        calibration_path=CALIBRACION, cycle_seconds=0.01, topology_check_seconds=0.02
    )
    servicio = armar(rapido, grafo)

    hilo = threading.Thread(target=servicio.run)
    hilo.start()
    threading.Event().wait(0.15)
    servicio.request_stop()
    hilo.join(timeout=5.0)

    assert not hilo.is_alive()
    assert servicio.cycles > 1


def test_el_bucle_verifica_la_topologia_mientras_corre(
    settings: MonitorSettings, grafo: AmiGraph, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = BaseFalsa(grafo)
    monkeypatch.setattr(app_mod, "load_ami_graph", base)
    rapido = MonitorSettings(
        calibration_path=CALIBRACION, cycle_seconds=0.01, topology_check_seconds=0.02
    )
    servicio = armar(rapido, grafo)

    hilo = threading.Thread(target=servicio.run)
    hilo.start()
    threading.Event().wait(0.15)
    servicio.request_stop()
    hilo.join(timeout=5.0)

    assert base.llamadas >= 1


def test_una_topologia_cambiada_en_marcha_propaga_y_detiene(
    grafo: AmiGraph, manizales: list[MeterNode], monkeypatch: pytest.MonkeyPatch
) -> None:
    otro = build_ami_graph(manizales[:-1], GraphConfig())
    monkeypatch.setattr(app_mod, "load_ami_graph", BaseFalsa(otro))
    rapido = MonitorSettings(
        calibration_path=CALIBRACION, cycle_seconds=0.01, topology_check_seconds=0.0001
    )
    servicio = armar(rapido, grafo)

    with pytest.raises(TopologyMismatchError):
        servicio.run()


def test_pedir_el_apagado_antes_de_arrancar_no_corre_ningun_ciclo(
    settings: MonitorSettings, grafo: AmiGraph
) -> None:
    servicio = armar(settings, grafo)
    servicio.request_stop()
    servicio.run()
    assert servicio.cycles == 0


def test_el_reloj_no_acumula_deriva(
    settings: MonitorSettings, grafo: AmiGraph, monkeypatch: pytest.MonkeyPatch
) -> None:
    """El reloj no acumula deriva.

    Cada despertar se calcula desde el arranque y no sumando el intervalo al
    anterior, así que un ciclo que se pase de largo no corre el siguiente
    para siempre. Con 10 ms de intervalo y 200 ms de reloj tienen que haber
    salido bastantes más ciclos de los que darían si cada uno arrastrara su
    propia duración.
    """
    monkeypatch.setattr(app_mod, "load_ami_graph", BaseFalsa(grafo))
    rapido = MonitorSettings(
        calibration_path=CALIBRACION, cycle_seconds=0.01, topology_check_seconds=100.0
    )
    servicio = armar(rapido, grafo)

    hilo = threading.Thread(target=servicio.run)
    inicio = datetime.now(UTC)
    hilo.start()
    threading.Event().wait(0.2)
    servicio.request_stop()
    hilo.join(timeout=5.0)
    transcurrido = (datetime.now(UTC) - inicio).total_seconds()

    esperados = transcurrido / rapido.cycle_seconds
    assert servicio.cycles >= esperados * 0.5


def test_los_manejadores_de_senal_piden_el_apagado(
    settings: MonitorSettings, grafo: AmiGraph
) -> None:
    """SIGTERM y SIGINT piden el apagado ordenado.

    Sin esto, `docker stop` mataría el proceso a mitad de un ciclo y dejaría
    la sesión colgada en el broker hasta que venciera el keepalive.
    """
    import signal

    servicio = armar(settings, grafo)
    previos = (signal.getsignal(signal.SIGTERM), signal.getsignal(signal.SIGINT))
    try:
        install_signal_handlers(servicio)
        manejador = signal.getsignal(signal.SIGTERM)
        assert callable(manejador)
        manejador(signal.SIGTERM, None)
        assert servicio._parar.is_set()
    finally:
        signal.signal(signal.SIGTERM, previos[0])
        signal.signal(signal.SIGINT, previos[1])


# ──────────────────────────────────────────────── la ruta de calibración


def test_una_ruta_absoluta_se_deja_como_esta() -> None:
    assert _resolve(Path("/etc/urbia/cal.json")) == Path("/etc/urbia/cal.json")


def test_una_ruta_relativa_se_resuelve_contra_la_raiz_del_repo() -> None:
    """Una ruta relativa se resuelve contra la raíz del repositorio.

    El servicio corre tanto desde el contenedor como desde el repositorio, y
    el defecto de `calibration_path` es relativo.
    """
    resuelta = _resolve(Path("data/calibrations/manizales_scan_v1.json"))
    assert resuelta.is_absolute()
    assert resuelta.exists()


def test_el_defecto_de_calibracion_apunta_al_archivo_versionado() -> None:
    assert _resolve(MonitorSettings().calibration_path) == CALIBRACION.resolve()


# ──────────────────────────────────────────── el armado del despacho


def test_el_servicio_publica_bajo_el_prefijo_configurado(grafo: AmiGraph) -> None:
    settings = MonitorSettings(
        calibration_path=CALIBRACION, mqtt_topic_prefix="urbia/borde/monitor"
    )
    recolector = CollectingPublisher()
    servicio = armar(settings, grafo, recolector)

    llenar_ventana(servicio._runtime, grafo)
    servicio.tick(despues_de_la_ventana())

    assert all(t.startswith("urbia/borde/monitor/") for t in recolector.topics())


def test_el_servicio_respeta_el_top_k_configurado(grafo: AmiGraph) -> None:
    settings = MonitorSettings(calibration_path=CALIBRACION, top_k=2)
    recolector = CollectingPublisher()
    servicio = armar(settings, grafo, recolector)

    llenar_ventana(servicio._runtime, grafo)
    servicio.tick(despues_de_la_ventana())

    _, cuerpo = recolector.messages[0]
    assert len(cuerpo["deteccion"]["ranking"]) == 2


def test_la_calibracion_cargada_es_la_que_se_declara(
    settings: MonitorSettings, grafo: AmiGraph
) -> None:
    servicio = armar(settings, grafo)
    assert servicio._calibration.version == calibracion_versionada().version


# ────────────────────────────────────────────── el punto de entrada


def test_main_devuelve_uno_si_el_monitor_se_niega_a_arrancar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """El código de salida es lo único que ve `docker compose` o systemd.

    Un servicio mal configurado tiene que salir distinto de cero, o el
    orquestador lo daría por sano y el panel quedaría en blanco sin motivo.
    """
    monkeypatch.setenv("CALIBRATION_PATH", str(tmp_path / "no-existe.json"))
    # `main` importa las dos de `.metrics` en tiempo de llamada, así que
    # el parche va sobre el módulo de origen y no sobre `app`.
    monkeypatch.setattr(metrics_mod, "start_metrics_server", lambda *a, **k: (None, None))
    monkeypatch.setattr(metrics_mod, "PrometheusMetrics", lambda **k: NullMetrics())

    assert app_mod.main() == 1


def test_main_devuelve_dos_si_la_topologia_cambia_en_marcha(
    grafo: AmiGraph, manizales: list[MeterNode], monkeypatch: pytest.MonkeyPatch
) -> None:
    """La topología cambiada en marcha sale con un código propio.

    Es distinto del código de arranque: son dos fallos distintos y el
    operador tiene que poder separarlos sin leer los logs.
    """
    otro = build_ami_graph(manizales[:-1], GraphConfig())
    monkeypatch.setenv("CALIBRATION_PATH", str(CALIBRACION))
    monkeypatch.setenv("CYCLE_SECONDS", "0.01")
    monkeypatch.setenv("TOPOLOGY_CHECK_SECONDS", "0.0001")
    # `main` importa las dos de `.metrics` en tiempo de llamada, así que
    # el parche va sobre el módulo de origen y no sobre `app`.
    monkeypatch.setattr(metrics_mod, "start_metrics_server", lambda *a, **k: (None, None))
    monkeypatch.setattr(metrics_mod, "PrometheusMetrics", lambda **k: NullMetrics())
    monkeypatch.setattr(app_mod, "load_ami_graph", BaseFalsa(grafo))

    publicados: list[str] = []

    class PublicadorMudo(CollectingPublisher):
        def start(self) -> None:
            publicados.append("start")

        def stop(self) -> None:
            publicados.append("stop")

    monkeypatch.setattr(app_mod, "MqttPublisher", lambda _s: PublicadorMudo())

    # El grafo se lee bien al arrancar y cambia en la reverificación.
    real = app_mod.build_service

    def armar_y_cambiar(*args: object, **kwargs: object) -> MonitorService:
        servicio = real(*args, graph=grafo, **kwargs)  # type: ignore[arg-type]
        servicio._source = None
        monkeypatch.setattr(app_mod, "load_ami_graph", BaseFalsa(otro))
        return servicio

    monkeypatch.setattr(app_mod, "build_service", armar_y_cambiar)

    assert app_mod.main() == 2
    assert publicados == ["start", "stop"]
