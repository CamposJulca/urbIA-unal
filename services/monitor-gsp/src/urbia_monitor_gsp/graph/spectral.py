"""Aparato espectral sobre grafos: Laplaciano, base de Fourier y GFT.

Portado del notebook `01_gsp_hello_world.ipynb` (E6), donde la pipeline
`A → L → L_norm → eigh → GFT` quedó validada sobre un grafo de juguete.
NumPy puro, sin pygsp: con 20 a 30 nodos por zona `numpy.linalg.eigh`
resuelve en microsegundos.

Todas las funciones operan sobre matrices y vectores. No saben qué es una
zona ni un medidor: el acoplamiento con el dominio AMI vive en `builder`.

Tres decisiones numéricas, con su justificación:

**Nodos de grado cero.** `normalized_laplacian` levanta
`ZeroDegreeNodeError` en vez de producir infinitos. Un NaN que nace en
`D^(-1/2)` se propaga a todo el espectro y aparece mucho después,
irreconocible. El Laplaciano combinatorio sí admite nodos aislados y se
puede usar en su lugar.

**Umbral de cero.** Un único origen: `eigenvalue_zero_tolerance`, con la
forma que usa `numpy.linalg.matrix_rank`, `tol = n · eps · λ_max`. Ningún
otro número mágico decide qué es cero en este módulo. Medido sobre los
seis subgrafos zonales reales (150 medidores, k-NN k=4 simetrizado):

    tolerancia                     6,7e-15 a 1,1e-14
    |λ_0| que devuelve eigh        ≤ 1e-15
    primer autovalor no nulo       0,050 a 0,124

Es decir, casi catorce órdenes de magnitud entre el ruido numérico y la
señal más chica, en el peor caso de las seis zonas. Sobre el grafo global
bloque-diagonal de los 150 medidores la holgura es menor pero sigue siendo
cómoda: la tolerancia vale 5,3e-14 y el gap más chico entre autovalores
distintos es 3,3e-5, casi nueve órdenes por encima.

El umbral no es entonces un 1e-12 elegido a ojo, y tampoco depende de
haber acertado el valor: sobre ese grafo global cualquier tolerancia entre
4,5e-16 (el mayor `|λ_0|` observado) y 3,3e-5 (el gap más chico) produce el
mismo conteo de componentes **y** la misma partición en subespacios
propios. Son once órdenes de margen; `eigenvalue_zero_tolerance` cae
holgadamente adentro. Lo que importa es que haya un solo origen para ese
número, no cuál de los once órdenes se elija.

**Degeneración.** Los autovalores repetidos existen y no son una rareza:
un par de nodos gemelos —misma vecindad cerrada— adyacentes y de grado `d`
produce el autovalor exacto `1 + 1/d`. Con k-NN k=4 sobre los 150
medidores reales eso da multiplicidad 6 en λ=1,25 en la zona palermo, 3 en
centro y 2 en palogrande y universitario. Dentro de un subespacio propio
degenerado **la base es arbitraria**: `eigh` devuelve una cualquiera, y
permutar el orden de los nodos la cambia. Consecuencia medida sobre
palermo (subespacio de dimensión 6 en λ=1,25), permutando el orden de los
nodos y comparando contra el resultado sin permutar:

    autovalores                          idénticos, ~1e-15
    energía por subespacio propio        idéntica,  ~1e-12
    filtro `L_norm · x`                  idéntico,  ~1e-15
    `|x_hat[k]|` de un modo individual   difiere en O(0,1)

Las tres primeras filas son ruido de redondeo; la cuarta es una
discrepancia real. Su valor exacto depende de la señal y de la permutación
concretas —por eso acá va como orden de magnitud y no como decimal—, pero
que sea O(0,1) sobre una señal de media 10 y desviación 0,3 no es un
detalle numérico: es el coeficiente diciendo otra cosa.

Es decir: lo que dependa del subespacio completo es reproducible; lo que
dependa de un autovector suelto dentro de un subespacio degenerado, no.
`degenerate_groups` expone esos subespacios para que el consumidor pueda
agrupar. El detector pasaaltos `(L_norm · x)²` que E6 dejó como bueno es
invariante; el de ventana abrupta que E6 descartó puede no serlo, si el
corte parte un subespacio por la mitad — una razón más, ahora numérica,
para no usarlo.

`graph_fourier_basis` sí fija el signo de cada autovector, que es
arbitrario incluso sin degeneración.
"""

from __future__ import annotations

from collections import deque
from typing import Final

import numpy as np
import numpy.typing as npt

from .types import InvalidAdjacencyError, ZeroDegreeNodeError

_EPS: Final = float(np.finfo(np.float64).eps)

_SYMMETRY_ATOL: Final = 1e-12
"""Holgura para aceptar una matriz como simétrica.

No es un umbral de cero espectral: sólo absorbe el error de redondeo de
construir la matriz. Las adyacencias se arman por asignación simétrica
explícita, así que en la práctica la diferencia es exactamente cero.
"""


def eigenvalue_zero_tolerance(
    n: int,
    lambda_max: float | None = None,
) -> float:
    """Umbral por debajo del cual un autovalor se considera nulo.

    Misma forma que usa `numpy.linalg.matrix_rank` para decidir el rango:
    el error de `eigh` sobre una matriz simétrica es del orden de
    `eps · ‖M‖₂`, y el factor `n` cubre la acumulación sobre la dimensión.

    Args:
        n: Dimensión de la matriz.
        lambda_max: Mayor autovalor en magnitud. Si es `None` se toma 2,
            la cota superior del espectro de un Laplaciano normalizado.

    Returns:
        Tolerancia absoluta, en las mismas unidades que los autovalores.

    Raises:
        ValueError: Si `n` no es positivo.
    """
    if n <= 0:
        raise ValueError(f"n debe ser positivo, recibido {n}")
    escala = 2.0 if lambda_max is None else max(abs(lambda_max), 1.0)
    return n * _EPS * escala


def _validate_adjacency(adjacency: npt.ArrayLike) -> npt.NDArray[np.float64]:
    """Valida y normaliza una matriz de adyacencia.

    Args:
        adjacency: Matriz cuadrada, simétrica, no negativa y sin lazos.

    Returns:
        La matriz como array de float64.

    Raises:
        InvalidAdjacencyError: Si no es cuadrada, no es simétrica, tiene
            pesos negativos o tiene diagonal no nula.
    """
    matrix = np.asarray(adjacency, dtype=np.float64)
    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1]:
        raise InvalidAdjacencyError(
            f"la adyacencia debe ser cuadrada, recibida forma {matrix.shape}"
        )
    if not np.allclose(matrix, matrix.T, atol=_SYMMETRY_ATOL, rtol=0.0):
        raise InvalidAdjacencyError(
            "la adyacencia debe ser simétrica: el grafo es no dirigido y todo el "
            "aparato espectral supone autovalores reales"
        )
    if (matrix < 0).any():
        raise InvalidAdjacencyError("la adyacencia no admite pesos negativos")
    if (np.diag(matrix) != 0).any():
        raise InvalidAdjacencyError(
            "la adyacencia debe tener diagonal nula: un lazo no tiene lectura en "
            "términos de vecindad y desplaza el espectro"
        )
    return matrix


def degree_vector(adjacency: npt.ArrayLike) -> npt.NDArray[np.float64]:
    """Grados ponderados de cada nodo.

    Args:
        adjacency: Matriz de adyacencia `(n, n)`.

    Returns:
        Vector `(n,)` con la suma de pesos incidentes en cada nodo.
    """
    matrix = _validate_adjacency(adjacency)
    return np.asarray(matrix.sum(axis=1), dtype=np.float64)


def laplacian(adjacency: npt.ArrayLike) -> npt.NDArray[np.float64]:
    """Laplaciano combinatorio `L = D - A`.

    Admite nodos de grado cero: su fila y columna quedan nulas, que es la
    lectura correcta de un nodo aislado.

    Args:
        adjacency: Matriz de adyacencia `(n, n)`.

    Returns:
        Matriz `(n, n)` simétrica y de suma-fila cero.
    """
    matrix = _validate_adjacency(adjacency)
    return np.diag(matrix.sum(axis=1)) - matrix


def normalized_laplacian(adjacency: npt.ArrayLike) -> npt.NDArray[np.float64]:
    """Laplaciano normalizado simétrico `L_norm = D^(-1/2) · L · D^(-1/2)`.

    Equivale a `I - D^(-1/2) · A · D^(-1/2)`. Su espectro vive en `[0, 2]`,
    lo que hace comparables grafos de distinto tamaño y densidad: es la
    razón por la que E6 lo prefirió al combinatorio.

    Args:
        adjacency: Matriz de adyacencia `(n, n)` sin nodos aislados.

    Returns:
        Matriz `(n, n)` simétrica con espectro en `[0, 2]`.

    Raises:
        ZeroDegreeNodeError: Si algún nodo tiene grado cero.
    """
    matrix = _validate_adjacency(adjacency)
    degrees = matrix.sum(axis=1)

    aislados = np.flatnonzero(degrees <= 0.0)
    if aislados.size > 0:
        raise ZeroDegreeNodeError(tuple(int(i) for i in aislados))

    inv_sqrt = np.diag(1.0 / np.sqrt(degrees))
    combinatorio = np.diag(degrees) - matrix
    l_norm = inv_sqrt @ combinatorio @ inv_sqrt
    # eigh sólo lee un triángulo; simetrizar elimina la asimetría de
    # redondeo que deja el doble producto matricial.
    return (l_norm + l_norm.T) / 2.0


def _apply_sign_convention(
    eigenvectors: npt.NDArray[np.float64],
) -> npt.NDArray[np.float64]:
    """Fija el signo de cada autovector de forma determinista.

    El signo de un autovector es arbitrario: `u` y `-u` son igual de
    válidos y `eigh` puede devolver cualquiera de los dos. La convención
    acá es que la componente de mayor magnitud sea positiva, con desempate
    por el índice más bajo. Esto no resuelve la arbitrariedad de la base
    dentro de un subespacio degenerado, que es un problema distinto.

    Args:
        eigenvectors: Matriz `(n, n)` con un autovector por columna.

    Returns:
        La misma base con los signos fijados.
    """
    dominantes = np.argmax(np.abs(eigenvectors), axis=0)
    signos = np.sign(eigenvectors[dominantes, np.arange(eigenvectors.shape[1])])
    signos[signos == 0] = 1.0
    return np.asarray(eigenvectors * signos, dtype=np.float64)


def graph_fourier_basis(
    laplacian_matrix: npt.ArrayLike,
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """Diagonaliza un Laplaciano y devuelve su base de Fourier.

    Usa `numpy.linalg.eigh`, que explota la simetría: es más estable que
    `eig` y devuelve autovalores reales en orden ascendente.

    Args:
        laplacian_matrix: Laplaciano `(n, n)`, simétrico.

    Returns:
        Par `(eigenvalues, eigenvectors)`. Los autovalores vienen en orden
        ascendente y son las "frecuencias" del grafo; la columna `k` de
        `eigenvectors` es el modo asociado a `eigenvalues[k]`, con el signo
        fijado por convención.

    Raises:
        InvalidAdjacencyError: Si la matriz no es cuadrada o no es simétrica.
    """
    matrix = np.asarray(laplacian_matrix, dtype=np.float64)
    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1]:
        raise InvalidAdjacencyError(
            f"el Laplaciano debe ser cuadrado, recibida forma {matrix.shape}"
        )
    if not np.allclose(matrix, matrix.T, atol=_SYMMETRY_ATOL, rtol=0.0):
        raise InvalidAdjacencyError("el Laplaciano debe ser simétrico")

    eigenvalues, eigenvectors = np.linalg.eigh(matrix)
    return eigenvalues, _apply_sign_convention(eigenvectors)


def gft(
    signal: npt.ArrayLike,
    eigenvectors: npt.NDArray[np.float64],
) -> npt.NDArray[np.float64]:
    """Transformada de Fourier sobre el grafo: `x_hat = Uᵀ · x`.

    Args:
        signal: Señal `(n,)` definida sobre los nodos.
        eigenvectors: Base de Fourier `(n, n)`.

    Returns:
        Coeficientes espectrales `(n,)`. El coeficiente `k` es la energía
        de la señal en el modo `k`.

    Raises:
        ValueError: Si las dimensiones no encajan.
    """
    x = np.asarray(signal, dtype=np.float64)
    if x.ndim != 1 or x.shape[0] != eigenvectors.shape[0]:
        raise ValueError(
            f"la señal debe ser un vector de {eigenvectors.shape[0]} componentes, "
            f"recibida forma {x.shape}"
        )
    return np.asarray(eigenvectors.T @ x, dtype=np.float64)


def igft(
    spectrum: npt.ArrayLike,
    eigenvectors: npt.NDArray[np.float64],
) -> npt.NDArray[np.float64]:
    """Transformada inversa: `x = U · x_hat`.

    Args:
        spectrum: Coeficientes espectrales `(n,)`.
        eigenvectors: La misma base usada en `gft`.

    Returns:
        Señal `(n,)` reconstruida sobre los nodos.

    Raises:
        ValueError: Si las dimensiones no encajan.
    """
    x_hat = np.asarray(spectrum, dtype=np.float64)
    if x_hat.ndim != 1 or x_hat.shape[0] != eigenvectors.shape[1]:
        raise ValueError(
            f"el espectro debe ser un vector de {eigenvectors.shape[1]} componentes, "
            f"recibida forma {x_hat.shape}"
        )
    return np.asarray(eigenvectors @ x_hat, dtype=np.float64)


def zero_multiplicity(
    eigenvalues: npt.ArrayLike,
    tolerance: float | None = None,
) -> int:
    """Cuántos autovalores son nulos, y por lo tanto cuántas componentes hay.

    Args:
        eigenvalues: Autovalores del Laplaciano.
        tolerance: Umbral de cero. Si es `None` se deriva de
            `eigenvalue_zero_tolerance`.

    Returns:
        Multiplicidad del autovalor cero.
    """
    values = np.asarray(eigenvalues, dtype=np.float64)
    tol = (
        eigenvalue_zero_tolerance(values.size, float(np.abs(values).max()))
        if tolerance is None
        else tolerance
    )
    return int((np.abs(values) <= tol).sum())


def fiedler_value(
    eigenvalues: npt.ArrayLike,
    tolerance: float | None = None,
) -> float:
    """Menor autovalor no nulo, medida de cuán lejos está el grafo de partirse.

    Args:
        eigenvalues: Autovalores en orden ascendente.
        tolerance: Umbral de cero. Si es `None` se deriva de
            `eigenvalue_zero_tolerance`.

    Returns:
        El primer autovalor por encima de la tolerancia, o `0.0` si todos
        son nulos (un grafo sin aristas).
    """
    values = np.asarray(eigenvalues, dtype=np.float64)
    tol = (
        eigenvalue_zero_tolerance(values.size, float(np.abs(values).max()))
        if tolerance is None
        else tolerance
    )
    no_nulos = values[values > tol]
    return float(no_nulos[0]) if no_nulos.size > 0 else 0.0


def degenerate_groups(
    eigenvalues: npt.ArrayLike,
    tolerance: float | None = None,
) -> tuple[tuple[int, ...], ...]:
    """Agrupa los índices de autovalores repetidos: los subespacios propios.

    Dentro de cada grupo con más de un elemento la base que devuelve `eigh`
    es arbitraria. Quien necesite resultados reproducibles debe trabajar
    con el subespacio entero (proyector, energía agregada) y no con sus
    autovectores por separado.

    Args:
        eigenvalues: Autovalores en orden ascendente.
        tolerance: Umbral para considerar dos autovalores iguales. Si es
            `None` se deriva de `eigenvalue_zero_tolerance`.

    Returns:
        Tupla de grupos de índices consecutivos. Los grupos de un solo
        elemento también aparecen, de modo que la concatenación cubre todos
        los índices.
    """
    values = np.asarray(eigenvalues, dtype=np.float64)
    if values.size == 0:
        return ()
    tol = (
        eigenvalue_zero_tolerance(values.size, float(np.abs(values).max()))
        if tolerance is None
        else tolerance
    )

    grupos: list[tuple[int, ...]] = []
    inicio = 0
    for i in range(1, values.size):
        if values[i] - values[inicio] > tol:
            grupos.append(tuple(range(inicio, i)))
            inicio = i
    grupos.append(tuple(range(inicio, values.size)))
    return tuple(grupos)


def connected_components(
    adjacency: npt.ArrayLike,
) -> tuple[int, npt.NDArray[np.int64]]:
    """Componentes conexas por recorrido en anchura, sin tocar el espectro.

    Independiente del aparato espectral a propósito: sirve de contraste
    para verificar que la multiplicidad del autovalor cero coincide con el
    número de componentes, que es la propiedad que sostiene la lectura de
    los seis subgrafos zonales.

    Args:
        adjacency: Matriz de adyacencia `(n, n)`.

    Returns:
        Par `(n_componentes, etiquetas)`, con una etiqueta por nodo.
    """
    matrix = _validate_adjacency(adjacency)
    n = matrix.shape[0]
    etiquetas = np.full(n, -1, dtype=np.int64)
    componente = 0

    for raiz in range(n):
        if etiquetas[raiz] != -1:
            continue
        etiquetas[raiz] = componente
        cola = deque([raiz])
        while cola:
            nodo = cola.popleft()
            for vecino in np.flatnonzero(matrix[nodo] > 0):
                if etiquetas[vecino] == -1:
                    etiquetas[vecino] = componente
                    cola.append(int(vecino))
        componente += 1

    return componente, etiquetas
