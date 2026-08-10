"""Detección de eventos colectivos sobre el grafo AMI.

Escaneo local sobre ventana: contrasta cada vecindario del grafo contra el
resto de su zona y se queda con el mayor desacuerdo. Cada decisión sale de
una medición previa, y el módulo documenta también **dónde pierde** — es
peor que un umbral por medidor en anomalías individuales.

```python
from urbia_monitor_gsp.detector import CollectiveScanDetector, DetectorConfig

detector = CollectiveScanDetector(
    zona,
    sigma_spatial=4.4012,                 # del perfil medido, no adivinado
    config=DetectorConfig(window=32),     # punto de operación declarado
)
detector.calibrate(seed=20260808)
detecciones = detector.detect(lecturas)   # (T, n)

detecciones[0].device_ids                 # QUÉ nodos marcó
detector.node_mask(detecciones, len(lecturas))   # para la matriz de confusión
```

No importa nada de `urbia_events`: recibe `sigma_spatial` como parámetro y
no sabe de dónde salió. Lo que genera la verdad de referencia y lo que se
puntúa contra ella no comparten paquete.
"""

from .detector import CollectiveScanDetector
from .scan import candidate_balls, contrasts, k_hop_indices
from .types import (
    DEFAULT_WINDOW,
    ConfusionMatrix,
    Detection,
    DetectorConfig,
    DetectorError,
    FrozenThreshold,
    ScanCandidate,
    confusion_matrix,
)

__all__ = [
    "DEFAULT_WINDOW",
    "CollectiveScanDetector",
    "ConfusionMatrix",
    "Detection",
    "DetectorConfig",
    "DetectorError",
    "FrozenThreshold",
    "ScanCandidate",
    "candidate_balls",
    "confusion_matrix",
    "contrasts",
    "k_hop_indices",
]
