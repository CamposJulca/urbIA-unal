# syntax=docker/dockerfile:1.7
# UrbIA frontend-v2 — build multi-stage: Node 20 alpine para
# compilar el bundle de Vite + nginx 1.27 alpine para servirlo.

# ─── Stage 1: build ────────────────────────────────────────────
FROM node:20-alpine AS build

WORKDIR /app

# Capa de dependencias: cambia solo cuando cambia el manifest.
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

# Copia del resto del codigo y compilacion.
COPY tsconfig.json tsconfig.node.json vite.config.ts index.html postcss.config.js tailwind.config.js ./
COPY src ./src
COPY public ./public

# `npm run build` ya ejecuta `tsc --noEmit && vite build`.
RUN npm run build

# ─── Stage 2: runtime ──────────────────────────────────────────
FROM nginx:1.27-alpine AS runtime

# Quita la config por defecto y deja la nuestra como unica.
RUN rm /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Bundle compilado.
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD wget --quiet --tries=1 --spider http://localhost/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
