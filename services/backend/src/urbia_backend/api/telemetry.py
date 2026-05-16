"""Endpoints REST del backend UrbIA — Entregable E4.

Cinco endpoints GET sobre la base `urbia`, todos documentados en
`/docs` (OpenAPI lo genera automáticamente a partir de las anotaciones
de tipos y los `response_model`).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status

from ..db import Database
from ..models import HealthResponse, MeterInfo, TelemetryRecord
from ..mqtt_consumer import MqttConsumer


_METER_ID_PATTERN = r"^AMI-MNZ-\d{5}$"
_DEFAULT_LIMIT = 100
_MAX_LIMIT = 1000


def get_database(request: Request) -> Database:
    """Dependency: devuelve el `Database` montado en `app.state`."""

    return request.app.state.database


def get_mqtt_consumer(request: Request) -> MqttConsumer:
    """Dependency: devuelve el `MqttConsumer` montado en `app.state`."""

    return request.app.state.mqtt_consumer


router = APIRouter()


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Salud del backend",
    tags=["meta"],
)
async def health(
    database: Database = Depends(get_database),
    mqtt_consumer: MqttConsumer = Depends(get_mqtt_consumer),
) -> HealthResponse:
    """Pinguea Postgres y consulta el estado del cliente MQTT."""

    db_ok = await database.ping()
    mqtt_ok = mqtt_consumer.is_connected
    return HealthResponse(
        status="ok" if (db_ok and mqtt_ok) else "degraded",
        db=db_ok,
        mqtt=mqtt_ok,
    )


@router.get(
    "/meters",
    response_model=list[MeterInfo],
    summary="Lista de medidores activos",
    tags=["meters"],
)
async def list_meters(
    database: Database = Depends(get_database),
) -> list[MeterInfo]:
    """Devuelve los medidores activos con su `last_seen`."""

    return await database.list_meters()


@router.get(
    "/meters/{meter_id}/telemetry/latest",
    response_model=TelemetryRecord,
    summary="Último mensaje de un medidor",
    tags=["telemetry"],
)
async def meter_latest_telemetry(
    meter_id: str = Path(pattern=_METER_ID_PATTERN, max_length=20),
    database: Database = Depends(get_database),
) -> TelemetryRecord:
    record = await database.latest_for_meter(meter_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No hay telemetría registrada para {meter_id}",
        )
    return record


@router.get(
    "/meters/{meter_id}/telemetry",
    response_model=list[TelemetryRecord],
    summary="Histórico de telemetría de un medidor",
    tags=["telemetry"],
)
async def meter_telemetry_history(
    meter_id: str = Path(pattern=_METER_ID_PATTERN, max_length=20),
    limit: int = Query(default=_DEFAULT_LIMIT, ge=1, le=_MAX_LIMIT),
    database: Database = Depends(get_database),
) -> list[TelemetryRecord]:
    return await database.history_for_meter(meter_id, limit)


@router.get(
    "/telemetry/recent",
    response_model=list[TelemetryRecord],
    summary="Últimos N mensajes globales",
    tags=["telemetry"],
)
async def recent_telemetry(
    limit: int = Query(default=_DEFAULT_LIMIT, ge=1, le=_MAX_LIMIT),
    database: Database = Depends(get_database),
) -> list[TelemetryRecord]:
    return await database.recent_telemetry(limit)
