"""Vecindarios del grafo: qué nodos abarca un evento.

Un evento colectivo se define sobre un nodo semilla y sus vecinos hasta
cierta profundidad. Esa profundidad es el único control que tiene el
experimento sobre el **tamaño** del grupo, y por eso conviene saber qué
tamaño produce.

Medido sobre la topología de los 150 con k-NN k=4 simetrizado por unión,
tamaño mediano del vecindario y fracción de la zona que cubre:

    depth = 0        1 nodo         ~4 %    la semilla sola: control individual
    depth = 1      5 a 6 nodos    20-27 %
    depth = 2     11 a 12 nodos   40-55 %
    depth = 3     17 a 19 nodos   63-85 %   degenerado

En profundidad 3 casi no queda vecindario sano contra el cual contrastar:
el evento deja de ser una discordancia local y se vuelve un corrimiento de
zona entera. Es un caso legítimo —de hecho es la familia de modo común, que
el detector *no* debería marcar— pero no es lo que pide una desviación
colectiva sutil.
"""

from __future__ import annotations

from collections import deque

import numpy as np
import numpy.typing as npt


def k_hop(
    adjacency: npt.NDArray[np.float64],
    seed_index: int,
    depth: int,
) -> tuple[int, ...]:
    """Nodos alcanzables desde una semilla en a lo sumo `depth` saltos.

    Recorrido en anchura sobre la matriz de adyacencia. El resultado
    incluye siempre a la semilla, y viene ordenado de forma creciente para
    que sea reproducible con independencia del orden de exploración.

    Args:
        adjacency: Matriz `(n, n)` simétrica con pesos no negativos. Sólo
            se mira si la entrada es positiva: los pesos no cambian quién
            es vecino de quién.
        seed_index: Posición del nodo semilla.
        depth: Cantidad máxima de saltos. `0` devuelve sólo la semilla.

    Returns:
        Posiciones de los nodos del vecindario, en orden creciente.

    Raises:
        ValueError: Si la matriz no es cuadrada, si `seed_index` cae fuera
            del grafo, o si `depth` es negativo.
    """
    matriz = np.asarray(adjacency)
    if matriz.ndim != 2 or matriz.shape[0] != matriz.shape[1]:
        raise ValueError(f"la adyacencia debe ser cuadrada, recibida {matriz.shape}")
    n = matriz.shape[0]
    if not 0 <= seed_index < n:
        raise ValueError(f"seed_index {seed_index} fuera del grafo de {n} nodos")
    if depth < 0:
        raise ValueError(f"depth debe ser >= 0, recibido {depth}")

    vistos = {seed_index}
    frontera: deque[tuple[int, int]] = deque([(seed_index, 0)])
    while frontera:
        nodo, salto = frontera.popleft()
        if salto == depth:
            continue
        for vecino in np.flatnonzero(matriz[nodo] > 0.0):
            posicion = int(vecino)
            if posicion not in vistos:
                vistos.add(posicion)
                frontera.append((posicion, salto + 1))
    return tuple(sorted(vistos))


def neighborhood_sizes(
    adjacency: npt.NDArray[np.float64],
    depth: int,
) -> npt.NDArray[np.int64]:
    """Tamaño del vecindario de cada nodo, para diagnosticar una topología.

    Sirve para saber, antes de inyectar, qué fracción de la zona va a
    abarcar un evento a esa profundidad.

    Args:
        adjacency: Matriz de adyacencia del subgrafo.
        depth: Profundidad del vecindario.

    Returns:
        Vector `(n,)` con el tamaño del vecindario de cada nodo.
    """
    matriz = np.asarray(adjacency)
    return np.array(
        [len(k_hop(matriz, i, depth)) for i in range(matriz.shape[0])],
        dtype=np.int64,
    )
