FROM python:3.12-slim

WORKDIR /app

COPY capa1/simuladores/python/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY capa1/simuladores/python/src/ ./src/
COPY capa1/comun/ ./comun/

ENV BROKER_HOST=192.168.0.101
ENV BROKER_PORT=1883
ENV NODE_ID=192.168.0.103
ENV INTERVALO_SEG=5
ENV LOG_LEVEL=INFO
ENV SEED_BASE=42

RUN mkdir -p logs

CMD ["python3", "src/main.py"]
