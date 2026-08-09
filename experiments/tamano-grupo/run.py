#!/usr/bin/env python3
"""Detección contra tamaño de grupo: la curva de degradación y su límite.

Todo lo publicado del detector está medido en `depth=2`, que da 11–12 nodos
sobre zonas de 20 a 30 — es decir `m ≈ n/2`. Entre un medidor solo y la zona
entera hay un continuo del que no se midió ningún punto, y el extremo —la
zona entera, que el detector no debe marcar— está sostenido por un caso
construido a mano, sin corrida trazable.

Los criterios están en `CRITERIOS.md`, commiteados antes de esta corrida.
Acá no se declara ninguno: este archivo los aplica.

Uso:

    python experiments/tamano-grupo/run.py --json results/medicion.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
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
    boundary_edges,
    device_type_of,
    load_bounds,
    load_profile,
)
from urbia_monitor_gsp.detector import (  # noqa: E402
    CollectiveScanDetector,
    DetectorConfig,
)
from urbia_monitor_gsp.detector.scan import candidate_balls  # noqa: E402
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

# C2: punto de operación, idéntico a `detector-deslizante`.
VENTANA: Final = 16
RADIOS: Final = (1, 2)
SIGMA_EVENTO: Final = 0.5
FACTOR_LARGO: Final = 4
CALIBRACION: Final = 600
FPR_OBJETIVO: Final = 0.01

# C3: eje del barrido, recortado al `n` de cada zona. `m = n` se agrega siempre.
GRID: Final = (1, 2, 3, 4, 5, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24)

N_ENSAYOS: Final = 2000  # C9
FORMAS_CONTRASTE: Final = (5, 6, 8)  # C10
CALIBRACION_CONTROL: Final = 20000  # C11


FORMAS: Final = ("compacto", "extendido")


def _clave(zona: str) -> int:
    """Entero estable derivado del nombre de la zona.

    `blake2b` y no `hash()`, que en Python está aleatorizado por proceso: con
    `hash()` la corrida no se reproduce entre ejecuciones. Es el mismo motivo
    por el que el inyector lo evita en `_zone_key`.

    Args:
        zona: Nombre de la zona.

    Returns:
        Entero de 32 bits, determinista entre procesos y máquinas.
    """
    return int.from_bytes(
        hashlib.blake2b(zona.encode("utf-8"), digest_size=4).digest(), "big"
    )


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


def grupos_y_deltas(
    zone: ZoneGraph,
    inyector: EventInjector,
    m: int,
    forma: str,
) -> tuple[npt.NDArray[np.float64], list[tuple[int, ...]]]:
    """Desviación y grupo afectado usando cada nodo como semilla.

    Args:
        zone: Subgrafo zonal.
        inyector: Inyector ya construido.
        m: Tamaño del grupo.
        forma: `"compacto"` o `"extendido"`.

    Returns:
        Par `(deltas, grupos)`. `deltas[j]` es la desviación con semilla `j`
        y `grupos[j]` los nodos que afecta.
    """
    deltas = np.zeros((zone.n_meters, zone.n_meters))
    grupos: list[tuple[int, ...]] = []
    for j, device_id in enumerate(zone.device_ids):
        senal, verdad = inyector.inject(
            zone,
            np.zeros(zone.n_meters),
            [
                CollectiveDeviationSpec(
                    magnitude=MAGNITUD,
                    size_target=m,
                    shape=forma,  # type: ignore[arg-type]
                    sigma_multiple=SIGMA_EVENTO,
                    seed_device_id=device_id,
                )
            ],
        )
        deltas[j] = senal[0]
        grupos.append(verdad.events[0].node_indices)
    return deltas, grupos


def contraste_alcanzable(
    mascaras: npt.NDArray[np.float64],
    grupo: tuple[int, ...],
    n: int,
) -> float:
    """Mayor contraste determinista que alguna bola candidata puede extraer.

    Es el predictor de A en su forma operativa: no `√(m(n−m)/n)`, que supone
    el candidato igual al grupo, sino lo que el escaneo real puede sacar con
    las bolas que efectivamente evalúa.

    Args:
        mascaras: Bolas candidatas `(B, n)`.
        grupo: Nodos afectados.
        n: Nodos de la zona.

    Returns:
        El contraste, en unidades de `Δ/σ_eff`.
    """
    indicador = np.zeros(n)
    indicador[list(grupo)] = 1.0
    tam = mascaras.sum(axis=1)
    dentro = mascaras @ indicador
    fuera = indicador.sum() - dentro
    diferencia = np.abs(dentro / tam - fuera / (n - tam))
    return float((diferencia / np.sqrt(1.0 / tam + 1.0 / (n - tam))).max())


def _tasa_umbral(
    limpio: npt.NDArray[np.float64],
    con_evento: npt.NDArray[np.float64],
    media: float,
    sigma_eff: float,
) -> tuple[float, float]:
    """Umbral por medidor sobre las mismas ventanas y la misma calibración.

    C4: el comparador ve la misma señal y la misma estructura de ventanas, y
    se calibra por señal sobre su propio máximo.

    Args:
        limpio: Señales sin evento `(R, T, n)`.
        con_evento: Señales con evento, misma forma.
        media: Media de la magnitud.
        sigma_eff: Dispersión tras promediar la ventana.

    Returns:
        Par `(tasa_deteccion, fpr_empirico)`.
    """

    def maximos(x: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
        total = x.shape[1]
        por_ventana = [
            np.abs(x[:, i : i + VENTANA].mean(axis=1) - media).max(axis=1) / sigma_eff
            for i in range(0, total - VENTANA + 1)
        ]
        return np.max(np.stack(por_ventana, axis=1), axis=1)

    neg, pos = maximos(limpio), maximos(con_evento)
    corte = float(np.quantile(neg, 1.0 - FPR_OBJETIVO))
    return float((pos > corte).mean()), float((neg > corte).mean())


def medir_celda(
    zone: ZoneGraph,
    p: Any,
    inyector: EventInjector,
    m: int,
    forma: str,
    calibracion: int = CALIBRACION,
) -> dict[str, Any]:
    """Una celda del barrido: una zona, un tamaño, una forma.

    Args:
        zone: Subgrafo zonal.
        p: Perfil de la magnitud para el tipo de medidor de la zona.
        inyector: Inyector ya construido.
        m: Tamaño del grupo.
        forma: `"compacto"` o `"extendido"`.
        calibracion: Muestras de calibración del detector.

    Returns:
        Fila con tasas, FPR empíricos y los dos predictores.
    """
    n = zone.n_meters
    total = FACTOR_LARGO * VENTANA
    deltas, grupos = grupos_y_deltas(zone, inyector, m, forma)

    detector = CollectiveScanDetector(
        zone,
        p.sigma_spatial,
        DetectorConfig(
            window=VENTANA, step=1, scan_radii=RADIOS, calibration_samples=calibracion
        ),
    )
    detector.calibrate(SEMILLA, n_instants=total)

    rng = np.random.default_rng([SEMILLA, _clave(zone.zona), m, FORMAS.index(forma)])
    limpio = rng.normal(p.mean, p.sigma_spatial, size=(N_ENSAYOS, total, n))
    semillas = np.arange(N_ENSAYOS) % n
    inicios = rng.integers(0, total - VENTANA + 1, size=N_ENSAYOS)

    con_evento = limpio.copy()
    for i in range(N_ENSAYOS):
        con_evento[i, inicios[i] : inicios[i] + VENTANA] += deltas[semillas[i]]

    detectadas = 0
    for i in range(N_ENSAYOS):
        if any(
            d.detected
            and d.window_start < inicios[i] + VENTANA
            and d.window_end > inicios[i]
            for d in detector.detect(con_evento[i])
        ):
            detectadas += 1

    # C11: el FPR se mide, no se supone.
    fpr_escaneo = float(
        np.mean([any(d.detected for d in detector.detect(x)) for x in limpio])
    )

    sigma_eff = p.sigma_spatial / np.sqrt(VENTANA)
    tasa_umbral, fpr_umbral = _tasa_umbral(limpio, con_evento, p.mean, sigma_eff)

    mascaras, _ = candidate_balls(zone, RADIOS)
    cortes = [boundary_edges(zone.adjacency, g) for g in grupos]
    contrastes = [contraste_alcanzable(mascaras, g, n) for g in grupos]

    tasa_escaneo = detectadas / N_ENSAYOS
    return {
        "zona": zone.zona,
        "n": n,
        "m": m,
        "cobertura": m / n,
        "forma": forma,
        "calibracion": calibracion,
        "tasa_escaneo": tasa_escaneo,
        "tasa_umbral": tasa_umbral,
        "ventaja": tasa_escaneo - tasa_umbral,
        "fpr_escaneo": fpr_escaneo,
        "fpr_umbral": fpr_umbral,
        # Predictor de A, forma operativa: lo que las bolas reales extraen.
        "contraste_alcanzable": float(np.mean(contrastes)),
        # Predictor de A, forma idealizada: candidato igual al grupo.
        "contraste_ideal": float(np.sqrt(m * (n - m) / n)),
        # Predictor de B.
        "corte_por_nodo": float(np.mean(cortes)) / m,
        "corte": float(np.mean(cortes)),
    }


def barrido(grafo: Any, perfil: Any, limites: Any) -> list[dict[str, Any]]:
    """C3: la curva completa, sobre las seis zonas, en forma compacta.

    Args:
        grafo: Grafo AMI.
        perfil: Perfil de señal.
        limites: Límites del esquema.

    Returns:
        Una fila por zona y tamaño.
    """
    inyector = EventInjector(perfil, limites, seed=SEMILLA)
    filas: list[dict[str, Any]] = []
    for nombre in grafo.zone_order:
        zona = grafo.zones[nombre]
        p = perfil.get(MAGNITUD, device_type_of(zona.device_ids[0]))
        tamanos = sorted({m for m in GRID if m <= zona.n_meters} | {zona.n_meters})
        for m in tamanos:
            filas.append(medir_celda(zona, p, inyector, m, "compacto"))
        print(f"  barrido: {nombre} listo ({len(tamanos)} tamaños)")
    return filas


def contraste_de_forma(grafo: Any, perfil: Any, limites: Any) -> list[dict[str, Any]]:
    """C10: compacto contra extendido a igual tamaño.

    Args:
        grafo: Grafo AMI.
        perfil: Perfil de señal.
        limites: Límites del esquema.

    Returns:
        Una fila por zona, tamaño y forma.
    """
    inyector = EventInjector(perfil, limites, seed=SEMILLA)
    filas: list[dict[str, Any]] = []
    for nombre in grafo.zone_order:
        zona = grafo.zones[nombre]
        p = perfil.get(MAGNITUD, device_type_of(zona.device_ids[0]))
        for m in FORMAS_CONTRASTE:
            for forma in FORMAS:
                filas.append(medir_celda(zona, p, inyector, m, forma))
        print(f"  forma: {nombre} listo")
    return filas


def control_calibracion(grafo: Any, perfil: Any, limites: Any) -> list[dict[str, Any]]:
    """C11: el mismo punto con calibración alta, para diagnosticar el FPR.

    Args:
        grafo: Grafo AMI.
        perfil: Perfil de señal.
        limites: Límites del esquema.

    Returns:
        Una fila por zona, en `m = n`.
    """
    inyector = EventInjector(perfil, limites, seed=SEMILLA)
    filas: list[dict[str, Any]] = []
    for nombre in grafo.zone_order:
        zona = grafo.zones[nombre]
        p = perfil.get(MAGNITUD, device_type_of(zona.device_ids[0]))
        filas.append(
            medir_celda(
                zona, p, inyector, zona.n_meters, "compacto", CALIBRACION_CONTROL
            )
        )
    print("  control de calibración listo")
    return filas


def spearman(x: list[float], y: list[float]) -> float:
    """Correlación de Spearman, sin dependencias externas.

    Args:
        x: Primera variable.
        y: Segunda variable.

    Returns:
        El coeficiente `ρ`.
    """

    def rangos(v: list[float]) -> npt.NDArray[np.float64]:
        orden = np.argsort(np.argsort(np.asarray(v, dtype=np.float64)))
        return np.asarray(orden, dtype=np.float64)

    a, b = rangos(x), rangos(y)
    a = a - a.mean()
    b = b - b.mean()
    return float((a @ b) / np.sqrt((a @ a) * (b @ b)))


def cruces(filas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """C5: dónde el escaneo cruza por debajo del umbral, por zona.

    Args:
        filas: Filas del barrido.

    Returns:
        Un registro por cruce, con `m` y `m/n` a cada lado.
    """
    salida: list[dict[str, Any]] = []
    zonas = sorted({f["zona"] for f in filas})
    for zona in zonas:
        curva = sorted((f for f in filas if f["zona"] == zona), key=lambda f: f["m"])
        for antes, despues in zip(curva, curva[1:], strict=False):
            if (antes["ventaja"] > 0) != (despues["ventaja"] > 0):
                salida.append(
                    {
                        "zona": zona,
                        "n": antes["n"],
                        "sentido": "a favor" if despues["ventaja"] > 0 else "en contra",
                        "m_antes": antes["m"],
                        "m_despues": despues["m"],
                        "cobertura_antes": antes["cobertura"],
                        "cobertura_despues": despues["cobertura"],
                    }
                )
    return salida


def main() -> int:
    """Corre el experimento completo y guarda la medición cruda.

    Returns:
        Código de salida.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json", type=Path, default=Path(__file__).parent / "results" / "medicion.json"
    )
    args = parser.parse_args()

    grafo, perfil, limites = cargar()
    inicio = time.perf_counter()

    print("barrido de tamaño (C3)...")
    filas = barrido(grafo, perfil, limites)
    print("contraste de forma (C10)...")
    forma = contraste_de_forma(grafo, perfil, limites)
    print("control de calibración (C11)...")
    control = control_calibracion(grafo, perfil, limites)

    # C6: Spearman de cada predictor contra la detección, sobre todo el barrido.
    deteccion = [f["tasa_escaneo"] for f in filas]
    rho = {
        "A_alcanzable": spearman([f["contraste_alcanzable"] for f in filas], deteccion),
        "A_ideal": spearman([f["contraste_ideal"] for f in filas], deteccion),
        "B_corte_por_nodo": spearman([f["corte_por_nodo"] for f in filas], deteccion),
    }

    salida = {
        "semilla": SEMILLA,
        "n_ensayos": N_ENSAYOS,
        "punto_de_operacion": {
            "ventana": VENTANA,
            "radios": list(RADIOS),
            "sigma_evento": SIGMA_EVENTO,
            "fpr_objetivo": FPR_OBJETIVO,
            "calibracion": CALIBRACION,
            "magnitud": MAGNITUD,
        },
        "barrido": filas,
        "contraste_de_forma": forma,
        "control_calibracion": control,
        "spearman": rho,
        "cruces": cruces(filas),
        "segundos": round(time.perf_counter() - inicio, 1),
    }

    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(
        json.dumps(salida, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\nescrito {args.json} ({salida['segundos']} s)")
    print("spearman:", json.dumps(rho, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
