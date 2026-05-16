# simulator-ami

Servicio del monorepo **UrbIA-UNAL** que simula medidores AMI urbanos y publica telemetría sintética al broker MQTT del cluster Neusi.

- Schema de mensajes: ver [`SCHEMA.md`](./SCHEMA.md).
- Topic: `urbia/ami/{meter_id}/telemetry`.
- Broker: `192.168.0.101:1883` (modo anónimo).
- Capa UrbIA: producto de software (no es contribución doctoral).

## Cómo correrlo

### Con docker compose (recomendado)

Desde la raíz del monorepo:

```bash
docker compose up -d simulator-ami
docker compose logs -f simulator-ami
```

Variables relevantes en `.env` (heredadas del bloque MQTT):

| Variable | Default | Descripción |
|---|---|---|
| `MQTT_HOST` | `192.168.0.101` | Host del broker |
| `MQTT_PORT` | `1883` | Puerto del broker |
| `MQTT_USERNAME` | vacío | Vacío para broker anónimo |
| `MQTT_PASSWORD` | vacío | Vacío para broker anónimo |
| `SIMULATOR_NUM_METERS` | `10` | Cantidad de medidores virtuales |
| `SIMULATOR_PUBLISH_RATE_HZ` | `1` | Tasa de publicación por medidor |
| `LOG_LEVEL` | `INFO` | Nivel de logging |

### En local (para tests)

```bash
cd services/simulator-ami
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/ -v
```

## Cómo verificar que está publicando

Desde cualquier máquina del cluster con `mosquitto-clients`:

```bash
mosquitto_sub -h 192.168.0.101 -p 1883 -t 'urbia/ami/+/telemetry' -v -C 10
```

Salida esperada: 10 mensajes JSON, uno por medidor, con los campos definidos en `SCHEMA.md`.

## Reinicio y determinismo

Los `meter_id` son determinísticos (`AMI-MNZ-00001` … `AMI-MNZ-{N:05d}`) y la zona asignada a cada medidor también lo es. La energía acumulada (`energy_kwh`) sí se reinicia al reiniciar el proceso (aceptable en v1.0).
