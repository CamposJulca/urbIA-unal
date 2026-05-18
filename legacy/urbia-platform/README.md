# urbia-platform

Plataforma de monitoreo urbano distribuido con Edge/Fog Computing y SDN.

## Estructura

- `capa1/` — Simuladores de medidores eléctricos (Python, C++, Java)
- `docs/` — Documentación técnica por sprint

## Clúster NEUSI

| Nodo | IP | Rol |
|------|----|-----|
| innova-desarrollo | 192.168.0.101 | Broker / Orquestador |
| innova-pruebas | 192.168.0.102 | Backend / Experimentos |
| innova-produccion | 192.168.0.100 | Frontend / Gateway |
| simulador1 | 192.168.0.103 | Sensores Python |
| camposjulca | 192.168.0.104 | Sensores C++ |
| manjaro-daniel | 192.168.0.105 | Desarrollo / Sensores Java |
