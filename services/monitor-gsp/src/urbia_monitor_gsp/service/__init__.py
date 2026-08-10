"""El monitor como servicio: de biblioteca a proceso que corre.

Lo que vive acá es todo lo que el núcleo doctoral no debe saber: dónde está
el broker, cómo se lee el padrón, cada cuánto se corre un ciclo, dónde se
publican las detecciones. `graph`, `detector` y `stream` siguen sin importar
nada de este paquete y se pueden usar desde un notebook con sólo numpy.

La separación no es estética. El servicio es el que va a mudarse al nodo de
borde para medir H1, y lo que se mide ahí tiene que ser el detector, no el
andamiaje que lo rodea.

## Cómo está partido

| Módulo | Qué es | Depende de |
|---|---|---|
| `calibration` | El archivo congelado y su verificación | núcleo |
| `fingerprint` | Huella de la topología que el umbral supone | núcleo |
| `settings` | Configuración desde el entorno | pydantic-settings |
| `runtime` | El ciclo: lecturas → resultados por zona | núcleo |
| `publisher` | La forma de lo que se publica | núcleo |
| `metrics` | Series de Prometheus | prometheus-client |
| `mqtt` | Transporte: de dónde llega y adónde va | paho-mqtt |
| `app` | Armado, bucle y apagado | todo lo anterior |

`runtime` y `publisher` **no importan paho ni prometheus**, así que el ciclo
entero se prueba sin broker y sin registro global.

`app` y `mqtt` no se reexportan acá a propósito: importarlos arrastraría
`paho-mqtt` y `psycopg`, y entonces leer una calibración desde un notebook
—o desde `scripts/calibracion/`— exigiría el extra `[service]` completo.
Quien los necesite los importa por su ruta.

```python
from urbia_monitor_gsp.service import MonitorSettings, CollectingPublisher
from urbia_monitor_gsp.service.app import build_service

recolector = CollectingPublisher()
servicio = build_service(MonitorSettings(), recolector)
servicio.tick()                    # un ciclo, sin bucle
recolector.topics()
```
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
from .metrics import MonitorMetrics, NullMetrics
from .publisher import (
    CollectingPublisher,
    CycleDispatcher,
    DetectionPayload,
    Publisher,
    PublishError,
)
from .runtime import (
    CycleResult,
    MonitorRuntime,
    RuntimeSetupError,
    ZoneResult,
    ZoneRuntime,
    build_runtime,
)
from .settings import (
    DEFAULT_CYCLE_SECONDS,
    MonitorSettings,
    MonitorSettingsError,
    get_monitor_settings,
)

__all__ = [
    "DEFAULT_CYCLE_SECONDS",
    "Calibration",
    "CalibrationError",
    "CollectingPublisher",
    "CycleDispatcher",
    "CycleResult",
    "DetectionPayload",
    "MonitorMetrics",
    "MonitorRuntime",
    "MonitorSettings",
    "MonitorSettingsError",
    "NullMetrics",
    "PublishError",
    "Publisher",
    "RuntimeSetupError",
    "TopologyMismatchError",
    "ZoneCalibration",
    "ZoneResult",
    "ZoneRuntime",
    "build_runtime",
    "get_monitor_settings",
    "graph_fingerprints",
    "load_calibration",
    "save_calibration",
    "zone_fingerprint",
]
