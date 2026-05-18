# UrbIA frontend-v2

Frontend React + Vite + TypeScript de UrbIA-UNAL. Reemplaza al
dashboard Streamlit anterior con un stack profesional, optimizado
y con identidad visual institucional UNAL.

## Stack

- Vite 5 + React 18 + TypeScript strict
- Tailwind CSS 3 con tokens UNAL (`tailwind.config.js`)
- shadcn/ui (componentes base copiados al repo en `src/components/ui/`)
- recharts (telemetria AMI)
- @xyflow/react (topologia SDN y nodos edge)
- @tanstack/react-query (cache de llamadas HTTP)
- react-router-dom (5 rutas con lazy loading)

## Modulos

- **M1 Telemetria AMI** (`/telemetria`) — datos REALES desde el
  backend FastAPI en `:8000`.
- **M2 SDN** (`/sdn`) — visualizacion conceptual con datos
  sinteticos hasta integracion con Ryu/Mininet (entregable E10).
- **M3 Edge** (`/edge`) — visualizacion conceptual de la
  computacion edge planificada (RPi5 .106 pendiente).

## Como correr

### Desarrollo (hot reload, puerto 3000)

Si tenes Node 20 instalado nativamente:

```bash
cd frontend-v2
npm install
npm run dev
```

Si no, podes usar Docker (recomendado en .102, sin sudo):

```bash
cd frontend-v2
docker run --rm -it -v "$PWD:/app" -w /app -p 3000:3000 \
  node:20-alpine sh -c "npm install && npm run dev -- --host 0.0.0.0"
```

### Produccion (nginx alpine via docker compose)

```bash
docker compose up -d frontend-v2
# Abrir http://localhost:3000
```

El servicio `frontend-v2` corre nginx alpine sirviendo el build
estatico en el puerto 80 del contenedor, mapeado a 3000 del host.

## Estructura

```
frontend-v2/
├── public/                # assets servidos al raiz (favicon, logos)
├── src/
│   ├── api/               # cliente HTTP del backend FastAPI
│   ├── components/
│   │   ├── layout/        # Header, Sidebar, Footer, PageLoader
│   │   ├── ui/            # shadcn primitives
│   │   ├── telemetry/     # graficos y tablas AMI
│   │   ├── sdn/           # diagrama react-flow SDN
│   │   └── edge/          # cards y diagrama edge
│   ├── pages/             # 5 rutas (Landing/Telemetry/SDN/Edge/About)
│   ├── lib/               # utilidades (cn, formatters)
│   ├── hooks/             # hooks reutilizables
│   ├── types/             # tipos compartidos
│   └── styles/            # globals.css con tokens UNAL
├── Dockerfile             # multi-stage build + nginx alpine
├── nginx.conf             # gzip, brotli, cache-control, /api proxy
├── tailwind.config.js     # paleta UNAL
└── vite.config.ts         # alias, chunking, compression
```

## Optimizacion

- Code splitting por ruta (lazy import).
- Chunks manuales: `react-vendor`, `data-vendor`, `charts`, `flow`.
- Compresion gzip y brotli aplicada por Vite en el build.
- Minify con terser (drop_console en produccion).
- React.memo en componentes pesados (graficos, topologias).
- Polling cada 2 s con AbortController y cancelacion al desmontar.
- Objetivo de bundle inicial: < 250 KB gzipped (verificable con
  `npm run analyze`).

## Notas

- El frontend Streamlit anterior (`services/frontend/`) se mantiene
  intacto como respaldo durante esta migracion.
- El backend FastAPI no se toca: este frontend solo lo consume vio
  cliente HTTP en `src/api/`.
