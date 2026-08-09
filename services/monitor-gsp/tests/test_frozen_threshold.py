"""Tests del umbral congelado: cargarlo, verificarlo y serializarlo.

Lo que se prueba acá no es que el número sea correcto —eso lo fija la
calibración— sino que el detector **se niegue** a usar un corte que no
corresponde a su configuración. Es la protección contra el error de
`ESTADO.md` §5.3, la única forma de equivocarse que ningún otro test cubre.
"""

from __future__ import annotations

import pytest

from urbia_monitor_gsp.detector import (
    CollectiveScanDetector,
    DetectorConfig,
    DetectorError,
    FrozenThreshold,
)
from urbia_monitor_gsp.graph.builder import build_zone_graph
from urbia_monitor_gsp.graph.types import GraphConfig, MeterNode, ZoneGraph

SEMILLA = 20260808
SIGMA = 4.4012


def rejilla(zona: str, filas: int, columnas: int) -> list[MeterNode]:
    """Medidores en rejilla regular, de geometría predecible."""
    return [
        MeterNode(
            device_id=f"urbia-cen-mon-{f * columnas + c:04d}",
            zona=zona,
            lat=5.06 + f * 0.001,
            lon=-75.51 + c * 0.001,
        )
        for f in range(filas)
        for c in range(columnas)
    ]


@pytest.fixture(scope="module")
def zona() -> ZoneGraph:
    return build_zone_graph(rejilla("centro", 5, 5), GraphConfig(k=4))


@pytest.fixture(scope="module")
def otra_zona() -> ZoneGraph:
    return build_zone_graph(rejilla("chipre", 5, 5), GraphConfig(k=4))


def _config() -> DetectorConfig:
    return DetectorConfig(window=4, calibration_samples=200)


def _congelado(zona_nombre: str = "centro", **cambios: object) -> FrozenThreshold:
    parametros: dict[str, object] = {
        "zona": zona_nombre,
        "threshold": 3.5,
        "sigma_spatial": SIGMA,
        "config": _config(),
        "seed": SEMILLA,
        "n_instants": 16,
        "source": "data/calibrations/prueba.json",
    }
    parametros.update(cambios)
    return FrozenThreshold(**parametros)  # type: ignore[arg-type]


# ----- carga -----


def test_load_threshold_adopta_el_corte_y_su_procedencia(zona: ZoneGraph) -> None:
    detector = CollectiveScanDetector(zona, SIGMA, _config())
    assert detector.load_threshold(_congelado()) == pytest.approx(3.5)
    assert detector.threshold == pytest.approx(3.5)
    assert detector.threshold_provenance == "data/calibrations/prueba.json"


def test_sin_umbral_no_hay_procedencia(zona: ZoneGraph) -> None:
    detector = CollectiveScanDetector(zona, SIGMA, _config())
    assert detector.threshold_provenance is None


def test_detect_sin_umbral_menciona_las_dos_vias(zona: ZoneGraph) -> None:
    detector = CollectiveScanDetector(zona, SIGMA, _config())
    with pytest.raises(DetectorError, match="load_threshold"):
        _ = detector.threshold


# ----- las tres verificaciones -----


def test_umbral_de_otra_zona_se_rechaza(otra_zona: ZoneGraph) -> None:
    """El estadístico depende del grafo: un corte de otra zona no aplica."""
    detector = CollectiveScanDetector(otra_zona, SIGMA, _config())
    with pytest.raises(DetectorError, match="zona 'centro'"):
        detector.load_threshold(_congelado("centro"))


def test_umbral_con_otra_sigma_se_rechaza(zona: ZoneGraph) -> None:
    detector = CollectiveScanDetector(zona, SIGMA, _config())
    with pytest.raises(DetectorError, match="sigma_spatial"):
        detector.load_threshold(_congelado(sigma_spatial=2.47))


def test_umbral_con_otro_punto_de_operacion_se_rechaza(zona: ZoneGraph) -> None:
    """Cambiar la ventana cambia la distribución del máximo."""
    detector = CollectiveScanDetector(zona, SIGMA, _config())
    otro = DetectorConfig(window=16, calibration_samples=200)
    with pytest.raises(DetectorError, match="punto de operación"):
        detector.load_threshold(_congelado(config=otro))


def test_umbral_con_otros_radios_se_rechaza(zona: ZoneGraph) -> None:
    detector = CollectiveScanDetector(zona, SIGMA, _config())
    otro = DetectorConfig(window=4, scan_radii=(1,), calibration_samples=200)
    with pytest.raises(DetectorError, match="punto de operación"):
        detector.load_threshold(_congelado(config=otro))


@pytest.mark.parametrize("valor", [0.0, -1.0, float("inf"), float("nan")])
def test_umbral_no_finito_o_no_positivo_se_rechaza(zona: ZoneGraph, valor: float) -> None:
    detector = CollectiveScanDetector(zona, SIGMA, _config())
    with pytest.raises(DetectorError, match="finito y > 0"):
        detector.load_threshold(_congelado(threshold=valor))


# ----- ida y vuelta con la calibración -----


def test_freeze_y_load_reproducen_el_mismo_corte(zona: ZoneGraph) -> None:
    """Lo que el script de calibración congela es lo que el servicio adopta."""
    calibrador = CollectiveScanDetector(zona, SIGMA, _config())
    esperado = calibrador.calibrate(SEMILLA, n_instants=16)
    congelado = calibrador.freeze_threshold(SEMILLA, 16, "prueba")

    servicio = CollectiveScanDetector(zona, SIGMA, _config())
    assert servicio.load_threshold(congelado) == pytest.approx(esperado)


def test_freeze_sin_calibrar_falla(zona: ZoneGraph) -> None:
    detector = CollectiveScanDetector(zona, SIGMA, _config())
    with pytest.raises(DetectorError, match="no está calibrado"):
        detector.freeze_threshold(SEMILLA, 16, "prueba")


def test_calibrate_deja_procedencia_legible(zona: ZoneGraph) -> None:
    detector = CollectiveScanDetector(zona, SIGMA, _config())
    detector.calibrate(SEMILLA, n_instants=16)
    assert detector.threshold_provenance == f"calibrate(seed={SEMILLA}, n_instants=16)"


# ----- serialización -----


def test_ida_y_vuelta_por_json(zona: ZoneGraph) -> None:
    original = _congelado()
    recuperado = FrozenThreshold.from_dict(original.to_dict())
    assert recuperado == original


def test_from_dict_conserva_el_objetivo_por_ventana() -> None:
    """`n_instants=None` y `n_instants=16` no son intercambiables."""
    original = _congelado(n_instants=None)
    assert FrozenThreshold.from_dict(original.to_dict()).n_instants is None


def test_from_dict_conserva_step_nulo() -> None:
    config = DetectorConfig(window=4, step=None, calibration_samples=200)
    original = _congelado(config=config)
    assert FrozenThreshold.from_dict(original.to_dict()).config.step is None


@pytest.mark.parametrize("clave", ["zona", "threshold", "sigma_spatial", "config", "seed"])
def test_from_dict_con_clave_faltante_falla(clave: str) -> None:
    datos = _congelado().to_dict()
    del datos[clave]
    with pytest.raises(DetectorError, match="mal formado"):
        FrozenThreshold.from_dict(datos)


def test_from_dict_con_punto_de_operacion_invalido_falla() -> None:
    datos = _congelado().to_dict()
    datos["config"]["window"] = 0
    with pytest.raises(DetectorError, match="mal formado"):
        FrozenThreshold.from_dict(datos)
