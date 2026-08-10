"""Tests del ranking de candidatas que acompaña a cada detección.

Guardar sólo la bola ganadora impide reconstruir después el punto de
operación: no se distingue un máximo despegado del resto de un empate en el
que la ganadora salió por azar. Lo que estos tests fijan es que el ranking
esté completo, ordenado, y que su cabeza sea exactamente la ganadora.
"""

from __future__ import annotations

import numpy as np
import pytest

from urbia_monitor_gsp.detector import (
    CollectiveScanDetector,
    Detection,
    DetectorConfig,
    DetectorError,
    ScanCandidate,
)
from urbia_monitor_gsp.graph.builder import build_ami_graph
from urbia_monitor_gsp.graph.types import GraphConfig, MeterNode, ZoneGraph

SEMILLA = 20260808
SIGMA = 4.4012


@pytest.fixture(scope="module")
def zona(manizales: list[MeterNode]) -> ZoneGraph:
    return build_ami_graph(manizales, GraphConfig()).zones["centro"]


@pytest.fixture(scope="module")
def detector(zona: ZoneGraph) -> CollectiveScanDetector:
    det = CollectiveScanDetector(zona, SIGMA, DetectorConfig(window=4, step=1))
    det.calibrate(SEMILLA)
    return det


@pytest.fixture(scope="module")
def senal(zona: ZoneGraph) -> np.ndarray:
    return np.random.default_rng(SEMILLA).normal(220.0, SIGMA, size=(8, zona.n_meters))


def test_ranking_incluye_todas_las_candidatas(
    detector: CollectiveScanDetector, senal: np.ndarray
) -> None:
    for deteccion in detector.detect(senal):
        assert len(deteccion.ranking) == detector.n_candidates


def test_ranking_ordenado_por_contraste_descendente(
    detector: CollectiveScanDetector, senal: np.ndarray
) -> None:
    for deteccion in detector.detect(senal):
        valores = [c.statistic for c in deteccion.ranking]
        assert valores == sorted(valores, reverse=True)


def test_cabeza_del_ranking_es_la_ganadora(
    detector: CollectiveScanDetector, senal: np.ndarray
) -> None:
    """La ganadora que reportan los campos y `ranking[0]` son la misma bola.

    No es redundante con el orden: `argmax` y `argsort` podrían resolver un
    empate de forma distinta y dejar `statistic` apuntando a una bola y el
    ranking a otra.
    """
    for deteccion in detector.detect(senal):
        cabeza = deteccion.ranking[0]
        assert cabeza.statistic == deteccion.statistic
        if deteccion.detected:
            assert cabeza.seed_index == deteccion.seed_index
            assert cabeza.seed_device_id == deteccion.seed_device_id
            assert cabeza.radius == deteccion.radius
            assert cabeza.size == len(deteccion.node_indices)


def test_empate_resuelto_igual_por_los_campos_y_por_el_ranking(zona: ZoneGraph) -> None:
    """Con la señal constante todos los contrastes valen cero y todo empata."""
    det = CollectiveScanDetector(zona, SIGMA, DetectorConfig(window=1))
    det.calibrate(SEMILLA)
    (deteccion,) = det.detect(np.full(zona.n_meters, 220.0))

    assert not deteccion.detected
    assert deteccion.statistic == pytest.approx(0.0)
    assert deteccion.ranking[0].seed_index == det._meta[0][0]
    assert deteccion.ranking[0].radius == det._meta[0][1]


def test_candidata_declara_el_tamano_de_su_bola(
    detector: CollectiveScanDetector, senal: np.ndarray, zona: ZoneGraph
) -> None:
    """El tamaño tiene que ser el de la bola, no el de la zona.

    Es lo que permite al consumidor reconstruir la bola desde el grafo y
    verificar que reconstruyó la correcta.
    """
    (deteccion, *_) = detector.detect(senal)
    for candidata in deteccion.ranking:
        assert 1 <= candidata.size < zona.n_meters
        assert candidata.seed_device_id == zona.device_ids[candidata.seed_index]


def test_ranking_serializado_completo_por_defecto(
    detector: CollectiveScanDetector, senal: np.ndarray
) -> None:
    (deteccion, *_) = detector.detect(senal)
    crudo = deteccion.to_dict()
    assert crudo["candidatas_evaluadas"] == detector.n_candidates
    assert len(crudo["ranking"]) == detector.n_candidates


def test_top_k_recorta_pero_deja_el_total_visible(
    detector: CollectiveScanDetector, senal: np.ndarray
) -> None:
    """Recortar no puede hacer creer que se evaluaron menos bolas."""
    (deteccion, *_) = detector.detect(senal)
    crudo = deteccion.to_dict(top_k=3)
    assert len(crudo["ranking"]) == 3
    assert crudo["candidatas_evaluadas"] == detector.n_candidates
    assert crudo["ranking"][0]["statistic"] == crudo["statistic"]


def test_top_k_mayor_que_el_ranking_no_inventa_candidatas(
    detector: CollectiveScanDetector, senal: np.ndarray
) -> None:
    (deteccion, *_) = detector.detect(senal)
    crudo = deteccion.to_dict(top_k=detector.n_candidates + 50)
    assert len(crudo["ranking"]) == detector.n_candidates


def test_top_k_cero_publica_la_deteccion_sin_ranking(
    detector: CollectiveScanDetector, senal: np.ndarray
) -> None:
    (deteccion, *_) = detector.detect(senal)
    crudo = deteccion.to_dict(top_k=0)
    assert crudo["ranking"] == []
    assert crudo["statistic"] == deteccion.statistic


def test_top_k_negativo_es_error(detector: CollectiveScanDetector, senal: np.ndarray) -> None:
    (deteccion, *_) = detector.detect(senal)
    with pytest.raises(DetectorError, match="top_k"):
        deteccion.to_dict(top_k=-1)


def test_deteccion_sin_ranking_se_serializa_igual() -> None:
    """`ranking` tiene defecto para no romper a quien arma detecciones a mano."""
    deteccion = Detection(
        zona="centro",
        window_start=0,
        window_end=16,
        statistic=1.0,
        threshold=4.0,
        detected=False,
        seed_index=None,
        seed_device_id=None,
        radius=None,
        node_indices=(),
        device_ids=(),
    )
    crudo = deteccion.to_dict()
    assert crudo["ranking"] == []
    assert crudo["candidatas_evaluadas"] == 0


def test_candidata_serializa_todos_sus_campos() -> None:
    candidata = ScanCandidate(
        seed_index=3,
        seed_device_id="urbia-cen-mon-0003",
        radius=2,
        size=11,
        statistic=5.5,
    )
    assert candidata.to_dict() == {
        "seed_index": 3,
        "seed_device_id": "urbia-cen-mon-0003",
        "radius": 2,
        "size": 11,
        "statistic": 5.5,
    }
