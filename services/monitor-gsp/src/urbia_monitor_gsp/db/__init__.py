"""Lectura de medidores desde PostgreSQL.

Vive fuera de `graph` a propósito y la dependencia va en un solo sentido:
`db` importa de `graph`, nunca al revés. Ese es el motivo de que el núcleo
del grafo dependa sólo de numpy y pueda correr en un nodo de borde sin
driver de base de datos, o importarse desde un notebook sin levantar nada.

Requiere el extra `db` del paquete:

    pip install -e '.[db]'
"""

from .config import DatabaseSettings, get_settings
from .meters import (
    IncompleteMeterError,
    NoMetersFoundError,
    load_ami_graph,
    load_meters,
)

__all__ = [
    "DatabaseSettings",
    "IncompleteMeterError",
    "NoMetersFoundError",
    "get_settings",
    "load_ami_graph",
    "load_meters",
]
