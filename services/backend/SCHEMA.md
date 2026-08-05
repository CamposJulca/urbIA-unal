# SCHEMA — Contratos de datos del backend UrbIA

Dos contratos separados. El de **entrada** (MQTT) está en español y es
espejo exacto de las columnas de PostgreSQL. El de **salida** (REST)
conserva los nombres en inglés que el frontend ya consume.

---

## 1. Entrada: AMI-JSON v2 (MQTT)

- **Productor:** externo, no vive en este monorepo. Se identifica en el
  propio mensaje con `nodo_origen` (hoy `192.168.0.103`, el nodo
  simulador1 del cluster) y `lenguaje` (hoy `python`).
- **Topic:** el productor publica bajo el árbol `urbia/manizales/`. El
  backend se suscribe con el comodín multinivel `urbia/manizales/#` y
  **no parsea el topic**: identifica el medidor por el `device_id` del
  payload. Los topics hermanos de ese árbol que no sean telemetría AMI
  fallan la validación y suben `invalid_count`.
- **Validación:** `urbia_backend.models.TelemetryPayload`
  (`extra="ignore"`: los campos que el productor agregue en el futuro no
  tumban la ingesta).
- **Obsoleto:** `services/simulator-ami` publicaba AMI-JSON v1.0 (campos
  en inglés, `meter_id` con formato `AMI-MNZ-NNNNN`). Ese esquema ya no
  se acepta.

| Campo | Tipo | Nulo | Notas |
|---|---|---|---|
| `device_id` | string(32) | no | `^urbia-(cen\|chi\|ena\|pal\|pgr\|uni)-(mon\|tri)-[0-9]{4}$` |
| `device_type` | string(16) | sí | valor observado: `mono`. **No coincide con el token del `device_id`**, que es `mon`/`tri`: son vocabularios distintos. El trifásico no se ha capturado todavía |
| `zona` | string(32) | sí | slug de zona (ver tabla 3) |
| `timestamp_utc` | ISO 8601 UTC | no | acepta sufijo `Z` |
| `voltaje_v` | float | no | |
| `corriente_a` | float | no | |
| `potencia_kw` | float | no | |
| `energia_kwh` | float | sí | el productor no siempre reporta acumulado |
| `frecuencia_hz` | float | no | |
| `factor_potencia` | float | no | |
| `estado` | string(24) | sí | enum de 7 valores, ver §1.1 |
| `nodo_origen` | string(24) | sí | nodo que originó el mensaje; valor observado: `192.168.0.103` |
| `lenguaje` | string(8) | sí | implementación del productor; valor observado: `python` |
| `seed` | int | sí | semilla de reproducibilidad |
| `lat` | float | sí | metadato: va a `ami_meters`, no a `ami_telemetry` |
| `lon` | float | sí | ídem |

> **Contrastado contra un mensaje real del broker** (captura del
> 2026-08-02, `urbia-cen-mon-0001`): valida sin errores contra
> `TelemetryPayload` y ningún valor desborda su `VARCHAR`. La única
> divergencia respecto de lo que se había asumido es `device_type`
> (`mono`, no `mon`), que no rompe nada porque el campo no está
> restringido a un enum. Si el productor agrega o renombra una clave
> obligatoria, el mensaje se descarta silenciosamente (`invalid_count`
> del `MqttConsumer` sube y queda un WARNING con `exc.errors()`).

### 1.1 Enum de `estado`

El productor declara siete valores. El backend **no** los valida (aceptar
un estado nuevo es preferible a descartar el mensaje); el que los
interpreta es el frontend, en `frontend-v2/src/lib/status.ts`.

| Valor | Emitido hoy | Color en el frontend |
|---|---|---|
| `activo` | sí (~98 %) | verde |
| `anomalia_voltaje` | sí (~1 %) | rojo |
| `falla` | sí (~1 %) | rojo |
| `mantenimiento` | no | ámbar |
| `anomalia_frecuencia` | no | rojo |
| `corte` | no | rojo |
| `desconectado` | no | rojo |

Los cuatro "no" no aparecerán hasta que exista el inyector de eventos.
Un valor fuera del enum se pinta rojo a propósito.

## 2. Persistencia

`services/backend/migrations/002_esquema_ami_v2.sql`. Las columnas de
`ami_telemetry` y `ami_meters` se llaman igual que los campos de
entrada; `id`, `recibido_en` e `instalado_en` los agrega la base.

## 3. Zonas

| Código (en `device_id`) | Slug (columna `zona`) | Etiqueta visible |
|---|---|---|
| `cen` | `centro` | Centro |
| `chi` | `chipre` | Chipre |
| `ena` | `la_enea` | La Enea |
| `pal` | `palermo` | Palermo |
| `pgr` | `palogrande` | Palogrande |
| `uni` | `universitario` | Universitario |

El backend **no** valida `zona` contra este enum: acepta cualquier
string de ≤32 caracteres para no rechazar telemetría si el productor
agrega una zona. El mapeo slug → etiqueta y color vive en el frontend
(`frontend-v2/src/lib/zones.ts`).

## 4. Salida: REST

`GET /telemetry/recent`, `/meters/{meter_id}/telemetry[/latest]` y
`/meters` devuelven los nombres en inglés históricos. La traducción se
hace con alias en el `SELECT` (`db.py`), no renombrando columnas ni con
adaptadores en el frontend.

| Columna | Campo REST |
|---|---|
| `device_id` | `meter_id` |
| `zona` | `zone` |
| `timestamp_utc` | `timestamp` |
| `voltaje_v` | `voltage_v` |
| `corriente_a` | `current_a` |
| `potencia_kw` | `power_kw` |
| `energia_kwh` | `energy_kwh` (ahora nullable) |
| `frecuencia_hz` | `frequency_hz` |
| `factor_potencia` | `power_factor` |
| `estado` | `status` |
| `recibido_en` | `received_at` |
| `instalado_en` | `installed_at` |
| `visto_por_ultima_vez` | `last_seen` |
| `activo` | `is_active` |

Los campos nuevos (`device_type`, `nodo_origen`, `lenguaje`, `seed`,
`lat`, `lon`) se exponen con su nombre de columna: no tenían nombre en
inglés previo que preservar.
