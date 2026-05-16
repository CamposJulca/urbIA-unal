# syntax=docker/dockerfile:1.7
#
# Imagen del servicio frontend (UrbIA-UNAL).
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

# Construye la wheel del paquete urbia_frontend y descarga las wheels
# de todas sus dependencias en /build/dist para reutilizarlas offline.
RUN pip install --upgrade pip \
    && pip wheel --wheel-dir /build/dist .


# ---------- Stage 2: runtime -------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

# Usuario no-root con UID/GID fijos para reproducibilidad.
RUN groupadd --system --gid 10001 urbia \
    && useradd  --system --uid 10001 --gid 10001 \
                --home-dir /home/urbia --create-home \
                --shell /usr/sbin/nologin urbia

# Instalacion offline desde las wheels generadas en el builder.
COPY --from=builder /build/dist /tmp/dist
RUN pip install --no-cache-dir --no-index --find-links=/tmp/dist urbia-frontend \
    && rm -rf /tmp/dist

# El script principal y las paginas viven al lado, beside main.py, para
# que Streamlit descubra pages/ por convencion. El paquete urbia_frontend
# ya está instalado en site-packages (desde la wheel) y main.py / pages
# lo importan como cualquier libreria.
WORKDIR /home/urbia
COPY --chown=urbia:urbia main.py ./main.py
COPY --chown=urbia:urbia pages ./pages

USER urbia

EXPOSE 8501

# Streamlit expone /_stcore/health para healthchecks. start-period
# generoso por la inicializacion del runtime de Streamlit.
HEALTHCHECK --interval=15s --timeout=5s --start-period=25s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=3).status == 200 else 1)" || exit 1

ENTRYPOINT ["streamlit", "run", "main.py", \
            "--server.port=8501", \
            "--server.address=0.0.0.0"]
