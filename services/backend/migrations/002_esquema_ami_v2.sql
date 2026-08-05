-- Migración 002 — Esquema AMI v2 (columnas en español).
--
-- Motivo: el productor real de telemetría dejó de ser
-- services/simulator-ami (obsoleto, ver su README) y pasó a ser el
-- productor externo que publica el esquema v2 en `urbia/manizales/#`.
-- El contrato de ingesta queda documentado en
-- services/backend/SCHEMA.md.
--
-- Cambios respecto de 001_initial.sql:
--   * Todas las columnas pasan a español (incluidas energia_kwh y
--     factor_potencia). Los nombres en inglés que ya consume el
--     frontend se preservan como alias en el SELECT del backend
--     (ver services/backend/src/urbia_backend/db.py), no en la tabla.
--   * meter_id VARCHAR(20) → device_id VARCHAR(32): el id nuevo es
--     `urbia-<zona>-<tipo>-NNNN` y no cabe en 20 caracteres.
--   * Columnas nuevas: device_type, nodo_origen, lenguaje, seed en
--     telemetría; device_type, lat, lon, nodo_origen en medidores.
--   * energia_kwh pasa a NULL: el productor v2 no siempre reporta
--     energía acumulada.
--   * Índices: un único compuesto (device_id, recibido_en DESC) para
--     las consultas por medidor, más el global por recibido_en DESC
--     que sostiene /telemetry/recent. Se eliminan el índice suelto de
--     device_id (redundante: es prefijo del compuesto) y el de
--     timestamp, que ninguna query usa hoy.
--
-- NO DESTRUCTIVA. Las tablas v1 se renombran a `ami_telemetry_v1` y
-- `ami_meters_v1` en vez de descartarse: sus filas (telemetría del
-- simulador obsoleto, con device_id y zonas que el esquema v2 ni
-- siquiera puede direccionar) no son migrables al esquema nuevo, pero
-- consultarlas cuesta segundos y restaurarlas desde un pg_dump no. El
-- backend v2 nunca las lee. Se borran a mano cuando el flujo nuevo
-- esté validado:
--   DROP TABLE ami_telemetry_v1;
--   DROP TABLE ami_meters_v1;
--
-- Ejecución única: un segundo `psql -f` falla en el primer ALTER
-- (`ami_telemetry` ya no existe) y aborta la transacción entera sin
-- dejar estado a medias.

BEGIN;

-- ----- v1 → sufijo _v1 (tablas, secuencia, PKs, índices) -----
-- Los nombres de PK, secuencia e índices son los que generó
-- 001_initial.sql. Renombrarlos evita colisión con los objetos que
-- crea esta misma migración y deja claro en \d que son legado.

ALTER TABLE ami_telemetry RENAME TO ami_telemetry_v1;
ALTER TABLE ami_meters    RENAME TO ami_meters_v1;

ALTER SEQUENCE ami_telemetry_id_seq RENAME TO ami_telemetry_v1_id_seq;

-- RENAME CONSTRAINT arrastra también el índice único que la respalda.
ALTER TABLE ami_telemetry_v1
    RENAME CONSTRAINT ami_telemetry_pkey TO ami_telemetry_v1_pkey;
ALTER TABLE ami_meters_v1
    RENAME CONSTRAINT ami_meters_pkey TO ami_meters_v1_pkey;

ALTER INDEX idx_ami_telemetry_meter_id
    RENAME TO idx_ami_telemetry_v1_meter_id;
ALTER INDEX idx_ami_telemetry_timestamp
    RENAME TO idx_ami_telemetry_v1_timestamp;
ALTER INDEX idx_ami_telemetry_received_at
    RENAME TO idx_ami_telemetry_v1_received_at;

-- ----- v2 -----

-- Tabla principal de telemetría AMI (esquema v2).
CREATE TABLE ami_telemetry (
    id              BIGSERIAL PRIMARY KEY,
    device_id       VARCHAR(32)  NOT NULL,
    device_type     VARCHAR(16),
    zona            VARCHAR(32),
    timestamp_utc   TIMESTAMPTZ  NOT NULL,
    voltaje_v       REAL         NOT NULL,
    corriente_a     REAL         NOT NULL,
    potencia_kw     REAL         NOT NULL,
    energia_kwh     REAL         NULL,
    frecuencia_hz   REAL         NOT NULL,
    factor_potencia REAL         NOT NULL,
    estado          VARCHAR(24),
    nodo_origen     VARCHAR(24),
    lenguaje        VARCHAR(8),
    seed            BIGINT,
    recibido_en     TIMESTAMPTZ  DEFAULT NOW()
);

-- Compuesto: cubre `WHERE device_id = $1 ORDER BY recibido_en DESC`
-- (latest_for_meter, history_for_meter) y hace redundante un índice
-- suelto sobre device_id, que es su prefijo.
CREATE INDEX idx_ami_telemetry_device_recibido
    ON ami_telemetry (device_id, recibido_en DESC);

-- Global: sostiene `ORDER BY recibido_en DESC LIMIT $1` de
-- /telemetry/recent, que el frontend consulta cada 2 s. El compuesto
-- no sirve para esta query porque no filtra por device_id.
CREATE INDEX idx_ami_telemetry_recibido_en
    ON ami_telemetry (recibido_en DESC);

-- Tabla de metadatos de medidores. El backend hace UPSERT con cada
-- mensaje recibido (actualiza visto_por_ultima_vez y, si es nuevo, lo
-- crea).
CREATE TABLE ami_meters (
    device_id            VARCHAR(32) PRIMARY KEY,
    device_type          VARCHAR(16),
    zona                 VARCHAR(32),
    lat                  DOUBLE PRECISION,
    lon                  DOUBLE PRECISION,
    nodo_origen          VARCHAR(24),
    instalado_en         TIMESTAMPTZ DEFAULT NOW(),
    visto_por_ultima_vez TIMESTAMPTZ,
    activo               BOOLEAN DEFAULT TRUE
);

COMMIT;
