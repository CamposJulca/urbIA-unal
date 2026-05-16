"""Pool asyncpg y queries de persistencia del backend UrbIA."""

from __future__ import annotations

import logging
from typing import Optional

import asyncpg

from .config import Settings
from .models import MeterInfo, TelemetryPayload, TelemetryRecord

logger = logging.getLogger(__name__)


_SELECT_TELEMETRY_COLUMNS = """
    id, meter_id, timestamp, voltage_v, current_a,
    power_kw, energy_kwh, frequency_hz, power_factor,
    zone, status, received_at
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
                        meter_id, timestamp, voltage_v, current_a,
                        power_kw, energy_kwh, frequency_hz, power_factor,
                        zone, status
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                    """,
                    payload.meter_id,
                    payload.timestamp,
                    payload.voltage_v,
                    payload.current_a,
                    payload.power_kw,
                    payload.energy_kwh,
                    payload.frequency_hz,
                    payload.power_factor,
                    payload.zone,
                    payload.status,
                )
                await conn.execute(
                    """
                    INSERT INTO ami_meters (meter_id, zone, last_seen, is_active)
                    VALUES ($1, $2, $3, TRUE)
                    ON CONFLICT (meter_id) DO UPDATE
                    SET zone = COALESCE(EXCLUDED.zone, ami_meters.zone),
                        last_seen = EXCLUDED.last_seen,
                        is_active = TRUE
                    """,
                    payload.meter_id,
                    payload.zone,
                    payload.timestamp,
                )

    async def list_meters(self) -> list[MeterInfo]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT meter_id, zone, installed_at, last_seen, is_active
                FROM ami_meters
                WHERE is_active = TRUE
                ORDER BY meter_id
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
                WHERE meter_id = $1
                ORDER BY received_at DESC
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
                WHERE meter_id = $1
                ORDER BY received_at DESC
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
                ORDER BY received_at DESC
                LIMIT $1
                """,
                limit,
            )
            return [TelemetryRecord(**dict(r)) for r in rows]
