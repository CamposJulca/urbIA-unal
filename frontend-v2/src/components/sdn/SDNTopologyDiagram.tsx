import { memo } from 'react';
import {
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
  Handle,
  Position,
} from '@xyflow/react';
import { Cpu, Server, Router } from 'lucide-react';
import { cn } from '@/lib/utils';

import '@xyflow/react/dist/style.css';

/**
 * Diagrama conceptual de la topologia SDN planificada. Sin conexion a un
 * controlador real. Layout manual para previsibilidad.
 *
 * Los nodos se identifican por rol, no por direccion ni hostname: el
 * inventario de maquinas no se publica.
 */

type ControllerData = {
  label: string;
  sublabel: string;
};

type SwitchRole =
  | 'integracion'
  | 'servicios'
  | 'observabilidad'
  | 'borde'
  | 'datos'
  | 'consola';

type SwitchData = {
  label: string;
  role: SwitchRole;
};

// El chip describe la funcion del nodo; el label describe su rol en la
// arquitectura. Ninguno expone direcciones ni hostnames.
const ROLE_STYLE: Record<SwitchRole, { ring: string; chip: string; label: string }> = {
  integracion:    { ring: 'border-primary',     chip: 'bg-primary text-primary-foreground', label: 'Backend y persistencia' },
  servicios:      { ring: 'border-success',     chip: 'bg-success text-success-foreground', label: 'Broker MQTT' },
  observabilidad: { ring: 'border-warning',     chip: 'bg-warning text-accent-foreground',  label: 'Metricas y tableros' },
  borde:          { ring: 'border-neutral-300', chip: 'bg-neutral-200 text-neutral-700',    label: 'Gateway IoT' },
  datos:          { ring: 'border-neutral-300', chip: 'bg-neutral-200 text-neutral-700',    label: 'Respaldos' },
  consola:        { ring: 'border-neutral-300', chip: 'bg-neutral-200 text-neutral-700',    label: 'Auditoria y capturas' },
};

function ControllerNode({ data }: NodeProps<Node<ControllerData, 'controller'>>): JSX.Element {
  return (
    <div className="flex h-[80px] w-[200px] flex-col items-center justify-center rounded-lg bg-gradient-to-br from-primary to-primary-dark px-3 text-white shadow-elev">
      <Handle type="source" position={Position.Bottom} style={{ background: '#FFC107' }} />
      <div className="flex items-center gap-2">
        <Router className="h-5 w-5 text-accent" aria-hidden="true" />
        <span className="text-sm font-semibold">{data.label}</span>
      </div>
      <span className="mt-1 text-[11px] text-white/80">{data.sublabel}</span>
    </div>
  );
}

function SwitchNode({ data }: NodeProps<Node<SwitchData, 'switch'>>): JSX.Element {
  const r = ROLE_STYLE[data.role];
  return (
    <div
      className={cn(
        'flex h-[80px] w-[150px] flex-col items-center justify-center gap-1 rounded-md border-2 bg-surface px-2 text-center shadow-card',
        r.ring,
      )}
    >
      <Handle type="target" position={Position.Top} style={{ background: '#94A3B8' }} />
      <Handle type="source" position={Position.Bottom} style={{ background: '#94A3B8' }} />
      <Handle type="source" position={Position.Left} id="left" style={{ background: '#94A3B8' }} />
      <Handle type="source" position={Position.Right} id="right" style={{ background: '#94A3B8' }} />
      <div className="flex items-center gap-1.5">
        {data.role === 'integracion' ? (
          <Cpu className="h-3.5 w-3.5 text-primary" aria-hidden="true" />
        ) : (
          <Server className="h-3.5 w-3.5 text-ink-muted" aria-hidden="true" />
        )}
        <span className="text-[11px] font-semibold text-ink">{data.label}</span>
      </div>
      <span className={cn('rounded px-1.5 py-0.5 text-[9px] font-semibold uppercase', r.chip)}>
        {r.label}
      </span>
    </div>
  );
}

const nodeTypes = { controller: ControllerNode, switch: SwitchNode };

// Layout manual (consistente, deterministico).
const Y_CTRL = 0;
const Y_SW = 220;
const X0 = 40;
const DX = 180;

const NODES: Node[] = [
  {
    id: 'ctrl',
    type: 'controller',
    position: { x: X0 + 2 * DX + 75, y: Y_CTRL },
    data: { label: 'Controlador SDN', sublabel: 'planificado — sin desplegar' } as ControllerData,
    draggable: true,
  },
  {
    id: 'sw-obs',
    type: 'switch',
    position: { x: X0 + 0 * DX, y: Y_SW },
    data: { label: 'Nodo de observabilidad', role: 'observabilidad' } as SwitchData,
    draggable: true,
  },
  {
    id: 'sw-svc',
    type: 'switch',
    position: { x: X0 + 1 * DX, y: Y_SW },
    data: { label: 'Nodo de servicios', role: 'servicios' } as SwitchData,
    draggable: true,
  },
  {
    id: 'sw-int',
    type: 'switch',
    position: { x: X0 + 2 * DX, y: Y_SW },
    data: { label: 'Nodo de integracion', role: 'integracion' } as SwitchData,
    draggable: true,
  },
  {
    id: 'sw-edge',
    type: 'switch',
    position: { x: X0 + 3 * DX, y: Y_SW },
    data: { label: 'Nodo de borde x86', role: 'borde' } as SwitchData,
    draggable: true,
  },
  {
    id: 'sw-data',
    type: 'switch',
    position: { x: X0 + 4 * DX, y: Y_SW },
    data: { label: 'Nodo de datos', role: 'datos' } as SwitchData,
    draggable: true,
  },
  {
    id: 'sw-console',
    type: 'switch',
    position: { x: X0 + 5 * DX, y: Y_SW },
    data: { label: 'Consola de operacion', role: 'consola' } as SwitchData,
    draggable: true,
  },
];

// Plano de control (controlador → switches), sin animacion.
const CONTROL_EDGES: Edge[] = ['sw-obs', 'sw-svc', 'sw-int', 'sw-edge', 'sw-data', 'sw-console'].map((id) => ({
  id: `ctrl-${id}`,
  source: 'ctrl',
  target: id,
  type: 'smoothstep',
  style: { stroke: 'rgba(46, 90, 158, 0.55)', strokeWidth: 1.5, strokeDasharray: '4 3' },
}));

// Plano de datos (nodo ↔ nodo). Sin animacion a proposito: el diagrama
// describe enlaces de la arquitectura, no trafico medido.
const DATA_EDGES: Edge[] = [
  {
    id: 'mqtt-svc-int',
    source: 'sw-svc',
    sourceHandle: 'right',
    target: 'sw-int',
    type: 'smoothstep',
    label: 'MQTT 1883',
    style: { stroke: '#10B981', strokeWidth: 2 },
    labelBgStyle: { fill: '#ECFDF5' },
    labelStyle: { fill: '#065F46', fontSize: 11, fontWeight: 600 },
  },
  {
    id: 'sim-edge-int',
    source: 'sw-edge',
    sourceHandle: 'left',
    target: 'sw-int',
    type: 'smoothstep',
    label: 'Telemetria AMI',
    style: { stroke: '#2E5A9E', strokeWidth: 2 },
    labelBgStyle: { fill: '#EFF6FF' },
    labelStyle: { fill: '#1A3A6E', fontSize: 11, fontWeight: 600 },
  },
  {
    id: 'bkp-int-data',
    source: 'sw-int',
    sourceHandle: 'right',
    target: 'sw-data',
    type: 'smoothstep',
    label: 'Respaldo NFS',
    style: { stroke: '#F59E0B', strokeWidth: 2, strokeDasharray: '6 4' },
    labelBgStyle: { fill: '#FFFBEB' },
    labelStyle: { fill: '#92400E', fontSize: 11, fontWeight: 600 },
  },
  {
    id: 'obs-obs-int',
    source: 'sw-obs',
    sourceHandle: 'right',
    target: 'sw-int',
    type: 'smoothstep',
    label: 'Metricas',
    style: { stroke: '#A855F7', strokeWidth: 2 },
    labelBgStyle: { fill: '#FAF5FF' },
    labelStyle: { fill: '#6B21A8', fontSize: 11, fontWeight: 600 },
  },
];

const EDGES: Edge[] = [...CONTROL_EDGES, ...DATA_EDGES];

function SDNTopologyDiagramImpl(): JSX.Element {
  return (
    <div className="h-[460px] w-full overflow-hidden rounded-md border border-border bg-neutral-50">
      <ReactFlow
        nodes={NODES}
        edges={EDGES}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.15 }}
        proOptions={{ hideAttribution: true }}
        nodesDraggable
        zoomOnScroll
        panOnDrag
      >
        <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="#CBD5E1" />
        <Controls position="bottom-left" showInteractive={false} />
        <MiniMap
          pannable
          zoomable
          position="bottom-right"
          nodeColor={(n) =>
            n.type === 'controller'
              ? '#1A3A6E'
              : (n.data as SwitchData).role === 'integracion'
                ? '#1A3A6E'
                : (n.data as SwitchData).role === 'servicios'
                  ? '#10B981'
                  : (n.data as SwitchData).role === 'observabilidad'
                    ? '#F59E0B'
                    : '#CBD5E1'
          }
        />
      </ReactFlow>
    </div>
  );
}

export const SDNTopologyDiagram = memo(SDNTopologyDiagramImpl);
