"""Tests de la configuración del servicio.

Lo que se verifica acá no es que pydantic sepa leer variables de entorno,
sino las **incoherencias que sólo se pueden detectar cruzando dos valores**
—el intervalo contra el ancho de bin— y que se detecten al arrancar y no
después de tres horas de pérdida acumulada.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from urbia_monitor_gsp.service.settings import (
    DEFAULT_CYCLE_SECONDS,
    DEFAULT_TOPOLOGY_CHECK_SECONDS,
    MonitorSettings,
    MonitorSettingsError,
    get_monitor_settings,
)
from urbia_monitor_gsp.stream.window import WindowConfig

BIN = WindowConfig().bin_seconds


# ─────────────────────────────────────────────────────────── defectos


def test_los_defectos_apuntan_al_broker_y_al_arbol_de_urbia() -> None:
    settings = MonitorSettings()
    assert settings.mqtt_host == "192.168.40.12"
    assert settings.mqtt_topic_telemetry == "urbia/manizales/#"
    assert settings.mqtt_topic_prefix.startswith("urbia/manizales/")


def test_el_defecto_de_magnitud_es_la_unica_evaluada() -> None:
    """Corriente y potencia tienen σ/media del 35 % y están sin evaluar.

    Cambiar esto sin medir sería operar fuera de la configuración calibrada.
    """
    assert MonitorSettings().magnitude == "voltaje_v"


def test_el_defecto_publica_el_ranking_completo() -> None:
    assert MonitorSettings().top_k is None


def test_el_intervalo_por_defecto_es_el_medido() -> None:
    """3 s sale de la regla C6 de `experiments/ciclo-deteccion/`, no de ojo."""
    assert MonitorSettings().cycle_seconds == DEFAULT_CYCLE_SECONDS
    assert DEFAULT_CYCLE_SECONDS == BIN / 2.0


def test_el_defecto_de_verificacion_de_topologia_no_es_cero() -> None:
    assert MonitorSettings().topology_check_seconds == DEFAULT_TOPOLOGY_CHECK_SECONDS


# ───────────────────────────────────────────── el intervalo y el bin


def test_un_intervalo_mayor_que_medio_bin_es_rechazado() -> None:
    """`emit` entrega una ventana por bin cerrado.

    Despertar menos seguido que el bin pierde bins, y cada bin perdido
    invalida las 16 ventanas que lo contenían. La pérdida se acumula y no se
    recupera sola.
    """
    settings = MonitorSettings(cycle_seconds=BIN)
    with pytest.raises(MonitorSettingsError, match="mitad del bin"):
        settings.validate_coherence(BIN)


def test_exactamente_medio_bin_pasa() -> None:
    """Es el defecto: el límite es `t ≤ b/2`, inclusive."""
    MonitorSettings(cycle_seconds=BIN / 2.0).validate_coherence(BIN)


def test_un_intervalo_no_positivo_es_rechazado() -> None:
    with pytest.raises(MonitorSettingsError, match="cycle_seconds"):
        MonitorSettings(cycle_seconds=0.0).validate_coherence(BIN)


def test_un_bin_mas_ancho_admite_un_intervalo_mas_largo() -> None:
    """La regla es relativa al bin, no un número fijo.

    Si alguien mide otro ancho de bin, el intervalo admisible se mueve con
    él en vez de quedar clavado en los 3 s de hoy.
    """
    MonitorSettings(cycle_seconds=5.0).validate_coherence(12.0)
    with pytest.raises(MonitorSettingsError):
        MonitorSettings(cycle_seconds=5.0).validate_coherence(8.0)


def test_una_verificacion_de_topologia_no_positiva_es_rechazada() -> None:
    with pytest.raises(MonitorSettingsError, match="topology_check_seconds"):
        MonitorSettings(topology_check_seconds=0.0).validate_coherence(BIN)


def test_un_top_k_negativo_es_rechazado() -> None:
    with pytest.raises(MonitorSettingsError, match="top_k"):
        MonitorSettings(top_k=-1).validate_coherence(BIN)


def test_top_k_cero_es_valido() -> None:
    """Publicar sin ranking es una elección legítima de tamaño de payload."""
    MonitorSettings(top_k=0).validate_coherence(BIN)


# ───────────────────────────────────────────────────── filtro de zonas


def test_sin_zonas_declaradas_se_atienden_todas() -> None:
    assert MonitorSettings().zone_filter() is None


def test_las_zonas_declaradas_se_parten_y_se_limpian() -> None:
    """Acotar es lo que permitirá al nodo de borde correr sólo la suya."""
    settings = MonitorSettings(zonas=" centro , chipre ,, ")
    assert settings.zone_filter() == ("centro", "chipre")


def test_una_lista_de_zonas_toda_en_blanco_equivale_a_no_acotar() -> None:
    assert MonitorSettings(zonas="  ,  , ").zone_filter() is None


# ──────────────────────────────────────────────────────── el entorno


def test_la_configuracion_se_lee_del_entorno(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MQTT_HOST", "127.0.0.1")
    monkeypatch.setenv("CYCLE_SECONDS", "1.5")
    monkeypatch.setenv("ZONAS", "palermo")

    settings = get_monitor_settings()
    assert settings.mqtt_host == "127.0.0.1"
    assert settings.cycle_seconds == 1.5
    assert settings.zone_filter() == ("palermo",)


def test_las_variables_son_insensibles_a_mayusculas(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("mqtt_port", "1884")
    assert get_monitor_settings().mqtt_port == 1884


def test_una_variable_ajena_no_rompe_la_configuracion(monkeypatch: pytest.MonkeyPatch) -> None:
    """El `.env` del proyecto define muchas variables de otros servicios."""
    monkeypatch.setenv("POSTGRES_PASSWORD", "algo")
    monkeypatch.setenv("GRAFANA_ADMIN_PASSWORD", "otra")
    assert get_monitor_settings().mqtt_host == "192.168.40.12"


def test_la_ruta_de_calibracion_se_lee_como_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CALIBRATION_PATH", "/tmp/otra.json")
    assert get_monitor_settings().calibration_path == Path("/tmp/otra.json")
