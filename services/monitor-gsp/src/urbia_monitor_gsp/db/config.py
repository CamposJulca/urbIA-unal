"""Configuración de conexión a PostgreSQL, desde variables de entorno.

Mismos nombres de variable que `services/backend` (`POSTGRES_HOST`,
`POSTGRES_PORT`, …), para que un único `.env` sirva a los dos servicios y
nadie tenga que mantener dos juegos de credenciales sincronizados.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """Parámetros de conexión a la base `urbia`.

    Todas las variables son case-insensitive. `extra="ignore"` permite
    convivir con el `.env` global del proyecto, que define muchas otras
    variables ajenas a este módulo (MQTT, Mongo, Redis, MinIO).

    Attributes:
        postgres_host: Host de PostgreSQL. El valor por defecto es el DNS
            interno de docker; fuera del compose se sobreescribe por
            entorno.
        postgres_port: Puerto de PostgreSQL.
        postgres_db: Nombre de la base.
        postgres_user: Usuario.
        postgres_password: Contraseña. Nunca se hardcodea ni se registra
            en el log; ver `conninfo`.
        connect_timeout_s: Segundos antes de abandonar la conexión. Un
            monitor de borde no puede quedarse colgado esperando a una
            base que no está.
    """

    model_config = SettingsConfigDict(
        env_file=None,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_db: str = "urbia"
    postgres_user: str = "urbia"
    postgres_password: str = ""
    connect_timeout_s: int = 10

    @property
    def conninfo(self) -> str:
        """Cadena de conexión para `psycopg.connect`.

        Returns:
            La cadena `key=value` que espera libpq, con la contraseña
            incluida. **No la registres en el log**: usá `safe_summary`.
        """
        return (
            f"host={self.postgres_host} port={self.postgres_port} "
            f"dbname={self.postgres_db} user={self.postgres_user} "
            f"password={self.postgres_password} "
            f"connect_timeout={self.connect_timeout_s}"
        )

    @property
    def safe_summary(self) -> str:
        """Descripción de la conexión apta para el log, sin contraseña.

        Returns:
            Cadena `usuario@host:puerto/base`.
        """
        return f"{self.postgres_user}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"


def get_settings() -> DatabaseSettings:
    """Construye la configuración leyendo el entorno.

    Existe como función y no como singleton de módulo para que los tests
    puedan sustituirla sin tocar estado global.

    Returns:
        La configuración de conexión.
    """
    return DatabaseSettings()
