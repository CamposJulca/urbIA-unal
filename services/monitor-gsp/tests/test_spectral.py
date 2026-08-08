"""Tests de las propiedades matemáticas del aparato espectral.

Estas propiedades son las que sostienen todo lo que viene después: si el
Laplaciano no es de suma-fila cero o la base no es ortonormal, cualquier
detector construido encima mide otra cosa.

Los grafos de prueba tienen espectro conocido en forma cerrada, de modo que
los valores esperados no salen de correr el propio código:

* Ciclo `C4`, 2-regular: `L_norm` tiene autovalores `0, 1, 1, 2`.
* Estrella `S_n`, bipartita: autovalores `0`, `1` con multiplicidad `n-2`
  y `2`.
* Grafo completo `K_n`: autovalores `0` y `n/(n-1)` con multiplicidad
  `n-1`.
"""

from __future__ import annotations

import numpy as np
import pytest

from urbia_monitor_gsp.graph.spectral import (
    connected_components,
    degenerate_groups,
    degree_vector,
    eigenvalue_zero_tolerance,
    fiedler_value,
    gft,
    graph_fourier_basis,
    igft,
    laplacian,
    normalized_laplacian,
    zero_multiplicity,
)
from urbia_monitor_gsp.graph.types import InvalidAdjacencyError, ZeroDegreeNodeError


def ciclo(n: int) -> np.ndarray:
    """Ciclo de n nodos, 2-regular."""
    A = np.zeros((n, n))
    for i in range(n):
        A[i, (i + 1) % n] = A[(i + 1) % n, i] = 1.0
    return A


def estrella(n: int) -> np.ndarray:
    """Estrella con un centro y n-1 hojas."""
    A = np.zeros((n, n))
    A[0, 1:] = A[1:, 0] = 1.0
    return A


def completo(n: int) -> np.ndarray:
    """Grafo completo de n nodos."""
    return np.ones((n, n)) - np.eye(n)


def camino(n: int) -> np.ndarray:
    """Camino de n nodos."""
    A = np.zeros((n, n))
    for i in range(n - 1):
        A[i, i + 1] = A[i + 1, i] = 1.0
    return A


def bloque_diagonal(*bloques: np.ndarray) -> np.ndarray:
    """Une varios grafos en uno solo, sin aristas entre ellos."""
    n = sum(b.shape[0] for b in bloques)
    A = np.zeros((n, n))
    offset = 0
    for b in bloques:
        m = b.shape[0]
        A[offset : offset + m, offset : offset + m] = b
        offset += m
    return A


class TestLaplacian:
    def test_laplacian_es_simetrico(self) -> None:
        L = laplacian(estrella(6))
        np.testing.assert_allclose(L, L.T, atol=1e-15)

    @pytest.mark.parametrize(
        "A", [ciclo(6), estrella(7), completo(5), camino(4)], ids=["C6", "S7", "K5", "P4"]
    )
    def test_laplacian_suma_de_filas_es_cero(self, A: np.ndarray) -> None:
        L = laplacian(A)
        np.testing.assert_allclose(L.sum(axis=1), np.zeros(len(A)), atol=1e-13)

    def test_laplacian_diagonal_son_los_grados(self) -> None:
        A = estrella(5)
        np.testing.assert_allclose(np.diag(laplacian(A)), degree_vector(A))

    def test_laplacian_vector_constante_es_autovector_de_cero(self) -> None:
        """En el Laplaciano combinatorio, no en el normalizado."""
        A = camino(5)
        constante = np.ones(5)
        np.testing.assert_allclose(laplacian(A) @ constante, np.zeros(5), atol=1e-13)

    def test_laplacian_admite_nodos_aislados(self) -> None:
        A = bloque_diagonal(camino(3), np.zeros((1, 1)))
        L = laplacian(A)
        np.testing.assert_allclose(L[3], np.zeros(4), atol=1e-15)


class TestNormalizedLaplacian:
    def test_normalized_laplacian_vector_constante_no_es_autovector_de_cero(self) -> None:
        """El autovector de λ=0 en L_norm es D^(1/2)·1, no el constante."""
        A = estrella(5)
        L_norm = normalized_laplacian(A)
        constante = np.ones(5)
        assert np.linalg.norm(L_norm @ constante) > 0.1

        raiz_grados = np.sqrt(degree_vector(A))
        np.testing.assert_allclose(L_norm @ raiz_grados, np.zeros(5), atol=1e-14)

    @pytest.mark.parametrize(
        "A", [ciclo(8), estrella(7), completo(6), camino(5)], ids=["C8", "S7", "K6", "P5"]
    )
    def test_normalized_laplacian_espectro_dentro_de_cero_y_dos(self, A: np.ndarray) -> None:
        valores, _ = graph_fourier_basis(normalized_laplacian(A))
        tol = eigenvalue_zero_tolerance(len(A))
        assert valores.min() >= -tol
        assert valores.max() <= 2.0 + tol

    def test_normalized_laplacian_ciclo_tiene_espectro_conocido(self) -> None:
        """C4 es 2-regular: L_norm = L/2 y su espectro es 0, 1, 1, 2."""
        valores, _ = graph_fourier_basis(normalized_laplacian(ciclo(4)))
        np.testing.assert_allclose(valores, [0.0, 1.0, 1.0, 2.0], atol=1e-14)

    def test_normalized_laplacian_estrella_tiene_espectro_conocido(self) -> None:
        """La estrella es bipartita: alcanza el máximo teórico λ = 2."""
        valores, _ = graph_fourier_basis(normalized_laplacian(estrella(5)))
        np.testing.assert_allclose(valores, [0.0, 1.0, 1.0, 1.0, 2.0], atol=1e-14)

    def test_normalized_laplacian_completo_tiene_espectro_conocido(self) -> None:
        """K_n: autovalor 0 y n/(n-1) con multiplicidad n-1."""
        n = 5
        valores, _ = graph_fourier_basis(normalized_laplacian(completo(n)))
        esperado = [0.0] + [n / (n - 1)] * (n - 1)
        np.testing.assert_allclose(valores, esperado, atol=1e-14)

    def test_normalized_laplacian_nodo_de_grado_cero_levanta_error(self) -> None:
        """Ni NaN ni infinito silencioso: error explícito con el culpable."""
        A = bloque_diagonal(camino(3), np.zeros((1, 1)))
        with pytest.raises(ZeroDegreeNodeError) as exc:
            normalized_laplacian(A)
        assert exc.value.indices == (3,)
        assert "grado cero" in str(exc.value)

    def test_normalized_laplacian_grafo_sin_aristas_levanta_error(self) -> None:
        with pytest.raises(ZeroDegreeNodeError) as exc:
            normalized_laplacian(np.zeros((3, 3)))
        assert exc.value.indices == (0, 1, 2)


class TestFourierBasis:
    @pytest.mark.parametrize(
        "A", [ciclo(8), estrella(7), completo(6), camino(5)], ids=["C8", "S7", "K6", "P5"]
    )
    def test_graph_fourier_basis_es_ortonormal(self, A: np.ndarray) -> None:
        _, U = graph_fourier_basis(normalized_laplacian(A))
        np.testing.assert_allclose(U.T @ U, np.eye(len(A)), atol=1e-13)
        np.testing.assert_allclose(U @ U.T, np.eye(len(A)), atol=1e-13)

    def test_graph_fourier_basis_autovalores_en_orden_ascendente(self) -> None:
        valores, _ = graph_fourier_basis(normalized_laplacian(camino(7)))
        assert np.all(np.diff(valores) >= 0)

    def test_graph_fourier_basis_reconstruye_la_matriz(self) -> None:
        """U · diag(λ) · Uᵀ debe devolver el Laplaciano original."""
        L_norm = normalized_laplacian(camino(6))
        valores, U = graph_fourier_basis(L_norm)
        np.testing.assert_allclose(U @ np.diag(valores) @ U.T, L_norm, atol=1e-13)

    def test_graph_fourier_basis_signo_es_determinista(self) -> None:
        """La convención debe dar lo mismo partiendo de U o de -U."""
        L_norm = normalized_laplacian(camino(6))
        valores, U = graph_fourier_basis(L_norm)
        _, U_otra_vez = graph_fourier_basis(L_norm)
        np.testing.assert_array_equal(U, U_otra_vez)

        # La componente dominante de cada modo queda positiva.
        dominantes = np.argmax(np.abs(U), axis=0)
        assert np.all(U[dominantes, np.arange(U.shape[1])] > 0)

    def test_graph_fourier_basis_matriz_no_simetrica_levanta_error(self) -> None:
        with pytest.raises(InvalidAdjacencyError, match="simétrico"):
            graph_fourier_basis(np.array([[0.0, 1.0], [2.0, 0.0]]))

    def test_graph_fourier_basis_matriz_no_cuadrada_levanta_error(self) -> None:
        with pytest.raises(InvalidAdjacencyError, match="cuadrado"):
            graph_fourier_basis(np.zeros((2, 3)))


class TestGft:
    @pytest.mark.parametrize(
        "A", [ciclo(8), estrella(7), completo(6), camino(5)], ids=["C8", "S7", "K6", "P5"]
    )
    def test_igft_de_gft_recupera_la_senal(self, A: np.ndarray) -> None:
        rng = np.random.default_rng(42)
        x = 10.0 + 0.3 * rng.standard_normal(len(A))
        _, U = graph_fourier_basis(normalized_laplacian(A))
        np.testing.assert_allclose(igft(gft(x, U), U), x, atol=1e-12)

    def test_gft_conserva_la_energia(self) -> None:
        """Parseval: una base ortonormal no crea ni destruye energía."""
        rng = np.random.default_rng(7)
        x = rng.standard_normal(9)
        _, U = graph_fourier_basis(normalized_laplacian(ciclo(9)))
        assert float((gft(x, U) ** 2).sum()) == pytest.approx(float((x**2).sum()))

    def test_gft_de_senal_constante_concentra_energia_en_el_modo_cero(self) -> None:
        """En un grafo regular el modo λ=0 es el constante normalizado."""
        A = ciclo(10)
        _, U = graph_fourier_basis(normalized_laplacian(A))
        x_hat = gft(np.full(10, 5.0), U)
        assert abs(x_hat[0]) > 15.0
        np.testing.assert_allclose(x_hat[1:], np.zeros(9), atol=1e-13)

    def test_gft_dimension_incompatible_levanta_error(self) -> None:
        _, U = graph_fourier_basis(normalized_laplacian(ciclo(5)))
        with pytest.raises(ValueError, match="5 componentes"):
            gft(np.ones(3), U)

    def test_igft_dimension_incompatible_levanta_error(self) -> None:
        _, U = graph_fourier_basis(normalized_laplacian(ciclo(5)))
        with pytest.raises(ValueError, match="5 componentes"):
            igft(np.ones(3), U)


class TestComponentesConexas:
    @pytest.mark.parametrize(
        ("bloques", "esperadas"),
        [
            ((camino(4),), 1),
            ((camino(3), ciclo(4)), 2),
            ((camino(3), ciclo(4), completo(3)), 3),
            ((camino(2), camino(2), camino(2), camino(2), camino(2), camino(2)), 6),
        ],
        ids=["1-componente", "2-componentes", "3-componentes", "6-zonas"],
    )
    def test_multiplicidad_de_cero_es_el_numero_de_componentes(
        self, bloques: tuple[np.ndarray, ...], esperadas: int
    ) -> None:
        """La propiedad que sostiene la lectura de los seis subgrafos zonales.

        El conteo por recorrido en anchura es independiente del espectro, así
        que la comparación no es circular.
        """
        A = bloque_diagonal(*bloques)
        valores, _ = graph_fourier_basis(normalized_laplacian(A))

        n_bfs, _ = connected_components(A)
        assert n_bfs == esperadas
        assert zero_multiplicity(valores) == esperadas

    def test_connected_components_etiqueta_cada_nodo_con_su_bloque(self) -> None:
        n_comp, etiquetas = connected_components(bloque_diagonal(camino(2), ciclo(3)))
        assert n_comp == 2
        np.testing.assert_array_equal(etiquetas, [0, 0, 1, 1, 1])

    def test_connected_components_grafo_sin_aristas_da_un_nodo_por_componente(self) -> None:
        n_comp, _ = connected_components(np.zeros((4, 4)))
        assert n_comp == 4


class TestToleranciaDeCero:
    def test_eigenvalue_zero_tolerance_escala_con_la_dimension(self) -> None:
        assert eigenvalue_zero_tolerance(30) > eigenvalue_zero_tolerance(20)

    def test_eigenvalue_zero_tolerance_dimension_invalida_levanta_error(self) -> None:
        with pytest.raises(ValueError, match="n debe ser positivo"):
            eigenvalue_zero_tolerance(0)

    def test_eigenvalue_zero_tolerance_separa_ruido_de_fiedler_por_ordenes(self) -> None:
        """El umbral tiene margen de sobra: no es un 1e-12 elegido a ojo.

        Sobre un grafo del tamaño de una zona, el cero numérico que devuelve
        `eigh` queda muy por debajo de la tolerancia, y ésta muy por debajo
        del primer autovalor no nulo.
        """
        A = ciclo(25)
        valores, _ = graph_fourier_basis(normalized_laplacian(A))
        tol = eigenvalue_zero_tolerance(len(A), float(valores.max()))

        assert abs(valores[0]) < tol / 10
        assert fiedler_value(valores) > tol * 1e9

    def test_fiedler_value_es_el_primer_autovalor_no_nulo(self) -> None:
        valores, _ = graph_fourier_basis(normalized_laplacian(ciclo(4)))
        assert fiedler_value(valores) == pytest.approx(1.0)

    def test_fiedler_value_grafo_desconectado_ignora_los_ceros(self) -> None:
        A = bloque_diagonal(ciclo(4), ciclo(4))
        valores, _ = graph_fourier_basis(normalized_laplacian(A))
        assert zero_multiplicity(valores) == 2
        assert fiedler_value(valores) == pytest.approx(1.0)

    def test_fiedler_value_sin_autovalores_no_nulos_devuelve_cero(self) -> None:
        assert fiedler_value(np.zeros(3)) == 0.0


class TestDegeneracion:
    def test_degenerate_groups_cubre_todos_los_indices(self) -> None:
        valores, _ = graph_fourier_basis(normalized_laplacian(estrella(6)))
        grupos = degenerate_groups(valores)
        assert sorted(i for g in grupos for i in g) == list(range(6))

    def test_degenerate_groups_detecta_el_subespacio_de_la_estrella(self) -> None:
        """S6: espectro 0, 1, 1, 1, 1, 2 — un subespacio de dimensión 4."""
        valores, _ = graph_fourier_basis(normalized_laplacian(estrella(6)))
        grupos = degenerate_groups(valores)
        assert [len(g) for g in grupos] == [1, 4, 1]

    def test_degenerate_groups_sin_repetidos_da_grupos_unitarios(self) -> None:
        valores, _ = graph_fourier_basis(normalized_laplacian(camino(5)))
        assert all(len(g) == 1 for g in degenerate_groups(valores))

    def test_degenerate_groups_espectro_vacio_no_falla(self) -> None:
        assert degenerate_groups(np.array([])) == ()

    def test_nodos_gemelos_producen_autovalor_uno_mas_uno_sobre_grado(self) -> None:
        """La degeneración de los grafos AMI reales tiene esta forma exacta.

        Dos nodos adyacentes con la misma vecindad cerrada y grado d
        producen el autovalor 1 + 1/d. Con k-NN k=4 sobre los 150 medidores
        reales esto da λ=1,25 repetido: multiplicidad 6 en palermo, 3 en
        centro, 2 en palogrande y en universitario.
        """
        # Triángulo con dos nodos gemelos colgando del mismo vecino.
        A = np.zeros((4, 4))
        A[0, 1] = A[1, 0] = 1.0
        A[0, 2] = A[2, 0] = 1.0
        A[0, 3] = A[3, 0] = 1.0
        A[2, 3] = A[3, 2] = 1.0  # 2 y 3 son gemelos: vecindad {0} y entre sí
        grado = 2.0
        valores, _ = graph_fourier_basis(normalized_laplacian(A))
        assert np.isclose(valores, 1 + 1 / grado).any()

    def test_energia_por_subespacio_es_invariante_a_la_permutacion(self) -> None:
        """Lo que define el criterio de reproducibilidad del monitor.

        Permutar el orden de los nodos puede rotar la base dentro de un
        subespacio degenerado. La energía agregada del subespacio no cambia;
        el coeficiente de un modo suelto sí puede cambiar.
        """
        rng = np.random.default_rng(11)
        A = estrella(6)  # espectro 0, 1, 1, 1, 1, 2: subespacio de dimensión 4
        x = 10.0 + 0.3 * rng.standard_normal(6)

        perm = rng.permutation(6)
        A_perm = A[np.ix_(perm, perm)]

        valores, U = graph_fourier_basis(normalized_laplacian(A))
        valores_perm, U_perm = graph_fourier_basis(normalized_laplacian(A_perm))
        np.testing.assert_allclose(valores, valores_perm, atol=1e-13)

        def energia_por_subespacio(vals: np.ndarray, x_hat: np.ndarray) -> list[float]:
            return [float((x_hat[list(g)] ** 2).sum()) for g in degenerate_groups(vals)]

        original = energia_por_subespacio(valores, gft(x, U))
        permutada = energia_por_subespacio(valores_perm, gft(x[perm], U_perm))
        np.testing.assert_allclose(original, permutada, atol=1e-10)

    def test_filtro_pasaaltos_es_invariante_a_la_permutacion(self) -> None:
        """El detector que E6 dejó como bueno no depende de la base.

        `(L_norm · x)` se calcula sin pasar por los autovectores, así que la
        arbitrariedad de la base en subespacios degenerados no lo toca.
        """
        rng = np.random.default_rng(3)
        A = estrella(6)
        x = 10.0 + 0.3 * rng.standard_normal(6)
        perm = rng.permutation(6)
        inversa = np.argsort(perm)

        directo = normalized_laplacian(A) @ x
        permutado = normalized_laplacian(A[np.ix_(perm, perm)]) @ x[perm]
        np.testing.assert_allclose(directo, permutado[inversa], atol=1e-13)


class TestValidacionDeAdyacencia:
    def test_adyacencia_no_cuadrada_levanta_error(self) -> None:
        with pytest.raises(InvalidAdjacencyError, match="cuadrada"):
            laplacian(np.zeros((2, 3)))

    def test_adyacencia_asimetrica_levanta_error(self) -> None:
        with pytest.raises(InvalidAdjacencyError, match="simétrica"):
            laplacian(np.array([[0.0, 1.0], [0.0, 0.0]]))

    def test_adyacencia_con_pesos_negativos_levanta_error(self) -> None:
        with pytest.raises(InvalidAdjacencyError, match="negativos"):
            laplacian(np.array([[0.0, -1.0], [-1.0, 0.0]]))

    def test_adyacencia_con_lazo_levanta_error(self) -> None:
        with pytest.raises(InvalidAdjacencyError, match="diagonal nula"):
            laplacian(np.array([[1.0, 1.0], [1.0, 0.0]]))

    def test_degree_vector_suma_los_pesos_incidentes(self) -> None:
        A = np.array([[0.0, 0.5, 0.25], [0.5, 0.0, 0.0], [0.25, 0.0, 0.0]])
        np.testing.assert_allclose(degree_vector(A), [0.75, 0.5, 0.25])
