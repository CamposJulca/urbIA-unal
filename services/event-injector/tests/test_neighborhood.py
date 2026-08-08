"""Tests del vecindario: qué nodos abarca un evento."""

from __future__ import annotations

import numpy as np
import pytest
from urbia_monitor_gsp.graph import AmiGraph, ZoneGraph

from urbia_events import k_hop, neighborhood_sizes


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
