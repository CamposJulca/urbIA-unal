"""Tests del contrato: especificación, límites, perfil y aislamiento."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from conftest import ESQUEMA, PERFIL
from urbia_events import (
    CollectiveDeviationSpec,
    InvalidSpecError,
    MagnitudeProfile,
    SignalBounds,
    SignalProfile,
    UnknownDeviceError,
    device_type_of,
    load_bounds,
    load_profile,
)


class TestDeviceType:
    @pytest.mark.parametrize(
        ("device_id", "esperado"),
        [
            ("urbia-cen-mon-0001", "mono"),
            ("urbia-ena-tri-0023", "trifasico"),
            ("urbia-pgr-mon-0030", "mono"),
        ],
    )
    def test_deduce_el_tipo_del_identificador(self, device_id: str, esperado: str) -> None:
        assert device_type_of(device_id) == esperado

    @pytest.mark.parametrize(
        "device_id",
        ["AMI-MNZ-00001", "urbia-cen-xxx-0001", "urbia-zzz-mon-0001", "", "urbia-cen-mon-1"],
    )
    def test_un_identificador_ajeno_al_esquema_levanta_error(self, device_id: str) -> None:
        with pytest.raises(UnknownDeviceError, match="formato"):
            device_type_of(device_id)


class TestSpec:
    def test_declarar_las_dos_magnitudes_levanta_error(self) -> None:
        with pytest.raises(InvalidSpecError, match="exactamente uno"):
            CollectiveDeviationSpec(
                magnitude="voltaje_v", depth=1, sigma_multiple=1.0, fraction=0.01
            )

    def test_no_declarar_ninguna_levanta_error(self) -> None:
        with pytest.raises(InvalidSpecError, match="exactamente uno"):
            CollectiveDeviationSpec(magnitude="voltaje_v", depth=1)

    def test_una_magnitud_negativa_levanta_error(self) -> None:
        """El sentido va en `direction`, no en el signo."""
        with pytest.raises(InvalidSpecError, match="> 0"):
            CollectiveDeviationSpec(magnitude="voltaje_v", depth=1, sigma_multiple=-1.0)

    @pytest.mark.parametrize(("campo", "valor"), [("depth", -1), ("start", -1), ("duration", 0)])
    def test_parametros_fuera_de_rango_levantan_error(self, campo: str, valor: int) -> None:
        argumentos: dict[str, Any] = {
            "magnitude": "voltaje_v",
            "depth": 1,
            "sigma_multiple": 1.0,
            campo: valor,
        }
        with pytest.raises(InvalidSpecError, match=campo):
            CollectiveDeviationSpec(**argumentos)

    def test_el_signo_sale_de_la_direccion(self) -> None:
        arriba = CollectiveDeviationSpec(magnitude="voltaje_v", depth=1, sigma_multiple=1.0)
        abajo = CollectiveDeviationSpec(
            magnitude="voltaje_v", depth=1, sigma_multiple=1.0, direction="down"
        )
        assert arriba.sign == 1.0
        assert abajo.sign == -1.0


class TestBounds:
    def test_un_rango_invertido_levanta_error(self) -> None:
        with pytest.raises(InvalidSpecError, match="rango inválido"):
            SignalBounds(magnitude="voltaje_v", minimum=253.0, maximum=187.0)

    def test_violations_marca_los_dos_extremos(self) -> None:
        limites = SignalBounds(magnitude="voltaje_v", minimum=187.0, maximum=253.0)
        valores = np.array([186.9, 220.0, 253.1])
        np.testing.assert_array_equal(limites.violations(valores), [True, False, True])

    def test_los_limites_salen_del_esquema_versionado(self) -> None:
        """Las cifras del contrato del productor, no escritas a mano acá."""
        limites = load_bounds(ESQUEMA)
        assert limites["voltaje_v"].minimum == 187.0
        assert limites["voltaje_v"].maximum == 253.0
        assert limites["corriente_a"].maximum == 60.0
        assert limites["potencia_kw"].maximum == 30.0

    def test_un_esquema_sin_la_magnitud_levanta_error(self, tmp_path: Path) -> None:
        incompleto = tmp_path / "esquema.json"
        incompleto.write_text(json.dumps({"properties": {}}), encoding="utf-8")
        with pytest.raises(InvalidSpecError, match="no declara la magnitud"):
            load_bounds(incompleto)

    def test_un_esquema_sin_el_limite_levanta_error(self, tmp_path: Path) -> None:
        incompleto = tmp_path / "esquema.json"
        incompleto.write_text(
            json.dumps({"properties": {"voltaje_v": {"minimum": 187.0}}}), encoding="utf-8"
        )
        with pytest.raises(InvalidSpecError, match="maximum"):
            load_bounds(incompleto)


class TestProfile:
    def test_el_perfil_versionado_trae_las_seis_combinaciones(self) -> None:
        perfil = load_profile(PERFIL)
        assert len(perfil.entries) == 6

    def test_el_voltaje_tiene_dispersion_del_dos_por_ciento(self) -> None:
        """La cifra que hace del voltaje la magnitud adecuada para esta familia."""
        perfil = load_profile(PERFIL)
        for tipo in ("mono", "trifasico"):
            assert perfil.get("voltaje_v", tipo).relative_spread == pytest.approx(0.020, abs=5e-4)

    def test_corriente_y_potencia_dispersan_treinta_veces_mas(self) -> None:
        """Por qué la magnitud no puede declararse en porcentaje crudo."""
        perfil = load_profile(PERFIL)
        for magnitud in ("corriente_a", "potencia_kw"):
            for tipo in ("mono", "trifasico"):
                assert 0.30 <= perfil.get(magnitud, tipo).relative_spread <= 0.40

    def test_las_zonas_estan_confundidas_con_el_tipo_de_medidor(self) -> None:
        """Advertencia registrada como test: cada zona es de un solo tipo."""
        perfil = load_profile(PERFIL)
        assert perfil.zone_to_device_type == {
            "centro": "mono",
            "chipre": "mono",
            "palogrande": "mono",
            "la_enea": "trifasico",
            "palermo": "trifasico",
            "universitario": "trifasico",
        }

    def test_pedir_una_combinacion_ausente_levanta_error(self) -> None:
        perfil = load_profile(PERFIL)
        vacio = SignalProfile(version="v", window_start_utc="", window_end_utc="")
        assert perfil.get("voltaje_v", "mono").mean > 0
        with pytest.raises(InvalidSpecError, match="no cubre"):
            vacio.get("voltaje_v", "mono")

    def test_un_perfil_sin_magnitudes_conocidas_levanta_error(self, tmp_path: Path) -> None:
        vacio = tmp_path / "perfil.json"
        vacio.write_text(json.dumps({"magnitudes": {}}), encoding="utf-8")
        with pytest.raises(InvalidSpecError, match="ninguna de las magnitudes"):
            load_profile(vacio)

    def test_una_dispersion_no_positiva_levanta_error(self) -> None:
        with pytest.raises(InvalidSpecError, match="sigma_spatial"):
            MagnitudeProfile(
                magnitude="voltaje_v",
                device_type="mono",
                mean=220.0,
                sigma_spatial=0.0,
                sigma_pooled=4.4,
                p1=210.0,
                p99=230.0,
                minimum_observed=198.0,
                maximum_observed=241.0,
            )


class TestAislamiento:
    def test_el_inyector_no_importa_nada_del_detector(self) -> None:
        """La razón de que el inyector sea un paquete aparte.

        Lo que produce la verdad de referencia no puede compartir supuestos
        con lo que se puntúa contra ella. Acá eso deja de ser una intención
        y pasa a ser algo que se rompe si alguien cruza la frontera.
        """
        raiz = Path(__file__).parents[1] / "src" / "urbia_events"
        prohibidos = ("detector", "wavelet", "difuminador")
        for modulo in sorted(raiz.rglob("*.py")):
            texto = modulo.read_text(encoding="utf-8")
            for linea in texto.splitlines():
                despojada = linea.strip()
                if not despojada.startswith(("import ", "from ")):
                    continue
                for prohibido in prohibidos:
                    assert prohibido not in despojada, f"{modulo.name}: {despojada}"
