"""Pool asyncpg y queries de persistencia del backend UrbIA."""

from __future__ import annotations

import logging
from typing import Optional

import asyncpg

from .config import Settings
from .models import MeterInfo, TelemetryPayload, TelemetryRecord

logger = logging.getLogger(__name__)


# Las columnas viven en español (ver migrations/002_esquema_ami_v2.sql)
# pero la API REST mantiene los nombres en inglés que el frontend ya
# consume. El puente es este alias, no un renombre de columnas ni un
# adaptador en el modelo Pydantic.
_SELECT_TELEMETRY_COLUMNS = """
    id,
    device_id       AS meter_id,
    device_type,
    zona            AS zone,
    timestamp_utc   AS timestamp,
    voltaje_v       AS voltage_v,
    corriente_a     AS current_a,
    potencia_kw     AS power_kw,
    energia_kwh     AS energy_kwh,
    frecuencia_hz   AS frequency_hz,
    factor_potencia AS power_factor,
    estado          AS status,
    nodo_origen,
    lenguaje,
    seed,
    recibido_en     AS received_at
"""

_SELECT_METER_COLUMNS = """
    device_id            AS meter_id,
    device_type,
    zona                 AS zone,
    lat,
    lon,
    nodo_origen,
    instalado_en         AS installed_at,
    visto_por_ultima_vez AS last_seen,
    activo               AS is_active
"""


class Database:
    """Wrapper de `asyncpg.Pool` con las queries del backend.

    El pool se abre en `connect()` (startup de FastAPI) y se cierra en
    `disconnect()` (shutdown). `ping()` lo usa `GET /health`. La
    inserción de un mensaje MQTT y el upsert del medidor se hacen en
    una transacción única para evitar dejar `ami_meters` desincronizada
    si una de las dos escrituras falla.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._pool: Optional[asyncpg.Pool] = None

    @property
    def pool(self) -> asyncpg.Pool:
        if self._pool is None:
            raise RuntimeError("Pool de base de datos no inicializado")
        return self._pool

    @property
    def is_connected(self) -> bool:
        return self._pool is not None

    async def connect(self) -> None:
        if self._pool is not None:
            return
        self._pool = await asyncpg.create_pool(
            host=self._settings.postgres_host,
            port=self._settings.postgres_port,
            user=self._settings.postgres_user,
            password=self._settings.postgres_password,
            database=self._settings.postgres_db,
            min_size=self._settings.db_pool_min_size,
            max_size=self._settings.db_pool_max_size,
        )
        logger.info(
            "Pool PostgreSQL conectado a %s:%s/%s",
            self._settings.postgres_host,
            self._settings.postgres_port,
            self._settings.postgres_db,
        )

    async def disconnect(self) -> None:
        if self._pool is None:
            return
        await self._pool.close()
        self._pool = None
        logger.info("Pool PostgreSQL cerrado")

    async def ping(self) -> bool:
        """Devuelve True si la conexión a PostgreSQL responde."""

        if self._pool is None:
            return False
        try:
            async with self._pool.acquire() as conn:
                value = await conn.fetchval("SELECT 1")
                return value == 1
        except (asyncpg.PostgresError, OSError):
            logger.exception("Fallo ping a PostgreSQL")
            return False

    async def insert_telemetry(self, payload: TelemetryPayload) -> None:
        """Inserta un mensaje y upsert del medidor en una transacción."""

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    INSERT INTO ami_telemetry (
                        device_id, device_type, zona, timestamp_utc,
                        voltaje_v, corriente_a, potencia_kw, energia_kwh,
                        frecuencia_hz, factor_potencia, estado,
                        nodo_origen, lenguaje, seed
                    ) VALUES (
                        $1, $2, $3, $4, $5, $6, $7,
                        $8, $9, $10, $11, $12, $13, $14
                    )
                    """,
                    payload.device_id,
                    payload.device_type,
                    payload.zona,
                    payload.timestamp_utc,
                    payload.voltaje_v,
                    payload.corriente_a,
                    payload.potencia_kw,
                    payload.energia_kwh,
                    payload.frecuencia_hz,
                    payload.factor_potencia,
                    payload.estado,
                    payload.nodo_origen,
                    payload.lenguaje,
                    payload.seed,
                )
                # COALESCE en cada metadato: un mensaje que omita zona,
                # lat/lon o nodo_origen no debe borrar lo que ya se
                # conocía del medidor.
                await conn.execute(
                    """
                    INSERT INTO ami_meters (
                        device_id, device_type, zona, lat, lon,
                        nodo_origen, visto_por_ultima_vez, activo
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, TRUE)
                    ON CONFLICT (device_id) DO UPDATE
                    SET device_type = COALESCE(
                            EXCLUDED.device_type, ami_meters.device_type
                        ),
                        zona = COALESCE(EXCLUDED.zona, ami_meters.zona),
                        lat = COALESCE(EXCLUDED.lat, ami_meters.lat),
                        lon = COALESCE(EXCLUDED.lon, ami_meters.lon),
                        nodo_origen = COALESCE(
                            EXCLUDED.nodo_origen, ami_meters.nodo_origen
                        ),
                        visto_por_ultima_vez = EXCLUDED.visto_por_ultima_vez,
                        activo = TRUE
                    """,
                    payload.device_id,
                    payload.device_type,
                    payload.zona,
                    payload.lat,
                    payload.lon,
                    payload.nodo_origen,
                    payload.timestamp_utc,
                )

    async def list_meters(self) -> list[MeterInfo]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT {_SELECT_METER_COLUMNS}
                FROM ami_meters
                WHERE activo = TRUE
                ORDER BY device_id
                """
            )
            return [MeterInfo(**dict(r)) for r in rows]

    async def latest_for_meter(
        self, meter_id: str
    ) -> Optional[TelemetryRecord]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                SELECT {_SELECT_TELEMETRY_COLUMNS}
                FROM ami_telemetry
                WHERE device_id = $1
                ORDER BY recibido_en DESC
                LIMIT 1
                """,
                meter_id,
            )
            return TelemetryRecord(**dict(row)) if row is not None else None

    async def history_for_meter(
        self, meter_id: str, limit: int
    ) -> list[TelemetryRecord]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT {_SELECT_TELEMETRY_COLUMNS}
                FROM ami_telemetry
                WHERE device_id = $1
                ORDER BY recibido_en DESC
                LIMIT $2
                """,
                meter_id,
                limit,
            )
            return [TelemetryRecord(**dict(r)) for r in rows]

    async def recent_telemetry(self, limit: int) -> list[TelemetryRecord]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT {_SELECT_TELEMETRY_COLUMNS}
                FROM ami_telemetry
                ORDER BY recibido_en DESC
                LIMIT $1
                """,
                limit,
            )
            return [TelemetryRecord(**dict(r)) for r in rows]
