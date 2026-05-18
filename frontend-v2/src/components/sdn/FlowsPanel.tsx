import { memo, useEffect, useState } from 'react';
import { ArrowRight, CircleDot } from 'lucide-react';
import { Badge } from '@/components/ui/Badge';
import { cn } from '@/lib/utils';

/**
 * Lista lateral de "flujos OpenFlow activos". Todo sintetico,
 * generado client-side. Cada 3 s un flujo se reemplaza.
 */

type Protocol = { name: string; port: number; color: string };

const HOSTS = ['.100', '.101', '.102', '.103', '.104', '.105'] as const;
const PROTOCOLS: readonly Protocol[] = [
  { name: 'MQTT',       port: 1883, color: 'success' },
  { name: 'HTTP',       port: 8000, color: 'primary' },
  { name: 'HTTP',       port: 8501, color: 'primary' },
  { name: 'PostgreSQL', port: 5432, color: 'warning' },
  { name: 'NFS',        port: 2049, color: 'warning' },
  { name: 'SCP',        port:   22, color: 'neutral' },
  { name: 'HTTPS',      port:  443, color: 'success' },
];

type SyntheticFlow = {
  id: string;
  src: string;
  dst: string;
  protocol: Protocol;
  latency_ms: number;
  bytes_s: number;
  idle: boolean;
};

function rand(min: number, max: number): number {
  return min + Math.random() * (max - min);
}
function pick<T>(arr: readonly T[]): T {
  return arr[Math.floor(Math.random() * arr.length)]!;
}

function genFlow(): SyntheticFlow {
  let src = pick(HOSTS);
  let dst = pick(HOSTS);
  while (dst === src) dst = pick(HOSTS);
  return {
    id: `${src}-${dst}-${Math.random().toString(36).slice(2, 8)}`,
    src,
    dst,
    protocol: pick(PROTOCOLS),
    latency_ms: Math.round(rand(1, 50) * 10) / 10,
    bytes_s: Math.round(rand(100, 50_000)),
    idle: Math.random() < 0.18,
  };
}

function bytesPerSec(n: number): string {
  if (n < 1024) return `${n} B/s`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB/s`;
  return `${(n / (1024 * 1024)).toFixed(2)} MB/s`;
}

function badgeVariant(p: Protocol): 'success' | 'primary' | 'warning' | 'neutral' {
  return p.color as 'success' | 'primary' | 'warning' | 'neutral';
}

function FlowsPanelImpl(): JSX.Element {
  const [flows, setFlows] = useState<SyntheticFlow[]>(() =>
    Array.from({ length: 10 }, genFlow),
  );

  useEffect(() => {
    // Cada 3 s: descarta el flujo mas viejo y agrega uno nuevo.
    // El conteo total oscila en [8, 12] dejando algunos ciclos sin
    // reposicion (azar) para que el numero no quede fijo.
    const id = setInterval(() => {
      setFlows((current) => {
        const next = [...current];
        const drop = Math.random() < 0.35;
        const add = Math.random() < 0.65 || next.length < 8;
        if (drop && next.length > 8) next.shift();
        if (add && next.length < 12) next.push(genFlow());
        return next;
      });
    }, 3000);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="flex h-full flex-col rounded-lg border border-border bg-surface shadow-card">
      <header className="flex items-center justify-between border-b border-border px-4 py-3">
        <div>
          <p className="text-sm font-semibold text-ink">Flujos OpenFlow activos</p>
          <p className="text-xs text-ink-muted">{flows.length} flujos en la tabla del switch</p>
        </div>
        <Badge variant="warning">sinteticos</Badge>
      </header>
      <ul className="max-h-[420px] divide-y divide-border overflow-auto">
        {flows.map((f) => (
          <li
            key={f.id}
            className="grid animate-fade-in grid-cols-[1fr,auto] items-center gap-2 px-4 py-2.5"
          >
            <div className="min-w-0">
              <div className="flex items-center gap-1.5 font-mono text-xs text-ink">
                <span className="font-semibold">{f.src}</span>
                <ArrowRight className="h-3 w-3 text-ink-muted" aria-hidden="true" />
                <span className="font-semibold">{f.dst}</span>
                <Badge variant={badgeVariant(f.protocol)} className="ml-1 px-1.5 py-0 text-[10px]">
                  {f.protocol.name}:{f.protocol.port}
                </Badge>
              </div>
              <div className="mt-1 flex gap-3 text-[11px] text-ink-muted">
                <span>{f.latency_ms.toFixed(1)} ms</span>
                <span>{bytesPerSec(f.bytes_s)}</span>
              </div>
            </div>
            <CircleDot
              className={cn(
                'h-3.5 w-3.5 shrink-0',
                f.idle ? 'text-ink-subtle' : 'animate-pulse-soft text-success',
              )}
              aria-hidden="true"
            />
          </li>
        ))}
      </ul>
    </div>
  );
}

export const FlowsPanel = memo(FlowsPanelImpl);
