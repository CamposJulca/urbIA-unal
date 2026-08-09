"""Tests de `stream.window`: la ventana temporal densa."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from urbia_monitor_gsp.stream import (
    BinIncompleteError,
    Window,
    WindowConfig,
    WindowError,
    ZoneWindow,
)

MEDIDORES = ("urbia-cen-mon-0001", "urbia-cen-mon-0002", "urbia-cen-mon-0003")

# Un instante alineado al borde de un bin de 6 s: 1e9 es divisible por 6.
BASE = datetime.fromtimestamp(1_800_000_000, tz=UTC)


def _config(**cambios: float | int) -> WindowConfig:
    parametros: dict[str, float | int] = {
        "bin_seconds": 6.0,
        "window_bins": 4,
        "close_grace_seconds": 5.0,
    }
    parametros.update(cambios)
    return WindowConfig(**parametros)  # type: ignore[arg-type]


def _ventana(**cambios: float | int) -> ZoneWindow:
    return ZoneWindow("centro", MEDIDORES, _config(**cambios))


def _llenar(zw: ZoneWindow, bins: int, desde: datetime = BASE, valor: float = 220.0) -> None:
    """Llena `bins` bins consecutivos con los tres medidores."""
    for b in range(bins):
        instante = desde + timedelta(seconds=6.0 * b + 1.0)
        for i, device_id in enumerate(MEDIDORES):
            zw.observe(device_id, instante, valor + i)


def _ahora_tras(bins: int, desde: datetime = BASE) -> datetime:
    """Instante en que el bin `bins - 1` ya está cerrado."""
    return desde + timedelta(seconds=6.0 * bins + 5.0 + 0.1)


# ----- WindowConfig -----


def test_window_config_defectos_corresponden_a_la_medicion() -> None:
    config = WindowConfig()
    assert config.bin_seconds == 6.0
    assert config.window_bins == 16
    assert config.close_grace_seconds == 5.0
    assert config.span_seconds == 96.0


@pytest.mark.parametrize(
    "cambio",
    [
        {"bin_seconds": 0.0},
        {"bin_seconds": -1.0},
        {"bin_seconds": float("nan")},
        {"window_bins": 0},
        {"close_grace_seconds": -1.0},
        {"max_future_seconds": -1.0},
    ],
)
def test_window_config_rechaza_parametros_fuera_de_rango(
    cambio: dict[str, float | int],
) -> None:
    with pytest.raises(WindowError):
        WindowConfig(**cambio)  # type: ignore[arg-type]


# ----- construcción -----


def test_zone_window_sin_medidores_falla() -> None:
    with pytest.raises(WindowError, match="no tiene medidores"):
        ZoneWindow("centro", ())


def test_zone_window_con_device_ids_repetidos_falla() -> None:
    with pytest.raises(WindowError, match="repetidos"):
        ZoneWindow("centro", ("a", "a"))


def test_zone_window_expone_zona_y_medidores() -> None:
    zw = _ventana()
    assert zw.zona == "centro"
    assert zw.n_meters == 3
    assert zw.config.window_bins == 4


# ----- observe -----


def test_observe_medidor_ajeno_a_la_zona_se_descarta() -> None:
    zw = _ventana()
    assert zw.observe("urbia-chi-mon-0001", BASE, 220.0) is False
    assert zw.unknown_device_count == 1
    assert zw.accepted_count == 0


def test_observe_datetime_sin_zona_horaria_falla() -> None:
    zw = _ventana()
    with pytest.raises(WindowError, match="zona horaria"):
        zw.observe(MEDIDORES[0], datetime(2026, 8, 9, 12, 0, 0), 220.0)


def test_observe_valor_no_finito_falla() -> None:
    zw = _ventana()
    with pytest.raises(WindowError, match="no finita"):
        zw.observe(MEDIDORES[0], BASE, float("nan"))


def test_observe_marca_muy_adelantada_se_descarta() -> None:
    zw = _ventana(max_future_seconds=60.0)
    futuro = BASE + timedelta(seconds=3600)
    assert zw.observe(MEDIDORES[0], futuro, 220.0, now=BASE) is False
    assert zw.future_count == 1


def test_observe_sin_now_no_controla_el_futuro() -> None:
    """Una reproducción offline pasa datos históricos sin reloj de pared."""
    zw = _ventana()
    assert zw.observe(MEDIDORES[0], BASE + timedelta(days=365), 220.0) is True


def test_observe_lectura_mas_reciente_gana_dentro_del_bin() -> None:
    """C4 del experimento: la más reciente, y nunca el promedio."""
    zw = _ventana()
    primera = BASE + timedelta(seconds=1.0)
    segunda = BASE + timedelta(seconds=4.0)
    for device_id in MEDIDORES:
        zw.observe(device_id, primera, 100.0)
        zw.observe(device_id, segunda, 300.0)

    _llenar(zw, 3, desde=BASE + timedelta(seconds=6.0))
    ventana = zw.emit(_ahora_tras(4))

    assert ventana is not None
    # Gana 300, no el promedio 200 de las dos lecturas del bin.
    assert ventana.matrix[0, 0] == pytest.approx(300.0)
    assert zw.superseded_count == 3


def test_observe_lectura_mas_vieja_no_desplaza_a_la_reciente() -> None:
    zw = _ventana()
    reciente = BASE + timedelta(seconds=4.0)
    vieja = BASE + timedelta(seconds=1.0)
    zw.observe(MEDIDORES[0], reciente, 300.0)
    assert zw.observe(MEDIDORES[0], vieja, 100.0) is False
    assert zw.superseded_count == 1


def test_observe_many_cuenta_las_aceptadas() -> None:
    zw = _ventana()
    lecturas = [
        (MEDIDORES[0], BASE, 220.0),
        ("ajeno", BASE, 220.0),
        (MEDIDORES[1], BASE, 221.0),
    ]
    assert zw.observe_many(lecturas) == 2


# ----- cierre de bins -----


def test_last_closed_bin_respeta_la_gracia() -> None:
    zw = _ventana()
    # Justo en el borde del bin 0, sin gracia cumplida: nada cerrado todavía.
    apenas = BASE + timedelta(seconds=6.0 + 4.9)
    ya = BASE + timedelta(seconds=6.0 + 5.1)
    base_bin = int(BASE.timestamp() // 6)
    assert zw.last_closed_bin(apenas) == base_bin - 1
    assert zw.last_closed_bin(ya) == base_bin


def test_last_closed_bin_exige_zona_horaria() -> None:
    zw = _ventana()
    with pytest.raises(WindowError, match="zona horaria"):
        zw.last_closed_bin(datetime(2026, 8, 9, 12, 0, 0))


# ----- emit -----


def test_emit_ventana_completa_tiene_la_forma_del_grafo() -> None:
    zw = _ventana()
    _llenar(zw, 4)
    ventana = zw.emit(_ahora_tras(4))

    assert isinstance(ventana, Window)
    assert ventana.matrix.shape == (4, 3)
    assert ventana.zona == "centro"
    assert ventana.skipped_bins == 0
    assert (ventana.end_utc - ventana.start_utc).total_seconds() == 24.0


def test_emit_respeta_el_orden_canonico_de_columnas() -> None:
    """Las columnas tienen que ir en el orden del grafo, no en el de llegada."""
    zw = _ventana()
    for b in range(4):
        instante = BASE + timedelta(seconds=6.0 * b + 1.0)
        for i, device_id in enumerate(reversed(MEDIDORES)):
            zw.observe(device_id, instante, 100.0 + 10.0 * (len(MEDIDORES) - 1 - i))

    ventana = zw.emit(_ahora_tras(4))
    assert ventana is not None
    np.testing.assert_allclose(ventana.matrix[0], [100.0, 110.0, 120.0])


def test_emit_dos_veces_en_el_mismo_bin_devuelve_none() -> None:
    zw = _ventana()
    _llenar(zw, 4)
    ahora = _ahora_tras(4)
    assert zw.emit(ahora) is not None
    assert zw.emit(ahora) is None


def test_emit_sin_ningun_bin_cerrado_devuelve_none() -> None:
    zw = _ventana()
    epoca = datetime.fromtimestamp(1.0, tz=UTC)
    assert zw.emit(epoca) is None


def test_emit_cuenta_los_bins_saltados() -> None:
    """Si el ciclo tarda más que el bin, el atraso tiene que ser visible."""
    zw = _ventana()
    _llenar(zw, 8)
    assert zw.emit(_ahora_tras(4)) is not None
    ventana = zw.emit(_ahora_tras(8))
    assert ventana is not None
    assert ventana.skipped_bins == 3


# ----- BinIncompleteError -----


def test_emit_con_un_medidor_faltante_no_produce_ventana() -> None:
    zw = _ventana()
    _llenar(zw, 4)
    # Un quinto bin al que le falta un medidor.
    quinto = BASE + timedelta(seconds=6.0 * 4 + 1.0)
    for device_id in MEDIDORES[:-1]:
        zw.observe(device_id, quinto, 220.0)

    with pytest.raises(BinIncompleteError) as excinfo:
        zw.emit(_ahora_tras(5))

    motivo = excinfo.value
    assert motivo.motivo == "bins_incompletos"
    assert motivo.zona == "centro"
    assert motivo.incomplete_bins == 1
    assert motivo.missing_device_ids == (MEDIDORES[-1],)


def test_emit_sin_historia_reporta_calentamiento() -> None:
    zw = _ventana()
    with pytest.raises(BinIncompleteError) as excinfo:
        zw.emit(_ahora_tras(4))
    assert excinfo.value.motivo == "calentamiento"


def test_calentamiento_pasa_a_bins_incompletos_cuando_hay_historia() -> None:
    zw = _ventana()
    _llenar(zw, 4)
    assert zw.emit(_ahora_tras(4)) is not None
    # El bin siguiente llega vacío: ya no es calentamiento, es falta de dato.
    with pytest.raises(BinIncompleteError) as excinfo:
        zw.emit(_ahora_tras(5))
    assert excinfo.value.motivo == "bins_incompletos"


def test_bin_incompleto_no_se_reintenta_con_lecturas_atrasadas() -> None:
    """Un tramo ya publicado no puede publicarse otra vez con otro veredicto."""
    zw = _ventana()
    _llenar(zw, 4)
    quinto = BASE + timedelta(seconds=6.0 * 4 + 1.0)
    for device_id in MEDIDORES[:-1]:
        zw.observe(device_id, quinto, 220.0)

    with pytest.raises(BinIncompleteError):
        zw.emit(_ahora_tras(5))

    # La lectura atrasada del medidor que faltaba llega ahora: se descarta.
    assert zw.observe(MEDIDORES[-1], quinto, 220.0) is False
    assert zw.late_count == 1


def test_bin_incomplete_serializa_el_motivo() -> None:
    zw = _ventana()
    with pytest.raises(BinIncompleteError) as excinfo:
        zw.emit(_ahora_tras(4))

    datos = excinfo.value.to_dict()
    assert datos["zona"] == "centro"
    assert datos["motivo"] == "calentamiento"
    assert datos["bins_incompletos"] == 4
    assert sorted(datos["medidores_faltantes"]) == sorted(MEDIDORES)
    assert datos["inicio_utc"].endswith("+00:00")


def test_bin_incomplete_resume_muchos_faltantes_en_el_mensaje() -> None:
    muchos = tuple(f"urbia-cen-mon-{i:04d}" for i in range(10))
    zw = ZoneWindow("centro", muchos, _config())
    with pytest.raises(BinIncompleteError, match="y 5 más"):
        zw.emit(_ahora_tras(4))


def test_window_serializa_sus_metadatos() -> None:
    zw = _ventana()
    _llenar(zw, 4)
    ventana = zw.emit(_ahora_tras(4))
    assert ventana is not None

    datos = ventana.to_dict()
    assert datos["bins"] == 4
    assert datos["medidores"] == 3
    assert datos["zona"] == "centro"
    assert "matrix" not in datos


# ----- rejilla y memoria -----


def test_la_rejilla_es_absoluta_y_no_depende_del_arranque() -> None:
    """Dos procesos que arrancan en momentos distintos ven los mismos bins."""
    primera = _ventana()
    segunda = _ventana()
    instante = BASE + timedelta(seconds=13.7)
    primera.observe(MEDIDORES[0], instante, 220.0)
    segunda.observe(MEDIDORES[0], instante, 220.0)

    esperado = int(instante.timestamp() // 6)
    assert primera.last_closed_bin(instante + timedelta(seconds=11)) == esperado
    assert segunda.last_closed_bin(instante + timedelta(seconds=11)) == esperado


def test_los_bins_viejos_se_podan() -> None:
    zw = _ventana(window_bins=2)
    _llenar(zw, 20)
    zw.emit(_ahora_tras(20))
    # window_bins=2 más el margen: no puede quedar la historia entera.
    assert zw.buffered_bins <= 2 + 4 + 1


def test_una_ventana_de_16_bins_de_6s_cubre_96_segundos() -> None:
    """El punto de operación real, no el reducido de los otros tests."""
    zw = ZoneWindow("centro", MEDIDORES, WindowConfig())
    _llenar(zw, 16)
    ventana = zw.emit(_ahora_tras(16))
    assert ventana is not None
    assert ventana.matrix.shape == (16, 3)
    assert (ventana.end_utc - ventana.start_utc).total_seconds() == 96.0
