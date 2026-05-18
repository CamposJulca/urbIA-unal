import { Network } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { ConceptualBanner } from '@/components/ui/ConceptualBanner';
import { SDNTopologyDiagram } from '@/components/sdn/SDNTopologyDiagram';
import { FlowsPanel } from '@/components/sdn/FlowsPanel';
import { StatsCards } from '@/components/sdn/StatsCards';

/**
 * Pagina M2 (visualizacion conceptual): Red Definida por Software.
 * Sin conexion a Ryu real. Animaciones y metricas son sinteticas
 * etiquetadas para honestidad academica.
 */
export default function SDN(): JSX.Element {
  return (
    <section className="mx-auto max-w-7xl px-6 py-10">
      {/* Cabecera */}
      <header className="mb-6 flex items-start gap-4">
        <div className="flex h-12 w-12 items-center justify-center rounded-md bg-primary/10 text-primary">
          <Network className="h-6 w-6" aria-hidden="true" />
        </div>
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-ink">Red Definida por Software</h1>
          <p className="text-sm text-ink-muted">
            Topologia de control del cluster Neusi · Visualizacion de la arquitectura planificada.
          </p>
        </div>
      </header>

      <ConceptualBanner title="Visualizacion conceptual · Datos sinteticos · Ryu controller pendiente (E10)">
        Esta vista muestra la arquitectura SDN disenada para UrbIA. Los flujos
        visualizados y las metricas superiores son sinteticos generados en el
        navegador. La integracion con un controlador Ryu real esta planificada
        en el Entregable 10 del cronograma doctoral.
      </ConceptualBanner>

      <div className="mt-6">
        <StatsCards />
      </div>

      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Topologia de red del cluster</CardTitle>
            <p className="text-xs text-ink-muted">
              Plano de control (lineas finas hacia el controlador) y plano de datos
              (lineas gruesas animadas entre switches). Arrastra los nodos para
              reorganizar; usa la rueda para zoom.
            </p>
          </CardHeader>
          <CardContent className="pt-0">
            <SDNTopologyDiagram />
          </CardContent>
        </Card>

        <div className="lg:col-span-1">
          <FlowsPanel />
        </div>
      </div>

      <Card className="mt-6">
        <CardHeader>
          <CardTitle>Arquitectura SDN planificada</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm leading-relaxed text-ink-muted">
            UrbIA planea desplegar un controlador <strong className="text-ink">Ryu</strong> sobre el cluster
            Neusi, separando el plano de control del plano de datos segun el modelo OpenFlow.
            Cada maquina del cluster expondra un switch logico OpenFlow administrado por el
            controlador desde el nodo <code className="font-mono">.102</code>. El proposito es
            aplicar <strong className="text-ink">politicas adaptativas de calidad de servicio</strong>
            que prioricen el trafico MQTT de telemetria AMI cuando el monitor distribuido GSP
            detecte anomalias espectrales en el grafo de medidores. Esta capa de coordinacion
            implementa la linea "Adaptador" del aparato de Aristizabal, integrada con el
            "Afinador" basado en Reinforcement Learning que ajusta los parametros τ del
            difuminador en tiempo real. La integracion concreta con Ryu y Mininet esta
            programada en el Entregable 10; hoy esta pagina demuestra la topologia objetivo.
          </p>
        </CardContent>
      </Card>
    </section>
  );
}
