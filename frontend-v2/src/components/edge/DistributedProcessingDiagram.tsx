import { memo } from 'react';

/**
 * Diagrama SVG inline del flujo de procesamiento distribuido:
 *
 *   [Simulador AMI] ─MQTT raw──> [Borde ARM] ─Anomalias─┐
 *                  └─MQTT raw (fallback)─> [Borde x86] ─Anomalias agregadas─┐
 *                                                            ├─> [Backend FastAPI] ─API futura─> [Consola]
 *
 * Se usa SVG inline (sin xyflow) para minimizar peso del bundle.
 * Flechas animadas con strokeDashoffset.
 */

const W = 1080;
const H = 320;

type Box = {
  id: string;
  x: number;
  y: number;
  w: number;
  h: number;
  title: string;
  subtitle: string;
  fill: string;
  stroke: string;
  textColor: string;
  dashed?: boolean;
  tooltip: string;
};

const BOXES: readonly Box[] = [
  {
    id: 'sim',
    x: 20, y: 130, w: 170, h: 60,
    title: 'Simulador AMI',
    subtitle: '10 medidores · MQTT',
    fill: '#EFF6FF', stroke: '#2E5A9E', textColor: '#1A3A6E',
    tooltip: 'Simulador de 10 medidores. Publicaba telemetria DLMS-JSON a 10 msg/s sobre el broker MQTT del cluster; la ingesta esta detenida.',
  },
  {
    id: 'edge',
    x: 320, y: 40, w: 200, h: 80,
    title: 'Nodo de borde ARM',
    subtitle: 'hardware pendiente',
    fill: '#FFFBEB', stroke: '#F59E0B', textColor: '#92400E',
    dashed: true,
    tooltip: 'Nodo de borde planificado. Ejecutara el filtro pasaaltos H(λ)=λ sobre el subgrafo zonal local para deteccion en hojas.',
  },
  {
    id: 'central',
    x: 320, y: 200, w: 200, h: 80,
    title: 'Nodo de borde x86',
    subtitle: 'agregacion central',
    fill: '#EFF6FF', stroke: '#1A3A6E', textColor: '#1A3A6E',
    tooltip: 'Agregacion central prevista del monitor GSP. Sin implementar: ningun nodo ejecuta el monitor hoy.',
  },
  {
    id: 'api',
    x: 660, y: 130, w: 180, h: 60,
    title: 'Backend FastAPI',
    subtitle: 'nodo de integracion',
    fill: '#ECFDF5', stroke: '#10B981', textColor: '#065F46',
    tooltip: 'Backend de UrbIA. Hoy persiste y expone telemetria AMI; la persistencia de anomalias y su endpoint REST estan sin implementar.',
  },
  {
    id: 'front',
    x: 900, y: 130, w: 160, h: 60,
    title: 'Frontend',
    subtitle: 'consola de operacion',
    fill: '#F5F3FF', stroke: '#A855F7', textColor: '#6B21A8',
    tooltip: 'Este mismo dashboard, consumiendo el endpoint de anomalias cuando exista.',
  },
];

type Arrow = {
  id: string;
  from: string;
  to: string;
  label: string;
  variant: 'solid' | 'dashed';
  color: string;
};

const ARROWS: readonly Arrow[] = [
  { id: 'sim-edge',     from: 'sim',     to: 'edge',    label: 'MQTT raw',                variant: 'solid',  color: '#F59E0B' },
  { id: 'sim-central',  from: 'sim',     to: 'central', label: 'MQTT raw (fallback)',     variant: 'dashed', color: '#1A3A6E' },
  { id: 'edge-api',     from: 'edge',    to: 'api',     label: 'Anomalias detectadas',    variant: 'solid',  color: '#F59E0B' },
  { id: 'central-api',  from: 'central', to: 'api',     label: 'Anomalias agregadas',     variant: 'solid',  color: '#1A3A6E' },
  { id: 'api-front',    from: 'api',     to: 'front',   label: 'API de anomalias (futura)', variant: 'dashed', color: '#10B981' },
];

function boxById(id: string): Box {
  const b = BOXES.find((x) => x.id === id);
  if (!b) throw new Error(`box ${id} no existe`);
  return b;
}

function rightEdge(b: Box): { x: number; y: number } {
  return { x: b.x + b.w, y: b.y + b.h / 2 };
}
function leftEdge(b: Box): { x: number; y: number } {
  return { x: b.x, y: b.y + b.h / 2 };
}

function DistributedProcessingDiagramImpl(): JSX.Element {
  return (
    <div className="w-full overflow-x-auto">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="h-[320px] min-w-[900px] w-full"
        role="img"
        aria-label="Diagrama del procesamiento distribuido GSP"
      >
        <defs>
          {ARROWS.map((a) => (
            <marker
              key={`mk-${a.id}`}
              id={`arrow-${a.id}`}
              viewBox="0 0 10 10"
              refX="9"
              refY="5"
              markerWidth="6"
              markerHeight="6"
              orient="auto-start-reverse"
            >
              <path d="M 0 0 L 10 5 L 0 10 z" fill={a.color} />
            </marker>
          ))}
        </defs>

        {/* Flechas */}
        {ARROWS.map((a) => {
          const src = rightEdge(boxById(a.from));
          const dst = leftEdge(boxById(a.to));
          const cx = (src.x + dst.x) / 2;
          const d = `M ${src.x} ${src.y} C ${cx} ${src.y}, ${cx} ${dst.y}, ${dst.x} ${dst.y}`;
          return (
            <g key={a.id}>
              <path
                d={d}
                fill="none"
                stroke={a.color}
                strokeWidth={2}
                strokeDasharray={a.variant === 'dashed' ? '6 4' : '6 6'}
                markerEnd={`url(#arrow-${a.id})`}
              >
                <animate
                  attributeName="stroke-dashoffset"
                  from="0"
                  to={a.variant === 'dashed' ? '-10' : '-12'}
                  dur="0.9s"
                  repeatCount="indefinite"
                />
              </path>
              {/* Etiqueta sobre la mitad del arco */}
              <g transform={`translate(${cx} ${(src.y + dst.y) / 2 - 10})`}>
                <rect
                  x="-70"
                  y="-10"
                  width="140"
                  height="20"
                  rx="6"
                  ry="6"
                  fill="white"
                  stroke={a.color}
                  strokeOpacity="0.4"
                />
                <text
                  x="0"
                  y="4"
                  textAnchor="middle"
                  fontFamily="Inter, system-ui, sans-serif"
                  fontSize="10"
                  fontWeight="600"
                  fill={a.color}
                >
                  {a.label}
                </text>
              </g>
            </g>
          );
        })}

        {/* Cajas */}
        {BOXES.map((b) => (
          <g key={b.id}>
            <rect
              x={b.x}
              y={b.y}
              width={b.w}
              height={b.h}
              rx="10"
              ry="10"
              fill={b.fill}
              stroke={b.stroke}
              strokeWidth={b.dashed ? 2 : 1.5}
              strokeDasharray={b.dashed ? '8 4' : undefined}
            >
              <title>{b.tooltip}</title>
            </rect>
            <text
              x={b.x + b.w / 2}
              y={b.y + 24}
              textAnchor="middle"
              fontFamily="Inter, system-ui, sans-serif"
              fontSize="13"
              fontWeight="700"
              fill={b.textColor}
            >
              {b.title}
            </text>
            <text
              x={b.x + b.w / 2}
              y={b.y + 44}
              textAnchor="middle"
              fontFamily="Inter, system-ui, sans-serif"
              fontSize="11"
              fill={b.textColor}
              opacity="0.7"
            >
              {b.subtitle}
            </text>
            {b.id === 'edge' && (
              <text
                x={b.x + b.w / 2}
                y={b.y + b.h - 8}
                textAnchor="middle"
                fontFamily="Inter, system-ui, sans-serif"
                fontSize="9"
                fontWeight="600"
                fill="#92400E"
              >
                ▢ filtro H(λ)=λ por subgrafo zonal
              </text>
            )}
            {b.id === 'central' && (
              <text
                x={b.x + b.w / 2}
                y={b.y + b.h - 8}
                textAnchor="middle"
                fontFamily="Inter, system-ui, sans-serif"
                fontSize="9"
                fontWeight="600"
                fill="#1A3A6E"
              >
                ▣ agregacion global del cluster
              </text>
            )}
          </g>
        ))}
      </svg>
    </div>
  );
}

export const DistributedProcessingDiagram = memo(DistributedProcessingDiagramImpl);
