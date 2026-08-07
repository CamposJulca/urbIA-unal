"""Proyección de coordenadas geográficas a un plano local en metros.

Todo el tratamiento de coordenadas del monitor pasa por este módulo. El
resto del paquete trabaja exclusivamente con metros: si algún día hace
falta una proyección más precisa (UTM, geodésica exacta, marco local
definido por catastro), se cambia acá y nada más se entera.

Proyección elegida: equirectangular local con los radios de curvatura del
elipsoide WGS84 evaluados en la latitud de referencia.

    dx = N(lat0) · cos(lat0) · (lon - lon0)
    dy = M(lat0) · (lat - lat0)

donde `N` es el radio de curvatura normal (este-oeste) y `M` el meridional
(norte-sur), ambos en radianes de entrada.

Por qué ésta y no una esfera de radio medio: sobre los 1825 pares
intra-zona de los 150 medidores reales de Manizales, medido contra
distancia geodésica de Vincenty sobre WGS84,

    plana esférica R = 6.371 km   error medio 1,349 m   máximo 5,442 m
    plana elipsoidal (M, N)       error medio 0,001 m   máximo 0,006 m

El error de la esfera es sistemático, no ruido: a 5,06° de latitud el
radio medio se desvía +0,553 % del radio meridional, y estira todas las
distancias norte-sur. A escala de vecindad (aristas de 100 a 500 m) eso
son metros, y llega a cambiar qué medidor es vecino de cuál: reconstruido
el k-NN con k=4 contra distancias geodésicas, la proyección esférica
produce 2 aristas distintas en la zona la_enea y la elipsoidal ninguna en
las seis zonas. Usar los dos radios en vez de uno cuesta una constante
más.

La aproximación plana es válida porque cada zona abarca ~1 km² y el
conjunto no supera los 6 km; la curvatura sobre esa extensión queda por
debajo del error de las propias coordenadas.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

import numpy as np
import numpy.typing as npt

# Elipsoide WGS84 (EPSG:4326), el marco de las coordenadas de ami_meters.
WGS84_A: Final = 6_378_137.0
"""Semieje mayor del elipsoide WGS84, en metros."""

WGS84_F: Final = 1 / 298.257_223_563
"""Achatamiento del elipsoide WGS84."""

WGS84_B: Final = WGS84_A * (1 - WGS84_F)
"""Semieje menor del elipsoide WGS84, en metros."""

WGS84_E2: Final = WGS84_F * (2 - WGS84_F)
"""Primera excentricidad al cuadrado del elipsoide WGS84."""

_VINCENTY_MAX_ITER: Final = 200
_VINCENTY_TOL: Final = 1e-14


def curvature_radii(lat_deg: float) -> tuple[float, float]:
    """Radios de curvatura del elipsoide WGS84 en una latitud dada.

    Args:
        lat_deg: Latitud en grados decimales.

    Returns:
        Par `(meridional, normal)` en metros. El meridional gobierna los
        desplazamientos norte-sur y el normal los este-oeste.
    """
    sin2 = math.sin(math.radians(lat_deg)) ** 2
    normal = WGS84_A / math.sqrt(1 - WGS84_E2 * sin2)
    meridional = WGS84_A * (1 - WGS84_E2) / (1 - WGS84_E2 * sin2) ** 1.5
    return meridional, normal


@dataclass(frozen=True, slots=True)
class LocalFrame:
    """Marco de proyección plana local, fijado en un punto de referencia.

    Se construye una sola vez por conjunto de medidores (ver
    `local_frame`) y queda inmutable. Proyectar dos veces con el mismo
    marco da exactamente el mismo resultado, que es lo que permite que el
    grafo sea reproducible.

    Attributes:
        lat0_deg: Latitud del origen del plano, en grados.
        lon0_deg: Longitud del origen del plano, en grados.
        meridional_radius_m: Radio de curvatura meridional en `lat0_deg`.
        normal_radius_m: Radio de curvatura normal en `lat0_deg`.
    """

    lat0_deg: float
    lon0_deg: float
    meridional_radius_m: float
    normal_radius_m: float

    def project(
        self,
        lats_deg: npt.ArrayLike,
        lons_deg: npt.ArrayLike,
    ) -> npt.NDArray[np.float64]:
        """Proyecta coordenadas geográficas al plano local.

        Args:
            lats_deg: Latitudes en grados decimales.
            lons_deg: Longitudes en grados decimales.

        Returns:
            Array `(n, 2)` de solo lectura con las columnas `(x, y)` en
            metros: `x` hacia el este, `y` hacia el norte, ambos relativos
            al origen del marco.

        Raises:
            ValueError: Si las dos secuencias no tienen la misma longitud.
        """
        lats = np.asarray(lats_deg, dtype=np.float64)
        lons = np.asarray(lons_deg, dtype=np.float64)
        if lats.shape != lons.shape:
            raise ValueError(
                f"latitudes y longitudes deben tener la misma forma: {lats.shape} != {lons.shape}"
            )

        cos_lat0 = math.cos(math.radians(self.lat0_deg))
        x = self.normal_radius_m * cos_lat0 * np.radians(lons - self.lon0_deg)
        y = self.meridional_radius_m * np.radians(lats - self.lat0_deg)

        coords = np.column_stack([x, y])
        coords.flags.writeable = False
        return coords


def local_frame(lats_deg: npt.ArrayLike, lons_deg: npt.ArrayLike) -> LocalFrame:
    """Construye el marco local centrado en el baricentro de los puntos.

    Centrar en la media mantiene los desplazamientos pequeños y reparte el
    error de la aproximación plana de forma simétrica.

    Args:
        lats_deg: Latitudes en grados decimales.
        lons_deg: Longitudes en grados decimales.

    Returns:
        El marco de proyección, con los radios de curvatura ya evaluados.

    Raises:
        ValueError: Si no se recibe ningún punto.
    """
    lats = np.asarray(lats_deg, dtype=np.float64)
    lons = np.asarray(lons_deg, dtype=np.float64)
    if lats.size == 0:
        raise ValueError("no se puede construir un marco local sin puntos")

    lat0 = float(lats.mean())
    lon0 = float(lons.mean())
    meridional, normal = curvature_radii(lat0)
    return LocalFrame(
        lat0_deg=lat0,
        lon0_deg=lon0,
        meridional_radius_m=meridional,
        normal_radius_m=normal,
    )


def project_to_local_meters(
    lats_deg: npt.ArrayLike,
    lons_deg: npt.ArrayLike,
    frame: LocalFrame | None = None,
) -> tuple[npt.NDArray[np.float64], LocalFrame]:
    """Proyecta un conjunto de coordenadas, construyendo el marco si falta.

    Args:
        lats_deg: Latitudes en grados decimales.
        lons_deg: Longitudes en grados decimales.
        frame: Marco a reutilizar. Si es `None` se construye uno centrado
            en los propios puntos.

    Returns:
        Par `(coords_m, frame)`, con `coords_m` de forma `(n, 2)` y solo
        lectura. Devolver el marco permite proyectar después otros puntos
        en el mismo plano.
    """
    if frame is None:
        frame = local_frame(lats_deg, lons_deg)
    return frame.project(lats_deg, lons_deg), frame


def pairwise_distances_m(
    coords_m: npt.NDArray[np.float64],
) -> npt.NDArray[np.float64]:
    """Matriz simétrica de distancias euclídeas entre puntos proyectados.

    Densa a propósito: con 20 a 30 medidores por zona una matriz `n × n`
    es despreciable y evita la dependencia de estructuras espaciales.

    Args:
        coords_m: Array `(n, 2)` de coordenadas en metros.

    Returns:
        Array `(n, n)` de distancias en metros, con diagonal exactamente
        cero.

    Raises:
        ValueError: Si `coords_m` no tiene forma `(n, 2)`.
    """
    coords = np.asarray(coords_m, dtype=np.float64)
    if coords.ndim != 2 or coords.shape[1] != 2:
        raise ValueError(f"coords_m debe tener forma (n, 2), recibido {coords.shape}")

    deltas = coords[:, np.newaxis, :] - coords[np.newaxis, :, :]
    distances = np.sqrt((deltas**2).sum(axis=2))
    np.fill_diagonal(distances, 0.0)
    return distances


def _vincenty_lambda(
    sin_u1: float,
    cos_u1: float,
    sin_u2: float,
    cos_u2: float,
    delta_lon: float,
) -> tuple[float, float, float, float, float]:
    """Itera la longitud auxiliar de Vincenty hasta converger.

    Returns:
        Tupla `(sigma, sin_sigma, cos_sigma, cos_sq_alpha, cos_2sigma_m)`
        con las cantidades auxiliares de la fórmula inversa.
    """
    lam = delta_lon
    sigma = sin_sigma = cos_sigma = cos_sq_alpha = cos_2sigma_m = 0.0

    for _ in range(_VINCENTY_MAX_ITER):
        sin_lam, cos_lam = math.sin(lam), math.cos(lam)
        sin_sigma = math.hypot(
            cos_u2 * sin_lam,
            cos_u1 * sin_u2 - sin_u1 * cos_u2 * cos_lam,
        )
        if sin_sigma == 0.0:  # puntos coincidentes
            return 0.0, 0.0, 1.0, 1.0, 0.0

        cos_sigma = sin_u1 * sin_u2 + cos_u1 * cos_u2 * cos_lam
        sigma = math.atan2(sin_sigma, cos_sigma)
        sin_alpha = cos_u1 * cos_u2 * sin_lam / sin_sigma
        cos_sq_alpha = 1 - sin_alpha**2
        # Sobre la línea ecuatorial cos_sq_alpha es cero y cos_2sigma_m
        # queda indefinido; la convención de Vincenty es tomarlo como 0.
        cos_2sigma_m = (
            cos_sigma - 2 * sin_u1 * sin_u2 / cos_sq_alpha if cos_sq_alpha != 0.0 else 0.0
        )
        c = WGS84_F / 16 * cos_sq_alpha * (4 + WGS84_F * (4 - 3 * cos_sq_alpha))
        lam_prev = lam
        lam = delta_lon + (1 - c) * WGS84_F * sin_alpha * (
            sigma + c * sin_sigma * (cos_2sigma_m + c * cos_sigma * (-1 + 2 * cos_2sigma_m**2))
        )
        if abs(lam - lam_prev) < _VINCENTY_TOL:
            break

    return sigma, sin_sigma, cos_sigma, cos_sq_alpha, cos_2sigma_m


def geodesic_distance_m(
    lat1_deg: float,
    lon1_deg: float,
    lat2_deg: float,
    lon2_deg: float,
) -> float:
    """Distancia geodésica sobre el elipsoide WGS84 (fórmula inversa de Vincenty).

    Precisión submilimétrica. **No la usa el constructor del grafo**: está
    acá como referencia independiente para auditar el error de la
    proyección plana sobre una topología nueva, y como oráculo de los
    tests.

    Args:
        lat1_deg: Latitud del primer punto, en grados.
        lon1_deg: Longitud del primer punto, en grados.
        lat2_deg: Latitud del segundo punto, en grados.
        lon2_deg: Longitud del segundo punto, en grados.

    Returns:
        Distancia en metros sobre la superficie del elipsoide.
    """
    lat1, lon1 = math.radians(lat1_deg), math.radians(lon1_deg)
    lat2, lon2 = math.radians(lat2_deg), math.radians(lon2_deg)

    u1 = math.atan((1 - WGS84_F) * math.tan(lat1))
    u2 = math.atan((1 - WGS84_F) * math.tan(lat2))
    sin_u1, cos_u1 = math.sin(u1), math.cos(u1)
    sin_u2, cos_u2 = math.sin(u2), math.cos(u2)

    sigma, sin_sigma, cos_sigma, cos_sq_alpha, cos_2sigma_m = _vincenty_lambda(
        sin_u1, cos_u1, sin_u2, cos_u2, lon2 - lon1
    )
    if sigma == 0.0:
        return 0.0

    u_sq = cos_sq_alpha * (WGS84_A**2 - WGS84_B**2) / WGS84_B**2
    a_coef = 1 + u_sq / 16384 * (4096 + u_sq * (-768 + u_sq * (320 - 175 * u_sq)))
    b_coef = u_sq / 1024 * (256 + u_sq * (-128 + u_sq * (74 - 47 * u_sq)))
    delta_sigma = (
        b_coef
        * sin_sigma
        * (
            cos_2sigma_m
            + b_coef
            / 4
            * (
                cos_sigma * (-1 + 2 * cos_2sigma_m**2)
                - b_coef / 6 * cos_2sigma_m * (-3 + 4 * sin_sigma**2) * (-3 + 4 * cos_2sigma_m**2)
            )
        )
    )
    return float(WGS84_B * a_coef * (sigma - delta_sigma))
