# Generación por lotes de datasets de eventos. El paquete es una librería,
# pero el CLI que produce datasets a disco sí es un trabajo por lotes real:
# corre una vez, escribe la señal y su verdad de referencia, y termina.
FROM python:3.12-slim

WORKDIR /app

# monitor-gsp aporta ZoneGraph. La dependencia va en un solo sentido.
COPY services/monitor-gsp /app/services/monitor-gsp
COPY services/event-injector /app/services/event-injector

RUN pip install --no-cache-dir /app/services/monitor-gsp \
 && pip install --no-cache-dir /app/services/event-injector

# Los artefactos versionados que dan sentido a las cifras: el contrato del
# productor (límite duro) y el perfil medido (dónde vive la señal).
COPY data/schemas   /app/data/schemas
COPY data/profiles  /app/data/profiles
COPY data/topologies /app/data/topologies

ENTRYPOINT ["urbia-inject"]
CMD ["--help"]
