"""Helpers de estado compartido entre páginas de Streamlit.

Centraliza el `BackendClient` con `@st.cache_resource` (una sola
instancia por proceso Streamlit) y expone wrappers `@st.cache_data`
con los TTL definidos en el README: 30 s para medidores, 10 s para
histórico, 2 s para telemetría reciente. Las páginas importan estos
helpers en vez de instanciar el cliente cada una.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd
import streamlit as st

from .api_client import (
    BackendClient,
    HealthStatus,
    TelemetryRecord,
    build_client_from_env,
)


@st.cache_resource(show_spinner=False)
def get_client() -> BackendClient:
    return build_client_from_env()


@st.cache_data(ttl=30, show_spinner=False)
def get_meters() -> pd.DataFrame:
    return get_client().get_meters()


@st.cache_data(ttl=2, show_spinner=False)
def get_recent_telemetry(limit: int = 100) -> pd.DataFrame:
    return get_client().get_recent_telemetry(limit=limit)


@st.cache_data(ttl=10, show_spinner=False)
def get_meter_history(meter_id: str, limit: int = 100) -> pd.DataFrame:
    return get_client().get_meter_history(meter_id, limit=limit)


@st.cache_data(ttl=2, show_spinner=False)
def get_meter_latest(meter_id: str) -> Optional[TelemetryRecord]:
    return get_client().get_meter_latest(meter_id)


def get_health() -> HealthStatus:
    """`/health` no se cachea — la UI quiere el estado real al pedirlo."""

    return get_client().health()
