"""Tests del CLI: el modo en que un experimento fija su material de una vez."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from conftest import ESQUEMA, PERFIL, SEMILLA, TOPOLOGIA
from urbia_events.cli import main
from urbia_events.types import InvalidSpecError


def escribir_spec(tmp_path: Path, **cambios: object) -> Path:
    """Deja una especificación en un árbol con la estructura del repositorio.

    El CLI resuelve las rutas contra la raíz, que deduce como
    `spec.resolve().parents[2]`, así que la especificación tiene que vivir
    dos niveles por debajo.
    """
    raiz = tmp_path / "experiments" / "prueba"
    raiz.mkdir(parents=True)
    for ruta_relativa, origen in (
        ("data/topologies/manizales_150.json", TOPOLOGIA),
        ("data/schemas/payload_schema_v1.json", ESQUEMA),
        ("data/profiles/manizales_signal_v1.json", PERFIL),
    ):
        objetivo = tmp_path / ruta_relativa
        objetivo.parent.mkdir(parents=True, exist_ok=True)
        objetivo.write_bytes(origen.read_bytes())

    spec: dict[str, object] = {
        "topologia": "data/topologies/manizales_150.json",
        "esquema": "data/schemas/payload_schema_v1.json",
        "perfil": "data/profiles/manizales_signal_v1.json",
        "seed": SEMILLA,
        "n_instantes": 12,
        "zonas": ["centro"],
        "eventos": [
            {"magnitude": "voltaje_v", "depth": 1, "sigma_multiple": 1.0, "start": 4, "duration": 3}
        ],
    }
    spec.update(cambios)
    destino = raiz / "spec.json"
    destino.write_text(json.dumps(spec), encoding="utf-8")
    return destino


class TestCli:
    def test_escribe_los_cuatro_artefactos(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        spec = escribir_spec(tmp_path)
        salida = tmp_path / "salida"
        monkeypatch.setattr(
            "sys.argv", ["urbia-inject", "--spec", str(spec), "--salida", str(salida)]
        )
        assert main() == 0
        for nombre in ("base_centro.npy", "senal_centro.npy", "verdad_centro.json", "resumen.json"):
            assert (salida / nombre).exists(), nombre

    def test_delta_reconstruye_la_base_desde_los_archivos(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """La invariante 1 del SCHEMA, verificada sobre lo que quedó en disco."""
        spec = escribir_spec(tmp_path)
        salida = tmp_path / "salida"
        monkeypatch.setattr(
            "sys.argv", ["urbia-inject", "--spec", str(spec), "--salida", str(salida)]
        )
        main()

        base = np.load(salida / "base_centro.npy")
        senal = np.load(salida / "senal_centro.npy")
        verdad = json.loads((salida / "verdad_centro.json").read_text(encoding="utf-8"))

        reconstruida = senal.copy()
        for evento in verdad["events"]:
            fin = evento["start"] + evento["duration"]
            reconstruida[evento["start"] : fin][:, evento["node_indices"]] -= np.array(
                evento["delta"]
            )
        np.testing.assert_allclose(reconstruida, base, atol=1e-12)

    def test_el_resumen_registra_la_semilla_y_el_perfil(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Un año después hay que poder decir contra qué perfil se generó."""
        spec = escribir_spec(tmp_path)
        salida = tmp_path / "salida"
        monkeypatch.setattr(
            "sys.argv", ["urbia-inject", "--spec", str(spec), "--salida", str(salida)]
        )
        main()
        resumen = json.loads((salida / "resumen.json").read_text(encoding="utf-8"))
        assert resumen["seed"] == SEMILLA
        assert resumen["perfil"] == "manizales-signal-v1"
        assert resumen["zonas"][0]["zona"] == "centro"

    def test_sin_zonas_declaradas_procesa_las_seis(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        spec = escribir_spec(tmp_path, zonas=None, n_instantes=8)
        salida = tmp_path / "salida"
        monkeypatch.setattr(
            "sys.argv", ["urbia-inject", "--spec", str(spec), "--salida", str(salida)]
        )
        main()
        resumen = json.loads((salida / "resumen.json").read_text(encoding="utf-8"))
        assert len(resumen["zonas"]) == 6

    def test_una_zona_inexistente_levanta_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        spec = escribir_spec(tmp_path, zonas=["marte"])
        salida = tmp_path / "salida"
        monkeypatch.setattr(
            "sys.argv", ["urbia-inject", "--spec", str(spec), "--salida", str(salida)]
        )
        with pytest.raises(InvalidSpecError, match="marte"):
            main()

    def test_dos_corridas_con_la_misma_spec_dan_lo_mismo(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        spec = escribir_spec(tmp_path)
        for nombre in ("una", "otra"):
            monkeypatch.setattr(
                "sys.argv",
                ["urbia-inject", "--spec", str(spec), "--salida", str(tmp_path / nombre)],
            )
            main()
        np.testing.assert_array_equal(
            np.load(tmp_path / "una" / "senal_centro.npy"),
            np.load(tmp_path / "otra" / "senal_centro.npy"),
        )
