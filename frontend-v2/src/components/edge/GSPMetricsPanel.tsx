import { memo } from 'react';
import { KNOWN_ZONES, type KnownZone } from '@/api/types';
import { colorForZone, labelForZone } from '@/lib/zones';

/**
 * Metricas sinteticas del monitor GSP. Sin recharts: barras
 * horizontales con divs e histograma simple SVG.
 */

export type GSPSnapshot = {
  totalAnomalies24h: number;
  byZone: Record<KnownZone, number>;
  byKind: Array<{ label: string; count: number }>;
  latencyHistogramMs: number[]; // 8 bins (0–80 ms)
};

function BarRow({
  label,
  value,
  max,
  color,
}: {
  label: string;
  value: number;
  max: number;
  color: string;
}): JSX.Element {
  const pct = max === 0 ? 0 : Math.min(100, (value / max) * 100);
  return (
    <li className="grid grid-cols-[110px,1fr,40px] items-center gap-3 text-xs">
      <span className="truncate text-ink">{label}</span>
      <div className="h-2 overflow-hidden rounded-full bg-neutral-100">
        <div
          className="h-full rounded-full transition-[width] duration-700 ease-out"
          style={{ width: `${pct}%`, background: color }}
        />
      </div>
      <span className="text-right font-mono font-semibold text-ink">{value}</span>
    </li>
  );
}

function GSPMetricsPanelImpl({ data }: { data: GSPSnapshot }): JSX.Element {
  const maxByZone = Math.max(1, ...Object.values(data.byZone));
  const maxByKind = Math.max(1, ...data.byKind.map((k) => k.count));
  const histMax = Math.max(1, ...data.latencyHistogramMs);

  return (
    <div className="space-y-6">
      {/* Total */}
      <div className="rounded-md border border-border bg-neutral-50 p-4">
        <p className="text-xs uppercase tracking-wider text-ink-muted">Anomalias detectadas (24 h)</p>
        <p className="mt-1 font-mono text-4xl font-bold text-primary">
          {data.totalAnomalies24h}
        </p>
        <p className="text-[11px] text-ink-muted">conteo agregado del cluster, sintetico</p>
      </div>

      {/* Distribucion por zona */}
      <div>
        <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-muted">
          Distribucion por zona
        </p>
        <ul className="space-y-2">
          {KNOWN_ZONES.map((z) => (
            <BarRow
              key={z}
              label={labelForZone(z)}
              value={data.byZone[z] ?? 0}
              max={maxByZone}
              color={colorForZone(z)}
            />
          ))}
        </ul>
      </div>

      {/* Tipo de anomalia */}
      <div>
        <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-muted">
          Tipos de anomalia
        </p>
        <ul className="space-y-2">
          {data.byKind.map((k) => (
            <BarRow
              key={k.label}
              label={k.label}
              value={k.count}
              max={maxByKind}
              color="#1A3A6E"
            />
          ))}
        </ul>
      </div>

      {/* Histograma de latencia GSP */}
      <div>
        <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-muted">
          Latencia de procesamiento GSP
        </p>
        <div className="flex h-24 items-end gap-1 rounded-md border border-border bg-neutral-50 p-2">
          {data.latencyHistogramMs.map((v, i) => {
            const h = (v / histMax) * 100;
            return (
              <div
                key={i}
                className="flex-1 rounded-t bg-primary transition-[height] duration-500"
                style={{ height: `${h}%` }}
                title={`${i * 10}–${i * 10 + 10} ms: ${v}`}
              />
            );
          })}
        </div>
        <div className="mt-1 flex justify-between text-[10px] text-ink-muted">
          <span>0 ms</span>
          <span>80 ms</span>
        </div>
      </div>
    </div>
  );
}

export const GSPMetricsPanel = memo(GSPMetricsPanelImpl);
