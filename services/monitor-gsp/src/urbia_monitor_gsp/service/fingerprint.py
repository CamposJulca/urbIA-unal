"""Huella de la topología: qué grafo es el que el umbral supone.

Un umbral congelado vale para un grafo. Si el padrón de medidores cambia
—se agrega uno, se da de baja otro, se corrige una coordenada y con ella la
vecindad— el corte deja de corresponder al sistema real y el servicio pasa a
detectar sobre un grafo que ya no existe, sin que nada avise.

La huella existe para que eso **falle ruidosamente** en vez de degradarse en
silencio: se calcula al congelar la calibración, viaja con ella, y el
servicio la recontrasta al arrancar y cada tanto mientras corre.

## Sobre qué se calcula, y por qué sobre eso

El corte sale de la distribución del máximo de `contrasts` sobre las bolas
candidatas bajo la hipótesis nula. Mirando la cadena completa —`contrasts`
usa las máscaras y `n`; las máscaras salen de `candidate_balls`, que recorre
`k_hop` sobre `adjacency > 0`— lo que el umbral realmente supone es:

* los medidores de la zona y su **orden canónico**, que indexa todo;
* el **conjunto de aristas**, que determina qué bolas hay y de qué tamaño.

Los **pesos** de las aristas no entran: con `weighting="binary"` son 1, y
aunque fueran gaussianos, `candidate_balls` sólo pregunta si el peso es
positivo. Por eso la huella se toma sobre la estructura discreta y no sobre
los flotantes de la matriz.

Que sea discreta importa por una razón concreta: este servicio va a mudarse
al nodo de borde para medir H1. Una huella sobre bytes de `float64` podría
diferir en el último bit entre máquinas y hacer fallar el arranque por una
diferencia que no cambia ninguna detección. Un conjunto de pares de enteros
no tiene ese problema.
"""

from __future__ import annotations

import hashlib
from typing import Final

import numpy as np

from ..graph.types import AmiGraph, ZoneGraph

_VERSION: Final = "urbia-zone-fingerprint-v1"
"""Etiqueta del algoritmo.

Va dentro del hash: si algún día cambia qué se toma en cuenta, las huellas
viejas dejan de coincidir por construcción en vez de coincidir por accidente.
"""


def zone_fingerprint(zone: ZoneGraph) -> str:
    """Huella de la estructura de una zona.

    Args:
        zone: Subgrafo zonal.

    Returns:
        Digest hexadecimal de 32 caracteres.
    """
    hasher = hashlib.blake2b(digest_size=16)
    hasher.update(_VERSION.encode("utf-8"))
    hasher.update(zone.zona.encode("utf-8"))
    hasher.update(str(zone.n_meters).encode("utf-8"))
    for device_id in zone.device_ids:
        hasher.update(b"\x00")
        hasher.update(device_id.encode("utf-8"))

    # Triángulo superior: la adyacencia es simétrica y contar cada arista
    # dos veces no agregaría información.
    filas, columnas = np.nonzero(np.triu(zone.adjacency > 0.0, k=1))
    hasher.update(b"\x01")
    for i, j in zip(filas.tolist(), columnas.tolist(), strict=True):
        hasher.update(f"{i}-{j};".encode())
    return hasher.hexdigest()


def graph_fingerprints(graph: AmiGraph) -> dict[str, str]:
    """Huella de cada zona del grafo.

    Args:
        graph: Grafo AMI completo.

    Returns:
        Huella indexada por nombre de zona.
    """
    return {zona: zone_fingerprint(zone) for zona, zone in graph.zones.items()}
