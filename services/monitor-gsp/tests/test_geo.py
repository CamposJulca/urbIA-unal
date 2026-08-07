"""Tests de la proyección local y de la distancia geodésica de referencia."""

from __future__ import annotations

import itertools
import math

import numpy as np
import pytest

from urbia_monitor_gsp.graph.geo import (
    WGS84_A,
    WGS84_E2,
    LocalFrame,
    curvature_radii,
    geodesic_distance_m,
    local_frame,
    pairwise_distances_m,
    project_to_local_meters,
)

# Extensión real de los 150 medidores de Manizales en ami_meters.
MANIZALES_LAT = (5.049, 5.078)
MANIZALES_LON = (-75.525, -75.470)
MANIZALES_CENTRO = (5.06, -75.5)

# El error de la aproximación plana crece con el cuadrado de la extensión.
# Medido contra Vincenty sobre rejillas centradas en Manizales:
#
#     distancia máxima entre puntos      error máximo
#              705 m                        0,17 cm
#            1.691 m                        0,99 cm
#            4.228 m                        6,21 cm
#            8.613 m                       25,82 cm
#
# La escala que gobierna las aristas es la intra-zona: la zona más
# extensa (la_enea) mide 1191 × 1014 m y su par más lejano está a 1350 m.
# Ahí el error es submilimétrico a milimétrico. Por eso el marco de
# proyección se construye por zona y no uno global para las seis.
ZONA_DELTA_DEG = 0.0108  # ~1,2 km de lado, la extensión de la zona mayor

# Valores geodésicos publicados para WGS84, usados como referencia externa.
# Un grado de longitud en el ecuador es exactamente 2·pi·a/360.
GRADO_LON_ECUADOR_M = 2 * math.pi * WGS84_A / 360
# Un grado de latitud en el ecuador, valor estándar de la literatura.
GRADO_LAT_ECUADOR_M = 110_574.4


def _rejilla_manizales(n_lat: int = 6, n_lon: int = 6) -> list[tuple[float, float]]:
    """Rejilla determinista sobre el área completa de los 150 medidores (~6 km)."""
    lats = np.linspace(*MANIZALES_LAT, n_lat)
    lons = np.linspace(*MANIZALES_LON, n_lon)
    return [(float(la), float(lo)) for la in lats for lo in lons]


def _rejilla_zona(n: int = 6) -> list[tuple[float, float]]:
    """Rejilla determinista a escala de una zona (~1,2 km de lado)."""
    lat_c, lon_c = MANIZALES_CENTRO
    lats = np.linspace(lat_c - ZONA_DELTA_DEG / 2, lat_c + ZONA_DELTA_DEG / 2, n)
    lons = np.linspace(lon_c - ZONA_DELTA_DEG / 2, lon_c + ZONA_DELTA_DEG / 2, n)
    return [(float(la), float(lo)) for la in lats for lo in lons]


def _error_maximo(puntos: list[tuple[float, float]], coords: np.ndarray) -> float:
    """Mayor discrepancia entre distancias proyectadas y geodésicas, en metros."""
    return max(
        abs(
            float(np.linalg.norm(coords[i] - coords[j]))
            - geodesic_distance_m(*puntos[i], *puntos[j])
        )
        for i, j in itertools.combinations(range(len(puntos)), 2)
    )


class TestCurvatureRadii:
    def test_curvature_radii_ecuador_normal_igual_semieje_mayor(self) -> None:
        meridional, normal = curvature_radii(0.0)
        assert normal == pytest.approx(WGS84_A, abs=1e-6)
        assert meridional == pytest.approx(WGS84_A * (1 - WGS84_E2), abs=1e-6)

    def test_curvature_radii_polo_ambos_radios_coinciden(self) -> None:
        meridional, normal = curvature_radii(90.0)
        esperado = WGS84_A / math.sqrt(1 - WGS84_E2)
        assert normal == pytest.approx(esperado, abs=1e-6)
        assert meridional == pytest.approx(esperado, abs=1e-6)

    def test_curvature_radii_manizales_meridional_menor_que_normal(self) -> None:
        meridional, normal = curvature_radii(5.06)
        assert meridional < normal
        # El radio esférico medio (6.371 km) queda entre ambos: usarlo
        # introduce el sesgo sistemático que motivó esta proyección.
        assert meridional < 6_371_000.0 < normal

    def test_curvature_radii_es_simetrico_respecto_al_ecuador(self) -> None:
        assert curvature_radii(5.06) == pytest.approx(curvature_radii(-5.06))


class TestGeodesicDistance:
    def test_geodesic_distance_grado_de_longitud_en_ecuador_valor_publicado(self) -> None:
        d = geodesic_distance_m(0.0, 0.0, 0.0, 1.0)
        assert d == pytest.approx(GRADO_LON_ECUADOR_M, abs=0.001)

    def test_geodesic_distance_grado_de_latitud_en_ecuador_valor_publicado(self) -> None:
        d = geodesic_distance_m(0.0, 0.0, 1.0, 0.0)
        assert d == pytest.approx(GRADO_LAT_ECUADOR_M, abs=1.0)

    def test_geodesic_distance_punto_consigo_mismo_es_cero(self) -> None:
        assert geodesic_distance_m(5.06, -75.5, 5.06, -75.5) == 0.0

    def test_geodesic_distance_es_simetrica(self) -> None:
        ida = geodesic_distance_m(5.049, -75.525, 5.078, -75.470)
        vuelta = geodesic_distance_m(5.078, -75.470, 5.049, -75.525)
        assert ida == pytest.approx(vuelta, abs=1e-9)

    def test_geodesic_distance_cuadrante_meridiano_valor_publicado(self) -> None:
        # Del ecuador al polo: 10.001,966 km según WGS84.
        d = geodesic_distance_m(0.0, 0.0, 90.0, 0.0)
        assert d == pytest.approx(10_001_965.729, abs=1.0)


class TestProjection:
    def test_project_to_local_meters_a_escala_de_zona_error_bajo_un_centimetro(self) -> None:
        """El criterio que importa: a escala de zona no altera las distancias.

        Es la escala en que se deciden las aristas, y la que gobierna el
        criterio de vecindad.
        """
        puntos = _rejilla_zona()
        coords, _ = project_to_local_meters([p[0] for p in puntos], [p[1] for p in puntos])
        assert _error_maximo(puntos, coords) < 0.01

    def test_project_to_local_meters_a_escala_metropolitana_error_bajo_treinta_cm(self) -> None:
        """El error crece con la extensión: documentado, no ignorado.

        Sobre los ~8,6 km que separan los extremos del área completa el
        error llega a ~26 cm. Sigue siendo irrelevante frente a distancias
        de vecindad de cientos de metros, pero justifica que el marco se
        construya por zona.
        """
        puntos = _rejilla_manizales()
        coords, _ = project_to_local_meters([p[0] for p in puntos], [p[1] for p in puntos])
        error = _error_maximo(puntos, coords)
        assert 0.01 < error < 0.30

    def test_project_to_local_meters_supera_a_la_esfera_de_radio_medio(self) -> None:
        """Test de regresión de la decisión de diseño (ADR-003).

        Documenta por qué se usan los dos radios de curvatura y no un radio
        esférico medio: el error de la esfera es de metros, no de
        centímetros, y a escala de vecindad cambia qué medidor es vecino de
        cuál.
        """
        puntos = _rejilla_zona()
        lats = [p[0] for p in puntos]
        lons = [p[1] for p in puntos]
        coords, _ = project_to_local_meters(lats, lons)

        r_medio = 6_371_000.0
        lat0 = float(np.mean(lats))
        esfericas = np.column_stack(
            [
                r_medio * math.cos(math.radians(lat0)) * np.radians(np.array(lons) - np.mean(lons)),
                r_medio * np.radians(np.array(lats) - lat0),
            ]
        )

        err_elipsoidal = _error_maximo(puntos, coords)
        err_esferico = _error_maximo(puntos, esfericas)

        assert err_elipsoidal < 0.01
        assert err_esferico > 1.0
        assert err_esferico > 100 * err_elipsoidal

    def test_project_to_local_meters_es_determinista(self) -> None:
        puntos = _rejilla_manizales(3, 3)
        lats = [p[0] for p in puntos]
        lons = [p[1] for p in puntos]
        primera, frame = project_to_local_meters(lats, lons)
        segunda, _ = project_to_local_meters(lats, lons, frame)
        np.testing.assert_array_equal(primera, segunda)

    def test_project_to_local_meters_devuelve_array_de_solo_lectura(self) -> None:
        """`coords_m` se calcula una vez y no debe poder mutarse después."""
        coords, _ = project_to_local_meters([5.06, 5.07], [-75.5, -75.49])
        assert coords.flags.writeable is False
        with pytest.raises(ValueError, match="read-only"):
            coords[0, 0] = 1.0

    def test_project_to_local_meters_origen_del_marco_queda_en_el_cero(self) -> None:
        meridional, normal = curvature_radii(5.06)
        frame = LocalFrame(
            lat0_deg=5.06,
            lon0_deg=-75.5,
            meridional_radius_m=meridional,
            normal_radius_m=normal,
        )
        coords = frame.project([5.06], [-75.5])
        np.testing.assert_allclose(coords, [[0.0, 0.0]], atol=1e-9)

    def test_project_to_local_meters_ejes_orientados_al_este_y_al_norte(self) -> None:
        frame = local_frame([5.06], [-75.5])
        al_este = frame.project([5.06], [-75.49])
        al_norte = frame.project([5.07], [-75.5])
        assert al_este[0, 0] > 0 and al_este[0, 1] == pytest.approx(0.0, abs=1e-9)
        assert al_norte[0, 1] > 0 and al_norte[0, 0] == pytest.approx(0.0, abs=1e-9)

    def test_project_to_local_meters_formas_distintas_levanta_error(self) -> None:
        with pytest.raises(ValueError, match="misma forma"):
            project_to_local_meters([5.06, 5.07], [-75.5])

    def test_local_frame_sin_puntos_levanta_error(self) -> None:
        with pytest.raises(ValueError, match="sin puntos"):
            local_frame([], [])

    def test_local_frame_se_centra_en_el_baricentro(self) -> None:
        frame = local_frame([5.0, 5.1], [-75.6, -75.4])
        assert frame.lat0_deg == pytest.approx(5.05)
        assert frame.lon0_deg == pytest.approx(-75.5)


class TestPairwiseDistances:
    def test_pairwise_distances_m_triangulo_conocido(self) -> None:
        coords = np.array([[0.0, 0.0], [3.0, 0.0], [0.0, 4.0]])
        distancias = pairwise_distances_m(coords)
        assert distancias[0, 1] == pytest.approx(3.0)
        assert distancias[0, 2] == pytest.approx(4.0)
        assert distancias[1, 2] == pytest.approx(5.0)

    def test_pairwise_distances_m_diagonal_nula_y_simetrica(self) -> None:
        coords, _ = project_to_local_meters(
            [p[0] for p in _rejilla_manizales(3, 3)],
            [p[1] for p in _rejilla_manizales(3, 3)],
        )
        distancias = pairwise_distances_m(coords)
        np.testing.assert_array_equal(np.diag(distancias), np.zeros(len(coords)))
        np.testing.assert_allclose(distancias, distancias.T, atol=1e-12)

    def test_pairwise_distances_m_forma_invalida_levanta_error(self) -> None:
        with pytest.raises(ValueError, match=r"forma \(n, 2\)"):
            pairwise_distances_m(np.array([1.0, 2.0, 3.0]))
