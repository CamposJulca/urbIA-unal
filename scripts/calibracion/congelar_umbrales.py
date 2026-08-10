#!/usr/bin/env python3
"""Congela los umbrales del detector y los versiona.

Produce `data/calibrations/manizales_scan_v1.json`, que es lo que el
servicio adopta al arrancar. No consulta la base ni el broker: trabaja sobre
los artefactos versionados, así que corre en cualquier máquina y da siempre
el mismo resultado.

## Las tres decisiones, declaradas

**1. El nulo es sintético.** Calibrar sobre datos vivos haría que una
anomalía persistente se volviera la nueva normalidad: el umbral subiría
hasta acomodarla y el detector dejaría de verla. σ sale del perfil
versionado.

**2. La topología es la versionada, no la de la base.** El grafo se
construye desde `data/topologies/manizales_150.json`. La huella queda en el
archivo y el servicio la recontrasta contra el grafo que arma desde
PostgreSQL: si difieren, no arranca. Así la comparación es contra algo
fijo en vez de contra lo que hubiera en la base el día de la calibración.

**3. El objetivo del 1 % es por señal de `4N` bins**, no por ventana. Es la
condición bajo la cual está medido el punto de operación en
`experiments/detector-deslizante/`, y calibrar por ventana daría un corte
más bajo que no corresponde a ninguna cifra publicada.

## La validación no es circular

Tras congelar, el script mide la tasa de falsas alarmas del umbral contra
señal nula **con otra semilla** que la de calibración. Con la misma semilla
el resultado saldría por construcción y no diría nada.

Uso:

    python scripts/calibracion/congelar_umbrales.py
    python scripts/calibracion/congelar_umbrales.py --validar-horas 2
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

_REPO: Final = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "services" / "monitor-gsp" / "src"))

from urbia_monitor_gsp.detector import (  # noqa: E402
    CollectiveScanDetector,
    DetectorConfig,
)
from urbia_monitor_gsp.graph import GraphConfig, MeterNode, build_ami_graph  # noqa: E402
from urbia_monitor_gsp.service import (  # noqa: E402
    Calibration,
    ZoneCalibration,
    save_calibration,
    zone_fingerprint,
)
from urbia_monitor_gsp.stream import WindowConfig  # noqa: E402

TOPOLOGIA: Final = _REPO / "data" / "topologies" / "manizales_150.json"
PERFIL: Final = _REPO / "data" / "profiles" / "manizales_signal_v1.json"
DESTINO: Final = _REPO / "data" / "calibrations" / "manizales_scan_v1.json"

VERSION: Final = "manizales-scan-v1"
MAGNITUD: Final = "voltaje_v"
"""Única magnitud con el detector evaluado.

Corriente y potencia tienen σ/media del 35 % contra el 2 % del voltaje y
están sin evaluar: calibrarlas sin medir antes sería inventar un punto de
operación.
"""

SEMILLA_CALIBRACION: Final = 20260808
"""La misma de todos los experimentos del detector."""

SEMILLA_VALIDACION: Final = 20260809
"""Distinta a propósito: con la de calibración la validación sería circular."""

FACTOR_LARGO: Final = 4
"""`n_instants = FACTOR_LARGO · window`, como en `detector-deslizante`."""


def _clave(zona: str) -> int:
    """Entero estable derivado del nombre de la zona.

    `blake2b` y no `hash()`, que en Python está aleatorizado por proceso:
    con `hash()` la validación no se reproduce entre ejecuciones. Es el
    mismo motivo por el que lo evitan el inyector y `tamano-grupo`.

    Args:
        zona: Nombre de la zona.

    Returns:
        Entero de 32 bits, determinista entre procesos y máquinas.
    """
    return int.from_bytes(hashlib.blake2b(zona.encode("utf-8"), digest_size=4).digest(), "big")


def _config_deteccion() -> DetectorConfig:
    """Punto de operación del servicio.

    `step=1` porque el servicio desliza de a un bin: cada bin nuevo produce
    una ventana. Todo lo demás son los defectos del módulo, que ya están
    medidos y justificados en `DEFAULT_WINDOW` y `DetectorConfig`.

    Returns:
        La configuración con la que se calibra y con la que opera.
    """
    return DetectorConfig(step=1)


def cargar_perfil() -> dict[str, Any]:
    """Lee el perfil de señal versionado.

    Returns:
        El perfil completo.
    """
    return dict(json.loads(PERFIL.read_text(encoding="utf-8")))


def sigma_de(perfil: dict[str, Any], zona: str) -> float:
    """σ espacial de la magnitud monitoreada para una zona.

    Las zonas son homogéneas en `device_type` —lo declara
    `zona_a_device_type` en el perfil— así que la σ de la zona es
    inequívoca. Si algún día una zona mezclara monofásicos y trifásicos,
    esto tendría que dejar de funcionar en vez de promediar dos
    dispersiones distintas.

    Args:
        perfil: Perfil versionado.
        zona: Nombre de la zona.

    Returns:
        La σ espacial.

    Raises:
        KeyError: Si la zona no está declarada en el perfil.
    """
    tipo = perfil["zona_a_device_type"][zona]
    return float(perfil["magnitudes"][MAGNITUD][tipo]["sigma_espacial"])


def falsas_alarmas_por_hora(
    detector: CollectiveScanDetector,
    sigma: float,
    n_meters: int,
    bins_por_hora: int,
    repeticiones: int,
    semilla: int,
) -> dict[str, float]:
    """Mide cuántas veces dispara el umbral congelado sin que pase nada.

    Es la cifra operativa que interesa a quien mira el panel: no "1 % de
    qué" sino cuántas alarmas falsas por hora y por zona hay que esperar.

    Args:
        detector: Detector con el umbral ya cargado.
        sigma: Dispersión espacial del nulo.
        n_meters: Medidores de la zona.
        bins_por_hora: Instantes que cubre una hora de operación.
        repeticiones: Horas simuladas.
        semilla: Semilla del generador, distinta a la de calibración.

    Se cuentan las dos cosas, y no son lo mismo. Con `step=1` dos ventanas
    contiguas comparten 15 de sus 16 bins, así que **una sola excursión del
    ruido dispara varias ventanas seguidas**. Contar ventanas sobreestima lo
    que vería un operador; un episodio —una racha maximal de ventanas
    contiguas que disparan— es lo que corresponde a una alarma.

    Returns:
        Media, p95 y máximo por hora de ventanas y de episodios, y la
        fracción de ventanas que dispararon.
    """
    rng = np.random.default_rng(semilla)
    ventanas: list[int] = []
    episodios: list[int] = []
    ventanas_totales = 0
    for _ in range(repeticiones):
        senal = rng.normal(0.0, sigma, size=(bins_por_hora, n_meters))
        marcas = np.array([d.detected for d in detector.detect(senal)], dtype=bool)
        ventanas_totales += int(marcas.size)
        ventanas.append(int(marcas.sum()))
        # Un episodio empieza donde una ventana dispara y la anterior no.
        arranques = marcas & ~np.concatenate(([False], marcas[:-1]))
        episodios.append(int(arranques.sum()))

    por_ventana = np.asarray(ventanas, dtype=np.float64)
    por_episodio = np.asarray(episodios, dtype=np.float64)
    return {
        "ventanas_media_por_hora": float(por_ventana.mean()),
        "ventanas_p95_por_hora": float(np.percentile(por_ventana, 95)),
        "ventanas_max_por_hora": float(por_ventana.max()),
        "episodios_media_por_hora": float(por_episodio.mean()),
        "episodios_p95_por_hora": float(np.percentile(por_episodio, 95)),
        "episodios_max_por_hora": float(por_episodio.max()),
        "fraccion_ventanas": float(por_ventana.sum() / ventanas_totales),
        "horas_simuladas": float(repeticiones),
    }


def main() -> int:
    """Punto de entrada.

    Returns:
        Código de salida del proceso.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destino", type=Path, default=DESTINO)
    parser.add_argument(
        "--validar-horas",
        type=int,
        default=100,
        help="horas de señal nula por zona para medir falsas alarmas (0 las omite)",
    )
    args = parser.parse_args()

    perfil = cargar_perfil()
    topologia = json.loads(TOPOLOGIA.read_text(encoding="utf-8"))
    medidores = [MeterNode(**m) for m in topologia["meters"]]
    grafo = build_ami_graph(medidores, GraphConfig())

    config = _config_deteccion()
    ventana = WindowConfig()
    n_instants = FACTOR_LARGO * config.window
    bins_por_hora = int(round(3600.0 / ventana.bin_seconds))

    print(f"topología: {topologia.get('version', '?')}, {len(medidores)} medidores")
    print(f"perfil: {perfil.get('version', '?')}, magnitud {MAGNITUD}")
    print(f"punto de operación: {config}")
    print(f"objetivo {config.fpr_target:.0%} por señal de {n_instants} bins")
    print()

    zonas: dict[str, ZoneCalibration] = {}
    validacion: dict[str, dict[str, float]] = {}

    for nombre in grafo.zone_order or sorted(grafo.zones):
        zona = grafo.zones[nombre]
        sigma = sigma_de(perfil, nombre)

        detector = CollectiveScanDetector(zona, sigma, config)
        arranque = time.perf_counter()
        umbral = detector.calibrate(SEMILLA_CALIBRACION, n_instants=n_instants)
        tardanza = time.perf_counter() - arranque

        congelado = detector.freeze_threshold(
            SEMILLA_CALIBRACION,
            n_instants,
            f"data/calibrations/{args.destino.name} ({VERSION})",
        )
        zonas[nombre] = ZoneCalibration(
            frozen=congelado,
            fingerprint=zone_fingerprint(zona),
            n_meters=zona.n_meters,
        )

        print(
            f"{nombre:<14} n={zona.n_meters:>2} σ={sigma:.4f} "
            f"bolas={detector.n_candidates:>3} umbral={umbral:.4f} "
            f"({tardanza:.1f} s)"
        )

        if args.validar_horas > 0:
            validacion[nombre] = falsas_alarmas_por_hora(
                detector,
                sigma,
                zona.n_meters,
                bins_por_hora,
                args.validar_horas,
                SEMILLA_VALIDACION + _clave(nombre) % 1000,
            )

    calibracion = Calibration(
        version=VERSION,
        magnitude=MAGNITUD,
        profile=str(perfil.get("version", "")),
        topology=str(topologia.get("version", "")),
        zones=zonas,
        validation=validacion,
        notes=(
            "Nulo sintético gaussiano con la σ espacial del perfil versionado. "
            "Objetivo por señal de "
            f"{n_instants} bins de {ventana.bin_seconds:g} s. "
            "Supone que la dispersión espacial de la telemetría real se parece a "
            "la del perfil; es un supuesto medible y no medido, declarado en el "
            "README del servicio."
        ),
    )
    save_calibration(calibracion, args.destino)

    if validacion:
        print()
        print("falsas alarmas bajo nulo, con semilla distinta a la de calibración:")
        print(
            f"{'zona':<14} {'vent/h':>7} {'p95':>5} {'máx':>5} "
            f"{'episod/h':>9} {'p95':>5} {'máx':>5} {'frac. vent.':>12}"
        )
        for nombre, datos in validacion.items():
            print(
                f"{nombre:<14} {datos['ventanas_media_por_hora']:>7.2f} "
                f"{datos['ventanas_p95_por_hora']:>5.0f} "
                f"{datos['ventanas_max_por_hora']:>5.0f} "
                f"{datos['episodios_media_por_hora']:>9.2f} "
                f"{datos['episodios_p95_por_hora']:>5.0f} "
                f"{datos['episodios_max_por_hora']:>5.0f} "
                f"{datos['fraccion_ventanas']:>11.4%}"
            )

    print()
    print(f"escrito: {args.destino}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
