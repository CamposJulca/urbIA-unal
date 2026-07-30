import { useMemo } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { AlertTriangle, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';
import { cn } from '@/lib/utils';
import { formatRelative } from '@/lib/format';
import { ageSeconds, STALE_THRESHOLD_S } from '@/lib/format';
import type { MeterInfo, SystemHealthState, TelemetryRecord } from '@/api/types';

/**
 * Barra superior con el resumen operativo: backend, total de
 * medidores activos (con lectura <10 s), tasa estimada de mensajes
 * por segundo, frescura del dato y boton de refresco manual.
 */

// El umbral de frescura vive en lib/format para que esta barra y la tabla
// de lecturas apliquen el mismo criterio. Con el simulador publicando a
// 10 msg/s (10 medidores a 1 Hz), 60 s es holgado.

// 'empty' es el caso sin registros almacenados: sin este estado la barra
// muestra solo guiones, que se leen como "cargando" y no como "sin
// ingesta". 'unreachable' existe para NO afirmar "sin datos" cuando en
// realidad no pudimos preguntar; de eso ya avisa Telemetry.tsx.
type DataFreshness = 'loading' | 'unreachable' | 'empty' | 'stale' | 'live';

export function SystemStatusBar({
  health,
  meters,
  records,
  lastUpdate,
  isLoading,
  hasError,
}: {
  health: SystemHealthState;
  meters: MeterInfo[];
  records: TelemetryRecord[];
  lastUpdate: Date | null;
  isLoading: boolean;
  hasError: boolean;
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

  // Lectura mas reciente del lote. Su antiguedad es distinta de
  // `lastUpdate`, que es cuando el navegador hizo el fetch: si el flujo
  // MQTT esta caido el fetch es reciente pero el dato puede tener
  // semanas, y sin esta distincion la barra presentaria telemetria
  // historica como si fuera en vivo.
  const newest = useMemo(() => {
    if (records.length === 0) return null;
    return records.reduce((a, b) =>
      Date.parse(b.timestamp) > Date.parse(a.timestamp) ? b : a,
    );
  }, [records]);

  // Sin useMemo a proposito: ageSeconds() depende de Date.now(), asi que
  // memorizar sobre su resultado no ahorraria nada.
  const dataAge = newest ? ageSeconds(newest.timestamp) : null;

  let freshness: DataFreshness;
  if (newest !== null) {
    freshness = dataAge !== null && dataAge > STALE_THRESHOLD_S ? 'stale' : 'live';
  } else if (isLoading) {
    freshness = 'loading';
  } else if (hasError) {
    freshness = 'unreachable';
  } else {
    freshness = 'empty';
  }

  const healthLabel: Record<SystemHealthState, { label: string; variant: 'success' | 'warning' | 'danger' | 'neutral' }> = {
    ok: { label: 'Backend conectado', variant: 'success' },
    degraded: { label: 'Backend degradado', variant: 'warning' },
    down: { label: 'Backend desconectado', variant: 'danger' },
    unknown: { label: 'Verificando backend...', variant: 'neutral' },
  };
  const h = healthLabel[health];

  return (
    <div className="rounded-lg border border-border bg-surface shadow-card">
      {freshness === 'stale' && newest && (
        <div
          role="alert"
          className="flex items-start gap-2 border-b border-danger/30 bg-danger/10 px-4 py-2.5 text-sm text-danger"
        >
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <p>
            <strong>Datos historicos — no en vivo.</strong> La lectura mas reciente es de{' '}
            {formatRelative(newest.timestamp)} y la ingesta MQTT esta detenida. Las cifras
            describen el ultimo periodo capturado, no el estado actual del cluster.
          </p>
        </div>
      )}

      {freshness === 'empty' && (
        <div
          role="alert"
          className="flex items-start gap-2 border-b border-warning/40 bg-warning/10 px-4 py-2.5 text-sm text-ink"
        >
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warning" aria-hidden="true" />
          <p>
            <strong>Sin datos de telemetria — ingesta no iniciada.</strong> No hay lecturas
            almacenadas todavia. Apareceran aqui en cuanto el simulador AMI vuelva a
            publicar y el backend las persista.
          </p>
        </div>
      )}

      <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
        <div className="flex flex-wrap items-center gap-4">
          <Badge variant={h.variant}>{h.label}</Badge>
          <div className="text-sm">
            <span className="text-ink-muted">Medidores activos:</span>{' '}
            <span className="font-mono font-semibold text-ink">
              {meters.length > 0 ? `${activeCount}/${meters.length}` : '—'}
            </span>
          </div>
          <div className="text-sm">
            <span className="text-ink-muted">Tasa:</span>{' '}
            <span className="font-mono font-semibold text-ink">
              {freshness === 'live' && msgRate
                ? `${msgRate.toFixed(1)} msg/s`
                : freshness === 'stale'
                  ? '0.0 msg/s'
                  : '—'}
            </span>
          </div>
          <div className="text-sm">
            <span className="text-ink-muted">Lectura mas reciente:</span>{' '}
            <span
              className={cn('text-ink', freshness === 'stale' && 'font-semibold text-danger')}
            >
              {newest
                ? formatRelative(newest.timestamp)
                : freshness === 'empty'
                  ? 'sin registros'
                  : '—'}
            </span>
          </div>
          <div className="text-sm">
            <span className="text-ink-muted">Ult. consulta:</span>{' '}
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
    </div>
  );
}
