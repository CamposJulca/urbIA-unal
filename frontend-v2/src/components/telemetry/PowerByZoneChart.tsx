import { memo, useMemo } from 'react';
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { KNOWN_ZONES, type TelemetryRecord } from '@/api/types';
import { ZONE_COLOR, labelForZone } from '@/lib/zones';

/**
 * Grafico de lineas con potencia agregada (kW) por zona en una
 * ventana deslizante de 60 segundos. Una serie por zona conocida.
 *
 * - Bucketing en intervalos de 2 s (coincide con el polling).
 * - X = HH:MM:SS; Y = kW agregado (sum de potencias).
 * - useMemo para evitar recomputar agregaciones en cada render.
 */
const WINDOW_MS = 60_000;
const BUCKET_MS = 2_000;

type Point = Record<string, number | string> & { t: string };

function PowerByZoneChartImpl({
  records,
}: {
  records: TelemetryRecord[];
}): JSX.Element {
  const data = useMemo<Point[]>(() => {
    if (records.length === 0) return [];
    const now = Date.now();
    const cutoff = now - WINDOW_MS;

    const buckets = new Map<number, Point>();
    for (const r of records) {
      const ts = Date.parse(r.timestamp);
      if (Number.isNaN(ts) || ts < cutoff) continue;
      const slot = Math.floor(ts / BUCKET_MS) * BUCKET_MS;
      let p = buckets.get(slot);
      if (!p) {
        p = { t: new Date(slot).toLocaleTimeString('es-CO', { hour12: false }) };
        for (const z of KNOWN_ZONES) p[z] = 0;
        buckets.set(slot, p);
      }
      const zoneKey = (r.zone ?? '') as string;
      if (zoneKey in p) {
        p[zoneKey] = ((p[zoneKey] as number) ?? 0) + r.power_kw;
      }
    }
    return Array.from(buckets.entries())
      .sort((a, b) => a[0] - b[0])
      .map(([, v]) => v);
  }, [records]);

  if (data.length === 0) {
    return (
      <div className="flex h-64 flex-col items-center justify-center gap-1 px-6 text-center text-sm text-ink-muted">
        <p className="font-medium text-ink">Sin lecturas en los ultimos 60 segundos.</p>
        <p>
          Este grafico solo cubre la ventana en vivo. La telemetria historica disponible
          se lista en la tabla inferior.
        </p>
      </div>
    );
  }

  return (
    <div className="h-72 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 10, right: 24, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
          <XAxis dataKey="t" tick={{ fontSize: 11, fill: '#64748B' }} minTickGap={32} />
          <YAxis
            tick={{ fontSize: 11, fill: '#64748B' }}
            label={{
              value: 'kW agregado',
              angle: -90,
              position: 'insideLeft',
              offset: 10,
              style: { fontSize: 11, fill: '#64748B' },
            }}
          />
          <Tooltip
            contentStyle={{
              borderRadius: 8,
              border: '1px solid #E2E8F0',
              fontSize: 12,
            }}
            formatter={(value: number) => [`${value.toFixed(2)} kW`, '']}
          />
          <Legend
            iconType="circle"
            wrapperStyle={{ fontSize: 12 }}
            formatter={(value: string) => labelForZone(value)}
          />
          {KNOWN_ZONES.map((zone) => (
            <Line
              key={zone}
              type="monotone"
              dataKey={zone}
              stroke={ZONE_COLOR[zone]}
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export const PowerByZoneChart = memo(PowerByZoneChartImpl);
