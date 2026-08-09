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
zona entera. No es otro tipo de evento: es el **régimen de grupo grande** del
mismo, el caso límite que el detector *no* debe marcar.

## Por qué `depth` no sirve como eje de un barrido

`depth` es el control natural cuando se quiere "la vecindad de un nodo", y
es el que usan todas las mediciones anteriores. Pero **el tamaño que produce
depende de la topología local**: el mismo `depth=2` da 11 nodos en una zona
y 18 en otra, y dentro de una misma zona varía con la semilla. Un barrido
indexado por `depth` no es comparable entre zonas.

Por eso `connected_subgraph` toma el tamaño como parámetro directo. El eje
queda limpio —`m` es un entero de 1 a `n`— y `depth` se conserva intacto
para la familia ya medida.

## Compacto contra extendido

A tamaño fijo, el perímetro todavía es libre: un grupo compacto y uno
alargado con los mismos `m` nodos tienen distinta cantidad de aristas de
corte. Sin esa segunda perilla, tamaño y perímetro quedan confundidos por
construcción y ninguna conclusión del barrido puede separarlos.

Las dos formas de crecimiento **garantizan conexidad por construcción**, que
es lo que las hace comparables:

* `"compacto"`: anchura por capas completas, truncando sólo dentro de la
  última. Todo nodo incluido tiene a su padre incluido.
* `"extendido"`: camino aleatorio. Cada nodo nuevo es vecino del actual, que
  ya estaba visitado.

Un grupo con dos componentes sería una tercera condición experimental, no un
grupo extendido, y por eso ninguna de las dos puede producirlo.
"""

from __future__ import annotations

from collections import deque
from typing import Final, Literal

import numpy as np
import numpy.typing as npt

Shape = Literal["compacto", "extendido"]
"""Forma de crecimiento del grupo, a tamaño fijo."""

SHAPES: Final[tuple[Shape, ...]] = ("compacto", "extendido")

_MAX_PASOS_POR_NODO: Final = 1000
"""Cota de pasos del camino aleatorio, por nodo pedido.

Sobre una componente con suficientes nodos el camino los visita casi
seguramente, así que la cota no debería alcanzarse nunca. Está para que un
grafo patológico falle con un mensaje en vez de colgarse.
"""


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


def _validar_grafo(adjacency: npt.NDArray[np.float64], seed_index: int) -> npt.NDArray[np.float64]:
    """Comprueba la adyacencia y la semilla, comunes a todos los recorridos.

    Args:
        adjacency: Matriz `(n, n)` simétrica con pesos no negativos.
        seed_index: Posición del nodo semilla.

    Returns:
        La adyacencia como arreglo.

    Raises:
        ValueError: Si la matriz no es cuadrada o la semilla cae fuera.
    """
    matriz = np.asarray(adjacency)
    if matriz.ndim != 2 or matriz.shape[0] != matriz.shape[1]:
        raise ValueError(f"la adyacencia debe ser cuadrada, recibida {matriz.shape}")
    if not 0 <= seed_index < matriz.shape[0]:
        raise ValueError(f"seed_index {seed_index} fuera del grafo de {matriz.shape[0]} nodos")
    return matriz


def _vecinos(matriz: npt.NDArray[np.float64], nodo: int) -> npt.NDArray[np.int64]:
    """Posiciones de los vecinos de un nodo.

    Args:
        matriz: Adyacencia validada.
        nodo: Posición del nodo.

    Returns:
        Vector con las posiciones de los vecinos, en orden creciente.
    """
    return np.asarray(np.flatnonzero(matriz[nodo] > 0.0), dtype=np.int64)


def _error_componente(seed_index: int, alcanzables: int, size_target: int) -> ValueError:
    """Error único de "el grupo pedido no cabe en la componente".

    Lo levantan los dos crecimientos, para que el mensaje no dependa de la
    forma: el problema es del grafo, no de cómo se lo recorrió.

    Args:
        seed_index: Nodo semilla.
        alcanzables: Nodos que la semilla alcanza.
        size_target: Nodos pedidos.

    Returns:
        El error, para que lo levante quien llama.
    """
    return ValueError(
        f"la componente conexa de {seed_index} tiene {alcanzables} nodos y se pidieron "
        f"{size_target}: un grupo de ese tamaño no sería conexo"
    )


def _crecer_compacto(
    matriz: npt.NDArray[np.float64],
    seed_index: int,
    size_target: int,
    rng: np.random.Generator,
) -> set[int]:
    """Anchura por capas, barajando dentro de cada capa.

    Las capas se consumen enteras y sólo se trunca dentro de la última, de
    modo que todo nodo incluido tiene a su padre incluido y el grupo queda
    conexo. El barajado usa el generador y no el orden de índice: el orden
    de índice arrastra el orden geográfico de los `device_id` y sesgaría la
    forma del grupo siempre en la misma dirección.

    Args:
        matriz: Adyacencia validada.
        seed_index: Nodo semilla.
        size_target: Cantidad de nodos pedida.
        rng: Generador ya sembrado.

    Returns:
        Posiciones del grupo.

    Raises:
        ValueError: Si la componente conexa de la semilla se agota antes de
            juntar el tamaño pedido.
    """
    elegidos = {seed_index}
    capa = [seed_index]
    while len(elegidos) < size_target:
        siguiente: list[int] = []
        for nodo in capa:
            for vecino in _vecinos(matriz, nodo):
                posicion = int(vecino)
                if posicion not in elegidos and posicion not in siguiente:
                    siguiente.append(posicion)
        if not siguiente:
            raise _error_componente(seed_index, len(elegidos), size_target)
        barajada = [siguiente[i] for i in rng.permutation(len(siguiente))]
        faltan = size_target - len(elegidos)
        elegidos.update(barajada[:faltan])
        capa = barajada
    return elegidos


def _crecer_extendido(
    matriz: npt.NDArray[np.float64],
    seed_index: int,
    size_target: int,
    rng: np.random.Generator,
) -> set[int]:
    """Camino aleatorio: cada nodo nuevo es vecino del actual.

    Produce grupos alargados, con más aristas de corte que un compacto del
    mismo tamaño. La conexidad está garantizada porque el nodo que se agrega
    siempre es vecino de uno ya visitado.

    Args:
        matriz: Adyacencia validada.
        seed_index: Nodo semilla.
        size_target: Cantidad de nodos pedida.
        rng: Generador ya sembrado.

    Returns:
        Posiciones del grupo.

    Raises:
        ValueError: Si la componente conexa de la semilla se agota antes de
            juntar el tamaño pedido, o si el camino agota su cota de pasos.
    """
    elegidos = {seed_index}
    actual = seed_index
    tope = _MAX_PASOS_POR_NODO * size_target
    for _ in range(tope):
        if len(elegidos) >= size_target:
            return elegidos
        vecinos = _vecinos(matriz, actual)
        if vecinos.size == 0:
            raise _error_componente(seed_index, len(elegidos), size_target)
        actual = int(vecinos[rng.integers(vecinos.size)])
        elegidos.add(actual)
    raise _error_componente(
        seed_index, len(k_hop(matriz, seed_index, matriz.shape[0])), size_target
    )


def connected_subgraph(
    adjacency: npt.NDArray[np.float64],
    seed_index: int,
    size_target: int,
    *,
    shape: Shape = "compacto",
    rng: np.random.Generator,
) -> tuple[int, ...]:
    """Grupo conexo de tamaño exacto, creciendo desde una semilla.

    Es el mecanismo que permite barrer el tamaño del grupo como variable
    independiente. A diferencia de `k_hop`, el tamaño es un parámetro y no
    una consecuencia de la topología local, así que el eje es comparable
    entre zonas y entre semillas.

    Args:
        adjacency: Matriz `(n, n)` simétrica con pesos no negativos.
        seed_index: Posición del nodo semilla, siempre incluida.
        size_target: Cantidad exacta de nodos del grupo.
        shape: `"compacto"` crece por capas; `"extendido"` por camino
            aleatorio, que a igual tamaño deja más perímetro.
        rng: Generador ya sembrado. Es obligatorio: sin él el grupo no sería
            reproducible y la verdad de referencia dejaría de servir.

    Returns:
        Posiciones del grupo, en orden creciente. Siempre conexo y de
        exactamente `size_target` nodos.

    Raises:
        ValueError: Si la matriz no es cuadrada, si `seed_index` cae fuera,
            si `size_target` no está en `[1, n]`, o si la componente conexa
            de la semilla tiene menos nodos que los pedidos.
    """
    matriz = _validar_grafo(adjacency, seed_index)
    n = matriz.shape[0]
    if not 1 <= size_target <= n:
        raise ValueError(
            f"size_target debe estar en [1, {n}], recibido {size_target}: el grupo no "
            f"puede tener menos de un nodo ni más que la zona"
        )
    if shape not in SHAPES:
        raise ValueError(f"shape debe ser uno de {SHAPES}, recibido '{shape}'")

    if shape == "compacto":
        elegidos = _crecer_compacto(matriz, seed_index, size_target, rng)
    else:
        elegidos = _crecer_extendido(matriz, seed_index, size_target, rng)
    return tuple(sorted(elegidos))


def boundary_edges(
    adjacency: npt.NDArray[np.float64],
    nodes: tuple[int, ...],
) -> int:
    """Aristas con exactamente un extremo dentro del grupo.

    Es el perímetro del grupo, y la cantidad que gobierna la firma espectral
    según `experiments/firma-espectral/` §2. Se registra en la verdad de
    referencia para poder contrastar después si la detección la sigue.

    Args:
        adjacency: Matriz `(n, n)` simétrica con pesos no negativos.
        nodes: Posiciones del grupo.

    Returns:
        Cantidad de aristas de corte.
    """
    matriz = np.asarray(adjacency)
    dentro = np.zeros(matriz.shape[0], dtype=np.bool_)
    dentro[list(nodes)] = True
    return int((matriz[np.ix_(dentro, ~dentro)] > 0.0).sum())


def is_connected(
    adjacency: npt.NDArray[np.float64],
    nodes: tuple[int, ...],
) -> bool:
    """Comprueba que un grupo induzca un subgrafo de una sola componente.

    Existe para poder verificarlo en los tests: un grupo con dos componentes
    sería una condición experimental distinta de un grupo extendido, y
    confundirlas invalidaría el contraste de forma.

    Args:
        adjacency: Matriz `(n, n)` simétrica con pesos no negativos.
        nodes: Posiciones del grupo.

    Returns:
        `True` si el subgrafo inducido es conexo. Un grupo vacío no lo es.
    """
    if not nodes:
        return False
    matriz = np.asarray(adjacency)
    pendientes = set(nodes)
    alcanzados = {nodes[0]}
    frontera = deque([nodes[0]])
    while frontera:
        nodo = frontera.popleft()
        for vecino in _vecinos(matriz, nodo):
            posicion = int(vecino)
            if posicion in pendientes and posicion not in alcanzados:
                alcanzados.add(posicion)
                frontera.append(posicion)
    return alcanzados == pendientes


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
