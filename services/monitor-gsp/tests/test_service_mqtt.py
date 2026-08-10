"""Tests del transporte MQTT, sin broker.

Los callbacks de paho se invocan a mano y el cliente se sustituye por un
doble. Lo que interesa verificar no es que paho funcione, sino las
decisiones del monitor sobre lo que llega y lo que sale:

* que un `timestamp_utc` **sin zona horaria se descarte con aviso**, en vez
  de leerse como hora local del proceso y correr el bin varias horas;
* que un payload inservible no tumbe la ingesta;
* que la validación sea la de los tres campos que el monitor usa y no la
  del esquema entero, para que un campo nuevo del productor no tire
  mensajes procesables;
* que ingesta y publicación usen **identificadores distintos**, porque el
  broker desconecta a uno de los dos si los comparten.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

import pytest

from conftest_service import BASE, calibracion_versionada
from urbia_monitor_gsp.graph.builder import build_ami_graph
from urbia_monitor_gsp.graph.types import AmiGraph, GraphConfig, MeterNode
from urbia_monitor_gsp.service.mqtt import MqttPublisher, TelemetrySource, _build_client
from urbia_monitor_gsp.service.publisher import PublishError
from urbia_monitor_gsp.service.runtime import MonitorRuntime, build_runtime
from urbia_monitor_gsp.service.settings import MonitorSettings


@pytest.fixture(scope="module")
def grafo(manizales: list[MeterNode]) -> AmiGraph:
    return build_ami_graph(manizales, GraphConfig())


@pytest.fixture
def runtime(grafo: AmiGraph) -> MonitorRuntime:
    return build_runtime(grafo, calibracion_versionada())


@pytest.fixture
def settings() -> MonitorSettings:
    return MonitorSettings()


@pytest.fixture
def source(settings: MonitorSettings, runtime: MonitorRuntime) -> TelemetrySource:
    return TelemetrySource(settings, runtime)


class MensajeFalso:
    """Lo mínimo de `mqtt.MQTTMessage` que usa `_on_message`."""

    def __init__(self, payload: bytes, topic: str = "urbia/manizales/centro/telemetria") -> None:
        self.payload = payload
        self.topic = topic


class InfoFalsa:
    """Lo que devuelve `client.publish`."""

    def __init__(self, rc: int) -> None:
        self.rc = rc


class ClienteFalso:
    """Doble del cliente paho: registra en vez de hablar con la red."""

    def __init__(self, rc: int = 0, conectado: bool = True) -> None:
        self._rc = rc
        self._conectado = conectado
        self.publicados: list[tuple[str, bytes, int]] = []
        self.suscripciones: list[tuple[str, int]] = []
        self.desconectado = False
        self.loop_detenido = False

    def is_connected(self) -> bool:
        return self._conectado

    def subscribe(self, topic: str, qos: int = 0) -> None:
        self.suscripciones.append((topic, qos))

    def publish(self, topic: str, payload: bytes, qos: int = 0) -> InfoFalsa:
        self.publicados.append((topic, payload, qos))
        return InfoFalsa(self._rc)

    def disconnect(self) -> None:
        self.desconectado = True

    def loop_stop(self) -> None:
        self.loop_detenido = True


def payload_de(device_id: str, instante: datetime, voltaje: float = 220.0) -> bytes:
    """Arma un payload del productor v2.

    Args:
        device_id: Medidor que publica.
        instante: Instante de la lectura.
        voltaje: Valor de la magnitud.

    Returns:
        El cuerpo en UTF-8.
    """
    cuerpo = {
        "device_id": device_id,
        "timestamp_utc": instante.isoformat(),
        "zona": "centro",
        "voltaje_v": voltaje,
        "corriente_a": 12.5,
        "potencia_w": 2750.0,
    }
    return json.dumps(cuerpo).encode("utf-8")


# ──────────────────────────────────────────────── lo que llega y sirve


def test_un_payload_del_productor_ocupa_una_celda(
    source: TelemetrySource, runtime: MonitorRuntime, grafo: AmiGraph
) -> None:
    device_id = grafo.zones["centro"].device_ids[0]
    source._on_message(None, None, MensajeFalso(payload_de(device_id, BASE)))  # type: ignore[arg-type]

    assert source.received_count == 1
    assert source.invalid_count == 0
    # La celda quedó ocupada en la zona que el padrón del grafo indica, que
    # es la autoridad: el campo `zona` del payload no se consulta.
    assert runtime._zones["centro"].window.accepted_count == 1
    assert runtime.ajenos == 0


def test_un_campo_nuevo_del_productor_no_tira_el_mensaje(
    source: TelemetrySource, grafo: AmiGraph
) -> None:
    """El backend valida el esquema entero antes de persistir.

    Repetirlo acá
    haría que un campo nuevo tirara mensajes que el monitor puede procesar.
    """
    cuerpo = json.loads(payload_de(grafo.zones["centro"].device_ids[0], BASE))
    cuerpo["campo_que_no_existia"] = 42
    source._on_message(None, None, MensajeFalso(json.dumps(cuerpo).encode("utf-8")))  # type: ignore[arg-type]

    assert source.invalid_count == 0


def test_una_lectura_de_un_medidor_ajeno_no_es_invalida(
    source: TelemetrySource, runtime: MonitorRuntime
) -> None:
    """Ajeno al padrón no es lo mismo que mal formado.

    El mensaje era legible; simplemente no es de este monitor. El topic es
    `#` y en el árbol conviven otros productores.
    """
    source._on_message(None, None, MensajeFalso(payload_de("urbia-xxx-mon-9999", BASE)))  # type: ignore[arg-type]

    assert source.invalid_count == 0
    assert runtime.ajenos == 1


# ─────────────────────────────────────────── lo que llega y no sirve


def test_un_timestamp_sin_zona_horaria_se_descarta_con_aviso(
    source: TelemetrySource, grafo: AmiGraph, caplog: pytest.LogCaptureFixture
) -> None:
    """Es el descarte que más importa.

    Un instante ingenuo se leería como
    hora local del proceso y correría el bin varias horas sin que nada
    avise; el contenedor puede correr en otra zona que el productor.
    """
    device_id = grafo.zones["centro"].device_ids[0]
    ingenuo = BASE.replace(tzinfo=None)

    with caplog.at_level(logging.WARNING):
        source._on_message(None, None, MensajeFalso(payload_de(device_id, ingenuo)))  # type: ignore[arg-type]

    assert source.invalid_count == 1
    assert "sin zona horaria" in caplog.text


def test_un_json_roto_se_descarta(source: TelemetrySource) -> None:
    source._on_message(None, None, MensajeFalso(b"{esto no es json"))  # type: ignore[arg-type]
    assert source.invalid_count == 1


def test_un_payload_sin_la_magnitud_se_descarta(source: TelemetrySource, grafo: AmiGraph) -> None:
    cuerpo = json.loads(payload_de(grafo.zones["centro"].device_ids[0], BASE))
    del cuerpo["voltaje_v"]
    source._on_message(None, None, MensajeFalso(json.dumps(cuerpo).encode("utf-8")))  # type: ignore[arg-type]
    assert source.invalid_count == 1


def test_un_payload_sin_device_id_se_descarta(source: TelemetrySource) -> None:
    cuerpo = {"timestamp_utc": BASE.isoformat(), "voltaje_v": 220.0}
    source._on_message(None, None, MensajeFalso(json.dumps(cuerpo).encode("utf-8")))  # type: ignore[arg-type]
    assert source.invalid_count == 1


def test_una_magnitud_no_numerica_se_descarta(source: TelemetrySource, grafo: AmiGraph) -> None:
    cuerpo = json.loads(payload_de(grafo.zones["centro"].device_ids[0], BASE))
    cuerpo["voltaje_v"] = "doscientos veinte"
    source._on_message(None, None, MensajeFalso(json.dumps(cuerpo).encode("utf-8")))  # type: ignore[arg-type]
    assert source.invalid_count == 1


def test_un_timestamp_no_parseable_se_descarta(source: TelemetrySource, grafo: AmiGraph) -> None:
    cuerpo = json.loads(payload_de(grafo.zones["centro"].device_ids[0], BASE))
    cuerpo["timestamp_utc"] = "ayer por la tarde"
    source._on_message(None, None, MensajeFalso(json.dumps(cuerpo).encode("utf-8")))  # type: ignore[arg-type]
    assert source.invalid_count == 1


def test_bytes_que_no_son_utf8_se_descartan(source: TelemetrySource) -> None:
    source._on_message(None, None, MensajeFalso(b"\xff\xfe\x00binario"))  # type: ignore[arg-type]
    assert source.invalid_count == 1


def test_un_mensaje_inservible_no_interrumpe_a_los_siguientes(
    source: TelemetrySource, grafo: AmiGraph
) -> None:
    device_id = grafo.zones["centro"].device_ids[0]
    source._on_message(None, None, MensajeFalso(b"basura"))  # type: ignore[arg-type]
    source._on_message(None, None, MensajeFalso(payload_de(device_id, BASE)))  # type: ignore[arg-type]

    assert source.received_count == 2
    assert source.invalid_count == 1


# ─────────────────────────────────────────────── el estado de conexión


def test_sin_arrancar_la_ingesta_no_esta_conectada(source: TelemetrySource) -> None:
    assert source.is_connected is False


def test_una_conexion_aceptada_suscribe_al_arbol(
    settings: MonitorSettings, runtime: MonitorRuntime
) -> None:
    estados: list[bool] = []
    fuente = TelemetrySource(settings, runtime, on_connection_change=estados.append)
    cliente = ClienteFalso()

    fuente._on_connect(cliente, None, None, 0)  # type: ignore[arg-type]

    assert cliente.suscripciones == [(settings.mqtt_topic_telemetry, 0)]
    assert estados == [True]


def test_una_conexion_rechazada_no_suscribe(
    settings: MonitorSettings, runtime: MonitorRuntime, caplog: pytest.LogCaptureFixture
) -> None:
    estados: list[bool] = []
    fuente = TelemetrySource(settings, runtime, on_connection_change=estados.append)
    cliente = ClienteFalso()

    with caplog.at_level(logging.ERROR):
        fuente._on_connect(cliente, None, None, 5)  # type: ignore[arg-type]

    assert cliente.suscripciones == []
    assert estados == [False]
    assert "rechazó" in caplog.text


def test_la_desconexion_se_refleja(settings: MonitorSettings, runtime: MonitorRuntime) -> None:
    estados: list[bool] = []
    fuente = TelemetrySource(settings, runtime, on_connection_change=estados.append)
    fuente._on_disconnect(None, None, None, 0)  # type: ignore[arg-type]
    assert estados == [False]


def test_sin_callback_los_cambios_de_conexion_no_rompen(source: TelemetrySource) -> None:
    source._on_connect(ClienteFalso(), None, None, 0)  # type: ignore[arg-type]
    source._on_disconnect(None, None, None, 0)  # type: ignore[arg-type]


def test_detener_una_ingesta_que_nunca_arrancó_no_hace_nada(source: TelemetrySource) -> None:
    source.stop()
    assert source.is_connected is False


def test_detener_la_ingesta_desconecta_y_para_el_hilo(source: TelemetrySource) -> None:
    cliente = ClienteFalso()
    source._client = cliente  # type: ignore[assignment]
    source.stop()

    assert cliente.desconectado
    assert cliente.loop_detenido
    assert source.is_connected is False


# ─────────────────────────────────────────────────────── publicación


def test_publicar_sin_arrancar_es_error(settings: MonitorSettings) -> None:
    with pytest.raises(PublishError, match="no está arrancada"):
        MqttPublisher(settings).publish("urbia/x", {"a": 1})


def test_un_cuerpo_publicado_viaja_serializado(settings: MonitorSettings) -> None:
    publicador = MqttPublisher(settings)
    cliente = ClienteFalso()
    publicador._client = cliente  # type: ignore[assignment]

    publicador.publish("urbia/manizales/monitor/ventana/centro", {"zona": "centro"})

    (topic, crudo, qos) = cliente.publicados[0]
    assert topic == "urbia/manizales/monitor/ventana/centro"
    assert json.loads(crudo.decode("utf-8")) == {"zona": "centro"}
    assert qos == 0


def test_un_rechazo_del_broker_es_error(settings: MonitorSettings) -> None:
    publicador = MqttPublisher(settings)
    publicador._client = ClienteFalso(rc=4)  # type: ignore[assignment]

    with pytest.raises(PublishError, match="rc=4"):
        publicador.publish("urbia/x", {"a": 1})


def test_el_qos_configurado_se_respeta(settings: MonitorSettings) -> None:
    publicador = MqttPublisher(settings, qos=1)
    cliente = ClienteFalso()
    publicador._client = cliente  # type: ignore[assignment]

    publicador.publish("urbia/x", {"a": 1})
    assert cliente.publicados[0][2] == 1


def test_detener_una_publicacion_que_nunca_arrancó_no_hace_nada(
    settings: MonitorSettings,
) -> None:
    MqttPublisher(settings).stop()


def test_detener_la_publicacion_desconecta(settings: MonitorSettings) -> None:
    publicador = MqttPublisher(settings)
    cliente = ClienteFalso()
    publicador._client = cliente  # type: ignore[assignment]
    publicador.stop()

    assert cliente.desconectado
    assert publicador.is_connected is False


# ──────────────────────────────────────────────── el cliente de paho


def test_ingesta_y_publicacion_usan_identificadores_distintos(
    settings: MonitorSettings,
) -> None:
    """Ingesta y publicación no pueden compartir identificador.

    Si lo compartieran, el broker desconectaría a uno de los dos, y un
    monitor que se autodesconecta cada vez que reconecta es un fallo difícil
    de leer.
    """
    entrada = _build_client(settings, f"{settings.mqtt_client_id}-in")
    salida = _build_client(settings, f"{settings.mqtt_client_id}-out")
    assert entrada._client_id != salida._client_id


def test_el_modo_anonimo_no_pone_credenciales(settings: MonitorSettings) -> None:
    """El broker de `192.168.40.12` corre en modo anónimo (CLAUDE.md §11.4)."""
    cliente = _build_client(settings, "urbia-test")
    assert cliente._username is None


def test_con_usuario_configurado_se_autentica() -> None:
    settings = MonitorSettings(mqtt_username="urbia", mqtt_password="secreto")
    cliente = _build_client(settings, "urbia-test")
    assert cliente._username == b"urbia"
    assert cliente._password == b"secreto"


def test_el_instante_parseado_conserva_la_zona_horaria(
    source: TelemetrySource, grafo: AmiGraph
) -> None:
    device_id = grafo.zones["centro"].device_ids[0]
    lectura = source._parse(payload_de(device_id, BASE), "urbia/manizales/centro")

    assert lectura is not None
    _, instante, valor = lectura
    assert instante.tzinfo is not None
    assert instante == BASE
    assert valor == 220.0


def test_se_lee_la_magnitud_configurada_y_no_otra(runtime: MonitorRuntime) -> None:
    """Si alguien cambiara `MAGNITUDE`, la ingesta tiene que seguirlo."""
    settings = MonitorSettings(magnitude="corriente_a")
    fuente = TelemetrySource(settings, runtime)
    lectura = fuente._parse(payload_de("urbia-cen-mon-0001", BASE), "t")

    assert lectura is not None
    assert lectura[2] == 12.5
