"""Generación por lotes de datasets de eventos, con su verdad al lado.

Lee una especificación JSON, construye el grafo AMI desde una topología
versionada, inyecta los eventos declarados y escribe a disco la señal
modificada y la verdad de referencia.

Es el modo en que un experimento produce su material de una vez y lo deja
fijo: el detector se puntúa después, contra archivos, sin volver a generar
nada.

    urbia-inject --spec spec.json --salida /tmp/dataset
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
from urbia_monitor_gsp.graph import AmiGraph, GraphConfig, MeterNode, build_ami_graph

from .bounds import load_bounds
from .injector import EventInjector
from .profile import SignalProfile, load_profile
from .types import CollectiveDeviationSpec, InvalidSpecError, Magnitude, device_type_of


def _cargar_topologia(path: Path) -> list[MeterNode]:
    """Lee los medidores de una topología versionada.

    Args:
        path: Ruta al JSON de topología.

    Returns:
        Los medidores como nodos del grafo.
    """
    datos = json.loads(path.read_text(encoding="utf-8"))
    return [MeterNode(**m) for m in datos["meters"]]


def _senal_base(
    n_instantes: int,
    n_medidores: int,
    magnitude: Magnitude,
    device_id: str,
    profile: SignalProfile,
    semilla: int,
) -> np.ndarray:
    """Señal de fondo con la media y la dispersión espacial medidas.

    No es telemetría real, pero reproduce el estadístico que decide si una
    desviación es sutil. La telemetría real entra cuando el experimento la
    consuma de `ami_telemetry`.

    Args:
        n_instantes: Instantes a generar.
        n_medidores: Medidores de la zona.
        magnitude: Magnitud a simular.
        device_id: Un medidor de la zona, para deducir el tipo.
        profile: Perfil medido.
        semilla: Semilla del ruido.

    Returns:
        Matriz `(n_instantes, n_medidores)`.
    """
    p = profile.get(magnitude, device_type_of(device_id))
    rng = np.random.default_rng(semilla)
    return np.asarray(rng.normal(p.mean, p.sigma_spatial, size=(n_instantes, n_medidores)))


def _specs_de(bloque: list[dict[str, Any]]) -> list[CollectiveDeviationSpec]:
    """Construye las especificaciones desde el JSON.

    Args:
        bloque: Lista de eventos declarados.

    Returns:
        Las especificaciones ya validadas.
    """
    return [CollectiveDeviationSpec(**evento) for evento in bloque]


def _procesar_zona(
    grafo: AmiGraph,
    zona: str,
    spec_json: dict[str, Any],
    inyector: EventInjector,
    profile: SignalProfile,
    salida: Path,
) -> dict[str, Any]:
    """Inyecta los eventos de una zona y escribe sus artefactos.

    Args:
        grafo: Grafo AMI completo.
        zona: Zona a procesar.
        spec_json: Especificación completa leída del JSON.
        inyector: Inyector configurado.
        profile: Perfil medido.
        salida: Directorio de salida.

    Returns:
        Resumen de lo escrito para esa zona.
    """
    z = grafo.zones[zona]
    n_instantes = int(spec_json.get("n_instantes", 1))
    specs = _specs_de(spec_json["eventos"])
    magnitud: Magnitude = specs[0].magnitude

    base = _senal_base(n_instantes, z.n_meters, magnitud, z.device_ids[0], profile, inyector.seed)
    senal, verdad = inyector.inject(
        z, base, specs, on_violation=spec_json.get("on_violation", "raise")
    )

    np.save(salida / f"senal_{zona}.npy", senal)
    np.save(salida / f"base_{zona}.npy", base)
    (salida / f"verdad_{zona}.json").write_text(
        json.dumps(verdad.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return {
        "zona": zona,
        "medidores": z.n_meters,
        "instantes": n_instantes,
        "eventos": len(verdad.events),
        "nodos_afectados": sorted({d for e in verdad.events for d in e.device_ids}),
    }


def main() -> int:
    """Genera el dataset declarado en la especificación.

    Returns:
        Código de salida del proceso.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--salida", type=Path, required=True)
    args = parser.parse_args()

    spec_json = json.loads(args.spec.read_text(encoding="utf-8"))
    raiz = args.spec.resolve().parents[2]

    profile = load_profile(raiz / spec_json["perfil"])
    bounds = load_bounds(raiz / spec_json["esquema"])
    grafo = build_ami_graph(_cargar_topologia(raiz / spec_json["topologia"]), GraphConfig())
    inyector = EventInjector(profile, bounds, seed=int(spec_json["seed"]))

    args.salida.mkdir(parents=True, exist_ok=True)
    zonas = spec_json.get("zonas") or list(grafo.zone_order)
    desconocidas = [z for z in zonas if z not in grafo.zones]
    if desconocidas:
        raise InvalidSpecError(f"zonas ausentes del grafo: {desconocidas}")

    resumen = [
        _procesar_zona(grafo, zona, spec_json, inyector, profile, args.salida) for zona in zonas
    ]

    (args.salida / "resumen.json").write_text(
        json.dumps(
            {"seed": inyector.seed, "perfil": profile.version, "zonas": resumen},
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    for fila in resumen:
        print(
            f"{fila['zona']:<14} {fila['eventos']} evento(s), "
            f"{len(fila['nodos_afectados'])} de {fila['medidores']} medidores afectados"
        )
    print(f"\nescrito en {args.salida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
