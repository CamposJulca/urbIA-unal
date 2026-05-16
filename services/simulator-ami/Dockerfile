# syntax=docker/dockerfile:1.7
#
# Imagen del servicio simulator-ami (UrbIA-UNAL).
# Multi-stage: el builder arma la wheel + todas las dependencias, el
# runtime instala sin red y corre como usuario no-root.

# ---------- Stage 1: builder -------------------------------------------------
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /build

COPY pyproject.toml README.md ./
COPY src ./src

# Construye la wheel del simulador y descarga las wheels de todas
# sus dependencias en /build/dist para reutilizarlas en el runtime.
RUN pip install --upgrade pip \
    && pip wheel --wheel-dir /build/dist .


# ---------- Stage 2: runtime -------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Usuario no-root con UID/GID fijos para reproducibilidad.
RUN groupadd --system --gid 10001 urbia \
    && useradd  --system --uid 10001 --gid 10001 \
                --home-dir /home/urbia --create-home \
                --shell /usr/sbin/nologin urbia

# Instalación offline desde las wheels generadas en el builder.
COPY --from=builder /build/dist /tmp/dist
RUN pip install --no-cache-dir --no-index --find-links=/tmp/dist urbia-simulator \
    && rm -rf /tmp/dist

USER urbia
WORKDIR /home/urbia

# main.py escribe su PID en /tmp/urbia-simulator.pid al arrancar.
# La healthcheck confirma que (a) el archivo existe y (b) el proceso
# sigue vivo. Sin paquetes extra: usa solo la stdlib de Python.
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import os; os.kill(int(open('/tmp/urbia-simulator.pid').read()), 0)" || exit 1

ENTRYPOINT ["urbia-simulator"]
