import { memo, useEffect, useRef, useState } from 'react';
import { Card, CardContent, CardHeader } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { ageSeconds, formatNumber, formatRelative } from '@/lib/format';
import { statusLabel, statusTone } from '@/lib/status';
import { colorForZone, labelForZone } from '@/lib/zones';
import type { MeterInfo, TelemetryRecord } from '@/api/types';

/**
 * Card individual de un medidor AMI. Recibe la fila de `/meters` y
 * la ultima lectura derivada de `/telemetry/recent`. Aplica un flash
 * sutil cuando llega un timestamp nuevo (transicion 200 ms).
 *
 * Estado del medidor (badge):
 *  - En vivo  : antiguedad < 10 s
 *  - Retraso  : 10 s <= antiguedad < 30 s
 *  - Sin senal: antiguedad >= 30 s o sin lectura
 *
 * Estado del campo `status` del backend (columna `estado` del esquema
 * v2): los tres tramos los define `lib/status.ts`, compartidos con
 * RecentReadingsTable — verde `activo`, ambar `mantenimiento`, rojo los
 * cinco estados de falla, gris cuando el backend no lo reporta.
 */
function MeterCardImpl({
  meter,
  latest,
}: {
  meter: MeterInfo;
  latest: TelemetryRecord | null;
}): JSX.Element {
  const lastTimestampRef = useRef<string | null>(null);
  const [flashing, setFlashing] = useState(false);

  useEffect(() => {
    if (latest && latest.timestamp !== lastTimestampRef.current) {
      lastTimestampRef.current = latest.timestamp;
      setFlashing(true);
      const t = setTimeout(() => setFlashing(false), 220);
      return () => clearTimeout(t);
    }
    return undefined;
  }, [latest]);

  const age = latest ? ageSeconds(latest.received_at) : ageSeconds(meter.last_seen);
  const liveness =
    age === null
      ? { variant: 'neutral' as const, label: 'Sin lectura' }
      : age < 10
        ? { variant: 'success' as const, label: 'En vivo' }
        : age < 30
          ? { variant: 'warning' as const, label: 'Retraso' }
          : { variant: 'danger' as const, label: 'Sin senal' };

  const status = latest?.status ?? null;
  const statusBadge = {
    variant: statusTone(status),
    label: statusLabel(status),
  };

  const zoneColor = colorForZone(meter.zone);

  return (
    <Card
      className="relative overflow-hidden transition-shadow hover:shadow-elev"
      style={{ borderLeft: `4px solid ${zoneColor}` }}
    >
      {flashing && (
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 animate-flash bg-accent/20"
        />
      )}

      <CardHeader className="gap-2 pb-3">
        <div className="flex items-center justify-between">
          <p className="font-mono text-sm font-semibold text-ink">{meter.meter_id}</p>
          <Badge variant={liveness.variant}>{liveness.label}</Badge>
        </div>
        <div className="flex items-center justify-between text-xs">
          <span className="font-medium uppercase tracking-wide" style={{ color: zoneColor }}>
            {labelForZone(meter.zone)}
          </span>
          <Badge variant={statusBadge.variant} className="text-[10px] uppercase">
            {statusBadge.label}
          </Badge>
        </div>
      </CardHeader>

      <CardContent className="pt-0">
        <div className="grid grid-cols-3 gap-3">
          <Metric label="Voltaje" unit="V" value={latest?.voltage_v} digits={1} />
          <Metric label="Corriente" unit="A" value={latest?.current_a} digits={2} />
          <Metric label="Potencia" unit="kW" value={latest?.power_kw} digits={2} />
        </div>

        <div className="mt-4 grid grid-cols-3 gap-3 border-t border-border pt-3">
          <MetricSmall label="Energia" unit="kWh" value={latest?.energy_kwh} digits={2} />
          <MetricSmall label="Frecuencia" unit="Hz" value={latest?.frequency_hz} digits={2} />
          <MetricSmall label="F. pot." unit="" value={latest?.power_factor} digits={3} />
        </div>

        <p className="mt-4 text-[11px] text-ink-muted">
          Ult. lectura: {formatRelative(latest?.received_at ?? meter.last_seen)}
        </p>
      </CardContent>
    </Card>
  );
}

function Metric({
  label,
  unit,
  value,
  digits,
}: {
  label: string;
  unit: string;
  value: number | null | undefined;
  digits: number;
}): JSX.Element {
  return (
    <div className="flex flex-col">
      <span className="text-[10px] font-medium uppercase tracking-wide text-ink-muted">
        {label}
      </span>
      <span className="mt-1 font-mono text-xl font-bold leading-tight text-ink">
        {formatNumber(value, digits)}
      </span>
      <span className="text-[10px] font-medium text-ink-muted">{unit}</span>
    </div>
  );
}

function MetricSmall({
  label,
  unit,
  value,
  digits,
}: {
  label: string;
  unit: string;
  value: number | null | undefined;
  digits: number;
}): JSX.Element {
  return (
    <div className="flex flex-col">
      <span className="text-[9px] uppercase tracking-wide text-ink-subtle">{label}</span>
      <span className="font-mono text-xs font-semibold text-ink">
        {formatNumber(value, digits)} <span className="text-ink-muted">{unit}</span>
      </span>
    </div>
  );
}

export const MeterCard = memo(MeterCardImpl);
