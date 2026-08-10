"""El monitor como servicio: de biblioteca a proceso que corre.

Lo que vive acá es todo lo que el núcleo doctoral no debe saber: dónde está
el broker, cómo se lee el padrón, cada cuánto se corre un ciclo, dónde se
publican las detecciones. `graph`, `detector` y `stream` siguen sin importar
nada de este paquete y se pueden usar desde un notebook con sólo numpy.

La separación no es estética. El servicio es el que va a mudarse al nodo de
borde para medir H1, y lo que se mide ahí tiene que ser el detector, no el
andamiaje que lo rodea.
"""

from .calibration import (
    Calibration,
    CalibrationError,
    TopologyMismatchError,
    ZoneCalibration,
    load_calibration,
    save_calibration,
)
from .fingerprint import graph_fingerprints, zone_fingerprint

__all__ = [
    "Calibration",
    "CalibrationError",
    "TopologyMismatchError",
    "ZoneCalibration",
    "graph_fingerprints",
    "load_calibration",
    "save_calibration",
    "zone_fingerprint",
]
