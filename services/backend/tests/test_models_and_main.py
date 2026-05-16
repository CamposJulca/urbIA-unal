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
        meter_id="AMI-MNZ-00001",
        timestamp="2026-05-04T18:00:00.000Z",
        voltage_v=120.0,
        current_a=8.0,
        power_kw=0.95,
        energy_kwh=42.0,
        frequency_hz=60.0,
        power_factor=0.95,
        zone="MNZ-CENTRO",
        status="NORMAL",
    )
    assert payload.timestamp.tzinfo is not None


def test_telemetry_payload_rejects_invalid_meter_id() -> None:
    with pytest.raises(ValidationError):
        TelemetryPayload(
            meter_id="NO_FORMAT",
            timestamp=datetime.now(timezone.utc),
            voltage_v=120.0,
            current_a=8.0,
            power_kw=0.95,
            energy_kwh=42.0,
            frequency_hz=60.0,
            power_factor=0.95,
        )


def test_telemetry_payload_ignores_extra_fields() -> None:
    payload = TelemetryPayload(
        meter_id="AMI-MNZ-00001",
        timestamp=datetime.now(timezone.utc),
        voltage_v=120.0,
        current_a=8.0,
        power_kw=0.95,
        energy_kwh=42.0,
        frequency_hz=60.0,
        power_factor=0.95,
        zone="MNZ-CENTRO",
        status="NORMAL",
        unexpected_field="should_be_ignored",
    )
    assert payload.meter_id == "AMI-MNZ-00001"


def test_telemetry_payload_optional_fields_default_to_none() -> None:
    payload = TelemetryPayload(
        meter_id="AMI-MNZ-00001",
        timestamp=datetime.now(timezone.utc),
        voltage_v=120.0,
        current_a=8.0,
        power_kw=0.95,
        energy_kwh=42.0,
        frequency_hz=60.0,
        power_factor=0.95,
    )
    assert payload.zone is None
    assert payload.status is None


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
