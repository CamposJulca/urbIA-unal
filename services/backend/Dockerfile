# syntax=docker/dockerfile:1.7
#
# Imagen del servicio backend (UrbIA-UNAL).
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

# Construye la wheel del backend y descarga las wheels de todas sus
# dependencias en /build/dist para reutilizarlas en el runtime.
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

# Instalacion offline desde las wheels generadas en el builder.
COPY --from=builder /build/dist /tmp/dist
RUN pip install --no-cache-dir --no-index --find-links=/tmp/dist urbia-backend \
    && rm -rf /tmp/dist

USER urbia
WORKDIR /home/urbia

EXPOSE 8000

# La healthcheck llama a GET /health usando solo la stdlib de Python
# (sin curl). Tolera 5xx como fallo. start-period generoso para dar
# tiempo a que el pool DB y el cliente MQTT terminen de levantarse.
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).status == 200 else 1)" || exit 1

ENTRYPOINT ["urbia-backend"]
