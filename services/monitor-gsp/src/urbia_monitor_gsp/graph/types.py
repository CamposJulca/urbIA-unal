"""Tipos, configuración y errores del constructor del grafo AMI.

Estas estructuras son el contrato entre quien aporta los medidores (una
consulta a PostgreSQL, un JSON de topología, una celda de notebook) y el
aparato espectral. Ninguna de ellas sabe de dónde salieron los datos.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Final, Literal

import numpy as np
import numpy.typing as npt

from .geo import LocalFrame

MIN_METERS_PER_ZONE: Final = 2
"""Mínimo de medidores para que una zona admita un grafo.

Con un solo medidor el grado es cero, el Laplaciano normalizado exige
dividir por la raíz del grado y el espectro resultante no significa nada.
El constructor levanta `InsufficientMetersError` en vez de devolver una
zona degenerada: si un filtro deja una zona con un nodo, eso es un
problema de los datos y debe verse, no propagarse en silencio.
"""

Strategy = Literal["knn", "radius"]
KnnMode = Literal["union", "mutual"]
Weighting = Literal["binary", "gaussian"]
BridgePolicy = Literal["zone_centroid_ring"]


class MonitorGspError(Exception):
    """Error base del monitor GSP."""


class InvalidCoordinateError(MonitorGspError, ValueError):
    """Una coordenada cae fuera del rango geográfico válido."""


class InvalidGraphConfigError(MonitorGspError, ValueError):
    """La configuración del grafo es inconsistente o incompleta."""


class InvalidAdjacencyError(MonitorGspError, ValueError):
    """La matriz de adyacencia no cumple las condiciones del aparato espectral."""


class ZeroDegreeNodeError(MonitorGspError, ValueError):
    """Hay nodos de grado cero y el Laplaciano normalizado no está definido.

    `L_norm = D^(-1/2) · L · D^(-1/2)` exige dividir por la raíz del grado.
    Un nodo aislado haría aparecer un infinito que se propaga como NaN por
    todo el espectro sin que nada avise.
    """

    def __init__(
        self,
        indices: tuple[int, ...],
        zona: str | None = None,
        device_ids: tuple[str, ...] | None = None,
    ) -> None:
        """Inicializa el error con los nodos culpables.

        Args:
            indices: Posiciones de los nodos con grado cero.
            zona: Zona donde aparecieron, si se conoce. El aparato
                espectral no la conoce; el constructor sí.
            device_ids: Identificadores de los medidores aislados, si se
                conocen. Un índice de fila no alcanza para ir a mirar el
                dato: el `device_id` sí.
        """
        self.indices = indices
        self.zona = zona
        self.device_ids = device_ids

        donde = f"la zona '{zona}'" if zona is not None else "el grafo"
        quienes = (
            f" ({', '.join(device_ids)})" if device_ids else f" en las posiciones {list(indices)}"
        )
        super().__init__(
            f"nodos de grado cero en {donde}{quienes}: el Laplaciano normalizado exige "
            f"dividir por la raíz del grado. Subí k, ampliá radius_m, filtrá los nodos "
            f"aislados, o usá el Laplaciano combinatorio, que sí los admite"
        )


class InsufficientMetersError(MonitorGspError, ValueError):
    """Una zona no tiene medidores suficientes para construir un grafo."""

    def __init__(self, zona: str, n_meters: int) -> None:
        """Inicializa el error con la zona culpable y su conteo.

        Args:
            zona: Nombre de la zona afectada.
            n_meters: Cantidad de medidores encontrados en esa zona.
        """
        self.zona = zona
        self.n_meters = n_meters
        super().__init__(
            f"la zona '{zona}' tiene {n_meters} medidor(es) y se requieren al menos "
            f"{MIN_METERS_PER_ZONE}: un grafo de un solo nodo no admite Laplaciano "
            f"normalizado ni espectro interpretable"
        )


@dataclass(frozen=True, slots=True)
class MeterNode:
    """Un medidor AMI como nodo del grafo: identidad, zona y posición.

    Deliberadamente plano y sin dependencias: es lo mínimo que el núcleo
    necesita, y cualquier fuente de datos puede producirlo.

    Attributes:
        device_id: Identificador único del medidor (`urbia-<zona>-<tipo>-NNNN`).
        zona: Zona a la que pertenece. Define en qué subgrafo entra.
        lat: Latitud en grados decimales (WGS84).
        lon: Longitud en grados decimales (WGS84).
    """

    device_id: str
    zona: str
    lat: float
    lon: float

    def __post_init__(self) -> None:
        """Valida identidad y rango de las coordenadas.

        Raises:
            InvalidCoordinateError: Si `lat` o `lon` caen fuera de rango, o
                si `device_id` o `zona` están vacíos.
        """
        if not self.device_id:
            raise InvalidCoordinateError("device_id no puede estar vacío")
        if not self.zona:
            raise InvalidCoordinateError(f"zona vacía en el medidor '{self.device_id}'")
        if not -90.0 <= self.lat <= 90.0:
            raise InvalidCoordinateError(
                f"latitud fuera de rango en '{self.device_id}': {self.lat}"
            )
        if not -180.0 <= self.lon <= 180.0:
            raise InvalidCoordinateError(
                f"longitud fuera de rango en '{self.device_id}': {self.lon}"
            )


@dataclass(frozen=True, slots=True)
class GraphConfig:
    """Parámetros de construcción del grafo.

    Los valores por defecto son k-NN simetrizado con k=4, pesos binarios y
    seis subgrafos independientes sin puente inter-zona.

    **Construcción de referencia de las cifras de este docstring.** Todos
    los números medidos que aparecen abajo salen de la misma construcción,
    y sin ella no son verificables: los 150 medidores activos de
    `ami_meters`, agrupados por zona; un marco de proyección local por
    zona (`geo.local_frame` sobre los medidores de esa zona); k-NN sobre
    distancias euclídeas en metros, **simetrizado por unión**; pesos
    binarios; y `L_norm` diagonalizado con `spectral.graph_fourier_basis`.
    El marco por zona y el marco global dan resultados idénticos a esta
    escala, así que la elección no afecta las cifras.

    Barrido de k bajo esa construcción, Fiedler de `L_norm` por zona:

        k=1    las seis zonas fragmentadas (6 a 9 componentes)
        k=2    cinco zonas fragmentadas; sólo chipre conecta (0,0155)
        k=3    la_enea se parte en 2 componentes; las otras cinco conectan,
               con Fiedler mínimo 0,0219 en universitario
        k=4    las seis conectadas, Fiedler mínimo 0,0505 en chipre
        k=5    las seis conectadas, Fiedler mínimo 0,0725 en centro

    De ahí el valor por defecto: **k=4 es el mínimo que conecta las seis
    zonas**, y además duplica el Fiedler de la peor zona respecto de k=3.
    Subir a k=5 sigue mejorando la conectividad, pero cada vecino extra
    agrega aristas que ya no corresponden a proximidad física real.

    Attributes:
        strategy: Criterio de vecindad. `"knn"` se adapta a la densidad
            local; `"radius"` existe para reproducir la comparación.
        k: Vecinos por nodo bajo `"knn"`. k=4 por defecto, por el barrido
            de arriba: es el mínimo que deja las seis zonas conexas.
        radius_m: Radio de vecindad en metros bajo `"radius"`. Obligatorio
            con esa estrategia.
        knn_mode: `"union"` conecta si cualquiera de los dos elige al otro;
            `"mutual"` exige reciprocidad. La reciprocidad fragmenta: con
            k=4 sobre las seis zonas, `"mutual"` deja conexa sólo a
            palogrande (Fiedler 0,0270) y parte las otras cinco en 2 a 5
            componentes. Por eso el defecto es `"union"`.
        weighting: `"binary"` (0/1, lo validado en E6) o `"gaussian"`
            (`exp(-d²/2σ²)`).
        sigma_m: Escala del peso gaussiano. Si es `None` se deriva de la
            mediana de las distancias de vecindad.
        inter_zone_bridge: Si es `True`, une las zonas entre sí. Apagado
            por defecto: una arista de puente no corresponde a ninguna
            realidad física y los seis subgrafos coinciden con la
            partición prevista para distribuir el monitor. Se enciende
            sólo para comparar construcciones.
        bridge_policy: Cómo tender el puente cuando está activo.
    """

    strategy: Strategy = "knn"
    k: int = 4
    radius_m: float | None = None
    knn_mode: KnnMode = "union"
    weighting: Weighting = "binary"
    sigma_m: float | None = None
    inter_zone_bridge: bool = False
    bridge_policy: BridgePolicy = "zone_centroid_ring"

    def __post_init__(self) -> None:
        """Valida la coherencia interna de la configuración.

        Raises:
            InvalidGraphConfigError: Si falta un parámetro que la
                estrategia elegida necesita, o si alguno es no positivo.
        """
        if self.strategy == "knn":
            if self.k < 1:
                raise InvalidGraphConfigError(f"k debe ser >= 1, recibido {self.k}")
        elif self.radius_m is None:
            raise InvalidGraphConfigError(
                "strategy='radius' requiere radius_m explícito: no hay un radio "
                "por defecto razonable porque la densidad varía entre zonas"
            )
        elif self.radius_m <= 0:
            raise InvalidGraphConfigError(f"radius_m debe ser > 0, recibido {self.radius_m}")

        if self.sigma_m is not None and self.sigma_m <= 0:
            raise InvalidGraphConfigError(f"sigma_m debe ser > 0, recibido {self.sigma_m}")
        if self.weighting == "binary" and self.sigma_m is not None:
            raise InvalidGraphConfigError(
                "sigma_m sólo aplica a weighting='gaussian'; con pesos binarios "
                "no tiene efecto y declararlo esconde un malentendido"
            )


@dataclass(frozen=True, slots=True)
class BuildStats:
    """Diagnóstico de un subgrafo ya construido.

    Todo esto se deriva de la matriz de adyacencia, pero calcularlo una vez
    y dejarlo a la vista evita que cada consumidor lo recalcule y hace
    auditable la construcción.

    Attributes:
        n_meters: Nodos del subgrafo.
        n_edges: Aristas no dirigidas.
        k_effective: k realmente aplicado bajo `strategy="knn"`. Puede ser
            menor que el pedido si la zona tiene menos de k+1 medidores.
            Vale 0 bajo `strategy="radius"`, donde no hay k.
        degree_min: Grado mínimo. Con k-NN simetrizado nunca baja de
            `k_effective`, que es lo que evita los nodos hoja que E6
            identificó como punto ciego del detector.
        degree_max: Grado máximo.
        degree_mean: Grado medio.
        n_components: Componentes conexas. Debe ser 1 en un subgrafo zonal
            bien formado.
        lambda_1: Segundo autovalor de `L_norm` (Fiedler). Mide cuán lejos
            está el subgrafo de partirse en dos.
        max_edge_length_m: Arista más larga, en metros.
    """

    n_meters: int
    n_edges: int
    k_effective: int
    degree_min: float
    degree_max: float
    degree_mean: float
    n_components: int
    lambda_1: float
    max_edge_length_m: float


@dataclass(frozen=True, slots=True, eq=False)
class ZoneGraph:
    """Grafo de una zona con su Laplaciano y descomposición espectral.

    Es la unidad que un nodo de borde puede construir y analizar por sí
    solo, sin conocer las demás zonas.

    Las coordenadas proyectadas se calculan **una sola vez**, al construir,
    y quedan en `coords_m` como array de solo lectura junto al `frame` que
    las produjo. Nada las recalcula después.

    Attributes:
        zona: Nombre de la zona.
        device_ids: Identificadores en el orden canónico del grafo. Este
            orden indexa filas y columnas de todas las matrices.
        coords_m: Array `(n, 2)` con las posiciones proyectadas en metros.
        frame: Marco de proyección usado para obtener `coords_m`.
        distances_m: Matriz `(n, n)` de distancias entre medidores.
        adjacency: Matriz `(n, n)` de adyacencia, simétrica y con diagonal
            nula. Binaria o con pesos gaussianos según la configuración.
        degrees: Vector `(n,)` de grados ponderados.
        laplacian: Laplaciano combinatorio `L = D - A`.
        laplacian_norm: Laplaciano normalizado simétrico
            `L_norm = D^(-1/2) · L · D^(-1/2)`, con espectro en `[0, 2]`.
        eigenvalues: Autovalores de `L_norm` en orden ascendente.
        eigenvectors: Base de Fourier del grafo. La columna `k` es el modo
            asociado a `eigenvalues[k]`.
        stats: Diagnóstico de la construcción.
    """

    zona: str
    device_ids: tuple[str, ...]
    coords_m: npt.NDArray[np.float64]
    frame: LocalFrame
    distances_m: npt.NDArray[np.float64]
    adjacency: npt.NDArray[np.float64]
    degrees: npt.NDArray[np.float64]
    laplacian: npt.NDArray[np.float64]
    laplacian_norm: npt.NDArray[np.float64]
    eigenvalues: npt.NDArray[np.float64]
    eigenvectors: npt.NDArray[np.float64]
    stats: BuildStats

    @property
    def n_meters(self) -> int:
        """Cantidad de medidores del subgrafo."""
        return len(self.device_ids)


@dataclass(frozen=True, slots=True, eq=False)
class AmiGraph:
    """Grafo AMI completo: una zona, un subgrafo.

    Sin puente inter-zona (el caso por defecto) los subgrafos son
    independientes y el grafo global es bloque-diagonal: la multiplicidad
    del autovalor cero equivale al número de zonas.

    Attributes:
        zones: Subgrafos indexados por nombre de zona.
        config: Configuración con la que se construyó.
        built_at: Momento de construcción, en UTC.
        zone_order: Orden canónico de las zonas, el mismo que usan los
            bloques del grafo global.
    """

    zones: dict[str, ZoneGraph]
    config: GraphConfig
    built_at: datetime
    zone_order: tuple[str, ...] = field(default_factory=tuple)

    @property
    def n_meters(self) -> int:
        """Total de medidores en todas las zonas."""
        return sum(zone.n_meters for zone in self.zones.values())

    @property
    def n_zones(self) -> int:
        """Cantidad de zonas."""
        return len(self.zones)
