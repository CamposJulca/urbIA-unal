"""Live — stream en tiempo real con autorefresh cada 2 s."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import plotly.express as px
import streamlit as st

from urbia_frontend.api_client import BackendError
from urbia_frontend.state import get_client, get_meters

st.set_page_config(page_title="UrbIA · Live", layout="wide")
st.title("Live")
st.caption(
    "Stream en tiempo real. Auto-refresh cada 2 s usando `st.fragment`."
)


_WINDOW_MINUTES = 5
_PER_METER_LIMIT = 400  # cubre 5 min + colchón a 1 Hz por medidor
_METRIC_ORDER = ["voltage_v", "current_a", "power_kw"]
_METRIC_LABELS = {
    "voltage_v": "Voltaje (V)",
    "current_a": "Corriente (A)",
    "power_kw": "Potencia (kW)",
}


# ----- Selector de medidores (fuera del fragment para no interrumpirlo) -----

try:
    meters_df = get_meters()
except BackendError as exc:
    st.error(f"No se pudo cargar la lista de medidores: {exc}")
    st.stop()

if meters_df.empty:
    st.info("No hay medidores registrados aún.")
    st.stop()

all_meter_ids = meters_df["meter_id"].tolist()
selected_meters = st.multiselect(
    "Medidores a graficar",
    options=all_meter_ids,
    default=all_meter_ids,
    help="Por defecto se grafican los 10 medidores.",
)
st.session_state["live_meter_selection"] = selected_meters

if not selected_meters:
    st.info("Selecciona al menos un medidor.")
    st.stop()


def _fetch_window(meter_ids: list[str]) -> pd.DataFrame:
    """Bypassa el `@st.cache_data` de state.py — Live quiere frescura.

    Hace una llamada `/meters/{id}/telemetry?limit=400` por medidor
    seleccionado y concatena. A 1 Hz por medidor, 400 muestras cubren
    holgadamente la ventana de 5 minutos.
    """

    client = get_client()
    frames: list[pd.DataFrame] = []
    for meter_id in meter_ids:
        frames.append(client.get_meter_history(meter_id, limit=_PER_METER_LIMIT))
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


@st.fragment(run_every=2)
def live_stream() -> None:
    meter_ids = st.session_state.get("live_meter_selection") or []
    if not meter_ids:
        return

    try:
        df = _fetch_window(meter_ids)
    except BackendError as exc:
        st.error(f"Backend no disponible: {exc}")
        return

    now_utc = datetime.now(timezone.utc)
    window_start = now_utc - timedelta(minutes=_WINDOW_MINUTES)
    df = df[df["received_at"] >= window_start].copy()

    status_col, last_col, count_col = st.columns([1, 2, 2])
    status_col.success(f"Conectado · {len(meter_ids)} medidores")
    last_col.markdown(
        f"**Última actualización:** `{now_utc.astimezone().strftime('%H:%M:%S')}`"
    )
    count_col.markdown(
        f"**Muestras en ventana:** `{len(df)}` "
        f"(últimos {_WINDOW_MINUTES} min)"
    )

    if df.empty:
        st.info("No hay datos en la ventana — esperando primer mensaje.")
        return

    long_df = (
        df.sort_values("received_at")
        .melt(
            id_vars=["received_at", "meter_id"],
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
        color="meter_id",
        facet_row="metric",
        labels={"received_at": "Tiempo", "value": "", "meter_id": "Medidor"},
        category_orders={
            "metric": [_METRIC_LABELS[k] for k in _METRIC_ORDER]
        },
    )
    fig.update_yaxes(matches=None)
    fig.for_each_annotation(
        lambda a: a.update(text=a.text.split("=", 1)[-1])
    )
    fig.update_layout(height=620, margin=dict(t=40, b=10))
    st.plotly_chart(fig, use_container_width=True)


live_stream()
