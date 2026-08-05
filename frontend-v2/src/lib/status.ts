/**
 * Clasificacion visual del campo `estado` del esquema AMI v2 (columna
 * `estado`, expuesta como `status` en la API REST).
 *
 * El enum del productor tiene siete valores. Hoy solo emite tres
 * (`activo` ~98%, `anomalia_voltaje` ~1%, `falla` ~1%); los otros
 * cuatro no apareceran hasta que exista el inyector de eventos, pero se
 * declaran aqui para que el dia que lleguen ya tengan color y no caigan
 * en el camino del desconocido.
 *
 * Tres tramos:
 *  - verde  : `activo` — unico estado nominal.
 *  - ambar  : `mantenimiento` — fuera de servicio previsto, no es falla.
 *  - rojo   : los cinco restantes.
 *
 * Un valor fuera del enum se pinta rojo a proposito: si el productor
 * empieza a emitir algo que este frontend no conoce, es preferible un
 * falso rojo visible a un estado anomalo pintado de verde.
 */

export const METER_STATUS_OK = 'activo';

export const METER_STATUS_MAINTENANCE = 'mantenimiento';

export const METER_STATUS_FAULT = [
  'anomalia_voltaje',
  'anomalia_frecuencia',
  'falla',
  'corte',
  'desconectado',
] as const;

/** Enum completo del productor, en el orden en que lo declara. */
export const METER_STATUSES = [
  METER_STATUS_OK,
  METER_STATUS_MAINTENANCE,
  ...METER_STATUS_FAULT,
] as const;

export type MeterStatus = (typeof METER_STATUSES)[number];

export type StatusTone = 'success' | 'warning' | 'danger' | 'neutral';

/** Tono del badge/celda para un `status` del backend. */
export function statusTone(status: string | null | undefined): StatusTone {
  if (status === null || status === undefined) return 'neutral';
  if (status === METER_STATUS_OK) return 'success';
  if (status === METER_STATUS_MAINTENANCE) return 'warning';
  return 'danger';
}

/** Etiqueta legible: `anomalia_voltaje` → `anomalia voltaje`. */
export function statusLabel(status: string | null | undefined): string {
  if (status === null || status === undefined) return 'Sin clasificar';
  return status.replace(/_/g, ' ');
}
