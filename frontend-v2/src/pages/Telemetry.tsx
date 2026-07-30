import { useMemo } from 'react';
import { Activity, AlertTriangle } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/Card';
import { MeterCard } from '@/components/telemetry/MeterCard';
import { PowerByZoneChart } from '@/components/telemetry/PowerByZoneChart';
import { RecentReadingsTable } from '@/components/telemetry/RecentReadingsTable';
import { SystemStatusBar } from '@/components/telemetry/SystemStatusBar';
import {
  useMeters,
  useRecentTelemetry,
  useSystemHealth,
} from '@/api/hooks';
import type { TelemetryRecord } from '@/api/types';

/**
 * Pagina M1: Telemetria AMI en vivo. Una sola query a
 * /telemetry/recent alimenta cards, grafico y tabla. /meters provee
 * la lista canonica de medidores y zonas. /health alimenta el badge
 * del header y la SystemStatusBar.
 */
export default function Telemetry(): JSX.Element {
  const meters = useMeters();
  const telemetry = useRecentTelemetry(600);
  const health = useSystemHealth();

  const records: TelemetryRecord[] = useMemo(
    () =>
      (telemetry.data ?? [])
        .slice()
        .sort((a, b) => Date.parse(b.timestamp) - Date.parse(a.timestamp)),
    [telemetry.data],
  );

  // Mapa meter_id -> ultima lectura.
  const latestByMeter = useMemo(() => {
    const m = new Map<string, TelemetryRecord>();
    for (const r of records) {
      if (!m.has(r.meter_id)) m.set(r.meter_id, r);
    }
    return m;
  }, [records]);

  const lastUpdate = telemetry.dataUpdatedAt
    ? new Date(telemetry.dataUpdatedAt)
    : null;

  const sortedMeters = useMemo(() => {
    const arr = [...(meters.data ?? [])];
    arr.sort((a, b) => a.meter_id.localeCompare(b.meter_id));
    return arr;
  }, [meters.data]);

  const backendDown =
    health.state === 'down' || (telemetry.isError && !telemetry.data);

  return (
    <section className="mx-auto max-w-7xl px-6 py-10">
      {/* Cabecera de pagina */}
      <header className="mb-6 flex items-start gap-4">
        <div className="flex h-12 w-12 items-center justify-center rounded-md bg-primary/10 text-primary">
          <Activity className="h-6 w-6" aria-hidden="true" />
        </div>
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-ink">Telemetria AMI</h1>
          <p className="text-sm text-ink-muted">
            10 medidores en 5 zonas — telemetria capturada por el simulador AMI via
            MQTT y persistida por el backend FastAPI.
          </p>
        </div>
      </header>

      {backendDown && (
        <div className="mb-4 flex items-start gap-3 rounded-md border border-danger/30 bg-danger/5 p-4 text-danger">
          <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0" aria-hidden="true" />
          <div className="text-sm">
            <p className="font-semibold">No se puede conectar al backend de UrbIA</p>
            <p className="text-danger/90">
              Verifica que el contenedor <code className="font-mono">urbia-backend</code> este
              activo en el puerto 8000. Reintentando automaticamente.
            </p>
          </div>
        </div>
      )}

      <SystemStatusBar
        health={health.state}
        meters={meters.data ?? []}
        records={records}
        lastUpdate={lastUpdate}
        isLoading={telemetry.isLoading}
        hasError={telemetry.isError}
      />

      {/* Grid de medidores */}
      <h2 className="mt-8 mb-3 text-sm font-semibold uppercase tracking-wider text-ink-muted">
        Medidores
      </h2>
      {sortedMeters.length === 0 ? (
        <Card>
          <CardContent className="py-10 text-center text-ink-muted">
            {meters.isLoading
              ? 'Cargando catalogo de medidores...'
              : 'El backend no ha registrado medidores aun.'}
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
          {sortedMeters.map((m) => (
            <MeterCard
              key={m.meter_id}
              meter={m}
              latest={latestByMeter.get(m.meter_id) ?? null}
            />
          ))}
        </div>
      )}

      {/* Grafico */}
      <h2 className="mt-10 mb-3 text-sm font-semibold uppercase tracking-wider text-ink-muted">
        Potencia agregada por zona (ventana 60 s)
      </h2>
      <Card>
        <CardContent className="pt-6">
          <PowerByZoneChart records={records} />
        </CardContent>
      </Card>

      {/* Tabla */}
      <h2 className="mt-10 mb-3 text-sm font-semibold uppercase tracking-wider text-ink-muted">
        Ultimas lecturas recibidas
      </h2>
      <Card className="overflow-hidden">
        <RecentReadingsTable records={records} />
      </Card>
    </section>
  );
}
