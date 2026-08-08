"""Inyector de eventos correlacionados para evaluar detección colectiva.

Genera anomalías donde **cada medidor está dentro de su rango normal** y lo
anómalo es el comportamiento del grupo respecto de su vecindario. Es lo
contrario del generador que ya trae el simulador, que produce anomalías
independientes por medidor a +6σ de la media y que cualquier umbral separa
sin error.

Paquete separado de `monitor-gsp` a propósito: lo que produce la verdad de
referencia no comparte paquete con lo que se puntúa contra ella. El
aislamiento es verificable — este paquete no importa nada del detector.

```python
from urbia_events import CollectiveDeviationSpec, EventInjector, load_bounds, load_profile

inyector = EventInjector(
    profile=load_profile(Path("data/profiles/manizales_signal_v1.json")),
    bounds=load_bounds(Path("data/schemas/payload_schema_v1.json")),
    seed=20260808,
)
señal, verdad = inyector.inject(
    zona,
    lecturas,
    [CollectiveDeviationSpec(magnitude="voltaje_v", depth=1, sigma_multiple=1.0)],
)
verdad.node_mask(instant=0)     # qué nodos son anómalos
```
"""

from .bounds import load_bounds
from .families import (
    FAMILY_COLLECTIVE,
    TemporalProfile,
    apply_collective_deviation,
    step_profile,
)
from .injector import EventInjector
from .neighborhood import k_hop, neighborhood_sizes
from .profile import SignalProfile, load_profile
from .types import (
    DEVICE_TYPES,
    MAGNITUDES,
    BoundsViolationError,
    CollectiveDeviationSpec,
    DeviceType,
    Direction,
    EventInjectorError,
    GroundTruth,
    InjectedEvent,
    InvalidSpecError,
    Magnitude,
    MagnitudeProfile,
    SignalBounds,
    UnknownDeviceError,
    device_type_of,
)

__all__ = [
    "DEVICE_TYPES",
    "FAMILY_COLLECTIVE",
    "MAGNITUDES",
    "BoundsViolationError",
    "CollectiveDeviationSpec",
    "DeviceType",
    "Direction",
    "EventInjector",
    "EventInjectorError",
    "GroundTruth",
    "InjectedEvent",
    "InvalidSpecError",
    "Magnitude",
    "MagnitudeProfile",
    "SignalBounds",
    "SignalProfile",
    "TemporalProfile",
    "UnknownDeviceError",
    "apply_collective_deviation",
    "device_type_of",
    "k_hop",
    "load_bounds",
    "load_profile",
    "neighborhood_sizes",
    "step_profile",
]
