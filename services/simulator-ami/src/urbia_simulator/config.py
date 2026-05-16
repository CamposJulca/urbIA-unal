"""Configuración del simulador desde variables de entorno.

Todas las variables tienen default razonable para correr en el cluster
Neusi sin necesidad de un .env. En Docker se inyectan desde el bloque
`environment:` del docker-compose.yml.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuración global del simulador AMI."""

    model_config = SettingsConfigDict(
        env_file=None,
        env_prefix="",
        case_sensitive=True,
        extra="ignore",
    )

    mqtt_host: str = Field(default="192.168.0.101", alias="MQTT_HOST")
    mqtt_port: int = Field(default=1883, alias="MQTT_PORT")
    # Broker .101 corre con allow_anonymous=true → username/password vacíos.
    mqtt_username: str = Field(default="", alias="MQTT_USERNAME")
    mqtt_password: str = Field(default="", alias="MQTT_PASSWORD")

    simulator_num_meters: int = Field(
        default=10, ge=1, le=99999, alias="SIMULATOR_NUM_METERS"
    )
    simulator_publish_rate_hz: float = Field(
        default=1.0, gt=0.0, le=100.0, alias="SIMULATOR_PUBLISH_RATE_HZ"
    )

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    @property
    def publish_interval_s(self) -> float:
        return 1.0 / self.simulator_publish_rate_hz

    @property
    def mqtt_auth_enabled(self) -> bool:
        return bool(self.mqtt_username)


def load_settings() -> Settings:
    return Settings()
