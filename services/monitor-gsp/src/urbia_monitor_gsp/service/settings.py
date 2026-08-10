"""Configuración del servicio del monitor, desde variables de entorno.

Mismos nombres que `services/backend` para lo compartido —`MQTT_HOST`,
`POSTGRES_*`— de modo que un único `.env` sirva a los dos y nadie tenga que
mantener dos juegos sincronizados. Lo propio del monitor lleva prefijo
`MONITOR_`.

**Ningún valor por defecto de acá es una estimación.** Los que salen de una
medición dicen cuál, y los que son una elección lo dicen también. Es la
regla de `ESTADO.md` §5.3 aplicada a la configuración: un número sin su
procedencia termina citado fuera de su contexto.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from pydantic_settings import BaseSettings, SettingsConfigDict

from ..graph.types import MonitorGspError

DEFAULT_CYCLE_SECONDS: Final = 3.0
"""Cada cuánto despierta el servicio. **Medido, no elegido a ojo.**

Sale de aplicar la regla C6 de `experiments/ciclo-deteccion/` al costo
medido del ciclo sobre las seis zonas de `manizales_150`: p99 de 1,39 ms
sobre neusi-stage. Los dos límites de la regla son `t ≤ b/2`, para que
ningún bin de 6 s se cierre sin que el servicio despierte dentro de él, y
`t ≥ 20·c`, para que el ciclo no pase del 5 % del intervalo. Con `c` tan
chico manda el primero y da `t = b/2 = 3 s`, donde el ciclo consume el
0,047 %.

**La cifra vale para neusi-stage y esta topología.** En el nodo de borde de
H1 —una RPi5 ARM— hay que rehacer la medición con el mismo `run.py` antes de
reusar este valor; leerlo allá sería el error de §5.3. Por eso el servicio
publica la duración del ciclo como métrica: este número es el punto de
partida, y la métrica dice si dejó de valer.
"""

DEFAULT_TOPOLOGY_CHECK_SECONDS: Final = 300.0
"""Cada cuánto se recontrasta la topología viva contra la calibrada.

Elección declarada, no medición. El padrón cambia con altas y bajas de
medidores, que son operaciones humanas y no ocurren en segundos. Cinco
minutos acota la ventana durante la cual el servicio podría estar
detectando sobre un grafo que ya no existe sin volver la verificación un
costo perceptible: son 150 filas leídas 12 veces por hora.
"""


class MonitorSettingsError(MonitorGspError, ValueError):
    """La configuración del servicio es incoherente."""


class MonitorSettings(BaseSettings):
    """Configuración del monitor como proceso.

    Todas las variables son case-insensitive. `extra="ignore"` permite
    convivir con el `.env` global del proyecto, que define muchas otras
    variables ajenas a este servicio.

    Attributes:
        mqtt_host: Broker MQTT. El de UrbIA vive en `192.168.40.12` en modo
            anónimo, **compartido con proyectos cliente** (`CLAUDE.md`
            §10.4).
        mqtt_port: Puerto del broker.
        mqtt_username: Usuario, o vacío para modo anónimo.
        mqtt_password: Contraseña.
        mqtt_topic_telemetry: Patrón al que se suscribe la ingesta. Se
            enruta por el `device_id` del payload y no por el topic, así
            que un cambio en la jerarquía del productor no rompe nada.
        mqtt_topic_prefix: Raíz bajo la que se publica lo que produce el
            monitor.
        mqtt_client_id: Identificador ante el broker. Distinto del backend,
            o el broker desconecta a uno de los dos.
        mqtt_keepalive: Keepalive de la conexión.
        magnitude: Campo del payload que se monitorea. **`voltaje_v` es la
            única magnitud con el detector evaluado**: corriente y potencia
            tienen σ/media del 35 % contra el 2 % del voltaje y están sin
            medir. Cambiarlo sin medir antes sería operar fuera de la
            configuración en la que se calibró.
        calibration_path: Archivo de calibración congelada que el servicio
            adopta. Sin él no arranca, y no se calibra en caliente: una
            anomalía persistente se volvería parte de la hipótesis nula.
        cycle_seconds: Intervalo entre ciclos. Ver `DEFAULT_CYCLE_SECONDS`.
        topology_check_seconds: Intervalo de reverificación de la
            topología. Ver `DEFAULT_TOPOLOGY_CHECK_SECONDS`.
        top_k: Candidatas del ranking que se publican por ventana. `None`
            publica el ranking completo, que es el defecto: guardar sólo la
            ganadora impide reconstruir después el punto de operación.
            Medido en `experiments/ciclo-deteccion/` §6: el ranking
            completo son 30,6 kB por ciclo, o 5,1 kB/s, contra los ~12 kB/s
            de la telemetría que el monitor consume. Existe para recortarlo
            si la topología crece.
        metrics_port: Puerto del exportador de Prometheus. El job
            `monitor-gsp` de `infra/observability/prometheus.yml` apunta
            acá; cambiarlo exige cambiar el job también, o Prometheus
            raspa un puerto muerto y las series se cortan sin que nada
            falle del lado del monitor.
        metrics_host: Interfaz en la que escucha el exportador.
        zonas: Zonas a monitorear, separadas por coma. Vacío las toma
            todas. Acotar acá es lo que permite a un nodo de borde correr
            sólo la suya.
        log_level: Nivel de log.
    """

    model_config = SettingsConfigDict(
        env_file=None,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    mqtt_host: str = "192.168.40.12"
    mqtt_port: int = 1883
    mqtt_username: str = ""
    mqtt_password: str = ""
    mqtt_topic_telemetry: str = "urbia/manizales/#"
    mqtt_topic_prefix: str = "urbia/manizales/monitor"
    mqtt_client_id: str = "urbia-monitor-gsp"
    mqtt_keepalive: int = 60

    magnitude: str = "voltaje_v"
    calibration_path: Path = Path("data/calibrations/manizales_scan_v1.json")

    cycle_seconds: float = DEFAULT_CYCLE_SECONDS
    topology_check_seconds: float = DEFAULT_TOPOLOGY_CHECK_SECONDS
    top_k: int | None = None

    metrics_port: int = 9101
    metrics_host: str = "0.0.0.0"

    zonas: str = ""
    log_level: str = "INFO"

    def zone_filter(self) -> tuple[str, ...] | None:
        """Zonas declaradas, o `None` si no se acotó.

        Returns:
            Nombres de zona, sin espacios ni vacíos.
        """
        nombres = tuple(z.strip() for z in self.zonas.split(",") if z.strip())
        return nombres or None

    def validate_coherence(self, bin_seconds: float) -> None:
        """Verifica lo que sólo se puede saber junto al ancho de bin.

        El intervalo no es libre: `ZoneWindow.emit` entrega una ventana por
        bin cerrado, así que un ciclo que despierte menos seguido que el
        bin **pierde bins**, y cada bin perdido invalida las 16 ventanas que
        lo contenían. La pérdida no es silenciosa —`skipped_bins` la
        cuenta— pero es evitable de entrada.

        Args:
            bin_seconds: Ancho de bin en uso.

        Raises:
            MonitorSettingsError: Si el intervalo, el `top_k` o el chequeo
                de topología caen fuera de rango.
        """
        if self.cycle_seconds <= 0.0:
            raise MonitorSettingsError(f"cycle_seconds debe ser > 0, recibido {self.cycle_seconds}")
        if self.cycle_seconds > bin_seconds / 2.0:
            raise MonitorSettingsError(
                f"cycle_seconds={self.cycle_seconds} s supera la mitad del bin "
                f"({bin_seconds} s): el servicio despertaría menos de dos veces por "
                f"bin y perdería bins de forma acumulativa. Ver la regla C6 de "
                f"experiments/ciclo-deteccion/"
            )
        if self.topology_check_seconds <= 0.0:
            raise MonitorSettingsError(
                f"topology_check_seconds debe ser > 0, recibido {self.topology_check_seconds}"
            )
        if self.top_k is not None and self.top_k < 0:
            raise MonitorSettingsError(f"top_k debe ser >= 0 o None, recibido {self.top_k}")


def get_monitor_settings() -> MonitorSettings:
    """Construye la configuración leyendo el entorno.

    Existe como función y no como singleton de módulo para que los tests
    puedan sustituirla sin tocar estado global.

    Returns:
        La configuración del servicio.
    """
    return MonitorSettings()
