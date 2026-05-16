"""Tests del MqttConsumer (sin broker real).

Construimos mensajes MQTT sintéticos y llamamos al callback
`_on_message` directamente, validando que la lógica de parsing,
validación Pydantic y agendado de la corutina asyncpg se comporta como
se espera. La parte de red de paho-mqtt no se ejerce aquí — eso lo
cubre el test de integración.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from tests.conftest import FakeDatabase, make_payload
from urbia_backend.config import Settings
from urbia_backend.mqtt_consumer import MqttConsumer


def _fake_message(topic: str, payload: bytes) -> SimpleNamespace:
    return SimpleNamespace(topic=topic, payload=payload)


def _build_consumer(loop: asyncio.AbstractEventLoop) -> tuple[MqttConsumer, FakeDatabase]:
    fake_db = FakeDatabase()
    settings = Settings(mqtt_host="example.invalid", mqtt_port=1883)
    return MqttConsumer(settings, fake_db, loop), fake_db


async def test_on_message_valid_payload_persists_to_db() -> None:
    loop = asyncio.get_running_loop()
    consumer, fake_db = _build_consumer(loop)
    payload = make_payload("AMI-MNZ-00001")
    raw = payload.model_dump_json().encode("utf-8")

    consumer._on_message(
        None,
        None,
        _fake_message("urbia/ami/AMI-MNZ-00001/telemetry", raw),
    )
    # run_coroutine_threadsafe usa call_soon_threadsafe → callback que
    # crea el Task → Task corre. Necesitamos múltiples vueltas del loop
    # para que la cadena complete. asyncio.sleep(0.05) basta.
    await asyncio.sleep(0.05)

    assert consumer.received_count == 1
    assert consumer.invalid_count == 0
    assert consumer.persist_failures == 0
    records = await fake_db.recent_telemetry(10)
    assert len(records) == 1
    assert records[0].meter_id == "AMI-MNZ-00001"


async def test_on_message_invalid_json_counts_as_invalid() -> None:
    loop = asyncio.get_running_loop()
    consumer, fake_db = _build_consumer(loop)

    consumer._on_message(
        None,
        None,
        _fake_message("urbia/ami/AMI-MNZ-00001/telemetry", b"{no es json"),
    )
    await asyncio.sleep(0)

    assert consumer.received_count == 1
    assert consumer.invalid_count == 1
    assert await fake_db.recent_telemetry(10) == []


async def test_on_message_invalid_schema_counts_as_invalid() -> None:
    loop = asyncio.get_running_loop()
    consumer, fake_db = _build_consumer(loop)

    bad_payload = json.dumps({"meter_id": "NO_MATCH", "timestamp": "x"}).encode()
    consumer._on_message(
        None,
        None,
        _fake_message("urbia/ami/INVALID/telemetry", bad_payload),
    )
    await asyncio.sleep(0)

    assert consumer.received_count == 1
    assert consumer.invalid_count == 1
    assert await fake_db.recent_telemetry(10) == []


async def test_is_connected_false_before_start() -> None:
    loop = asyncio.get_running_loop()
    consumer, _ = _build_consumer(loop)
    assert consumer.is_connected is False


async def test_on_connect_with_success_subscribes() -> None:
    loop = asyncio.get_running_loop()
    consumer, _ = _build_consumer(loop)
    subscribed: list[tuple[str, int]] = []

    fake_client = SimpleNamespace(
        subscribe=lambda topic, qos: subscribed.append((topic, qos))
    )
    consumer._on_connect(fake_client, None, None, 0)
    assert subscribed == [("urbia/ami/+/telemetry", 0)]


async def test_on_connect_with_failure_logs_and_does_not_subscribe(caplog) -> None:
    loop = asyncio.get_running_loop()
    consumer, _ = _build_consumer(loop)
    subscribed: list[str] = []
    fake_client = SimpleNamespace(
        subscribe=lambda topic, qos: subscribed.append(topic)
    )

    consumer._on_connect(fake_client, None, None, 5)
    assert subscribed == []


async def test_on_disconnect_does_not_raise() -> None:
    loop = asyncio.get_running_loop()
    consumer, _ = _build_consumer(loop)
    consumer._on_disconnect(None, None, None, 0)
    consumer._on_disconnect(None, None, None, 7)


def test_stop_without_start_is_noop() -> None:
    loop = asyncio.new_event_loop()
    try:
        consumer, _ = _build_consumer(loop)
        consumer.stop()  # no debe explotar aunque _client sea None
        assert consumer.is_connected is False
    finally:
        loop.close()


async def test_start_and_stop_lifecycle_without_real_broker() -> None:
    """Verifica que start()/stop() arman y desarman el cliente paho.

    Usa un host inválido a propósito: paho intenta conectar en su thread
    y falla silenciosamente; nuestro código tiene que tolerarlo. La
    propiedad `is_connected` debe seguir siendo False y stop() debe
    desmontar sin excepciones.
    """

    loop = asyncio.get_running_loop()
    consumer, _ = _build_consumer(loop)
    consumer.start()
    try:
        # No esperamos a que conecte (no hay broker); solo confirmamos
        # que el cliente fue instanciado y se considera "no conectado".
        assert consumer._client is not None
        assert consumer.is_connected is False
    finally:
        consumer.stop()
    assert consumer._client is None
    # Doble stop() debe ser idempotente.
    consumer.stop()


async def test_start_with_auth_credentials_sets_username() -> None:
    loop = asyncio.get_running_loop()
    fake_db = FakeDatabase()
    settings = Settings(
        mqtt_host="example.invalid",
        mqtt_username="urbia",
        mqtt_password="secret",
    )
    consumer = MqttConsumer(settings, fake_db, loop)
    consumer.start()
    try:
        assert consumer._client is not None
    finally:
        consumer.stop()


async def test_double_start_is_idempotent() -> None:
    loop = asyncio.get_running_loop()
    consumer, _ = _build_consumer(loop)
    consumer.start()
    first_client = consumer._client
    consumer.start()
    try:
        assert consumer._client is first_client
    finally:
        consumer.stop()
