"""Núcleo puro del grafo AMI: geometría, tipos y aparato espectral.

Sólo depende de numpy. No importa drivers de base de datos ni
configuración de servicio, así que puede usarse desde un notebook sin
levantar nada.
"""

from .builder import build_ami_graph, build_zone_graph
from .geo import (
    LocalFrame,
    curvature_radii,
    geodesic_distance_m,
    local_frame,
    pairwise_distances_m,
    project_to_local_meters,
)
from .spectral import (
    connected_components,
    degenerate_groups,
    degree_vector,
    eigenvalue_zero_tolerance,
    fiedler_value,
    gft,
    graph_fourier_basis,
    igft,
    laplacian,
    normalized_laplacian,
    zero_multiplicity,
)
from .types import (
    MIN_METERS_PER_ZONE,
    AmiGraph,
    BuildStats,
    GraphConfig,
    InsufficientMetersError,
    InvalidAdjacencyError,
    InvalidCoordinateError,
    InvalidGraphConfigError,
    MeterNode,
    MonitorGspError,
    ZeroDegreeNodeError,
    ZoneGraph,
)

__all__ = [
    "MIN_METERS_PER_ZONE",
    "AmiGraph",
    "BuildStats",
    "GraphConfig",
    "InsufficientMetersError",
    "InvalidAdjacencyError",
    "InvalidCoordinateError",
    "InvalidGraphConfigError",
    "LocalFrame",
    "MeterNode",
    "MonitorGspError",
    "ZeroDegreeNodeError",
    "ZoneGraph",
    "build_ami_graph",
    "build_zone_graph",
    "connected_components",
    "curvature_radii",
    "degenerate_groups",
    "degree_vector",
    "eigenvalue_zero_tolerance",
    "fiedler_value",
    "geodesic_distance_m",
    "gft",
    "graph_fourier_basis",
    "igft",
    "laplacian",
    "local_frame",
    "normalized_laplacian",
    "pairwise_distances_m",
    "project_to_local_meters",
    "zero_multiplicity",
]
