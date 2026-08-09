# Observabilidad del cluster Neusi

Prometheus y Grafana en **neusi-obs**, node_exporter en los seis nodos.

> **Estado: escrito y no desplegado.** Desde neusi-stage no hay acceso SSH
> saliente —verificado el 2026-08-09: `publickey` denegado en los cinco
> nodos remotos, con `pruebas`, `camposjulca` y `neusi`—. Todo lo de acá
> está listo para correrse desde una máquina con llaves; hoy la única
> candidata es neusi-ops.

---

## 1. Qué se despliega

| Dónde | Qué | Cómo |
|---|---|---|
| neusi-obs | Prometheus + Grafana | `docker-compose.yml` |
| los seis nodos | node_exporter 1.8.2 | binario + systemd, vía `../ansible/node_exporter.yml` |

**Binario y no contenedor** para node_exporter. Lo manda neusi-edge-x86:
3,3 GB de RAM y disco mecánico, donde bajar capas de Docker y sostener el
runtime cuesta más que un binario de 20 MB. Va igual en los seis para que el
playbook y el diagnóstico sean uno solo.

---

## 2. Dimensionamiento

### 2.1 Lo que está medido

Medido en **neusi-stage** el 2026-08-09, node_exporter 1.8.2 con colectores
por defecto, contando líneas de muestra de `/metrics`:

| | |
|---|---|
| Series expuestas | **1.605** |
| Métricas distintas | 307 |
| Series de red | 719, sobre 20 interfaces |
| Series de CPU | 128, sobre 16 núcleos |

neusi-stage es el nodo **más pesado** de los seis —16 núcleos y 8 redes
Docker—, así que usarlo como cota para todos es conservador. **Los otros
cinco no están medidos**: no hay acceso. El playbook imprime el conteo por
nodo al terminar, justamente para poder cerrar este número con datos.

### 2.2 Lo que es cálculo

Los bytes por muestra son la cifra documentada de Prometheus (1–2 B tras
compresión), no una medición nuestra.

```
6 nodos × 1.605  +  ~1.000 de Prometheus  ≈  10.600 series
10.600 series × 5.760 muestras/día         =  61,1 M muestras/día
```

| Bytes/muestra | Por día | 30 d | **90 d** | 180 d |
|---|---|---|---|---|
| 1,5 B | 92 MB | 2,7 GB | **8,2 GB** | 16,5 GB |
| 2,0 B | 122 MB | 3,7 GB | **11,0 GB** | 22,0 GB |

Sobre los **79 GB libres** de neusi-obs, 90 días son el **10–14 %**.

### 2.3 Las decisiones que salen de ahí

**Retención 90 días.** Cubre un ciclo completo de experimentos y permite
comparar el comportamiento del cluster antes y después de cambios en el
monitor.

**Tope duro de 20 GB además del temporal.** Es la red de seguridad: ~2× el
cálculo, y hace imposible llenar el disco aunque la estimación esté mal o
aparezca una explosión de cardinalidad. Prometheus borra los bloques más
viejos al tocar el tope.

**Interfaces `veth`, `br-` y `docker` excluidas en node_exporter.** De las
1.605 series, 719 son de red, y en un nodo con Docker la mayoría son `veth`
que nacen y mueren con cada contenedor. Eso no es volumen: es *churn* de
cardinalidad, que es lo que degrada un TSDB. Se corta en el origen y no con
`relabel`, para que ni siquiera se transmitan.

**Disco local, nunca NFS.** El TSDB hace `mmap` y `fsync` sobre sus bloques;
sobre NFS es un modo de corrupción conocido y sin soporte upstream. El NAS
de neusi-data entra como destino de respaldo, no como almacenamiento vivo.

---

## 3. Cómo verificar el dimensionamiento contra lo real

El cálculo de §2.2 hay que cerrarlo con medición. **A los 7 días de
desplegar**, sobre neusi-obs:

```bash
# Bytes por muestra, de verdad
docker exec urbia-prometheus promtool tsdb analyze /prometheus | head -20

# Tamaño en disco
docker run --rm -v urbia_prometheus_data:/d alpine du -sh /d

# Series vivas
curl -s 'http://192.168.40.10:9090/api/v1/query?query=prometheus_tsdb_head_series' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["data"]["result"][0]["value"][1])'

# Muestras por segundo ingeridas
curl -s 'http://192.168.40.10:9090/api/v1/query?query=rate(prometheus_tsdb_head_samples_appended_total[1h])' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["data"]["result"][0]["value"][1])'
```

Extrapolar el tamaño de 7 días a 90 y contrastarlo contra la tabla. **Si se
aparta más de 2×, corregir este README con la cifra medida** y ajustar la
retención. Lo que no hay que hacer es dejar la estimación escrita como si
fuera medición.

---

## 4. Qué queda cubierto y qué no

**Cubierto:** CPU, memoria, disco y red por nodo, en los seis.

**Preparado y apagado:** el job `monitor-gsp` está escrito y comentado en
`prometheus.yml`. El servicio del monitor todavía no existe; cuando exponga
`/metrics` en `:9101` se descomenta. Va como job aparte porque su
cardinalidad la manda el grafo —zonas y medidores—, no la máquina, y
conviene poder acotarla sin tocar la de los nodos.

**No cubierto, y a decidir:**

* **Sin alertas.** No hay `alertmanager` ni reglas. Un disco llenándose no
  avisa: hay que mirarlo.
* **Sin dashboards versionados.** Sólo el datasource se provisiona. Los
  paneles que alguien arme a mano en Grafana viven en su volumen y no en el
  repo.
* **Grafana sin TLS ni proxy.** Queda expuesto en `:3000` dentro de la red
  del cluster. Aceptable en red cerrada; no para exponer afuera.
* **Los cinco nodos remotos, sin medir.** El conteo de series de §2.1 es de
  uno solo.
