"""Fixtures compartidas por los tests del monitor GSP.

La topología real vive acá y no en un módulo de test concreto porque más
de un módulo la necesita: `test_builder` fija sobre ella las cifras del
criterio de vecindad y `test_geo` las del error de proyección.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from urbia_monitor_gsp.graph.types import MeterNode

TOPOLOGIA = Path(__file__).parents[3] / "data" / "topologies" / "manizales_150.json"
"""Instantánea versionada de `ami_meters`. Sustrato de toda la regresión."""


@pytest.fixture(scope="session")
def manizales() -> list[MeterNode]:
    """Los 150 medidores reales, desde la topología versionada.

    Returns:
        Los medidores como nodos del grafo, en el orden del archivo.
    """
    if not TOPOLOGIA.exists():
        pytest.fail(f"falta la topología de regresión: {TOPOLOGIA}")
    datos = json.loads(TOPOLOGIA.read_text(encoding="utf-8"))
    return [MeterNode(**m) for m in datos["meters"]]
