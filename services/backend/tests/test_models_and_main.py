"""Tests de modelos Pydantic y del factory `create_app`."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from urbia_backend.config import Settings, get_settings
from urbia_backend.main import create_app
from urbia_backend.models import TelemetryPayload


def test_telemetry_payload_accepts_iso8601_with_z_suffix() -> None:
    payload = TelemetryPayload(
        device_id="urbia-cen-mon-0001",
        device_type="mon",
        zona="centro",
        timestamp_utc="2026-05-04T18:00:00.000Z",
        voltaje_v=120.0,
        corriente_a=8.0,
        potencia_kw=0.95,
        energia_kwh=42.0,
        frecuencia_hz=60.0,
        factor_potencia=0.95,
        estado="activo",
    )
    assert payload.timestamp_utc.tzinfo is not None


@pytest.mark.parametrize(
    "device_id",
    [
        "NO_FORMAT",
        "AMI-MNZ-00001",        # formato v1, ya no aceptado
        "urbia-xxx-mon-0001",   # zona fuera del enum
        "urbia-cen-bic-0001",   # tipo fuera del enum
        "urbia-cen-mon-001",    # 3 dígitos en vez de 4
        "urbia-cen-mon-00001",  # 5 dígitos en vez de 4
    ],
)
def test_telemetry_payload_rejects_invalid_device_id(device_id: str) -> None:
    with pytest.raises(ValidationError):
        TelemetryPayload(
            device_id=device_id,
            timestamp_utc=datetime.now(timezone.utc),
            voltaje_v=120.0,
            corriente_a=8.0,
            potencia_kw=0.95,
            frecuencia_hz=60.0,
            factor_potencia=0.95,
        )


def test_telemetry_payload_accepts_all_zone_and_type_codes() -> None:
    for zona in ("cen", "chi", "ena", "pal", "pgr", "uni"):
        for tipo in ("mon", "tri"):
            payload = TelemetryPayload(
                device_id=f"urbia-{zona}-{tipo}-0001",
                timestamp_utc=datetime.now(timezone.utc),
                voltaje_v=120.0,
                corriente_a=8.0,
                potencia_kw=0.95,
                frecuencia_hz=60.0,
                factor_potencia=0.95,
            )
            assert payload.device_id.endswith("-0001")


def test_telemetry_payload_ignores_extra_fields() -> None:
    payload = TelemetryPayload(
        device_id="urbia-cen-mon-0001",
        zona="centro",
        timestamp_utc=datetime.now(timezone.utc),
        voltaje_v=120.0,
        corriente_a=8.0,
        potencia_kw=0.95,
        energia_kwh=42.0,
        frecuencia_hz=60.0,
        factor_potencia=0.95,
        estado="activo",
        unexpected_field="should_be_ignored",
    )
    assert payload.device_id == "urbia-cen-mon-0001"


def test_telemetry_payload_optional_fields_default_to_none() -> None:
    payload = TelemetryPayload(
        device_id="urbia-cen-mon-0001",
        timestamp_utc=datetime.now(timezone.utc),
        voltaje_v=120.0,
        corriente_a=8.0,
        potencia_kw=0.95,
        frecuencia_hz=60.0,
        factor_potencia=0.95,
    )
    assert payload.zona is None
    assert payload.estado is None
    assert payload.device_type is None
    assert payload.nodo_origen is None
    assert payload.lenguaje is None
    assert payload.seed is None
    # energia_kwh es nullable en v2: el productor no siempre la reporta.
    assert payload.energia_kwh is None


def test_create_app_returns_fastapi_with_routes_and_settings() -> None:
    app = create_app(settings=Settings())
    assert app.state.settings is not None
    paths = {route.path for route in app.routes}
    expected = {
        "/health",
        "/meters",
        "/meters/{meter_id}/telemetry/latest",
        "/meters/{meter_id}/telemetry",
        "/telemetry/recent",
    }
    assert expected <= paths


def test_get_settings_returns_instance() -> None:
    settings = get_settings()
    assert isinstance(settings, Settings)
