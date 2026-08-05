"""Configuración del backend cargada desde variables de entorno."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuración del servicio.

    Todas las variables son case-insensitive. `extra="ignore"` permite
    convivir con el `.env` global del proyecto, que define muchas otras
    variables ajenas al backend (Mongo, MinIO, Redis, etc.).
    """

    model_config = SettingsConfigDict(
        env_file=None,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # PostgreSQL — el host por defecto es el DNS interno de docker
    # ("postgres"). En tests o ejecuciones locales se sobreescribe vía
    # variable de entorno.
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_db: str = "urbia"
    postgres_user: str = "urbia"
    postgres_password: str = ""

    # MQTT — el broker vive en 192.168.40.12 en modo anónimo (el
    # segmento 192.168.0.x ya no lo sirve). Si username y password
    # vienen vacíos, el consumer no envía credenciales.
    mqtt_host: str = "192.168.40.12"
    mqtt_port: int = 1883
    mqtt_username: str = ""
    mqtt_password: str = ""
    # El productor v2 publica bajo el árbol `urbia/manizales/`. Se
    # suscribe con `#` (multinivel) porque la profundidad del topic
    # depende del productor y el consumidor no la usa: enruta por el
    # `device_id` del payload, no por el topic.
    mqtt_topic_telemetry: str = "urbia/manizales/#"
    mqtt_client_id: str = "urbia-backend"
    mqtt_keepalive: int = 60

    # HTTP
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000

    # Pool asyncpg
    db_pool_min_size: int = 1
    db_pool_max_size: int = 10

    # Logging
    log_level: str = "INFO"


def get_settings() -> Settings:
    """Factory de Settings. Útil para sobreescribir en tests."""

    return Settings()
