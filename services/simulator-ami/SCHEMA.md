# Schema de mensajes AMI — UrbIA v1.0

> Define el contrato de telemetría AMI que el servicio `simulator-ami` publica al broker MQTT del cluster Neusi. Cualquier consumidor (backend, monitor GSP, frontend) debe respetar este schema. Cambios al schema requieren bump de versión y nota en `docs/decisions/`.

---

## Versión

`AMI-JSON v1.0` — esta versión es la inicial. Sin compatibilidad hacia atrás todavía (no aplica).

---

## Topic

```
urbia/ami/{meter_id}/telemetry
```

- Patrón: `urbia/ami/+/telemetry` (un nivel `+` para `meter_id`).
- QoS recomendado: `0` (telemetría de alta frecuencia, mejor perder un mensaje que retransmitir).
- Retención: `false` (no `retain`; cada mensaje es transitorio).
- Codificación: UTF-8.

Ejemplo concreto:

```
urbia/ami/AMI-MNZ-00001/telemetry
```

---

## Payload (JSON)

```json
{
  "meter_id": "AMI-MNZ-00001",
  "timestamp": "2026-05-04T18:00:00.000Z",
  "voltage_v": 120.45,
  "current_a": 8.32,
  "power_kw": 1.001,
  "energy_kwh": 1542.78,
  "frequency_hz": 60.01,
  "power_factor": 0.95,
  "zone": "MNZ-CENTRO",
  "status": "NORMAL"
}
```

---

## Campos

| Campo | Tipo | Rango / Formato | Descripción |
|---|---|---|---|
| `meter_id` | string | `AMI-MNZ-NNNNN` (regex `^AMI-MNZ-\d{5}$`) | Identificador único del medidor virtual. Determinístico entre reinicios. |
| `timestamp` | string | ISO 8601 UTC con milisegundos (`YYYY-MM-DDTHH:MM:SS.sssZ`) | Momento exacto de la medición. UTC obligatorio. |
| `voltage_v` | float | `100.0` ≤ V ≤ `130.0`, nominal `120.0`, jitter ±2 | Voltaje RMS en voltios. |
| `current_a` | float | `0.0` ≤ A ≤ `50.0`, nominal `8.0`, jitter dependiente de la hora | Corriente RMS en amperios. |
| `power_kw` | float | derivado: `voltage_v * current_a * power_factor / 1000` | Potencia activa en kW. |
| `energy_kwh` | float | monotónico creciente | Energía consumida acumulada desde arranque del medidor. |
| `frequency_hz` | float | `59.5` ≤ Hz ≤ `60.5`, nominal `60.0`, jitter ±0.05 | Frecuencia de red en Hz. |
| `power_factor` | float | `0.0` ≤ pf ≤ `1.0`, nominal `0.95`, jitter ±0.02 | Factor de potencia (adimensional). |
| `zone` | string (enum) | una de las 5 zonas de Manizales | Zona urbana asignada al medidor. Estable entre reinicios. |
| `status` | string (enum) | `NORMAL` / `WARNING` / `ALARM` | Estado operativo. En v1.0 siempre `NORMAL`. |

### Enum `zone`

| Código | Zona urbana |
|---|---|
| `MNZ-CENTRO` | Centro de Manizales |
| `MNZ-NORTE` | Norte |
| `MNZ-SUR` | Sur |
| `MNZ-ESTE` | Este |
| `MNZ-OESTE` | Oeste |

Distribución determinística de los 10 medidores de la v1.0 (2 por zona):

| meter_id | zone |
|---|---|
| `AMI-MNZ-00001` | `MNZ-CENTRO` |
| `AMI-MNZ-00002` | `MNZ-CENTRO` |
| `AMI-MNZ-00003` | `MNZ-NORTE` |
| `AMI-MNZ-00004` | `MNZ-NORTE` |
| `AMI-MNZ-00005` | `MNZ-SUR` |
| `AMI-MNZ-00006` | `MNZ-SUR` |
| `AMI-MNZ-00007` | `MNZ-ESTE` |
| `AMI-MNZ-00008` | `MNZ-ESTE` |
| `AMI-MNZ-00009` | `MNZ-OESTE` |
| `AMI-MNZ-00010` | `MNZ-OESTE` |

### Enum `status`

| Código | Significado | Generado en v1.0 |
|---|---|---|
| `NORMAL` | Operación normal | Siempre |
| `WARNING` | Anomalía leve detectada localmente | No (reservado) |
| `ALARM` | Anomalía severa | No (reservado) |

---

## Invariantes obligatorias

1. **`meter_id` determinístico**: el medidor #k siempre se llama `AMI-MNZ-{k:05d}` entre reinicios.
2. **`zone` estable**: misma `zone` para un mismo `meter_id` entre reinicios.
3. **`energy_kwh` monotónico**: dentro de un mismo proceso (entre reinicios puede resetearse en v1.0).
4. **`power_kw` derivado**: no muestreado independientemente; se calcula con `voltage_v * current_a * power_factor / 1000` redondeado a 3 decimales.
5. **`timestamp` siempre en UTC** con sufijo `Z` y precisión de milisegundos.
6. **JSON serializable** sin caracteres especiales fuera de UTF-8 estándar.

---

## Validación

Cada mensaje publicado pasa por un modelo Pydantic v2 (`TelemetryPayload`) antes de salir al broker. El servicio rechaza (descarta y loggea) cualquier mensaje que no valide. Consumidores deben hacer su propia validación: el broker es anónimo y no garantiza el origen.

---

## Notas operativas

- **Tasa de publicación**: configurable vía `SIMULATOR_PUBLISH_RATE_HZ` (default `1`). A `1 Hz` con 10 medidores → ~10 msg/s sobre el broker.
- **Reconexión**: el cliente paho-mqtt reintenta solo en caso de pérdida de conexión.
- **Privacidad**: los datos son sintéticos; ningún dato refleja consumo real.
