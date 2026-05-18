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
 * Diagrama conceptual de la topologia SDN planificada del cluster
 * Neusi. NO conecta a un Ryu real. Layout manual para previsibilidad.
 */

type ControllerData = {
  label: string;
  sublabel: string;
};

type SwitchRole = 'cerebro' | 'broker' | 'produccion' | 'simulador' | 'datos' | 'auditoria';

type SwitchData = {
  ip: string;
  hostname: string;
  role: SwitchRole;
  description: string;
};

const ROLE_STYLE: Record<SwitchRole, { ring: string; chip: string; label: string }> = {
  cerebro:    { ring: 'border-primary',  chip: 'bg-primary text-primary-foreground',  label: 'Cerebro UrbIA' },
  broker:     { ring: 'border-success',  chip: 'bg-success text-success-foreground',  label: 'Broker MQTT' },
  produccion: { ring: 'border-warning',  chip: 'bg-warning text-accent-foreground',   label: 'Observabilidad' },
  simulador:  { ring: 'border-neutral-300', chip: 'bg-neutral-200 text-neutral-700',  label: 'Gateway IoT' },
  datos:      { ring: 'border-neutral-300', chip: 'bg-neutral-200 text-neutral-700',  label: 'Datos / NAS' },
  auditoria:  { ring: 'border-neutral-300', chip: 'bg-neutral-200 text-neutral-700',  label: 'Auditoria' },
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
        {data.role === 'cerebro' ? (
          <Cpu className="h-3.5 w-3.5 text-primary" aria-hidden="true" />
        ) : (
          <Server className="h-3.5 w-3.5 text-ink-muted" aria-hidden="true" />
        )}
        <span className="font-mono text-[11px] font-semibold text-ink">{data.ip}</span>
      </div>
      <span className="text-[10px] font-medium text-ink">{data.hostname}</span>
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
    data: { label: 'Ryu Controller', sublabel: '.102 (planificado · E10)' } as ControllerData,
    draggable: true,
  },
  {
    id: 'sw-100',
    type: 'switch',
    position: { x: X0 + 0 * DX, y: Y_SW },
    data: { ip: '.100', hostname: 'innova-produccion', role: 'produccion', description: '' } as SwitchData,
    draggable: true,
  },
  {
    id: 'sw-101',
    type: 'switch',
    position: { x: X0 + 1 * DX, y: Y_SW },
    data: { ip: '.101', hostname: 'innova-desarrollo', role: 'broker', description: '' } as SwitchData,
    draggable: true,
  },
  {
    id: 'sw-102',
    type: 'switch',
    position: { x: X0 + 2 * DX, y: Y_SW },
    data: { ip: '.102', hostname: 'innova-pruebas', role: 'cerebro', description: '' } as SwitchData,
    draggable: true,
  },
  {
    id: 'sw-103',
    type: 'switch',
    position: { x: X0 + 3 * DX, y: Y_SW },
    data: { ip: '.103', hostname: 'simulador1', role: 'simulador', description: '' } as SwitchData,
    draggable: true,
  },
  {
    id: 'sw-104',
    type: 'switch',
    position: { x: X0 + 4 * DX, y: Y_SW },
    data: { ip: '.104', hostname: 'camposjulca', role: 'datos', description: '' } as SwitchData,
    draggable: true,
  },
  {
    id: 'sw-105',
    type: 'switch',
    position: { x: X0 + 5 * DX, y: Y_SW },
    data: { ip: '.105', hostname: 'manjaro-daniel', role: 'auditoria', description: '' } as SwitchData,
    draggable: true,
  },
];

// Plano de control (controlador → switches), sin animacion.
const CONTROL_EDGES: Edge[] = ['sw-100', 'sw-101', 'sw-102', 'sw-103', 'sw-104', 'sw-105'].map((id) => ({
  id: `ctrl-${id}`,
  source: 'ctrl',
  target: id,
  type: 'smoothstep',
  style: { stroke: 'rgba(46, 90, 158, 0.55)', strokeWidth: 1.5, strokeDasharray: '4 3' },
}));

// Plano de datos (switch ↔ switch), animado con dash animation propio de react-flow.
const DATA_EDGES: Edge[] = [
  {
    id: 'mqtt-101-102',
    source: 'sw-101',
    sourceHandle: 'right',
    target: 'sw-102',
    type: 'smoothstep',
    label: 'MQTT 1883',
    animated: true,
    style: { stroke: '#10B981', strokeWidth: 2 },
    labelBgStyle: { fill: '#ECFDF5' },
    labelStyle: { fill: '#065F46', fontSize: 11, fontWeight: 600 },
  },
  {
    id: 'sim-103-102',
    source: 'sw-103',
    sourceHandle: 'left',
    target: 'sw-102',
    type: 'smoothstep',
    label: 'AMI sim',
    animated: true,
    style: { stroke: '#2E5A9E', strokeWidth: 2 },
    labelBgStyle: { fill: '#EFF6FF' },
    labelStyle: { fill: '#1A3A6E', fontSize: 11, fontWeight: 600 },
  },
  {
    id: 'bkp-102-104',
    source: 'sw-102',
    sourceHandle: 'right',
    target: 'sw-104',
    type: 'smoothstep',
    label: 'NFS backup',
    animated: true,
    style: { stroke: '#F59E0B', strokeWidth: 2, strokeDasharray: '6 4' },
    labelBgStyle: { fill: '#FFFBEB' },
    labelStyle: { fill: '#92400E', fontSize: 11, fontWeight: 600 },
  },
  {
    id: 'obs-100-102',
    source: 'sw-100',
    sourceHandle: 'right',
    target: 'sw-102',
    type: 'smoothstep',
    label: 'Metricas',
    animated: true,
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
              : (n.data as SwitchData).role === 'cerebro'
                ? '#1A3A6E'
                : (n.data as SwitchData).role === 'broker'
                  ? '#10B981'
                  : (n.data as SwitchData).role === 'produccion'
                    ? '#F59E0B'
                    : '#CBD5E1'
          }
        />
      </ReactFlow>
    </div>
  );
}

export const SDNTopologyDiagram = memo(SDNTopologyDiagramImpl);
