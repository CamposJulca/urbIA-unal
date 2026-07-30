import { memo } from 'react';
import {
  ageSeconds,
  formatClock,
  formatStampWithDate,
  STALE_THRESHOLD_S,
} from '@/lib/format';
import { colorForZone, labelForZone } from '@/lib/zones';
import type { TelemetryRecord } from '@/api/types';

/**
 * Tabla compacta con los ultimos 20 mensajes globales. Cabecera
 * sticky, scroll horizontal en pantallas estrechas, color sutil por
 * zona en el borde izquierdo de cada fila.
 *
 * Si el lote mostrado es historico (mas viejo que STALE_THRESHOLD_S), la
 * columna de tiempo incluye la fecha: una hora suelta sobre datos de
 * semanas atras se lee como si fuera de hoy.
 */
function RecentReadingsTableImpl({
  records,
}: {
  records: TelemetryRecord[];
}): JSX.Element {
  const rows = records.slice(0, 20);

  if (rows.length === 0) {
    return <div className="p-6 text-sm text-ink-muted">No hay lecturas para mostrar.</div>;
  }

  // PRECONDICION: `records` llega ordenado por timestamp descendente (lo
  // ordena Telemetry.tsx antes de pasarlo), asi que rows[0] es la lectura
  // mas reciente. Si alguien invierte ese orden, tomar el maximo aqui en
  // vez de rows[0]: con orden ascendente este indicador daria "historico"
  // permanentemente y volveriamos a mostrar horas sin fecha en vivo.
  const isStale = (ageSeconds(rows[0]!.timestamp) ?? 0) > STALE_THRESHOLD_S;

  return (
    <div className="max-h-[420px] overflow-auto">
      <table className="w-full min-w-[820px] text-sm">
        <thead className="sticky top-0 z-10 bg-neutral-50 text-left text-xs font-semibold uppercase tracking-wide text-ink-muted">
          <tr>
            <th className="px-4 py-2">{isStale ? 'Fecha y hora' : 'Hora'}</th>
            <th className="px-4 py-2">Medidor</th>
            <th className="px-4 py-2">Zona</th>
            <th className="px-4 py-2 text-right">V</th>
            <th className="px-4 py-2 text-right">A</th>
            <th className="px-4 py-2 text-right">kW</th>
            <th className="px-4 py-2 text-right">kWh</th>
            <th className="px-4 py-2 text-right">Hz</th>
            <th className="px-4 py-2 text-right">F. Pot.</th>
            <th className="px-4 py-2">Estado</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {rows.map((r) => {
            const zc = colorForZone(r.zone);
            return (
              <tr
                key={r.id}
                className="hover:bg-neutral-50"
                style={{ boxShadow: `inset 3px 0 0 ${zc}` }}
              >
                <td className="whitespace-nowrap px-4 py-2 font-mono text-xs text-ink-muted">
                  {isStale ? formatStampWithDate(r.timestamp) : formatClock(r.timestamp)}
                </td>
                <td className="whitespace-nowrap px-4 py-2 font-mono text-xs">{r.meter_id}</td>
                <td className="whitespace-nowrap px-4 py-2 text-xs">{labelForZone(r.zone)}</td>
                <td className="whitespace-nowrap px-4 py-2 text-right font-mono">
                  {r.voltage_v.toFixed(1)}
                </td>
                <td className="whitespace-nowrap px-4 py-2 text-right font-mono">
                  {r.current_a.toFixed(2)}
                </td>
                <td className="whitespace-nowrap px-4 py-2 text-right font-mono">
                  {r.power_kw.toFixed(2)}
                </td>
                <td className="whitespace-nowrap px-4 py-2 text-right font-mono">
                  {r.energy_kwh.toFixed(2)}
                </td>
                <td className="whitespace-nowrap px-4 py-2 text-right font-mono">
                  {r.frequency_hz.toFixed(2)}
                </td>
                <td className="whitespace-nowrap px-4 py-2 text-right font-mono">
                  {r.power_factor.toFixed(3)}
                </td>
                <td className="whitespace-nowrap px-4 py-2">
                  <span
                    className={
                      r.status === 'NORMAL'
                        ? 'text-success'
                        : r.status === null
                          ? 'text-ink-muted'
                          : 'text-danger font-semibold'
                    }
                  >
                    {r.status ?? '—'}
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export const RecentReadingsTable = memo(RecentReadingsTableImpl);
