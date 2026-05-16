"""Modelos Pydantic v2 del backend UrbIA.

Mantiene contrato con services/simulator-ami/SCHEMA.md (AMI-JSON v1.0):
`TelemetryPayload` es el mensaje MQTT que entra, `TelemetryRecord` es
la representación enriquecida con `id` y `received_at` que sale por la
API REST.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


_METER_ID_PATTERN = r"^AMI-MNZ-\d{5}$"


class TelemetryPayload(BaseModel):
    """Mensaje MQTT recibido del simulador AMI.

    Los 10 campos coinciden con el schema v1.0 publicado por el
    simulador. Pydantic v2 acepta directamente ISO 8601 con sufijo `Z`
    para `datetime`.
    """

    model_config = ConfigDict(extra="ignore")

    meter_id: str = Field(pattern=_METER_ID_PATTERN, max_length=20)
    timestamp: datetime
    voltage_v: float
    current_a: float
    power_kw: float
    energy_kwh: float
    frequency_hz: float
    power_factor: float
    zone: Optional[str] = Field(default=None, max_length=50)
    status: Optional[str] = Field(default=None, max_length=20)


class TelemetryRecord(BaseModel):
    """Telemetría serializada para la API REST (fila de `ami_telemetry`)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    meter_id: str
    timestamp: datetime
    voltage_v: float
    current_a: float
    power_kw: float
    energy_kwh: float
    frequency_hz: float
    power_factor: float
    zone: Optional[str] = None
    status: Optional[str] = None
    received_at: datetime


class MeterInfo(BaseModel):
    """Metadato de medidor (fila de `ami_meters`)."""

    model_config = ConfigDict(from_attributes=True)

    meter_id: str
    zone: Optional[str] = None
    installed_at: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    is_active: bool = True


class HealthResponse(BaseModel):
    """Cuerpo de `GET /health`."""

    status: str
    db: bool
    mqtt: bool
