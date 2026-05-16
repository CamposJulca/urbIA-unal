"""Entry point del backend UrbIA: FastAPI con lifespan + uvicorn."""

from __future__ import annotations

import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

from fastapi import FastAPI

from .api.telemetry import router as telemetry_router
from .config import Settings, get_settings
from .db import Database
from .mqtt_consumer import MqttConsumer

logger = logging.getLogger("urbia_backend")


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
        stream=sys.stdout,
        force=True,
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup: levanta pool asyncpg y cliente MQTT. Shutdown: los cierra."""

    settings: Settings = app.state.settings

    database = Database(settings)
    await database.connect()
    app.state.database = database

    loop = asyncio.get_running_loop()
    mqtt_consumer = MqttConsumer(settings, database, loop)
    mqtt_consumer.start()
    app.state.mqtt_consumer = mqtt_consumer

    logger.info("Backend UrbIA listo (HTTP %s:%s)",
                settings.backend_host, settings.backend_port)

    try:
        yield
    finally:
        mqtt_consumer.stop()
        await database.disconnect()
        logger.info("Backend UrbIA detenido")


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    """Factory de la app FastAPI. Permite inyectar settings en tests."""

    if settings is None:
        settings = get_settings()
    _configure_logging(settings.log_level)

    app = FastAPI(
        title="urbia-backend",
        description=(
            "Backend FastAPI de UrbIA-UNAL: consume telemetría AMI por MQTT, "
            "persiste a PostgreSQL y expone endpoints REST."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.include_router(telemetry_router)
    return app


app = create_app()


def run() -> None:
    """Entry point del script `urbia-backend` (consola)."""

    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "urbia_backend.main:app",
        host=settings.backend_host,
        port=settings.backend_port,
        log_level=settings.log_level.lower(),
    )
