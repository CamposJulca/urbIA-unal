import json
import logging
import time
import paho.mqtt.client as mqtt

logger = logging.getLogger(__name__)


class MQTTPublisher:
    def __init__(self, broker_host: str, broker_port: int = 1883,
                 client_id: str = "urbia-sim"):
        self.broker_host = broker_host
        self.broker_port = broker_port
        self._conectado  = False
        self._publicados = 0
        self._errores    = 0

        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=client_id,
            clean_session=False,
        )
        self.client.on_connect    = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_publish    = self._on_publish

    def conectar(self):
        self.client.connect_async(self.broker_host, self.broker_port, keepalive=60)
        self.client.loop_start()
        time.sleep(1)

    def publicar(self, topic: str, payload: dict) -> bool:
        if not self._conectado:
            self._errores += 1
            return False
        try:
            msg = json.dumps(payload, ensure_ascii=False)
            result = self.client.publish(topic, msg, qos=1)
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                return True
            self._errores += 1
            return False
        except Exception as e:
            self._errores += 1
            logger.error(f"Error publicando: {e}")
            return False

    def desconectar(self):
        self.client.loop_stop()
        self.client.disconnect()

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        self._conectado = not reason_code.is_failure
        if self._conectado:
            logger.info(f"Conectado a {self.broker_host}:{self.broker_port}")
        else:
            logger.error(f"Error de conexión: {reason_code}")

    def _on_disconnect(self, client, userdata, flags, reason_code, properties):
        self._conectado = False
        if reason_code.value != 0:
            logger.warning(f"Desconexión inesperada ({reason_code}), reconectando...")

    def _on_publish(self, client, userdata, mid, reason_code, properties):
        self._publicados += 1

    def estadisticas(self) -> dict:
        return {
            "conectado":  self._conectado,
            "publicados": self._publicados,
            "errores":    self._errores,
        }
