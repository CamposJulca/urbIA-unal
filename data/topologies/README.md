# Topologías AMI

Instantáneas versionadas de los conjuntos de medidores sobre los que se
miden los resultados del monitor GSP.

Estos archivos están acá **porque son el sustrato de los resultados, no
porque sean cómodos**. Una instrucción de cómo regenerar la topología no
sirve para replicar un resultado dentro de un año: hace falta la
topología. Todo número que aparezca en un docstring, en un README o en la
tesis debe poder rastrearse hasta uno de estos archivos.

## `manizales_150.json`

150 medidores sintéticos distribuidos en las seis zonas de Manizales.

| | |
|---|---|
| Versión | `manizales-v1` |
| Medidores | 150 |
| Zonas | centro 25, chipre 25, la_enea 25, palermo 25, palogrande 30, universitario 20 |
| Campos | `device_id`, `zona`, `lat`, `lon` (WGS84, grados decimales) |

### Procedencia

Exportado el **2026-08-07** de la tabla `ami_meters` de la base `urbia`
en el contenedor `urbia-postgres` de `.102` (`innova-pruebas`), con:

```sql
SELECT device_id, zona, lat, lon FROM ami_meters ORDER BY device_id;
```

La cadena completa de origen de esos datos:

```
medidores_manizales.json          catálogo estático, v1.0, fecha_generacion
  (urbia-platform, fuera           2026-04-20, seed_utilizada 42
   de este repositorio)            md5 3cb0f5b865a61ac7d8e4d3462fbbe110
        ↓
simulador MQTT (urbia-sim-*)      publica telemetría a urbia/manizales/#
        ↓
backend UrbIA                     UPSERT de los metadatos en ami_meters
        ↓
manizales_150.json                esta exportación
```

**Verificado el 2026-08-07:** los 150 `device_id`, sus coordenadas y sus
zonas coinciden exactamente con el catálogo origen. La ingesta no
introdujo deriva.

Esa cadena es justamente la razón de conservar la instantánea acá. El
catálogo origen vive **fuera de este repositorio**, en el árbol
`urbia-platform` de una sola máquina: no está versionado junto a la tesis,
puede cambiar y puede desaparecer. Lo que sostiene los resultados es este
archivo, no aquél.

### Naturaleza de los datos

**Datos sintéticos generados con semilla.** No son medidores reales ni
clientes reales; las coordenadas son posiciones simuladas dentro de los
*bounding boxes* declarados de cada zona. No hay ninguna implicación de
privacidad, y tampoco ninguna pretensión de que la geometría reproduzca
la red de distribución real de Manizales.

Vale acá el supuesto declarado en el README de `monitor-gsp`: una arista
del grafo significa "estos dos medidores están geográficamente próximos",
**no** "comparten conductor". La topología eléctrica real no está en los
datos.

### Quién lo consume

- `services/monitor-gsp/tests/test_builder.py` — tests de regresión que
  fijan las cifras de los docstrings (Fiedler por zona, multiplicidades
  espectrales, k mínimo, radio mínimo).
- Los docstrings de `graph/types.py` y `graph/geo.py`, y el README de
  `monitor-gsp`, cuyas cifras están medidas contra este archivo.

### Cómo verificar una cifra

```python
import json
from pathlib import Path
from urbia_monitor_gsp.graph import build_ami_graph, GraphConfig, MeterNode

datos = json.loads(Path("data/topologies/manizales_150.json").read_text())
meters = [MeterNode(**m) for m in datos["meters"]]

grafo = build_ami_graph(meters, GraphConfig(k=4))
for zona in grafo.zone_order:
    print(zona, grafo.zones[zona].stats.lambda_1)
```
