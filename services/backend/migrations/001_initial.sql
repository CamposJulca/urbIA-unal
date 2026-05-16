-- Migración inicial del backend UrbIA — Entregable E4 (semana 1).
-- Crea las tablas que persisten la telemetría AMI publicada por
-- services/simulator-ami al broker MQTT .101 y los metadatos de
-- medidores. Schema fijado en plan-trabajo/semana1.md (E4.1) y
-- alineado con services/simulator-ami/SCHEMA.md (AMI-JSON v1.0).

-- Tabla principal de telemetría AMI.
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

-- Tabla de metadatos de medidores. El backend hace UPSERT con cada
-- mensaje recibido (actualiza last_seen y, si es nuevo, lo crea).
CREATE TABLE IF NOT EXISTS ami_meters (
    meter_id VARCHAR(20) PRIMARY KEY,
    zone VARCHAR(50),
    installed_at TIMESTAMPTZ DEFAULT NOW(),
    last_seen TIMESTAMPTZ,
    is_active BOOLEAN DEFAULT TRUE
);
