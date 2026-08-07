"""Núcleo puro del grafo AMI: geometría, tipos y aparato espectral.

Sólo depende de numpy. No importa drivers de base de datos ni
configuración de servicio, así que puede usarse desde un notebook sin
levantar nada.
"""

from .geo import (
    LocalFrame,
    curvature_radii,
    geodesic_distance_m,
    local_frame,
    pairwise_distances_m,
    project_to_local_meters,
)
from .types import (
    MIN_METERS_PER_ZONE,
    AmiGraph,
    BuildStats,
    GraphConfig,
    InsufficientMetersError,
    InvalidCoordinateError,
    InvalidGraphConfigError,
    MeterNode,
    MonitorGspError,
    ZoneGraph,
)

__all__ = [
    "MIN_METERS_PER_ZONE",
    "AmiGraph",
    "BuildStats",
    "GraphConfig",
    "InsufficientMetersError",
    "InvalidCoordinateError",
    "InvalidGraphConfigError",
    "LocalFrame",
    "MeterNode",
    "MonitorGspError",
    "ZoneGraph",
    "curvature_radii",
    "geodesic_distance_m",
    "local_frame",
    "pairwise_distances_m",
    "project_to_local_meters",
]
