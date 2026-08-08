# event-injector — Inyector de eventos correlacionados

Genera anomalías donde **cada medidor está dentro de su rango normal** y lo
anómalo es el comportamiento del grupo respecto de su vecindario, con la
verdad de referencia explícita de qué nodos, qué instantes y qué magnitud.

## Por qué existe

El generador que trae el simulador produce anomalías **independientes** por
medidor: sube el voltaje a 243–250 V con probabilidad 1 %. Medido sobre
`ami_telemetry`, la media de `anomalia_voltaje` es 246,50 V contra 220,00 V
de la operación normal, con σ espacial de 4,40 V: eso son **+6σ**.
Cualquier regla de umbral lo separa sin error.

Sobre esa señal no se puede evaluar si un detector espectral aporta algo,
porque no hay nada que aportar. La tercera línea de contribución —detección
de anomalías por análisis espectral del grafo— necesita eventos donde el
umbral por medidor **no pueda** funcionar, para que la comparación signifique
algo.

## Qué produce

Familia implementada: **desviación colectiva sutil**. Un nodo semilla y sus
vecinos hasta cierta profundidad se desvían en la misma dirección, con una
magnitud lo bastante chica para que ningún medidor se distinga de su propia
variación normal.

```python
from pathlib import Path
from urbia_events import CollectiveDeviationSpec, EventInjector, load_bounds, load_profile

inyector = EventInjector(
    profile=load_profile(Path("data/profiles/manizales_signal_v1.json")),
    bounds=load_bounds(Path("data/schemas/payload_schema_v1.json")),
    seed=20260808,
)

señal, verdad = inyector.inject(
    grafo.zones["centro"],
    lecturas,                                   # (n,) o (T, n)
    [CollectiveDeviationSpec(magnitude="voltaje_v", depth=1, sigma_multiple=1.0)],
)

verdad.node_mask(instant=0)      # qué nodos son anómalos
verdad.to_dict()                 # verdad serializable, para el experimento
```

## La magnitud se declara en múltiplos de σ, no en porcentaje

Es la decisión de diseño que más consecuencias tiene, y sale de una
medición. Dispersión **espacial** —entre medidores en un mismo instante, que
es la que ve un detector de grafo— sobre 24 h de `ami_telemetry`:

| Magnitud | σ/media |
|---|---|
| `voltaje_v` | **2,00 %** |
| `corriente_a` | 34,6 – 34,8 % |
| `potencia_kw` | 34,9 – 35,4 % |

Un 5 % es 2,5σ en voltaje —evidente— y 0,14σ en corriente —invisible—. El
mismo número significa cosas opuestas según la magnitud, así que el
porcentaje crudo no es comparable y `sigma_multiple` es la forma por
defecto. `fraction` sigue disponible para cuando la desviación relativa sea
lo físicamente natural.

De ahí también que **el voltaje sea la magnitud adecuada** para esta
familia: con σ/μ del 2 %, una desviación de 1σ es indistinguible del ruido
para un umbral por medidor y perfectamente coherente entre los nodos del
grupo.

Todo esto sale de `data/profiles/manizales_signal_v1.json`; el detalle y las
advertencias están en `data/profiles/README.md`.

## La profundidad tiene un rango útil corto

Medido sobre la topología de los 150 con k-NN k=4, tamaño mediano del
vecindario y fracción de la zona que cubre:

| `depth` | Nodos | Fracción de la zona |
|---|---|---|
| 0 | 1 | ~4 % — control individual |
| 1 | 5 – 6 | 20 – 27 % |
| 2 | 11 – 12 | 40 – 55 % |
| 3 | 17 – 19 | **63 – 85 %** |

En profundidad 3 casi no queda vecindario sano contra el cual contrastar: el
evento deja de ser una discordancia local y se vuelve un corrimiento de zona
entera. El rango útil en esta topología es `{0, 1, 2}`.

## Dos rangos distintos, y no son intercambiables

* **`data/schemas/payload_schema_v1.json`** es el **límite duro**: fuera de
  ahí el productor rechaza el mensaje y la lectura no existe. El inyector no
  lo cruza nunca; si la magnitud pedida no cabe, levanta
  `BoundsViolationError` en vez de recortar en silencio.
* **`data/profiles/manizales_signal_v1.json`** es **dónde vive la señal**, y
  es lo que decide si una desviación es sutil.

Respetar el primero no basta: una desviación puede caber holgadamente en el
esquema y ser evidente para un umbral estadístico. La que importa es la
segunda.

## Inconsistencia detectada entre el contrato y su consumidor

Al versionar `data/schemas/payload_schema_v1.json` apareció una divergencia
que **no es de este paquete pero lo afecta**, porque el inyector garantiza
sus límites contra ese contrato:

El esquema declara `additionalProperties: false` y **no incluye
`energia_kwh`** entre sus propiedades. `services/backend/SCHEMA.md` sí lo
lista como campo de entrada, nullable, con la nota de que "el productor no
siempre reporta acumulado". Las dos cosas no pueden ser ciertas a la vez:
un payload que trajera `energia_kwh` sería rechazado por el
`PayloadValidator` del productor antes de publicarse.

Las lecturas posibles son que el productor no lo envíe nunca —y entonces la
documentación del backend describe un campo que no llega—, o que valide
contra otra versión del contrato que la copiada acá.

**A revisar cuando se toque `urbia-platform`.** No bloquea al inyector: la
familia actual desvía voltaje, corriente o potencia, y `energia_kwh` es
acumulado monotónico, que no es una magnitud sobre la que tenga sentido
inyectar una desviación colectiva instantánea. Queda anotado para que no se
pierda.

## Por qué es un paquete separado de monitor-gsp

Porque produce la verdad de referencia contra la que se puntúa el detector,
y la tercera hipótesis es precisamente una afirmación sobre el desempeño de
ese detector. Si vivieran en el mismo paquete, compartir supuestos entre el
generador de eventos y el detector estaría a un import de distancia y no
dejaría rastro.

Acá el aislamiento es verificable: este paquete no importa nada del
detector, y `tests/test_types.py::TestAislamiento` falla si alguien cruza la
frontera.

La dependencia va en un solo sentido — `event-injector` → `monitor-gsp`,
por `ZoneGraph` — y así debe quedar.

## Familias previstas y no construidas

La interfaz está hecha para que estas entren sin cambiarla. Lo que cada una
exigía ya está en su lugar:

| Familia | Qué exigía | Dónde está |
|---|---|---|
| Dipolo / antifase | desviación con signo por nodo | `delta` es una matriz, no un escalar |
| Deriva gradual | perfil temporal separable | `TemporalProfile` |
| Intermitente | ventana, no instante | `start` + `duration` |
| Individual | — | es `depth=0` |
| Modo común | casos negativos en la verdad | `expected_detectable` |
| Desconexión | máscara de nodos ausentes | **falta** |
| Grupo a caballo de zonas | operar sobre `AmiGraph` | **falta** |

Las dos últimas sí requieren tocar la interfaz. La de desconexión cambia el
Laplaciano, no la señal; la de frontera zonal es la que mediría
empíricamente la limitación de las 34 aristas suprimidas que documenta el
ADR-003 §3.2.

## Instalación

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ../monitor-gsp        # ZoneGraph
pip install -e ".[dev]"
```

## Verificación

```bash
ruff check . && ruff format --check .
mypy
pytest --cov
```

Cobertura mínima exigida: 90 %. No es el 80 % general de `services/`: un
error acá no da un resultado malo, da un resultado que **parece** bueno.

Los tests marcados `integration` verifican que el perfil congelado siga
describiendo la base viva y quedan fuera de la corrida normal.

```bash
POSTGRES_HOST=localhost POSTGRES_PASSWORD=... pytest -m integration
```

## CLI

Genera un dataset de eventos a disco desde una especificación JSON, con su
verdad de referencia al lado:

```bash
urbia-inject --spec experiments/inyector-eventos/spec.json --salida /tmp/dataset
```
