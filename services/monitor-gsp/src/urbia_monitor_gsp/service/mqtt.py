"""Transporte MQTT: de dónde llegan las lecturas y adónde van los resultados.

Todo lo que sabe de `paho` vive acá. El ciclo (`runtime`) y la forma del
payload (`publisher`) no lo importan, así que se pueden probar sin broker.

## Por qué el monitor consume del broker y no de PostgreSQL

Podría leer `ami_telemetry`, que es donde el backend ya persiste todo. No lo
hace por dos razones, y la segunda es la que manda:

1. Un `SELECT` cada 3 s sobre una tabla que crece a 30 filas por segundo
   agrega carga a la base por dato que ya pasó por la red.
2. **El monitor va a mudarse al nodo de borde.** Un nodo de borde tiene
   broker cerca y base lejos —o no tiene base—. Atarse a PostgreSQL para la
   telemetría haría que la primera línea de contribución no se pudiera
   medir sin arrastrar la base al borde.

De PostgreSQL sí se lee el **padrón** (`ami_meters`), que son 150 filas al
arrancar y una reverificación cada cinco minutos.

## El payload que se consume

El del productor v2, `data/schemas/payload_schema_v1.json`. Se validan sólo
los tres campos que el monitor necesita —`device_id`, `timestamp_utc` y la
magnitud— y no el esquema entero: el backend ya lo valida completo antes de
persistir, y duplicar esa validación acá haría que un campo nuevo del
productor tirara mensajes que el monitor puede procesar igual.

`timestamp_utc` se exige **con zona horaria**. Un instante ingenuo se leería
como hora local del proceso y correría el bin varias horas sin que nada
avise; el contenedor puede correr en otra zona que el productor.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:  # pragma: no cover
    # Sólo para anotar. Importar paho en el nivel de módulo obligaría al
    # extra `[service]` a quien apenas quiere leer una calibración, y con
    # `from __future__ import annotations` las anotaciones no se evalúan.
    import paho.mqtt.client as mqtt

from ..graph.types import MonitorGspError
from .publisher import Publisher, PublishError, encode
from .runtime import MonitorRuntime
from .settings import MonitorSettings

logger: Final = logging.getLogger(__name__)


class BrokerError(MonitorGspError, RuntimeError):
    """No se pudo hablar con el broker."""


def _build_client(settings: MonitorSettings, client_id: str) -> mqtt.Client:
    """Construye el cliente paho con la configuración del servicio.

    Args:
        settings: Configuración del servicio.
        client_id: Identificador ante el broker.

    Returns:
        El cliente, sin conectar.

    Raises:
        ImportError: Si `paho-mqtt` no está instalado. Es el extra
            `[service]`; el núcleo no lo necesita.
    """
    import paho.mqtt.client as mqtt
    from paho.mqtt.enums import CallbackAPIVersion

    cliente = mqtt.Client(
        callback_api_version=CallbackAPIVersion.VERSION2,
        client_id=client_id,
        protocol=mqtt.MQTTv311,
    )
    if settings.mqtt_username:
        cliente.username_pw_set(settings.mqtt_username, settings.mqtt_password)
    return cliente


class TelemetrySource:
    """Suscribe al árbol de telemetría y alimenta el ciclo.

    El callback de paho corre en su propio hilo de red, así que
    `MonitorRuntime.observe` tiene que ser seguro desde otro hilo. Lo es:
    toma el candado de la zona.

    Args:
        settings: Configuración del servicio.
        runtime: Monitor al que se le entregan las lecturas.
        on_connection_change: Se llama con el estado de la conexión cada vez
            que cambia, para reflejarlo en las métricas.
    """

    def __init__(
        self,
        settings: MonitorSettings,
        runtime: MonitorRuntime,
        on_connection_change: Callable[[bool], None] | None = None,
    ) -> None:
        """Prepara el consumidor, sin conectar todavía."""
        self._settings = settings
        self._runtime = runtime
        self._on_connection_change = on_connection_change
        self._client: mqtt.Client | None = None

        self.received_count = 0
        self.invalid_count = 0

    @property
    def is_connected(self) -> bool:
        """Si la conexión con el broker está viva."""
        return self._client is not None and bool(self._client.is_connected())

    def start(self) -> None:
        """Conecta y arranca el hilo de red. No bloquea."""
        if self._client is not None:
            return
        cliente = _build_client(self._settings, f"{self._settings.mqtt_client_id}-in")
        cliente.on_connect = self._on_connect
        cliente.on_disconnect = self._on_disconnect
        cliente.on_message = self._on_message
        cliente.connect_async(
            self._settings.mqtt_host,
            self._settings.mqtt_port,
            keepalive=self._settings.mqtt_keepalive,
        )
        cliente.loop_start()
        self._client = cliente
        logger.info(
            "ingesta arrancada contra %s:%d, topic %s",
            self._settings.mqtt_host,
            self._settings.mqtt_port,
            self._settings.mqtt_topic_telemetry,
        )

    def stop(self) -> None:
        """Desconecta y detiene el hilo de red."""
        if self._client is None:
            return
        cliente, self._client = self._client, None
        try:
            cliente.disconnect()
        except OSError:
            logger.exception("error desconectando la ingesta")
        cliente.loop_stop()

    def _notificar(self, conectado: bool) -> None:
        """Avisa del cambio de estado de la conexión.

        Args:
            conectado: Si la conexión está viva.
        """
        if self._on_connection_change is not None:
            self._on_connection_change(conectado)

    def _on_connect(
        self,
        client: mqtt.Client,
        _userdata: object,
        _flags: object,
        reason_code: object,
        _properties: object = None,
    ) -> None:
        """Suscribe al árbol de telemetría cuando la conexión prospera."""
        if getattr(reason_code, "value", reason_code) == 0:
            client.subscribe(self._settings.mqtt_topic_telemetry, qos=0)
            self._notificar(True)
            logger.info("ingesta suscrita a %s", self._settings.mqtt_topic_telemetry)
        else:
            self._notificar(False)
            logger.error("el broker rechazó la ingesta (reason_code=%s)", reason_code)

    def _on_disconnect(
        self,
        _client: mqtt.Client,
        _userdata: object,
        _flags: object,
        reason_code: object,
        _properties: object = None,
    ) -> None:
        """Refleja la desconexión. paho reconecta solo mientras el loop viva."""
        self._notificar(False)
        codigo = getattr(reason_code, "value", reason_code)
        logger.log(
            logging.INFO if codigo == 0 else logging.WARNING,
            "ingesta desconectada del broker (reason_code=%s)",
            reason_code,
        )

    def _on_message(
        self,
        _client: mqtt.Client,
        _userdata: object,
        message: mqtt.MQTTMessage,
    ) -> None:
        """Extrae la lectura del payload y se la entrega al ciclo."""
        self.received_count += 1
        lectura = self._parse(message.payload, message.topic)
        if lectura is None:
            return
        device_id, instante, valor = lectura
        self._runtime.observe(device_id, instante, valor)

    def _parse(self, crudo: bytes, topic: str) -> tuple[str, datetime, float] | None:
        """Saca `(device_id, timestamp, valor)` del payload, o `None`.

        Se validan sólo los tres campos que el monitor usa. El backend ya
        valida el esquema entero antes de persistir; repetirlo acá haría
        que un campo nuevo del productor tirara mensajes procesables.

        Args:
            crudo: Cuerpo del mensaje.
            topic: Topic del que llegó, para el log.

        Returns:
            La lectura, o `None` si el mensaje no sirve.
        """
        try:
            datos: dict[str, Any] = json.loads(crudo)
            device_id = str(datos["device_id"])
            instante = datetime.fromisoformat(str(datos["timestamp_utc"]))
            valor = float(datos[self._settings.magnitude])
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            self.invalid_count += 1
            logger.debug("mensaje inservible en %s: %s", topic, exc)
            return None

        if instante.tzinfo is None:
            self.invalid_count += 1
            logger.warning(
                "'%s' publicó timestamp_utc sin zona horaria (%s): se leería como hora "
                "local del proceso y correría el bin sin que nada avise",
                device_id,
                datos["timestamp_utc"],
            )
            return None
        return device_id, instante, valor


class MqttPublisher(Publisher):
    """Publica los resultados del monitor en el broker.

    Cliente aparte del de la ingesta, con otro `client_id`: el broker
    desconecta a uno de los dos si comparten identificador, y un monitor que
    se autodesconecta cada vez que reconecta sería un fallo difícil de leer.

    Args:
        settings: Configuración del servicio.
        qos: Calidad de servicio de la publicación. El defecto de 0 es el
            del productor de telemetría: el resultado siguiente llega en 6 s
            y reintentar uno viejo tiene menos valor que publicar el nuevo.
    """

    def __init__(self, settings: MonitorSettings, qos: int = 0) -> None:
        """Prepara el publicador, sin conectar todavía."""
        self._settings = settings
        self._qos = qos
        self._client: mqtt.Client | None = None

    @property
    def is_connected(self) -> bool:
        """Si la conexión con el broker está viva."""
        return self._client is not None and bool(self._client.is_connected())

    def start(self) -> None:
        """Conecta y arranca el hilo de red. No bloquea."""
        if self._client is not None:
            return
        cliente = _build_client(self._settings, f"{self._settings.mqtt_client_id}-out")
        cliente.connect_async(
            self._settings.mqtt_host,
            self._settings.mqtt_port,
            keepalive=self._settings.mqtt_keepalive,
        )
        cliente.loop_start()
        self._client = cliente
        logger.info(
            "publicación arrancada contra %s:%d, prefijo %s",
            self._settings.mqtt_host,
            self._settings.mqtt_port,
            self._settings.mqtt_topic_prefix,
        )

    def stop(self) -> None:
        """Desconecta y detiene el hilo de red."""
        if self._client is None:
            return
        cliente, self._client = self._client, None
        try:
            cliente.disconnect()
        except OSError:
            logger.exception("error desconectando la publicación")
        cliente.loop_stop()

    def publish(self, topic: str, payload: dict[str, Any]) -> None:
        """Manda un mensaje al broker.

        Args:
            topic: Topic completo.
            payload: Cuerpo serializable.

        Raises:
            PublishError: Si el cliente no está arrancado o el broker no
                aceptó el mensaje.
        """
        if self._client is None:
            raise PublishError("la publicación no está arrancada")
        info = self._client.publish(topic, encode(payload), qos=self._qos)
        if info.rc != 0:
            raise PublishError(f"el broker rechazó el mensaje en {topic} (rc={info.rc})")
