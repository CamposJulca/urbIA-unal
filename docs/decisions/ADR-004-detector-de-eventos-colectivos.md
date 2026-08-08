# ADR-004 — Detector de eventos colectivos, y reformulación de H3

| | |
|---|---|
| Estado | Aceptado |
| Fecha | 2026-08-08 |
| Autor | Cristhiam Daniel Campos Julca |
| Ámbito | Núcleo de detección del monitor GSP y enunciado de la tercera hipótesis |
| Código afectado | `services/monitor-gsp/src/urbia_monitor_gsp/detector/`, `services/event-injector/` |
| Reemplaza | El detector paso-alto validado en `notebooks/01_gsp_hello_world.ipynb` (E6) como núcleo del monitor |
| Cifras medidas en | `experiments/firma-espectral/`, `experiments/magnitud-duracion/`, `experiments/detector-colectivo/`, `experiments/detector-deslizante/` |

---

## 1. Contexto

La tercera línea de contribución doctoral es la detección de anomalías por
análisis espectral del grafo. Su hipótesis de trabajo, tal como venía
enunciada, era que **el método espectral detecta mejor que una regla de
umbral por medidor**.

Al llegar el momento de construir el detector, tres cosas hacían falta y
ninguna existía: eventos sobre los que evaluar, una medición de dónde vive
la firma de esos eventos en el espectro, y un comparador. Este ADR registra
lo que apareció al construirlas.

### 1.1 El punto de partida no servía para evaluar

El generador del simulador produce anomalías **independientes** por medidor:
sube el voltaje a 243–250 V con probabilidad 1 %. Medido sobre
`ami_telemetry`, la media de `anomalia_voltaje` es 246,50 V contra 220,00 V
de operación normal, con σ espacial de 4,40 V. Son **+6,0σ**.

Un umbral por medidor las separa al 99 % con un instante. Sobre esa señal
no se puede evaluar si un detector espectral aporta algo, porque no hay
nada que aportar. De ahí `services/event-injector/`, que genera eventos
donde cada medidor queda dentro de su variación normal y lo anómalo es la
coherencia del grupo.

---

## 2. Decisión

1. **El núcleo de detección es un escaneo local sobre ventana**, no un
   estadístico espectral global. Contrasta cada vecindario del grafo contra
   el resto de su zona y se queda con el mayor desacuerdo.
2. **El detector paso-alto de E6 queda descartado como núcleo del monitor.**
   No se elimina: se reubica como detector de anomalías puntuales, un caso
   que un umbral ya resuelve más barato.
3. **Punto de operación: ventana de 16 instantes, radios de escaneo {1, 2},
   falso positivo del 1 % por señal**, elegido por ventaja sobre el umbral
   y no por detección absoluta.
4. **Ningún preprocesado espectral en la ruta de detección**: ni proyección
   fuera de `u₀` ni prefiltrado con el Difuminador.
5. **H3 se reformula** en los términos de §6.

---

## 3. Justificación

### 3.1 Por qué local y no global

Ningún escalar que resuma la zona entera separa un evento colectivo del
ruido. Medido sobre eventos a profundidad 2 y 1σ, AUC:

| Estadístico global | AUC |
|---|---|
| Energía de Dirichlet normalizada | 0,4848 |
| Íd., señal centrada | 0,5614 |
| Energía de Dirichlet combinatoria | 0,5633 |
| Residuo local agregado | 0,5345 |

Todos indistinguibles del azar. La causa es de dilución: un evento a
profundidad 2 toca unas 9 aristas de corte de las 61 a 72 que tiene una
zona, y un estadístico global integra el ruido de todas.

El escaneo, sobre el mismo material, da 0,73 a 0,81 de AUC.

### 3.2 Por qué el paso-alto de E6 quedó descartado

Es el hallazgo que reordena el aparato heredado, y conviene enunciarlo con
precisión.

**E6 observó que la firma de anomalía se repartía por el espectro y la
registró como una "firma de banda ancha". No era una firma sin patrón:
eran dos firmas distintas mezcladas.** Sobre un grafo de juguete de 10
nodos y con anomalías individuales no había forma de separarlas. Con los
150 medidores reales y eventos colectivos construidos aparte, las dos
poblaciones se separan sin solapamiento:

| | Banda alta | Cociente de Rayleigh |
|---|---|---|
| Anomalía **individual** | 79,20 % ± 5,76 % | 1,0000 ± 0,0000 |
| Evento **colectivo**, profundidad 1 | 16,39 % ± 10,04 % | 0,2981 ± 0,0899 |
| Evento **colectivo**, profundidad 2 | 18,59 % ± 8,85 % | 0,1698 ± 0,0549 |

La anomalía individual es un **impulso** en el dominio de los nodos, y un
impulso es plano en el dominio de la frecuencia del grafo: su energía llega
hasta el modo más alto. El evento colectivo es una **meseta** sobre un
subconjunto conexo, y su energía de alta frecuencia viene sólo del
**perímetro** del grupo. Promediar las dos poblaciones produce el espectro
aparentemente plano que E6 describió.

**La consecuencia sobre el aparato heredado: el paso-alto está afinado para
el caso que un umbral por medidor ya resuelve.** No funciona mal — funciona
bien, y funciona bien para lo que no hace falta. A un instante y al 1 % de
falsos positivos, sobre la anomalía individual de +6σ, un umbral por
medidor detecta el 99,7 % y el escaneo el 33,3 %. Cualquier ganancia que un
detector espectral pueda aportar ahí está acotada por ese 0,3 % restante.

Y la energía de banda alta del evento colectivo —16 a 19 %— está
precisamente donde el paso-alto no mira.

### 3.3 El punto de operación, y por qué se elige por ventaja

`σ·√N` es la magnitud efectiva por medidor después de integrar. Medido, la
ventaja del escaneo sobre el umbral es máxima donde **`σ·√N ≈ 2`**:

| σ | N óptimo | `σ·√N` | Ventaja |
|---|---|---|---|
| 0,5 | 16 | 2,00 | +38,8 |
| 1,0 | 4 | 2,00 | +43,3 |
| 1,5 | 1 | 1,50 | +47,6 |

La lectura: **la ventaja es máxima justo por debajo del punto donde un
umbral por medidor empieza a funcionar.** Por debajo ninguno de los dos ve
nada; por encima los dos ven todo. De ahí una regla transferible: ante un
evento de magnitud σ conocida, la ventana que más aporta es `N ≈ (2/σ)²`.

Perseguir **detección** en vez de ventaja lleva a N=64, donde los dos
métodos llegan al 100 % y la ventaja es +0,0. Son dos objetivos distintos y
se persigue el primero explícitamente, porque el segundo ya lo resuelve un
método más barato.

**Verificado en condición realista.** El punto se había elegido sobre
mediciones con ventana conocida. Rehecho con ventana deslizante, evento en
posición sorteada y falso positivo calibrado por señal:

| Condición | Escaneo | Umbral | Ventaja |
|---|---|---|---|
| Ventana conocida | 93,6 % | 54,8 % | +38,8 |
| **Deslizante** | 79,4 % | 29,8 % | **+49,6** |

N=16 sobrevive y la ventaja **sube**. Deslizar le cuesta más al umbral, que
toma el máximo sobre 49 ventanas × 25 medidores con comparaciones casi
independientes, que al escaneo, cuyas 41 bolas se solapan fuertemente. Las
mediciones idealizadas estaban **subestimando** el método.

En ese punto el detector además localiza: **recall por nodo 92,1 %,
precisión 77,2 %, F1 0,839.**

### 3.4 Radios {1, 2}

Un evento a profundidad 2 abarca ~12 nodos y una bola de radio 1 tiene ~6,
así que ni acertando de lleno puede cubrirlo. Medido en condición realista:

| | {1} | {1,2} | {1,2,3} |
|---|---|---|---|
| Detección | 55,2 % | **79,4 %** | — |
| Ventaja | +25,7 | **+49,6** | — |
| Recall por nodo | 49,2 % | **92,1 %** | 43,1 %\* |
| F1 | 0,570 | **0,839** | 0,549\* |

\* medido con ventana conocida en `detector-colectivo`; radio 3 sube la
detección 2,5 puntos pero baja la precisión 5,6 —más candidatos es más
oportunidad de acertar por casualidad— y empeora el F1.

### 3.5 Sin preprocesado espectral en la ruta de detección

Dos opciones se implementaron, se midieron y quedaron apagadas.

**Proyectar fuera de `u₀`** cuesta de 40 a 77 puntos de detección
(78,8–97,2 % baja a 19,0–55,0 %). El contraste de dos muestras ya es
invariante al nivel medio, así que la proyección no aporta; y como
`u₀ ∝ √d` no es constante, deja un sesgo determinista por bola de hasta
42σ, con lo que el máximo cae siempre en la misma sin importar los datos.

**El Difuminador como prefiltro** merece un enunciado cuidadoso, porque es
el componente heredado de Aristizábal (2022) y el resultado se presta a
leerse como un rechazo del aparato. No lo es.

Sobre la tabla de detección el filtro parece el mejor componente del
detector: sube del 55,8 % al 100 %. Pero la ganancia es espuria. **El
Difuminador rompe la invariancia a sumar una constante**, que es la
propiedad que hacía robusto al escaneo: `diffuse(1)` no es constante —va de
0,8524 a 1,2426 con τ=0,05— porque el vector constante no está en el núcleo
de `L_norm`. Medido sobre un **modo común**, toda la zona corrida 2σ, que
el detector *no* debe marcar porque no hay discordancia con la vecindad:

| | Sin filtro | τ=0,05 | τ=0,447 | τ=1,0 |
|---|---|---|---|---|
| Modo común marcado | **0,0–0,7 %** | 100 % | 100 % | 100 % |

Lo que la tabla mostraba como mejora no era detectar mejor los eventos
colectivos: era **dejar de distinguir**.

**El enunciado correcto es que el Difuminador filtra y no detecta, y son
funciones distintas.** El filtro es un paso-bajo: suaviza el desacuerdo
entre vecinos. La firma de un evento colectivo está precisamente en la
**discontinuidad de frontera** entre el grupo desviado y el resto, que es
lo que el contraste mide. Un paso-bajo suaviza esa discontinuidad. El
componente hace bien su trabajo; su trabajo no es éste.

Esto no dice nada en contra del Difuminador como filtro, que es para lo que
está construido y donde sus propiedades —invariancia a la degeneración
espectral, rango estable de τ, límites correctos— siguen medidas y
vigentes en `experiments/difuminador-tau/`.

### 3.6 El τ óptimo depende del uso

Un resultado lateral que conviene registrar. La grilla de τ para detección
tiene su óptimo en una **meseta de τ=0,05 a 1,5**, mientras el rango estable
para **filtrar** es `[0,447, 2,239]`. La meseta se extiende muy por debajo,
en plena región que para filtrar se declaró degenerada porque la señal
colapsa al núcleo del operador.

Tiene sentido: para filtrar importa preservar la señal; para detectar sólo
importa el contraste. La región donde el filtro "destruye la señal" es la
región donde destruye sobre todo el ruido.

**El τ que se optimice depende de para qué se use el filtro.** Ver §7.

---

## 4. Consecuencias

### 4.1 Lo que habilita

* Un detector con punto de operación medido en la condición realista, que
  reporta **qué nodos** marcó y por lo tanto admite matriz de confusión por
  nodo contra la verdad de referencia del inyector.
* Una regla de diseño transferible: `N ≈ (2/σ)²`.
* Una separación limpia de responsabilidades: regla por medidor para lo
  puntual, escaneo para lo colectivo.

### 4.2 Lo que queda limitado

* **El detector es peor que un umbral en anomalías individuales**: 33,3 %
  contra 99,7 % a un instante. Es el alcance del método, no un defecto a
  corregir.
* **La precisión por nodo se estanca en 77–80 %** y no sube con N. Es el
  techo de escanear bolas: el grupo verdadero tiene ~12 nodos y la bola de
  radio 2 que mejor lo cubre también, pero no son los mismos doce.
* **Un monitor completo necesita los dos detectores.** El sistema no es "el
  método espectral"; es una regla barata más un escaneo, cada uno en su
  régimen.
* **Todo lo medido usa una sola magnitud** (`voltaje_v`, la única con
  σ/media del 2 %) **y una sola profundidad de vecindario**.

### 4.3 Deuda declarada

* **La familia de modo común no existe en el inyector.** Se construyó a
  mano para descartar el prefiltro, y descartó un componente entero sin
  tener verdad de referencia ni casos negativos etiquetados. Es la deuda
  más urgente.
* **Sin costo computacional medido.** 49 ventanas × 41 bolas por señal y
  por zona es lo que un nodo de borde tendría que sostener.
* **Ruido gaussiano independiente entre medidores** en toda la evaluación.

---

## 5. Alternativas descartadas

| Alternativa | Motivo | Medición |
|---|---|---|
| Detector paso-alto (E6) como núcleo | Afinado para el caso que un umbral resuelve al 99,7 % | §3.2 |
| Escalar espectral global por zona | AUC 0,48–0,57 sobre eventos colectivos | §3.1 |
| Energía de Dirichlet con `L_norm` cruda | El 98 % de su valor penaliza el estado normal | ADR pendiente / README de `monitor-gsp` |
| Proyectar fuera de `u₀` antes de puntuar | 40 a 77 puntos de detección | §3.5 |
| Difuminador como prefiltro | Marca el 100 % de los modos comunes | §3.5 |
| Escanear sólo radio 1 | Mitad de la ventaja, mitad del recall | §3.4 |
| Escanear radios {1,2,3} | Más candidatos, peor precisión y peor F1 | §3.4 |
| Elegir N por detección máxima | Lleva a N=64, donde la ventaja es +0,0 | §3.3 |

---

## 6. Reformulación de H3

### 6.1 El enunciado anterior no se sostiene

**"El método espectral detecta mejor que una regla de umbral"** es falso
como afirmación general, y las mediciones lo contradicen en dos frentes:

* Es **falso en anomalías individuales**: 33,3 % contra 99,7 %.
* En eventos colectivos depende del régimen: a `σ·√N ≫ 2` los dos métodos
  llegan al 100 % y la ventaja es +0,0.

### 6.2 El enunciado que sí sostienen las mediciones

> **H3.** Sobre eventos donde la anomalía es la coherencia de un grupo
> conectado del grafo y no el valor de ningún medidor individual, un
> escaneo local sobre el grafo detecta significativamente más que una regla
> de umbral por medidor calibrada al mismo falso positivo. La ventaja es
> máxima cuando la magnitud efectiva tras integrar cumple `σ·√N ≈ 2` —justo
> por debajo del punto donde el umbral empieza a funcionar— y se anula
> cuando el régimen se aleja de ahí en cualquiera de los dos sentidos. El
> método además localiza el grupo afectado, cosa que el umbral no hace.

Con las cifras que la sostienen, en condición realista (ventana deslizante,
evento en posición sorteada, 1 % de falsos positivos por señal, σ=0,5,
N=16):

| | Escaneo | Umbral |
|---|---|---|
| Detección | **79,4 %** | 29,8 % |
| Ventaja | **+49,6 puntos** | — |
| Recall por nodo | **92,1 %** | no aplica |
| Precisión por nodo | **77,2 %** | no aplica |

Y con su alcance declarado: sobre anomalías individuales el mismo detector
rinde 33,3 % contra 99,7 % del umbral.

### 6.3 Por qué el enunciado nuevo es mejor, y no sólo más chico

Es **falsable**: nombra el régimen, el comparador, la calibración y el
punto de operación, así que puede desmentirse midiendo. El anterior no
nombraba nada de eso.

Es **más informativo**: incorpora la ley `σ·√N ≈ 2`, que predice dónde
esperar la ventaja en un despliegue distinto.

Y **declara dónde pierde**, que es lo que le da crédito a lo demás.

---

## 7. Pregunta abierta: qué optimiza el Afinador

Se deja planteada y **no se resuelve acá**, porque es material del bloque
siguiente y resolverla ahora sería fijar una afirmación sin medición.

El Afinador es el componente que ajusta τ por aprendizaje por refuerzo.
Hasta ahora se lo pensaba en el ciclo Difuminador → detección: el filtro
suaviza, el detector mira lo suavizado, y τ se ajusta para que el detector
funcione mejor. **Este ADR rompe ese ciclo**: el filtro no participa en la
detección, así que τ no tiene función de recompensa evidente por ese lado.

Las lecturas posibles, ninguna medida todavía:

* **τ optimiza el filtrado, y el filtrado sirve para otra cosa** —el QoS
  adaptativo, la reducción de tráfico en el nodo de borde, la
  presentación—. Entonces el rango estable `[0,447, 2,239]` sigue siendo el
  correcto y el Afinador no tiene nada que ver con el detector.
* **El Afinador ajusta otro parámetro.** El detector tiene su propio punto
  de operación —la ventana, el radio, el falso positivo objetivo— y `N`
  depende de σ por `N ≈ (2/σ)²`, con σ estimable en línea. Un Afinador que
  ajuste la ventana en vez de τ tendría una recompensa clara.
* **El filtro entra en otro lugar del ciclo**, por ejemplo antes de estimar
  σ, o para separar la componente de modo común que hoy el detector rechaza
  por construcción.

Lo que estas mediciones sí dejan fijado es que **la respuesta no puede
suponerse**: la conjetura razonable de que un paso-bajo ayudaría a detectar
una firma de baja frecuencia resultó falsa por un efecto lateral que el
argumento no contemplaba.

---

## 8. Trazabilidad

| Afirmación | Dónde se sostiene |
|---|---|
| La anomalía existente está a +6,0σ | `experiments/firma-espectral/RESULTADOS.md` §3 |
| Firma individual contra colectiva | `firma-espectral/RESULTADOS.md` §3, §3.1 |
| Escalares globales dan AUC 0,48–0,57 | `firma-espectral/RESULTADOS.md` §5 |
| Ley `σ·√N ≈ 2` | `experiments/detector-colectivo/RESULTADOS.md` §1 |
| Punto de operación N=16, radios {1,2} | `detector-colectivo` §1, §3 y `detector-deslizante` §1, §3 |
| Ventaja +49,6 y confusión por nodo | `experiments/detector-deslizante/RESULTADOS.md` §1, §2 |
| Proyección fuera de `u₀`: 40–77 puntos | `detector-colectivo` §4; test de regresión en `tests/test_detector.py` |
| Prefiltro y modo común | `detector-colectivo/RESULTADOS.md` §4; test de regresión |
| τ óptimo fuera del rango estable | `detector-colectivo/RESULTADOS.md` §4 |
| Rango estable de τ para filtrar | `experiments/difuminador-tau/RESULTADOS.md` §4.2 |

---

## Referencias

* L. A. Aristizábal Quintero, *tesis doctoral*, UNAL, 2022. Capítulo 3:
  Difuminador, Afinador y Adaptador.
* `notebooks/01_gsp_hello_world.ipynb` (E6): prototipo del aparato
  espectral, origen del detector paso-alto y de la observación de "firma de
  banda ancha" que §3.2 reinterpreta.
* `docs/decisions/ADR-003-construccion-del-grafo-ami.md`: el grafo sobre el
  que todo esto corre.
