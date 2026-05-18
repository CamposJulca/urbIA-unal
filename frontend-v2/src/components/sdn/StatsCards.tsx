import { memo, useEffect, useRef, useState } from 'react';
import { Area, AreaChart, ResponsiveContainer, Tooltip } from 'recharts';
import { Card, CardContent } from '@/components/ui/Card';
import { Activity, Gauge, Server } from 'lucide-react';

/**
 * Tres metricas sinteticas top de la pagina SDN. Cada una conserva
 * un buffer de 30 muestras para el sparkline. Actualiza cada 2 s.
 */

const HISTORY = 30;

function pushTrend(prev: number[], v: number): number[] {
  const next = [...prev, v];
  if (next.length > HISTORY) next.shift();
  return next;
}

function useSyntheticSeries(initial: number, jitter: number, intervalMs = 2000): number[] {
  const [series, setSeries] = useState<number[]>(() =>
    Array.from({ length: HISTORY }, () => initial + (Math.random() - 0.5) * jitter),
  );
  const seedRef = useRef(initial);

  useEffect(() => {
    const id = setInterval(() => {
      // Caminata aleatoria suave, vuelve a la media.
      const last = seedRef.current;
      const delta = (Math.random() - 0.5) * jitter;
      const drift = (initial - last) * 0.08;
      const next = Math.max(0, last + delta + drift);
      seedRef.current = next;
      setSeries((prev) => pushTrend(prev, next));
    }, intervalMs);
    return () => clearInterval(id);
  }, [initial, jitter, intervalMs]);

  return series;
}

function Spark({ data, color }: { data: number[]; color: string }): JSX.Element {
  const points = data.map((v, i) => ({ i, v }));
  return (
    <div className="h-12 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={points} margin={{ top: 0, right: 0, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id={`g-${color}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.35} />
              <stop offset="100%" stopColor={color} stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <Tooltip
            contentStyle={{ fontSize: 11, padding: '2px 6px', borderRadius: 6 }}
            formatter={(v: number) => v.toFixed(2)}
            labelFormatter={() => ''}
          />
          <Area
            type="monotone"
            dataKey="v"
            stroke={color}
            strokeWidth={1.6}
            fill={`url(#g-${color})`}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

function StatCard({
  label,
  value,
  unit,
  icon,
  color,
  series,
}: {
  label: string;
  value: string;
  unit: string;
  icon: JSX.Element;
  color: string;
  series: number[];
}): JSX.Element {
  return (
    <Card>
      <CardContent className="p-5">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold uppercase tracking-wider text-ink-muted">
            {label}
          </span>
          <span className="text-ink-muted">{icon}</span>
        </div>
        <div className="mt-1 flex items-baseline gap-1">
          <span className="font-mono text-3xl font-bold text-ink">{value}</span>
          <span className="text-sm text-ink-muted">{unit}</span>
        </div>
        <Spark data={series} color={color} />
      </CardContent>
    </Card>
  );
}

function StatsCardsImpl(): JSX.Element {
  const flows = useSyntheticSeries(10, 2);
  const latency = useSyntheticSeries(12.4, 4);
  const throughput = useSyntheticSeries(1.2, 0.6);

  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
      <StatCard
        label="Flujos activos"
        value={Math.round(flows[flows.length - 1] ?? 10).toString()}
        unit="flujos"
        icon={<Activity className="h-4 w-4" aria-hidden="true" />}
        color="#1A3A6E"
        series={flows}
      />
      <StatCard
        label="Latencia promedio"
        value={(latency[latency.length - 1] ?? 12.4).toFixed(1)}
        unit="ms"
        icon={<Gauge className="h-4 w-4" aria-hidden="true" />}
        color="#10B981"
        series={latency}
      />
      <StatCard
        label="Throughput cluster"
        value={(throughput[throughput.length - 1] ?? 1.2).toFixed(2)}
        unit="MB/s"
        icon={<Server className="h-4 w-4" aria-hidden="true" />}
        color="#F59E0B"
        series={throughput}
      />
    </div>
  );
}

export const StatsCards = memo(StatsCardsImpl);
