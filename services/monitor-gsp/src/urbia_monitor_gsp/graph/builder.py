"""Constructor del grafo AMI: de medidores a subgrafos zonales con espectro.

Acá entra el dominio. `geo` proyecta coordenadas y `spectral` diagonaliza
matrices; ninguno de los dos sabe qué es un medidor. Este módulo es el que
sí lo sabe: agrupa por zona, fija el orden canónico de los nodos, tiende
las aristas según la configuración y devuelve un `AmiGraph` con todo ya
calculado.

No lee de ninguna parte. Recibe `MeterNode` y devuelve `AmiGraph`: de
dónde salieron los medidores —PostgreSQL, un JSON de topología, una celda
de notebook— es problema de quien llama. Eso es lo que permite construir
el mismo grafo en un nodo de borde sin base de datos.

**Reproducibilidad.** Dos construcciones con los mismos medidores y la
misma configuración dan matrices idénticas bit a bit. Eso descansa en tres
decisiones, no en la suerte:

* Los nodos se ordenan por `device_id`. El orden de llegada de los
  medidores no influye en nada.
* Las zonas se ordenan alfabéticamente en `zone_order`.
* El k-NN desempata distancias iguales por índice, con ordenamiento
  estable. Dos medidores exactamente equidistantes de un tercero eligen
  siempre al mismo.

Lo que **no** queda fijado por esto es la base de Fourier dentro de un
subespacio propio degenerado; ver el docstring de `spectral`. Con el orden
canónico fijo la base es reproducible entre corridas, pero sigue siendo
arbitraria como base del subespacio.

**Construcción por defecto.** k-NN con k=4 simetrizado por unión, pesos
binarios, un marco de proyección local por zona y sin puente inter-zona.
El barrido de k que justifica ese k=4 está en el docstring de
`GraphConfig`, con la construcción exacta con que se midió.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Final

import numpy as np
import numpy.typing as npt

from . import spectral
from .geo import pairwise_distances_m, project_to_local_meters
from .types import (
    MIN_METERS_PER_ZONE,
    AmiGraph,
    BuildStats,
    GraphConfig,
    InsufficientMetersError,
    InvalidGraphConfigError,
    KnnMode,
    MeterNode,
    ZeroDegreeNodeError,
    ZoneGraph,
)

_NO_K: Final = 0
"""Valor de `k_effective` bajo `strategy="radius"`, donde no hay k."""


def _frozen(array: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    """Devuelve el array marcado como de solo lectura.

    Las matrices de un `ZoneGraph` describen una construcción ya hecha:
    mutarlas dejaría el espectro guardado describiendo otro grafo.

    Args:
        array: Array a congelar.

    Returns:
        El mismo array, sin permiso de escritura.
    """
    array.flags.writeable = False
    return array


def _knn_mask(
    distances: npt.NDArray[np.float64],
    k: int,
    mode: KnnMode,
) -> npt.NDArray[np.bool_]:
    """Selecciona los k vecinos más cercanos de cada nodo y simetriza.

    Args:
        distances: Matriz `(n, n)` de distancias en metros.
        k: Vecinos por nodo. Se supone ya acotado a `n - 1`.
        mode: `"union"` (basta que uno elija al otro) o `"mutual"` (hace
            falta que se elijan los dos).

    Returns:
        Máscara booleana `(n, n)` simétrica y con diagonal falsa.
    """
    n = distances.shape[0]
    # La diagonal a infinito saca al propio nodo de su vecindario sin
    # suponer que la distancia mínima es la de sí mismo: dos medidores en
    # la misma coordenada están a distancia cero y romperían ese supuesto.
    sin_diagonal = distances.copy()
    np.fill_diagonal(sin_diagonal, np.inf)

    # `stable` desempata por índice, y como los nodos vienen ordenados por
    # device_id, el desempate es reproducible entre corridas y máquinas.
    elegidos = np.zeros((n, n), dtype=bool)
    orden = np.argsort(sin_diagonal, axis=1, kind="stable")[:, :k]
    np.put_along_axis(elegidos, orden, True, axis=1)

    return elegidos | elegidos.T if mode == "union" else elegidos & elegidos.T


def _radius_mask(
    distances: npt.NDArray[np.float64],
    radius_m: float,
) -> npt.NDArray[np.bool_]:
    """Conecta todo par de nodos a no más de `radius_m` metros.

    Args:
        distances: Matriz `(n, n)` de distancias en metros.
        radius_m: Radio de vecindad, en metros.

    Returns:
        Máscara booleana `(n, n)` simétrica y con diagonal falsa.
    """
    mask = distances <= radius_m
    np.fill_diagonal(mask, False)
    return mask


def _weights(
    mask: npt.NDArray[np.bool_],
    distances: npt.NDArray[np.float64],
    config: GraphConfig,
) -> npt.NDArray[np.float64]:
    """Pondera las aristas seleccionadas.

    Args:
        mask: Máscara de aristas.
        distances: Matriz `(n, n)` de distancias en metros.
        config: Configuración; define `weighting` y `sigma_m`.

    Returns:
        Matriz de adyacencia `(n, n)` simétrica, con diagonal nula.

    Raises:
        InvalidGraphConfigError: Si hace falta derivar `sigma_m` y no hay
            ninguna arista de la cual derivarlo.
    """
    if config.weighting == "binary":
        return mask.astype(np.float64)

    sigma = config.sigma_m if config.sigma_m is not None else _median_edge_length(mask, distances)
    pesos = np.zeros_like(distances)
    pesos[mask] = np.exp(-(distances[mask] ** 2) / (2.0 * sigma**2))
    return pesos


def _median_edge_length(
    mask: npt.NDArray[np.bool_],
    distances: npt.NDArray[np.float64],
) -> float:
    """Mediana de las longitudes de arista, escala por defecto del peso gaussiano.

    Derivarla de la propia vecindad hace que el peso se adapte a la
    densidad de la zona, que es la razón de haber elegido k-NN: una sigma
    fija en metros volvería a introducir la escala única que el radio fijo
    imponía.

    Args:
        mask: Máscara de aristas.
        distances: Matriz `(n, n)` de distancias en metros.

    Returns:
        Mediana de las distancias de las aristas presentes.

    Raises:
        InvalidGraphConfigError: Si no hay ninguna arista.
    """
    longitudes = distances[np.triu(mask, k=1)]
    if longitudes.size == 0:
        raise InvalidGraphConfigError(
            "no se puede derivar sigma_m de un grafo sin aristas: pasá sigma_m "
            "explícito o ampliá el criterio de vecindad"
        )
    return float(np.median(longitudes))


def _adjacency(
    distances: npt.NDArray[np.float64],
    config: GraphConfig,
) -> tuple[npt.NDArray[np.float64], int]:
    """Arma la adyacencia de una zona según la estrategia configurada.

    Args:
        distances: Matriz `(n, n)` de distancias en metros.
        config: Configuración de construcción.

    Returns:
        Par `(adyacencia, k_effective)`. `k_effective` vale 0 bajo
        `strategy="radius"`.
    """
    if config.strategy == "knn":
        # Una zona de n medidores no puede dar más de n-1 vecinos a nadie.
        k_effective = min(config.k, distances.shape[0] - 1)
        mask = _knn_mask(distances, k_effective, config.knn_mode)
    elif config.radius_m is None:  # pragma: no cover — GraphConfig ya lo impide
        raise InvalidGraphConfigError("strategy='radius' requiere radius_m explícito")
    else:
        k_effective = _NO_K
        mask = _radius_mask(distances, config.radius_m)

    return _weights(mask, distances, config), k_effective


def _build_stats(
    adjacency: npt.NDArray[np.float64],
    distances: npt.NDArray[np.float64],
    eigenvalues: npt.NDArray[np.float64],
    k_effective: int,
) -> BuildStats:
    """Calcula el diagnóstico de un subgrafo ya construido.

    Args:
        adjacency: Matriz de adyacencia.
        distances: Matriz de distancias en metros.
        eigenvalues: Autovalores de `L_norm`, en orden ascendente.
        k_effective: k realmente aplicado.

    Returns:
        El diagnóstico completo de la construcción.
    """
    aristas = np.triu(adjacency, k=1) > 0
    grados = adjacency.sum(axis=1)
    n_componentes, _ = spectral.connected_components(adjacency)
    largos = distances[aristas]

    return BuildStats(
        n_meters=adjacency.shape[0],
        n_edges=int(aristas.sum()),
        k_effective=k_effective,
        degree_min=float(grados.min()),
        degree_max=float(grados.max()),
        degree_mean=float(grados.mean()),
        n_components=n_componentes,
        lambda_1=spectral.fiedler_value(eigenvalues),
        max_edge_length_m=float(largos.max()) if largos.size > 0 else 0.0,
    )


def build_zone_graph(
    meters: Sequence[MeterNode],
    config: GraphConfig | None = None,
) -> ZoneGraph:
    """Construye el subgrafo de una zona, con su Laplaciano y su espectro.

    Todos los medidores deben pertenecer a la misma zona. El orden en que
    lleguen no importa: se reordenan por `device_id` antes de cualquier
    cálculo, y ese orden es el que indexa filas y columnas de todas las
    matrices del resultado.

    Args:
        meters: Medidores de una única zona. Al menos
            `MIN_METERS_PER_ZONE`.
        config: Configuración de construcción. Si es `None` se usan los
            valores por defecto de `GraphConfig`.

    Returns:
        El subgrafo con coordenadas proyectadas, distancias, adyacencia,
        ambos Laplacianos, la base de Fourier y el diagnóstico.

    Raises:
        InvalidGraphConfigError: Si `meters` está vacío, si mezcla zonas o
            si el puente inter-zona está activo (no implementado).
        InsufficientMetersError: Si la zona no llega a
            `MIN_METERS_PER_ZONE`.
        ZeroDegreeNodeError: Si la construcción deja medidores aislados,
            cosa que `strategy="radius"` sí puede hacer.
    """
    config = config or GraphConfig()
    if config.inter_zone_bridge:
        raise InvalidGraphConfigError(
            "inter_zone_bridge no está implementado: 'zone_centroid_ring' no tiene "
            "todavía una definición acordada y una arista de puente inventada "
            "cambiaría el espectro de las seis zonas"
        )
    if not meters:
        raise InvalidGraphConfigError("no se puede construir un subgrafo sin medidores")

    zonas = {m.zona for m in meters}
    if len(zonas) > 1:
        raise InvalidGraphConfigError(
            f"build_zone_graph espera una sola zona, recibidas {sorted(zonas)}: "
            f"usá build_ami_graph para un conjunto multizona"
        )

    zona = meters[0].zona
    if len(meters) < MIN_METERS_PER_ZONE:
        raise InsufficientMetersError(zona, len(meters))

    ordenados = sorted(meters, key=lambda m: m.device_id)
    device_ids = tuple(m.device_id for m in ordenados)
    coords_m, frame = project_to_local_meters(
        [m.lat for m in ordenados], [m.lon for m in ordenados]
    )
    distances_m = pairwise_distances_m(coords_m)

    adjacency, k_effective = _adjacency(distances_m, config)
    aislados = np.flatnonzero(adjacency.sum(axis=1) <= 0.0)
    if aislados.size > 0:
        raise ZeroDegreeNodeError(
            tuple(int(i) for i in aislados),
            zona=zona,
            device_ids=tuple(device_ids[i] for i in aislados),
        )

    laplacian_norm = spectral.normalized_laplacian(adjacency)
    eigenvalues, eigenvectors = spectral.graph_fourier_basis(laplacian_norm)

    return ZoneGraph(
        zona=zona,
        device_ids=device_ids,
        coords_m=coords_m,
        frame=frame,
        distances_m=_frozen(distances_m),
        adjacency=_frozen(adjacency),
        degrees=_frozen(spectral.degree_vector(adjacency)),
        laplacian=_frozen(spectral.laplacian(adjacency)),
        laplacian_norm=_frozen(laplacian_norm),
        eigenvalues=_frozen(eigenvalues),
        eigenvectors=_frozen(eigenvectors),
        stats=_build_stats(adjacency, distances_m, eigenvalues, k_effective),
    )


def build_ami_graph(
    meters: Sequence[MeterNode],
    config: GraphConfig | None = None,
) -> AmiGraph:
    """Construye el grafo AMI completo: un subgrafo independiente por zona.

    Sin puente inter-zona los subgrafos no se tocan, y el grafo global es
    bloque-diagonal. Esa independencia no es un detalle de implementación:
    es la que permite que cada zona se analice en su propio nodo de borde
    sin conocer a las demás.

    Args:
        meters: Medidores de todas las zonas. Se agrupan por `zona`.
        config: Configuración de construcción, común a todas las zonas. Si
            es `None` se usan los valores por defecto de `GraphConfig`.

    Returns:
        El grafo AMI con un `ZoneGraph` por zona y las zonas en orden
        alfabético.

    Raises:
        InvalidGraphConfigError: Si `meters` está vacío o si el puente
            inter-zona está activo (no implementado).
        InsufficientMetersError: Si alguna zona no llega a
            `MIN_METERS_PER_ZONE`.
        ZeroDegreeNodeError: Si alguna zona queda con medidores aislados.
    """
    config = config or GraphConfig()
    if not meters:
        raise InvalidGraphConfigError("no se puede construir un grafo AMI sin medidores")

    por_zona: dict[str, list[MeterNode]] = defaultdict(list)
    for meter in meters:
        por_zona[meter.zona].append(meter)

    zone_order = tuple(sorted(por_zona))
    return AmiGraph(
        zones={zona: build_zone_graph(por_zona[zona], config) for zona in zone_order},
        config=config,
        built_at=datetime.now(UTC),
        zone_order=zone_order,
    )
