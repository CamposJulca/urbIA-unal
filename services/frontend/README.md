# frontend

Dashboard **Streamlit** del monorepo UrbIA-UNAL. Visualiza la telemetría AMI consumiendo los endpoints REST del servicio [`backend`](../backend/).

- Capa UrbIA: producto de software (no es contribución doctoral).
- Puerto: `8501`.
- Cliente HTTP al backend: `urbia_frontend.api_client.BackendClient`.

## Páginas

| Página | Path | Contenido |
|---|---|---|
| Home | `main.py` | Bienvenida + estado del backend (botón "ping") |
| Overview | `pages/01_Overview.py` | Métricas globales: medidores activos, tasa de ingesta, distribución por zona |
| Meters | `pages/02_Meters.py` | Tabla de medidores + drill-down al histórico |
| Live | `pages/03_Live.py` | Stream en tiempo real con autorefresh cada 2 s |

## Cómo correrlo

### Con docker compose (recomendado)

```bash
docker compose up -d frontend
docker compose logs -f frontend
```

Variables relevantes:

| Variable | Default | Descripción |
|---|---|---|
| `BACKEND_URL` | `http://backend:8000` | URL del backend dentro de la red bridge |
| `LOG_LEVEL` | `INFO` | Nivel de logging |

Abre `http://192.168.0.102:8501` desde tu máquina local.

### En local (para tests y desarrollo)

```bash
cd services/frontend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/ -v
BACKEND_URL=http://localhost:8000 streamlit run main.py
```

## Cache de Streamlit

Para que la UI no asesine al backend con cada interacción:

| Función | Cache TTL | Razón |
|---|---|---|
| `get_meters()` | 30 s | Cambia poco (10 medidores fijos) |
| `get_recent_telemetry()` (Live) | 2 s | Stream casi en tiempo real |
| `get_meter_telemetry_history()` | 10 s | Drill-down en Meters, no necesita ser instantáneo |
