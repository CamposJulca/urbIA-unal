"""Modelo de medidor AMI virtual y schema Pydantic del payload.

Define:
- ``TelemetryPayload``: validador Pydantic v2 del JSON publicado.
- ``Meter``: clase con estado interno (energía acumulada) que produce
  una lectura nueva en cada llamada a ``generate_reading()``.

Schema completo en ``services/simulator-ami/SCHEMA.md``.
"""

from __future__ import annotations

import math
import random
import time
from datetime import datetime, timezone
from typing import Final

from pydantic import BaseModel, ConfigDict, Field, field_validator


# --- Distribución determinística zone ← index del medidor -------------
# Patrón cíclico: 2 medidores por zona. Para N>10 el patrón se repite.
_ZONE_CYCLE: Final[tuple[str, ...]] = (
    "MNZ-CENTRO",
    "MNZ-CENTRO",
    "MNZ-NORTE",
    "MNZ-NORTE",
    "MNZ-SUR",
    "MNZ-SUR",
    "MNZ-ESTE",
    "MNZ-ESTE",
    "MNZ-OESTE",
    "MNZ-OESTE",
)
VALID_ZONES: Final[frozenset[str]] = frozenset(_ZONE_CYCLE)

# --- Rangos de las magnitudes eléctricas (ver SCHEMA.md) --------------
VOLTAGE_NOMINAL: Final[float] = 120.0
VOLTAGE_SIGMA: Final[float] = 1.0          # σ realista
VOLTAGE_MIN: Final[float] = 100.0
VOLTAGE_MAX: Final[float] = 130.0

CURRENT_NOMINAL: Final[float] = 8.0
CURRENT_SIGMA: Final[float] = 1.5
CURRENT_DAILY_AMPLITUDE: Final[float] = 3.0  # ±3 A por curva diaria
CURRENT_MIN: Final[float] = 0.0
CURRENT_MAX: Final[float] = 50.0

FREQUENCY_NOMINAL: Final[float] = 60.0
FREQUENCY_SIGMA: Final[float] = 0.025
FREQUENCY_MIN: Final[float] = 59.5
FREQUENCY_MAX: Final[float] = 60.5

POWER_FACTOR_NOMINAL: Final[float] = 0.95
POWER_FACTOR_SIGMA: Final[float] = 0.02
POWER_FACTOR_MIN: Final[float] = 0.0
POWER_FACTOR_MAX: Final[float] = 1.0

METER_ID_REGEX: Final[str] = r"^AMI-MNZ-\d{5}$"
METER_INDEX_MIN: Final[int] = 1
METER_INDEX_MAX: Final[int] = 99999

VALID_STATUSES: Final[frozenset[str]] = frozenset({"NORMAL", "WARNING", "ALARM"})


class TelemetryPayload(BaseModel):
    """Schema Pydantic v2 que valida cada mensaje antes de publicarlo."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    meter_id: str = Field(pattern=METER_ID_REGEX)
    timestamp: str
    voltage_v: float = Field(ge=VOLTAGE_MIN, le=VOLTAGE_MAX)
    current_a: float = Field(ge=CURRENT_MIN, le=CURRENT_MAX)
    power_kw: float = Field(ge=0.0)
    energy_kwh: float = Field(ge=0.0)
    frequency_hz: float = Field(ge=FREQUENCY_MIN, le=FREQUENCY_MAX)
    power_factor: float = Field(ge=POWER_FACTOR_MIN, le=POWER_FACTOR_MAX)
    zone: str
    status: str

    @field_validator("zone")
    @classmethod
    def _validate_zone(cls, v: str) -> str:
        if v not in VALID_ZONES:
            raise ValueError(f"zone {v!r} no está en el enum permitido")
        return v

    @field_validator("status")
    @classmethod
    def _validate_status(cls, v: str) -> str:
        if v not in VALID_STATUSES:
            raise ValueError(f"status {v!r} no está en el enum permitido")
        return v


def build_meter_id(index: int) -> str:
    """Devuelve el meter_id canónico para un índice 1-based."""
    if not (METER_INDEX_MIN <= index <= METER_INDEX_MAX):
        raise ValueError(
            f"index {index} fuera de rango "
            f"[{METER_INDEX_MIN}, {METER_INDEX_MAX}]"
        )
    return f"AMI-MNZ-{index:05d}"


def zone_for_index(index: int) -> str:
    """Devuelve la zona asignada al medidor #index (1-based)."""
    return _ZONE_CYCLE[(index - 1) % len(_ZONE_CYCLE)]


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _daily_load_factor(now: datetime) -> float:
    """Modulación diaria del consumo: pico ~19h, valle ~07h."""
    hour = now.hour + now.minute / 60.0 + now.second / 3600.0
    # Senoidal con pico en hora 19 (1 cuando hour=19, -1 cuando hour=7).
    return math.sin(2 * math.pi * (hour - 13) / 24)


def _iso8601_utc_ms(now: datetime) -> str:
    """Serializa datetime UTC en ISO 8601 con sufijo Z y milisegundos."""
    return now.isoformat(timespec="milliseconds").replace("+00:00", "Z")


class Meter:
    """Medidor AMI virtual con estado de energía acumulada.

    ``meter_id`` y ``zone`` se derivan de ``index`` (1-based) y son
    estables entre reinicios del proceso. La energía acumulada
    ``energy_kwh`` se reinicia al instanciar el objeto (aceptable en
    v1.0; la persistencia real es trabajo futuro).

    Args:
        index: índice 1-based del medidor (1..99999).
        rng: generador aleatorio inyectable (útil para tests
            determinísticos). Por defecto se usa ``random.Random()``.
    """

    def __init__(
        self,
        index: int,
        rng: random.Random | None = None,
    ) -> None:
        self.meter_id: str = build_meter_id(index)
        self.zone: str = zone_for_index(index)
        self._rng: random.Random = rng if rng is not None else random.Random()
        self._energy_kwh: float = 0.0
        self._last_monotonic: float | None = None

    def generate_reading(self) -> dict[str, object]:
        """Produce una lectura nueva y actualiza energía acumulada.

        Returns:
            Diccionario JSON-serializable que pasa validación contra
            ``TelemetryPayload``.
        """
        now_utc = datetime.now(timezone.utc)

        voltage_v = _clamp(
            self._rng.gauss(VOLTAGE_NOMINAL, VOLTAGE_SIGMA),
            VOLTAGE_MIN,
            VOLTAGE_MAX,
        )

        current_mean = CURRENT_NOMINAL + CURRENT_DAILY_AMPLITUDE * _daily_load_factor(now_utc)
        current_a = _clamp(
            self._rng.gauss(current_mean, CURRENT_SIGMA),
            CURRENT_MIN,
            CURRENT_MAX,
        )

        frequency_hz = _clamp(
            self._rng.gauss(FREQUENCY_NOMINAL, FREQUENCY_SIGMA),
            FREQUENCY_MIN,
            FREQUENCY_MAX,
        )
        power_factor = _clamp(
            self._rng.gauss(POWER_FACTOR_NOMINAL, POWER_FACTOR_SIGMA),
            POWER_FACTOR_MIN,
            POWER_FACTOR_MAX,
        )

        power_kw = round(voltage_v * current_a * power_factor / 1000.0, 3)

        # Energía acumulada: integra power * dt. Usar time.monotonic()
        # para que el delta no salte por ajustes de reloj.
        now_mono = time.monotonic()
        if self._last_monotonic is not None:
            elapsed_s = max(0.0, now_mono - self._last_monotonic)
            self._energy_kwh += power_kw * (elapsed_s / 3600.0)
        self._last_monotonic = now_mono

        payload: dict[str, object] = {
            "meter_id": self.meter_id,
            "timestamp": _iso8601_utc_ms(now_utc),
            "voltage_v": round(voltage_v, 2),
            "current_a": round(current_a, 2),
            "power_kw": power_kw,
            "energy_kwh": round(self._energy_kwh, 6),
            "frequency_hz": round(frequency_hz, 3),
            "power_factor": round(power_factor, 3),
            "zone": self.zone,
            "status": "NORMAL",
        }
        # Validación local: si alguna magnitud salió del rango por una
        # combinación rara de jitter + clamp, esto eleva ValidationError
        # y el caller decide qué hacer.
        TelemetryPayload.model_validate(payload)
        return payload
