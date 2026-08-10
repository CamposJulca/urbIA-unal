#!/usr/bin/env python3
"""Costo del ciclo de detección, y el intervalo que se deriva de él.

Mide cuánto tarda el servicio en recorrer las seis zonas —cerrar el bin,
armar la ventana densa, escanear y serializar— y aplica la regla de C6 para
elegir el intervalo con el que despierta.

Los criterios están en `CRITERIOS.md`, commiteados antes de esta corrida.
Acá no se declara ninguno: este archivo los aplica.

No necesita cluster: trabaja sobre los artefactos versionados.

Uso:

    python experiments/ciclo-deteccion/run.py --json results/medicion.json
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Final

import numpy as np

_REPO: Final = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "services" / "monitor-gsp" / "src"))

from urbia_monitor_gsp.detector import CollectiveScanDetector  # noqa: E402
from urbia_monitor_gsp.graph import (  # noqa: E402
    GraphConfig,
    MeterNode,
    build_ami_graph,
)
from urbia_monitor_gsp.service import graph_fingerprints, load_calibration  # noqa: E402
from urbia_monitor_gsp.stream import WindowConfig, ZoneWindow  # noqa: E402

TOPOLOGIA: Final = _REPO / "data" / "topologies" / "manizales_150.json"
PERFIL: Final = _REPO / "data" / "profiles" / "manizales_signal_v1.json"
CALIBRACION: Final = _REPO / "data" / "calibrations" / "manizales_scan_v1.json"

# C2 — repeticiones.
CICLOS: Final = 1000
CALENTAMIENTO: Final = 100

# C4 — régimen del productor actual: 150 medidores cada ~5 s.
MENSAJES_POR_SEGUNDO: Final = 30.0
MENSAJES_MEDIDOS: Final = 20000

# C6 — el ancho de bin que fijó `ventana-viva`, y el factor de la condición
# de viabilidad.
BIN_SEGUNDOS: Final = 6.0
FACTOR_VIABILIDAD: Final = 10.0
FACTOR_HOLGURA: Final = 20.0

SEMILLA: Final = 20260809


def percentiles(muestras: list[float]) -> dict[str, float]:
    """Estadísticos de una lista de duraciones en microsegundos.

    Args:
        muestras: Duraciones, en µs.

    Returns:
        p50, p95, p99, máximo y media.
    """
    ordenadas = sorted(muestras)
    return {
        "p50": statistics.median(ordenadas),
        "p95": ordenadas[int(0.95 * (len(ordenadas) - 1))],
        "p99": ordenadas[int(0.99 * (len(ordenadas) - 1))],
        "max": ordenadas[-1],
        "media": statistics.fmean(ordenadas),
        "n": float(len(ordenadas)),
    }


def medir_arranque() -> dict[str, Any]:
    """C5 — costo de dejar el servicio listo para el primer ciclo.

    Returns:
        Duraciones en milisegundos de cada etapa del arranque.
    """
    topologia = json.loads(TOPOLOGIA.read_text(encoding="utf-8"))
    medidores = [MeterNode(**m) for m in topologia["meters"]]

    t0 = time.perf_counter_ns()
    grafo = build_ami_graph(medidores, GraphConfig())
    t1 = time.perf_counter_ns()

    calibracion = load_calibration(CALIBRACION)
    detectores = {}
    for nombre, zona in grafo.zones.items():
        cal = calibracion.zones[nombre]
        det = CollectiveScanDetector(zona, cal.frozen.sigma_spatial, cal.frozen.config)
        det.load_threshold(cal.frozen)
        detectores[nombre] = det
    t2 = time.perf_counter_ns()

    return {
        "grafo_ms": (t1 - t0) / 1e6,
        "detectores_ms": (t2 - t1) / 1e6,
        "total_ms": (t2 - t0) / 1e6,
        "medidores": len(medidores),
        "zonas": len(grafo.zones),
    }


def _armar(
    grafo: Any, calibracion: Any
) -> tuple[dict[str, CollectiveScanDetector], dict[str, ZoneWindow], WindowConfig]:
    """Prepara detectores y ventanas de las seis zonas.

    Args:
        grafo: Grafo AMI construido.
        calibracion: Calibración versionada ya cargada.

    Returns:
        Detectores por zona, ventanas por zona y la configuración de ventana.
    """
    config_ventana = WindowConfig()
    detectores: dict[str, CollectiveScanDetector] = {}
    ventanas: dict[str, ZoneWindow] = {}
    for nombre, zona in grafo.zones.items():
        cal = calibracion.zones[nombre]
        det = CollectiveScanDetector(zona, cal.frozen.sigma_spatial, cal.frozen.config)
        det.load_threshold(cal.frozen)
        detectores[nombre] = det
        ventanas[nombre] = ZoneWindow(nombre, zona.device_ids, config_ventana)
    return detectores, ventanas, config_ventana


def _llenar(
    ventana: ZoneWindow,
    device_ids: tuple[str, ...],
    base: datetime,
    bins: int,
    config: WindowConfig,
    rng: np.random.Generator,
    sigma: float,
) -> None:
    """Llena `bins` bins consecutivos con una lectura por medidor.

    C1: todos los bins completos, que es el ciclo caro. Un bin incompleto
    corta antes de llegar al detector y costaría menos.

    Args:
        ventana: Acumulador de la zona.
        device_ids: Medidores de la zona.
        base: Instante del primer bin.
        bins: Cuántos bins llenar.
        config: Parámetros de la ventana.
        rng: Generador de la señal.
        sigma: Dispersión espacial de la zona.
    """
    for b in range(bins):
        instante = base + timedelta(seconds=b * config.bin_seconds)
        valores = rng.normal(220.0, sigma, size=len(device_ids))
        for device_id, valor in zip(device_ids, valores.tolist(), strict=True):
            ventana.observe(device_id, instante, valor)


def medir_ingesta(grafo: Any, calibracion: Any) -> dict[str, Any]:
    """C4 — costo de `observe` por mensaje.

    Args:
        grafo: Grafo AMI construido.
        calibracion: Calibración versionada.

    Returns:
        µs por mensaje y fracción de segundo que consume a 30 msg/s.
    """
    rng = np.random.default_rng(SEMILLA)
    nombre, zona = next(iter(grafo.zones.items()))
    config = WindowConfig()
    sigma = calibracion.zones[nombre].frozen.sigma_spatial

    ventana = ZoneWindow(nombre, zona.device_ids, config)
    base = datetime(2026, 8, 9, 12, 0, 0, tzinfo=UTC)
    valores = rng.normal(220.0, sigma, size=MENSAJES_MEDIDOS)

    # Cada mensaje a un bin distinto de a poco, para no medir sólo el camino
    # de "celda ya ocupada", que es más barato.
    t0 = time.perf_counter_ns()
    for i, valor in enumerate(valores.tolist()):
        instante = base + timedelta(seconds=(i // len(zona.device_ids)) * config.bin_seconds)
        ventana.observe(zona.device_ids[i % len(zona.device_ids)], instante, valor)
    total_ns = time.perf_counter_ns() - t0

    us_por_mensaje = total_ns / MENSAJES_MEDIDOS / 1e3
    return {
        "us_por_mensaje": us_por_mensaje,
        "mensajes_por_segundo": MENSAJES_POR_SEGUNDO,
        "fraccion_de_segundo": us_por_mensaje * MENSAJES_POR_SEGUNDO / 1e6,
        "mensajes_medidos": MENSAJES_MEDIDOS,
    }


def medir_ciclos(grafo: Any, calibracion: Any) -> dict[str, Any]:
    """C2 y C3 — duración del ciclo completo y de cada componente.

    Args:
        grafo: Grafo AMI construido.
        calibracion: Calibración versionada.

    Returns:
        Estadísticos del ciclo, de cada componente y de cada zona.
    """
    rng = np.random.default_rng(SEMILLA)
    detectores, ventanas, config = _armar(grafo, calibracion)
    nombres = list(grafo.zone_order or sorted(grafo.zones))

    # Una ventana llena por zona, y el reloj parado en el instante en que el
    # último bin ya cerró. Se reconstruye por ciclo para que `emit` haga en
    # cada repetición el mismo trabajo que hace en operación.
    base = datetime(2026, 8, 9, 12, 0, 0, tzinfo=UTC)
    ahora = base + timedelta(
        seconds=config.bin_seconds * config.window_bins + config.close_grace_seconds + 1.0
    )

    ciclo: list[float] = []
    por_componente: dict[str, list[float]] = {"emit": [], "detect": [], "serializar": []}
    por_zona: dict[str, list[float]] = {n: [] for n in nombres}

    for repeticion in range(CALENTAMIENTO + CICLOS):
        # Ventanas nuevas cada vez: `emit` marca el bin como emitido y no lo
        # vuelve a entregar.
        for nombre in nombres:
            zona = grafo.zones[nombre]
            ventanas[nombre] = ZoneWindow(nombre, zona.device_ids, config)
            _llenar(
                ventanas[nombre],
                zona.device_ids,
                base,
                config.window_bins,
                config,
                rng,
                calibracion.zones[nombre].frozen.sigma_spatial,
            )

        medir = repeticion >= CALENTAMIENTO
        inicio_ciclo = time.perf_counter_ns()
        acumulado = {"emit": 0, "detect": 0, "serializar": 0}

        for nombre in nombres:
            t0 = time.perf_counter_ns()
            ventana = ventanas[nombre].emit(ahora)
            t1 = time.perf_counter_ns()
            if ventana is None:
                raise RuntimeError(f"'{nombre}' no emitió ventana: la medición no es válida")
            detecciones = detectores[nombre].detect(ventana.matrix)
            t2 = time.perf_counter_ns()
            json.dumps([d.to_dict() for d in detecciones])
            t3 = time.perf_counter_ns()

            acumulado["emit"] += t1 - t0
            acumulado["detect"] += t2 - t1
            acumulado["serializar"] += t3 - t2
            if medir:
                por_zona[nombre].append((t2 - t0) / 1e3)

        total = time.perf_counter_ns() - inicio_ciclo
        if medir:
            ciclo.append(total / 1e3)
            for clave, valor in acumulado.items():
                por_componente[clave].append(valor / 1e3)

    return {
        "ciclo_us": percentiles(ciclo),
        "componentes_us": {k: percentiles(v) for k, v in por_componente.items()},
        "zonas_us": {
            nombre: {
                **percentiles(valores),
                "n_meters": grafo.zones[nombre].n_meters,
                "n_candidates": detectores[nombre].n_candidates,
            }
            for nombre, valores in por_zona.items()
        },
        "ciclos": CICLOS,
        "calentamiento": CALENTAMIENTO,
    }


def medir_payload(grafo: Any, calibracion: Any) -> dict[str, Any]:
    """POSTERIOR a `CRITERIOS.md` — tamaño del payload contra `top_k`.

    **No participa del veredicto de C6**, que sale de la duración del ciclo
    y tiene tres órdenes de margen. Se agrega porque la corrida mostró que
    serializar cuesta tanto como escanear —26,2 % del ciclo— y porque el
    defecto de `top_k` del publicador hay que elegirlo con una cifra.

    Args:
        grafo: Grafo AMI construido.
        calibracion: Calibración versionada.

    Returns:
        Bytes por detección y por ciclo de seis zonas, para cada `top_k`.
    """
    rng = np.random.default_rng(SEMILLA)
    detectores, _, config = _armar(grafo, calibracion)
    nombres = list(grafo.zone_order or sorted(grafo.zones))

    detecciones = {}
    for nombre in nombres:
        zona = grafo.zones[nombre]
        sigma = calibracion.zones[nombre].frozen.sigma_spatial
        senal = rng.normal(220.0, sigma, size=(config.window_bins, zona.n_meters))
        (deteccion,) = detectores[nombre].detect(senal)
        detecciones[nombre] = deteccion

    resultado: dict[str, Any] = {}
    for etiqueta, top_k in (("0", 0), ("1", 1), ("5", 5), ("10", 10), ("completo", None)):
        tamanos = {
            nombre: len(json.dumps(d.to_dict(top_k=top_k), ensure_ascii=False).encode("utf-8"))
            for nombre, d in detecciones.items()
        }
        resultado[etiqueta] = {
            "bytes_por_deteccion_max": max(tamanos.values()),
            "bytes_por_ciclo": sum(tamanos.values()),
        }
    return resultado


def elegir_intervalo(p99_us: float) -> dict[str, Any]:
    """C6 — aplica la regla de elección del intervalo.

    Args:
        p99_us: p99 de la duración del ciclo, en microsegundos.

    Returns:
        El veredicto: si el ciclo cabe, el intervalo elegido y por qué.
    """
    c = p99_us / 1e6
    viable = c <= BIN_SEGUNDOS / FACTOR_VIABILIDAD
    if not viable:
        return {
            "viable": False,
            "p99_s": c,
            "limite_viabilidad_s": BIN_SEGUNDOS / FACTOR_VIABILIDAD,
            "intervalo_s": None,
            "motivo": (
                "el ciclo no cabe: hay que repartir las zonas entre procesos o "
                "subir el ancho de bin"
            ),
        }

    techo = BIN_SEGUNDOS / 2.0
    piso = FACTOR_HOLGURA * c
    # `t = b/k` con k entero: se recorre k creciente y se toma el mayor t
    # que respete los dos límites.
    candidatos = [BIN_SEGUNDOS / k for k in range(2, 61)]
    admisibles = [t for t in candidatos if t <= techo and t >= piso]
    if admisibles:
        intervalo = max(admisibles)
        regla = "t = b/k, el mayor con t <= b/2 y t >= 20c"
    else:
        intervalo = techo
        regla = "20c > b/2: gana t = b/2 (C6.3)"

    return {
        "viable": True,
        "p99_s": c,
        "limite_viabilidad_s": BIN_SEGUNDOS / FACTOR_VIABILIDAD,
        "techo_s": techo,
        "piso_s": piso,
        "intervalo_s": intervalo,
        "k": BIN_SEGUNDOS / intervalo,
        "fraccion_del_intervalo": c / intervalo,
        "latencia_agregada_s": intervalo,
        "span_ventana_s": BIN_SEGUNDOS * 16,
        "latencia_sobre_span": intervalo / (BIN_SEGUNDOS * 16),
        "regla": regla,
    }


def main() -> int:
    """Punto de entrada.

    Returns:
        Código de salida del proceso.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, default=None, help="destino de los datos crudos")
    args = parser.parse_args()

    topologia = json.loads(TOPOLOGIA.read_text(encoding="utf-8"))
    grafo = build_ami_graph([MeterNode(**m) for m in topologia["meters"]], GraphConfig())
    calibracion = load_calibration(CALIBRACION)
    # La misma verificación bloqueante que hace el servicio: medir el costo
    # de un ciclo que no corresponde al grafo calibrado no mediría nada.
    calibracion.verify_topology(graph_fingerprints(grafo))

    print(f"topología {topologia.get('version', '?')}, calibración {calibracion.version}")
    print(f"{CICLOS} ciclos medidos, {CALENTAMIENTO} de calentamiento descartados")
    print()

    arranque = medir_arranque()
    ingesta = medir_ingesta(grafo, calibracion)
    ciclos = medir_ciclos(grafo, calibracion)
    payload = medir_payload(grafo, calibracion)
    veredicto = elegir_intervalo(ciclos["ciclo_us"]["p99"])

    print("ciclo completo, seis zonas (µs)")
    for clave in ("p50", "p95", "p99", "max"):
        print(f"  {clave:<4} {ciclos['ciclo_us'][clave]:>10.1f}")
    print()

    print(f"{'componente':<12} {'p50':>10} {'p99':>10} {'% del p50':>10}")
    total_p50 = ciclos["ciclo_us"]["p50"]
    for nombre, datos in ciclos["componentes_us"].items():
        print(
            f"{nombre:<12} {datos['p50']:>10.1f} {datos['p99']:>10.1f} "
            f"{datos['p50'] / total_p50:>9.1%}"
        )
    print()

    print(f"{'zona':<15} {'n':>3} {'bolas':>6} {'p50 µs':>9} {'p99 µs':>9}")
    for nombre, datos in ciclos["zonas_us"].items():
        print(
            f"{nombre:<15} {datos['n_meters']:>3} {datos['n_candidates']:>6} "
            f"{datos['p50']:>9.1f} {datos['p99']:>9.1f}"
        )
    print()

    print(f"{'top_k':<10} {'B/detección':>12} {'B/ciclo':>10}   (posterior a CRITERIOS)")
    for etiqueta, datos in payload.items():
        print(
            f"{etiqueta:<10} {datos['bytes_por_deteccion_max']:>12} "
            f"{datos['bytes_por_ciclo']:>10}"
        )
    print()

    print(f"arranque: {arranque['total_ms']:.1f} ms "
          f"(grafo {arranque['grafo_ms']:.1f}, detectores {arranque['detectores_ms']:.1f})")
    print(f"ingesta:  {ingesta['us_por_mensaje']:.2f} µs/mensaje, "
          f"{ingesta['fraccion_de_segundo']:.4%} de cada segundo a "
          f"{ingesta['mensajes_por_segundo']:.0f} msg/s")
    print()

    if veredicto["viable"]:
        print(
            f"C6: p99 = {veredicto['p99_s'] * 1e3:.3f} ms <= "
            f"{veredicto['limite_viabilidad_s'] * 1e3:.0f} ms — el ciclo cabe"
        )
        print(f"    intervalo = {veredicto['intervalo_s']:g} s ({veredicto['regla']})")
        print(f"    el ciclo consume el {veredicto['fraccion_del_intervalo']:.4%} del intervalo")
        print(
            f"    latencia agregada {veredicto['latencia_agregada_s']:g} s sobre una "
            f"ventana de {veredicto['span_ventana_s']:g} s "
            f"({veredicto['latencia_sobre_span']:.1%})"
        )
    else:
        print(f"C6: {veredicto['motivo']}")

    if args.json is not None:
        destino = args.json if args.json.is_absolute() else Path(__file__).parent / args.json
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(
            json.dumps(
                {
                    "topologia": topologia.get("version"),
                    "calibracion": calibracion.version,
                    "arranque": arranque,
                    "ingesta": ingesta,
                    "payload_posterior": payload,
                    **ciclos,
                    "veredicto": veredicto,
                },
                indent=2,
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"\nescrito: {destino}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
