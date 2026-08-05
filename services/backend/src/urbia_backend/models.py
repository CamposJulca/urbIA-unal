"""Modelos Pydantic v2 del backend UrbIA.

Dos contratos deliberadamente asimétricos:

* **Entrada (MQTT).** `TelemetryPayload` refleja el mensaje que publica
  el productor externo bajo `urbia/manizales/#` con el esquema AMI v2:
  todos los campos en español, igual que las columnas de
  `ami_telemetry`. Ver `services/backend/SCHEMA.md`.
* **Salida (REST).** `TelemetryRecord` y `MeterInfo` conservan los
  nombres en inglés que el frontend ya consume (`meter_id`,
  `voltage_v`, `zone`, `received_at`, …). La traducción se hace con
  alias en el SELECT de `db.py`, no renombrando columnas.

Los campos nuevos del esquema v2 que el frontend no consumía antes
(`device_type`, `nodo_origen`, `lenguaje`, `seed`, `lat`, `lon`) se
exponen con su nombre de columna: no hay nombre en inglés previo que
preservar y traducirlos inventaría vocabulario.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# `urbia-<zona>-<tipo>-NNNN`; zona ∈ {cen, chi, ena, pal, pgr, uni},
# tipo ∈ {mon, tri} (monofásico / trifásico).
DEVICE_ID_PATTERN = r"^urbia-(cen|chi|ena|pal|pgr|uni)-(mon|tri)-[0-9]{4}$"
DEVICE_ID_MAX_LENGTH = 32


class TelemetryPayload(BaseModel):
    """Mensaje MQTT recibido del productor AMI (esquema v2).

    `extra="ignore"` deja pasar campos que el productor agregue más
    adelante sin tumbar la ingesta. Pydantic v2 acepta directamente
    ISO 8601 con sufijo `Z` para `datetime`.
    """

    model_config = ConfigDict(extra="ignore")

    device_id: str = Field(
        pattern=DEVICE_ID_PATTERN, max_length=DEVICE_ID_MAX_LENGTH
    )
    device_type: Optional[str] = Field(default=None, max_length=16)
    zona: Optional[str] = Field(default=None, max_length=32)
    timestamp_utc: datetime
    voltaje_v: float
    corriente_a: float
    potencia_kw: float
    energia_kwh: Optional[float] = None
    frecuencia_hz: float
    factor_potencia: float
    estado: Optional[str] = Field(default=None, max_length=24)
    nodo_origen: Optional[str] = Field(default=None, max_length=24)
    lenguaje: Optional[str] = Field(default=None, max_length=8)
    seed: Optional[int] = None
    # Georreferencia: no va a ami_telemetry (es metadato, no serie de
    # tiempo) pero alimenta el UPSERT de ami_meters cuando el productor
    # la incluye.
    lat: Optional[float] = None
    lon: Optional[float] = None


class TelemetryRecord(BaseModel):
    """Telemetría serializada para la API REST (fila de `ami_telemetry`)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    meter_id: str
    device_type: Optional[str] = None
    zone: Optional[str] = None
    timestamp: datetime
    voltage_v: float
    current_a: float
    power_kw: float
    energy_kwh: Optional[float] = None
    frequency_hz: float
    power_factor: float
    status: Optional[str] = None
    nodo_origen: Optional[str] = None
    lenguaje: Optional[str] = None
    seed: Optional[int] = None
    received_at: datetime


class MeterInfo(BaseModel):
    """Metadato de medidor (fila de `ami_meters`)."""

    model_config = ConfigDict(from_attributes=True)

    meter_id: str
    device_type: Optional[str] = None
    zone: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    nodo_origen: Optional[str] = None
    installed_at: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    is_active: bool = True


class HealthResponse(BaseModel):
    """Cuerpo de `GET /health`."""

    status: str
    db: bool
    mqtt: bool
