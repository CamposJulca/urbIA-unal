"""Tests del detector de eventos colectivos."""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from urbia_monitor_gsp.detector import (
    CollectiveScanDetector,
    ConfusionMatrix,
    DetectorConfig,
    DetectorError,
    candidate_balls,
    confusion_matrix,
    contrasts,
    k_hop_indices,
)
from urbia_monitor_gsp.graph.builder import build_ami_graph, build_zone_graph
from urbia_monitor_gsp.graph.types import GraphConfig, MeterNode, ZoneGraph

SEMILLA = 20260808
SIGMA = 4.4012
"""σ espacial del voltaje, del perfil medido sobre ami_telemetry."""


def rejilla(zona: str, filas: int, columnas: int) -> list[MeterNode]:
    """Medidores en rejilla regular, de geometría predecible."""
    return [
        MeterNode(
            device_id=f"urbia-cen-mon-{f * columnas + c:04d}",
            zona=zona,
            lat=5.06 + f * 0.001,
            lon=-75.51 + c * 0.001,
        )
        for f in range(filas)
        for c in range(columnas)
    ]


@pytest.fixture(scope="module")
def zona_rejilla() -> ZoneGraph:
    return build_zone_graph(rejilla("centro", 6, 6), GraphConfig(k=4))


@pytest.fixture(scope="module")
def zona_real(manizales: list[MeterNode]) -> ZoneGraph:
    return build_ami_graph(manizales, GraphConfig()).zones["centro"]


class TestKHopIndices:
    def test_profundidad_cero_es_la_semilla(self, zona_rejilla: ZoneGraph) -> None:
        assert k_hop_indices(zona_rejilla.adjacency, 7, 0) == (7,)

    def test_incluye_a_los_vecinos_directos(self, zona_rejilla: ZoneGraph) -> None:
        vecinos = set(np.flatnonzero(zona_rejilla.adjacency[7] > 0).tolist())
        assert set(k_hop_indices(zona_rejilla.adjacency, 7, 1)) == vecinos | {7}

    def test_crece_con_la_profundidad(self, zona_rejilla: ZoneGraph) -> None:
        tamanos = [len(k_hop_indices(zona_rejilla.adjacency, 7, d)) for d in range(4)]
        assert tamanos == sorted(tamanos)
        assert tamanos[0] < tamanos[-1]

    def test_el_resultado_viene_ordenado(self, zona_rejilla: ZoneGraph) -> None:
        nodos = k_hop_indices(zona_rejilla.adjacency, 3, 2)
        assert list(nodos) == sorted(nodos)


class TestCandidateBalls:
    def test_una_fila_por_bola_distinta(self, zona_rejilla: ZoneGraph) -> None:
        mascaras, meta = candidate_balls(zona_rejilla, (1,))
        assert mascaras.shape == (len(meta), zona_rejilla.n_meters)

    def test_descarta_las_bolas_que_cubren_toda_la_zona(self, zona_rejilla: ZoneGraph) -> None:
        """Sin complemento no hay contraste, y un grupo total es modo común."""
        mascaras, _ = candidate_balls(zona_rejilla, (1, 2, 3, 4, 5))
        assert np.all(mascaras.sum(axis=1) < zona_rejilla.n_meters)

    def test_deduplica_bolas_identicas_entre_radios(self, zona_rejilla: ZoneGraph) -> None:
        mascaras, _ = candidate_balls(zona_rejilla, (1, 1, 1))
        solo_una_vez, _ = candidate_balls(zona_rejilla, (1,))
        assert mascaras.shape == solo_una_vez.shape

    def test_varios_radios_dan_mas_candidatos_que_uno(self, zona_rejilla: ZoneGraph) -> None:
        una, _ = candidate_balls(zona_rejilla, (1,))
        dos, _ = candidate_balls(zona_rejilla, (1, 2))
        assert dos.shape[0] > una.shape[0]

    def test_un_grafo_sin_bolas_validas_levanta_error(self) -> None:
        """Con 3 nodos y k=2 toda bola de radio 1 cubre la zona."""
        zona = build_zone_graph(rejilla("centro", 1, 3), GraphConfig(k=2))
        with pytest.raises(DetectorError, match="ninguna bola candidata"):
            candidate_balls(zona, (1,))


class TestContrastes:
    def test_es_invariante_a_sumar_una_constante(self, zona_rejilla: ZoneGraph) -> None:
        """El hecho que sostiene no centrar la señal en esta ruta.

        Las dos medias se corren igual y la diferencia no cambia. Por eso
        el nivel de 220 V, que arruina cualquier medida de rugosidad basada
        en L_norm, acá se cancela solo.
        """
        mascaras, _ = candidate_balls(zona_rejilla, (1,))
        rng = np.random.default_rng(SEMILLA)
        x = rng.normal(0.0, SIGMA, size=zona_rejilla.n_meters)
        np.testing.assert_allclose(
            contrasts(x, mascaras, SIGMA),
            contrasts(x + 220.0, mascaras, SIGMA),
            atol=1e-10,
        )

    def test_una_senal_plana_da_contraste_nulo(self, zona_rejilla: ZoneGraph) -> None:
        mascaras, _ = candidate_balls(zona_rejilla, (1,))
        plana = np.full(zona_rejilla.n_meters, 220.0)
        np.testing.assert_allclose(contrasts(plana, mascaras, SIGMA), 0.0, atol=1e-10)

    def test_crece_con_la_magnitud_de_la_desviacion(self, zona_rejilla: ZoneGraph) -> None:
        mascaras, meta = candidate_balls(zona_rejilla, (1,))
        grupo = mascaras[0] > 0
        chico, grande = np.zeros(zona_rejilla.n_meters), np.zeros(zona_rejilla.n_meters)
        chico[grupo] = SIGMA
        grande[grupo] = 3 * SIGMA
        assert contrasts(grande, mascaras, SIGMA)[0, 0] > contrasts(chico, mascaras, SIGMA)[0, 0]
        del meta

    def test_el_maximo_cae_en_el_grupo_desviado(self, zona_rejilla: ZoneGraph) -> None:
        mascaras, _ = candidate_balls(zona_rejilla, (1,))
        objetivo = 5
        x = np.zeros(zona_rejilla.n_meters)
        x[mascaras[objetivo] > 0] = 4 * SIGMA
        assert int(contrasts(x, mascaras, SIGMA)[0].argmax()) == objetivo

    def test_sigma_no_positiva_levanta_error(self, zona_rejilla: ZoneGraph) -> None:
        mascaras, _ = candidate_balls(zona_rejilla, (1,))
        with pytest.raises(DetectorError, match="sigma_eff"):
            contrasts(np.zeros(zona_rejilla.n_meters), mascaras, 0.0)

    def test_senal_de_largo_equivocado_levanta_error(self, zona_rejilla: ZoneGraph) -> None:
        mascaras, _ = candidate_balls(zona_rejilla, (1,))
        with pytest.raises(DetectorError, match="nodos"):
            contrasts(np.zeros(3), mascaras, SIGMA)


class TestConfig:
    @pytest.mark.parametrize(
        ("campo", "valor"),
        [
            ("window", 0),
            ("step", 0),
            ("fpr_target", 0.0),
            ("fpr_target", 1.0),
            ("prefilter_tau", 0.0),
            ("calibration_samples", 10),
        ],
    )
    def test_parametros_invalidos_levantan_error(self, campo: str, valor: float) -> None:
        argumentos: dict[str, Any] = {campo: valor}
        with pytest.raises(DetectorError):
            DetectorConfig(**argumentos)

    def test_radios_vacios_levantan_error(self) -> None:
        with pytest.raises(DetectorError, match="al menos un radio"):
            DetectorConfig(scan_radii=())

    def test_el_defecto_de_la_ventana_es_treinta_y_dos(self) -> None:
        """Punto de operación declarado, no constante enterrada."""
        assert DetectorConfig().window == 32

    def test_la_proyeccion_viene_apagada(self) -> None:
        """Medido: encenderla cuesta entre 40 y 77 puntos de detección."""
        assert DetectorConfig().project_out_kernel is False

    def test_sin_step_las_ventanas_no_se_solapan(self) -> None:
        assert DetectorConfig(window=8).effective_step == 8


class TestDetector:
    def test_sin_calibrar_no_detecta(self, zona_rejilla: ZoneGraph) -> None:
        detector = CollectiveScanDetector(zona_rejilla, SIGMA, DetectorConfig(window=4))
        with pytest.raises(DetectorError, match="no está calibrado"):
            detector.detect(np.zeros((4, zona_rejilla.n_meters)))

    def test_la_calibracion_es_reproducible(self, zona_rejilla: ZoneGraph) -> None:
        config = DetectorConfig(window=4, calibration_samples=300)
        una = CollectiveScanDetector(zona_rejilla, SIGMA, config).calibrate(7)
        otra = CollectiveScanDetector(zona_rejilla, SIGMA, config).calibrate(7)
        assert una == otra

    def test_el_fpr_empirico_se_acerca_al_objetivo(self, zona_rejilla: ZoneGraph) -> None:
        config = DetectorConfig(window=8, fpr_target=0.05, calibration_samples=1500)
        detector = CollectiveScanDetector(zona_rejilla, SIGMA, config)
        detector.calibrate(SEMILLA)

        rng = np.random.default_rng(4242)
        marcadas = sum(
            detector.detect(rng.normal(220.0, SIGMA, size=(8, zona_rejilla.n_meters)))[0].detected
            for _ in range(400)
        )
        assert 0.02 <= marcadas / 400 <= 0.10

    def test_detecta_una_desviacion_colectiva_grande(self, zona_rejilla: ZoneGraph) -> None:
        config = DetectorConfig(window=4, calibration_samples=400)
        detector = CollectiveScanDetector(zona_rejilla, SIGMA, config)
        detector.calibrate(SEMILLA)

        rng = np.random.default_rng(1)
        senal = rng.normal(220.0, SIGMA, size=(4, zona_rejilla.n_meters))
        grupo = k_hop_indices(zona_rejilla.adjacency, 14, 1)
        senal[:, list(grupo)] += 4 * SIGMA

        deteccion = detector.detect(senal)[0]
        assert deteccion.detected
        assert set(deteccion.node_indices) & set(grupo)

    def test_reporta_los_nodos_de_la_bola_ganadora(self, zona_rejilla: ZoneGraph) -> None:
        """Sin esto no hay matriz de confusión por nodo."""
        config = DetectorConfig(window=4, scan_radii=(1,), calibration_samples=400)
        detector = CollectiveScanDetector(zona_rejilla, SIGMA, config)
        detector.calibrate(SEMILLA)

        senal = np.full((4, zona_rejilla.n_meters), 220.0)
        grupo = k_hop_indices(zona_rejilla.adjacency, 14, 1)
        senal[:, list(grupo)] += 6 * SIGMA

        deteccion = detector.detect(senal)[0]
        assert deteccion.node_indices == grupo
        assert deteccion.seed_device_id == zona_rejilla.device_ids[14]
        assert deteccion.radius == 1
        assert len(deteccion.device_ids) == len(grupo)

    def test_sin_deteccion_no_reporta_nodos(self, zona_rejilla: ZoneGraph) -> None:
        """Marcar nodos sin haber detectado ensuciaría la confusión."""
        config = DetectorConfig(window=4, calibration_samples=400)
        detector = CollectiveScanDetector(zona_rejilla, SIGMA, config)
        detector.calibrate(SEMILLA)
        deteccion = detector.detect(np.full((4, zona_rejilla.n_meters), 220.0))[0]
        assert not deteccion.detected
        assert deteccion.node_indices == ()
        assert deteccion.seed_device_id is None

    def test_las_ventanas_cubren_la_senal_sin_solaparse(self, zona_rejilla: ZoneGraph) -> None:
        config = DetectorConfig(window=4, calibration_samples=200)
        detector = CollectiveScanDetector(zona_rejilla, SIGMA, config)
        detector.calibrate(SEMILLA)
        detecciones = detector.detect(np.full((12, zona_rejilla.n_meters), 220.0))
        assert [(d.window_start, d.window_end) for d in detecciones] == [
            (0, 4),
            (4, 8),
            (8, 12),
        ]

    def test_step_menor_que_la_ventana_las_solapa(self, zona_rejilla: ZoneGraph) -> None:
        config = DetectorConfig(window=4, step=2, calibration_samples=200)
        detector = CollectiveScanDetector(zona_rejilla, SIGMA, config)
        detector.calibrate(SEMILLA)
        detecciones = detector.detect(np.full((8, zona_rejilla.n_meters), 220.0))
        assert [d.window_start for d in detecciones] == [0, 2, 4]

    def test_una_senal_mas_corta_que_la_ventana_levanta_error(
        self, zona_rejilla: ZoneGraph
    ) -> None:
        config = DetectorConfig(window=8, calibration_samples=200)
        detector = CollectiveScanDetector(zona_rejilla, SIGMA, config)
        detector.calibrate(SEMILLA)
        with pytest.raises(DetectorError, match="no alcanza"):
            detector.detect(np.zeros((3, zona_rejilla.n_meters)))

    def test_una_senal_con_nan_levanta_error(self, zona_rejilla: ZoneGraph) -> None:
        config = DetectorConfig(window=4, calibration_samples=200)
        detector = CollectiveScanDetector(zona_rejilla, SIGMA, config)
        detector.calibrate(SEMILLA)
        senal = np.full((4, zona_rejilla.n_meters), 220.0)
        senal[0, 0] = np.nan
        with pytest.raises(DetectorError, match="no finitos"):
            detector.detect(senal)

    def test_sigma_no_positiva_levanta_error(self, zona_rejilla: ZoneGraph) -> None:
        with pytest.raises(DetectorError, match="sigma_spatial"):
            CollectiveScanDetector(zona_rejilla, 0.0)

    def test_la_mascara_por_nodo_cubre_la_ventana_detectada(self, zona_rejilla: ZoneGraph) -> None:
        config = DetectorConfig(window=4, scan_radii=(1,), calibration_samples=400)
        detector = CollectiveScanDetector(zona_rejilla, SIGMA, config)
        detector.calibrate(SEMILLA)

        senal = np.full((8, zona_rejilla.n_meters), 220.0)
        grupo = k_hop_indices(zona_rejilla.adjacency, 14, 1)
        senal[4:, list(grupo)] += 6 * SIGMA

        mascara = detector.node_mask(detector.detect(senal), 8)
        assert mascara.shape == (8, zona_rejilla.n_meters)
        assert not mascara[:4].any()
        assert mascara[4:, list(grupo)].all()

    def test_el_prefiltro_no_rompe_la_deteccion(self, zona_rejilla: ZoneGraph) -> None:
        """Si ayuda o estorba lo mide el experimento; acá sólo que corre."""
        config = DetectorConfig(window=4, prefilter_tau=0.5, calibration_samples=400)
        detector = CollectiveScanDetector(zona_rejilla, SIGMA, config)
        detector.calibrate(SEMILLA)
        senal = np.full((4, zona_rejilla.n_meters), 220.0)
        senal[:, list(k_hop_indices(zona_rejilla.adjacency, 14, 1))] += 8 * SIGMA
        assert detector.detect(senal)[0].detected

    def test_la_deteccion_es_serializable(self, zona_rejilla: ZoneGraph) -> None:
        import json

        config = DetectorConfig(window=4, calibration_samples=200)
        detector = CollectiveScanDetector(zona_rejilla, SIGMA, config)
        detector.calibrate(SEMILLA)
        deteccion = detector.detect(np.full((4, zona_rejilla.n_meters), 220.0))[0]
        assert json.loads(json.dumps(deteccion.to_dict()))["zona"] == "centro"


class TestConfusionMatrix:
    def test_cuenta_los_cuatro_casos(self) -> None:
        predicho = np.array([True, True, False, False])
        verdadero = np.array([True, False, True, False])
        m = confusion_matrix(predicho, verdadero)
        assert (m.true_positive, m.false_positive, m.false_negative, m.true_negative) == (
            1,
            1,
            1,
            1,
        )

    def test_las_tasas_derivadas(self) -> None:
        m = ConfusionMatrix(true_positive=8, false_positive=2, false_negative=2, true_negative=88)
        assert m.recall == pytest.approx(0.8)
        assert m.precision == pytest.approx(0.8)
        assert m.f1 == pytest.approx(0.8)
        assert m.false_positive_rate == pytest.approx(2 / 90)
        assert m.total == 100

    def test_sin_positivos_el_recall_es_cero_y_no_divide_por_cero(self) -> None:
        m = ConfusionMatrix(true_positive=0, false_positive=0, false_negative=0, true_negative=10)
        assert m.recall == 0.0
        assert m.precision == 0.0
        assert m.f1 == 0.0

    def test_formas_distintas_levantan_error(self) -> None:
        with pytest.raises(DetectorError, match="misma forma"):
            confusion_matrix(np.zeros(3, dtype=bool), np.zeros(4, dtype=bool))


class TestRegresionContraLosExperimentos:
    """Ata el módulo a las cifras que justificaron su diseño."""

    def test_el_escaneo_supera_al_umbral_en_un_evento_colectivo(self, zona_real: ZoneGraph) -> None:
        """La afirmación central, sobre la topología real.

        Reproduce el punto de operación medido en
        `experiments/firma-espectral/`: evento colectivo a profundidad 2 y
        1σ, un instante, 1 % de falsos positivos. Allí el escaneo detectó
        el 18,9 % y el umbral por medidor el 6,7 %.
        """
        n = zona_real.n_meters
        mascaras, _ = candidate_balls(zona_real, (1,))
        rng = np.random.default_rng(SEMILLA)
        limpio = rng.normal(220.0, SIGMA, size=(600, n))

        grupos = [k_hop_indices(zona_real.adjacency, j, 2) for j in range(n)]
        con_evento = limpio.copy()
        for i in range(600):
            con_evento[i, list(grupos[i % n])] += SIGMA

        escaneo_neg = contrasts(limpio, mascaras, SIGMA).max(axis=1)
        escaneo_pos = contrasts(con_evento, mascaras, SIGMA).max(axis=1)
        umbral_neg = np.abs(limpio - 220.0).max(axis=1) / SIGMA
        umbral_pos = np.abs(con_evento - 220.0).max(axis=1) / SIGMA

        tasa_escaneo = float((escaneo_pos > np.quantile(escaneo_neg, 0.99)).mean())
        tasa_umbral = float((umbral_pos > np.quantile(umbral_neg, 0.99)).mean())

        assert tasa_escaneo > tasa_umbral
        assert tasa_escaneo > 0.10

    def test_integrar_la_ventana_mejora_la_deteccion(self, zona_real: ZoneGraph) -> None:
        """`√N`: el efecto que justifica el punto de operación."""
        n = zona_real.n_meters
        mascaras, _ = candidate_balls(zona_real, (1,))
        grupo = list(k_hop_indices(zona_real.adjacency, 0, 2))
        rng = np.random.default_rng(SEMILLA)

        tasas = []
        for ventana in (1, 5):
            limpio = rng.normal(220.0, SIGMA, size=(400, ventana, n)).mean(axis=1)
            con_evento = limpio.copy()
            con_evento[:, grupo] += SIGMA
            sigma_eff = SIGMA / np.sqrt(ventana)
            neg = contrasts(limpio, mascaras, sigma_eff).max(axis=1)
            pos = contrasts(con_evento, mascaras, sigma_eff).max(axis=1)
            tasas.append(float((pos > np.quantile(neg, 0.99)).mean()))

        assert tasas[1] > tasas[0] + 0.30

    def test_la_proyeccion_fuera_del_nucleo_degrada(self, zona_real: ZoneGraph) -> None:
        """La cifra que justifica que `project_out_kernel` venga apagado.

        Medido sobre las seis zonas a σ=1,0 y N=5, encenderla baja la
        detección de 78,8–97,2 % a 19,0–55,0 %.

        El mecanismo: la proyección resta `(u₀ᵀx)·u₀`, y como `u₀ ∝ √d` no
        es constante, deja en cada bola un corrimiento proporcional a
        `(u₀ᵀx)` por el desbalance de grado del grupo. En una señal de
        220 V, `u₀ᵀx` vale ~1 092, así que el corrimiento es enorme y
        **determinista**: el máximo cae siempre en la misma bola, la de
        mayor desbalance, sin importar los datos.

        Por eso el daño **crece con la ventana**: el sesgo no cambia, pero
        el ruido contra el que compite baja como `√N`. Medido, el factor de
        inflación del estadístico nulo va de ~9× con un instante a ~50× con
        los 32 de la ventana por defecto.
        """
        n = zona_real.n_meters
        u0 = zona_real.eigenvectors[:, 0]
        mascaras, _ = candidate_balls(zona_real, (1,))
        rng = np.random.default_rng(SEMILLA)

        inflaciones = []
        for ventana in (1, 32):
            limpio = rng.normal(220.0, SIGMA, size=(300, ventana, n)).mean(axis=1)
            proyectado = limpio - (limpio @ u0)[:, None] * u0[None, :]
            sigma_eff = SIGMA / np.sqrt(ventana)
            sin = contrasts(limpio, mascaras, sigma_eff).max(axis=1).mean()
            con = contrasts(proyectado, mascaras, sigma_eff).max(axis=1).mean()
            inflaciones.append(float(con / sin))

        assert inflaciones[0] > 5.0
        assert inflaciones[1] > 25.0
        assert inflaciones[1] > inflaciones[0]
