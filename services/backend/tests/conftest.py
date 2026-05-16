"""Fixtures compartidas para los tests del backend UrbIA.

Levanta una FastAPI app de prueba con `Database` y `MqttConsumer`
sustituidos por fakes en memoria — sin tocar PostgreSQL ni el broker.
El test de integración (marcado con `@pytest.mark.integration`) usa
fixtures distintas que SÍ requieren Postgres real.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from urbia_backend.api.telemetry import router as telemetry_router
from urbia_backend.models import MeterInfo, TelemetryPayload, TelemetryRecord


class FakeDatabase:
    """Sustituto in-memory de `urbia_backend.db.Database` para tests."""

    def __init__(self) -> None:
        self._records: list[TelemetryRecord] = []
        self._meters: dict[str, MeterInfo] = {}
        self._next_id: int = 1
        self.ping_result: bool = True

    async def ping(self) -> bool:
        return self.ping_result

    async def insert_telemetry(self, payload: TelemetryPayload) -> None:
        now = datetime.now(timezone.utc)
        record = TelemetryRecord(
            id=self._next_id,
            meter_id=payload.meter_id,
            timestamp=payload.timestamp,
            voltage_v=payload.voltage_v,
            current_a=payload.current_a,
            power_kw=payload.power_kw,
            energy_kwh=payload.energy_kwh,
            frequency_hz=payload.frequency_hz,
            power_factor=payload.power_factor,
            zone=payload.zone,
            status=payload.status,
            received_at=now,
        )
        self._next_id += 1
        self._records.append(record)
        previous = self._meters.get(payload.meter_id)
        installed_at = previous.installed_at if previous is not None else now
        zone = payload.zone or (previous.zone if previous is not None else None)
        self._meters[payload.meter_id] = MeterInfo(
            meter_id=payload.meter_id,
            zone=zone,
            installed_at=installed_at,
            last_seen=payload.timestamp,
            is_active=True,
        )

    async def list_meters(self) -> list[MeterInfo]:
        return sorted(
            (m for m in self._meters.values() if m.is_active),
            key=lambda m: m.meter_id,
        )

    async def latest_for_meter(
        self, meter_id: str
    ) -> Optional[TelemetryRecord]:
        records = [r for r in self._records if r.meter_id == meter_id]
        if not records:
            return None
        return max(records, key=lambda r: r.received_at)

    async def history_for_meter(
        self, meter_id: str, limit: int
    ) -> list[TelemetryRecord]:
        records = [r for r in self._records if r.meter_id == meter_id]
        records.sort(key=lambda r: r.received_at, reverse=True)
        return records[:limit]

    async def recent_telemetry(self, limit: int) -> list[TelemetryRecord]:
        records = sorted(
            self._records, key=lambda r: r.received_at, reverse=True
        )
        return records[:limit]


class FakeMqttConsumer:
    """Sustituto de `MqttConsumer` que solo expone `is_connected`."""

    def __init__(self, connected: bool = True) -> None:
        self.connected = connected

    @property
    def is_connected(self) -> bool:
        return self.connected


def make_payload(
    meter_id: str = "AMI-MNZ-00001",
    *,
    zone: str = "MNZ-CENTRO",
    timestamp: Optional[datetime] = None,
    voltage_v: float = 120.0,
    current_a: float = 8.0,
    power_kw: float = 0.95,
    energy_kwh: float = 100.0,
) -> TelemetryPayload:
    """Helper para construir payloads válidos en tests."""

    return TelemetryPayload(
        meter_id=meter_id,
        timestamp=timestamp or datetime.now(timezone.utc),
        voltage_v=voltage_v,
        current_a=current_a,
        power_kw=power_kw,
        energy_kwh=energy_kwh,
        frequency_hz=60.0,
        power_factor=0.95,
        zone=zone,
        status="NORMAL",
    )


@pytest.fixture
def fake_db() -> FakeDatabase:
    return FakeDatabase()


@pytest.fixture
def fake_mqtt() -> FakeMqttConsumer:
    return FakeMqttConsumer()


@pytest.fixture
def app(fake_db: FakeDatabase, fake_mqtt: FakeMqttConsumer) -> FastAPI:
    """App FastAPI mínima con fakes en `app.state`. Sin lifespan."""

    test_app = FastAPI(title="urbia-backend-test")
    test_app.state.database = fake_db
    test_app.state.mqtt_consumer = fake_mqtt
    test_app.include_router(telemetry_router)
    return test_app


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ----- Helpers para el test de integración -----

def integration_db_dsn() -> Optional[str]:
    """DSN de Postgres real para tests `@pytest.mark.integration`.

    Devuelve None si las variables de entorno no apuntan a una BD
    accesible. El propio test usa este resultado para skip explícito.
    """

    host = os.environ.get("POSTGRES_HOST")
    user = os.environ.get("POSTGRES_USER")
    password = os.environ.get("POSTGRES_PASSWORD")
    db = os.environ.get("POSTGRES_DB")
    port = os.environ.get("POSTGRES_PORT", "5432")
    if not all([host, user, password, db]):
        return None
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


def fresh_timestamp(offset_seconds: int = 0) -> datetime:
    return datetime.now(timezone.utc) + timedelta(seconds=offset_seconds)
