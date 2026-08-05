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
        """Réplica in-memory del alias español → inglés que hace `db.py`."""

        now = datetime.now(timezone.utc)
        record = TelemetryRecord(
            id=self._next_id,
            meter_id=payload.device_id,
            device_type=payload.device_type,
            zone=payload.zona,
            timestamp=payload.timestamp_utc,
            voltage_v=payload.voltaje_v,
            current_a=payload.corriente_a,
            power_kw=payload.potencia_kw,
            energy_kwh=payload.energia_kwh,
            frequency_hz=payload.frecuencia_hz,
            power_factor=payload.factor_potencia,
            status=payload.estado,
            nodo_origen=payload.nodo_origen,
            lenguaje=payload.lenguaje,
            seed=payload.seed,
            received_at=now,
        )
        self._next_id += 1
        self._records.append(record)
        previous = self._meters.get(payload.device_id)
        installed_at = previous.installed_at if previous is not None else now
        # Mismo COALESCE del UPSERT real: lo que ya se sabía no se pierde.
        def keep(new: object, attr: str) -> object:
            return new if new is not None else (
                getattr(previous, attr) if previous is not None else None
            )

        self._meters[payload.device_id] = MeterInfo(
            meter_id=payload.device_id,
            device_type=keep(payload.device_type, "device_type"),
            zone=keep(payload.zona, "zone"),
            lat=keep(payload.lat, "lat"),
            lon=keep(payload.lon, "lon"),
            nodo_origen=keep(payload.nodo_origen, "nodo_origen"),
            installed_at=installed_at,
            last_seen=payload.timestamp_utc,
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
    device_id: str = "urbia-cen-mon-0001",
    *,
    zona: str = "centro",
    device_type: str = "mon",
    timestamp_utc: Optional[datetime] = None,
    voltaje_v: float = 120.0,
    corriente_a: float = 8.0,
    potencia_kw: float = 0.95,
    energia_kwh: Optional[float] = None,
) -> TelemetryPayload:
    """Helper para construir payloads válidos en tests (esquema v2).

    Los defaults son valores reales del productor, no inventados:
    `estado="activo"`, `lenguaje="python"`, `nodo_origen="192.168.0.103"`
    (el nodo .103 del cluster) y `energia_kwh=None` — el productor no
    reporta energía acumulada en todos los mensajes.
    """

    return TelemetryPayload(
        device_id=device_id,
        device_type=device_type,
        zona=zona,
        timestamp_utc=timestamp_utc or datetime.now(timezone.utc),
        voltaje_v=voltaje_v,
        corriente_a=corriente_a,
        potencia_kw=potencia_kw,
        energia_kwh=energia_kwh,
        frecuencia_hz=60.0,
        factor_potencia=0.95,
        estado="activo",
        nodo_origen="192.168.0.103",
        lenguaje="python",
        seed=42,
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
