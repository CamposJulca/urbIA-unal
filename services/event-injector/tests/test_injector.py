"""Tests del inyector: qué se aplica, qué queda registrado y qué se respeta."""

from __future__ import annotations

import numpy as np
import pytest
from urbia_monitor_gsp.graph import AmiGraph, ZoneGraph

from conftest import SEMILLA, senal_normal
from urbia_events import (
    BoundsViolationError,
    CollectiveDeviationSpec,
    EventInjector,
    InvalidSpecError,
    SignalBounds,
    SignalProfile,
    UnknownDeviceError,
    device_type_of,
)
from urbia_events.types import Magnitude


@pytest.fixture
def inyector(perfil: SignalProfile, limites: dict[Magnitude, SignalBounds]) -> EventInjector:
    return EventInjector(profile=perfil, bounds=limites, seed=SEMILLA)


class TestAplicacion:
    def test_solo_el_vecindario_se_desvia(
        self, inyector: EventInjector, zona_mono: ZoneGraph, perfil: SignalProfile
    ) -> None:
        """Lo que define la familia: el resto de la zona sigue su patrón."""
        x = senal_normal(zona_mono, perfil)
        spec = CollectiveDeviationSpec(magnitude="voltaje_v", depth=1, sigma_multiple=1.0)
        y, verdad = inyector.inject(zona_mono, x, [spec])

        afectados = set(verdad.events[0].node_indices)
        for i in range(zona_mono.n_meters):
            if i in afectados:
                assert y[0, i] != pytest.approx(x[0, i])
            else:
                assert y[0, i] == pytest.approx(x[0, i], abs=0.0)

    def test_todos_los_afectados_se_mueven_en_la_misma_direccion(
        self, inyector: EventInjector, zona_mono: ZoneGraph, perfil: SignalProfile
    ) -> None:
        x = senal_normal(zona_mono, perfil)
        spec = CollectiveDeviationSpec(magnitude="voltaje_v", depth=1, sigma_multiple=1.0)
        y, verdad = inyector.inject(zona_mono, x, [spec])
        diferencias = (
            y[0, list(verdad.events[0].node_indices)] - x[0, list(verdad.events[0].node_indices)]
        )
        assert np.all(diferencias > 0)

    def test_direccion_hacia_abajo_invierte_el_signo(
        self, inyector: EventInjector, zona_mono: ZoneGraph, perfil: SignalProfile
    ) -> None:
        x = senal_normal(zona_mono, perfil)
        spec = CollectiveDeviationSpec(
            magnitude="voltaje_v", depth=1, sigma_multiple=1.0, direction="down"
        )
        y, verdad = inyector.inject(zona_mono, x, [spec])
        indices = list(verdad.events[0].node_indices)
        assert np.all(y[0, indices] - x[0, indices] < 0)

    def test_la_desviacion_vale_el_multiplo_de_sigma_pedido(
        self, inyector: EventInjector, zona_mono: ZoneGraph, perfil: SignalProfile
    ) -> None:
        x = senal_normal(zona_mono, perfil)
        sigma = perfil.sigma_spatial("voltaje_v", device_type_of(zona_mono.device_ids[0]))
        spec = CollectiveDeviationSpec(magnitude="voltaje_v", depth=1, sigma_multiple=1.5)
        y, verdad = inyector.inject(zona_mono, x, [spec])
        indices = list(verdad.events[0].node_indices)
        np.testing.assert_allclose(y[0, indices] - x[0, indices], 1.5 * sigma)

    def test_profundidad_cero_afecta_solo_a_la_semilla(
        self, inyector: EventInjector, zona_mono: ZoneGraph, perfil: SignalProfile
    ) -> None:
        """El caso de control individual, contra el que se compara el umbral."""
        x = senal_normal(zona_mono, perfil)
        spec = CollectiveDeviationSpec(magnitude="voltaje_v", depth=0, sigma_multiple=1.0)
        _, verdad = inyector.inject(zona_mono, x, [spec])
        assert len(verdad.events[0].device_ids) == 1
        assert verdad.events[0].device_ids[0] == verdad.events[0].seed_device_id

    def test_fraction_desvia_en_proporcion_al_valor_de_cada_nodo(
        self, inyector: EventInjector, zona_mono: ZoneGraph, perfil: SignalProfile
    ) -> None:
        x = senal_normal(zona_mono, perfil)
        spec = CollectiveDeviationSpec(magnitude="voltaje_v", depth=1, fraction=0.01)
        y, verdad = inyector.inject(zona_mono, x, [spec])
        indices = list(verdad.events[0].node_indices)
        np.testing.assert_allclose(y[0, indices], x[0, indices] * 1.01)

    def test_la_ventana_temporal_se_respeta(
        self, inyector: EventInjector, zona_mono: ZoneGraph, perfil: SignalProfile
    ) -> None:
        x = senal_normal(zona_mono, perfil, n_instantes=6)
        spec = CollectiveDeviationSpec(
            magnitude="voltaje_v", depth=1, sigma_multiple=1.0, start=2, duration=3
        )
        y, verdad = inyector.inject(zona_mono, x, [spec])
        indices = list(verdad.events[0].node_indices)
        for t in (0, 1, 5):
            np.testing.assert_allclose(y[t], x[t])
        for t in (2, 3, 4):
            assert np.all(y[t, indices] > x[t, indices])

    def test_dos_eventos_sobre_el_mismo_nodo_acumulan(
        self, inyector: EventInjector, zona_mono: ZoneGraph, perfil: SignalProfile
    ) -> None:
        x = senal_normal(zona_mono, perfil)
        semilla = zona_mono.device_ids[0]
        spec = CollectiveDeviationSpec(
            magnitude="voltaje_v", depth=0, sigma_multiple=1.0, seed_device_id=semilla
        )
        y, verdad = inyector.inject(zona_mono, x, [spec, spec])
        sigma = perfil.sigma_spatial("voltaje_v", device_type_of(semilla))
        assert y[0, 0] - x[0, 0] == pytest.approx(2.0 * sigma)
        assert len(verdad.events) == 2


class TestVerdadDeReferencia:
    def test_restar_delta_reconstruye_la_senal_original(
        self, inyector: EventInjector, zona_mono: ZoneGraph, perfil: SignalProfile
    ) -> None:
        """Sin esto la verdad no serviría para puntuar nada."""
        x = senal_normal(zona_mono, perfil, n_instantes=4)
        spec = CollectiveDeviationSpec(
            magnitude="voltaje_v", depth=2, sigma_multiple=0.8, start=1, duration=2
        )
        y, verdad = inyector.inject(zona_mono, x, [spec])

        reconstruida = y.copy()
        evento = verdad.events[0]
        delta = np.array(evento.delta)
        reconstruida[evento.start : evento.start + evento.duration][
            :, list(evento.node_indices)
        ] -= delta
        np.testing.assert_allclose(reconstruida, x, atol=1e-12)

    def test_la_mascara_marca_los_nodos_correctos_en_cada_instante(
        self, inyector: EventInjector, zona_mono: ZoneGraph, perfil: SignalProfile
    ) -> None:
        x = senal_normal(zona_mono, perfil, n_instantes=5)
        spec = CollectiveDeviationSpec(
            magnitude="voltaje_v", depth=1, sigma_multiple=1.0, start=2, duration=2
        )
        _, verdad = inyector.inject(zona_mono, x, [spec])
        afectados = set(verdad.events[0].node_indices)
        for t in range(5):
            esperada = afectados if t in (2, 3) else set()
            assert set(np.flatnonzero(verdad.node_mask(t)).tolist()) == esperada

    def test_la_verdad_es_serializable_a_json(
        self, inyector: EventInjector, zona_mono: ZoneGraph, perfil: SignalProfile
    ) -> None:
        import json

        x = senal_normal(zona_mono, perfil)
        spec = CollectiveDeviationSpec(magnitude="voltaje_v", depth=1, sigma_multiple=1.0)
        _, verdad = inyector.inject(zona_mono, x, [spec])
        texto = json.dumps(verdad.to_dict())
        assert json.loads(texto)["events"][0]["family"] == "desviacion_colectiva"

    def test_instant_mask_tiene_la_forma_de_la_senal(
        self, inyector: EventInjector, zona_mono: ZoneGraph, perfil: SignalProfile
    ) -> None:
        x = senal_normal(zona_mono, perfil, n_instantes=3)
        spec = CollectiveDeviationSpec(magnitude="voltaje_v", depth=1, sigma_multiple=1.0)
        _, verdad = inyector.inject(zona_mono, x, [spec])
        assert verdad.instant_mask().shape == (3, zona_mono.n_meters)


class TestSutileza:
    """La propiedad que hace útil a esta familia."""

    def test_ningun_medidor_sale_del_rango_del_esquema(
        self,
        inyector: EventInjector,
        zona_mono: ZoneGraph,
        perfil: SignalProfile,
        limites: dict[Magnitude, SignalBounds],
    ) -> None:
        x = senal_normal(zona_mono, perfil, n_instantes=20)
        spec = CollectiveDeviationSpec(magnitude="voltaje_v", depth=2, sigma_multiple=1.0)
        y, _ = inyector.inject(zona_mono, x, [spec])
        assert not limites["voltaje_v"].violations(y).any()

    def test_toda_lectura_inyectada_es_un_valor_que_la_operacion_normal_produce(
        self, inyector: EventInjector, zona_mono: ZoneGraph, perfil: SignalProfile
    ) -> None:
        """El sentido preciso de "individualmente indistinguible".

        No se puede señalar ninguna lectura y decir que es anormal, porque
        ese mismo valor ocurre en operación normal: con 1σ de desviación el
        grupo queda en 207,2–235,1 V, dentro del 198,4–240,5 V que el perfil
        registra como rango observado.
        """
        p = perfil.get("voltaje_v", device_type_of(zona_mono.device_ids[0]))
        x = senal_normal(zona_mono, perfil, n_instantes=50)
        spec = CollectiveDeviationSpec(magnitude="voltaje_v", depth=2, sigma_multiple=1.0)
        y, _ = inyector.inject(zona_mono, x, [spec])
        assert y.min() >= p.minimum_observed
        assert y.max() <= p.maximum_observed

    def test_un_umbral_por_medidor_marca_el_grupo_a_la_tasa_del_ruido(
        self, inyector: EventInjector, zona_mono: ZoneGraph, perfil: SignalProfile
    ) -> None:
        """El punto entero de la familia, enunciado como es cierto.

        No es que ninguna lectura cruce 3σ: con 25 medidores y 50 instantes
        el ruido solo ya produce 2 excursiones de 1 250. Lo que importa es
        que el evento **no aumenta esa tasa**: el grupo afectado marca 2 de
        650 (0,31 %), del mismo orden que el fondo. Un umbral por medidor no
        distingue el evento del ruido.

        La comparación que da la escala: la anomalía que el simulador ya
        produce está a +6,0σ, donde cualquier umbral acierta siempre.
        """
        p = perfil.get("voltaje_v", device_type_of(zona_mono.device_ids[0]))
        x = senal_normal(zona_mono, perfil, n_instantes=50)
        spec = CollectiveDeviationSpec(magnitude="voltaje_v", depth=2, sigma_multiple=1.0)
        y, verdad = inyector.inject(zona_mono, x, [spec])

        indices = list(verdad.events[0].node_indices)
        z_grupo = np.abs(y[:, indices] - p.mean) / p.sigma_spatial
        z_fondo = np.abs(x - p.mean) / p.sigma_spatial

        assert float((z_grupo > 3.0).mean()) < 0.01
        assert float((z_grupo > 3.0).mean()) < 5.0 * float((z_fondo > 3.0).mean()) + 0.005
        assert float(z_grupo.max()) < 6.0  # muy lejos del +6σ de la anomalía trivial


class TestLimites:
    def test_una_desviacion_imposible_levanta_error(
        self, inyector: EventInjector, zona_mono: ZoneGraph, perfil: SignalProfile
    ) -> None:
        x = senal_normal(zona_mono, perfil)
        spec = CollectiveDeviationSpec(magnitude="voltaje_v", depth=1, sigma_multiple=50.0)
        with pytest.raises(BoundsViolationError, match="voltaje_v"):
            inyector.inject(zona_mono, x, [spec])

    def test_el_error_nombra_a_los_medidores_culpables(
        self, inyector: EventInjector, zona_mono: ZoneGraph, perfil: SignalProfile
    ) -> None:
        x = senal_normal(zona_mono, perfil)
        spec = CollectiveDeviationSpec(magnitude="voltaje_v", depth=1, sigma_multiple=50.0)
        with pytest.raises(BoundsViolationError) as exc:
            inyector.inject(zona_mono, x, [spec])
        assert exc.value.device_ids
        assert all(d.startswith("urbia-") for d in exc.value.device_ids)

    def test_con_scale_la_desviacion_se_reduce_y_queda_registrado(
        self,
        inyector: EventInjector,
        zona_mono: ZoneGraph,
        perfil: SignalProfile,
        limites: dict[Magnitude, SignalBounds],
    ) -> None:
        x = senal_normal(zona_mono, perfil)
        spec = CollectiveDeviationSpec(magnitude="voltaje_v", depth=1, sigma_multiple=50.0)
        y, verdad = inyector.inject(zona_mono, x, [spec], on_violation="scale")
        assert verdad.events[0].scaled is True
        assert verdad.events[0].sigma_multiple is not None
        assert verdad.events[0].sigma_multiple < 50.0
        assert not limites["voltaje_v"].violations(y).any()


class TestReproducibilidad:
    def test_la_misma_semilla_da_el_mismo_evento(
        self,
        perfil: SignalProfile,
        limites: dict[Magnitude, SignalBounds],
        zona_mono: ZoneGraph,
    ) -> None:
        x = senal_normal(zona_mono, perfil)
        spec = CollectiveDeviationSpec(magnitude="voltaje_v", depth=1, sigma_multiple=1.0)
        una, _ = EventInjector(perfil, limites, seed=7).inject(zona_mono, x, [spec])
        otra, _ = EventInjector(perfil, limites, seed=7).inject(zona_mono, x, [spec])
        np.testing.assert_array_equal(una, otra)

    def test_semillas_distintas_dan_semillas_de_evento_distintas(
        self,
        perfil: SignalProfile,
        limites: dict[Magnitude, SignalBounds],
        zona_mono: ZoneGraph,
    ) -> None:
        x = senal_normal(zona_mono, perfil)
        spec = CollectiveDeviationSpec(magnitude="voltaje_v", depth=0, sigma_multiple=1.0)
        elegidas = {
            EventInjector(perfil, limites, seed=s)
            .inject(zona_mono, x, [spec])[1]
            .events[0]
            .seed_device_id
            for s in range(12)
        }
        assert len(elegidas) > 1

    def test_zonas_distintas_no_comparten_la_secuencia_aleatoria(
        self,
        inyector: EventInjector,
        zona_mono: ZoneGraph,
        zona_tri: ZoneGraph,
        perfil: SignalProfile,
    ) -> None:
        """El nombre de la zona entra en la semilla, y de forma estable."""
        spec = CollectiveDeviationSpec(magnitude="voltaje_v", depth=0, sigma_multiple=1.0)
        _, una = inyector.inject(zona_mono, senal_normal(zona_mono, perfil), [spec])
        _, otra = inyector.inject(zona_tri, senal_normal(zona_tri, perfil), [spec])
        assert una.events[0].seed_device_id != otra.events[0].seed_device_id

    def test_la_senal_de_entrada_no_se_modifica(
        self, inyector: EventInjector, zona_mono: ZoneGraph, perfil: SignalProfile
    ) -> None:
        x = senal_normal(zona_mono, perfil)
        original = x.copy()
        spec = CollectiveDeviationSpec(magnitude="voltaje_v", depth=1, sigma_multiple=1.0)
        inyector.inject(zona_mono, x, [spec])
        np.testing.assert_array_equal(x, original)


class TestValidacion:
    def test_una_senal_de_largo_equivocado_levanta_error(
        self, inyector: EventInjector, zona_mono: ZoneGraph
    ) -> None:
        spec = CollectiveDeviationSpec(magnitude="voltaje_v", depth=1, sigma_multiple=1.0)
        with pytest.raises(InvalidSpecError, match="forma"):
            inyector.inject(zona_mono, np.zeros(3), [spec])

    def test_una_senal_con_nan_levanta_error(
        self, inyector: EventInjector, zona_mono: ZoneGraph, perfil: SignalProfile
    ) -> None:
        x = senal_normal(zona_mono, perfil)
        x[0, 0] = np.nan
        spec = CollectiveDeviationSpec(magnitude="voltaje_v", depth=1, sigma_multiple=1.0)
        with pytest.raises(InvalidSpecError, match="no finito"):
            inyector.inject(zona_mono, x, [spec])

    def test_una_ventana_que_excede_la_senal_levanta_error(
        self, inyector: EventInjector, zona_mono: ZoneGraph, perfil: SignalProfile
    ) -> None:
        x = senal_normal(zona_mono, perfil, n_instantes=2)
        spec = CollectiveDeviationSpec(
            magnitude="voltaje_v", depth=1, sigma_multiple=1.0, start=1, duration=5
        )
        with pytest.raises(ValueError, match="ventana"):
            inyector.inject(zona_mono, x, [spec])

    def test_una_semilla_ajena_a_la_zona_levanta_error(
        self, inyector: EventInjector, zona_mono: ZoneGraph, perfil: SignalProfile
    ) -> None:
        x = senal_normal(zona_mono, perfil)
        spec = CollectiveDeviationSpec(
            magnitude="voltaje_v",
            depth=1,
            sigma_multiple=1.0,
            seed_device_id="urbia-ena-tri-0001",
        )
        with pytest.raises(UnknownDeviceError, match="no pertenece"):
            inyector.inject(zona_mono, x, [spec])

    def test_on_violation_invalido_levanta_error(
        self, inyector: EventInjector, zona_mono: ZoneGraph, perfil: SignalProfile
    ) -> None:
        x = senal_normal(zona_mono, perfil)
        spec = CollectiveDeviationSpec(magnitude="voltaje_v", depth=1, sigma_multiple=1.0)
        with pytest.raises(InvalidSpecError, match="on_violation"):
            inyector.inject(zona_mono, x, [spec], on_violation="recortar")

    def test_una_magnitud_sin_limites_levanta_error(
        self, perfil: SignalProfile, zona_mono: ZoneGraph
    ) -> None:
        vacio = EventInjector(perfil, {}, seed=SEMILLA)
        spec = CollectiveDeviationSpec(magnitude="voltaje_v", depth=1, sigma_multiple=1.0)
        with pytest.raises(InvalidSpecError, match="límites"):
            vacio.inject(zona_mono, senal_normal(zona_mono, perfil), [spec])


class TestEjeDeTamano:
    """`size_target`: el eje limpio que el barrido necesita.

    Con `depth` el tamaño queda atado a la topología local —el mismo
    `depth=2` da 11 nodos en una zona y 18 en otra—, así que un barrido
    indexado por `depth` no sería comparable entre zonas.
    """

    @pytest.mark.parametrize("m", [1, 3, 7, 12, 25])
    def test_el_grupo_tiene_el_tamano_pedido(
        self, inyector: EventInjector, zona_mono: ZoneGraph, perfil: SignalProfile, m: int
    ) -> None:
        spec = CollectiveDeviationSpec(magnitude="voltaje_v", size_target=m, sigma_multiple=0.5)
        _, verdad = inyector.inject(zona_mono, senal_normal(zona_mono, perfil), [spec])
        evento = verdad.events[0]
        assert evento.n_nodes == m
        assert len(evento.device_ids) == m

    def test_el_mismo_tamano_en_todas_las_zonas(
        self, inyector: EventInjector, grafo: AmiGraph, perfil: SignalProfile
    ) -> None:
        """Lo que `depth` no puede dar, y es la razón del eje nuevo."""
        tamanos = set()
        for nombre in grafo.zone_order:
            zona = grafo.zones[nombre]
            spec = CollectiveDeviationSpec(magnitude="voltaje_v", size_target=8, sigma_multiple=0.5)
            _, verdad = inyector.inject(zona, senal_normal(zona, perfil), [spec])
            tamanos.add(verdad.events[0].n_nodes)
        assert tamanos == {8}

    def test_registra_perimetro_cobertura_y_tamano_de_zona(
        self, inyector: EventInjector, zona_mono: ZoneGraph, perfil: SignalProfile
    ) -> None:
        """Sin el perímetro no se puede contrastar la hipótesis del perímetro."""
        spec = CollectiveDeviationSpec(magnitude="voltaje_v", size_target=6, sigma_multiple=0.5)
        _, verdad = inyector.inject(zona_mono, senal_normal(zona_mono, perfil), [spec])
        evento = verdad.events[0]
        assert evento.zone_size == zona_mono.n_meters
        assert evento.boundary_edges > 0
        assert evento.coverage == 6 / zona_mono.n_meters
        assert evento.boundary_per_node == evento.boundary_edges / 6

    def test_el_grupo_completo_no_tiene_perimetro(
        self, inyector: EventInjector, zona_mono: ZoneGraph, perfil: SignalProfile
    ) -> None:
        """El caso límite: sin frontera no hay nada que un detector de grafo vea."""
        spec = CollectiveDeviationSpec(
            magnitude="voltaje_v", size_target=zona_mono.n_meters, sigma_multiple=0.5
        )
        _, verdad = inyector.inject(zona_mono, senal_normal(zona_mono, perfil), [spec])
        evento = verdad.events[0]
        assert evento.boundary_edges == 0
        assert evento.coverage == 1.0

    def test_la_forma_queda_registrada(
        self, inyector: EventInjector, zona_mono: ZoneGraph, perfil: SignalProfile
    ) -> None:
        spec = CollectiveDeviationSpec(
            magnitude="voltaje_v", size_target=6, shape="extendido", sigma_multiple=0.5
        )
        _, verdad = inyector.inject(zona_mono, senal_normal(zona_mono, perfil), [spec])
        evento = verdad.events[0]
        assert evento.shape == "extendido"
        assert evento.size_target == 6
        assert evento.depth is None

    def test_por_depth_no_se_registra_forma(
        self, inyector: EventInjector, zona_mono: ZoneGraph, perfil: SignalProfile
    ) -> None:
        """La familia ya medida no cambia de significado."""
        spec = CollectiveDeviationSpec(magnitude="voltaje_v", depth=1, sigma_multiple=0.5)
        _, verdad = inyector.inject(zona_mono, senal_normal(zona_mono, perfil), [spec])
        evento = verdad.events[0]
        assert evento.shape is None
        assert evento.size_target is None
        assert evento.depth == 1

    def test_delta_reconstruye_el_original_tambien_por_tamano(
        self, inyector: EventInjector, zona_mono: ZoneGraph, perfil: SignalProfile
    ) -> None:
        """El invariante que hace verificable a la verdad, en el eje nuevo."""
        base = senal_normal(zona_mono, perfil, n_instantes=6)
        spec = CollectiveDeviationSpec(
            magnitude="voltaje_v", size_target=9, sigma_multiple=0.5, start=1, duration=3
        )
        senal, verdad = inyector.inject(zona_mono, base, [spec])
        evento = verdad.events[0]
        reconstruida = senal.copy()
        reconstruida[1:4][:, list(evento.node_indices)] -= np.asarray(evento.delta)
        assert np.allclose(reconstruida, base)


class TestExpectedDetectableDerivado:
    """La etiqueta sale del álgebra, no de lo que uno espera medir.

    El caso ambiguo —un grupo grande pero no total— es justo el que uno
    estaría tentado de etiquetar según el resultado deseado. Derivarlo de
    `m < n` lo saca de la discusión.
    """

    @pytest.mark.parametrize("m", [1, 6, 12, 24])
    def test_un_grupo_con_complemento_es_detectable(
        self, inyector: EventInjector, zona_mono: ZoneGraph, perfil: SignalProfile, m: int
    ) -> None:
        spec = CollectiveDeviationSpec(magnitude="voltaje_v", size_target=m, sigma_multiple=0.5)
        _, verdad = inyector.inject(zona_mono, senal_normal(zona_mono, perfil), [spec])
        assert verdad.events[0].expected_detectable

    def test_la_zona_entera_no_es_detectable(
        self, inyector: EventInjector, zona_mono: ZoneGraph, perfil: SignalProfile
    ) -> None:
        """El modo común: no hay discordancia con la vecindad."""
        spec = CollectiveDeviationSpec(
            magnitude="voltaje_v", size_target=zona_mono.n_meters, sigma_multiple=0.5
        )
        _, verdad = inyector.inject(zona_mono, senal_normal(zona_mono, perfil), [spec])
        assert not verdad.events[0].expected_detectable

    def test_depth_que_cubre_la_zona_entera_tampoco(
        self, inyector: EventInjector, zona_mono: ZoneGraph, perfil: SignalProfile
    ) -> None:
        """La derivación es del grupo resultante, no del eje que se declaró."""
        spec = CollectiveDeviationSpec(magnitude="voltaje_v", depth=99, sigma_multiple=0.5)
        _, verdad = inyector.inject(zona_mono, senal_normal(zona_mono, perfil), [spec])
        assert not verdad.events[0].expected_detectable

    def test_se_puede_fijar_a_mano_como_escape(
        self, inyector: EventInjector, zona_mono: ZoneGraph, perfil: SignalProfile
    ) -> None:
        spec = CollectiveDeviationSpec(
            magnitude="voltaje_v",
            size_target=zona_mono.n_meters,
            sigma_multiple=0.5,
            expected_detectable=True,
        )
        _, verdad = inyector.inject(zona_mono, senal_normal(zona_mono, perfil), [spec])
        assert verdad.events[0].expected_detectable


class TestValidacionDeEjes:
    def test_declarar_los_dos_ejes_es_error(self) -> None:
        with pytest.raises(InvalidSpecError, match="exactamente uno de depth o size_target"):
            CollectiveDeviationSpec(
                magnitude="voltaje_v", depth=1, size_target=6, sigma_multiple=0.5
            )

    def test_no_declarar_ninguno_es_error(self) -> None:
        with pytest.raises(InvalidSpecError, match="exactamente uno de depth o size_target"):
            CollectiveDeviationSpec(magnitude="voltaje_v", sigma_multiple=0.5)

    def test_tamano_cero_es_error(self) -> None:
        with pytest.raises(InvalidSpecError, match="size_target debe ser >= 1"):
            CollectiveDeviationSpec(magnitude="voltaje_v", size_target=0, sigma_multiple=0.5)

    def test_forma_desconocida_es_error(self) -> None:
        with pytest.raises(InvalidSpecError, match="shape debe ser"):
            CollectiveDeviationSpec(
                magnitude="voltaje_v",
                size_target=6,
                shape="raro",  # type: ignore[arg-type]
                sigma_multiple=0.5,
            )

    def test_tamano_mayor_que_la_zona_es_error(
        self, inyector: EventInjector, zona_mono: ZoneGraph, perfil: SignalProfile
    ) -> None:
        """La spec no conoce la zona; el error aparece al aplicar."""
        spec = CollectiveDeviationSpec(
            magnitude="voltaje_v", size_target=zona_mono.n_meters + 1, sigma_multiple=0.5
        )
        with pytest.raises(ValueError, match="size_target debe estar"):
            inyector.inject(zona_mono, senal_normal(zona_mono, perfil), [spec])
