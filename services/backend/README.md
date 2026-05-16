# backend

Servicio del monorepo **UrbIA-UNAL** que consume telemetría AMI por MQTT, persiste cada mensaje a PostgreSQL y expone endpoints REST.

- Capa UrbIA: producto de software (no es contribución doctoral).
- Schema de mensajes consumidos: ver [`../simulator-ami/SCHEMA.md`](../simulator-ami/SCHEMA.md).
- Schema de la base de datos: ver [`migrations/001_initial.sql`](./migrations/001_initial.sql).

## Endpoints

| Método | Path | Descripción |
|---|---|---|
| `GET` | `/health` | Salud del servicio. Reporta estado del pool DB y del cliente MQTT. |
| `GET` | `/meters` | Lista de medidores activos con su `last_seen`. |
| `GET` | `/meters/{meter_id}/telemetry/latest` | Último mensaje recibido de un medidor. |
| `GET` | `/meters/{meter_id}/telemetry?limit=N` | Histórico de un medidor (`N` ∈ [1, 1000], default 100). |
| `GET` | `/telemetry/recent?limit=N` | Últimos N mensajes globales (`N` ∈ [1, 1000], default 100). |

OpenAPI / Swagger UI: `http://localhost:8000/docs`.

## Cómo correrlo

### Con docker compose (recomendado)

Desde la raíz del monorepo:

```bash
docker compose up -d backend
docker compose logs -f backend
```

Variables relevantes en `.env`:

| Variable | Default | Descripción |
|---|---|---|
| `POSTGRES_HOST` | `postgres` (DNS interno docker) | Host del Postgres |
| `POSTGRES_PORT` | `5432` | Puerto del Postgres |
| `POSTGRES_DB` | `urbia` | Base de datos |
| `POSTGRES_USER` | `urbia` | Usuario |
| `POSTGRES_PASSWORD` | `...` | Contraseña (desde `.env`, no commiteada) |
| `MQTT_HOST` | `192.168.0.101` | Broker MQTT del cluster |
| `MQTT_PORT` | `1883` | Puerto del broker |
| `MQTT_USERNAME` / `MQTT_PASSWORD` | vacío | Modo anónimo |
| `MQTT_TOPIC_TELEMETRY` | `urbia/ami/+/telemetry` | Topic suscrito |
| `BACKEND_HOST` | `0.0.0.0` | Bind del servidor HTTP |
| `BACKEND_PORT` | `8000` | Puerto del servidor HTTP |
| `LOG_LEVEL` | `INFO` | Nivel de logging |

### En local (para tests)

```bash
cd services/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/ -v
```

## Migración inicial

La migración SQL no se aplica desde el contenedor del backend; se aplica una sola vez contra el contenedor `urbia-postgres`:

```bash
docker exec -i urbia-postgres psql -U urbia -d urbia < services/backend/migrations/001_initial.sql
```

## Cómo verificar que está sano

```bash
curl -s http://localhost:8000/health | jq
curl -s "http://localhost:8000/telemetry/recent?limit=5" | jq
```

El servicio se considera sano cuando `/health` devuelve `200` con `db: true` y `mqtt: true` y la tabla `ami_telemetry` crece a ~10 filas/segundo (10 medidores × 1 Hz).
