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

/**
 * Item de GET /meters (esquema `MeterInfo`).
 *
 * `meter_id` es el `device_id` del esquema v2 (`urbia-<zona>-<tipo>-NNNN`);
 * el backend lo expone con el nombre REST historico. `device_type`,
 * `lat`, `lon` y `nodo_origen` son campos v2 y viajan con su nombre de
 * columna: no tenian equivalente en ingles previo.
 */
export type MeterInfo = {
  meter_id: string;
  device_type: string | null;
  zone: string | null;
  lat: number | null;
  lon: number | null;
  nodo_origen: string | null;
  installed_at: string | null;
  last_seen: string | null;
  is_active: boolean;
};

/**
 * Item de GET /telemetry/recent y /meters/{id}/telemetry/latest.
 *
 * `energy_kwh` es nullable desde el esquema v2: el productor no reporta
 * energia acumulada en todos los mensajes. Todo consumidor debe tratar
 * el null (no encadenar `.toFixed()` sin guarda).
 */
export type TelemetryRecord = {
  id: number;
  meter_id: string;
  device_type: string | null;
  timestamp: string;
  voltage_v: number;
  current_a: number;
  power_kw: number;
  energy_kwh: number | null;
  frequency_hz: number;
  power_factor: number;
  zone: string | null;
  status: string | null;
  nodo_origen: string | null;
  lenguaje: string | null;
  seed: number | null;
  received_at: string;
};

/**
 * Zonas del esquema AMI v2 — slugs tal como llegan en la columna
 * `zona`, derivados del codigo de tres letras del `device_id`
 * (`cen`, `chi`, `ena`, `pal`, `pgr`, `uni`). Ver
 * `services/backend/SCHEMA.md` §3. El backend NO valida `zona` contra
 * este conjunto, asi que puede llegar una zona fuera de la lista:
 * `colorForZone`/`labelForZone` tienen fallback.
 */
export const KNOWN_ZONES = [
  'centro',
  'chipre',
  'la_enea',
  'palermo',
  'palogrande',
  'universitario',
] as const;

export type KnownZone = (typeof KNOWN_ZONES)[number];

/** Estado derivado del sistema, consumido por el Header. */
export type SystemHealthState = 'ok' | 'degraded' | 'down' | 'unknown';
