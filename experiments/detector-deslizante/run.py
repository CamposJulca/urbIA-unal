#!/usr/bin/env python3
"""El detector en condición realista: ventana deslizante y FPR por señal.

`experiments/detector-colectivo/` eligió N=16 como punto de operación, pero
lo eligió sobre una curva medida con **ventana conocida**: cada realización
era una sola ventana perfectamente alineada con el evento. Ésa no es la
condición real. Un detector que recorre la señal no sabe dónde está el
evento, recorre W ventanas, y con un objetivo del 1 % por ventana termina
disparando en falso mucho más seguido.

Acá se rehace todo bajo deslizamiento, con la calibración por señal que el
módulo ahora soporta, para responder tres cosas:

1. ¿Sobrevive N=16 como punto de máxima ventaja?
2. ¿Cuánto cuesta el deslizamiento, medido en la misma moneda para el
   escaneo y para el umbral?
3. ¿Qué da la matriz de confusión **por nodo** en el punto de operación
   real?

# CRITERIOS, DECLARADOS ANTES DE MIRAR LOS RESULTADOS

**E1 — El falso positivo se declara POR SEÑAL, no por ventana.** Es la
unidad operativa: a un monitor le importa cuántas veces al día levanta una
alarma falsa, no cuántas ventanas de las que evaluó. Objetivo: 1 % por
señal, para el escaneo y para el umbral por igual.

**E2 — Los dos comparadores ven la misma señal y la misma estructura de
ventanas.** El umbral por medidor también recorre las ventanas y también se
calibra por señal sobre su propio máximo. Cualquier ventaja que quede no
puede atribuirse a que uno vio más datos que el otro.

**E3 — El punto de operación se re-elige con la regla de siempre**, D1–D3
de `experiments/detector-colectivo/`: mayor ventaja entre los N que superan
el 50 % de detección. Si el N que gana bajo deslizamiento no es 16, se
cambia el defecto del módulo y se dice por qué.

**E4 — El evento se coloca en una posición sorteada**, no alineada al borde
de ventana. La alineación era una comodidad de los experimentos previos.

**E5 — La confusión por nodo se mide sólo sobre las señales detectadas.**
Un evento no detectado no aporta información sobre si el detector localiza
bien; mezclarlo confundiría dos preguntas distintas —cuánto detecta y qué
tan bien localiza— en un solo número. La tasa de detección se reporta
aparte.

Uso:

    python experiments/detector-deslizante/run.py --json results/medicion.json
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
    confusion_matrix,
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
SIGMA_EVENTO: Final = 0.5
"""La magnitud sobre la que se eligió el punto de operación anterior."""

VENTANAS: Final = (4, 8, 16, 32)
RADIOS: Final = ((1,), (1, 2))
N_ENSAYOS: Final = 200
CALIBRACION: Final = 600
FACTOR_LARGO: Final = 4
"""La señal dura `FACTOR_LARGO × ventana`; el evento ocupa una ventana."""

FPR_OBJETIVO: Final = 0.01
PISO_UTILIDAD: Final = 0.50


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
    zone: ZoneGraph, perfil: Any, limites: Any, sigma_multiple: float
) -> npt.NDArray[np.float64]:
    """Desviación que aplica el inyector con cada nodo como semilla.

    Args:
        zone: Subgrafo zonal.
        perfil: Perfil de señal.
        limites: Límites del esquema.
        sigma_multiple: Magnitud de la desviación.

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
                    depth=DEPTH,
                    sigma_multiple=sigma_multiple,
                    seed_device_id=device_id,
                )
            ],
        )
        salida[j] = senal[0]
    return salida


def _umbral_por_senal(
    limpio: npt.NDArray[np.float64],
    con_evento: npt.NDArray[np.float64],
    ventana: int,
    media: float,
    sigma_eff: float,
) -> tuple[float, float]:
    """Umbral por medidor recorriendo las mismas ventanas (E2).

    Args:
        limpio: Señales sin evento `(R, T, n)`.
        con_evento: Señales con evento, misma forma.
        ventana: Ancho de la ventana.
        media: Media de la magnitud.
        sigma_eff: Dispersión tras promediar.

    Returns:
        Par `(tasa_deteccion, fpr_empirico)`.
    """

    def maximos(x: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
        total = x.shape[1]
        por_ventana = [
            np.abs(x[:, i : i + ventana].mean(axis=1) - media).max(axis=1) / sigma_eff
            for i in range(0, total - ventana + 1)
        ]
        return np.max(np.stack(por_ventana, axis=1), axis=1)

    neg, pos = maximos(limpio), maximos(con_evento)
    corte = float(np.quantile(neg, 1.0 - FPR_OBJETIVO))
    return float((pos > corte).mean()), float((neg > corte).mean())


def medir_celda(
    zone: ZoneGraph,
    p: Any,
    deltas: npt.NDArray[np.float64],
    ventana: int,
    radios: tuple[int, ...],
) -> dict[str, Any]:
    """Mide una combinación de ventana y radios bajo deslizamiento.

    Args:
        zone: Subgrafo zonal.
        p: Perfil de la magnitud.
        deltas: Desviaciones por semilla.
        ventana: Ancho de la ventana.
        radios: Radios del escaneo.

    Returns:
        Tasas, FPR empírico y confusión por nodo.
    """
    n = zone.n_meters
    total = FACTOR_LARGO * ventana
    config = DetectorConfig(
        window=ventana, step=1, scan_radii=radios, calibration_samples=CALIBRACION
    )
    detector = CollectiveScanDetector(zone, p.sigma_spatial, config)
    detector.calibrate(SEMILLA, n_instants=total)

    rng = np.random.default_rng([SEMILLA, ventana, len(radios)])
    limpio = rng.normal(p.mean, p.sigma_spatial, size=(N_ENSAYOS, total, n))
    semillas = np.arange(N_ENSAYOS) % n
    # E4: el evento arranca en una posición sorteada, no alineada.
    inicios = rng.integers(0, total - ventana + 1, size=N_ENSAYOS)

    con_evento = limpio.copy()
    for i in range(N_ENSAYOS):
        con_evento[i, inicios[i] : inicios[i] + ventana] += deltas[semillas[i]]

    grupos = [k_hop_indices(zone.adjacency, j, DEPTH) for j in range(n)]
    predicho: list[npt.NDArray[np.bool_]] = []
    verdadero: list[npt.NDArray[np.bool_]] = []
    detectadas = 0

    for i in range(N_ENSAYOS):
        marcados = np.zeros(n, dtype=bool)
        acierto = False
        for d in detector.detect(con_evento[i]):
            if d.detected and d.window_start < inicios[i] + ventana and d.window_end > inicios[i]:
                acierto = True
                marcados[list(d.node_indices)] = True
        detectadas += int(acierto)
        if acierto:  # E5: la confusión sólo sobre lo detectado
            cierto = np.zeros(n, dtype=bool)
            cierto[list(grupos[semillas[i]])] = True
            predicho.append(marcados)
            verdadero.append(cierto)

    fpr = float(
        np.mean([any(d.detected for d in detector.detect(x)) for x in limpio])
    )
    sigma_eff = p.sigma_spatial / np.sqrt(ventana)
    tasa_umbral, fpr_umbral = _umbral_por_senal(
        limpio, con_evento, ventana, p.mean, sigma_eff
    )

    salida: dict[str, Any] = {
        "ventana": ventana,
        "radios": list(radios),
        "candidatos": detector.n_candidates,
        "ventanas_por_senal": len(detector.detect(limpio[0])),
        "tasa_escaneo": detectadas / N_ENSAYOS,
        "tasa_umbral": tasa_umbral,
        "ventaja": detectadas / N_ENSAYOS - tasa_umbral,
        "fpr_escaneo": fpr,
        "fpr_umbral": fpr_umbral,
    }
    if predicho:
        salida.update(confusion_matrix(np.array(predicho), np.array(verdadero)).to_dict())
    return salida


def medir(grafo: Any, perfil: Any, limites: Any) -> list[dict[str, Any]]:
    """Barre ventana y radios sobre las seis zonas.

    Args:
        grafo: Grafo AMI.
        perfil: Perfil de señal.
        limites: Límites del esquema.

    Returns:
        Una fila por zona, ventana y conjunto de radios.
    """
    filas: list[dict[str, Any]] = []
    for zona_nombre in grafo.zone_order:
        zona = grafo.zones[zona_nombre]
        p = perfil.get(MAGNITUD, device_type_of(zona.device_ids[0]))
        deltas = deltas_por_semilla(zona, perfil, limites, SIGMA_EVENTO)
        for ventana in VENTANAS:
            for radios in RADIOS:
                filas.append(
                    {"zona": zona_nombre, **medir_celda(zona, p, deltas, ventana, radios)}
                )
        print(f"  {zona_nombre} listo")
    return filas


def _promedio(filas: list[dict[str, Any]], campos: tuple[str, ...]) -> dict[str, float]:
    """Promedia campos numéricos presentes en las filas.

    Args:
        filas: Filas a promediar.
        campos: Campos buscados.

    Returns:
        Promedios, omitiendo los campos ausentes.
    """
    return {
        c: float(np.mean([f[c] for f in filas if c in f]))
        for c in campos
        if any(c in f for f in filas)
    }


def main() -> int:
    """Corre el barrido y aplica E1–E5.

    Returns:
        Código de salida del proceso.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args()

    grafo, perfil, limites = cargar()
    print(f"magnitud {MAGNITUD}  sigma={SIGMA_EVENTO}  depth={DEPTH}  "
          f"{N_ENSAYOS} ensayos por celda\n")
    filas = medir(grafo, perfil, limites)

    print("\n== CURVA DE VENTAJA BAJO DESLIZAMIENTO, FPR POR SENAL ==\n")
    print(f"  {'radios':<8} {'N':>4} {'ventanas':>9} {'escaneo':>9} {'umbral':>8} "
          f"{'ventaja':>9} {'FPR esc':>8} {'FPR umb':>8}")
    resumen: dict[tuple[str, int], dict[str, float]] = {}
    for radios in RADIOS:
        for ventana in VENTANAS:
            grupo = [
                f for f in filas if f["ventana"] == ventana and f["radios"] == list(radios)
            ]
            d = _promedio(grupo, ("ventanas_por_senal", "tasa_escaneo", "tasa_umbral",
                                  "ventaja", "fpr_escaneo", "fpr_umbral",
                                  "recall", "precision", "f1"))
            resumen[(str(radios), ventana)] = d
            print(f"  {str(radios):<8} {ventana:>4} {d['ventanas_por_senal']:>9.0f} "
                  f"{d['tasa_escaneo']:>8.1%} {d['tasa_umbral']:>8.1%} "
                  f"{d['ventaja']:>+9.1%} {d['fpr_escaneo']:>7.1%} {d['fpr_umbral']:>8.1%}")

    print("\n== E3: PUNTO DE OPERACION BAJO DESLIZAMIENTO ==\n")
    candidatos = {
        k: v for k, v in resumen.items()
        if k[0] == str((1, 2)) and v["tasa_escaneo"] >= PISO_UTILIDAD
    }
    if candidatos:
        mejor = max(candidatos, key=lambda k: candidatos[k]["ventaja"])
        print(f"  N = {mejor[1]}   ventaja {candidatos[mejor]['ventaja']:+.1%} "
              f"(escaneo {candidatos[mejor]['tasa_escaneo']:.1%}, "
              f"umbral {candidatos[mejor]['tasa_umbral']:.1%})")
    else:
        mejor = max(resumen, key=lambda k: resumen[k]["tasa_escaneo"])
        print(f"  ninguna ventana supera el piso del {PISO_UTILIDAD:.0%}; "
              f"la mejor es N={mejor[1]} con {resumen[mejor]['tasa_escaneo']:.1%}")

    print("\n== CONFUSION POR NODO (solo sobre lo detectado, E5) ==\n")
    print(f"  {'radios':<8} {'N':>4} {'recall':>8} {'precision':>10} {'F1':>7}")
    for clave, d in resumen.items():
        if "recall" in d:
            print(f"  {clave[0]:<8} {clave[1]:>4} {d['recall']:>7.1%} "
                  f"{d['precision']:>10.1%} {d['f1']:>7.3f}")

    if args.json is not None:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(
                {"semilla": SEMILLA, "sigma": SIGMA_EVENTO, "n_ensayos": N_ENSAYOS,
                 "fpr_objetivo": FPR_OBJETIVO, "barrido": filas},
                indent=2, ensure_ascii=False, default=str,
            ),
            encoding="utf-8",
        )
        print(f"\nJSON escrito en {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
