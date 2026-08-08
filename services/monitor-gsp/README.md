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

Falta: wavelet multiescala. El puente inter-zona está declarado en
`GraphConfig` pero no implementado; encenderlo levanta
`InvalidGraphConfigError`.

## Detector de eventos colectivos

`detector/` contrasta cada vecindario del grafo contra el resto de su zona,
sobre una ventana promediada, y reporta **qué nodos** marcó.

```python
from urbia_monitor_gsp.detector import CollectiveScanDetector, DetectorConfig

detector = CollectiveScanDetector(zona, sigma_spatial=4.4012,
                                  config=DetectorConfig(window=16))
detector.calibrate(seed=20260808)
detecciones = detector.detect(lecturas)          # (T, n)
detecciones[0].device_ids                        # los nodos marcados
detector.node_mask(detecciones, len(lecturas))   # para la matriz de confusión
```

Cada decisión sale de una medición: `experiments/firma-espectral/`,
`experiments/magnitud-duracion/` y `experiments/detector-colectivo/`.

| Decisión | Por qué |
|---|---|
| Escaneo local, no escalar por zona | Todo escalar global da AUC 0,48–0,57 sobre eventos colectivos |
| Contraste de dos muestras sobre bolas | AUC 0,73–0,81 contra 0,65–0,80 del umbral por medidor |
| Sobre ventana promediada | Integrar N instantes mejora la detección en `√N` |
| Sin centrado de ninguna clase | El contraste ya es invariante al nivel medio |
| Radios 1 y 2 | Un evento a profundidad 2 abarca ~12 nodos; una bola de radio 1 tiene ~6 |

### Dónde pierde

**Es peor que un umbral por medidor en anomalías individuales.** No es un
defecto a corregir: es el alcance del método. Medido sobre un instante al
1 % de falsos positivos:

| Caso | Umbral por medidor | Este detector |
|---|---|---|
| Anomalía individual de +6σ | **99,0 %** | 33,4 % |
| Evento colectivo, profundidad 2 | 6,7 % | **18,9 %** |

La anomalía individual es un impulso en el dominio de los nodos —79,2 % de
su energía en banda alta— y promediar una bola de vecinos la diluye. El
evento colectivo es una meseta sobre un subconjunto conexo —16–19 % en banda
alta— y promediar la bola es lo que lo concentra.

**Un monitor completo necesita los dos**: una regla por medidor para lo
puntual y este escaneo para lo colectivo.

### Sobre el punto de operación

`window=16` por defecto, configurable. Elegido por **ventaja sobre el
umbral**, no por detección absoluta. Medido sobre σ=0,5 al 1 % de falsos
positivos:

| N | Escaneo | Umbral | Ventaja |
|---|---|---|---|
| **16** | 93,6 % | 54,8 % | **+38,8** |
| 32 | 99,9 % | 90,2 % | +9,7 |
| 64 | 100 % | 100 % | +0,0 |

**Reverificado en condición realista** —ventana deslizante, evento en
posición sorteada, FPR calibrado por señal— en
`experiments/detector-deslizante/`: N=16 sobrevive y la ventaja **sube** a
+49,6 (escaneo 79,4 % contra umbral 29,8 %). Deslizar le cuesta más al
umbral, que toma el máximo sobre 49 ventanas × 25 medidores casi
independientes, que al escaneo, cuyas 41 bolas se solapan. Los experimentos
con ventana conocida estaban **subestimando** la ventaja.

En ese punto el detector además localiza bien: **recall por nodo 92,1 %,
precisión 77,2 %, F1 0,839**. Con radios {1} solamente caen a 49,2 %,
67,8 % y 0,570.

La ventaja obedece a **`σ·√N ≈ 2`**: es máxima justo por debajo del punto
donde un umbral por medidor empieza a funcionar. De ahí una regla
transferible: ante un evento de magnitud σ conocida, la ventana que más
aporta es `N ≈ (2/σ)²`. Perseguir detección lleva a N=64, donde el método
no aporta nada.

### Dos opciones apagadas por defecto, con medición detrás

`project_out_kernel` proyecta fuera de `u₀` antes de puntuar. **Cuesta de 40
a 77 puntos de detección** (78,8–97,2 % → 19,0–55,0 % sobre las seis zonas a
σ=1,0 y N=5). El contraste ya es invariante al nivel medio, así que la
proyección no aporta nada y sí introduce un sesgo determinista por bola:
`u₀ᵀx` vale ~1 092 en una señal de 220 V y, multiplicado por el desbalance
de grado del grupo, llega a 42σ. El daño crece con la ventana, porque el
sesgo es fijo y el ruido baja como `√N`.

`prefilter_tau` aplica el Difuminador antes de puntuar. **Medido, y
rechazado.** Sube la detección de 55,8 % a 100 %, pero la ganancia es
espuria: el filtro rompe la invariancia a sumar una constante, porque
`diffuse(1)` no es constante —va de 0,8524 a 1,2426 con τ=0,05—. Sobre un
**modo común**, toda la zona corrida 2σ, que el detector no debe marcar:

| | Sin filtro | τ=0,05 | τ=0,447 | τ=1,0 |
|---|---|---|---|---|
| Modo común marcado | 0,0–0,7 % | 100 % | 100 % | 100 % |

Convierte un detector de discordancia local en uno de nivel medio.

De paso deja un resultado propio: **el τ óptimo depende del uso**. Para
filtrar el rango estable es `[0,447, 2,239]`; para detectar la meseta llega
hasta τ=0,05, en plena región que para filtrar se declaró degenerada. El
Afinador tiene que saber para qué está ajustando.

### Advertencia: cuatro veces un argumento de invariancia sonó correcto y falló

Quien vaya a tocar el preprocesado de esta ruta debería leer esto antes.
**Cuatro veces en este desarrollo se razonó sobre invariancia o sobre
filtrado, el argumento era formalmente correcto, y la conclusión que se
sacó de él resultó falsa al medirla.** No son cuatro descuidos distintos:
es el mismo error cuatro veces.

**1. "`E_D` es invariante al modo cero, así que no hay que centrar."** La
invariancia es cierta. La conclusión, falsa: `E_D` es invariante al
**núcleo** —la dirección `√d`— y no al **nivel medio**. Una señal AMI es
sobre todo nivel medio, y una plana de 220 V da `E_D_norm` de 8 876 a
21 672 según la zona contra ~286 que aporta el ruido. El 98 % de la medida
era una penalización al estado normal.

**2. "Centrar por la media corrompe `E_D`."** También sonaba bien: restar
la media cambia el valor de 45,02 a 22,03, y un cambio así parece daño.
Era la lectura equivocada. Lo que remueve es un término de estorbo, y
removerlo sube el AUC de detección de 0,661 a 0,986.

**3. "El contraste de dos muestras ya es invariante al nivel medio, así que
proyectar fuera de `u₀` da lo mismo."** La invariancia vuelve a ser cierta
y la conclusión vuelve a ser falsa. Proyectar cuesta de 40 a 77 puntos de
detección, porque `u₀ ∝ √d` **no** es constante: la proyección deja un
sesgo determinista de hasta 42σ por bola, y el máximo cae siempre en la
misma sin importar los datos.

**4. "La firma colectiva es de baja frecuencia y el Difuminador es un
paso-bajo, luego debería ayudar."** Y ayuda, en apariencia: la detección
sube de 55,8 % a 100 %. Pero el filtro rompe la invariancia a sumar una
constante —`diffuse(1)` va de 0,8524 a 1,2426— y con eso marca el 100 % de
los modos comunes, que debe ignorar. La ganancia no era detectar mejor: era
dejar de distinguir.

**El patrón.** Una invariancia siempre lo es **respecto de un subespacio**.
Decir "es invariante" sin decir *a qué* invita a concluir que cualquier
preprocesado es inocuo, y no lo es: basta que la transformación toque una
dirección que el subespacio no contiene. Y el estado físicamente normal de
esta señal —todos los medidores en 220 V— **no vive en el núcleo del
operador que se estaba usando**, que es la raíz de los tres casos.

**La regla que queda.** Ninguna decisión de preprocesado entra a esta ruta
sin medirla contra la tasa de detección. El argumento formal sirve para
saber qué medir, no para saltearse la medición.

### El paso-alto de E6 quedó descartado como núcleo

Está afinado para anomalías individuales, que un umbral por medidor ya
resuelve al 99,7 %. La decisión, su evidencia y la reformulación de H3
están en **`docs/decisions/ADR-004-detector-de-eventos-colectivos.md`**.

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

## Núcleo, nivel medio y qué Laplaciano usar

Dos hechos medidos que se confunden con facilidad y que juntos deciden si
un detector funciona:

**1. El núcleo de `L_norm` es `D^(1/2)·1`, no el vector constante.**
`cos(u₀, √d) = 1,000000000000` contra `cos(u₀, 1) = 0,992` a 0,996. Por eso
restar la media **no** remueve el modo cero: deja `|x̂₀|` entre 0,064 y
0,268, mientras que proyectar fuera de `u₀` lo lleva a ~1e-14. Para leer el
espectro por modo o por banda, **proyectar fuera de `u₀`**.

**2. `E_D` es invariante al núcleo pero no al nivel medio.** Sumar un
múltiplo de `√d` no la cambia; sumar una constante sí, porque la constante
no está en el núcleo. Y una señal AMI es sobre todo una constante. Energía
de una señal perfectamente plana de 220 V:

| Zona | `E_D` con `L_norm` | `E_D` con `L = D − A` |
|---|---|---|
| centro | 14 656 | **0** |
| chipre | 12 120 | **0** |
| la_enea | 21 671 | **0** |
| palermo | 14 256 | **0** |
| palogrande | 12 094 | **0** |
| universitario | 8 876 | **0** |

El ruido real de la señal aporta ~286. Es decir: **el 98 % de `E_D_norm` de
una señal AMI penaliza el estado normal** y depende sólo de la irregularidad
de los grados.

Medido en detección, AUC para separar una anomalía individual de +6σ sobre
500 realizaciones por zona:

| Estadístico | AUC |
|---|---|
| `E_D` normalizado, señal cruda | 0,661 |
| `E_D` normalizado, señal centrada | 0,986 |
| `E_D` combinatorio | 0,982 |

**La regla:**

* Espectro por modo o banda → proyectar fuera de `u₀`, nunca restar la
  media.
* Rugosidad con intención de detectar → sacar el nivel medio. `L_norm`
  sobre la señal cruda está dominado por el término constante. El
  **Laplaciano combinatorio** lo resuelve sin preprocesar: su núcleo sí es
  la constante.
* `L_norm` sigue siendo el operador correcto para el Difuminador, que
  necesita el espectro acotado en `[0, 2]`.

No hay un único Laplaciano correcto: depende de qué estado se considera
"sin anomalía". El detalle está en el docstring de `graph/filter` y las
mediciones en `experiments/firma-espectral/`.

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
