import { format, formatDistanceToNowStrict, parseISO } from 'date-fns';
import { es } from 'date-fns/locale';

/**
 * Antiguedad (en segundos) por encima de la cual una lectura deja de
 * considerarse en vivo. Definida aqui —y no en cada componente— para que
 * la barra de estado y la tabla de lecturas usen un unico criterio: si
 * divergen, el banner puede decir "historico" mientras la tabla presenta
 * horas sueltas como si fueran de hoy.
 */
export const STALE_THRESHOLD_S = 60;

/** Format numerico con `digits` decimales. */
export function formatNumber(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return value.toLocaleString('es-CO', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

/** "hace 3 s" / "hace 12 min" — fallback si timestamp es invalido. */
export function formatRelative(iso: string | null | undefined): string {
  if (!iso) return '—';
  try {
    const d = parseISO(iso);
    return `hace ${formatDistanceToNowStrict(d, { locale: es })}`;
  } catch {
    return '—';
  }
}

/** HH:MM:SS — para etiquetas del eje X del grafico y tabla. */
export function formatClock(iso: string): string {
  try {
    const d = parseISO(iso);
    return d.toLocaleTimeString('es-CO', { hour12: false });
  } catch {
    return iso;
  }
}

/**
 * "22 may 21:59:46" — variante con fecha de formatClock, para cuando el
 * lote mostrado no es del dia en curso y una hora suelta se leeria como
 * reciente.
 */
export function formatStampWithDate(iso: string): string {
  try {
    return format(parseISO(iso), 'd MMM HH:mm:ss', { locale: es });
  } catch {
    return iso;
  }
}

/** Antiguedad en segundos. Util para badges En vivo / Retraso / Sin senal. */
export function ageSeconds(iso: string | null | undefined): number | null {
  if (!iso) return null;
  try {
    return Math.max(0, (Date.now() - parseISO(iso).getTime()) / 1000);
  } catch {
    return null;
  }
}
