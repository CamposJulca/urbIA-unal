"""Meters — tabla de medidores y drill-down al histórico."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from urbia_frontend.api_client import BackendError
from urbia_frontend.state import (
    get_meter_history,
    get_meters,
    get_recent_telemetry,
)

st.set_page_config(page_title="UrbIA · Meters", layout="wide")
st.title("Meters")
st.caption("Inventario de medidores y drill-down al histórico.")


_DRILL_LIMIT = 100
_METRIC_ORDER = ["voltage_v", "current_a", "power_kw"]
_METRIC_LABELS = {
    "voltage_v": "Voltaje (V)",
    "current_a": "Corriente (A)",
    "power_kw": "Potencia (kW)",
}


def _latest_per_meter(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    return df.sort_values("received_at", ascending=False).drop_duplicates(
        subset=["meter_id"], keep="first"
    )


def _build_meter_overview(
    meters: pd.DataFrame, recent: pd.DataFrame
) -> pd.DataFrame:
    if meters.empty:
        return meters
    latest = _latest_per_meter(recent)[
        ["meter_id", "voltage_v", "current_a", "power_kw", "status"]
    ]
    merged = meters.merge(latest, on="meter_id", how="left")
    return merged[
        [
            "meter_id",
            "zone",
            "last_seen",
            "status",
            "voltage_v",
            "current_a",
            "power_kw",
        ]
    ]


if st.button("Refrescar"):
    get_meters.clear()
    get_recent_telemetry.clear()
    get_meter_history.clear()
    st.rerun()

try:
    meters_df = get_meters()
    recent_df = get_recent_telemetry(limit=100)
except BackendError as exc:
    st.error(f"No se pudo consultar el backend: {exc}")
    st.stop()

overview = _build_meter_overview(meters_df, recent_df)
if overview.empty:
    st.info("No hay medidores registrados aún.")
    st.stop()

st.subheader(f"Medidores ({len(overview)})")
st.dataframe(
    overview,
    use_container_width=True,
    hide_index=True,
    column_config={
        "meter_id": st.column_config.TextColumn("Meter ID"),
        "zone": st.column_config.TextColumn("Zona"),
        "last_seen": st.column_config.DatetimeColumn(
            "Visto por última vez", format="YYYY-MM-DD HH:mm:ss"
        ),
        "status": st.column_config.TextColumn("Status"),
        "voltage_v": st.column_config.NumberColumn(
            "Último V", format="%.2f"
        ),
        "current_a": st.column_config.NumberColumn(
            "Última I (A)", format="%.2f"
        ),
        "power_kw": st.column_config.NumberColumn(
            "Última P (kW)", format="%.3f"
        ),
    },
)

st.subheader("Drill-down al histórico")
meter_id = st.selectbox(
    "Medidor",
    options=overview["meter_id"].tolist(),
    index=0,
)

try:
    history = get_meter_history(meter_id, limit=_DRILL_LIMIT)
except BackendError as exc:
    st.error(f"No se pudo obtener el histórico: {exc}")
    st.stop()

if history.empty:
    st.info(f"No hay histórico para {meter_id}.")
else:
    long_df = (
        history.sort_values("received_at")
        .melt(
            id_vars=["received_at"],
            value_vars=_METRIC_ORDER,
            var_name="metric",
            value_name="value",
        )
        .replace({"metric": _METRIC_LABELS})
    )
    fig = px.line(
        long_df,
        x="received_at",
        y="value",
        facet_row="metric",
        labels={"received_at": "Tiempo", "value": ""},
        title=f"Últimas {len(history)} lecturas de {meter_id}",
        category_orders={
            "metric": [_METRIC_LABELS[k] for k in _METRIC_ORDER]
        },
    )
    fig.update_yaxes(matches=None)
    fig.for_each_annotation(
        lambda a: a.update(text=a.text.split("=", 1)[-1])
    )
    fig.update_layout(height=540, margin=dict(t=40, b=10), showlegend=False)
    st.plotly_chart(fig, use_container_width=True)
