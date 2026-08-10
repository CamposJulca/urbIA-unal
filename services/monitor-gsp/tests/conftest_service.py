"""Piezas compartidas por los tests del servicio.

No es un `conftest.py` para que las funciones se importen explícitamente:
así se ve en cada test de dónde salen las lecturas sintéticas y con qué
reloj, que es lo que hace legible un test de ventanas temporales.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np

from urbia_monitor_gsp.graph.types import AmiGraph
from urbia_monitor_gsp.service.calibration import Calibration, load_calibration
from urbia_monitor_gsp.service.runtime import MonitorRuntime
from urbia_monitor_gsp.stream.window import WindowConfig

CALIBRACION = Path(__file__).parents[3] / "data" / "calibrations" / "manizales_scan_v1.json"

BASE = datetime(2026, 8, 9, 12, 0, 0, tzinfo=UTC)
"""Instante que cae exactamente en un borde de bin de 6 s.

Elegido así para que los índices de bin del test sean predecibles: la
rejilla es absoluta, anclada a la época Unix, y 12:00:00 UTC es múltiplo
de 60 y por lo tanto de 6.
"""


def calibracion_versionada() -> Calibration:
    """La calibración que el servicio adopta en producción.

    Returns:
        La calibración cargada del archivo versionado.
    """
    return load_calibration(CALIBRACION)


def despues_de_la_ventana(config: WindowConfig | None = None) -> datetime:
    """Instante en el que la ventana completa ya cerró.

    Args:
        config: Parámetros de la ventana. `None` usa los medidos.

    Returns:
        Un instante posterior al borde derecho del último bin más la gracia.
    """
    cfg = config if config is not None else WindowConfig()
    return BASE + timedelta(seconds=cfg.span_seconds + cfg.close_grace_seconds + 1.0)


def llenar_ventana(
    runtime: MonitorRuntime,
    graph: AmiGraph,
    *,
    omitir: dict[str, tuple[str, ...]] | None = None,
    desplazar: dict[str, tuple[tuple[str, ...], float]] | None = None,
    config: WindowConfig | None = None,
    seed: int = 20260809,
) -> None:
    """Alimenta una ventana completa de todas las zonas.

    Args:
        runtime: Monitor que recibe las lecturas.
        graph: Grafo del que salen los medidores de cada zona.
        omitir: Por zona, medidores que **no** publican. Sirve para forzar
            el bin incompleto.
        desplazar: Por zona, `(medidores, corrimiento)` que se suma a la
            señal. Sirve para forzar una detección.
        config: Parámetros de la ventana. `None` usa los medidos.
        seed: Semilla de la señal de fondo.
    """
    cfg = config if config is not None else WindowConfig()
    rng = np.random.default_rng(seed)
    sin_dato = omitir or {}
    corridos = desplazar or {}

    for b in range(cfg.window_bins):
        instante = BASE + timedelta(seconds=b * cfg.bin_seconds)
        for nombre, zona in graph.zones.items():
            ausentes = set(sin_dato.get(nombre, ()))
            afectados, delta = corridos.get(nombre, ((), 0.0))
            valores = rng.normal(220.0, 4.4, size=zona.n_meters)
            for i, device_id in enumerate(zona.device_ids):
                if device_id in ausentes:
                    continue
                extra = delta if device_id in set(afectados) else 0.0
                runtime.observe(device_id, instante, float(valores[i]) + extra)
