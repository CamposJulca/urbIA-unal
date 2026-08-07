"""Tests de los tipos, la configuración y los errores del constructor."""

from __future__ import annotations

import dataclasses

import pytest

from urbia_monitor_gsp.graph.types import (
    MIN_METERS_PER_ZONE,
    GraphConfig,
    InsufficientMetersError,
    InvalidCoordinateError,
    InvalidGraphConfigError,
    MeterNode,
    MonitorGspError,
)


class TestMeterNode:
    def test_meter_node_coordenadas_validas_se_construye(self) -> None:
        nodo = MeterNode("urbia-cen-mon-0001", "centro", 5.068755, -75.517165)
        assert nodo.device_id == "urbia-cen-mon-0001"
        assert nodo.zona == "centro"

    def test_meter_node_es_inmutable(self) -> None:
        nodo = MeterNode("urbia-cen-mon-0001", "centro", 5.068755, -75.517165)
        with pytest.raises(dataclasses.FrozenInstanceError):
            nodo.lat = 0.0  # type: ignore[misc]

    @pytest.mark.parametrize("lat", [90.1, -90.1, 1e6])
    def test_meter_node_latitud_fuera_de_rango_levanta_error(self, lat: float) -> None:
        with pytest.raises(InvalidCoordinateError, match="latitud fuera de rango"):
            MeterNode("urbia-cen-mon-0001", "centro", lat, -75.5)

    @pytest.mark.parametrize("lon", [180.1, -180.1, 1e6])
    def test_meter_node_longitud_fuera_de_rango_levanta_error(self, lon: float) -> None:
        with pytest.raises(InvalidCoordinateError, match="longitud fuera de rango"):
            MeterNode("urbia-cen-mon-0001", "centro", 5.06, lon)

    def test_meter_node_device_id_vacio_levanta_error(self) -> None:
        with pytest.raises(InvalidCoordinateError, match="device_id"):
            MeterNode("", "centro", 5.06, -75.5)

    def test_meter_node_zona_vacia_levanta_error(self) -> None:
        with pytest.raises(InvalidCoordinateError, match="zona vacía"):
            MeterNode("urbia-cen-mon-0001", "", 5.06, -75.5)


class TestGraphConfig:
    def test_graph_config_por_defecto_es_knn_k4_binario_sin_puente(self) -> None:
        """Los valores por defecto son la configuración justificada en ADR-003."""
        config = GraphConfig()
        assert config.strategy == "knn"
        assert config.k == 4
        assert config.knn_mode == "union"
        assert config.weighting == "binary"
        assert config.inter_zone_bridge is False
        assert config.sigma_m is None

    def test_graph_config_es_inmutable(self) -> None:
        config = GraphConfig()
        with pytest.raises(dataclasses.FrozenInstanceError):
            config.k = 8  # type: ignore[misc]

    @pytest.mark.parametrize("k", [0, -1])
    def test_graph_config_k_menor_que_uno_levanta_error(self, k: int) -> None:
        with pytest.raises(InvalidGraphConfigError, match="k debe ser >= 1"):
            GraphConfig(k=k)

    def test_graph_config_radius_sin_radio_levanta_error(self) -> None:
        with pytest.raises(InvalidGraphConfigError, match="requiere radius_m"):
            GraphConfig(strategy="radius")

    @pytest.mark.parametrize("radio", [0.0, -100.0])
    def test_graph_config_radius_no_positivo_levanta_error(self, radio: float) -> None:
        with pytest.raises(InvalidGraphConfigError, match="radius_m debe ser > 0"):
            GraphConfig(strategy="radius", radius_m=radio)

    def test_graph_config_radius_con_radio_valido_se_construye(self) -> None:
        config = GraphConfig(strategy="radius", radius_m=450.0)
        assert config.radius_m == 450.0

    def test_graph_config_sigma_no_positivo_levanta_error(self) -> None:
        with pytest.raises(InvalidGraphConfigError, match="sigma_m debe ser > 0"):
            GraphConfig(weighting="gaussian", sigma_m=0.0)

    def test_graph_config_sigma_con_pesos_binarios_levanta_error(self) -> None:
        """Declarar sigma sin gaussianas esconde un malentendido: hay que gritar."""
        with pytest.raises(InvalidGraphConfigError, match="sólo aplica a weighting"):
            GraphConfig(weighting="binary", sigma_m=200.0)

    def test_graph_config_gaussiana_sin_sigma_se_construye(self) -> None:
        """sigma=None es válido: se deriva de las distancias de vecindad."""
        config = GraphConfig(weighting="gaussian")
        assert config.sigma_m is None

    def test_graph_config_puente_inter_zona_se_puede_encender(self) -> None:
        config = GraphConfig(inter_zone_bridge=True)
        assert config.inter_zone_bridge is True


class TestInsufficientMetersError:
    def test_min_meters_per_zone_es_dos(self) -> None:
        assert MIN_METERS_PER_ZONE == 2

    def test_insufficient_meters_error_conserva_zona_y_conteo(self) -> None:
        error = InsufficientMetersError("universitario", 1)
        assert error.zona == "universitario"
        assert error.n_meters == 1

    def test_insufficient_meters_error_mensaje_nombra_la_zona_culpable(self) -> None:
        error = InsufficientMetersError("universitario", 1)
        assert "universitario" in str(error)
        assert "1 medidor" in str(error)

    def test_insufficient_meters_error_es_value_error_y_error_del_monitor(self) -> None:
        error = InsufficientMetersError("centro", 0)
        assert isinstance(error, ValueError)
        assert isinstance(error, MonitorGspError)
