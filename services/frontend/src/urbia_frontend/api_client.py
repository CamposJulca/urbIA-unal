"""Cliente HTTP del frontend Streamlit al backend FastAPI de UrbIA.

Encapsula las 5 rutas REST del backend y devuelve modelos Pydantic
para respuestas singulares y `pandas.DataFrame` para respuestas
tabulares. Centraliza también el manejo de errores: cualquier fallo
de red, timeout o 4xx/5xx se traduce a una excepción específica del
módulo (subclase de `BackendError`) para que la UI pueda atrapar y
mostrar un mensaje útil sin filtrar trazas de `requests`.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, Optional

import pandas as pd
import requests
from pydantic import BaseModel, ConfigDict
from requests import Response

logger = logging.getLogger(__name__)


# ----- Modelos Pydantic (espejo de los del backend) -----

class HealthStatus(BaseModel):
    status: str
    db: bool
    mqtt: bool


class Meter(BaseModel):
    model_config = ConfigDict(extra="ignore")

    meter_id: str
    zone: Optional[str] = None
    installed_at: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    is_active: bool = True


class TelemetryRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    meter_id: str
    timestamp: datetime
    voltage_v: float
    current_a: float
    power_kw: float
    energy_kwh: float
    frequency_hz: float
    power_factor: float
    zone: Optional[str] = None
    status: Optional[str] = None
    received_at: datetime


# ----- Excepciones del cliente -----

class BackendError(Exception):
    """Raíz de los errores del backend desde la UI."""


class BackendUnavailable(BackendError):
    """No se pudo establecer conexión con el backend."""


class BackendTimeout(BackendError):
    """El backend no respondió dentro del timeout configurado."""


class BackendHTTPError(BackendError):
    """El backend respondió con código 4xx/5xx no manejado."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(f"HTTP {status_code}: {detail}")
        self.status_code = status_code
        self.detail = detail


# ----- Cliente -----

DEFAULT_TIMEOUT_SECONDS = 5.0
_TELEMETRY_COLUMNS = [
    "id",
    "meter_id",
    "timestamp",
    "voltage_v",
    "current_a",
    "power_kw",
    "energy_kwh",
    "frequency_hz",
    "power_factor",
    "zone",
    "status",
    "received_at",
]
_METER_COLUMNS = [
    "meter_id",
    "zone",
    "installed_at",
    "last_seen",
    "is_active",
]


class BackendClient:
    """Cliente HTTP al backend FastAPI de UrbIA."""

    def __init__(
        self,
        base_url: str,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._session = session or requests.Session()

    # ----- Métodos públicos: un wrapper por endpoint del backend -----

    def health(self) -> HealthStatus:
        data = self._get("/health")
        return HealthStatus.model_validate(data)

    def get_meters(self) -> pd.DataFrame:
        data = self._get("/meters")
        return _records_to_dataframe(
            data, _METER_COLUMNS, parse_dates=("installed_at", "last_seen")
        )

    def get_meter_latest(self, meter_id: str) -> Optional[TelemetryRecord]:
        """Devuelve el último mensaje del medidor, o `None` si no hay."""

        try:
            data = self._get(f"/meters/{meter_id}/telemetry/latest")
        except BackendHTTPError as exc:
            if exc.status_code == 404:
                return None
            raise
        return TelemetryRecord.model_validate(data)

    def get_meter_history(
        self, meter_id: str, limit: int = 100
    ) -> pd.DataFrame:
        data = self._get(
            f"/meters/{meter_id}/telemetry", params={"limit": limit}
        )
        return _records_to_dataframe(
            data, _TELEMETRY_COLUMNS, parse_dates=("timestamp", "received_at")
        )

    def get_recent_telemetry(self, limit: int = 100) -> pd.DataFrame:
        data = self._get("/telemetry/recent", params={"limit": limit})
        return _records_to_dataframe(
            data, _TELEMETRY_COLUMNS, parse_dates=("timestamp", "received_at")
        )

    # ----- Mecánica HTTP -----

    def _get(self, path: str, params: Optional[dict[str, Any]] = None) -> Any:
        url = f"{self.base_url}{path}"
        try:
            response: Response = self._session.get(
                url, params=params, timeout=self.timeout
            )
        except requests.Timeout as exc:
            logger.warning("Timeout llamando a %s: %s", url, exc)
            raise BackendTimeout(f"Timeout llamando a {path}") from exc
        except requests.ConnectionError as exc:
            logger.warning("Backend no accesible en %s: %s", url, exc)
            raise BackendUnavailable(
                f"No se pudo conectar al backend en {self.base_url}"
            ) from exc
        except requests.RequestException as exc:
            logger.exception("Error de requests llamando a %s", url)
            raise BackendError(f"Fallo de requests: {exc}") from exc

        if not response.ok:
            detail = _extract_error_detail(response)
            logger.warning(
                "Backend devolvió %s en %s: %s",
                response.status_code,
                path,
                detail,
            )
            raise BackendHTTPError(response.status_code, detail)
        return response.json()


# ----- Helpers privados -----

def _extract_error_detail(response: Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text[:200]
    if isinstance(body, dict) and "detail" in body:
        return str(body["detail"])
    return str(body)[:200]


def _records_to_dataframe(
    records: list[dict],
    columns: list[str],
    parse_dates: tuple[str, ...] = (),
) -> pd.DataFrame:
    """Convierte una lista de dicts JSON a `pd.DataFrame`.

    Si la lista viene vacía, devuelve un DataFrame con las columnas
    esperadas para que las páginas no tengan que chequear el caso vacío.
    """

    if not records:
        return pd.DataFrame(columns=columns)
    df = pd.DataFrame.from_records(records, columns=columns)
    for col in parse_dates:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], utc=True, errors="coerce")
    return df


def build_client_from_env() -> BackendClient:
    """Factory por defecto: lee `BACKEND_URL` del entorno."""

    base_url = os.environ.get("BACKEND_URL", "http://backend:8000")
    return BackendClient(base_url=base_url)
