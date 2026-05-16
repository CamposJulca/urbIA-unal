"""Tests del cliente HTTP al backend (`urbia_frontend.api_client`).

Usa `requests-mock` para no depender del backend real. Cubre los 5
métodos del cliente, la traducción de errores de `requests` a las
excepciones del módulo, y la conversión a DataFrame.
"""

from __future__ import annotations

import pandas as pd
import pytest
import requests

from urbia_frontend.api_client import (
    BackendClient,
    BackendError,
    BackendHTTPError,
    BackendTimeout,
    BackendUnavailable,
    HealthStatus,
    TelemetryRecord,
    build_client_from_env,
)

BASE_URL = "http://backend.test:8000"

_TELEMETRY_SAMPLE = {
    "id": 1,
    "meter_id": "AMI-MNZ-00001",
    "timestamp": "2026-05-16T16:00:00Z",
    "voltage_v": 120.0,
    "current_a": 8.0,
    "power_kw": 0.95,
    "energy_kwh": 100.0,
    "frequency_hz": 60.0,
    "power_factor": 0.95,
    "zone": "MNZ-CENTRO",
    "status": "NORMAL",
    "received_at": "2026-05-16T16:00:00Z",
}


@pytest.fixture
def client() -> BackendClient:
    return BackendClient(base_url=BASE_URL, timeout=2.0)


def test_backend_client_health_returns_pydantic_model(
    client: BackendClient, requests_mock
) -> None:
    requests_mock.get(
        f"{BASE_URL}/health",
        json={"status": "ok", "db": True, "mqtt": True},
    )
    health = client.health()
    assert isinstance(health, HealthStatus)
    assert health.status == "ok"
    assert health.db is True
    assert health.mqtt is True


def test_backend_client_get_meters(
    client: BackendClient, requests_mock
) -> None:
    requests_mock.get(
        f"{BASE_URL}/meters",
        json=[
            {
                "meter_id": "AMI-MNZ-00001",
                "zone": "MNZ-CENTRO",
                "installed_at": "2026-05-01T00:00:00Z",
                "last_seen": "2026-05-16T16:00:00Z",
                "is_active": True,
            },
            {
                "meter_id": "AMI-MNZ-00002",
                "zone": "MNZ-NORTE",
                "installed_at": "2026-05-01T00:00:00Z",
                "last_seen": "2026-05-16T16:00:01Z",
                "is_active": True,
            },
        ],
    )
    df = client.get_meters()
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 2
    assert list(df.columns) == [
        "meter_id",
        "zone",
        "installed_at",
        "last_seen",
        "is_active",
    ]
    assert df["meter_id"].tolist() == ["AMI-MNZ-00001", "AMI-MNZ-00002"]
    # Fechas parseadas a datetime64[ns, UTC]
    assert pd.api.types.is_datetime64_any_dtype(df["last_seen"])


def test_backend_client_get_meters_empty_returns_dataframe_with_columns(
    client: BackendClient, requests_mock
) -> None:
    requests_mock.get(f"{BASE_URL}/meters", json=[])
    df = client.get_meters()
    assert df.empty
    assert list(df.columns) == [
        "meter_id",
        "zone",
        "installed_at",
        "last_seen",
        "is_active",
    ]


def test_backend_client_get_telemetry_recent(
    client: BackendClient, requests_mock
) -> None:
    requests_mock.get(
        f"{BASE_URL}/telemetry/recent",
        json=[_TELEMETRY_SAMPLE],
    )
    df = client.get_recent_telemetry(limit=1)
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 1
    assert df.iloc[0]["meter_id"] == "AMI-MNZ-00001"
    # El query param se mandó correctamente.
    assert requests_mock.last_request.qs == {"limit": ["1"]}


def test_backend_client_get_meter_history(
    client: BackendClient, requests_mock
) -> None:
    requests_mock.get(
        f"{BASE_URL}/meters/AMI-MNZ-00001/telemetry",
        json=[_TELEMETRY_SAMPLE],
    )
    df = client.get_meter_history("AMI-MNZ-00001", limit=50)
    assert len(df) == 1
    assert requests_mock.last_request.qs == {"limit": ["50"]}


def test_backend_client_get_meter_latest_returns_record(
    client: BackendClient, requests_mock
) -> None:
    requests_mock.get(
        f"{BASE_URL}/meters/AMI-MNZ-00001/telemetry/latest",
        json=_TELEMETRY_SAMPLE,
    )
    record = client.get_meter_latest("AMI-MNZ-00001")
    assert isinstance(record, TelemetryRecord)
    assert record.meter_id == "AMI-MNZ-00001"


def test_backend_client_get_meter_latest_returns_none_on_404(
    client: BackendClient, requests_mock
) -> None:
    requests_mock.get(
        f"{BASE_URL}/meters/AMI-MNZ-99999/telemetry/latest",
        status_code=404,
        json={"detail": "No hay telemetría registrada para AMI-MNZ-99999"},
    )
    assert client.get_meter_latest("AMI-MNZ-99999") is None


def test_backend_client_handles_connection_error(
    client: BackendClient, requests_mock
) -> None:
    requests_mock.get(
        f"{BASE_URL}/meters", exc=requests.exceptions.ConnectionError
    )
    with pytest.raises(BackendUnavailable):
        client.get_meters()


def test_backend_client_handles_timeout(
    client: BackendClient, requests_mock
) -> None:
    requests_mock.get(
        f"{BASE_URL}/meters", exc=requests.exceptions.Timeout
    )
    with pytest.raises(BackendTimeout):
        client.get_meters()


def test_backend_client_raises_http_error_on_5xx(
    client: BackendClient, requests_mock
) -> None:
    requests_mock.get(
        f"{BASE_URL}/meters",
        status_code=502,
        json={"detail": "bad gateway"},
    )
    with pytest.raises(BackendHTTPError) as exc_info:
        client.get_meters()
    assert exc_info.value.status_code == 502
    assert "bad gateway" in exc_info.value.detail


def test_backend_client_raises_http_error_with_non_json_body(
    client: BackendClient, requests_mock
) -> None:
    requests_mock.get(
        f"{BASE_URL}/meters", status_code=500, text="upstream exploded"
    )
    with pytest.raises(BackendHTTPError) as exc_info:
        client.get_meters()
    assert exc_info.value.status_code == 500
    assert "upstream exploded" in exc_info.value.detail


def test_backend_client_wraps_other_requests_exceptions(
    client: BackendClient, requests_mock
) -> None:
    requests_mock.get(
        f"{BASE_URL}/meters",
        exc=requests.exceptions.TooManyRedirects,
    )
    with pytest.raises(BackendError):
        client.get_meters()


def test_backend_client_strips_trailing_slash_from_base_url() -> None:
    client = BackendClient(base_url="http://example.test:8000/")
    assert client.base_url == "http://example.test:8000"


def test_build_client_from_env_uses_default_when_unset(monkeypatch) -> None:
    monkeypatch.delenv("BACKEND_URL", raising=False)
    client = build_client_from_env()
    assert client.base_url == "http://backend:8000"


def test_build_client_from_env_honors_backend_url(monkeypatch) -> None:
    monkeypatch.setenv("BACKEND_URL", "http://otro:9000/")
    client = build_client_from_env()
    assert client.base_url == "http://otro:9000"
