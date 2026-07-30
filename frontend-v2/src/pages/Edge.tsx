import { useEffect, useState } from 'react';
import { Cpu } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { ConceptualBanner } from '@/components/ui/ConceptualBanner';
import { EdgeNodeCard, type EdgeMetrics } from '@/components/edge/EdgeNodeCard';
import { DistributedProcessingDiagram } from '@/components/edge/DistributedProcessingDiagram';
import { GSPMetricsPanel, type GSPSnapshot } from '@/components/edge/GSPMetricsPanel';
import { KNOWN_ZONES, type KnownZone } from '@/api/types';

/**
 * Pagina M3 (visualizacion conceptual): Computacion Edge.
 * Un unico setInterval por pagina genera todas las metricas
 * sinteticas para evitar multiples timers compitiendo.
 */

function clamp(n: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, n));
}

function walk(prev: number, target: number, jitter: number, min: number, max: number): number {
  const drift = (target - prev) * 0.12;
  const noise = (Math.random() - 0.5) * jitter;
  return clamp(prev + drift + noise, min, max);
}

const KIND_LABELS = ['Saturacion voltaje', 'Caida potencia abrupta'] as const;

type EdgeState = {
  central: EdgeMetrics;
  edge: EdgeMetrics;
  gsp: GSPSnapshot;
};

function initialZoneMap(): Record<KnownZone, number> {
  return {
    'MNZ-CENTRO': 3,
    'MNZ-NORTE': 1,
    'MNZ-SUR': 0,
    'MNZ-ESTE': 2,
    'MNZ-OESTE': 0,
  };
}

function initialState(): EdgeState {
  return {
    central: { cpuPercent: 38, memoryPercent: 52, gspLatencyMs: 14.2, anomaliesLastHour: 2 },
    edge:    { cpuPercent: 22, memoryPercent: 34, gspLatencyMs: 8.6,  anomaliesLastHour: 1 },
    gsp: {
      totalAnomalies24h: 47,
      byZone: initialZoneMap(),
      byKind: KIND_LABELS.map((l, i) => ({ label: l, count: i === 0 ? 4 : 2 })),
      latencyHistogramMs: [3, 6, 9, 12, 7, 4, 2, 1],
    },
  };
}

export default function Edge(): JSX.Element {
  const [state, setState] = useState<EdgeState>(initialState);

  // Tick rapido (2 s) para CPU/mem/latencia de los EdgeNodeCard.
  useEffect(() => {
    const id = setInterval(() => {
      setState((prev) => ({
        ...prev,
        central: {
          cpuPercent: walk(prev.central.cpuPercent, 40, 6, 12, 78),
          memoryPercent: walk(prev.central.memoryPercent, 55, 3, 30, 80),
          gspLatencyMs: walk(prev.central.gspLatencyMs, 14, 1.6, 6, 28),
          anomaliesLastHour: prev.central.anomaliesLastHour,
        },
        edge: {
          cpuPercent: walk(prev.edge.cpuPercent, 24, 5, 10, 60),
          memoryPercent: walk(prev.edge.memoryPercent, 36, 3, 20, 65),
          gspLatencyMs: walk(prev.edge.gspLatencyMs, 9, 1.2, 4, 22),
          anomaliesLastHour: prev.edge.anomaliesLastHour,
        },
      }));
    }, 2000);
    return () => clearInterval(id);
  }, []);

  // Tick lento (5 s) para metricas GSP agregadas + anomalias por hora.
  useEffect(() => {
    const id = setInterval(() => {
      setState((prev) => {
        const nextByZone = { ...prev.gsp.byZone };
        // Probabilidad baja de incrementar el contador de una zona.
        for (const z of KNOWN_ZONES) {
          if (Math.random() < 0.15) {
            nextByZone[z] = Math.min(15, (nextByZone[z] ?? 0) + 1);
          }
        }
        const total =
          prev.gsp.totalAnomalies24h + (Math.random() < 0.4 ? 1 : 0);
        const nextByKind = prev.gsp.byKind.map((k) => ({
          ...k,
          count: Math.max(0, k.count + (Math.random() < 0.3 ? 1 : 0)),
        }));
        const nextHist = prev.gsp.latencyHistogramMs.map((v) =>
          Math.max(0, Math.round(v + (Math.random() - 0.5) * 1.4)),
        );
        return {
          ...prev,
          central: {
            ...prev.central,
            anomaliesLastHour: clamp(
              prev.central.anomaliesLastHour + (Math.random() < 0.18 ? 1 : 0),
              0,
              12,
            ),
          },
          edge: {
            ...prev.edge,
            anomaliesLastHour: clamp(
              prev.edge.anomaliesLastHour + (Math.random() < 0.1 ? 1 : 0),
              0,
              8,
            ),
          },
          gsp: {
            totalAnomalies24h: Math.min(999, total),
            byZone: nextByZone,
            byKind: nextByKind,
            latencyHistogramMs: nextHist,
          },
        };
      });
    }, 5000);
    return () => clearInterval(id);
  }, []);

  return (
    <section className="mx-auto max-w-7xl px-6 py-10">
      <header className="mb-6 flex items-start gap-4">
        <div className="flex h-12 w-12 items-center justify-center rounded-md bg-primary/10 text-primary">
          <Cpu className="h-6 w-6" aria-hidden="true" />
        </div>
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-ink">Computacion Edge</h1>
          <p className="text-sm text-ink-muted">
            Monitor GSP distribuido del cluster · Arquitectura edge planificada.
          </p>
        </div>
      </header>

      <ConceptualBanner title="Maqueta de interfaz · Monitor GSP no implementado · Metricas sinteticas">
        El monitor GSP <strong>todavia no esta implementado</strong>: esta pagina es
        una maqueta de la interfaz prevista. Todas las cifras que se muestran
        (latencia, CPU, memoria, anomalias) se generan en el navegador y{' '}
        <strong>no corresponden a ninguna medicion</strong>. Tanto la implementacion
        centralizada como su distribucion a un nodo edge fisico (Raspberry Pi 5) son
        trabajo pendiente.
      </ConceptualBanner>

      <div className="mt-6 grid grid-cols-1 gap-6 md:grid-cols-2">
        <EdgeNodeCard
          name="Nodo de borde x86"
          descriptor="Agregacion central del monitor GSP"
          role="central"
          status="not-deployed"
          metrics={state.central}
        />
        <EdgeNodeCard
          name="Nodo de borde ARM (pendiente)"
          descriptor="Deteccion zonal sobre el subgrafo local"
          role="edge"
          status="pending"
          metrics={state.edge}
        />
      </div>

      <Card className="mt-6">
        <CardHeader>
          <CardTitle>Procesamiento distribuido</CardTitle>
          <p className="text-xs text-ink-muted">
            Flujo planificado de la telemetria AMI a traves del monitor GSP particionado.
          </p>
        </CardHeader>
        <CardContent className="pt-0">
          <DistributedProcessingDiagram />
        </CardContent>
      </Card>

      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Detecciones del monitor GSP</CardTitle>
            <p className="text-xs text-ink-muted">
              Sintetico. Cuando el monitor GSP exista, sus detecciones alimentaran este
              panel; hoy no hay ninguna medicion detras de estas cifras.
            </p>
          </CardHeader>
          <CardContent className="pt-0">
            <GSPMetricsPanel data={state.gsp} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Arquitectura distribuida planificada</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm leading-relaxed text-ink-muted">
            <p>
              <strong className="text-ink">Por que distribuir.</strong> La capa edge en AMI
              urbana reduce la latencia entre la deteccion y la respuesta de control,
              recorta el ancho de banda enviado al datacenter y otorga autonomia local
              al gateway cuando el enlace al backend se degrada.
            </p>
            <p>
              <strong className="text-ink">Particion del monitor GSP.</strong> Cada nodo
              edge ejecuta un filtro pasaaltos sobre el subgrafo zonal de los medidores
              que cuelgan de el; el nodo central agrega los resultados zonales para
              detectar anomalias emergentes a escala de cluster y cerrar el lazo con el
              Afinador de τ.
            </p>
            <p>
              <strong className="text-ink">Base experimental.</strong> El detector espectral{' '}
              <code className="font-mono">H(λ) = λ</code>, evaluado en los experimentos
              preliminares de la tesis, detecta anomalias estructurales en nodos hoja del
              grafo AMI. Esta propiedad
              motiva la distribucion del procesamiento: cada nodo edge ejecuta el filtro
              pasaaltos sobre su subgrafo zonal local, y el nodo central agrega
              resultados para deteccion de anomalias emergentes a escala de cluster.
            </p>
            <p>
              <strong className="text-ink">Plan de integracion.</strong> Cuando se disponga
              del nodo de borde ARM, el agente edge se desplegara en contenedor; mientras
              tanto se emulara sobre el nodo x86 para validar la coordinacion. La
              integracion concreta esta prevista para fases posteriores del proyecto.
            </p>
          </CardContent>
        </Card>
      </div>
    </section>
  );
}
