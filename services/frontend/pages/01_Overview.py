"""Overview — métricas globales del cluster AMI urbano."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import plotly.express as px
import streamlit as st

from urbia_frontend.api_client import BackendError
from urbia_frontend.state import get_meters, get_recent_telemetry

st.set_page_config(page_title="UrbIA · Overview", layout="wide")
st.title("Overview")
st.caption("Métricas globales del cluster AMI urbano.")


def _ingestion_rate_msg_per_sec(df: pd.DataFrame) -> float:
    """Tasa estimada de ingesta a partir del rango de received_at."""

    if len(df) < 2:
        return 0.0
    span = (df["received_at"].max() - df["received_at"].min()).total_seconds()
    if span <= 0:
        return 0.0
    return (len(df) - 1) / span


def _current_total_power_kw(df: pd.DataFrame) -> float:
    """Suma de power_kw del último mensaje recibido por medidor."""

    if df.empty:
        return 0.0
    latest_per_meter = (
        df.sort_values("received_at", ascending=False)
        .drop_duplicates(subset=["meter_id"], keep="first")
    )
    return float(latest_per_meter["power_kw"].sum())


if st.button("Refrescar"):
    get_meters.clear()
    get_recent_telemetry.clear()
    st.rerun()

try:
    meters_df = get_meters()
    short_window_df = get_recent_telemetry(limit=200)
    long_window_df = get_recent_telemetry(limit=1000)
except BackendError as exc:
    st.error(f"No se pudo consultar el backend: {exc}")
    st.stop()

active_meters = int(meters_df["is_active"].sum()) if not meters_df.empty else 0
ingestion_rate = _ingestion_rate_msg_per_sec(short_window_df)
now_utc = datetime.now(timezone.utc)
last_hour_count = (
    int((long_window_df["received_at"] >= now_utc - timedelta(hours=1)).sum())
    if not long_window_df.empty
    else 0
)
total_power_kw = _current_total_power_kw(long_window_df)

col1, col2, col3, col4 = st.columns(4)
col1.metric("Medidores activos", f"{active_meters}")
col2.metric("Tasa de ingesta", f"{ingestion_rate:.1f} msg/s")
col3.metric("Mensajes (≈ últimos 100 s)", f"{last_hour_count}")
col4.metric("Potencia total ahora", f"{total_power_kw:.2f} kW")

st.caption(
    "**Mensajes (≈ 100 s):** count de registros con `received_at` en la última "
    "hora, pero acotado por el límite de `/telemetry/recent?limit=1000`. A "
    "10 msg/s eso cubre ~100 segundos. Para una métrica horaria real haría "
    "falta un endpoint `/stats` en el backend (anotado como deuda técnica)."
)

st.subheader("Distribución de medidores por zona")
if meters_df.empty:
    st.info("No hay medidores registrados aún.")
else:
    zone_counts = (
        meters_df.assign(zone=meters_df["zone"].fillna("(sin zona)"))
        .groupby("zone")["meter_id"]
        .count()
        .reset_index(name="count")
        .sort_values("count", ascending=True)
    )
    fig = px.bar(
        zone_counts,
        x="count",
        y="zone",
        orientation="h",
        labels={"count": "Medidores", "zone": "Zona"},
    )
    fig.update_layout(yaxis_title=None, height=320, margin=dict(t=10, b=10))
    st.plotly_chart(fig, use_container_width=True)
