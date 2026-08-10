# syntax=docker/dockerfile:1.7
#
# Imagen del monitor GSP (UrbIA-UNAL).
# Multi-stage: el builder arma la wheel + sus dependencias, el runtime
# instala sin red y corre como usuario no-root.
#
# El contexto de build es la RAIZ DEL REPOSITORIO, no este directorio.
# La razon es que el servicio necesita dos cosas que viven fuera de
# `services/monitor-gsp/`:
#
#   data/calibrations/  el umbral congelado, sin el cual no arranca
#   data/topologies/    la topologia sobre la que se calibro
#
# Se copian a la imagen en vez de montarse porque son parte del punto de
# operacion: una imagen que dependiera de un volumen podria arrancar
# contra otra calibracion sin que la etiqueta de la imagen cambiara, y
# entonces la version de la imagen dejaria de identificar lo que corre.

# ---------- Stage 1: builder -------------------------------------------------
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /build

COPY services/monitor-gsp/pyproject.toml services/monitor-gsp/README.md ./
COPY services/monitor-gsp/src ./src

# El extra [service] trae paho-mqtt, prometheus-client, psycopg y
# pydantic-settings. El nucleo por si solo no los necesita.
RUN pip install --upgrade pip \
    && pip wheel --wheel-dir /build/dist ".[service]"


# ---------- Stage 2: runtime -------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN groupadd --system --gid 10001 urbia \
    && useradd  --system --uid 10001 --gid 10001 \
                --home-dir /home/urbia --create-home \
                --shell /usr/sbin/nologin urbia

COPY --from=builder /build/dist /tmp/dist
RUN pip install --no-cache-dir --no-index --find-links=/tmp/dist "urbia-monitor-gsp[service]" \
    && rm -rf /tmp/dist

# Artefactos versionados de los que dependen todos los resultados.
# En el contenedor el paquete vive en site-packages, asi que la
# resolucion de rutas relativas contra la raiz del repo no aplica: la
# calibracion se pasa por ruta ABSOLUTA en CALIBRATION_PATH.
COPY data/calibrations /opt/urbia/data/calibrations
COPY data/topologies   /opt/urbia/data/topologies

ENV CALIBRATION_PATH=/opt/urbia/data/calibrations/manizales_scan_v1.json

USER urbia
WORKDIR /home/urbia

# Exportador de Prometheus. El job vive en infra/observability/prometheus.yml.
EXPOSE 9101

# La healthcheck raspa /metrics con la stdlib (sin curl). Que el
# exportador responda prueba que el proceso esta vivo y que el hilo del
# servidor no murio; que ademas este detectando se ve en las series, no
# aca. start-period cubre la construccion del grafo y la verificacion de
# topologia contra PostgreSQL.
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:9101/metrics', timeout=3).status == 200 else 1)" || exit 1

ENTRYPOINT ["urbia-monitor-gsp"]
