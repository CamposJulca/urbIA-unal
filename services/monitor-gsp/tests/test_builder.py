"""Tests del constructor del grafo AMI.

Dos clases de test, con propósitos distintos:

* **Propiedades**, sobre topologías sintéticas de geometría conocida
  (rejilla regular, dos cúmulos separados). Verifican lo que debe valer
  para cualquier entrada: reproducibilidad, orden canónico, simetría,
  grado mínimo garantizado por el k-NN simetrizado.

* **Regresión sobre la topología real** de `data/topologies/manizales_150.json`,
  los 150 medidores de las seis zonas de Manizales. Fijan las cifras que
  los docstrings de `GraphConfig` y del `README` usan como justificación,
  para que dejen de ser afirmaciones y pasen a ser algo que se rompe si
  cambia la construcción.

Las cifras esperadas no salen de correr el constructor: se midieron con un
script independiente que arma el k-NN a mano, antes de que este módulo
existiera.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import ClassVar

import numpy as np
import pytest

from urbia_monitor_gsp.graph.builder import build_ami_graph, build_zone_graph
from urbia_monitor_gsp.graph.spectral import degenerate_groups
from urbia_monitor_gsp.graph.types import (
    GraphConfig,
    InsufficientMetersError,
    InvalidGraphConfigError,
    MeterNode,
    ZeroDegreeNodeError,
)

TOPOLOGIA = Path(__file__).parents[3] / "data" / "topologies" / "manizales_150.json"


@pytest.fixture(scope="module")
def manizales() -> list[MeterNode]:
    """Los 150 medidores reales, desde la topología versionada."""
    if not TOPOLOGIA.exists():
        pytest.fail(f"falta la topología de regresión: {TOPOLOGIA}")
    datos = json.loads(TOPOLOGIA.read_text(encoding="utf-8"))
    return [MeterNode(**m) for m in datos["meters"]]


def rejilla(zona: str, filas: int, columnas: int, paso_grados: float = 0.001) -> list[MeterNode]:
    """Medidores en una rejilla regular, para geometría predecible."""
    return [
        MeterNode(
            device_id=f"{zona}-{f:02d}{c:02d}",
            zona=zona,
            lat=5.06 + f * paso_grados,
            lon=-75.51 + c * paso_grados,
        )
        for f in range(filas)
        for c in range(columnas)
    ]


def dos_cumulos(zona: str = "z") -> list[MeterNode]:
    """Dos grupos de 3 medidores muy separados entre sí."""
    cerca = [(5.060 + i * 0.0002, -75.510) for i in range(3)]
    lejos = [(5.090 + i * 0.0002, -75.510) for i in range(3)]
    return [
        MeterNode(device_id=f"{zona}-{i:02d}", zona=zona, lat=lat, lon=lon)
        for i, (lat, lon) in enumerate(cerca + lejos)
    ]


class TestReproducibilidad:
    def test_build_zone_graph_es_independiente_del_orden_de_entrada(self) -> None:
        """El orden de llegada de los medidores no debe influir en nada."""
        meters = rejilla("z", 5, 5)
        barajados = [meters[i] for i in np.random.default_rng(0).permutation(len(meters))]

        directo = build_zone_graph(meters)
        barajado = build_zone_graph(barajados)

        assert directo.device_ids == barajado.device_ids
        np.testing.assert_array_equal(directo.adjacency, barajado.adjacency)
        np.testing.assert_array_equal(directo.eigenvalues, barajado.eigenvalues)

    def test_build_zone_graph_dos_veces_da_lo_mismo_bit_a_bit(self) -> None:
        meters = rejilla("z", 4, 4)
        una, otra = build_zone_graph(meters), build_zone_graph(meters)
        np.testing.assert_array_equal(una.adjacency, otra.adjacency)
        np.testing.assert_array_equal(una.eigenvectors, otra.eigenvectors)

    def test_device_ids_quedan_en_orden_alfabetico(self) -> None:
        grafo = build_zone_graph(rejilla("z", 3, 3))
        assert list(grafo.device_ids) == sorted(grafo.device_ids)

    def test_las_matrices_son_de_solo_lectura(self) -> None:
        """Mutarlas dejaría el espectro guardado describiendo otro grafo."""
        grafo = build_zone_graph(rejilla("z", 3, 3))
        for matriz in (
            grafo.adjacency,
            grafo.distances_m,
            grafo.laplacian,
            grafo.laplacian_norm,
            grafo.eigenvalues,
            grafo.eigenvectors,
            grafo.coords_m,
        ):
            assert not matriz.flags.writeable
            with pytest.raises(ValueError, match="read-only"):
                matriz[0] = 0.0


class TestConstruccionKnn:
    def test_knn_union_garantiza_grado_minimo_k(self) -> None:
        """Lo que evita los nodos hoja que E6 marcó como punto ciego."""
        grafo = build_zone_graph(rejilla("z", 5, 5), GraphConfig(k=4))
        assert grafo.stats.degree_min >= 4
        assert grafo.stats.k_effective == 4

    def test_adyacencia_es_simetrica_con_diagonal_nula(self) -> None:
        grafo = build_zone_graph(rejilla("z", 4, 4))
        np.testing.assert_array_equal(grafo.adjacency, grafo.adjacency.T)
        np.testing.assert_array_equal(np.diag(grafo.adjacency), np.zeros(16))

    def test_k_se_recorta_cuando_la_zona_tiene_menos_de_k_mas_uno(self) -> None:
        grafo = build_zone_graph(rejilla("z", 1, 3), GraphConfig(k=10))
        assert grafo.stats.k_effective == 2
        assert grafo.n_meters == 3

    def test_knn_mutual_puede_fragmentar_la_zona(self) -> None:
        """La reciprocidad no garantiza conectividad; la unión sí, más."""
        meters = rejilla("z", 5, 5)
        union = build_zone_graph(meters, GraphConfig(k=4, knn_mode="union"))
        mutual = build_zone_graph(meters, GraphConfig(k=4, knn_mode="mutual"))
        assert union.stats.n_components == 1
        assert mutual.stats.degree_min <= union.stats.degree_min

    def test_n_edges_cuenta_aristas_no_dirigidas(self) -> None:
        grafo = build_zone_graph(rejilla("z", 4, 4), GraphConfig(k=2))
        assert grafo.stats.n_edges == int((grafo.adjacency > 0).sum()) // 2


class TestConstruccionRadio:
    def test_radius_conecta_lo_que_esta_dentro_del_radio(self) -> None:
        grafo = build_zone_graph(rejilla("z", 3, 3), GraphConfig(strategy="radius", radius_m=150.0))
        assert grafo.stats.max_edge_length_m <= 150.0
        assert grafo.stats.k_effective == 0

    def test_radius_demasiado_chico_deja_medidores_aislados(self) -> None:
        """Error explícito con la zona y los device_id, no un NaN en el espectro."""
        with pytest.raises(ZeroDegreeNodeError) as exc:
            build_zone_graph(dos_cumulos("la_enea"), GraphConfig(strategy="radius", radius_m=5.0))
        assert exc.value.zona == "la_enea"
        assert exc.value.device_ids is not None
        assert "la_enea" in str(exc.value)

    def test_radius_grande_conecta_los_dos_cumulos(self) -> None:
        grafo = build_zone_graph(dos_cumulos(), GraphConfig(strategy="radius", radius_m=5000.0))
        assert grafo.stats.n_components == 1


class TestPesoGaussiano:
    def test_gaussian_pondera_entre_cero_y_uno(self) -> None:
        grafo = build_zone_graph(rejilla("z", 4, 4), GraphConfig(weighting="gaussian"))
        pesos = grafo.adjacency[grafo.adjacency > 0]
        assert pesos.size > 0
        assert np.all((pesos > 0.0) & (pesos <= 1.0))

    def test_gaussian_pesa_menos_a_mayor_distancia(self) -> None:
        grafo = build_zone_graph(rejilla("z", 4, 4), GraphConfig(weighting="gaussian"))
        aristas = np.triu(grafo.adjacency, k=1) > 0
        pesos, largos = grafo.adjacency[aristas], grafo.distances_m[aristas]
        assert np.corrcoef(pesos, largos)[0, 1] < -0.5

    def test_gaussian_sin_sigma_la_deriva_de_la_mediana_de_las_aristas(self) -> None:
        """Sigma explícita igual a la mediana debe dar la misma matriz."""
        meters = rejilla("z", 4, 4)
        derivada = build_zone_graph(meters, GraphConfig(weighting="gaussian"))
        aristas = np.triu(derivada.adjacency, k=1) > 0
        mediana = float(np.median(derivada.distances_m[aristas]))

        explicita = build_zone_graph(meters, GraphConfig(weighting="gaussian", sigma_m=mediana))
        np.testing.assert_allclose(derivada.adjacency, explicita.adjacency, atol=1e-15)

    def test_gaussian_conserva_la_topologia_del_binario(self) -> None:
        """El peso cambia la magnitud de las aristas, no cuáles existen."""
        meters = rejilla("z", 4, 4)
        binario = build_zone_graph(meters, GraphConfig(weighting="binary"))
        gaussiano = build_zone_graph(meters, GraphConfig(weighting="gaussian"))
        np.testing.assert_array_equal(binario.adjacency > 0, gaussiano.adjacency > 0)


class TestValidacion:
    def test_zona_con_un_solo_medidor_levanta_error(self) -> None:
        with pytest.raises(InsufficientMetersError, match="al menos"):
            build_zone_graph([MeterNode("m-1", "z", 5.06, -75.51)])

    def test_build_zone_graph_sin_medidores_levanta_error(self) -> None:
        with pytest.raises(InvalidGraphConfigError, match="sin medidores"):
            build_zone_graph([])

    def test_build_ami_graph_sin_medidores_levanta_error(self) -> None:
        with pytest.raises(InvalidGraphConfigError, match="sin medidores"):
            build_ami_graph([])

    def test_build_zone_graph_con_zonas_mezcladas_levanta_error(self) -> None:
        mezcla = [MeterNode("m-1", "a", 5.06, -75.51), MeterNode("m-2", "b", 5.07, -75.52)]
        with pytest.raises(InvalidGraphConfigError, match="una sola zona"):
            build_zone_graph(mezcla)

    def test_puente_inter_zona_levanta_error_por_no_implementado(self) -> None:
        with pytest.raises(InvalidGraphConfigError, match="no está implementado"):
            build_zone_graph(rejilla("z", 3, 3), GraphConfig(inter_zone_bridge=True))

    def test_gaussian_sin_aristas_no_puede_derivar_sigma(self) -> None:
        config = GraphConfig(strategy="radius", radius_m=1.0, weighting="gaussian")
        with pytest.raises(InvalidGraphConfigError, match="sin aristas"):
            build_zone_graph(rejilla("z", 3, 3), config)


class TestAmiGraph:
    def test_build_ami_graph_arma_un_subgrafo_por_zona(self) -> None:
        meters = rejilla("norte", 3, 3) + rejilla("sur", 3, 3)
        grafo = build_ami_graph(meters)
        assert grafo.n_zones == 2
        assert grafo.n_meters == 18
        assert set(grafo.zones) == {"norte", "sur"}

    def test_zone_order_es_alfabetico(self) -> None:
        meters = rejilla("sur", 3, 3) + rejilla("norte", 3, 3) + rejilla("centro", 3, 3)
        assert build_ami_graph(meters).zone_order == ("centro", "norte", "sur")

    def test_las_zonas_no_comparten_aristas(self) -> None:
        """Sin puente, cada subgrafo es analizable por su nodo de borde."""
        grafo = build_ami_graph(rejilla("norte", 3, 3) + rejilla("sur", 3, 3))
        for zona in grafo.zones.values():
            assert zona.stats.n_components == 1
            assert zona.n_meters == 9

    def test_una_zona_insuficiente_hace_fallar_toda_la_construccion(self) -> None:
        meters = [*rejilla("norte", 3, 3), MeterNode("s-1", "sur", 5.06, -75.51)]
        with pytest.raises(InsufficientMetersError, match="'sur'"):
            build_ami_graph(meters)


class TestRegresionManizales:
    """Fija las cifras que los docstrings usan como justificación.

    Medidas con un script independiente sobre los 150 medidores reales,
    antes de que existiera `builder`. Si alguna cambia, cambió la
    construcción y hay docstrings que dejaron de ser ciertos.
    """

    FIEDLER_K4: ClassVar[dict[str, float]] = {
        "centro": 0.0545,
        "chipre": 0.0505,
        "la_enea": 0.0901,
        "palermo": 0.0940,
        "palogrande": 0.0602,
        "universitario": 0.1238,
    }
    MULTIPLICIDAD_125: ClassVar[dict[str, int]] = {
        "palermo": 6,
        "centro": 3,
        "palogrande": 2,
        "universitario": 2,
    }

    def test_la_topologia_tiene_150_medidores_en_6_zonas(self, manizales: list[MeterNode]) -> None:
        grafo = build_ami_graph(manizales)
        assert grafo.n_meters == 150
        assert grafo.zone_order == (
            "centro",
            "chipre",
            "la_enea",
            "palermo",
            "palogrande",
            "universitario",
        )

    def test_k4_deja_las_seis_zonas_conexas(self, manizales: list[MeterNode]) -> None:
        """La afirmación central del docstring de GraphConfig."""
        grafo = build_ami_graph(manizales, GraphConfig(k=4))
        for zona in grafo.zones.values():
            assert zona.stats.n_components == 1, f"{zona.zona} quedó desconectada"

    def test_k3_parte_la_enea_en_dos_componentes(self, manizales: list[MeterNode]) -> None:
        """k=4 no es holgura sobre el mínimo: es el mínimo."""
        grafo = build_ami_graph(manizales, GraphConfig(k=3))
        assert grafo.zones["la_enea"].stats.n_components == 2
        otras = [z for z in grafo.zones.values() if z.zona != "la_enea"]
        assert all(z.stats.n_components == 1 for z in otras)

    def test_k3_deja_fiedler_minimo_en_universitario(self, manizales: list[MeterNode]) -> None:
        grafo = build_ami_graph(manizales, GraphConfig(k=3))
        conexas = {z.zona: z.stats.lambda_1 for z in grafo.zones.values() if z.zona != "la_enea"}
        assert min(conexas, key=lambda z: conexas[z]) == "universitario"
        assert conexas["universitario"] == pytest.approx(0.0219, abs=5e-5)

    @pytest.mark.parametrize("zona", sorted(FIEDLER_K4))
    def test_fiedler_por_zona_con_k4(self, manizales: list[MeterNode], zona: str) -> None:
        grafo = build_ami_graph(manizales, GraphConfig(k=4))
        assert grafo.zones[zona].stats.lambda_1 == pytest.approx(self.FIEDLER_K4[zona], abs=5e-5)

    @pytest.mark.parametrize("zona", sorted(MULTIPLICIDAD_125))
    def test_multiplicidad_de_lambda_125_por_nodos_gemelos(
        self, manizales: list[MeterNode], zona: str
    ) -> None:
        """Nodos gemelos de grado 4 dan el autovalor exacto 1 + 1/4."""
        grafo = build_ami_graph(manizales, GraphConfig(k=4))
        valores = grafo.zones[zona].eigenvalues
        grupos = degenerate_groups(valores)
        en_125 = [len(g) for g in grupos if abs(valores[g[0]] - 1.25) < 1e-9]
        assert en_125 == [self.MULTIPLICIDAD_125[zona]]

    def test_mutual_con_k4_solo_deja_conexa_a_palogrande(self, manizales: list[MeterNode]) -> None:
        """La cifra que justifica knn_mode='union' por defecto."""
        config = GraphConfig(k=4, knn_mode="mutual")
        conexas = []
        for zona in sorted({m.zona for m in manizales}):
            de_zona = [m for m in manizales if m.zona == zona]
            try:
                grafo = build_zone_graph(de_zona, config)
            except ZeroDegreeNodeError:
                continue
            if grafo.stats.n_components == 1:
                conexas.append(zona)
        assert conexas == ["palogrande"]

    def test_radio_399_es_el_minimo_que_conecta_las_seis_zonas(
        self, manizales: list[MeterNode]
    ) -> None:
        """La cifra corregida del README: no es 450 m.

        Un metro menos y la_enea se parte en dos, que es exactamente la
        zona que también falla con k=3. Es la zona más rala de las seis y
        la que fija el punto de operación de toda la construcción.
        """
        conexo = build_ami_graph(manizales, GraphConfig(strategy="radius", radius_m=399.0))
        assert all(z.stats.n_components == 1 for z in conexo.zones.values())

        apenas_menos = build_ami_graph(manizales, GraphConfig(strategy="radius", radius_m=398.0))
        partidas = {z.zona: z.stats.n_components for z in apenas_menos.zones.values()}
        assert partidas["la_enea"] == 2
        assert all(n == 1 for zona, n in partidas.items() if zona != "la_enea")

    def test_a_radio_399_los_grados_van_de_2_a_17(self, manizales: list[MeterNode]) -> None:
        """La dispersión que justifica k-NN sobre radio fijo."""
        grafo = build_ami_graph(manizales, GraphConfig(strategy="radius", radius_m=399.0))
        grados = [(z.stats.degree_min, z.stats.degree_max) for z in grafo.zones.values()]
        assert min(g[0] for g in grados) == 2
        assert max(g[1] for g in grados) == 17
