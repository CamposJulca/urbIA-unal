"""Tests del backend UrbIA.

8 tests unitarios contra `FakeDatabase` + `FakeMqttConsumer` y 1 test
de integración que requiere PostgreSQL real (marcado para que se pueda
correr con `pytest -m integration`).
"""

from __future__ import annotations

from datetime import timedelta

import asyncpg
import pytest

from tests.conftest import (
    FakeDatabase,
    FakeMqttConsumer,
    fresh_timestamp,
    integration_db_dsn,
    make_payload,
)
from urbia_backend.db import Database
from urbia_backend.models import TelemetryPayload


# ----- 1) health -----

async def test_health_endpoint_returns_200(client) -> None:
    response = await client.get("/health")
    assert response.status_code == 200


async def test_health_reports_db_and_mqtt_status(
    client, fake_db: FakeDatabase, fake_mqtt: FakeMqttConsumer
) -> None:
    fake_db.ping_result = True
    fake_mqtt.connected = True
    body = (await client.get("/health")).json()
    assert body == {"status": "ok", "db": True, "mqtt": True}

    fake_db.ping_result = False
    body = (await client.get("/health")).json()
    assert body == {"status": "degraded", "db": False, "mqtt": True}

    fake_db.ping_result = True
    fake_mqtt.connected = False
    body = (await client.get("/health")).json()
    assert body == {"status": "degraded", "db": True, "mqtt": False}


# ----- 2) /meters -----

async def test_meters_endpoint_empty_returns_empty_array(client) -> None:
    response = await client.get("/meters")
    assert response.status_code == 200
    assert response.json() == []


async def test_meters_endpoint_returns_meters_after_seed(
    client, fake_db: FakeDatabase
) -> None:
    await fake_db.insert_telemetry(make_payload("AMI-MNZ-00001", zone="MNZ-CENTRO"))
    await fake_db.insert_telemetry(make_payload("AMI-MNZ-00002", zone="MNZ-CENTRO"))
    await fake_db.insert_telemetry(make_payload("AMI-MNZ-00003", zone="MNZ-NORTE"))

    response = await client.get("/meters")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 3
    meter_ids = [m["meter_id"] for m in body]
    assert meter_ids == sorted(meter_ids)
    assert all(m["is_active"] is True for m in body)
    assert all(m["last_seen"] is not None for m in body)


# ----- 3) /telemetry/recent -----

async def test_telemetry_recent_format(client, fake_db: FakeDatabase) -> None:
    await fake_db.insert_telemetry(
        make_payload("AMI-MNZ-00001", voltage_v=121.5, current_a=8.2)
    )
    response = await client.get("/telemetry/recent?limit=1")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    record = body[0]
    expected_fields = {
        "id",
        "meter_id",
        "timestamp",
        "voltage_v",
        "current_a",
        "power_kw",
        "energy_kwh",
        "frequency_hz",
        "power_factor",
        "zone",
        "status",
        "received_at",
    }
    assert expected_fields <= set(record.keys())
    assert record["meter_id"] == "AMI-MNZ-00001"
    assert record["voltage_v"] == pytest.approx(121.5)


async def test_telemetry_recent_respects_limit(
    client, fake_db: FakeDatabase
) -> None:
    for i in range(10):
        await fake_db.insert_telemetry(make_payload(f"AMI-MNZ-{i:05d}"))

    assert len((await client.get("/telemetry/recent?limit=3")).json()) == 3
    assert len((await client.get("/telemetry/recent")).json()) == 10
    # Fuera de rango → 422 por validación de FastAPI.
    assert (await client.get("/telemetry/recent?limit=0")).status_code == 422
    assert (await client.get("/telemetry/recent?limit=1001")).status_code == 422


# ----- 4) /meters/{id}/telemetry/latest -----

async def test_meter_telemetry_latest(
    client, fake_db: FakeDatabase
) -> None:
    base = fresh_timestamp()
    for i in range(3):
        await fake_db.insert_telemetry(
            make_payload(
                "AMI-MNZ-00001",
                timestamp=base + timedelta(seconds=i),
                voltage_v=120.0 + i,
            )
        )

    response = await client.get("/meters/AMI-MNZ-00001/telemetry/latest")
    assert response.status_code == 200
    body = response.json()
    assert body["meter_id"] == "AMI-MNZ-00001"
    assert body["voltage_v"] == pytest.approx(122.0)

    # 404 cuando no hay registros.
    response = await client.get("/meters/AMI-MNZ-99999/telemetry/latest")
    assert response.status_code == 404

    # 422 cuando meter_id no matchea el regex.
    response = await client.get("/meters/INVALIDO/telemetry/latest")
    assert response.status_code == 422


# ----- 5) /meters/{id}/telemetry?limit=N -----

async def test_meter_telemetry_history_with_limit(
    client, fake_db: FakeDatabase
) -> None:
    base = fresh_timestamp()
    for i in range(5):
        await fake_db.insert_telemetry(
            make_payload(
                "AMI-MNZ-00001",
                timestamp=base + timedelta(seconds=i),
                voltage_v=120.0 + i,
            )
        )

    response = await client.get("/meters/AMI-MNZ-00001/telemetry?limit=2")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    # Más recientes primero (received_at DESC).
    assert body[0]["voltage_v"] >= body[1]["voltage_v"]

    response = await client.get("/meters/AMI-MNZ-00001/telemetry")
    assert len(response.json()) == 5


# ----- 6) Integration: MQTT → DB persiste de verdad -----

@pytest.mark.integration
async def test_mqtt_message_persists_to_db() -> None:
    """Test end-to-end real: inserta vía `Database` y verifica con SQL.

    No depende del cliente MQTT (probarlo aquí requeriría un broker
    real y un timing frágil). Lo que sí queremos verificar es que el
    path "payload validado → INSERT + UPSERT" funciona contra el
    Postgres real con el schema de `001_initial.sql`.
    """

    dsn = integration_db_dsn()
    if dsn is None:
        pytest.skip("Variables de entorno POSTGRES_* incompletas")

    import os

    from urbia_backend.config import Settings

    # Trato de conectar antes de empezar; si no, skip.
    try:
        probe = await asyncpg.connect(dsn=dsn, timeout=2)
    except (asyncpg.PostgresError, OSError) as exc:
        pytest.skip(f"PostgreSQL no accesible: {exc}")

    sentinel_meter = "AMI-MNZ-99001"
    try:
        await probe.execute(
            "DELETE FROM ami_telemetry WHERE meter_id = $1", sentinel_meter
        )
        await probe.execute(
            "DELETE FROM ami_meters WHERE meter_id = $1", sentinel_meter
        )
    finally:
        await probe.close()

    settings = Settings(
        postgres_host=os.environ["POSTGRES_HOST"],
        postgres_port=int(os.environ.get("POSTGRES_PORT", "5432")),
        postgres_user=os.environ["POSTGRES_USER"],
        postgres_password=os.environ["POSTGRES_PASSWORD"],
        postgres_db=os.environ["POSTGRES_DB"],
    )
    database = Database(settings)
    await database.connect()
    try:
        payload = TelemetryPayload(
            meter_id=sentinel_meter,
            timestamp=fresh_timestamp(),
            voltage_v=120.5,
            current_a=8.1,
            power_kw=0.93,
            energy_kwh=42.0,
            frequency_hz=60.01,
            power_factor=0.96,
            zone="MNZ-TEST",
            status="NORMAL",
        )
        await database.insert_telemetry(payload)

        latest = await database.latest_for_meter(sentinel_meter)
        assert latest is not None
        assert latest.meter_id == sentinel_meter
        assert latest.voltage_v == pytest.approx(120.5)
        assert latest.zone == "MNZ-TEST"

        meters = await database.list_meters()
        sentinel = next(
            (m for m in meters if m.meter_id == sentinel_meter), None
        )
        assert sentinel is not None
        assert sentinel.zone == "MNZ-TEST"
        assert sentinel.last_seen is not None

        # ping + history + recent ejercen las demás queries del wrapper.
        assert await database.ping() is True

        history = await database.history_for_meter(sentinel_meter, limit=5)
        assert len(history) >= 1
        assert history[0].meter_id == sentinel_meter

        recent = await database.recent_telemetry(limit=100)
        assert any(r.meter_id == sentinel_meter for r in recent)

        # latest_for_meter sobre un id inexistente devuelve None.
        missing = await database.latest_for_meter("AMI-MNZ-99998")
        assert missing is None
    finally:
        cleanup = await asyncpg.connect(dsn=dsn)
        try:
            await cleanup.execute(
                "DELETE FROM ami_telemetry WHERE meter_id = $1",
                sentinel_meter,
            )
            await cleanup.execute(
                "DELETE FROM ami_meters WHERE meter_id = $1", sentinel_meter
            )
        finally:
            await cleanup.close()
        await database.disconnect()
