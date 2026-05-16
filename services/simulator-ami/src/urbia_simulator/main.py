"""Entry point del simulador AMI.

Conecta a un broker MQTT, instancia N medidores y publica una lectura
de cada medidor a la tasa configurada. Maneja SIGINT/SIGTERM para
parar limpiamente, y escribe un archivo PID que la HEALTHCHECK de
Docker usa para confirmar que el proceso vive.
"""

from __future__ import annotations

import json
import logging
import os
import signal
import sys
import time
from pathlib import Path
from types import FrameType

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion
from pydantic import ValidationError

from urbia_simulator.config import Settings, load_settings
from urbia_simulator.meter import Meter


PID_FILE: Path = Path("/tmp/urbia-simulator.pid")
TOPIC_TEMPLATE: str = "urbia/ami/{meter_id}/telemetry"

LOG_FORMAT = "%(asctime)s - %(levelname)s - %(meter_id)s - %(message)s"
LOG_DATEFMT = "%Y-%m-%dT%H:%M:%S%z"


class _MeterIdInjector(logging.Filter):
    """Asegura que cada LogRecord tenga el campo ``meter_id``."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "meter_id"):
            record.meter_id = "system"
        return True


def _configure_logging(level: str) -> logging.Logger:
    logger = logging.getLogger("urbia_simulator")
    logger.setLevel(level.upper())
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=LOG_DATEFMT))
    handler.addFilter(_MeterIdInjector())
    logger.handlers = [handler]
    logger.propagate = False
    return logger


def _build_mqtt_client(settings: Settings, logger: logging.Logger) -> mqtt.Client:
    client_id = f"urbia-simulator-{os.getpid()}"
    client = mqtt.Client(
        callback_api_version=CallbackAPIVersion.VERSION2,
        client_id=client_id,
        protocol=mqtt.MQTTv311,
    )
    if settings.mqtt_auth_enabled:
        client.username_pw_set(settings.mqtt_username, settings.mqtt_password)
        logger.info("MQTT con auth habilitada (usuario=%s)", settings.mqtt_username)
    else:
        logger.info("MQTT en modo anónimo (sin auth)")

    def on_connect(_c, _u, _flags, reason_code, _props=None) -> None:
        logger.info("Conectado al broker (reason_code=%s)", reason_code)

    def on_disconnect(_c, _u, _flags, reason_code, _props=None) -> None:
        logger.warning("Desconectado del broker (reason_code=%s)", reason_code)

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    return client


class _RunFlag:
    """Bandera de parada compartida con los handlers de señal."""

    def __init__(self) -> None:
        self.running: bool = True


def _install_signal_handlers(flag: _RunFlag, logger: logging.Logger) -> None:
    def handler(signum: int, _frame: FrameType | None) -> None:
        name = signal.Signals(signum).name
        logger.info("Señal %s recibida; parando…", name)
        flag.running = False

    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)


def _publish_meter(
    client: mqtt.Client,
    meter: Meter,
    logger: logging.Logger,
) -> None:
    try:
        payload = meter.generate_reading()
    except ValidationError as exc:
        logger.error(
            "payload inválido, descartado: %s",
            exc,
            extra={"meter_id": meter.meter_id},
        )
        return

    topic = TOPIC_TEMPLATE.format(meter_id=meter.meter_id)
    body = json.dumps(payload, separators=(",", ":"))
    result = client.publish(topic, body, qos=0, retain=False)
    if result.rc != mqtt.MQTT_ERR_SUCCESS:
        logger.error(
            "publish falló rc=%s en %s",
            result.rc,
            topic,
            extra={"meter_id": meter.meter_id},
        )


def _write_pid_file() -> None:
    PID_FILE.write_text(f"{os.getpid()}\n", encoding="utf-8")


def _remove_pid_file() -> None:
    try:
        PID_FILE.unlink(missing_ok=True)
    except OSError:
        pass


def main() -> int:
    settings = load_settings()
    logger = _configure_logging(settings.log_level)
    logger.info(
        "Arrancando simulador: meters=%d rate=%.2fHz broker=%s:%d",
        settings.simulator_num_meters,
        settings.simulator_publish_rate_hz,
        settings.mqtt_host,
        settings.mqtt_port,
    )

    meters = [Meter(i) for i in range(1, settings.simulator_num_meters + 1)]
    for m in meters:
        logger.info(
            "meter inicializado zone=%s",
            m.zone,
            extra={"meter_id": m.meter_id},
        )

    client = _build_mqtt_client(settings, logger)
    flag = _RunFlag()
    _install_signal_handlers(flag, logger)

    try:
        client.connect(settings.mqtt_host, settings.mqtt_port, keepalive=30)
    except OSError as exc:
        logger.error(
            "No pude conectar a %s:%d — %s",
            settings.mqtt_host,
            settings.mqtt_port,
            exc,
        )
        return 2

    client.loop_start()
    _write_pid_file()

    interval = settings.publish_interval_s
    try:
        while flag.running:
            tick_start = time.monotonic()
            for meter in meters:
                _publish_meter(client, meter, logger)
            # Espera cancelable: revisa el flag cada 100 ms para
            # responder rápido a SIGINT/SIGTERM.
            deadline = tick_start + interval
            while flag.running and time.monotonic() < deadline:
                time.sleep(min(0.1, max(0.0, deadline - time.monotonic())))
    finally:
        logger.info("Cerrando cliente MQTT…")
        client.loop_stop()
        client.disconnect()
        _remove_pid_file()
        logger.info("Simulador detenido limpiamente.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
