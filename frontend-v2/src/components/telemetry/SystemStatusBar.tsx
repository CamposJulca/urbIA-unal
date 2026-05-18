import { useMemo } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';
import { formatRelative } from '@/lib/format';
import { ageSeconds } from '@/lib/format';
import type { MeterInfo, SystemHealthState, TelemetryRecord } from '@/api/types';

/**
 * Barra superior con el resumen operativo: backend, total de
 * medidores activos (con lectura <10 s), tasa estimada de mensajes
 * por segundo, ultima actualizacion y boton de refresco manual.
 */
export function SystemStatusBar({
  health,
  meters,
  records,
  lastUpdate,
}: {
  health: SystemHealthState;
  meters: MeterInfo[];
  records: TelemetryRecord[];
  lastUpdate: Date | null;
}): JSX.Element {
  const qc = useQueryClient();

  const activeCount = useMemo(
    () =>
      meters.filter((m) => {
        const a = ageSeconds(m.last_seen);
        return a !== null && a < 10;
      }).length,
    [meters],
  );

  // Tasa de mensajes por segundo derivada de la ventana real cubierta
  // por /telemetry/recent (delta entre el mas viejo y el mas nuevo).
  const msgRate = useMemo(() => {
    if (records.length < 2) return null;
    const sorted = [...records].sort(
      (a, b) => Date.parse(a.timestamp) - Date.parse(b.timestamp),
    );
    const t0 = Date.parse(sorted[0]!.timestamp);
    const tN = Date.parse(sorted[sorted.length - 1]!.timestamp);
    const dt = (tN - t0) / 1000;
    if (dt <= 0) return null;
    return records.length / dt;
  }, [records]);

  const healthLabel: Record<SystemHealthState, { label: string; variant: 'success' | 'warning' | 'danger' | 'neutral' }> = {
    ok: { label: 'Backend conectado', variant: 'success' },
    degraded: { label: 'Backend degradado', variant: 'warning' },
    down: { label: 'Backend desconectado', variant: 'danger' },
    unknown: { label: 'Verificando backend...', variant: 'neutral' },
  };
  const h = healthLabel[health];

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-surface px-4 py-3 shadow-card">
      <div className="flex flex-wrap items-center gap-4">
        <Badge variant={h.variant}>{h.label}</Badge>
        <div className="text-sm">
          <span className="text-ink-muted">Medidores activos:</span>{' '}
          <span className="font-mono font-semibold text-ink">
            {activeCount}/{meters.length || 10}
          </span>
        </div>
        <div className="text-sm">
          <span className="text-ink-muted">Tasa:</span>{' '}
          <span className="font-mono font-semibold text-ink">
            {msgRate ? `${msgRate.toFixed(1)} msg/s` : '—'}
          </span>
        </div>
        <div className="text-sm">
          <span className="text-ink-muted">Ult. actualizacion:</span>{' '}
          <span className="text-ink">
            {lastUpdate ? formatRelative(lastUpdate.toISOString()) : '—'}
          </span>
        </div>
      </div>

      <Button
        size="sm"
        variant="outline"
        onClick={() => {
          void qc.invalidateQueries({ queryKey: ['telemetry-recent'] });
          void qc.invalidateQueries({ queryKey: ['meters'] });
          void qc.invalidateQueries({ queryKey: ['health'] });
        }}
      >
        <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
        Refrescar ahora
      </Button>
    </div>
  );
}
