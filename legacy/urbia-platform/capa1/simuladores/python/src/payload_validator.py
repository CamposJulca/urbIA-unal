import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

try:
    from jsonschema import validate, ValidationError
except ImportError:
    raise ImportError("Instalar: pip install --break-system-packages jsonschema")

logger = logging.getLogger(__name__)

SCHEMA_PATH = Path(os.environ.get("COMUN_DIR", "/app/comun")) / "payload_schema_v1.json"


class PayloadValidator:
    """
    Validador de payloads de telemetría UrbIA.
    Tres capas: schema JSON, rangos técnicos, timestamp.
    """

    def __init__(self, schema_path: Path = SCHEMA_PATH):
        with open(schema_path, "r", encoding="utf-8") as f:
            self.schema = json.load(f)
        self.validos_total  = 0
        self.errores_total  = 0

    def validar(self, payload: dict) -> tuple[bool, str]:
        try:
            validate(instance=payload, schema=self.schema)
            self._validar_rangos_tecnicos(payload)
            self.validos_total += 1
            return True, ""
        except ValidationError as e:
            self.errores_total += 1
            campo = e.path[-1] if e.path else "raíz"
            msg = f"Schema inválido — campo '{campo}': {e.message}"
            logger.warning(msg)
            return False, msg
        except ValueError as e:
            self.errores_total += 1
            msg = f"Rango técnico inválido: {str(e)}"
            logger.warning(msg)
            return False, msg

    def _validar_rangos_tecnicos(self, payload: dict):
        v = payload["voltaje_v"]
        if not (187.0 <= v <= 253.0):
            raise ValueError(f"voltaje_v={v} fuera de rango (187–253V)")

        f = payload["frecuencia_hz"]
        if not (57.0 <= f <= 63.0):
            raise ValueError(f"frecuencia_hz={f} fuera de rango (57–63Hz)")

        p_calc = payload["voltaje_v"] * payload["corriente_a"] * payload["factor_potencia"] / 1000
        p_decl = payload["potencia_kw"]
        if p_decl > 0 and abs(p_calc - p_decl) / max(p_calc, 0.001) > 0.20:
            raise ValueError(
                f"potencia_kw={p_decl} incoherente con V×I×fp={p_calc:.3f}kW (diferencia >20%)"
            )

        ts = datetime.fromisoformat(payload["timestamp_utc"].replace("Z", "+00:00"))
        if (ts - datetime.now(timezone.utc)).total_seconds() > 60:
            raise ValueError(f"timestamp_utc está en el futuro")

    def estadisticas(self) -> dict:
        total = self.validos_total + self.errores_total
        return {
            "total_procesados": total,
            "validos":          self.validos_total,
            "errores":          self.errores_total,
            "tasa_exito_pct":   round(self.validos_total / total * 100, 2) if total > 0 else 0
        }
