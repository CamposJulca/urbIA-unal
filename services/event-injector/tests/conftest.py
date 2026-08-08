"""Fixtures compartidas de los tests del inyector.

Se apoyan en los mismos artefactos versionados que usan los experimentos:
la topología de los 150, el contrato del productor y el perfil medido. Un
test que inventara sus propios rangos verificaría el inyector contra una
realidad que no existe.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from urbia_monitor_gsp.graph import AmiGraph, GraphConfig, MeterNode, ZoneGraph, build_ami_graph

from urbia_events import SignalBounds, SignalProfile, load_bounds, load_profile
from urbia_events.types import Magnitude

_RAIZ = Path(__file__).parents[3]
TOPOLOGIA = _RAIZ / "data" / "topologies" / "manizales_150.json"
ESQUEMA = _RAIZ / "data" / "schemas" / "payload_schema_v1.json"
PERFIL = _RAIZ / "data" / "profiles" / "manizales_signal_v1.json"

SEMILLA = 20260808
"""Semilla de los tests. Fija: las cifras de los docstrings dependen de ella."""


@pytest.fixture(scope="session")
def grafo() -> AmiGraph:
    """Grafo AMI de los 150 medidores con la construcción por defecto."""
    if not TOPOLOGIA.exists():
        pytest.fail(f"falta la topología: {TOPOLOGIA}")
    datos = json.loads(TOPOLOGIA.read_text(encoding="utf-8"))
    meters = [MeterNode(**m) for m in datos["meters"]]
    return build_ami_graph(meters, GraphConfig())


@pytest.fixture(scope="session")
def zona_mono(grafo: AmiGraph) -> ZoneGraph:
    """Una zona monofásica: centro, 25 medidores."""
    return grafo.zones["centro"]


@pytest.fixture(scope="session")
def zona_tri(grafo: AmiGraph) -> ZoneGraph:
    """Una zona trifásica: la_enea, la más rala de las seis."""
    return grafo.zones["la_enea"]


@pytest.fixture(scope="session")
def perfil() -> SignalProfile:
    """Perfil de señal medido y congelado."""
    if not PERFIL.exists():
        pytest.fail(f"falta el perfil de señal: {PERFIL}")
    return load_profile(PERFIL)


@pytest.fixture(scope="session")
def limites() -> dict[Magnitude, SignalBounds]:
    """Límites duros del contrato del productor."""
    if not ESQUEMA.exists():
        pytest.fail(f"falta el esquema del productor: {ESQUEMA}")
    return load_bounds(ESQUEMA)


def senal_normal(
    zone: ZoneGraph,
    perfil: SignalProfile,
    magnitude: Magnitude = "voltaje_v",
    n_instantes: int = 1,
    semilla: int = SEMILLA,
) -> np.ndarray:
    """Señal sintética con la media y la dispersión medidas de la zona.

    No es telemetría real, pero reproduce el estadístico que importa: la
    dispersión **espacial**, que es la que decide si una desviación es
    sutil o evidente.

    Args:
        zone: Subgrafo zonal.
        perfil: Perfil medido.
        magnitude: Magnitud a simular.
        n_instantes: Instantes a generar.
        semilla: Semilla del ruido.

    Returns:
        Matriz `(n_instantes, n_medidores)`.
    """
    from urbia_events import device_type_of

    tipo = device_type_of(zone.device_ids[0])
    p = perfil.get(magnitude, tipo)
    rng = np.random.default_rng(semilla)
    return np.asarray(rng.normal(p.mean, p.sigma_spatial, size=(n_instantes, zone.n_meters)))
