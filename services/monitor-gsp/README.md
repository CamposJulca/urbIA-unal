# monitor-gsp — Monitor espectral GSP

Núcleo doctoral de UrbIA: construcción del grafo AMI, Laplaciano y
transformada de Fourier sobre grafos (GFT) para la detección espectral de
anomalías.

Continúa el prototipo de `notebooks/01_gsp_hello_world.ipynb` (E6), que
validó la pipeline `A → L → L_norm → eigh → GFT` en NumPy puro sobre un
grafo de juguete de 10 nodos. Este módulo la lleva a los 150 medidores
reales de `ami_meters`.

## Estado

En construcción. Entrega actual: empaquetado (paso 1 de 10). El código del
constructor todavía no existe.

## Supuesto de vecindad geográfica

**La vecindad entre medidores se deriva de proximidad geográfica. Esto es
una aproximación de la topología eléctrica real, que no está disponible en
los datos.**

`ami_meters` sólo contiene `lat`, `lon` y `zona`. No hay catálogo de
transformadores, ni ramales de baja tensión, ni identificador de
alimentador. La columna `nodo_origen` registra de qué nodo del cluster
llegó el mensaje MQTT — procedencia de red, no conectividad eléctrica.

En consecuencia, una arista de este grafo significa "estos dos medidores
están geográficamente próximos", **no** "estos dos medidores comparten
conductor". Lo que el monitor puede afirmar sobre esa base es que un nodo
es discordante respecto de su vecindario espacial; no puede afirmar
propagación eléctrica de un evento.

Es un supuesto declarado de la tesis, no un detalle de implementación. Si
más adelante aparece el catálogo de transformadores, el constructor acepta
una topología externa sin cambiar su interfaz.

## Criterio de vecindad

k-NN simetrizado con **k = 4** por defecto, seis subgrafos independientes
(uno por zona), sin aristas de puente inter-zona.

La justificación, medida sobre los 150 medidores reales de `ami_meters`:
las seis zonas difieren en densidad por un factor 1,85 (de 20,8 a 38,5
medidores por km² de bounding box zonal), así que ningún radio único las
sirve bien. El radio mínimo que deja las seis zonas conexas es r = 399 m,
y a ese radio la dispersión de grados va de 2 en la_enea a 17 en
palogrande. k-NN se adapta por construcción y garantiza grado mínimo k, lo
que además evita los nodos hoja que el notebook E6 identificó como punto
ciego del detector de ventana abrupta.

El barrido completo de k que fija el valor por defecto está en el
docstring de `GraphConfig`, junto con la construcción exacta con la que se
midió. La comparación entra a un ADR en el paso 7.

El puente inter-zona existe como opción configurable, apagada por defecto,
para poder comparar ambas construcciones.

## Instalación

```bash
# Entorno de desarrollo del servicio
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[db,dev]"
```

El núcleo (`urbia_monitor_gsp.graph`) sólo depende de numpy y no importa
nada de base de datos, de modo que puede instalarse e importarse desde
`notebooks/.venv` sin el extra `[db]`:

```bash
notebooks/.venv/bin/pip install -e services/monitor-gsp
```

## Verificación

```bash
ruff check . && ruff format --check .
mypy
pytest --cov
```

Cobertura mínima exigida: 90% (CLAUDE.md §8.2, núcleo doctoral).
