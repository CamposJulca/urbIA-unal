# monitor-gsp — Monitor espectral GSP

Núcleo doctoral de UrbIA: construcción del grafo AMI, Laplaciano y
transformada de Fourier sobre grafos (GFT) para la detección espectral de
anomalías.

Continúa el prototipo de `notebooks/01_gsp_hello_world.ipynb` (E6), que
validó la pipeline `A → L → L_norm → eigh → GFT` en NumPy puro sobre un
grafo de juguete de 10 nodos. Este módulo la lleva a los 150 medidores
reales de `ami_meters`.

## Estado

En construcción, paso 6 de 10. El ciclo dato → grafo → señal filtrada ya
está cerrado:

| Módulo | Qué hace | Depende de |
|---|---|---|
| `graph/geo` | Proyección WGS84 a plano local en metros y distancias | numpy |
| `graph/types` | Contrato: `MeterNode`, `GraphConfig`, `ZoneGraph`, `AmiGraph` | numpy |
| `graph/spectral` | `A → L → L_norm → eigh → GFT`, sobre matrices | numpy |
| `graph/builder` | De medidores a subgrafos zonales con espectro | numpy |
| `graph/filter` | Difuminador: filtro paso-bajo `exp(−λ/(τ·λmax))` y métricas | numpy |
| `db/` | Lectura de `ami_meters` | extra `[db]` |

La dependencia va en un solo sentido: `db` importa de `graph` y nunca al
revés. Por eso el núcleo depende sólo de numpy y puede correr en un nodo
de borde sin driver de base de datos.

```python
# desde la base
from urbia_monitor_gsp.db import load_ami_graph
grafo = load_ami_graph()

# o sin base, desde medidores en memoria o un JSON de topología
from urbia_monitor_gsp.graph import build_ami_graph, gft
grafo = build_ami_graph(meters)

zona = grafo.zones["la_enea"]
x_hat = gft(lecturas, zona.eigenvectors)     # espectro de la señal

# Difuminador: atenúa el desacuerdo entre vecinos
from urbia_monitor_gsp.graph import diffuse, dirichlet_energy
suave = diffuse(zona, lecturas, tau=0.5)
dirichlet_energy(zona, suave) < dirichlet_energy(zona, lecturas)   # True
```

Falta: detector espectral y wavelet multiescala. El puente inter-zona está
declarado en `GraphConfig` pero no implementado; encenderlo levanta
`InvalidGraphConfigError`.

## Mediciones pendientes

Lo que hoy está decidido pero **no medido**, para que no se lea como
resultado (ADR-003 §4.3 y §6):

- **Pesos binarios contra gaussianos sobre los 150 medidores.** El defecto
  es binario por continuidad con el notebook E6 y por simplicidad
  interpretativa, no porque se haya comparado. Los gaussianos están
  implementados y probados en corrección —ponderan entre 0 y 1, pesan menos
  a mayor distancia, derivan σ de la mediana de las aristas— pero sólo
  sobre rejillas sintéticas de juguete. Falta medir sobre la topología
  real cómo se mueven el espectro, el Fiedler por zona y la detección de
  la anomalía inyectada al pasar de unos a otros, y si σ derivado de la
  mediana es defendible o hay que barrerlo. Es la única decisión del
  ADR-003 que no tiene medición detrás.
- **Efecto del Difuminador sobre anomalías extendidas.** Todo lo medido usa
  un pico en un único medidor. El caso de varios medidores vecinos
  afectados a la vez —donde un filtro definido por la vecindad debería
  lucirse— requiere el inyector de eventos correlacionados, que no existe.
- **Grafo geográfico contra grafo eléctrico.** Cuando aparezca el catálogo
  de transformadores: cuántas de las 369 aristas actuales sobreviven, y
  cuánto cambia el diagnóstico del detector. Es lo que convertiría el
  supuesto de vecindad geográfica de limitación declarada en error acotado.

El Difuminador implementa el exponente **negativo**, `exp(−λ/(τ·λmax))`.
La formulación publicada en la tesis de Aristizábal (2022, Cap. 3) lo
escribe positivo, con lo que amplifica la alta frecuencia en vez de
atenuarla; el docstring de `graph/filter` explica la corrección y
`experiments/difuminador-tau/RESULTADOS.md` la mide sobre los 150
medidores.

Los números de este README y de los docstrings están medidos contra
`data/topologies/manizales_150.json`, la topología versionada de los 150
medidores, y fijados como tests de regresión en `tests/test_builder.py`.

## Centrar la señal: no para `E_D`, y nunca por la media

El modo de frecuencia cero se lleva entre el 97,8 % y el 99,1 % de la
energía de una señal AMI, así que cualquier lectura por modo o por banda
queda dominada por la media. Centrar antes de analizar es lo natural, y
tiene dos trampas medidas:

| Operación | Coeficiente del modo 0 | `E_D` en centro |
|---|---|---|
| Cruda | 98,34 % de la energía | 45,0239 |
| `x − mean(x)` | \|x̂₀\| = 0,153 — **no lo anula** | **22,0260** |
| `x − (u₀ᵀx)·u₀` | ≈ 2e-14 | 45,0239 — idéntico |

El núcleo de `L_norm` es `D^(1/2)·1`, proporcional a `√dᵢ`, **no** el vector
constante: `cos(u₀, √d) = 1,000000000000` contra `cos(u₀, 1) = 0,992` a
0,996. Restar la media no remueve el modo cero, y además **corrompe la
energía de Dirichlet** —en centro la baja a menos de la mitad, en
universitario la sube de 19,72 a 24,76— porque la constante no es un
elemento del núcleo.

**La regla:**

* Con `dirichlet_energy` o cualquier detector sobre `L_norm·x`: **no
  centrar**. `E_D` ya es invariante al modo cero, y centrar sólo puede
  romper esa invariancia.
* Con GFT, bandas o cualquier lectura por modo: **proyectar fuera de
  `u₀`**, nunca restar la media.

El detalle completo está en el docstring de `graph/filter`. Se documenta acá
porque es un error que produce resultados plausibles y falsos.

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

## Configuración de la base

Sólo la usa `urbia_monitor_gsp.db`. Mismos nombres de variable que
`services/backend`, para que un único `.env` sirva a los dos:

| Variable | Por defecto | Qué es |
|---|---|---|
| `POSTGRES_HOST` | `postgres` | DNS interno de docker; fuera del compose, sobreescribir |
| `POSTGRES_PORT` | `5432` | |
| `POSTGRES_DB` | `urbia` | |
| `POSTGRES_USER` | `urbia` | |
| `POSTGRES_PASSWORD` | *(vacío)* | Nunca se registra en el log |
| `CONNECT_TIMEOUT_S` | `10` | Un monitor de borde no puede colgarse esperando |

## Verificación

```bash
ruff check . && ruff format --check .
mypy
pytest --cov                    # sin base de datos
```

Cobertura mínima exigida: 90% (CLAUDE.md §8.2, núcleo doctoral).

Los tests marcados `integration` necesitan PostgreSQL real y quedan fuera
de la corrida normal. Verifican que `ami_meters` siga coincidiendo con
`data/topologies/manizales_150.json`: si fallan, la base cambió y las
cifras de los docstrings dejaron de describir el padrón vivo.

```bash
POSTGRES_HOST=localhost POSTGRES_PASSWORD=... pytest -m integration
```
