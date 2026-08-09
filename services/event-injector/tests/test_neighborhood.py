"""Tests del vecindario: qué nodos abarca un evento."""

from __future__ import annotations

import numpy as np
import pytest
from urbia_monitor_gsp.graph import AmiGraph, ZoneGraph

from urbia_events import (
    boundary_edges,
    connected_subgraph,
    is_connected,
    k_hop,
    neighborhood_sizes,
)


def camino(n: int) -> np.ndarray:
    """Grafo en línea: 0—1—2—...—(n-1). Vecindarios de tamaño predecible."""
    a = np.zeros((n, n))
    for i in range(n - 1):
        a[i, i + 1] = a[i + 1, i] = 1.0
    return a


class TestKHop:
    def test_profundidad_cero_devuelve_solo_la_semilla(self) -> None:
        assert k_hop(camino(5), 2, 0) == (2,)

    def test_profundidad_uno_devuelve_la_semilla_y_sus_vecinos(self) -> None:
        assert k_hop(camino(5), 2, 1) == (1, 2, 3)

    def test_profundidad_dos_alcanza_dos_saltos(self) -> None:
        assert k_hop(camino(5), 2, 2) == (0, 1, 2, 3, 4)

    def test_desde_un_extremo_el_vecindario_es_asimetrico(self) -> None:
        assert k_hop(camino(5), 0, 2) == (0, 1, 2)

    def test_profundidad_mayor_que_el_diametro_devuelve_la_componente(self) -> None:
        assert k_hop(camino(5), 2, 99) == (0, 1, 2, 3, 4)

    def test_el_resultado_viene_ordenado(self) -> None:
        """El orden no debe depender del recorrido, para ser reproducible."""
        vecindario = k_hop(camino(7), 3, 2)
        assert list(vecindario) == sorted(vecindario)

    def test_los_pesos_no_cambian_la_vecindad(self) -> None:
        """Sólo importa si la arista existe, no cuánto pesa."""
        binario = camino(5)
        ponderado = binario * 0.001
        assert k_hop(binario, 2, 1) == k_hop(ponderado, 2, 1)

    def test_un_nodo_aislado_es_su_propio_vecindario(self) -> None:
        aislado = np.zeros((3, 3))
        aislado[0, 1] = aislado[1, 0] = 1.0
        assert k_hop(aislado, 2, 5) == (2,)

    def test_adyacencia_no_cuadrada_levanta_error(self) -> None:
        with pytest.raises(ValueError, match="cuadrada"):
            k_hop(np.zeros((3, 4)), 0, 1)

    def test_semilla_fuera_del_grafo_levanta_error(self) -> None:
        with pytest.raises(ValueError, match="fuera del grafo"):
            k_hop(camino(3), 7, 1)

    def test_profundidad_negativa_levanta_error(self) -> None:
        with pytest.raises(ValueError, match="depth"):
            k_hop(camino(3), 0, -1)


class TestSobreLaTopologiaReal:
    """Fija los tamaños que justifican el rango útil de `depth`."""

    def test_profundidad_uno_cubre_entre_el_20_y_el_27_por_ciento(self, grafo: AmiGraph) -> None:
        for zona in grafo.zones.values():
            fraccion = float(np.median(neighborhood_sizes(zona.adjacency, 1))) / zona.n_meters
            assert 0.20 <= fraccion <= 0.275, f"{zona.zona}: {fraccion:.1%}"

    def test_profundidad_dos_cubre_entre_el_40_y_el_55_por_ciento(self, grafo: AmiGraph) -> None:
        for zona in grafo.zones.values():
            fraccion = float(np.median(neighborhood_sizes(zona.adjacency, 2))) / zona.n_meters
            assert 0.40 <= fraccion <= 0.55, f"{zona.zona}: {fraccion:.1%}"

    def test_profundidad_tres_es_degenerada(self, grafo: AmiGraph) -> None:
        """A partir de 3 saltos casi no queda vecindario sano que contrastar.

        Es la cifra que justifica documentar `depth >= 3` como degenerado:
        el evento deja de ser una discordancia local.
        """
        for zona in grafo.zones.values():
            fraccion = float(np.median(neighborhood_sizes(zona.adjacency, 3))) / zona.n_meters
            assert fraccion >= 0.60, f"{zona.zona}: {fraccion:.1%}"

    def test_el_grado_minimo_garantiza_vecindario_no_trivial(self, zona_mono: ZoneGraph) -> None:
        """Con k-NN k=4 por unión ningún nodo queda sin vecinos."""
        tamanos = neighborhood_sizes(zona_mono.adjacency, 1)
        assert int(tamanos.min()) >= 5


def rejilla(lado: int) -> np.ndarray:
    """Rejilla cuadrada de 4 vecinos: perímetro predecible."""
    n = lado * lado
    a = np.zeros((n, n))
    for f in range(lado):
        for c in range(lado):
            i = f * lado + c
            if c + 1 < lado:
                a[i, i + 1] = a[i + 1, i] = 1.0
            if f + 1 < lado:
                a[i, i + lado] = a[i + lado, i] = 1.0
    return a


class TestConnectedSubgraph:
    """El eje del barrido: tamaño exacto, conexo y reproducible."""

    @pytest.mark.parametrize("forma", ["compacto", "extendido"])
    @pytest.mark.parametrize("m", [1, 2, 3, 5, 8, 13, 25])
    def test_devuelve_exactamente_el_tamano_pedido(self, forma: str, m: int) -> None:
        grupo = connected_subgraph(rejilla(5), 12, m, shape=forma, rng=np.random.default_rng(1))
        assert len(grupo) == m

    @pytest.mark.parametrize("forma", ["compacto", "extendido"])
    @pytest.mark.parametrize("m", [1, 2, 3, 5, 8, 13, 25])
    def test_el_grupo_es_conexo(self, forma: str, m: int) -> None:
        """Lo que separa un grupo extendido de dos componentes sueltas.

        Un grupo partido sería una tercera condición experimental y
        confundirla con "extendido" invalidaría el contraste de forma.
        """
        adyacencia = rejilla(5)
        for semilla in range(25):
            grupo = connected_subgraph(
                adyacencia, semilla, m, shape=forma, rng=np.random.default_rng(semilla)
            )
            assert is_connected(adyacencia, grupo), f"{forma} m={m} semilla={semilla}"

    @pytest.mark.parametrize("forma", ["compacto", "extendido"])
    def test_incluye_siempre_a_la_semilla(self, forma: str) -> None:
        for m in (1, 4, 9):
            grupo = connected_subgraph(rejilla(5), 7, m, shape=forma, rng=np.random.default_rng(2))
            assert 7 in grupo

    @pytest.mark.parametrize("forma", ["compacto", "extendido"])
    def test_misma_semilla_mismo_grupo(self, forma: str) -> None:
        """Sin esto la verdad de referencia no sería reproducible."""
        uno = connected_subgraph(rejilla(5), 12, 6, shape=forma, rng=np.random.default_rng(7))
        otro = connected_subgraph(rejilla(5), 12, 6, shape=forma, rng=np.random.default_rng(7))
        assert uno == otro

    def test_semillas_distintas_dan_grupos_distintos(self) -> None:
        """El barajado dentro de la capa tiene que hacer trabajo real."""
        grupos = {
            connected_subgraph(rejilla(5), 12, 6, rng=np.random.default_rng(s)) for s in range(20)
        }
        assert len(grupos) > 1

    def test_tamano_uno_es_solo_la_semilla(self) -> None:
        assert connected_subgraph(rejilla(5), 12, 1, rng=np.random.default_rng(1)) == (12,)

    def test_tamano_total_es_la_zona_entera(self) -> None:
        """El caso limite del barrido: el modo comun."""
        grupo = connected_subgraph(rejilla(5), 12, 25, rng=np.random.default_rng(1))
        assert grupo == tuple(range(25))

    def test_el_resultado_viene_ordenado(self) -> None:
        grupo = connected_subgraph(rejilla(5), 12, 7, rng=np.random.default_rng(3))
        assert list(grupo) == sorted(grupo)

    def test_tamano_cero_es_error(self) -> None:
        with pytest.raises(ValueError, match="size_target debe estar"):
            connected_subgraph(rejilla(5), 12, 0, rng=np.random.default_rng(1))

    def test_tamano_mayor_que_el_grafo_es_error(self) -> None:
        with pytest.raises(ValueError, match="size_target debe estar"):
            connected_subgraph(rejilla(5), 12, 26, rng=np.random.default_rng(1))

    def test_forma_desconocida_es_error(self) -> None:
        with pytest.raises(ValueError, match="shape debe ser"):
            connected_subgraph(rejilla(5), 12, 4, shape="raro", rng=np.random.default_rng(1))  # type: ignore[arg-type]

    def test_a_igual_tamano_el_extendido_deja_mas_perimetro(self) -> None:
        """La medicion que le da poder al contraste de forma.

        Si las dos formas dieran el mismo perimetro, tamano y perimetro
        seguirian confundidos y el contraste no separaria nada.
        """
        adyacencia = rejilla(6)
        cortes = {}
        for forma in ("compacto", "extendido"):
            cortes[forma] = float(
                np.mean(
                    [
                        boundary_edges(
                            adyacencia,
                            connected_subgraph(
                                adyacencia, s, 8, shape=forma, rng=np.random.default_rng(s)
                            ),
                        )
                        for s in range(36)
                    ]
                )
            )
        assert cortes["extendido"] > cortes["compacto"]

    @pytest.mark.parametrize("forma", ["compacto", "extendido"])
    def test_componente_mas_chica_que_lo_pedido_es_error(self, forma: str) -> None:
        """No se puede devolver un grupo conexo más grande que su componente.

        El mensaje no depende de la forma: el problema es del grafo, no de
        cómo se lo recorrió.
        """
        a = np.zeros((6, 6))
        a[0, 1] = a[1, 0] = 1.0
        with pytest.raises(ValueError, match="componente conexa de 0 tiene 2 nodos"):
            connected_subgraph(a, 0, 3, shape=forma, rng=np.random.default_rng(1))

    @pytest.mark.parametrize("forma", ["compacto", "extendido"])
    def test_semilla_aislada_es_error(self, forma: str) -> None:
        with pytest.raises(ValueError, match="componente conexa de 3 tiene 1 nodos"):
            connected_subgraph(camino(5) * 0.0, 3, 2, shape=forma, rng=np.random.default_rng(1))

    def test_adyacencia_no_cuadrada_es_error(self) -> None:
        with pytest.raises(ValueError, match="debe ser cuadrada"):
            connected_subgraph(np.zeros((3, 4)), 0, 2, rng=np.random.default_rng(1))

    def test_semilla_fuera_del_grafo_es_error(self) -> None:
        with pytest.raises(ValueError, match="fuera del grafo"):
            connected_subgraph(camino(5), 9, 2, rng=np.random.default_rng(1))


class TestBoundaryEdges:
    def test_grupo_entero_no_tiene_corte(self) -> None:
        """El caso limite: sin complemento no hay frontera."""
        assert boundary_edges(camino(5), (0, 1, 2, 3, 4)) == 0

    def test_un_extremo_del_camino_corta_una_arista(self) -> None:
        assert boundary_edges(camino(5), (0,)) == 1

    def test_un_nodo_interior_corta_dos(self) -> None:
        assert boundary_edges(camino(5), (2,)) == 2

    def test_un_tramo_interior_corta_dos(self) -> None:
        assert boundary_edges(camino(5), (1, 2, 3)) == 2

    def test_no_cuenta_las_aristas_internas(self) -> None:
        """Cuatro nodos en cuadrado dentro de una rejilla de 3x3."""
        assert boundary_edges(rejilla(3), (0, 1, 3, 4)) == 4


class TestIsConnected:
    def test_un_tramo_es_conexo(self) -> None:
        assert is_connected(camino(5), (1, 2, 3))

    def test_dos_tramos_sueltos_no(self) -> None:
        assert not is_connected(camino(5), (0, 1, 3, 4))

    def test_un_solo_nodo_es_conexo(self) -> None:
        assert is_connected(camino(5), (2,))

    def test_el_grupo_vacio_no_es_conexo(self) -> None:
        assert not is_connected(camino(5), ())
