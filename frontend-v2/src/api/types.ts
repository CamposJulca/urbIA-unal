/**
 * Tipos TypeScript alineados 1:1 con el OpenAPI del backend FastAPI.
 * No renombrar campos: `voltage_v`, `current_a`, `power_kw` provienen
 * del backend y el frontend los respeta para evitar adaptadores.
 */

/** Respuesta de GET /health. */
export type HealthResponse = {
  status: string;
  db: boolean;
  mqtt: boolean;
};

/** Item de GET /meters (esquema `MeterInfo`). */
export type MeterInfo = {
  meter_id: string;
  zone: string | null;
  installed_at: string | null;
  last_seen: string | null;
  is_active: boolean;
};

/** Item de GET /telemetry/recent y /meters/{id}/telemetry/latest. */
export type TelemetryRecord = {
  id: number;
  meter_id: string;
  timestamp: string;
  voltage_v: number;
  current_a: number;
  power_kw: number;
  energy_kwh: number;
  frequency_hz: number;
  power_factor: number;
  zone: string | null;
  status: string | null;
  received_at: string;
};

/** Conjunto fijo de zonas observadas en el simulador AMI. */
export const KNOWN_ZONES = [
  'MNZ-CENTRO',
  'MNZ-NORTE',
  'MNZ-SUR',
  'MNZ-ESTE',
  'MNZ-OESTE',
] as const;

export type KnownZone = (typeof KNOWN_ZONES)[number];

/** Estado derivado del sistema, consumido por el Header. */
export type SystemHealthState = 'ok' | 'degraded' | 'down' | 'unknown';
