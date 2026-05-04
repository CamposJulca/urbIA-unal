# UrbIA — Plan de implementación semana 1 (.102)

> Plan paso por paso para levantar el stack base de UrbIA en `innova-pruebas` (.102), desde bases de datos vacías hasta un dashboard funcional con telemetría AMI real fluyendo. Cada entregable tiene **criterios de aceptación verificables** y **pruebas mínimas** antes de avanzar al siguiente.
>
> Regla de oro: **no se pasa al siguiente entregable hasta que el actual pase todas sus pruebas.**

---

## Convenciones del documento

- Comandos prefijados con `[local]` se ejecutan en tu máquina local (`AsusCJ`).
- Comandos prefijados con `[.102]` se ejecutan en `innova-pruebas` por SSH.
- Comandos prefijados con `[.101]` se ejecutan en `innova-desarrollo` por SSH (broker MQTT).
- Bloques con `# ✅ CRITERIO` son criterios de aceptación obligatorios.
- Bloques con `# 🧪 TEST` son pruebas a ejecutar antes de declarar el paso completo.

---

## Pre-requisitos (ya cumplidos)

- [x] Repo `urbIA-unal` clonado en `~/urbIA-unal/` en .102
- [x] SSH key de .102 → GitHub funcionando
- [x] `git remote -v` apunta a `git@github.com:CamposJulca/urbIA-unal.git`
- [x] Docker 29.3.0 y Docker Compose v5.1.1 instalados
- [x] Python 3.12.3 instalado
- [x] Disco /var en .101 saneado (40%)
- [x] .102 con 309 GB libres y 13 GB RAM disponible

---

# E1 — Stack base: PostgreSQL + MongoDB + Redis + Adminer

**Objetivo:** levantar las cuatro bases de datos del proyecto en .102, con persistencia local, accesibles desde la red interna.

**Tiempo estimado:** 1-2 horas.

## E1.1 — Verificar puertos libres en .102

```bash
# [.102]
ss -tln | grep -E '5432|27017|6379|8080|8888|9000|9001'
```

```
# ✅ CRITERIO
# El comando NO debe devolver líneas en escucha (LISTEN) en esos puertos.
# Excepción: 9000-9001 ya están ocupados por minio_pruebas (eso lo manejamos aparte).
```

## E1.2 — Crear `.env` desde `.env.example`

```bash
# [.102]
cd ~/urbIA-unal
cp .env.example .env

# Generar passwords aleatorios
POSTGRES_PASS=$(openssl rand -base64 32 | tr -d '/+=' | head -c 24)
MONGO_PASS=$(openssl rand -base64 32 | tr -d '/+=' | head -c 24)
MINIO_PASS=$(openssl rand -base64 32 | tr -d '/+=' | head -c 24)

# Reemplazar 'changeme' en .env
sed -i "s|POSTGRES_PASSWORD=changeme|POSTGRES_PASSWORD=${POSTGRES_PASS}|" .env
sed -i "s|MONGO_PASSWORD=changeme|MONGO_PASSWORD=${MONGO_PASS}|" .env
sed -i "s|MINIO_SECRET_KEY=changeme|MINIO_SECRET_KEY=${MINIO_PASS}|" .env

# Verificar que .env NO se va a commitear (debe estar en .gitignore)
git check-ignore .env
```

```
# ✅ CRITERIO
# 'git check-ignore .env' debe devolver '.env' (significa que está ignorado).
# Si no devuelve nada, agregar '.env' a .gitignore antes de continuar.
```

## E1.3 — Escribir `docker-compose.yml`

Reemplaza el archivo vacío con:

```yaml
# docker-compose.yml — Stack base UrbIA en .102
services:

  postgres:
    image: postgres:16-alpine
    container_name: urbia-postgres
    restart: unless-stopped
    environment:
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    ports:
      - "${POSTGRES_PORT}:5432"
    volumes:
      - ./data-volumes/postgres:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - urbia

  mongo:
    image: mongo:7.0
    container_name: urbia-mongo
    restart: unless-stopped
    environment:
      MONGO_INITDB_ROOT_USERNAME: ${MONGO_USER}
      MONGO_INITDB_ROOT_PASSWORD: ${MONGO_PASSWORD}
      MONGO_INITDB_DATABASE: ${MONGO_DB}
    ports:
      - "${MONGO_PORT}:27017"
    volumes:
      - ./data-volumes/mongo:/data/db
    healthcheck:
      test: ["CMD", "mongosh", "--quiet", "--eval", "db.runCommand({ ping: 1 })"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - urbia

  redis:
    image: redis:7-alpine
    container_name: urbia-redis
    restart: unless-stopped
    ports:
      - "${REDIS_PORT}:6379"
    volumes:
      - ./data-volumes/redis:/data
    command: redis-server --appendonly yes
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - urbia

  adminer:
    image: adminer:latest
    container_name: urbia-adminer
    restart: unless-stopped
    ports:
      - "8080:8080"
    environment:
      ADMINER_DEFAULT_SERVER: postgres
    depends_on:
      postgres:
        condition: service_healthy
    networks:
      - urbia

  mongo-express:
    image: mongo-express:latest
    container_name: urbia-mongo-express
    restart: unless-stopped
    ports:
      - "8081:8081"
    environment:
      ME_CONFIG_MONGODB_ADMINUSERNAME: ${MONGO_USER}
      ME_CONFIG_MONGODB_ADMINPASSWORD: ${MONGO_PASSWORD}
      ME_CONFIG_MONGODB_URL: mongodb://${MONGO_USER}:${MONGO_PASSWORD}@mongo:27017/
      ME_CONFIG_BASICAUTH: "false"
    depends_on:
      mongo:
        condition: service_healthy
    networks:
      - urbia

networks:
  urbia:
    name: urbia-network
    driver: bridge
```

Y la versión de `.gitignore` debe incluir:
```
data-volumes/
.env
```

## E1.4 — Crear estructura de volúmenes

```bash
# [.102]
cd ~/urbIA-unal
mkdir -p data-volumes/postgres data-volumes/mongo data-volumes/redis
chmod 700 data-volumes/
```

## E1.5 — Levantar el stack

```bash
# [.102]
cd ~/urbIA-unal

# Validar la sintaxis del compose
docker compose config

# Levantar (descarga imágenes si no las tiene)
docker compose up -d

# Esperar 30 segundos para que healthchecks corran
sleep 30

# Estado
docker compose ps
```

```
# ✅ CRITERIO
# 'docker compose ps' debe mostrar 5 servicios:
#   - urbia-postgres        STATUS=Up (healthy)
#   - urbia-mongo           STATUS=Up (healthy)
#   - urbia-redis           STATUS=Up (healthy)
#   - urbia-adminer         STATUS=Up
#   - urbia-mongo-express   STATUS=Up
```

## E1.6 — Pruebas unitarias del stack

```bash
# [.102]

# 🧪 TEST 1 — Conectar a PostgreSQL
docker exec urbia-postgres psql -U ${POSTGRES_USER:-urbia} -d ${POSTGRES_DB:-urbia} -c "SELECT version();"

# 🧪 TEST 2 — Crear tabla de prueba en PostgreSQL
docker exec urbia-postgres psql -U urbia -d urbia -c "
CREATE TABLE IF NOT EXISTS urbia_health_check (
  id SERIAL PRIMARY KEY,
  message TEXT,
  created_at TIMESTAMP DEFAULT NOW()
);
INSERT INTO urbia_health_check (message) VALUES ('hola desde postgres');
SELECT * FROM urbia_health_check;
"

# 🧪 TEST 3 — Conectar a MongoDB
docker exec urbia-mongo mongosh -u ${MONGO_USER:-urbia} -p ${MONGO_PASSWORD} --quiet --eval "
db = db.getSiblingDB('urbia_telemetry');
db.health_check.insertOne({message: 'hola desde mongo', timestamp: new Date()});
db.health_check.find().pretty();
"

# 🧪 TEST 4 — Conectar a Redis
docker exec urbia-redis redis-cli SET urbia:test "hola desde redis"
docker exec urbia-redis redis-cli GET urbia:test
docker exec urbia-redis redis-cli DEL urbia:test

# 🧪 TEST 5 — Verificar persistencia
docker exec urbia-postgres ls -lah /var/lib/postgresql/data/ | head -5
ls -lah ~/urbIA-unal/data-volumes/postgres/ | head -5
```

```
# ✅ CRITERIO
# - TEST 1 imprime 'PostgreSQL 16.x'
# - TEST 2 crea tabla, inserta y devuelve 1 fila con 'hola desde postgres'
# - TEST 3 inserta en mongo y devuelve documento con 'hola desde mongo'
# - TEST 4 SET → GET devuelve "hola desde redis"
# - TEST 5 muestra archivos en data-volumes/postgres/ (persistencia OK)
```

## E1.7 — Validación visual

Abre en tu navegador (desde tu máquina local, .102 está en LAN):

- **Adminer:** http://192.168.0.102:8080
  - System: PostgreSQL
  - Server: postgres
  - Username: urbia
  - Password: el de tu .env
  - Database: urbia
  - Debe entrar y mostrar la tabla `urbia_health_check` con tu registro de prueba.

- **Mongo Express:** http://192.168.0.102:8081
  - Debe mostrar la base `urbia_telemetry` con la colección `health_check`.

```
# ✅ CRITERIO E1
# - Las 5 pruebas unitarias pasan.
# - Adminer muestra la tabla de prueba.
# - Mongo Express muestra el documento de prueba.
# - Si reinicias los contenedores con 'docker compose restart', los datos siguen ahí.
```

## E1.8 — Commit y push

```bash
# [.102]
cd ~/urbIA-unal

# Limpiar tabla de prueba (opcional, para empezar limpio)
docker exec urbia-postgres psql -U urbia -d urbia -c "DROP TABLE urbia_health_check;"

# Commit
git add docker-compose.yml .gitignore
git commit -m "feat(infra): stack base PostgreSQL + MongoDB + Redis + Adminer"
git push origin main
```

---

# E2 — Conectividad MQTT desde .102 hacia .101

**Objetivo:** confirmar que .102 puede publicar y suscribirse al broker MQTT de .101.

**Tiempo estimado:** 30 minutos.

## E2.1 — Instalar mosquitto-clients en .102

```bash
# [.102]
sudo apt update
sudo apt install -y mosquitto-clients

mosquitto_sub --help | head -3
```

## E2.2 — Verificar que el broker en .101 está accesible

```bash
# [.102]
nc -zv 192.168.0.101 1883
```

```
# ✅ CRITERIO
# Debe responder: "Connection to 192.168.0.101 1883 port [tcp/*] succeeded!"
# Si dice 'Connection refused' o 'No route to host', hay que revisar el broker en .101.
```

## E2.3 — Inspeccionar configuración del broker

```bash
# [.101]
ssh desarrollo@4.tcp.ngrok.io -p 16657

# Ver puerto y configuración del broker
docker ps | grep mqtt
docker exec urbia-mqtt cat /mosquitto/config/mosquitto.conf 2>/dev/null || \
  docker inspect urbia-mqtt | grep -A 5 Mounts

# Ver si requiere autenticación
docker logs urbia-mqtt 2>&1 | tail -20
```

```
# ✅ CRITERIO
# Identificar:
# - Si requiere autenticación (allow_anonymous true/false)
# - Qué topics están en uso actualmente
```

## E2.4 — Prueba publish/subscribe básico

Abre dos terminales en .102.

**Terminal A** (suscriptor):
```bash
# [.102]
mosquitto_sub -h 192.168.0.101 -p 1883 -t 'urbia/test/#' -v
```

**Terminal B** (publicador):
```bash
# [.102]
mosquitto_pub -h 192.168.0.101 -p 1883 -t 'urbia/test/hello' -m "primer mensaje desde .102"

# Publicar varios mensajes
for i in 1 2 3; do
  mosquitto_pub -h 192.168.0.101 -p 1883 -t "urbia/test/counter" -m "$i"
  sleep 1
done
```

```
# 🧪 TEST E2
# La Terminal A debe imprimir:
#   urbia/test/hello primer mensaje desde .102
#   urbia/test/counter 1
#   urbia/test/counter 2
#   urbia/test/counter 3
```

```
# ✅ CRITERIO E2
# Mensajes publicados desde .102 son recibidos por suscriptor en .102 vía broker en .101.
# Esto confirma que el flujo .102 → .101 → .102 funciona.
```

---

# E3 — Simulador AMI mínimo

**Objetivo:** un servicio Python que simula 10 medidores AMI urbanos publicando telemetría a MQTT cada segundo.

**Tiempo estimado:** 4-6 horas.

> **Nota:** este es el primer servicio donde Codex puede ayudar significativamente. Al final del documento hay un prompt listo para Codex.

## E3.1 — Schema de telemetría AMI

Antes de codificar, definir el formato del mensaje. Crear archivo `services/simulator-ami/SCHEMA.md`:

```markdown
# Schema de mensajes AMI — UrbIA v1.0

## Topic
`urbia/ami/{meter_id}/telemetry`

## Payload (JSON)
```json
{
  "meter_id": "AMI-MNZ-00001",
  "timestamp": "2026-05-02T03:00:00.000Z",
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

## Campos
| Campo | Tipo | Rango/Formato | Descripción |
|---|---|---|---|
| meter_id | string | `AMI-MNZ-NNNNN` | Identificador único del medidor |
| timestamp | ISO 8601 | UTC | Momento de la medición |
| voltage_v | float | 100.0 – 130.0 | Voltaje RMS en voltios |
| current_a | float | 0.0 – 50.0 | Corriente RMS en amperios |
| power_kw | float | 0.0 – 6.0 | Potencia activa en kW |
| energy_kwh | float | acumulado | Energía consumida acumulada |
| frequency_hz | float | 59.5 – 60.5 | Frecuencia en Hz |
| power_factor | float | 0.0 – 1.0 | Factor de potencia |
| zone | string | enum | Zona urbana de Manizales |
| status | string | NORMAL/WARNING/ALARM | Estado del medidor |
```

## E3.2 — Estructura del servicio

```bash
# [.102]
cd ~/urbIA-unal/services/simulator-ami

# Crear estructura
mkdir -p src/urbia_simulator tests

# Archivos a crear:
# - pyproject.toml
# - src/urbia_simulator/__init__.py
# - src/urbia_simulator/config.py
# - src/urbia_simulator/meter.py
# - src/urbia_simulator/main.py
# - tests/test_meter.py
# - Dockerfile
```

(El contenido de cada archivo se genera con Codex — ver prompt al final.)

## E3.3 — Pruebas unitarias del simulador

```bash
# [.102]
cd ~/urbIA-unal/services/simulator-ami

# Crear venv para tests locales
python3 -m venv .venv
source .venv/bin/activate
pip install -e . pytest

# Correr tests
pytest tests/ -v
```

```
# ✅ CRITERIO E3.3
# pytest debe pasar mínimo:
# - test_meter_generates_valid_voltage      (100.0 ≤ V ≤ 130.0)
# - test_meter_generates_valid_current      (0.0 ≤ A ≤ 50.0)
# - test_meter_generates_valid_frequency    (59.5 ≤ Hz ≤ 60.5)
# - test_payload_matches_schema             (todos los campos presentes)
# - test_energy_kwh_is_monotonic            (energía solo aumenta)
# - test_meter_id_format                    (regex AMI-MNZ-\d{5})
```

## E3.4 — Construcción y despliegue

```bash
# [.102]
cd ~/urbIA-unal

# Agregar el simulador al docker-compose.yml (ver E3.5)
# Build
docker compose build simulator-ami

# Levantar solo el simulador (con verbose logs)
docker compose up -d simulator-ami
docker compose logs -f simulator-ami | head -50
```

## E3.5 — Extensión del docker-compose.yml

Agregar al `docker-compose.yml` (en la sección `services:`):

```yaml
  simulator-ami:
    build:
      context: ./services/simulator-ami
      dockerfile: Dockerfile
    container_name: urbia-simulator-ami
    restart: unless-stopped
    environment:
      MQTT_HOST: ${MQTT_HOST}
      MQTT_PORT: ${MQTT_PORT}
      MQTT_USERNAME: ${MQTT_USERNAME}
      MQTT_PASSWORD: ${MQTT_PASSWORD}
      SIMULATOR_NUM_METERS: 10
      SIMULATOR_PUBLISH_RATE_HZ: 1
      LOG_LEVEL: INFO
    networks:
      - urbia
    depends_on:
      - postgres
```

## E3.6 — Validación end-to-end

```bash
# [.102]
# Suscribirse a la telemetría que el simulador está publicando
mosquitto_sub -h 192.168.0.101 -p 1883 -t 'urbia/ami/+/telemetry' -v | head -30
```

```
# 🧪 TEST E3.6
# Debe ver 10 medidores publicando ~1 mensaje/segundo cada uno.
# Cada mensaje debe ser JSON válido con los 9 campos del schema.
```

```bash
# Validar formato JSON con jq
mosquitto_sub -h 192.168.0.101 -p 1883 -t 'urbia/ami/+/telemetry' -C 5 | \
  while read line; do
    echo "$line" | jq -e '.meter_id and .voltage_v and .timestamp' > /dev/null \
      && echo "✓ Mensaje válido" || echo "✗ Mensaje inválido"
  done
```

```
# ✅ CRITERIO E3
# - 10 medidores publicando a tasa estable (1Hz por defecto).
# - 100% de los mensajes son JSON válidos.
# - Todos los campos del schema están presentes.
# - Los valores caen dentro de los rangos esperados.
# - El simulador soporta reinicio sin pérdida de meter_id (mantiene IDs).
```

## E3.7 — Commit

```bash
# [.102]
cd ~/urbIA-unal
git add services/simulator-ami docker-compose.yml
git commit -m "feat(simulator-ami): simulador AMI mínimo con 10 medidores y schema DLMS-JSON"
git push origin main
```

---

# E4 — Backend que persiste telemetría

**Objetivo:** un servicio FastAPI que (a) consume MQTT, (b) persiste cada mensaje a PostgreSQL, (c) expone endpoints REST básicos.

**Tiempo estimado:** 4-6 horas.

## E4.1 — Schema de la base de datos

Crear `services/backend/migrations/001_initial.sql`:

```sql
-- Tabla principal de telemetría AMI
CREATE TABLE IF NOT EXISTS ami_telemetry (
    id BIGSERIAL PRIMARY KEY,
    meter_id VARCHAR(20) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    voltage_v REAL NOT NULL,
    current_a REAL NOT NULL,
    power_kw REAL NOT NULL,
    energy_kwh REAL NOT NULL,
    frequency_hz REAL NOT NULL,
    power_factor REAL NOT NULL,
    zone VARCHAR(50),
    status VARCHAR(20),
    received_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_ami_telemetry_meter_id ON ami_telemetry(meter_id);
CREATE INDEX idx_ami_telemetry_timestamp ON ami_telemetry(timestamp DESC);
CREATE INDEX idx_ami_telemetry_received_at ON ami_telemetry(received_at DESC);

-- Tabla de metadatos de medidores
CREATE TABLE IF NOT EXISTS ami_meters (
    meter_id VARCHAR(20) PRIMARY KEY,
    zone VARCHAR(50),
    installed_at TIMESTAMPTZ DEFAULT NOW(),
    last_seen TIMESTAMPTZ,
    is_active BOOLEAN DEFAULT TRUE
);
```

## E4.2 — Aplicar migración

```bash
# [.102]
cd ~/urbIA-unal
docker exec -i urbia-postgres psql -U urbia -d urbia < services/backend/migrations/001_initial.sql

# Verificar
docker exec urbia-postgres psql -U urbia -d urbia -c "\dt"
```

```
# ✅ CRITERIO E4.2
# El comando '\dt' debe listar:
#   ami_meters
#   ami_telemetry
```

## E4.3 — Estructura del backend

```bash
# [.102]
cd ~/urbIA-unal/services/backend

mkdir -p src/urbia_backend tests migrations

# Archivos a crear (con ayuda de Codex):
# - pyproject.toml          dependencias: fastapi, uvicorn, asyncpg, paho-mqtt, pydantic
# - src/urbia_backend/__init__.py
# - src/urbia_backend/config.py
# - src/urbia_backend/models.py             (Pydantic models)
# - src/urbia_backend/db.py                 (asyncpg pool)
# - src/urbia_backend/mqtt_consumer.py      (consumidor MQTT)
# - src/urbia_backend/api/telemetry.py      (endpoints REST)
# - src/urbia_backend/main.py               (entry point FastAPI)
# - tests/test_models.py
# - tests/test_api.py
# - Dockerfile
```

## E4.4 — Endpoints mínimos

| Método | Path | Descripción |
|---|---|---|
| `GET` | `/health` | Health check (200 si DB y MQTT OK) |
| `GET` | `/meters` | Lista de medidores activos |
| `GET` | `/meters/{meter_id}/telemetry/latest` | Último mensaje de un medidor |
| `GET` | `/meters/{meter_id}/telemetry?limit=100` | Histórico de un medidor |
| `GET` | `/telemetry/recent?limit=100` | Últimos N mensajes globales |

## E4.5 — Pruebas del backend

```bash
# [.102]
cd ~/urbIA-unal/services/backend

# Tests unitarios (con DB de prueba)
pytest tests/ -v

# Tests de integración (con stack levantado)
docker compose up -d backend
sleep 10

# 🧪 TEST E4.5.1 — Health check
curl -s http://localhost:8000/health | jq

# 🧪 TEST E4.5.2 — Lista de medidores (debe haber 10 si el simulador corre)
curl -s http://localhost:8000/meters | jq 'length'

# 🧪 TEST E4.5.3 — Telemetría reciente
curl -s "http://localhost:8000/telemetry/recent?limit=5" | jq

# 🧪 TEST E4.5.4 — Telemetría de un medidor
curl -s http://localhost:8000/meters/AMI-MNZ-00001/telemetry/latest | jq
```

```
# ✅ CRITERIO E4
# - GET /health devuelve 200 con {"status": "ok", "db": true, "mqtt": true}
# - GET /meters devuelve un array con 10 elementos
# - GET /telemetry/recent devuelve los últimos 5 mensajes con todos los campos
# - GET /meters/{id}/telemetry/latest devuelve el último mensaje del medidor
# - La base PostgreSQL crece a un ritmo aproximado de 10 filas/segundo
```

## E4.6 — Validación con Adminer

Abrir http://192.168.0.102:8080 y verificar:

- Tabla `ami_telemetry` debe tener miles de filas (depende del tiempo de ejecución).
- Tabla `ami_meters` debe tener 10 filas.
- Las consultas SQL desde Adminer responden rápido (< 100 ms).

## E4.7 — Commit

```bash
# [.102]
git add services/backend docker-compose.yml
git commit -m "feat(backend): FastAPI con consumer MQTT y endpoints REST de telemetría"
git push origin main
```

---

# E5 — Frontend Streamlit con telemetría real

**Objetivo:** dashboard visual con datos AMI reales fluyendo en tiempo real.

**Tiempo estimado:** 2-3 horas.

## E5.1 — Estructura del frontend

```bash
# [.102]
cd ~/urbIA-unal/services/frontend

mkdir -p src/urbia_frontend pages

# Archivos:
# - pyproject.toml        dependencias: streamlit, requests, pandas, plotly
# - src/urbia_frontend/main.py
# - src/urbia_frontend/api_client.py
# - pages/01_Overview.py
# - pages/02_Meters.py
# - pages/03_Live.py
# - Dockerfile
```

## E5.2 — Páginas del dashboard

**Página 1 — Overview:**
- Total de medidores activos
- Mensajes recibidos en última hora
- Promedio de potencia consumida actual
- Mapa de zonas (si hay coordenadas, opcional)

**Página 2 — Meters:**
- Tabla con todos los medidores
- Click en un medidor → drill-down a su histórico

**Página 3 — Live:**
- Stream en tiempo real (refresca cada 2 segundos)
- Gráfico de voltaje, corriente, potencia para los últimos 5 minutos

## E5.3 — Extensión del docker-compose.yml

```yaml
  frontend:
    build:
      context: ./services/frontend
      dockerfile: Dockerfile
    container_name: urbia-frontend
    restart: unless-stopped
    environment:
      BACKEND_URL: http://backend:8000
    ports:
      - "8501:8501"
    depends_on:
      - backend
    networks:
      - urbia
```

## E5.4 — Validación visual

```bash
# [.102]
docker compose up -d frontend
docker compose logs -f frontend | head -30
```

Abrir en navegador desde tu máquina local:

**http://192.168.0.102:8501**

```
# 🧪 TEST E5
# - La página carga en menos de 5 segundos.
# - El "Overview" muestra 10 medidores activos.
# - El stream "Live" muestra datos actualizándose cada 1-2 segundos.
# - Las gráficas se renderizan correctamente.
# - Los valores caen dentro de los rangos del schema (V: 100-130, A: 0-50, etc.).
```

```
# ✅ CRITERIO E5
# - Dashboard accesible en http://192.168.0.102:8501
# - Datos reales fluyendo desde simulador → MQTT → backend → DB → frontend
# - Sin errores en logs de docker compose
# - Refresco automático funciona
```

## E5.5 — Commit final de la semana

```bash
# [.102]
git add services/frontend docker-compose.yml
git commit -m "feat(frontend): dashboard Streamlit con telemetría AMI en tiempo real"
git push origin main

# Tag de la primera release
git tag -a v0.1.0 -m "v0.1.0 — stack base UrbIA con telemetría AMI end-to-end"
git push origin v0.1.0
```

---

# Estado al cierre de la semana 1

```
┌──────────────────────────────────────────────────────────────────┐
│                                                                  │
│       Simulador AMI ──► MQTT (.101) ──► Backend (.102) ──┐       │
│                                                          │       │
│                                                          ▼       │
│                                                     PostgreSQL   │
│                                                     MongoDB      │
│                                                     Redis        │
│                                                          │       │
│                                                          ▼       │
│                                                     Frontend     │
│                                                     (Streamlit)  │
│                                                          │       │
│                                                          ▼       │
│                                              http://.102:8501    │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

**Lo que tienes al final:**
- Stack base con bases de datos persistentes.
- Simulador de 10 medidores AMI funcionando 24/7.
- Backend FastAPI consumiendo MQTT y persistiendo a PostgreSQL.
- Dashboard visual mostrando datos reales en tiempo real.
- Repo en GitHub con 5 commits funcionales.
- Tag `v0.1.0` listo para mostrar a Osorio.

**Lo que NO tienes todavía** (semanas siguientes):
- Monitor GSP — el núcleo doctoral. Empieza en semana 2.
- Controlador SDN modificado.
- Generador de tráfico hostil.
- Análisis estadístico de los datos.

---

# Anexo: prompt para Codex (cuando llegue E3)

> Cuando estés listo para implementar el simulador AMI con ayuda de Codex, abre un chat con el siguiente prompt. Asegúrate de pegarle también `services/simulator-ami/SCHEMA.md` para que tenga el schema.

```
Eres ingeniero de software senior. Vas a implementar el servicio
'simulator-ami' en el monorepo UrbIA-UNAL.

CONTEXTO:
- Repo: github.com/CamposJulca/urbIA-unal (clonado en .102)
- Lenguaje: Python 3.12
- Framework: ninguno (script standalone con paho-mqtt)
- Stack: el simulador publica a un broker MQTT externo
- Schema de mensajes: ver services/simulator-ami/SCHEMA.md

TAREA:
Implementar los siguientes archivos en services/simulator-ami/:

1. pyproject.toml
   - dependencias: paho-mqtt, pydantic, python-dotenv
   - dev-dependencies: pytest, pytest-mock
   - entry point: 'urbia-simulator = urbia_simulator.main:main'

2. src/urbia_simulator/config.py
   - Cargar configuración desde variables de entorno con pydantic Settings
   - Variables: MQTT_HOST, MQTT_PORT, MQTT_USERNAME, MQTT_PASSWORD,
     SIMULATOR_NUM_METERS, SIMULATOR_PUBLISH_RATE_HZ, LOG_LEVEL

3. src/urbia_simulator/meter.py
   - Clase Meter que mantiene estado de un medidor virtual
   - Método generate_reading() que produce un dict con el schema
   - Energía acumulada (energy_kwh) que solo aumenta en el tiempo
   - Voltaje, corriente, frecuencia con jitter realista alrededor de valores nominales
   - meter_id formato 'AMI-MNZ-NNNNN'

4. src/urbia_simulator/main.py
   - Conecta a MQTT broker
   - Crea N medidores
   - Loop principal que publica cada medidor a tasa configurable
   - Manejo de Ctrl+C limpio
   - Logging estructurado

5. tests/test_meter.py
   Tests obligatorios:
   - test_meter_generates_valid_voltage
   - test_meter_generates_valid_current
   - test_meter_generates_valid_frequency
   - test_payload_matches_schema
   - test_energy_kwh_is_monotonic
   - test_meter_id_format

6. Dockerfile
   - Multi-stage build
   - Imagen base: python:3.12-slim
   - Usuario no-root
   - HEALTHCHECK que verifica que el proceso esté vivo

CRITERIOS DE ACEPTACIÓN:
- pytest tests/ pasa con coverage > 80%
- 'docker compose up simulator-ami' arranca sin error
- 'mosquitto_sub -h 192.168.0.101 -t "urbia/ami/+/telemetry"' muestra mensajes
- Mensajes son JSON válido con todos los campos del SCHEMA.md
- El servicio mantiene estado entre reinicios (mismos meter_ids)

DESPUÉS DE IMPLEMENTAR:
- Crear PR con descripción clara
- Incluir un README.md en services/simulator-ami/ con instrucciones
```

---

# Reglas de oro para toda la semana

1. **No avanzar al siguiente entregable hasta que el actual pase TODOS sus criterios.**
2. **Commit pequeños y frecuentes.** Mínimo 1 commit por entregable, idealmente 3-5.
3. **Si algo falla, NO improvises. Lee el error completo y pega salida acá.**
4. **Tests primero, código después.** Si un test no existe, ese código no se considera terminado.
5. **El `.env` jamás se commitea.** Verificar con `git status` antes de cada `git add`.
6. **Logs de containers se revisan SIEMPRE** después de levantar algo nuevo: `docker compose logs -f <servicio>`.
7. **Cuando dudes, pregúntame.** Es más rápido aclarar que reescribir.

---

*Plan operativo UrbIA — semana 1 de implementación. Versión 1.0.*