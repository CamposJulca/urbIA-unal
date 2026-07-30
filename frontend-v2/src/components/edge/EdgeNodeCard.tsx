import { memo } from 'react';
import { CheckCircle2, Hourglass, Cpu, MemoryStick, Activity, AlertOctagon } from 'lucide-react';
import { Card, CardContent, CardHeader } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { cn } from '@/lib/utils';

/**
 * Card representando un nodo del monitor GSP distribuido. Sin
 * dependencia de recharts: las barras de progreso son divs.
 */

// 'not-deployed' es el estado real de todos los nodos hoy: el monitor GSP
// no existe como software. 'pending' anade que tampoco existe el hardware.
// Ninguno de los dos puede pintarse en verde.
export type EdgeStatus = 'active' | 'pending' | 'not-deployed';
export type EdgeRole = 'central' | 'edge';

export type EdgeMetrics = {
  cpuPercent: number;
  memoryPercent: number;
  gspLatencyMs: number;
  anomaliesLastHour: number;
};

type Props = {
  name: string;
  descriptor: string;
  role: EdgeRole;
  status: EdgeStatus;
  metrics: EdgeMetrics;
};

const ROLE_BADGE: Record<EdgeRole, { variant: 'primary' | 'warning'; label: string }> = {
  central: { variant: 'primary', label: 'Central' },
  edge: { variant: 'warning', label: 'Edge' },
};

const STATUS_BADGE: Record<
  EdgeStatus,
  { variant: 'success' | 'warning' | 'neutral'; label: string }
> = {
  active:         { variant: 'success', label: 'Operativo' },
  'not-deployed': { variant: 'neutral', label: 'Sin desplegar' },
  pending:        { variant: 'warning', label: 'Hardware pendiente' },
};

function ProgressBar({
  value,
  color,
}: {
  value: number;
  color: string;
}): JSX.Element {
  const pct = Math.max(0, Math.min(100, value));
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-neutral-200">
      <div
        className="h-full rounded-full transition-[width] duration-700 ease-out"
        style={{ width: `${pct}%`, background: color }}
      />
    </div>
  );
}

function EdgeNodeCardImpl({ name, descriptor, role, status, metrics }: Props): JSX.Element {
  const isPending = status === 'pending';
  const roleBadge = ROLE_BADGE[role];
  const statusBadge = STATUS_BADGE[status];

  // Color de la barra segun severidad (verde < 60 < ambar < 85 < rojo).
  const cpuColor =
    metrics.cpuPercent > 85 ? '#EF4444' : metrics.cpuPercent > 60 ? '#F59E0B' : '#10B981';
  const memColor =
    metrics.memoryPercent > 85 ? '#EF4444' : metrics.memoryPercent > 60 ? '#F59E0B' : '#10B981';

  const anomalyVariant =
    metrics.anomaliesLastHour === 0
      ? 'success'
      : metrics.anomaliesLastHour < 5
        ? 'warning'
        : 'danger';

  return (
    <Card
      className={cn(
        'transition-shadow hover:shadow-elev',
        isPending && 'border-dashed border-warning/50 bg-warning/[0.02]',
      )}
    >
      <CardHeader className="gap-2 pb-3">
        <div className="flex items-center justify-between">
          <div className="min-w-0">
            <p className="text-sm font-semibold text-ink">{name}</p>
            <p className="text-[11px] text-ink-muted">{descriptor}</p>
          </div>
          <div className="flex flex-col items-end gap-1">
            <Badge variant={roleBadge.variant}>{roleBadge.label}</Badge>
            <Badge variant={statusBadge.variant} className="text-[10px]">
              {statusBadge.label}
            </Badge>
          </div>
        </div>
      </CardHeader>

      <CardContent className="grid grid-cols-2 gap-4 pt-0">
        {/* CPU */}
        <div>
          <div className="mb-1 flex items-center justify-between text-xs text-ink-muted">
            <span className="flex items-center gap-1">
              <Cpu className="h-3 w-3" aria-hidden="true" /> CPU
            </span>
            <span className="font-mono font-semibold text-ink">
              {metrics.cpuPercent.toFixed(0)}%
            </span>
          </div>
          <ProgressBar value={metrics.cpuPercent} color={cpuColor} />
        </div>

        {/* Memoria */}
        <div>
          <div className="mb-1 flex items-center justify-between text-xs text-ink-muted">
            <span className="flex items-center gap-1">
              <MemoryStick className="h-3 w-3" aria-hidden="true" /> Memoria
            </span>
            <span className="font-mono font-semibold text-ink">
              {metrics.memoryPercent.toFixed(0)}%
            </span>
          </div>
          <ProgressBar value={metrics.memoryPercent} color={memColor} />
        </div>

        {/* Latencia GSP */}
        <div className="rounded-md border border-border bg-neutral-50 p-3">
          <div className="flex items-center justify-between text-[10px] uppercase tracking-wide text-ink-muted">
            <span className="flex items-center gap-1">
              <Activity className="h-3 w-3" aria-hidden="true" /> Lat. GSP
            </span>
            <span>ms</span>
          </div>
          <p className="mt-1 font-mono text-2xl font-bold text-ink">
            {metrics.gspLatencyMs.toFixed(1)}
          </p>
        </div>

        {/* Anomalias */}
        <div className="rounded-md border border-border bg-neutral-50 p-3">
          <div className="flex items-center justify-between text-[10px] uppercase tracking-wide text-ink-muted">
            <span className="flex items-center gap-1">
              <AlertOctagon className="h-3 w-3" aria-hidden="true" /> Anomalias 1 h
            </span>
            <Badge variant={anomalyVariant} className="text-[9px]">
              {metrics.anomaliesLastHour === 0 ? 'estables' : 'detectadas'}
            </Badge>
          </div>
          <p className="mt-1 font-mono text-2xl font-bold text-ink">
            {metrics.anomaliesLastHour}
          </p>
        </div>
      </CardContent>

      <div className="flex items-center justify-between border-t border-border px-6 py-3 text-xs text-ink-muted">
        <span>Monitor GSP</span>
        <span className="flex items-center gap-1.5">
          {status === 'active' ? (
            <>
              <CheckCircle2 className="h-3.5 w-3.5 text-success" aria-hidden="true" />
              <span className="text-success">activo</span>
            </>
          ) : isPending ? (
            <>
              <Hourglass className="h-3.5 w-3.5 text-ink-muted" aria-hidden="true" />
              <span>sin hardware asignado</span>
            </>
          ) : (
            <>
              <Hourglass className="h-3.5 w-3.5 text-ink-muted" aria-hidden="true" />
              <span>sin implementar</span>
            </>
          )}
        </span>
      </div>
    </Card>
  );
}

export const EdgeNodeCard = memo(EdgeNodeCardImpl);
