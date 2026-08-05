"""Consumidor MQTT del backend UrbIA.

Suscribe al árbol de telemetría AMI v2 (`urbia/manizales/#` por
defecto, configurable con `MQTT_TOPIC_TELEMETRY`), valida cada mensaje
contra `TelemetryPayload` (esquema v2, campos en español — ver
`services/backend/SCHEMA.md`) y lo persiste en PostgreSQL vía
`Database.insert_telemetry`, que en una sola transacción inserta la
fila de `ami_telemetry` y hace UPSERT del medidor en `ami_meters`
(incluidas `lat`/`lon` cuando el mensaje las trae).

El topic no se parsea: el medidor se identifica por el `device_id` del
payload, así que un cambio en la jerarquía del productor no rompe la
ingesta. La contrapartida del comodín `#` es que también entregan los
topics hermanos bajo `urbia/manizales/` que no sean telemetría AMI;
esos fallan la validación Pydantic, suben `invalid_count` y quedan como
WARNING. Si el productor empieza a publicar otra cosa en ese árbol con
volumen, acotar el patrón en vez de filtrar aquí.

paho-mqtt corre su network loop en un thread propio (`loop_start`), así
que el callback `_on_message` se ejecuta FUERA del event loop asyncio
del backend. Para invocar la corutina `db.insert_telemetry` desde ahí
usamos `asyncio.run_coroutine_threadsafe(coro, loop)`, que la agenda en
el loop principal y devuelve un `concurrent.futures.Future`. No
bloqueamos el thread MQTT esperando el resultado: registramos un
done-callback que solo loggea errores. Con 10 msg/s y un pool asyncpg
de 10 conexiones no hay riesgo de backpressure.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import logging
from typing import Optional

import asyncpg
import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion
from pydantic import ValidationError

from .config import Settings
from .db import Database
from .models import TelemetryPayload

logger = logging.getLogger(__name__)


class MqttConsumer:
    """Cliente MQTT que persiste cada mensaje recibido en PostgreSQL."""

    def __init__(
        self,
        settings: Settings,
        database: Database,
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        self._settings = settings
        self._database = database
        self._loop = loop
        self._client: Optional[mqtt.Client] = None
        # Contadores expuestos para debugging y futuras métricas.
        self.received_count: int = 0
        self.invalid_count: int = 0
        self.persist_failures: int = 0

    @property
    def is_connected(self) -> bool:
        return self._client is not None and self._client.is_connected()

    def start(self) -> None:
        """Conecta al broker y arranca el network thread (no bloqueante)."""

        if self._client is not None:
            return

        client = mqtt.Client(
            callback_api_version=CallbackAPIVersion.VERSION2,
            client_id=self._settings.mqtt_client_id,
            protocol=mqtt.MQTTv311,
        )

        if self._settings.mqtt_username:
            client.username_pw_set(
                self._settings.mqtt_username,
                self._settings.mqtt_password,
            )
            logger.info(
                "MQTT con auth habilitada (usuario=%s)",
                self._settings.mqtt_username,
            )
        else:
            logger.info("MQTT en modo anónimo (sin auth)")

        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_message = self._on_message

        client.connect_async(
            self._settings.mqtt_host,
            self._settings.mqtt_port,
            keepalive=self._settings.mqtt_keepalive,
        )
        client.loop_start()
        self._client = client
        logger.info(
            "MQTT consumer arrancado contra %s:%s, topic=%s",
            self._settings.mqtt_host,
            self._settings.mqtt_port,
            self._settings.mqtt_topic_telemetry,
        )

    def stop(self) -> None:
        """Detiene el network thread y desconecta del broker."""

        if self._client is None:
            return
        client = self._client
        self._client = None
        try:
            client.disconnect()
        except OSError:
            logger.exception("Error desconectando del broker MQTT")
        client.loop_stop()
        logger.info("MQTT consumer detenido")

    # ----- Callbacks paho (corren en el thread del network loop) -----

    def _on_connect(
        self,
        client: mqtt.Client,
        _userdata: object,
        _flags: object,
        reason_code: object,
        _properties: object = None,
    ) -> None:
        # reason_code == 0 (o ReasonCode con value 0) significa éxito.
        if getattr(reason_code, "value", reason_code) == 0:
            logger.info(
                "Conectado al broker MQTT, suscribiendo a %s",
                self._settings.mqtt_topic_telemetry,
            )
            client.subscribe(self._settings.mqtt_topic_telemetry, qos=0)
        else:
            logger.error(
                "Conexión MQTT rechazada (reason_code=%s)", reason_code
            )

    def _on_disconnect(
        self,
        _client: mqtt.Client,
        _userdata: object,
        _flags: object,
        reason_code: object,
        _properties: object = None,
    ) -> None:
        # paho reconecta automáticamente mientras loop_start() está vivo.
        code_value = getattr(reason_code, "value", reason_code)
        level = logging.INFO if code_value == 0 else logging.WARNING
        logger.log(
            level,
            "Desconectado del broker MQTT (reason_code=%s)",
            reason_code,
        )

    def _on_message(
        self,
        _client: mqtt.Client,
        _userdata: object,
        message: mqtt.MQTTMessage,
    ) -> None:
        self.received_count += 1

        try:
            payload_dict = json.loads(message.payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            self.invalid_count += 1
            logger.warning(
                "Mensaje MQTT no decodificable como JSON en topic=%s: %s",
                message.topic,
                exc,
            )
            return

        try:
            payload = TelemetryPayload.model_validate(payload_dict)
        except ValidationError as exc:
            self.invalid_count += 1
            logger.warning(
                "Mensaje MQTT con schema inválido en topic=%s: %s",
                message.topic,
                exc.errors(),
            )
            return

        future = asyncio.run_coroutine_threadsafe(
            self._database.insert_telemetry(payload), self._loop
        )
        future.add_done_callback(self._on_insert_done)

    def _on_insert_done(self, future: concurrent.futures.Future) -> None:
        try:
            future.result()
        except (asyncpg.PostgresError, OSError, asyncio.CancelledError):
            self.persist_failures += 1
            logger.exception(
                "Fallo persistiendo telemetría AMI a PostgreSQL"
            )
