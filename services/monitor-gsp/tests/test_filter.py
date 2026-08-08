"""Tests del Difuminador: propiedades del filtro paso-bajo espectral.

Los grafos de prueba tienen espectro conocido en forma cerrada, así que lo
que se afirma no sale de correr el propio código:

* Camino `P4`: grados 1, 2, 2, 1 — desiguales a propósito, que es lo que
  permite distinguir el núcleo de `L_norm` (`D^(1/2)·1`) de la señal
  constante.
* Estrella `S6`: autovalores `0`, `1` con multiplicidad 4, y `2`. El
  subespacio degenerado de dimensión 4 es el que hace visible cualquier
  dependencia de la base.
* Ciclo `C4`, 2-regular: acá sí el núcleo coincide con la constante,
  porque todos los grados son iguales.

Las cifras del grafo real de los 150 medidores no se verifican acá sino en
`experiments/difuminador-tau/`, que es material de tesis y no un test.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from urbia_monitor_gsp.graph.filter import (
    DEFAULT_TAU,
    _diffuse_published,
    _published_response,
    band_cut_index,
    band_energy,
    diffuse,
    dirichlet_energy,
    low_pass_response,
)
from urbia_monitor_gsp.graph.geo import LocalFrame
from urbia_monitor_gsp.graph.spectral import (
    degenerate_groups,
    degree_vector,
    graph_fourier_basis,
    laplacian,
    normalized_laplacian,
)
from urbia_monitor_gsp.graph.types import (
    BuildStats,
    InvalidFilterParameterError,
    ZoneGraph,
)

_TOL_REDONDEO = 1e-12
"""Holgura para las cotas de la respuesta espectral.

`g(λ)` vale exactamente 1 en λ=0 y baja de ahí, pero `eigh` devuelve el
autovalor nulo como un número del orden de ±1e-16 —en la estrella S6, por
ejemplo, -4,4e-16—, y `exp` de eso queda un ulp por encima de 1. Afirmar
`g ≤ 1` a secas haría fallar el test por una propiedad del redondeo de
`eigh`, no del filtro.
"""


def camino(n: int) -> np.ndarray:
    """Camino de n nodos: grados 1 en los extremos, 2 adentro."""
    A = np.zeros((n, n))
    for i in range(n - 1):
        A[i, i + 1] = A[i + 1, i] = 1.0
    return A


def estrella(n: int) -> np.ndarray:
    """Estrella de n nodos: un centro y n-1 hojas."""
    A = np.zeros((n, n))
    A[0, 1:] = 1.0
    A[1:, 0] = 1.0
    return A


def ciclo(n: int) -> np.ndarray:
    """Ciclo de n nodos, 2-regular."""
    A = np.zeros((n, n))
    for i in range(n):
        A[i, (i + 1) % n] = A[(i + 1) % n, i] = 1.0
    return A


def zona(adjacency: np.ndarray, nombre: str = "prueba") -> ZoneGraph:
    """Arma un `ZoneGraph` a partir de una adyacencia de juguete.

    La geometría se rellena con ceros: el filtro no la mira. Lo que
    importa es que el Laplaciano normalizado y la base de Fourier salgan
    del mismo aparato que usa el constructor real.
    """
    n = adjacency.shape[0]
    l_norm = normalized_laplacian(adjacency)
    valores, vectores = graph_fourier_basis(l_norm)
    grados = degree_vector(adjacency)
    return ZoneGraph(
        zona=nombre,
        device_ids=tuple(f"urbia-tst-mon-{i:04d}" for i in range(n)),
        coords_m=np.zeros((n, 2)),
        frame=LocalFrame(0.0, 0.0, 6_367_000.0, 6_378_000.0),
        distances_m=np.zeros((n, n)),
        adjacency=adjacency,
        degrees=grados,
        laplacian=laplacian(adjacency),
        laplacian_norm=l_norm,
        eigenvalues=valores,
        eigenvectors=vectores,
        stats=BuildStats(
            n_meters=n,
            n_edges=int(adjacency.astype(bool).sum() // 2),
            k_effective=0,
            degree_min=float(grados.min()),
            degree_max=float(grados.max()),
            degree_mean=float(grados.mean()),
            n_components=1,
            lambda_1=float(valores[1]),
            max_edge_length_m=0.0,
        ),
    )


def senal(n: int, semilla: int = 7) -> np.ndarray:
    """Señal de prueba: base 10 kWh, ruido chico y un pico."""
    rng = np.random.default_rng(semilla)
    x = 10.0 + 0.3 * rng.standard_normal(n)
    x[n // 2] += 5.0
    return x


def direccion_del_nucleo(z: ZoneGraph) -> np.ndarray:
    """Núcleo de `L_norm` normalizado: la dirección `D^(1/2)·1`."""
    v = np.sqrt(z.degrees)
    return np.asarray(v / np.linalg.norm(v))


class TestRespuestaEspectral:
    def test_response_vale_uno_en_frecuencia_cero(self) -> None:
        valores, _ = graph_fourier_basis(normalized_laplacian(camino(5)))
        assert low_pass_response(valores, 0.5)[0] == pytest.approx(1.0)

    def test_response_es_decreciente_y_esta_acotada(self) -> None:
        """La cota es `1 + ε` y no `1`: ver `_TOL_REDONDEO`."""
        valores, _ = graph_fourier_basis(normalized_laplacian(estrella(6)))
        g = low_pass_response(valores, 0.7)
        assert np.all(np.diff(g) <= _TOL_REDONDEO)
        assert np.all((g > 0.0) & (g <= 1.0 + _TOL_REDONDEO))

    def test_response_atenua_mas_cuanto_menor_es_tau(self) -> None:
        valores, _ = graph_fourier_basis(normalized_laplacian(estrella(6)))
        assert np.all(
            low_pass_response(valores, 0.1) <= low_pass_response(valores, 1.0) + _TOL_REDONDEO
        )

    def test_response_en_lambda_max_vale_exp_menos_uno_sobre_tau(self) -> None:
        """`g(λmax) = exp(−1/τ)` sin importar el grafo: eso hace τ comparable."""
        for adyacencia in (camino(5), estrella(6), ciclo(4)):
            valores, _ = graph_fourier_basis(normalized_laplacian(adyacencia))
            g = low_pass_response(valores, 0.4)
            assert g[-1] == pytest.approx(math.exp(-1 / 0.4))

    def test_response_con_lambda_max_explicito_usa_ese_normalizador(self) -> None:
        valores = np.array([0.0, 1.0, 2.0])
        g = low_pass_response(valores, 1.0, lambda_max=4.0)
        np.testing.assert_allclose(g, np.exp(-valores / 4.0))

    @pytest.mark.parametrize("tau", [0.0, -1.0, -0.5])
    def test_tau_no_positivo_levanta_error(self, tau: float) -> None:
        with pytest.raises(InvalidFilterParameterError, match="τ debe ser > 0"):
            low_pass_response(np.array([0.0, 1.0]), tau)

    @pytest.mark.parametrize("tau", [float("nan"), float("inf")])
    def test_tau_no_finito_levanta_error(self, tau: float) -> None:
        with pytest.raises(InvalidFilterParameterError, match="finito"):
            low_pass_response(np.array([0.0, 1.0]), tau)

    def test_espectro_vacio_levanta_error(self) -> None:
        with pytest.raises(InvalidFilterParameterError, match="vacío"):
            low_pass_response(np.array([]), 0.5)

    def test_espectro_sin_lambda_max_positivo_levanta_error(self) -> None:
        with pytest.raises(InvalidFilterParameterError, match="λmax"):
            low_pass_response(np.zeros(3), 0.5)

    def test_composicion_de_dos_tau_equivale_a_la_suma_de_inversos(self) -> None:
        """`g(τ₁)·g(τ₂) = g(τ)` con `1/τ = 1/τ₁ + 1/τ₂`: es un semigrupo."""
        valores, _ = graph_fourier_basis(normalized_laplacian(estrella(6)))
        t1, t2 = 0.8, 2.5
        combinado = 1.0 / (1.0 / t1 + 1.0 / t2)
        np.testing.assert_allclose(
            low_pass_response(valores, t1) * low_pass_response(valores, t2),
            low_pass_response(valores, combinado),
            rtol=1e-12,
        )


class TestExponentePositivoDeLaFuente:
    """La formulación impresa en Aristizábal (2022) hace lo contrario."""

    def test_el_exponente_positivo_es_creciente_en_lambda(self) -> None:
        valores, _ = graph_fourier_basis(normalized_laplacian(estrella(6)))
        g = _published_response(valores, 0.7)
        assert np.all(np.diff(g) >= -_TOL_REDONDEO)
        assert np.all(g >= 1.0 - _TOL_REDONDEO)

    def test_el_exponente_positivo_es_el_reciproco_del_negativo(self) -> None:
        valores, _ = graph_fourier_basis(normalized_laplacian(camino(5)))
        np.testing.assert_allclose(
            _published_response(valores, 0.6) * low_pass_response(valores, 0.6),
            np.ones(5),
            rtol=1e-12,
        )

    def test_el_exponente_positivo_desborda_a_infinito_con_tau_chico(self) -> None:
        """No es sólo que amplifique: para τ chico deja de dar un número."""
        valores, _ = graph_fourier_basis(normalized_laplacian(estrella(6)))
        with np.errstate(over="ignore"):
            g = _published_response(valores, 1e-3)
        assert np.isinf(g[-1])

    def test_el_exponente_positivo_aumenta_la_energia_de_dirichlet(self) -> None:
        z = zona(estrella(6))
        x = senal(6)
        assert dirichlet_energy(z, _diffuse_published(z, x, 0.5)) > dirichlet_energy(z, x)


class TestDifuminado:
    def test_tau_grande_tiende_a_la_identidad(self) -> None:
        z = zona(camino(6))
        x = senal(6)
        np.testing.assert_allclose(diffuse(z, x, 1e6), x, rtol=1e-5)

    def test_tau_chico_colapsa_al_nucleo_de_l_norm(self) -> None:
        z = zona(camino(6))
        x_f = diffuse(z, senal(6), 1e-3)
        unitaria = x_f / np.linalg.norm(x_f)
        assert unitaria @ direccion_del_nucleo(z) == pytest.approx(1.0, abs=1e-9)

    def test_el_nucleo_no_es_la_senal_constante_si_los_grados_diferen(self) -> None:
        """La distinción que se lee mal: `D^(1/2)·1`, no la constante.

        En el camino los grados son 1, 2, 2, 2, 2, 1 y el perfil límite es
        proporcional a `√dᵢ`, no plano.
        """
        z = zona(camino(6))
        x_f = diffuse(z, senal(6), 1e-3)
        unitaria = x_f / np.linalg.norm(x_f)
        constante = np.ones(6) / math.sqrt(6)
        assert unitaria @ constante < 0.99
        assert x_f.max() / x_f.min() == pytest.approx(math.sqrt(2.0), rel=1e-6)

    def test_en_un_grafo_regular_el_nucleo_si_es_la_constante(self) -> None:
        """El contraste que explica de dónde viene la confusión."""
        z = zona(ciclo(4))
        x_f = diffuse(z, senal(4), 1e-3)
        np.testing.assert_allclose(x_f, np.full(4, x_f.mean()), rtol=1e-9)

    def test_una_senal_en_el_nucleo_no_cambia(self) -> None:
        z = zona(camino(5))
        x = np.sqrt(z.degrees) * 3.0
        np.testing.assert_allclose(diffuse(z, x, 0.3), x, rtol=1e-12)

    def test_difuminar_dos_veces_equivale_a_difuminar_una_con_tau_compuesto(self) -> None:
        z = zona(estrella(6))
        x = senal(6)
        t1, t2 = 0.9, 3.0
        combinado = 1.0 / (1.0 / t1 + 1.0 / t2)
        np.testing.assert_allclose(
            diffuse(z, diffuse(z, x, t1), t2),
            diffuse(z, x, combinado),
            rtol=1e-11,
        )

    def test_el_operador_es_la_exponencial_matricial_del_laplaciano(self) -> None:
        """`diffuse` calcula `exp(−L_norm/(τ·λmax))·x`, y no algo parecido.

        La serie de Taylor es una implementación independiente de la
        misma cosa: no pasa por la base de Fourier.
        """
        z = zona(estrella(6))
        x = senal(6)
        tau = 0.8
        escala = -1.0 / (tau * float(z.eigenvalues[-1]))

        termino = x.copy()
        serie = x.copy()
        for k in range(1, 60):
            termino = escala * (z.laplacian_norm @ termino) / k
            serie = serie + termino

        np.testing.assert_allclose(diffuse(z, x, tau), serie, rtol=1e-11)

    def test_tau_por_defecto_esta_en_el_rango_estable_medido(self) -> None:
        assert 0.45 <= DEFAULT_TAU <= 2.24

    def test_senal_de_largo_equivocado_levanta_error(self) -> None:
        z = zona(camino(5))
        with pytest.raises(InvalidFilterParameterError, match="5 componentes"):
            diffuse(z, np.ones(4), 0.5)

    def test_senal_bidimensional_levanta_error(self) -> None:
        z = zona(camino(5))
        with pytest.raises(InvalidFilterParameterError, match="vector"):
            diffuse(z, np.ones((5, 2)), 0.5)

    def test_senal_con_nan_levanta_error_nombrando_el_medidor(self) -> None:
        z = zona(camino(5))
        x = senal(5)
        x[2] = np.nan
        with pytest.raises(InvalidFilterParameterError, match="urbia-tst-mon-0002"):
            diffuse(z, x, 0.5)

    def test_senal_con_infinito_levanta_error(self) -> None:
        z = zona(camino(5))
        x = senal(5)
        x[0] = np.inf
        with pytest.raises(InvalidFilterParameterError, match="no finito"):
            diffuse(z, x, 0.5)


class TestEnergiaDeDirichlet:
    def test_las_tres_formas_de_la_energia_coinciden(self) -> None:
        """Forma cuadrática, suma espectral y suma sobre aristas."""
        z = zona(estrella(6))
        x = senal(6)

        cuadratica = dirichlet_energy(z, x)
        espectral = float((z.eigenvalues * (z.eigenvectors.T @ x) ** 2).sum())
        normalizada = x / np.sqrt(z.degrees)
        por_aristas = 0.0
        for i in range(6):
            for j in range(i + 1, 6):
                if z.adjacency[i, j] > 0:
                    por_aristas += z.adjacency[i, j] * (normalizada[i] - normalizada[j]) ** 2

        assert cuadratica == pytest.approx(espectral, rel=1e-10)
        assert cuadratica == pytest.approx(por_aristas, rel=1e-10)

    def test_la_energia_es_no_negativa(self) -> None:
        z = zona(estrella(6))
        assert dirichlet_energy(z, senal(6)) >= 0.0

    def test_la_energia_es_nula_en_el_nucleo(self) -> None:
        z = zona(camino(5))
        assert dirichlet_energy(z, np.sqrt(z.degrees)) == pytest.approx(0.0, abs=1e-14)

    def test_difuminar_baja_la_energia_de_dirichlet(self) -> None:
        for adyacencia in (camino(6), estrella(6), ciclo(4)):
            z = zona(adyacencia)
            x = senal(z.n_meters)
            assert dirichlet_energy(z, diffuse(z, x, 0.5)) < dirichlet_energy(z, x)

    def test_la_energia_retenida_crece_con_tau(self) -> None:
        z = zona(estrella(6))
        x = senal(6)
        energias = [dirichlet_energy(z, diffuse(z, x, t)) for t in (0.1, 0.5, 1.0, 5.0, 50.0)]
        assert energias == sorted(energias)

    def test_senal_de_largo_equivocado_levanta_error(self) -> None:
        with pytest.raises(InvalidFilterParameterError, match="componentes"):
            dirichlet_energy(zona(camino(5)), np.ones(3))


class TestCorteDeBandas:
    def test_el_corte_cae_en_un_borde_de_subespacio(self) -> None:
        """S6 tiene un subespacio de dimensión 4: el corte no lo parte."""
        valores, _ = graph_fourier_basis(normalized_laplacian(estrella(6)))
        corte = band_cut_index(valores)
        bordes = {g[0] for g in degenerate_groups(valores)}
        assert corte in bordes

    def test_un_corte_fijo_en_lambda_max_medios_si_partiria_el_subespacio(self) -> None:
        """Por qué el corte se ajusta en vez de ir fijo, con el caso que lo rompe.

        En S6 el espectro exacto es 0, 1, 1, 1, 1, 2, así que λmax/2 vale
        justo 1: el objetivo cae **encima** del subespacio degenerado. Y
        `eigh` no devuelve los cuatro unos idénticos —el primero sale
        0,9999999999999998 y los otros tres 1,0 exacto—, de modo que
        comparar contra 1,0 manda un miembro del subespacio a la banda
        baja y tres a la alta. El reparto quedaría decidido por el
        redondeo, y con él la energía atribuida a cada banda.
        """
        valores, _ = graph_fourier_basis(normalized_laplacian(estrella(6)))
        grupo_degenerado = max(degenerate_groups(valores), key=len)

        ingenuo = int(np.searchsorted(valores, valores[-1] / 2.0))
        assert ingenuo in grupo_degenerado
        assert ingenuo != grupo_degenerado[0]
        assert valores[ingenuo] - valores[ingenuo - 1] < 1e-15

        assert band_cut_index(valores) == grupo_degenerado[0]

    def test_target_ratio_mueve_el_corte(self) -> None:
        valores, _ = graph_fourier_basis(normalized_laplacian(camino(8)))
        bajo = band_cut_index(valores, 0.2)
        alto = band_cut_index(valores, 0.8)
        assert bajo < alto

    @pytest.mark.parametrize("ratio", [0.0, 1.0, -0.3, 1.5])
    def test_target_ratio_fuera_de_rango_levanta_error(self, ratio: float) -> None:
        valores, _ = graph_fourier_basis(normalized_laplacian(camino(5)))
        with pytest.raises(InvalidFilterParameterError, match="target_ratio"):
            band_cut_index(valores, ratio)

    def test_espectro_de_un_solo_valor_levanta_error(self) -> None:
        with pytest.raises(InvalidFilterParameterError, match="al menos 2"):
            band_cut_index(np.array([1.0]))

    def test_espectro_enteramente_degenerado_levanta_error(self) -> None:
        with pytest.raises(InvalidFilterParameterError, match="único subespacio"):
            band_cut_index(np.ones(4))


class TestRepartoPorBandas:
    def test_las_bandas_suman_la_energia_total(self) -> None:
        z = zona(estrella(6))
        x = senal(6)
        banda = band_energy(z, x)
        assert banda.low + banda.high == pytest.approx(banda.total)
        assert banda.total == pytest.approx(float(x @ x), rel=1e-12)

    def test_difuminar_baja_la_banda_alta(self) -> None:
        z = zona(estrella(6))
        x = senal(6)
        assert band_energy(z, diffuse(z, x, 0.5)).high < band_energy(z, x).high

    def test_difuminar_baja_la_fraccion_de_alta_frecuencia(self) -> None:
        z = zona(estrella(6))
        x = senal(6)
        antes = band_energy(z, x).high_fraction
        despues = band_energy(z, diffuse(z, x, 0.5)).high_fraction
        assert despues < antes

    def test_el_exponente_positivo_sube_la_banda_alta(self) -> None:
        z = zona(estrella(6))
        x = senal(6)
        assert band_energy(z, _diffuse_published(z, x, 0.5)).high > band_energy(z, x).high

    def test_senal_nula_no_divide_por_cero(self) -> None:
        banda = band_energy(zona(camino(5)), np.zeros(5))
        assert banda.total == 0.0
        assert banda.high_fraction == 0.0

    def test_corte_explicito_se_respeta(self) -> None:
        z = zona(camino(6))
        banda = band_energy(z, senal(6), cut_index=2)
        assert banda.cut_index == 2
        assert banda.cut_eigenvalue == pytest.approx(float(z.eigenvalues[2]))

    @pytest.mark.parametrize("corte", [0, 6, 7, -1])
    def test_corte_explicito_fuera_de_rango_levanta_error(self, corte: int) -> None:
        with pytest.raises(InvalidFilterParameterError, match="cut_index"):
            band_energy(zona(camino(6)), senal(6), cut_index=corte)


class TestInvarianciaAPermutacion:
    """El criterio de reproducibilidad que fijó el paso 3, aplicado al filtro.

    `g` depende sólo de λ, así que es constante dentro de cada subespacio
    propio y la rotación arbitraria de la base se cancela. Nada de esto
    depende de que `eigh` haya elegido una base u otra.
    """

    @staticmethod
    def _permutado(adyacencia: np.ndarray, perm: np.ndarray) -> ZoneGraph:
        return zona(adyacencia[np.ix_(perm, perm)])

    def test_la_senal_filtrada_es_invariante(self) -> None:
        rng = np.random.default_rng(11)
        A = estrella(6)
        x = senal(6)
        perm = rng.permutation(6)
        inversa = np.argsort(perm)

        directo = diffuse(zona(A), x, 0.5)
        permutado = diffuse(self._permutado(A, perm), x[perm], 0.5)
        np.testing.assert_allclose(directo, permutado[inversa], atol=1e-13)

    def test_la_energia_de_dirichlet_es_invariante(self) -> None:
        rng = np.random.default_rng(5)
        A = estrella(6)
        x = senal(6)
        perm = rng.permutation(6)

        assert dirichlet_energy(zona(A), x) == pytest.approx(
            dirichlet_energy(self._permutado(A, perm), x[perm]), abs=1e-12
        )

    def test_el_reparto_por_bandas_es_invariante(self) -> None:
        rng = np.random.default_rng(3)
        A = estrella(6)
        x = senal(6)
        perm = rng.permutation(6)

        original = band_energy(zona(A), x)
        permutada = band_energy(self._permutado(A, perm), x[perm])

        assert original.cut_index == permutada.cut_index
        assert original.cut_eigenvalue == pytest.approx(permutada.cut_eigenvalue, abs=1e-13)
        assert original.high == pytest.approx(permutada.high, abs=1e-12)
        assert original.low == pytest.approx(permutada.low, abs=1e-12)

    def test_un_coeficiente_suelto_si_cambia(self) -> None:
        """El contraste que da sentido a los tres tests anteriores.

        Dentro del subespacio degenerado los coeficientes individuales sí
        dependen de la base. Si esto dejara de valer, los tests de
        invariancia estarían pasando por una razón trivial.
        """
        rng = np.random.default_rng(11)
        A = estrella(6)
        x = senal(6)
        perm = rng.permutation(6)

        original = np.abs(zona(A).eigenvectors.T @ x)
        permutado = np.abs(self._permutado(A, perm).eigenvectors.T @ x[perm])
        assert np.abs(original - permutado).max() > 1e-3
