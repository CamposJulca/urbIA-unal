import json
import logging
import os
import random
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

CATALOGO_PATH = Path(os.environ.get("COMUN_DIR", "/app/comun")) / "medidores_manizales.json"


class SensorBase(ABC):
    """
    Clase abstracta base para todos los simuladores de medidores eléctricos UrbIA.
    Implementaciones: SensorMonofasico, SensorTrifasico
    """

    def __init__(self, device_id: str, seed: int = 42):
        self.device_id   = device_id
        self.seed        = seed
        self.rng         = np.random.default_rng(seed)
        self._activo     = False
        self._mensajes   = 0
        self._errores    = 0

        catalogo = json.load(open(CATALOGO_PATH))
        medidor  = next((m for m in catalogo["medidores"] if m["device_id"] == device_id), None)
        if not medidor:
            raise ValueError(f"device_id '{device_id}' no encontrado en el catálogo")

        self.device_type  = medidor["device_type"]
        self.zona         = medidor["zona"]
        self.lat          = medidor["lat"]
        self.lon          = medidor["lon"]
        self.nodo_origen  = medidor["nodo_origen"]
        self.lenguaje     = medidor["lenguaje"]

    @abstractmethod
    def _generar_valores(self) -> dict:
        """Genera los valores eléctricos del medidor. Implementado en cada subclase."""
        pass

    def generar_lectura(self) -> dict:
        """Genera un payload completo conforme a payload_schema_v1.json."""
        valores = self._generar_valores()
        return {
            "device_id":       self.device_id,
            "device_type":     self.device_type,
            "zona":            self.zona,
            "timestamp_utc":   datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "voltaje_v":       round(valores["voltaje_v"], 3),
            "corriente_a":     round(valores["corriente_a"], 3),
            "potencia_kw":     round(valores["potencia_kw"], 4),
            "frecuencia_hz":   round(valores["frecuencia_hz"], 3),
            "factor_potencia": round(valores["factor_potencia"], 3),
            "lat":             self.lat,
            "lon":             self.lon,
            "estado":          valores.get("estado", "activo"),
            "nodo_origen":     self.nodo_origen,
            "lenguaje":        self.lenguaje,
            "seed":            self.seed,
        }

    def _perfil_horario(self) -> float:
        """Factor de carga según hora del día (0.0 – 1.0)."""
        hora = datetime.now().hour
        if   0  <= hora < 6:  return 0.15   # madrugada — muy bajo
        elif 6  <= hora < 12: return 0.60   # mañana — medio
        elif 12 <= hora < 14: return 0.85   # mediodía — alto
        elif 14 <= hora < 18: return 0.65   # tarde — medio-alto
        elif 18 <= hora < 22: return 0.90   # noche — pico máximo
        else:                 return 0.40   # noche tardía — bajo

    def estadisticas(self) -> dict:
        return {
            "device_id": self.device_id,
            "activo":    self._activo,
            "mensajes":  self._mensajes,
            "errores":   self._errores,
        }
