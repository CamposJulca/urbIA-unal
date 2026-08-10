"""Tests de la calibración congelada y de la huella de topología.

Lo que estos tests protegen es la respuesta a una pregunta operativa: qué
pasa cuando el grafo vivo deja de ser el grafo con el que se calibró. La
respuesta elegida es que el servicio no arranque, y eso sólo sirve si la
huella cambia cuando tiene que cambiar y no cambia cuando no.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from urbia_monitor_gsp.detector import DetectorConfig, FrozenThreshold
from urbia_monitor_gsp.graph.builder import build_ami_graph, build_zone_graph
from urbia_monitor_gsp.graph.types import GraphConfig, MeterNode
from urbia_monitor_gsp.service import (
    Calibration,
    CalibrationError,
    TopologyMismatchError,
    ZoneCalibration,
    graph_fingerprints,
    load_calibration,
    save_calibration,
    zone_fingerprint,
)

CALIBRACION_VERSIONADA = (
    Path(__file__).parents[3] / "data" / "calibrations" / "manizales_scan_v1.json"
)
"""El archivo que el servicio adopta al arrancar."""


def rejilla(zona: str, filas: int, columnas: int, *, desde: int = 0) -> list[MeterNode]:
    """Medidores en rejilla regular, de geometría predecible."""
    return [
        MeterNode(
            device_id=f"urbia-cen-mon-{desde + f * columnas + c:04d}",
            zona=zona,
            lat=5.06 + f * 0.001,
            lon=-75.51 + c * 0.001,
        )
        for f in range(filas)
        for c in range(columnas)
    ]


def congelado(zona: str = "centro", *, threshold: float = 4.4) -> FrozenThreshold:
    """Un umbral congelado cualquiera, con procedencia."""
    return FrozenThreshold(
        zona=zona,
        threshold=threshold,
        sigma_spatial=4.401231,
        config=DetectorConfig(step=1),
        seed=20260808,
        n_instants=64,
        source="test",
    )


def calibracion(zonas: dict[str, str]) -> Calibration:
    """Calibración mínima con las huellas que se le pasen."""
    return Calibration(
        version="test-v1",
        magnitude="voltaje_v",
        profile="manizales-signal-v1",
        topology="manizales-v1",
        zones={
            nombre: ZoneCalibration(frozen=congelado(nombre), fingerprint=huella, n_meters=25)
            for nombre, huella in zonas.items()
        },
    )


# ─────────────────────────────────────────────────── huella de topología


def test_zone_fingerprint_es_estable_entre_construcciones() -> None:
    medidores = rejilla("centro", 5, 5)
    primera = build_zone_graph(medidores, GraphConfig())
    segunda = build_zone_graph(medidores, GraphConfig())
    assert zone_fingerprint(primera) == zone_fingerprint(segunda)


def test_zone_fingerprint_cambia_al_agregar_un_medidor() -> None:
    """Es el caso que motiva la huella: un medidor nuevo en el padrón."""
    base = build_zone_graph(rejilla("centro", 5, 5), GraphConfig())
    ampliada = build_zone_graph(
        rejilla("centro", 5, 5) + rejilla("centro", 1, 1, desde=99), GraphConfig()
    )
    assert zone_fingerprint(base) != zone_fingerprint(ampliada)


def test_zone_fingerprint_cambia_al_cambiar_la_vecindad() -> None:
    """Mismos medidores, otro k: otras aristas, otras bolas, otro umbral."""
    medidores = rejilla("centro", 5, 5)
    con_k4 = build_zone_graph(medidores, GraphConfig(k=4))
    con_k6 = build_zone_graph(medidores, GraphConfig(k=6))
    assert zone_fingerprint(con_k4) != zone_fingerprint(con_k6)


def test_zone_fingerprint_ignora_los_pesos() -> None:
    """Los pesos no entran en el umbral: `candidate_balls` sólo mira si hay arista.

    Si la huella los tomara en cuenta, cambiar de pesos binarios a
    gaussianos impediría arrancar sin que ninguna bola candidata hubiera
    cambiado.
    """
    medidores = rejilla("centro", 5, 5)
    binaria = build_zone_graph(medidores, GraphConfig(weighting="binary"))
    gaussiana = build_zone_graph(medidores, GraphConfig(weighting="gaussian"))
    assert zone_fingerprint(binaria) == zone_fingerprint(gaussiana)


def test_zone_fingerprint_distingue_zonas_con_la_misma_forma() -> None:
    """Dos zonas de geometría idéntica no pueden compartir huella.

    El umbral es por zona; si las huellas coincidieran, un archivo con las
    zonas cruzadas pasaría la verificación.
    """
    izquierda = build_zone_graph(rejilla("centro", 5, 5), GraphConfig())
    derecha = build_zone_graph(
        [
            MeterNode(device_id=m.device_id, zona="chipre", lat=m.lat, lon=m.lon)
            for m in rejilla("centro", 5, 5)
        ],
        GraphConfig(),
    )
    assert zone_fingerprint(izquierda) != zone_fingerprint(derecha)


def test_graph_fingerprints_cubre_todas_las_zonas(manizales: list[MeterNode]) -> None:
    grafo = build_ami_graph(manizales, GraphConfig())
    huellas = graph_fingerprints(grafo)
    assert set(huellas) == set(grafo.zones)
    assert len(set(huellas.values())) == len(huellas)


# ─────────────────────────────────────────────────── verificación bloqueante


def test_verify_topology_pasa_con_el_grafo_de_calibracion(manizales: list[MeterNode]) -> None:
    grafo = build_ami_graph(manizales, GraphConfig())
    huellas = graph_fingerprints(grafo)
    calibracion(huellas).verify_topology(huellas)


def test_verify_topology_falla_si_una_zona_cambio() -> None:
    cal = calibracion({"centro": "aaaa", "chipre": "bbbb"})
    with pytest.raises(TopologyMismatchError) as exc:
        cal.verify_topology({"centro": "aaaa", "chipre": "cccc"})
    assert exc.value.diferencias == {"chipre": ("bbbb", "cccc")}
    assert "topología cambiada" in str(exc.value)


def test_verify_topology_falla_si_falta_una_zona_calibrada() -> None:
    cal = calibracion({"centro": "aaaa", "chipre": "bbbb"})
    with pytest.raises(TopologyMismatchError) as exc:
        cal.verify_topology({"centro": "aaaa"})
    assert exc.value.faltantes == ("chipre",)


def test_verify_topology_falla_si_hay_una_zona_nueva_sin_calibrar() -> None:
    """Una zona nueva no puede monitorearse con el umbral de otra."""
    cal = calibracion({"centro": "aaaa"})
    with pytest.raises(TopologyMismatchError) as exc:
        cal.verify_topology({"centro": "aaaa", "la_enea": "dddd"})
    assert exc.value.sobrantes == ("la_enea",)


def test_el_error_de_topologia_dice_como_recuperarse() -> None:
    """Un fallo bloqueante que no dice qué hacer deja el servicio caído sin salida."""
    cal = calibracion({"centro": "aaaa"})
    with pytest.raises(TopologyMismatchError) as exc:
        cal.verify_topology({"centro": "zzzz"})
    mensaje = str(exc.value)
    assert "congelar_umbrales.py" in mensaje
    assert "no corresponderían al sistema real" in mensaje or "sistema real" in mensaje


# ─────────────────────────────────────────────────── serialización


def test_calibracion_ida_y_vuelta_conserva_todo() -> None:
    original = calibracion({"centro": "aaaa", "chipre": "bbbb"})
    reconstruida = Calibration.from_dict(original.to_dict())
    assert reconstruida == original


def test_guardar_dos_veces_produce_los_mismos_bytes(tmp_path: Path) -> None:
    """Bytes estables para que el diff de git muestre sólo lo que cambió."""
    cal = calibracion({"chipre": "bbbb", "centro": "aaaa"})
    primero, segundo = tmp_path / "a.json", tmp_path / "b.json"
    save_calibration(cal, primero)
    save_calibration(cal, segundo)
    assert primero.read_bytes() == segundo.read_bytes()


def test_guardar_crea_el_directorio(tmp_path: Path) -> None:
    destino = tmp_path / "nuevo" / "sub" / "cal.json"
    save_calibration(calibracion({"centro": "aaaa"}), destino)
    assert destino.exists()


def test_cargar_lo_guardado(tmp_path: Path) -> None:
    destino = tmp_path / "cal.json"
    original = calibracion({"centro": "aaaa"})
    save_calibration(original, destino)
    assert load_calibration(destino) == original


def test_calibracion_ausente_explica_por_que_no_se_calibra_en_caliente(tmp_path: Path) -> None:
    with pytest.raises(CalibrationError) as exc:
        load_calibration(tmp_path / "no-existe.json")
    assert "congelar_umbrales.py" in str(exc.value)


def test_calibracion_ilegible_es_error(tmp_path: Path) -> None:
    destino = tmp_path / "roto.json"
    destino.write_text("{no es json", encoding="utf-8")
    with pytest.raises(CalibrationError, match="no se pudo leer"):
        load_calibration(destino)


def test_calibracion_que_no_es_objeto_es_error(tmp_path: Path) -> None:
    destino = tmp_path / "lista.json"
    destino.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(CalibrationError, match="no es un objeto"):
        load_calibration(destino)


def test_formato_desconocido_es_error() -> None:
    crudo = calibracion({"centro": "aaaa"}).to_dict()
    crudo["format"] = "urbia-calibration-v99"
    with pytest.raises(CalibrationError, match="formato de calibración desconocido"):
        Calibration.from_dict(crudo)


def test_calibracion_sin_zonas_es_error() -> None:
    crudo = calibracion({"centro": "aaaa"}).to_dict()
    crudo["zones"] = {}
    with pytest.raises(CalibrationError, match="ninguna zona"):
        Calibration.from_dict(crudo)


def test_calibracion_sin_clave_zones_es_error() -> None:
    crudo = calibracion({"centro": "aaaa"}).to_dict()
    del crudo["zones"]
    with pytest.raises(CalibrationError, match="mal formada"):
        Calibration.from_dict(crudo)


@pytest.mark.parametrize("clave", ["fingerprint", "n_meters", "threshold", "config"])
def test_zona_a_la_que_le_falta_una_clave_es_error(clave: str) -> None:
    crudo = calibracion({"centro": "aaaa"}).to_dict()
    del crudo["zones"]["centro"][clave]
    with pytest.raises(CalibrationError, match="mal formada"):
        Calibration.from_dict(crudo)


def test_umbral_mal_tipado_es_error() -> None:
    crudo = calibracion({"centro": "aaaa"}).to_dict()
    crudo["zones"]["centro"]["threshold"] = "cuatro"
    with pytest.raises(CalibrationError, match="mal formada"):
        Calibration.from_dict(crudo)


# ─────────────────────────────────────────────── el archivo versionado


def test_la_calibracion_versionada_se_lee() -> None:
    if not CALIBRACION_VERSIONADA.exists():
        pytest.fail(f"falta la calibración versionada: {CALIBRACION_VERSIONADA}")
    cal = load_calibration(CALIBRACION_VERSIONADA)
    assert cal.version == "manizales-scan-v1"
    assert cal.magnitude == "voltaje_v"
    assert len(cal.zones) == 6


def test_la_calibracion_versionada_corresponde_a_la_topologia_versionada(
    manizales: list[MeterNode],
) -> None:
    """El test de regresión que sostiene todo lo demás.

    Si alguien toca `manizales_150.json` o el criterio de vecindad sin
    recalibrar, esto falla acá y no en producción.
    """
    cal = load_calibration(CALIBRACION_VERSIONADA)
    cal.verify_topology(graph_fingerprints(build_ami_graph(manizales, GraphConfig())))


def test_la_calibracion_versionada_declara_el_punto_de_operacion_del_servicio() -> None:
    """`step=1`: el servicio desliza de a un bin, no de a una ventana entera."""
    cal = load_calibration(CALIBRACION_VERSIONADA)
    for nombre, zona in cal.zones.items():
        assert zona.frozen.config == DetectorConfig(step=1), nombre
        assert zona.frozen.n_instants == 64, nombre
        assert zona.frozen.threshold > 0.0, nombre


def test_cada_zona_versionada_declara_de_donde_salio() -> None:
    """Un corte sin procedencia no se puede auditar después."""
    cal = load_calibration(CALIBRACION_VERSIONADA)
    for nombre, zona in cal.zones.items():
        assert "manizales-scan-v1" in zona.frozen.source, nombre


def test_la_validacion_versionada_viaja_con_el_umbral() -> None:
    """La cifra operativa —alarmas por hora sin que pase nada— junto al corte."""
    cal = load_calibration(CALIBRACION_VERSIONADA)
    assert set(cal.validation) == set(cal.zones)
    for nombre, datos in cal.validation.items():
        assert datos["horas_simuladas"] > 0, nombre
        assert 0.0 <= datos["fraccion_ventanas"] <= 1.0, nombre


def test_el_archivo_versionado_esta_en_bytes_estables() -> None:
    """Reescribirlo sin cambios no debe producir diff."""
    cal = load_calibration(CALIBRACION_VERSIONADA)
    texto = json.dumps(cal.to_dict(), indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    assert texto == CALIBRACION_VERSIONADA.read_text(encoding="utf-8")


def test_la_calibracion_no_declara_magnitudes_sin_evaluar() -> None:
    """Corriente y potencia tienen σ/media del 35 % y están sin medir.

    Calibrarlas sin evaluar antes sería inventar un punto de operación.
    """
    datos: dict[str, Any] = json.loads(CALIBRACION_VERSIONADA.read_text(encoding="utf-8"))
    assert datos["magnitude"] == "voltaje_v"
