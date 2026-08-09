"""Ingesta de telemetría en vivo: de llegadas asíncronas a ventanas densas.

El detector consume una matriz `(T, n)` **densa**: cada instante con los `n`
medidores de la zona. La telemetría real no llega así — cada medidor publica
por su cuenta— y este paquete es el que salva esa distancia.

No sabe de MQTT ni de PostgreSQL. Recibe lecturas sueltas y entrega
ventanas; quién se las trae es problema del servicio.

La ventana es **temporal**, no por conteo, y un bin al que le falte un
medidor **no produce detección**: levanta `BinIncompleteError` con el motivo,
para que el servicio lo publique en vez de detectar sobre dato inventado.
El porqué de las dos decisiones está en `window.py`.
"""

from .window import BinIncompleteError, Window, WindowConfig, WindowError, ZoneWindow

__all__ = [
    "BinIncompleteError",
    "Window",
    "WindowConfig",
    "WindowError",
    "ZoneWindow",
]
