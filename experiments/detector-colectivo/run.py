#!/usr/bin/env python3
"""Evaluación del detector: punto de operación, radios, τ y confusión por nodo.

Mide sobre `urbia_monitor_gsp.detector` lo que el módulo dejó abierto, y
revisa el punto de operación que el experimento anterior había fijado en
N=32. Si a N=32 la ventaja sobre el umbral es nula y donde el método aporta
es en N≤2, entonces ese N optimizaba el objetivo equivocado.

# CRITERIOS, DECLARADOS ANTES DE MIRAR LOS RESULTADOS

Se commitean **antes** de correr, como en `experiments/magnitud-duracion/`.

**D1 — El objetivo es la VENTAJA, no la detección.** El punto de operación
se elige por el N donde el escaneo más supera al umbral por medidor, no por
el N donde más detecta. Son dos objetivos distintos y se persigue el
primero explícitamente: el segundo ya está resuelto por un método más
barato.

**D2 — Ventaja = `tasa_escaneo − tasa_umbral`.** Diferencia absoluta, no
cociente. La diferencia se traduce a eventos capturados por cada cien; el
cociente premia regímenes donde los dos métodos detectan casi nada, que es
justo el defecto que se detectó en C5 del experimento anterior.

**D3 — Piso de utilidad: el escaneo tiene que detectar al menos el 50 %.**
Un régimen con ventaja grande y detección baja no es un punto de operación:
es una curiosidad. Entre los N que pasan el piso, gana el de mayor ventaja.

**D4 — Se reporta también el N de máxima detección**, para que la distancia
entre los dos objetivos quede a la vista y no escondida en la elección.

**D5 — El barrido de τ excede el rango estable de filtrado.** La grilla va
de 0,05 a 20 y el rango estable medido es `[0,447, 2,239]`. Se declara de
antemano que **el resultado de interés es si el óptimo de detección cae
dentro o fuera de ese rango**, en cualquiera de los dos sentidos: si cae
fuera, el parámetro que el Afinador debe ajustar depende de para qué se use
el filtro, y eso es un resultado propio.

**D6 — La ventana deslizante es la configuración realista.** Se reporta
cuánto cuesta contra la ventana conocida, que es lo que suponían los
experimentos anteriores y que inflaba sus cifras.

**D7 — Las comparaciones secundarias corren en el punto de máxima
resolución**, definido como el `(σ, N)` donde la configuración de
referencia detecta más cerca del 50 %. *Agregado tras la primera corrida,
que dejó las cuatro comparaciones secundarias en 100 % y por lo tanto sin
poder distinguir nada.* No toca el punto de operación, que lo eligen D1 a
D3 y no cambia: D7 sólo dice **dónde se miden** las comparaciones entre
configuraciones. Un punto saturado no puede separar dos radios ni dos
valores de τ, y medir ahí no es un resultado sino una ceguera.

Uso:

    python experiments/detector-colectivo/run.py --json results/medicion.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Final

import numpy as np
import numpy.typing as npt

_REPO: Final = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "services" / "monitor-gsp" / "src"))
sys.path.insert(0, str(_REPO / "services" / "event-injector" / "src"))

from urbia_events import (  # noqa: E402
    CollectiveDeviationSpec,
    EventInjector,
    device_type_of,
    load_bounds,
    load_profile,
)
from urbia_monitor_gsp.detector import (  # noqa: E402
    CollectiveScanDetector,
    DetectorConfig,
    candidate_balls,
    confusion_matrix,
    contrasts,
    k_hop_indices,
)
from urbia_monitor_gsp.graph import (  # noqa: E402
    GraphConfig,
    MeterNode,
    ZoneGraph,
    build_ami_graph,
)

TOPOLOGIA: Final = _REPO / "data" / "topologies" / "manizales_150.json"
ESQUEMA: Final = _REPO / "data" / "schemas" / "payload_schema_v1.json"
PERFIL: Final = _REPO / "data" / "profiles" / "manizales_signal_v1.json"

SEMILLA: Final = 20260808
MAGNITUD: Final = "voltaje_v"
DEPTH: Final = 2
N_ENSAYOS: Final = 300

VENTANAS: Final = (1, 2, 4, 8, 16, 32, 64)
SIGMAS: Final = (0.5, 1.0, 1.5)
RADIOS: Final = ((1,), (1, 2), (1, 2, 3))
TAUS: Final = (0.05, 0.1, 0.25, 0.447, 0.75, 1.0, 1.5, 2.239, 3.0, 5.0, 10.0, 20.0)
RANGO_ESTABLE: Final = (0.447, 2.239)
SIGMA_INDIVIDUAL: Final = 6.0

FPR_OBJETIVO: Final = 0.01
PISO_UTILIDAD: Final = 0.50   # D3


def cargar() -> tuple[Any, Any, Any]:
    """Carga grafo, perfil y límites.

    Returns:
        Tupla `(grafo, perfil, limites)`.
    """
    datos = json.loads(TOPOLOGIA.read_text(encoding="utf-8"))
    meters = [MeterNode(**m) for m in datos["meters"]]
    return (
        build_ami_graph(meters, GraphConfig()),
        load_profile(PERFIL),
        load_bounds(ESQUEMA),
    )


def deltas_por_semilla(
    zone: ZoneGraph, perfil: Any, limites: Any, sigma_multiple: float, depth: int = DEPTH
) -> npt.NDArray[np.float64]:
    """Desviación que aplica el inyector con cada nodo como semilla.

    Args:
        zone: Subgrafo zonal.
        perfil: Perfil de señal.
        limites: Límites del esquema.
        sigma_multiple: Magnitud de la desviación.
        depth: Profundidad del vecindario.

    Returns:
        Matriz `(n, n)`: la fila `j` es la desviación con semilla `j`.
    """
    inyector = EventInjector(perfil, limites, seed=SEMILLA)
    salida = np.zeros((zone.n_meters, zone.n_meters))
    for j, device_id in enumerate(zone.device_ids):
        senal, _ = inyector.inject(
            zone,
            np.zeros(zone.n_meters),
            [
                CollectiveDeviationSpec(
                    magnitude=MAGNITUD,
                    depth=depth,
                    sigma_multiple=sigma_multiple,
                    seed_device_id=device_id,
                )
            ],
        )
        salida[j] = senal[0]
    return salida


def _tasas(
    zone: ZoneGraph,
    p: Any,
    deltas: npt.NDArray[np.float64],
    ventana: int,
    radios: tuple[int, ...],
    tau: float | None,
    rng: np.random.Generator,
) -> tuple[float, float]:
    """Tasa de detección del escaneo y del umbral, misma señal para los dos.

    Args:
        zone: Subgrafo zonal.
        p: Perfil de la magnitud.
        deltas: Desviaciones por semilla.
        ventana: Instantes a integrar.
        radios: Radios del escaneo.
        tau: τ del prefiltro, o `None`.
        rng: Generador.

    Returns:
        Par `(tasa_escaneo, tasa_umbral)`.
    """
    n = zone.n_meters
    config = DetectorConfig(
        window=ventana, scan_radii=radios, prefilter_tau=tau, calibration_samples=1000
    )
    detector = CollectiveScanDetector(zone, p.sigma_spatial, config)
    detector.calibrate(SEMILLA)

    limpio = rng.normal(p.mean, p.sigma_spatial, size=(N_ENSAYOS, ventana, n))
    semillas = np.arange(N_ENSAYOS) % n
    con_evento = limpio + deltas[semillas][:, None, :]

    escaneo = float(np.mean([detector.detect(x)[0].detected for x in con_evento]))

    sigma_eff = p.sigma_spatial / np.sqrt(ventana)
    umbral_neg = np.abs(limpio.mean(axis=1) - p.mean).max(axis=1) / sigma_eff
    umbral_pos = np.abs(con_evento.mean(axis=1) - p.mean).max(axis=1) / sigma_eff
    corte = float(np.quantile(umbral_neg, 1.0 - FPR_OBJETIVO))
    return escaneo, float((umbral_pos > corte).mean())


# ───────────────────────────────────── M1. curva de ventaja contra N


def medir_ventaja(grafo: Any, perfil: Any, limites: Any) -> list[dict[str, Any]]:
    """Barre N y mide la ventaja del escaneo sobre el umbral.

    Args:
        grafo: Grafo AMI.
        perfil: Perfil de señal.
        limites: Límites del esquema.

    Returns:
        Una fila por zona, magnitud y ventana.
    """
    filas: list[dict[str, Any]] = []
    for zona_nombre in grafo.zone_order:
        zona = grafo.zones[zona_nombre]
        p = perfil.get(MAGNITUD, device_type_of(zona.device_ids[0]))
        for sigma in SIGMAS:
            deltas = deltas_por_semilla(zona, perfil, limites, sigma)
            for ventana in VENTANAS:
                rng = np.random.default_rng([SEMILLA, ventana, int(sigma * 100)])
                escaneo, umbral = _tasas(zona, p, deltas, ventana, (1, 2), None, rng)
                filas.append(
                    {
                        "zona": zona_nombre,
                        "sigma_multiple": sigma,
                        "ventana": ventana,
                        "tasa_escaneo": escaneo,
                        "tasa_umbral": umbral,
                        "ventaja": escaneo - umbral,
                    }
                )
        print(f"  ventaja: {zona_nombre} listo")
    return filas


# ─────────────────────────────────────────────── M2. ventana deslizante


def medir_deslizante(
    grafo: Any, perfil: Any, limites: Any, ventana: int, sigma: float
) -> list[dict[str, Any]]:
    """Cuánto cuesta no saber dónde está el evento.

    La señal dura cuatro ventanas y el evento ocupa una. Se prueba con el
    evento alineado al borde de ventana y desplazado media ventana, que es
    el peor caso: ninguna ventana lo cubre entero.

    Args:
        grafo: Grafo AMI.
        perfil: Perfil de señal.
        limites: Límites del esquema.
        ventana: Ancho de la ventana.

    Returns:
        Una fila por zona y alineación.
    """
    filas: list[dict[str, Any]] = []
    for zona_nombre in grafo.zone_order:
        zona = grafo.zones[zona_nombre]
        p = perfil.get(MAGNITUD, device_type_of(zona.device_ids[0]))
        deltas = deltas_por_semilla(zona, perfil, limites, sigma)
        n = zona.n_meters
        total = 4 * ventana

        config = DetectorConfig(
            window=ventana, step=1, scan_radii=(1, 2), calibration_samples=1000
        )
        detector = CollectiveScanDetector(zona, p.sigma_spatial, config)
        detector.calibrate(SEMILLA)

        rng = np.random.default_rng([SEMILLA, 77, ventana])
        limpio = rng.normal(p.mean, p.sigma_spatial, size=(N_ENSAYOS, total, n))
        semillas = np.arange(N_ENSAYOS) % n

        # Falsos positivos por señal: cualquier ventana que dispare sin evento.
        fpr = float(np.mean([any(d.detected for d in detector.detect(x)) for x in limpio]))

        for etiqueta, inicio in (("alineado", ventana), ("desplazado", ventana + ventana // 2)):
            con_evento = limpio.copy()
            for i in range(N_ENSAYOS):
                con_evento[i, inicio : inicio + ventana] += deltas[semillas[i]]
            aciertos = 0
            for i in range(N_ENSAYOS):
                for d in detector.detect(con_evento[i]):
                    if d.detected and d.window_start < inicio + ventana and d.window_end > inicio:
                        aciertos += 1
                        break
            filas.append(
                {
                    "zona": zona_nombre,
                    "ventana": ventana,
                    "alineacion": etiqueta,
                    "tasa_deslizante": aciertos / N_ENSAYOS,
                    "fpr_por_senal": fpr,
                }
            )
        print(f"  deslizante: {zona_nombre} listo")
    return filas


# ──────────────────────────────────────────────────────── M3. radios


def medir_radios(
    grafo: Any, perfil: Any, limites: Any, ventana: int, sigma: float
) -> list[dict[str, Any]]:
    """Detección y recall por nodo según los radios que escanea.

    Args:
        grafo: Grafo AMI.
        perfil: Perfil de señal.
        limites: Límites del esquema.
        ventana: Ancho de la ventana.

    Returns:
        Una fila por zona y conjunto de radios.
    """
    filas: list[dict[str, Any]] = []
    for zona_nombre in grafo.zone_order:
        zona = grafo.zones[zona_nombre]
        p = perfil.get(MAGNITUD, device_type_of(zona.device_ids[0]))
        deltas = deltas_por_semilla(zona, perfil, limites, sigma)
        n = zona.n_meters
        grupos = [k_hop_indices(zona.adjacency, j, DEPTH) for j in range(n)]

        for radios in RADIOS:
            config = DetectorConfig(
                window=ventana, scan_radii=radios, calibration_samples=1000
            )
            detector = CollectiveScanDetector(zona, p.sigma_spatial, config)
            detector.calibrate(SEMILLA)

            rng = np.random.default_rng([SEMILLA, 55, len(radios)])
            limpio = rng.normal(p.mean, p.sigma_spatial, size=(N_ENSAYOS, ventana, n))
            semillas = np.arange(N_ENSAYOS) % n
            con_evento = limpio + deltas[semillas][:, None, :]

            predicho = np.zeros((N_ENSAYOS, n), dtype=bool)
            verdadero = np.zeros((N_ENSAYOS, n), dtype=bool)
            detectadas = 0
            for i in range(N_ENSAYOS):
                d = detector.detect(con_evento[i])[0]
                detectadas += int(d.detected)
                predicho[i, list(d.node_indices)] = True
                verdadero[i, list(grupos[semillas[i]])] = True

            m = confusion_matrix(predicho, verdadero)
            filas.append(
                {
                    "zona": zona_nombre,
                    "radios": list(radios),
                    "candidatos": detector.n_candidates,
                    "tasa_deteccion": detectadas / N_ENSAYOS,
                    **m.to_dict(),
                }
            )
        print(f"  radios: {zona_nombre} listo")
    return filas


# ───────────────────────────────────────────────────── M4. barrido de τ


def medir_tau(
    grafo: Any, perfil: Any, limites: Any, ventana: int, sigma: float
) -> list[dict[str, Any]]:
    """Detección en función de τ del Difuminador, más el caso sin filtro.

    Args:
        grafo: Grafo AMI.
        perfil: Perfil de señal.
        limites: Límites del esquema.
        ventana: Ancho de la ventana.

    Returns:
        Una fila por zona y τ, con `None` para el caso sin filtro.
    """
    filas: list[dict[str, Any]] = []
    for zona_nombre in grafo.zone_order:
        zona = grafo.zones[zona_nombre]
        p = perfil.get(MAGNITUD, device_type_of(zona.device_ids[0]))
        deltas = deltas_por_semilla(zona, perfil, limites, sigma)
        for tau in (None, *TAUS):
            rng = np.random.default_rng([SEMILLA, 33, int((tau or 0) * 1000)])
            escaneo, umbral = _tasas(zona, p, deltas, ventana, (1, 2), tau, rng)
            filas.append(
                {
                    "zona": zona_nombre,
                    "tau": tau,
                    "tasa_escaneo": escaneo,
                    "tasa_umbral": umbral,
                }
            )
        print(f"  tau: {zona_nombre} listo")
    return filas


# ──────────────────────────────────────────────── M5. anomalía individual


def medir_individual(
    grafo: Any, perfil: Any, limites: Any, ventanas: tuple[int, ...]
) -> list[dict[str, Any]]:
    """Dónde el detector pierde: anomalías de un solo medidor.

    Args:
        grafo: Grafo AMI.
        perfil: Perfil de señal.
        limites: Límites del esquema.
        ventana: Ancho de la ventana.

    Returns:
        Una fila por zona.
    """
    filas: list[dict[str, Any]] = []
    for zona_nombre in grafo.zone_order:
        zona = grafo.zones[zona_nombre]
        p = perfil.get(MAGNITUD, device_type_of(zona.device_ids[0]))
        deltas = deltas_por_semilla(zona, perfil, limites, SIGMA_INDIVIDUAL, depth=0)
        for ventana in ventanas:
            rng = np.random.default_rng([SEMILLA, 99, ventana])
            escaneo, umbral = _tasas(zona, p, deltas, ventana, (1, 2), None, rng)
            filas.append(
                {"zona": zona_nombre, "ventana": ventana,
                 "tasa_escaneo": escaneo, "tasa_umbral": umbral}
            )
    return filas


# ──────────────────────────────────────────── aplicación de criterios


def _promedio(filas: list[dict[str, Any]], clave: str, campos: tuple[str, ...]) -> dict[Any, dict[str, float]]:
    """Promedia campos numéricos agrupando por una clave.

    Args:
        filas: Filas a agrupar.
        clave: Campo de agrupación.
        campos: Campos a promediar.

    Returns:
        Promedios por valor de la clave.
    """
    salida: dict[Any, dict[str, float]] = {}
    for valor in sorted({f[clave] for f in filas}, key=lambda v: (v is None, v)):
        grupo = [f for f in filas if f[clave] == valor]
        salida[valor] = {c: float(np.mean([f[c] for f in grupo])) for c in campos}
    return salida


def elegir_punto(ventaja: list[dict[str, Any]], sigma: float) -> dict[str, Any]:
    """Aplica D1, D2, D3 y D4 a la curva de ventaja.

    Args:
        ventaja: Salida de `medir_ventaja`.
        sigma: Magnitud sobre la que se elige.

    Returns:
        El punto por ventaja, el punto por detección, y si difieren.
    """
    de_sigma = [f for f in ventaja if f["sigma_multiple"] == sigma]
    tabla = _promedio(de_sigma, "ventana", ("tasa_escaneo", "tasa_umbral", "ventaja"))
    utiles = {n: d for n, d in tabla.items() if d["tasa_escaneo"] >= PISO_UTILIDAD}

    por_ventaja = max(utiles, key=lambda n: utiles[n]["ventaja"]) if utiles else None
    por_deteccion = max(tabla, key=lambda n: tabla[n]["tasa_escaneo"])
    return {
        "sigma": sigma,
        "n_por_ventaja": por_ventaja,
        "n_por_deteccion": por_deteccion,
        "diferentes": por_ventaja != por_deteccion,
        "tabla": {str(n): d for n, d in tabla.items()},
    }


def main() -> int:
    """Corre las cinco mediciones y aplica los criterios.

    Returns:
        Código de salida del proceso.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args()

    grafo, perfil, limites = cargar()
    print(f"magnitud {MAGNITUD}  depth={DEPTH}  {N_ENSAYOS} ensayos por celda\n")

    ventaja = medir_ventaja(grafo, perfil, limites)
    puntos = [elegir_punto(ventaja, s) for s in SIGMAS]

    print("\n== M1. VENTAJA DEL ESCANEO SOBRE EL UMBRAL, POR VENTANA ==\n")
    for punto in puntos:
        print(f"  sigma = {punto['sigma']}")
        print(f"    {'N':>5} {'escaneo':>9} {'umbral':>9} {'ventaja':>9}")
        for n, d in punto["tabla"].items():
            marca = ""
            if int(n) == punto["n_por_ventaja"]:
                marca += "  <- ventaja (D1)"
            if int(n) == punto["n_por_deteccion"]:
                marca += "  <- deteccion (D4)"
            print(
                f"    {n:>5} {d['tasa_escaneo']:>8.1%} {d['tasa_umbral']:>9.1%} "
                f"{d['ventaja']:>+9.1%}{marca}"
            )
        print()

    elegido = next((p for p in puntos if p["n_por_ventaja"] is not None), puntos[0])
    ventana = elegido["n_por_ventaja"] or 8
    print(f"  D1-D3 eligen N = {ventana} (sigma = {elegido['sigma']})")
    print(f"  D4: el N de maxima deteccion seria {elegido['n_por_deteccion']}\n")

    # D7: las comparaciones secundarias van donde hay resolucion.
    celdas = _promedio(
        [{**f, "celda": (f["sigma_multiple"], f["ventana"])} for f in ventaja],
        "celda",
        ("tasa_escaneo",),
    )
    sigma_res, ventana_res = min(
        celdas, key=lambda c: abs(celdas[c]["tasa_escaneo"] - 0.50)
    )
    print(f"  D7: comparaciones secundarias en sigma={sigma_res}, N={ventana_res} "
          f"(deteccion {celdas[(sigma_res, ventana_res)]['tasa_escaneo']:.1%})\n")

    radios = medir_radios(grafo, perfil, limites, ventana_res, sigma_res)
    tau = medir_tau(grafo, perfil, limites, ventana_res, sigma_res)
    deslizante = medir_deslizante(grafo, perfil, limites, ventana_res, sigma_res)
    individual = medir_individual(grafo, perfil, limites, (1, ventana))

    print("\n== M2. VENTANA DESLIZANTE CONTRA VENTANA CONOCIDA ==\n")
    conocida = float(np.mean([f["tasa_escaneo"] for f in ventaja
                              if f["ventana"] == ventana_res
                              and f["sigma_multiple"] == sigma_res]))
    print(f"  ventana conocida (lo que suponian los experimentos previos): {conocida:.1%}")
    for alineacion, d in _promedio(deslizante, "alineacion",
                                   ("tasa_deslizante", "fpr_por_senal")).items():
        print(f"  deslizante, evento {alineacion:<11} {d['tasa_deslizante']:.1%}   "
              f"FPR por senal {d['fpr_por_senal']:.1%}")

    print("\n== M3. RADIOS DEL ESCANEO ==\n")
    print(f"  {'radios':<12} {'candidatos':>11} {'deteccion':>10} {'recall':>8} "
          f"{'precision':>10} {'F1':>7}")
    for radios_str, d in _promedio(
        [{**f, "radios": str(f["radios"])} for f in radios],
        "radios",
        ("candidatos", "tasa_deteccion", "recall", "precision", "f1"),
    ).items():
        print(f"  {radios_str:<12} {d['candidatos']:>11.0f} {d['tasa_deteccion']:>9.1%} "
              f"{d['recall']:>8.1%} {d['precision']:>10.1%} {d['f1']:>7.3f}")

    print("\n== M4. BARRIDO DE TAU (rango estable de filtrado: "
          f"[{RANGO_ESTABLE[0]}, {RANGO_ESTABLE[1]}]) ==\n")
    tabla_tau = _promedio(tau, "tau", ("tasa_escaneo",))
    print(f"  {'tau':>10} {'deteccion':>11}   dentro del rango estable")
    for valor, d in tabla_tau.items():
        dentro = "" if valor is None else (
            "si" if RANGO_ESTABLE[0] <= valor <= RANGO_ESTABLE[1] else "NO"
        )
        etiqueta = "sin filtro" if valor is None else f"{valor:g}"
        print(f"  {etiqueta:>10} {d['tasa_escaneo']:>10.1%}   {dentro}")
    con_filtro = {k: v for k, v in tabla_tau.items() if k is not None}
    mejor_tau = max(con_filtro, key=lambda k: con_filtro[k]["tasa_escaneo"])
    print(f"\n  optimo de deteccion: tau = {mejor_tau:g}")
    print(f"  cae dentro del rango estable de filtrado: "
          f"{'SI' if RANGO_ESTABLE[0] <= mejor_tau <= RANGO_ESTABLE[1] else 'NO'}")
    print(f"  sin filtro: {tabla_tau[None]['tasa_escaneo']:.1%}   "
          f"con el mejor tau: {con_filtro[mejor_tau]['tasa_escaneo']:.1%}")

    print("\n== M5. DONDE PIERDE: ANOMALIA INDIVIDUAL DE +6 SIGMA ==\n")
    print(f"  {'N':>5} {'umbral':>9} {'escaneo':>9} {'ventaja':>9}")
    for n, d in _promedio(individual, "ventana", ("tasa_escaneo", "tasa_umbral")).items():
        print(f"  {n:>5} {d['tasa_umbral']:>8.1%} {d['tasa_escaneo']:>9.1%} "
              f"{d['tasa_escaneo'] - d['tasa_umbral']:>+9.1%}")

    if args.json is not None:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(
                {
                    "semilla": SEMILLA,
                    "n_ensayos": N_ENSAYOS,
                    "ventana_elegida": ventana,
                    "criterios": {"D2": "diferencia de tasas", "D3": PISO_UTILIDAD,
                                  "D5_rango_estable": list(RANGO_ESTABLE)},
                    "puntos": puntos,
                    "ventaja": ventaja,
                    "radios": radios,
                    "tau": tau,
                    "deslizante": deslizante,
                    "individual": individual,
                },
                indent=2,
                ensure_ascii=False,
                default=str,
            ),
            encoding="utf-8",
        )
        print(f"\nJSON escrito en {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
