# MIGRATION_NOTES — `urbia-platform` (.103) → `urbIA-unal` (.102)

> Notas de migración del snapshot legacy `urbia-platform` (sprints 2–3 del nodo
> .103, abril 2026) al monorepo nuevo `urbIA-unal` que vive en .102.
>
> Este documento acompaña al snapshot bajo `legacy/urbia-platform/` y registra
> (a) el hallazgo de seguridad encontrado durante la copia, (b) el inventario
> de piezas valiosas reutilizables, (c) el mapeo propuesto a la nueva
> estructura `services/` / `libs/` / `data/`.
>
> **No es un plan de implementación.** El plan vive en `plan-trabajo/` y los
> ADRs en `docs/decisions/`. Este archivo es la guía arqueológica.

---

## 1. Hallazgo de seguridad — Token GitHub

Durante la preparación del snapshot se detectó un Personal Access Token de
GitHub embebido en la URL del remoto del repositorio legacy en .103.

### 1.1 Resumen

| Campo | Valor |
|---|---|
| Tipo de credencial | GitHub Personal Access Token (clásico) |
| Ubicación encontrada | `/opt/urbia/.git/config` en `simulador1` (192.168.0.103) |
| Forma | Embebido en la URL del remoto `origin` (`https://<token>@github.com/...`) |
| Snapshot afectado | `legacy/urbia-platform/` (este directorio) |
| Estado del token | **Revocado en GitHub el 2026-05-18** |
| Bundle git (`git-history.bundle`) | Verificado: no contiene el token (la URL del remoto no se versiona, vive sólo en `.git/config`) |

### 1.2 Mitigación aplicada

1. El token fue **eliminado del snapshot** `legacy/urbia-platform/` **antes**
   de copiar los artefactos desde .103 hacia .102. El árbol que vive bajo
   este directorio no contiene ningún `.git/config` con la URL afectada;
   sólo conserva el `git-history.bundle` (los commits del trabajo) y los
   archivos fuente.
2. El token fue **revocado en GitHub el 2026-05-18** desde
   `https://github.com/settings/tokens`. Esto invalida cualquier copia que
   pudiera quedar en otros sitios.
3. Verificación: `grep -rE "ghp_|github_pat_|gho_|ghu_|ghs_|ghr_"` sobre
   `legacy/urbia-platform/` y sobre `/home/pruebas/urbIA-unal/` no arroja
   coincidencias. El `.git/config` del nuevo repo `urbIA-unal` usa `git@`
   (SSH key de .102), no HTTPS con token.

### 1.3 Riesgo residual conocido

- **`/opt/urbia/.git/config` en .103 todavía contiene la cadena del token**,
  pero el token ya fue revocado y por lo tanto es inutilizable. Esta copia
  desaparecerá cuando `/opt/urbia/` sea retirado de .103 al cerrar la
  migración (acción operativa pendiente, no bloqueante para el MVP).
- El `~/.bash_history` y los logs del shell en .103 **podrían** contener
  fragmentos del token tecleados durante `git clone` / `git push` originales.
  No se auditó porque está fuera de scope de esta migración.

### 1.4 Recomendaciones post-MVP

Cuando el MVP esté estable y haya tiempo de auditoría, revisar en .103:

- `~/.bash_history` del usuario que clonó (`grep -E "ghp_|github_pat_"`).
- `~/.zsh_history` si aplica.
- Logs persistentes de cron / systemd que hayan capturado salida con la URL.
- Salidas guardadas (`tee`, redirecciones a archivo) bajo `/opt/urbia/`,
  `/tmp/` y `/var/log/`.
- Backups antiguos de `/opt/urbia/` (si los hay) que puedan contener el
  `.git/config` con el token.

Para reducir reincidencia, en .102 el repo usa **SSH** (`git@github.com:...`)
con la key registrada en GitHub, no tokens HTTPS. Esa es la política a
mantener para el resto del cluster.

---

## 2. Origen del snapshot

| Campo | Valor |
|---|---|
| Nodo origen | `simulador1` — 192.168.0.103 |
| Ruta origen | `/opt/urbia/` |
| Fecha de copia | 2026-05-18 |
| Branch capturado | `develop` |
| Commit HEAD del bundle | `5b3ad88` (Sprint 3 — simulador Python funcional) |
| Commits incluidos | 4 (init Sprint 2 → Sprint 3 dupla `5b3ad88`/`9be65d2`) |
| Tamaño bundle | ~22 KB (`git-history.bundle`) |

El bundle se generó con `git bundle create git-history.bundle --all` antes
de mover los archivos, y se conserva para recuperar autoría, fechas y
mensajes de commit originales si se decide reescribir historia más
adelante.

---

## 3. Inventario de piezas valiosas

Cada entrada describe la pieza, su valor para el monorepo nuevo, y a dónde
debería migrar bajo la estructura definida en `CLAUDE.md §6`.

### 3.1 Contrato de datos AMI (compartido)

**`capa1/comun/payload_schema_v1.json`** · 2.1 KB · JSON Schema draft-07

Esquema de telemetría con 15 campos requeridos. Define:

- Regex de `device_id`: `^urbia-(cen|chi|ena|pal|pgr|uni)-(mon|tri)-[0-9]{4}$`.
- Enum de `zona` (6 zonas Manizales), `estado` (7 estados), `nodo_origen`
  (3 IPs), `lenguaje` (python/cpp/java), `device_type` (mono/trifasico).
- Rangos físicos: voltaje 187–253 V, corriente 0–60 A, potencia 0–30 kW,
  frecuencia 57–63 Hz, factor de potencia 0–1.
- Bounding box geográfico de Manizales: lat 5.03–5.12, lon −75.55 a −75.44.
- `additionalProperties: false` — los payloads no aceptan campos extra.

**Destino sugerido:** `libs/urbia-ami-protocol/schemas/payload_v1.json` (más
modelo Pydantic equivalente en `libs/urbia-ami-protocol/src/`). Es el
candidato natural a la primera librería compartida del monorepo y debería
versionarse explícitamente (`v1`, `v2`, …) antes del primer mensaje
publicado por el simulador nuevo.

### 3.2 Catálogo de medidores Manizales

**`capa1/comun/medidores_manizales.json`** · 39 KB · catálogo estático

150 medidores generados con `seed=42`, distribuidos así:

| Zona | Cantidad | Tipo | Nodo origen | Lenguaje |
|---|---:|---|---|---|
| centro | 25 | mono | 192.168.0.103 | python |
| chipre | 25 | mono | 192.168.0.103 | python |
| la_enea | 25 | trifasico | 192.168.0.104 | cpp |
| palermo | 25 | trifasico | 192.168.0.104 | cpp |
| palogrande | 30 | mono | 192.168.0.105 | java |
| universitario | 20 | trifasico | 192.168.0.105 | java |

Cada zona trae bbox propio. Cada medidor trae `device_id`, `device_type`,
`zona`, `lat`, `lon`, `nodo_origen`, `lenguaje`, `estado` inicial.

**Destino sugerido:** `data/topologies/manizales_pilot_v1.json` (datos
pequeños quedan en el repo según `CLAUDE.md §6`). Documentar la `seed=42`
como invariante reproducible — cualquier cambio implica `v2` y un ADR.

### 3.3 Validador de payloads

**`capa1/simuladores/python/src/payload_validator.py`** · 2.7 KB

Clase `PayloadValidator` con **tres capas de validación en cascada**:

1. **Schema JSON** vía `jsonschema.validate()`.
2. **Rangos técnicos:** voltaje (187–253 V), frecuencia (57–63 Hz) y
   **coherencia energética** — `|P_declarada − V·I·fp| / P_calc ≤ 20%`.
3. **Timestamp:** `timestamp_utc` no puede estar más de 60 s en el futuro.

Contadores integrados (`validos_total`, `errores_total`) y método
`estadisticas()` con `tasa_exito_pct`.

**Destino sugerido:** `libs/urbia-ami-protocol/src/validator.py`. Vale la
pena conservar la estructura de 3 capas; es una decisión correcta para AMI
y la coherencia V·I·fp es una salvaguarda específica del dominio que no
está en el schema JSON.

**Deuda a corregir en la migración:** el módulo tiene un anti-patrón al
inicio (`try: from jsonschema except ImportError: raise ImportError("pip
install --break-system-packages jsonschema")`). En el monorepo nuevo
`jsonschema` será dependencia declarada en `pyproject.toml`; la importación
debe ser directa y dejar que el error sea limpio (cf. `CLAUDE.md §8.1`).

### 3.4 Suite de tests del validador

**`capa1/simuladores/python/tests/test_payload_validator.py`** · 3.9 KB

13 tests pytest: 4 positivos (payload mono canónico, payload trifasico,
recorrido de los 7 estados, recorrido de las 6 zonas) + 9 negativos (campo
requerido faltante, regex de device_id, voltaje fuera de rango, frecuencia
fuera de rango, zona inválida, nodo_origen inválido, coordenadas fuera de
Manizales, `additionalProperties`, verificación de contadores).

**Destino sugerido:** `libs/urbia-ami-protocol/tests/test_validator.py`.
Cumple `CLAUDE.md §8.2` (nombres descriptivos, no dependen de orden, no
requieren red). La coverage que aporta es directamente reutilizable como
piso para la meta de 90 % en `libs/`.

### 3.5 Simulador Python — sensor base + monofásico

**`capa1/simuladores/python/src/sensor_base.py`** · 3.3 KB
**`capa1/simuladores/python/src/sensor_monofasico.py`** · 1.8 KB

- `SensorBase` (ABC): carga del catálogo, RNG por seed (`np.random.default_rng`),
  `generar_lectura()` que produce el payload completo conforme al schema,
  `_perfil_horario()` con factor de carga por franja horaria (0.15
  madrugada, 0.60 mañana, 0.85 mediodía, 0.65 tarde, 0.90 pico noche, 0.40
  noche tardía). Método abstracto `_generar_valores()`.
- `SensorMonofasico`: 220 V nominal, ±2 % ruido gaussiano, corriente
  hasta 20 A según factor horario, factor de potencia residencial 0.88–0.98,
  frecuencia 60 Hz ±0.15 Hz acotada a 59–61 Hz, estado probabilístico
  (98 % activo, 1 % anomalía_voltaje, 1 % falla).

**Destino sugerido:** `services/simulator-ami/src/sensors/`. El perfil
horario y el modelo eléctrico monofásico son el núcleo del simulador AMI
que el plan de la semana 1 nombra como E3. Se reescribe en lugar de
copiarse: nueva configuración con `pydantic-settings`, logging estructurado,
async para batching MQTT si se requiere.

**Faltante esperado:** no existe `SensorTrifasico`. El snapshot sólo
cubre el nodo 103 (50 medidores monofásicos). Trifásico es del nodo .104
(cpp) y queda fuera del scope Python.

### 3.6 Publicador MQTT

**`capa1/simuladores/python/src/mqtt_publisher.py`** · 2.4 KB

`MQTTPublisher` sobre `paho-mqtt 2.1.0` con `CallbackAPIVersion.VERSION2`,
QoS=1, `clean_session=False`, callbacks de conexión / desconexión /
publish, reconexión vía `connect_async` + `loop_start`, contadores
`publicados` y `errores`.

**Destino sugerido:** `services/simulator-ami/src/mqtt.py` o, si va a usarse
también desde `services/mqtt-bridge/`, mover a `libs/urbia-mqtt-client/`.
Recomendación: dejarlo en el simulador por ahora; promoverlo a `libs/` sólo
cuando un segundo consumidor lo necesite (regla de los dos usuarios).

### 3.7 Orquestador del nodo (main)

**`capa1/simuladores/python/src/main.py`** · 3.1 KB

`main()` arma 50 sensores filtrando el catálogo por `nodo_origen`,
instancia el publicador, atrapa `SIGTERM`/`SIGINT`, ciclo `while running`
con `INTERVALO_SEG` configurable. Topic MQTT jerárquico:
`urbia/manizales/{zona}/{device_type}/{device_id}/telemetria`. Loggea
estadísticas cada 12 ciclos (≈ 1 minuto a 5 s).

**Destino sugerido:** `services/simulator-ami/src/main.py` o reemplazarlo
por un `__main__` que use FastAPI lifespans / `asyncio.run` para coherencia
con el resto del stack. La jerarquía de topic MQTT es buena y se conserva
tal cual; documentarla en `services/simulator-ami/SCHEMA.md`.

### 3.8 Stack Docker del simulador

**`capa1/simuladores/python/Dockerfile`** · `python:3.12-slim`
**`capa1/simuladores/python/docker-compose.yml`** · servicio `simulator-python`
**`capa1/simuladores/python/requirements.txt`** · 13 dependencias pinneadas

Healthcheck simple (`python3 -c "import paho.mqtt.client"`), red externa
`urbia-sim`, restart `unless-stopped`, montaje de logs `./logs:/app/logs`.

**Destino sugerido:** `services/simulator-ami/Dockerfile` y servicio
nuevo en el `docker-compose.yml` raíz del monorepo. El simulador deja de
ser stack independiente y entra al compose unificado del cluster .102.

**Deuda a corregir:**

- **Hardcoding de IPs y NODE_ID** en `ENV` del Dockerfile y en el
  `docker-compose.yml` (`BROKER_HOST=192.168.0.101`, `NODE_ID=192.168.0.103`).
  Viola `CLAUDE.md §8.4`. En .102 todos los parámetros deben venir del
  `.env` raíz, sin defaults sensibles en el Dockerfile.
- **`context: /opt/urbia`** en el compose original asume el layout de
  .103; debe pasar a ruta relativa al monorepo (`context: .`).

### 3.9 Documentación arquitectónica del Sprint 2

**`docs/sprint2_nodo103.md`** · 5.0 KB

Documento de cierre del Sprint 2 con tabla de campos del schema, distribución
de medidores por zona/nodo/lenguaje, descripción de las 3 capas del
validador, listado de los 13 tests con su propósito, y notas sobre
`device_id` corto (`mon`) vs `device_type` largo (`mono`), tolerancia 20 %
en coherencia energética, y resolución de `COMUN_DIR`.

**Destino sugerido:** `docs/architecture/ami-protocol-v1.md` (reescrito
para no depender de la organización por sprints / nodos del legacy). Es la
mejor fuente para escribir la sección AMI de la tesis y los `SCHEMA.md`
del backend y simulador nuevos.

### 3.10 README arquitectónico raíz

**`README.md`** del snapshot · 0.6 KB

Tabla de nodos del cluster (.100 al .105 con IP y rol). El mapeo es
**obsoleto** respecto al actual `CLAUDE.md` (los roles cambiaron: .101 es
broker MQTT, .102 es cerebro, .105 cambió de "Sensores Java" a auditoría
Kali). Valor sólo como evidencia histórica.

**Destino sugerido:** no migrar. Conservar en `legacy/` para trazabilidad,
pero el README del monorepo nuevo refleja el cluster correcto.

### 3.11 Bundle git histórico

**`git-history.bundle`** · 22 KB · 4 commits

Permite reconstruir autoría/fechas/mensajes originales (`init`, Sprint 2
`c733633`, Sprint 3 `9be65d2` y `5b3ad88`). Verificado limpio de
secretos. Útil para citar evidencia temporal en la tesis (cuándo se
escribió cada pieza).

**Destino sugerido:** quedarse aquí mismo en `legacy/urbia-platform/`. No
mezclar con la historia de `urbIA-unal`.

---

## 4. Resumen de mapeo legacy → monorepo

| Legacy (snapshot) | Destino propuesto en `urbIA-unal/` |
|---|---|
| `capa1/comun/payload_schema_v1.json` | `libs/urbia-ami-protocol/schemas/payload_v1.json` |
| `capa1/comun/medidores_manizales.json` | `data/topologies/manizales_pilot_v1.json` |
| `capa1/simuladores/python/src/payload_validator.py` | `libs/urbia-ami-protocol/src/validator.py` |
| `capa1/simuladores/python/tests/test_payload_validator.py` | `libs/urbia-ami-protocol/tests/test_validator.py` |
| `capa1/simuladores/python/src/sensor_base.py` | `services/simulator-ami/src/sensors/base.py` |
| `capa1/simuladores/python/src/sensor_monofasico.py` | `services/simulator-ami/src/sensors/monofasico.py` |
| `capa1/simuladores/python/src/mqtt_publisher.py` | `services/simulator-ami/src/mqtt.py` |
| `capa1/simuladores/python/src/main.py` | `services/simulator-ami/src/main.py` |
| `capa1/simuladores/python/Dockerfile` | `services/simulator-ami/Dockerfile` |
| `capa1/simuladores/python/docker-compose.yml` | fusionado en `docker-compose.yml` raíz |
| `docs/sprint2_nodo103.md` | `docs/architecture/ami-protocol-v1.md` (reescrito) |
| `README.md` | no migrar (obsoleto, conservar en `legacy/` por trazabilidad) |
| `git-history.bundle` | permanece aquí |

---

## 5. Deuda heredada conocida

Antes de cualquier copia mecánica al monorepo, resolver:

1. **Hardcoding de IPs y `NODE_ID`** en Dockerfile/compose — pasar a `.env`.
2. **`pip install --break-system-packages` como mensaje de ImportError** en
   `payload_validator.py` — eliminar al pinnear `jsonschema` en
   `pyproject.toml`.
3. **`context: /opt/urbia`** en el compose legacy — pasar a path relativo.
4. **`requirements.txt`** pinea versiones inalcanzables al momento de la
   migración (`numpy==2.4.4`, `pytest==9.0.3`, `attrs==26.1.0`). Resolver
   con un `pyproject.toml` nuevo y dejar `pip-compile` regenerar el lock.
5. **Ausencia de `SensorTrifasico`** — confirmado, queda fuera de scope
   Python; la implementación trifásica la harán .104 (cpp) y .105 (java)
   en su momento. El monorepo Python sólo expone `SensorMonofasico`.
6. **`device_id` regex usa código corto `mon`**, pero `device_type` usa
   forma larga `mono`. Es intencional según el sprint2 doc, pero
   documentarlo explícitamente en `libs/urbia-ami-protocol/README.md` para
   evitar reportes de bug futuros.

---

*Documento generado el 2026-05-18 como parte del paso 3 de la migración
`urbia-platform` → `urbIA-unal`. Autor: Cristhiam Daniel Campos Julca.*
