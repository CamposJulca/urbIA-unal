# Sprint 2 — Nodo 192.168.0.103 (simulador1 · Python)

**Fecha:** 2026-04-19  
**Branch:** develop  
**Commit:** `c733633`  
**Máquina:** simulador1 — `192.168.0.103`

---

## Contexto

El Sprint 2 establece la capa de contrato de datos compartida por todo el clúster NEUSI y la lógica de validación del lado Python. Los entregables viven en `capa1/comun/` (compartido) y `capa1/simuladores/python/` (específico del nodo 103).

---

## Archivos creados

### 1. `capa1/comun/payload_schema_v1.json`

Esquema JSON Schema (draft-07) que define el contrato de telemetría para **todos** los nodos del clúster.

**Campos requeridos (15):**

| Campo | Tipo | Restricción |
|---|---|---|
| `device_id` | string | Regex `^urbia-(cen|chi|ena|pal|pgr|uni)-(mon|tri)-[0-9]{4}$` |
| `device_type` | string | enum: `mono`, `trifasico` |
| `zona` | string | enum: 6 zonas de Manizales |
| `timestamp_utc` | string | formato ISO 8601 date-time |
| `voltaje_v` | number | 187.0 – 253.0 V |
| `corriente_a` | number | 0.0 – 60.0 A |
| `potencia_kw` | number | 0.0 – 30.0 kW |
| `frecuencia_hz` | number | 57.0 – 63.0 Hz |
| `factor_potencia` | number | 0.0 – 1.0 |
| `lat` | number | 5.03 – 5.12 (bbox Manizales) |
| `lon` | number | -75.55 – -75.44 (bbox Manizales) |
| `estado` | string | enum: 7 estados operativos |
| `nodo_origen` | string | enum: `.103`, `.104`, `.105` |
| `lenguaje` | string | enum: `python`, `cpp`, `java` |
| `seed` | integer | ≥ 0 |

`additionalProperties: false` — cualquier campo extra invalida el payload.

---

### 2. `capa1/comun/medidores_manizales.json`

Catálogo estático de los **150 medidores** del piloto Manizales, generado con `seed=42`.

**Distribución por zona y nodo:**

| Zona | Cantidad | Tipo | Nodo | Lenguaje |
|---|---|---|---|---|
| centro | 25 | mono | 192.168.0.**103** | python |
| chipre | 25 | mono | 192.168.0.**103** | python |
| la_enea | 25 | trifasico | 192.168.0.104 | cpp |
| palermo | 25 | trifasico | 192.168.0.104 | cpp |
| palogrande | 30 | mono | 192.168.0.105 | java |
| universitario | 20 | trifasico | 192.168.0.105 | java |

El nodo 103 es responsable de **50 medidores monofásicos** (zonas centro y chipre).

Cada entrada tiene: `device_id`, `device_type`, `zona`, `lat`, `lon`, `nodo_origen`, `lenguaje`, `estado`.

---

### 3. `capa1/simuladores/python/src/payload_validator.py`

Clase `PayloadValidator` con **tres capas de validación** en cascada:

1. **Schema JSON** — `jsonschema.validate()` contra `payload_schema_v1.json`
2. **Rangos técnicos** — verificaciones adicionales:
   - Voltaje dentro de 187–253 V
   - Frecuencia dentro de 57–63 Hz
   - Coherencia energética: `|potencia_declarada − V×I×fp| / potencia_calc ≤ 20%`
3. **Timestamp** — el `timestamp_utc` no puede estar más de 60 s en el futuro

**Contadores integrados:** `validos_total`, `errores_total`.  
**Método `estadisticas()`** retorna `total_procesados`, `validos`, `errores`, `tasa_exito_pct`.

La ruta al schema se resuelve desde la variable de entorno `COMUN_DIR` (default `/app/comun`), alineada con el volumen Docker de la máquina.

---

### 4. `capa1/simuladores/python/tests/test_payload_validator.py`

Suite pytest con **13 tests** (4 positivos + 9 negativos):

**Positivos:**
- `test_payload_valido_completo` — payload canónico del nodo 103
- `test_payload_trifasico_valido` — payload del nodo 104 (cpp/trifasico)
- `test_todos_los_estados_validos` — recorre los 7 estados
- `test_todas_las_zonas_validas` — recorre las 6 zonas con device_id correcto

**Negativos:**
- `test_falta_campo_requerido` — falta `device_id`
- `test_device_id_formato_invalido` — formato libre rechazado
- `test_voltaje_fuera_de_rango` — 300 V → falla
- `test_frecuencia_fuera_de_rango` — 55 Hz → falla
- `test_zona_invalida` — zona fuera del enum
- `test_nodo_origen_invalido` — IP no registrada
- `test_coordenadas_fuera_de_manizales` — coordenadas de Bogotá
- `test_campo_adicional_no_permitido` — `additionalProperties` activo
- `test_estadisticas` — verifica contadores tras 1 válido + 1 inválido

---

## Estructura resultante del nodo 103 tras Sprint 2

```
capa1/
├── comun/
│   ├── medidores_manizales.json      ← catálogo 150 medidores (compartido)
│   └── payload_schema_v1.json        ← contrato de telemetría v1 (compartido)
└── simuladores/python/
    ├── src/
    │   └── payload_validator.py      ← validador 3 capas
    └── tests/
        └── test_payload_validator.py ← 13 tests pytest
```

---

## Notas

- El `device_id` usa el código corto `mon` en el JSON de medidores (`urbia-cen-mon-0001`) pero el schema acepta `mono` en el campo `device_type`. Son campos distintos; el regex en `device_id` usa la forma corta de 3 letras.
- La validación de coherencia energética tolera un 20 % de margen para cubrir pérdidas y redondeo de punto flotante en los simuladores.
- `COMUN_DIR` debe apuntar a `capa1/comun/` al correr tests localmente fuera de Docker.
