"""Página de inicio del dashboard UrbIA.

Streamlit detecta automáticamente las páginas en `pages/`, por lo que
este script solo necesita renderizar la home y la barra lateral.
Aprovecha el `BackendClient` cacheado en `urbia_frontend.state` para
mostrar el estado del backend en vivo.
"""

from __future__ import annotations

import streamlit as st

from urbia_frontend.api_client import BackendError
from urbia_frontend.state import get_client, get_health

st.set_page_config(
    page_title="UrbIA — Monitoreo AMI",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="expanded",
)


def _render_sidebar() -> None:
    st.sidebar.title("UrbIA")
    st.sidebar.caption(
        "Dashboard de telemetría AMI — tesis doctoral, UNAL Manizales."
    )
    client = get_client()
    st.sidebar.markdown(f"**Backend:** `{client.base_url}`")
    st.sidebar.markdown(
        "Páginas disponibles (selecciónalas arriba):\n\n"
        "- **Overview** — métricas globales\n"
        "- **Meters** — tabla y drill-down por medidor\n"
        "- **Live** — stream en tiempo real"
    )


def _render_home() -> None:
    st.title("UrbIA — Sistema de monitoreo AMI urbano")
    st.markdown(
        "Esta aplicación visualiza la telemetría sintética de 10 medidores "
        "AMI publicada por `simulator-ami` al broker MQTT del cluster Neusi, "
        "persistida por el servicio `backend` en PostgreSQL y consumida acá "
        "por HTTP.\n\nUsa la barra lateral para navegar entre páginas."
    )

    st.subheader("Estado del backend")
    col_status, col_db, col_mqtt, col_refresh = st.columns([2, 1, 1, 1])

    try:
        health = get_health()
    except BackendError as exc:
        col_status.error(f"Backend no disponible: {exc}")
        return

    col_status.metric(
        label="Estado",
        value=health.status.upper(),
    )
    col_db.metric(label="PostgreSQL", value="OK" if health.db else "DOWN")
    col_mqtt.metric(label="MQTT", value="OK" if health.mqtt else "DOWN")
    if col_refresh.button("Refrescar"):
        st.rerun()


_render_sidebar()
_render_home()
