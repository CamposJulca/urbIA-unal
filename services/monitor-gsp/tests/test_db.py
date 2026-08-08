"""Tests del lector de PostgreSQL.

Casi todo corre sin base: la conexión se sustituye por un doble y lo que
se verifica es la conversión de filas a nodos, el manejo de datos
incompletos y los parámetros que viajan a la consulta.

El único test que necesita PostgreSQL real está marcado `integration` y no
corre en CI. Vale la pena igual, porque detecta deriva entre la tabla
`ami_meters` y la topología versionada en `data/topologies/`: si alguien
agrega medidores a la base, las cifras de los docstrings dejan de
corresponder al padrón vivo y hay que decidir qué hacer.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import psycopg
import pytest

from urbia_monitor_gsp.db import meters as meters_mod
from urbia_monitor_gsp.db.config import DatabaseSettings, get_settings
from urbia_monitor_gsp.db.meters import (
    IncompleteMeterError,
    NoMetersFoundError,
    _to_meter_nodes,
    load_ami_graph,
    load_meters,
)
from urbia_monitor_gsp.graph.types import GraphConfig

TOPOLOGIA = Path(__file__).parents[3] / "data" / "topologies" / "manizales_150.json"

FILAS_OK = [
    ("m-1", "centro", 5.060, -75.510),
    ("m-2", "centro", 5.061, -75.511),
    ("m-3", "centro", 5.062, -75.512),
]

VARIABLES_ENTORNO = (
    "POSTGRES_HOST",
    "POSTGRES_PORT",
    "POSTGRES_DB",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "CONNECT_TIMEOUT_S",
)


@pytest.fixture
def entorno_limpio(monkeypatch: pytest.MonkeyPatch) -> None:
    """Aísla la configuración del entorno real de la máquina."""
    for variable in VARIABLES_ENTORNO:
        monkeypatch.delenv(variable, raising=False)


def filas_de_topologia() -> list[tuple[Any, ...]]:
    """Las 150 filas reales, desde la topología versionada."""
    datos = json.loads(TOPOLOGIA.read_text(encoding="utf-8"))
    return [(m["device_id"], m["zona"], m["lat"], m["lon"]) for m in datos["meters"]]


class ConexionFalsa:
    """Doble de `psycopg.Connection` que registra lo que se le ejecuta."""

    def __init__(self, filas: list[tuple[Any, ...]]) -> None:
        """Guarda las filas que devolverá y prepara el registro."""
        self.filas = filas
        self.query: str | None = None
        self.parametros: dict[str, Any] | None = None
        self.cerrada = False

    def __enter__(self) -> ConexionFalsa:
        """Hace de context manager de conexión y de cursor a la vez."""
        return self

    def __exit__(self, *_: object) -> None:
        """Registra que la conexión se cerró al salir del bloque."""
        self.cerrada = True

    def cursor(self) -> ConexionFalsa:
        return self

    def execute(self, query: str, parametros: dict[str, Any]) -> None:
        self.query = query
        self.parametros = parametros

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self.filas


class TestDatabaseSettings:
    def test_valores_por_defecto_apuntan_al_dns_de_docker(self, entorno_limpio: None) -> None:
        settings = DatabaseSettings()
        assert settings.postgres_host == "postgres"
        assert settings.postgres_db == "urbia"

    def test_get_settings_lee_del_entorno(
        self, entorno_limpio: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("POSTGRES_HOST", "192.168.0.102")
        monkeypatch.setenv("POSTGRES_PORT", "6543")
        settings = get_settings()
        assert settings.postgres_host == "192.168.0.102"
        assert settings.postgres_port == 6543

    def test_conninfo_incluye_la_contrasena(self, entorno_limpio: None) -> None:
        settings = DatabaseSettings(postgres_password="secreta")
        assert "password=secreta" in settings.conninfo
        assert "connect_timeout=10" in settings.conninfo

    def test_safe_summary_no_filtra_la_contrasena(self, entorno_limpio: None) -> None:
        """Lo que va al log no debe contener credenciales."""
        settings = DatabaseSettings(postgres_password="secreta", postgres_host="h")
        assert "secreta" not in settings.safe_summary
        assert settings.safe_summary == "urbia@h:5432/urbia"

    def test_variables_ajenas_del_env_global_no_rompen(
        self, entorno_limpio: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """El .env del proyecto define MQTT, Mongo y Redis además de esto."""
        monkeypatch.setenv("MQTT_HOST", "192.168.40.12")
        assert DatabaseSettings().postgres_db == "urbia"


class TestConversionDeFilas:
    def test_convierte_filas_completas_a_meter_nodes(self) -> None:
        meters = _to_meter_nodes(FILAS_OK, skip_incomplete=False)
        assert [m.device_id for m in meters] == ["m-1", "m-2", "m-3"]
        assert meters[0].zona == "centro"
        assert meters[0].lat == pytest.approx(5.060)

    def test_conserva_el_orden_de_las_filas(self) -> None:
        meters = _to_meter_nodes(list(reversed(FILAS_OK)), skip_incomplete=False)
        assert [m.device_id for m in meters] == ["m-3", "m-2", "m-1"]

    @pytest.mark.parametrize(
        "fila",
        [
            ("m-x", None, 5.06, -75.51),
            ("m-x", "centro", None, -75.51),
            ("m-x", "centro", 5.06, None),
        ],
        ids=["sin-zona", "sin-lat", "sin-lon"],
    )
    def test_fila_incompleta_levanta_error_con_el_device_id(self, fila: tuple[Any, ...]) -> None:
        """Descartarla en silencio cambiaría la topología sin avisar."""
        with pytest.raises(IncompleteMeterError) as exc:
            _to_meter_nodes([*FILAS_OK, fila], skip_incomplete=False)
        assert exc.value.device_ids == ("m-x",)
        assert "m-x" in str(exc.value)

    def test_skip_incomplete_descarta_y_deja_aviso_en_el_log(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        fila_mala = ("m-x", "centro", None, -75.51)
        with caplog.at_level(logging.WARNING):
            meters = _to_meter_nodes([*FILAS_OK, fila_mala], skip_incomplete=True)
        assert len(meters) == 3
        assert "m-x" in caplog.text

    def test_el_mensaje_de_error_resume_cuando_hay_muchos(self) -> None:
        malas = [(f"m-{i}", None, 5.06, -75.51) for i in range(8)]
        with pytest.raises(IncompleteMeterError, match="y 3 más"):
            _to_meter_nodes(malas, skip_incomplete=False)


class TestLoadMeters:
    def test_load_meters_devuelve_los_medidores(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(meters_mod, "_fetch_rows", lambda *_: FILAS_OK)
        meters = load_meters(DatabaseSettings())
        assert len(meters) == 3

    def test_load_meters_sin_filas_levanta_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(meters_mod, "_fetch_rows", lambda *_: [])
        with pytest.raises(NoMetersFoundError, match="ninguna fila"):
            load_meters(DatabaseSettings())

    def test_load_meters_con_todas_las_filas_incompletas_levanta_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(meters_mod, "_fetch_rows", lambda *_: [("m-1", None, None, None)])
        with pytest.raises(NoMetersFoundError, match="todas incompletas"):
            load_meters(DatabaseSettings(), skip_incomplete=True)

    def test_load_meters_sin_settings_los_lee_del_entorno(
        self, entorno_limpio: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        vistos: list[DatabaseSettings] = []

        def espia(settings: DatabaseSettings, *_: object) -> list[tuple[Any, ...]]:
            vistos.append(settings)
            return FILAS_OK

        monkeypatch.setattr(meters_mod, "_fetch_rows", espia)
        monkeypatch.setenv("POSTGRES_HOST", "desde-el-entorno")
        load_meters()
        assert vistos[0].postgres_host == "desde-el-entorno"


class TestConsulta:
    def test_fetch_rows_pasa_los_filtros_como_parametros(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Nada de componer el WHERE con f-strings: no hay inyección posible."""
        falsa = ConexionFalsa(FILAS_OK)
        monkeypatch.setattr(psycopg, "connect", lambda _: falsa)

        filas = meters_mod._fetch_rows(DatabaseSettings(), ["la_enea", "chipre"], True)

        assert filas == FILAS_OK
        assert falsa.parametros == {"solo_activos": True, "zonas": ["la_enea", "chipre"]}
        assert "ORDER BY device_id" in (falsa.query or "")
        assert "la_enea" not in (falsa.query or "")

    def test_fetch_rows_sin_zonas_manda_null(self, monkeypatch: pytest.MonkeyPatch) -> None:
        falsa = ConexionFalsa(FILAS_OK)
        monkeypatch.setattr(psycopg, "connect", lambda _: falsa)

        meters_mod._fetch_rows(DatabaseSettings(), None, False)

        assert falsa.parametros == {"solo_activos": False, "zonas": None}

    def test_fetch_rows_cierra_la_conexion(self, monkeypatch: pytest.MonkeyPatch) -> None:
        falsa = ConexionFalsa(FILAS_OK)
        monkeypatch.setattr(psycopg, "connect", lambda _: falsa)
        meters_mod._fetch_rows(DatabaseSettings(), None, True)
        assert falsa.cerrada


class TestLoadAmiGraph:
    def test_load_ami_graph_construye_las_seis_zonas(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """El ciclo completo dato → grafo, con las filas reales."""
        monkeypatch.setattr(meters_mod, "_fetch_rows", lambda *_: filas_de_topologia())
        grafo = load_ami_graph(GraphConfig(k=4))

        assert grafo.n_meters == 150
        assert grafo.n_zones == 6
        assert all(z.stats.n_components == 1 for z in grafo.zones.values())

    def test_load_ami_graph_reproduce_el_fiedler_de_la_enea(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """La misma cifra que fija test_builder, ahora por la ruta de la base."""
        monkeypatch.setattr(meters_mod, "_fetch_rows", lambda *_: filas_de_topologia())
        grafo = load_ami_graph()
        assert grafo.zones["la_enea"].stats.lambda_1 == pytest.approx(0.0901, abs=5e-5)


@pytest.mark.integration
class TestIntegracionPostgres:
    """Requiere PostgreSQL real. No corre en CI."""

    def test_la_base_coincide_con_la_topologia_versionada(self) -> None:
        """Detector de deriva entre `ami_meters` y `data/topologies/`.

        Si falla, la base cambió y las cifras de los docstrings dejaron de
        describir el padrón vivo. Hay que decidir si se reexporta la
        topología y se remiden las cifras, o si el cambio no debía estar.
        """
        de_la_base = load_meters(DatabaseSettings(postgres_host="localhost"))
        datos = json.loads(TOPOLOGIA.read_text(encoding="utf-8"))
        del_archivo = datos["meters"]

        assert len(de_la_base) == len(del_archivo)
        assert [m.device_id for m in de_la_base] == [m["device_id"] for m in del_archivo]
        for vivo, guardado in zip(de_la_base, del_archivo, strict=True):
            assert vivo.zona == guardado["zona"]
            assert vivo.lat == pytest.approx(guardado["lat"])
            assert vivo.lon == pytest.approx(guardado["lon"])

    def test_filtrar_por_zona_trae_solo_esa_zona(self) -> None:
        meters = load_meters(DatabaseSettings(postgres_host="localhost"), zonas=["la_enea"])
        assert {m.zona for m in meters} == {"la_enea"}
        assert len(meters) == 25
