# ADR-003 — Construcción del grafo AMI para el monitor espectral

| | |
|---|---|
| Estado | Aceptado |
| Fecha | 2026-08-08 |
| Autor | Cristhiam Daniel Campos Julca |
| Ámbito | Sustrato de todo el monitor GSP: sobre este grafo corren la GFT, la wavelet multiescala, el detector espectral y el Difuminador |
| Código afectado | `services/monitor-gsp/src/urbia_monitor_gsp/graph/` (`geo`, `types`, `spectral`, `builder`, `filter`) |
| Cifras medidas sobre | `data/topologies/manizales_150.json` (`manizales-v1`, exportada de `ami_meters` el 2026-08-07) |

---

## 1. Contexto

El monitor espectral de UrbIA no analiza series de tiempo independientes: analiza
una **señal definida sobre los nodos de un grafo**. El grafo es la estructura que
decide qué significa "frecuencia alta" — desacuerdo entre nodos vecinos — y por lo
tanto qué cuenta como anomalía. Antes de escribir una sola línea de detector hay
que decidir cuál es ese grafo, porque cualquier resultado espectral posterior es
una afirmación sobre él y no sobre la red eléctrica en abstracto.

### 1.1 Lo que hay en los datos

La tabla `ami_meters` de la base `urbia` tiene, por medidor: `device_id`, `zona`,
`lat`, `lon` y `nodo_origen`. Son 150 medidores en seis zonas de Manizales:

| Zona | Medidores |
|---|---|
| centro | 25 |
| chipre | 25 |
| la_enea | 25 |
| palermo | 25 |
| palogrande | 30 |
| universitario | 20 |

### 1.2 Lo que no hay

**No hay topología eléctrica.** No hay catálogo de transformadores, ni ramales de
baja tensión, ni identificador de alimentador, ni ninguna columna que diga qué
medidores cuelgan del mismo conductor. La columna `nodo_origen` registra de qué
nodo del cluster llegó el mensaje MQTT: es procedencia de red, no conectividad
eléctrica, y confundir las dos cosas produciría un grafo que describe la
infraestructura de cómputo en vez de la de distribución.

### 1.3 Las preguntas que había que cerrar

1. Si no hay conectividad eléctrica, ¿de dónde sale la vecindad del grafo, y qué
   se puede afirmar sobre esa base?
2. ¿Un grafo global de 150 nodos o un subgrafo por zona?
3. ¿Qué criterio de vecindad, con qué parámetro y con qué pesos?
4. ¿Cómo se pasa de grados decimales a distancias en metros?
5. ¿Se implementa el Difuminador como está publicado en la fuente?

Las cinco tienen consecuencia medible sobre la topología resultante. La cuarta y
la quinta parecían detalles de implementación y no lo eran.

---

## 2. Decisión

1. **La vecindad del grafo se deriva de proximidad geográfica**, declarada
   explícitamente como aproximación de la topología eléctrica. Una arista
   significa "estos dos medidores están próximos", **no** "comparten conductor".
2. **Seis subgrafos independientes, uno por zona, sin aristas de puente
   inter-zona.** El grafo AMI es bloque-diagonal.
3. **k-NN con k=4, simetrizado por unión, pesos binarios.**
4. **Proyección plana local con los dos radios de curvatura del elipsoide
   WGS84** evaluados en la latitud de referencia, no con una esfera de radio
   medio.
5. **El Difuminador se implementa con el exponente negativo**,
   `g(λ) = exp(−λ/(τ·λmax))`, corrigiendo el signo de la formulación publicada en
   Aristizábal (2022, Capítulo 3). El signo no es configurable.

---

## 3. Justificación

Todas las cifras de esta sección se midieron sobre `manizales_150.json` con el
código de `services/monitor-gsp`. La construcción de referencia es la misma en
todas las tablas salvo donde se indique lo contrario: k-NN k=4 por unión, pesos
binarios, un marco de proyección local por zona, `L_norm` diagonalizado con
`spectral.graph_fourier_basis`. La §7 mapea cada afirmación al archivo que la
sostiene.

### 3.1 Vecindad geográfica como aproximación declarada

No es una decisión entre alternativas: es la única vecindad derivable de los
datos disponibles. Lo que se decide es **cómo se declara**.

La proximidad geográfica correlaciona con la conectividad eléctrica en una red de
distribución urbana —los medidores de una misma manzana suelen compartir
transformador— pero no la determina. Dos medidores a 30 m pueden estar en
ramales distintos, y dos del mismo transformador pueden estar separados por una
manzana.

En consecuencia queda acotado lo que el monitor puede afirmar:

* **Puede afirmar** que un medidor es discordante respecto de su vecindario
  espacial: su lectura no se parece a la de los medidores que tiene alrededor.
* **No puede afirmar** propagación eléctrica de un evento, ni atribuir una
  anomalía a un elemento de la red — un transformador, un ramal, una fase.

Esta distinción es un supuesto declarado de la tesis, no un detalle de
implementación, y debe aparecer en el capítulo de método y en la discusión de
resultados. Un revisor que la ignore leerá los resultados como si fueran
afirmaciones sobre la red física.

La ruta de validación está en §6.

### 3.2 Seis subgrafos independientes

La decisión tiene dos apoyos de naturaleza distinta, y conviene no confundirlos.

**Apoyo de despliegue.** La partición zonal coincide con la distribución prevista
del monitor: un nodo de borde por zona, cada uno analizando su propio subgrafo sin
conocer los demás. Ésa es la primera línea de contribución doctoral —bajar el
monitor del datacenter al borde—, y un grafo global de 150 nodos la contradice:
obligaría a cada nodo de borde a conocer el estado de toda la ciudad para
diagonalizar su Laplaciano. La estructura bloque-diagonal hace que el análisis
por zona sea **exacto**, no una aproximación: el espectro del grafo global es la
unión de los espectros zonales, y la multiplicidad del autovalor cero es 6, una
por zona.

**Apoyo geométrico, con una limitación medida.** Las zonas están separadas, pero
no uniformemente. Distancia entre centroides zonales y distancia entre los dos
medidores más próximos de cada par:

| Par de zonas | Centroides | Medidores más próximos |
|---|---|---|
| palermo – universitario | 911 m | **25 m** |
| centro – chipre | 1 030 m | **73 m** |
| palermo – palogrande | 1 317 m | **261 m** |
| centro – palermo | 1 635 m | 517 m |
| centro – palogrande | 1 792 m | 937 m |
| palogrande – universitario | 1 792 m | 795 m |
| la_enea – universitario | 1 930 m | 849 m |
| chipre – palermo | 2 623 m | 1 528 m |
| centro – universitario | 2 546 m | 1 506 m |
| chipre – palogrande | 2 765 m | 1 835 m |
| la_enea – palermo | 2 816 m | 1 694 m |
| chipre – universitario | 3 529 m | 2 516 m |
| la_enea – palogrande | 3 606 m | 2 527 m |
| centro – la_enea | 4 434 m | 3 212 m |
| chipre – la_enea | 5 368 m | 4 214 m |

Los diámetros zonales van de 1 044 m (centro) a 1 348 m (la_enea), y la arista
intra-zona más larga del grafo con k=4 mide 501 m. Para doce de los quince pares
la separación es holgada: ningún medidor de una zona tiene vecinos de otra a
menos de 500 m, así que la partición no le quita al grafo ninguna arista que la
proximidad hubiera propuesto.

**Para los tres primeros pares no.** Medido: un k-NN k=4 aplicado a los 150
medidores sin partir por zonas coloca 377 aristas, de las cuales **34 cruzan
frontera zonal**:

| Par | Aristas inter-zona suprimidas | La más corta |
|---|---|---|
| palermo – universitario | 18 | 25 m |
| centro – chipre | 10 | 73 m |
| palermo – palogrande | 6 | 261 m |

La partición zonal, entonces, **no es una partición geográfica**: es la partición
administrativa que trae la columna `zona`, y en tres pares de zonas corta a
través de proximidad física real. El grafo particionado tiene 369 aristas
intra-zona contra las 343 del global, porque al aislar cada zona sus nodos
periféricos deben buscar sus cuatro vecinos dentro de la zona y aceptan aristas
más largas que las que la proximidad global les hubiera dado.

Se acepta el costo por dos razones. La primera es que puentear inventaría
conectividad: una arista entre dos medidores de zonas distintas no tiene más
correlato físico que una intra-zona, y agregarla sólo para "cerrar" el grafo
introduce estructura que después el espectro reporta como si fuera del dato. La
segunda es que un grafo global sin partición **tampoco** queda conexo: k=4 sobre
los 150 medidores deja 3 componentes, así que ni siquiera compra la conectividad
que sería su único argumento.

**Limitación declarada:** una discordancia entre un medidor de palermo y su
vecino físicamente más cercano —a 25 m, del otro lado de la frontera zonal— es
invisible para este monitor. Vale para 34 pares de medidores de los 11 175
posibles.

### 3.3 k-NN con k=4, por unión, pesos binarios

#### El parámetro k

Barrido de k sobre las seis zonas, con el valor de Fiedler de `L_norm` cuando la
zona queda conexa y el número de componentes cuando no:

| k | centro | chipre | la_enea | palermo | palogrande | universitario | Zonas conexas |
|---|---|---|---|---|---|---|---|
| 1 | 6 comp. | 9 comp. | 7 comp. | 9 comp. | 8 comp. | 6 comp. | 0 / 6 |
| 2 | 2 comp. | 0,0155 | 4 comp. | 3 comp. | 2 comp. | 2 comp. | 1 / 6 |
| 3 | 0,0368 | 0,0411 | **2 comp.** | 0,0295 | 0,0529 | 0,0219 | 5 / 6 |
| **4** | 0,0545 | **0,0505** | 0,0901 | 0,0940 | 0,0602 | 0,1238 | **6 / 6** |
| 5 | 0,0725 | 0,0726 | 0,1062 | 0,1649 | 0,1022 | 0,1534 | 6 / 6 |
| 6 | 0,0862 | 0,1097 | 0,1793 | 0,1819 | 0,1337 | 0,2298 | 6 / 6 |

**k=4 es el mínimo que deja las seis zonas conexas.** No es holgura sobre el
mínimo: es el mínimo. Y no lo fija un promedio: lo fija **una sola zona**. Con
k=3 cinco zonas conectan sin problema —la peor de ellas, universitario, con
Fiedler 0,0219— y la_enea se parte en dos componentes.

La conectividad no es una preferencia estética. Un subgrafo con dos componentes
tiene el autovalor cero con multiplicidad 2, el "modo de Fiedler" deja de medir
cuán lejos está el grafo de partirse, y una anomalía confinada a una componente
no aparece en el espectro de la otra. El detector espectral quedaría ciego a
media zona sin ninguna señal de que lo está.

#### El hallazgo de la_enea

la_enea es la zona más rala de las seis. Densidad, medida como medidores por km²
del *bounding box* del propio conjunto de medidores de cada zona:

| Zona | Medidores | Área del bbox | Densidad |
|---|---|---|---|
| la_enea | 25 | 1,2023 km² | **20,79 med/km²** |
| universitario | 20 | 0,8535 km² | 23,43 med/km² |
| centro | 25 | 0,9332 km² | 26,79 med/km² |
| palermo | 25 | 0,7947 km² | 31,46 med/km² |
| chipre | 25 | 0,7510 km² | 33,29 med/km² |
| palogrande | 30 | 0,7791 km² | **38,50 med/km²** |

Las seis zonas difieren en densidad por un factor **1,852**, y la_enea está en el
extremo ralo.

Lo que convierte esto en un hallazgo y no en una anécdota es que **dos criterios
de vecindad independientes señalan la misma zona como límite inferior de
conectividad**:

* Por k-NN: k=3 parte la_enea en dos componentes, y sólo la_enea.
* Por radio fijo: r = 399 m es el radio mínimo que deja las seis zonas conexas.
  Un metro menos, r = 398 m, y **la_enea se parte en dos componentes, y sólo
  la_enea**.

| r | Zonas conexas | Grado mín. | Grado máx. | Qué falla |
|---|---|---|---|---|
| 250 m | 1 / 6 | 1 | 6 | grado cero en centro, palermo, palogrande; la_enea en 6 comp., universitario en 3 |
| 300 m | 2 / 6 | 1 | 10 | grado cero en centro, palogrande; la_enea y universitario en 2 comp. |
| 350 m | 3 / 6 | 2 | 13 | grado cero en centro; la_enea y universitario en 2 comp. |
| 380 m | 5 / 6 | 2 | 17 | la_enea en 2 comp. |
| **398 m** | 5 / 6 | 2 | 17 | **la_enea en 2 comp.** |
| **399 m** | **6 / 6** | 2 | 17 | — |
| 450 m | 6 / 6 | 2 | 21 | — |
| 500 m | 6 / 6 | 3 | 23 | — |

Que la zona crítica sea la misma bajo los dos criterios dice que el límite no es
un artefacto del criterio elegido, sino una propiedad de la distribución
espacial de los medidores: la_enea fija el punto de operación de toda la
construcción. Es la zona a mirar primero cuando el detector se comporte raro, y
la que hay que revisar si la topología cambia.

#### Por qué k-NN y no radio fijo

El radio r = 399 m conecta las seis zonas, así que la conectividad no distingue
entre los dos criterios. Lo que los distingue es la **dispersión de grados**. A
r = 399 m:

| Zona | Aristas | Grados | Grado medio |
|---|---|---|---|
| centro | 98 | 3 a 13 | 7,84 |
| chipre | 106 | 4 a 13 | 8,48 |
| la_enea | 63 | **2** a 9 | 5,04 |
| palermo | 100 | 3 a 13 | 8,00 |
| palogrande | 157 | 2 a **17** | 10,47 |
| universitario | 59 | 3 a 9 | 5,90 |

Los grados van de 2 a 17. Un único radio no puede servir a la vez a una zona de
20,79 med/km² y a otra de 38,50: donde es suficiente para conectar la rala, es
excesivo para la densa. Con k-NN cada nodo se adapta a su densidad local por
construcción, y la simetrización por unión garantiza **grado mínimo ≥ k**: con
k=4 el grado mínimo es exactamente 4 en las seis zonas, y el máximo llega a 9.

Ese piso de grado importa por una razón concreta ya vista: el notebook E6
identificó los nodos hoja —grado 1— como punto ciego del detector, porque un nodo
con un solo vecino no tiene vecindario contra el cual discrepar. Con radio fijo
aparecen nodos de grado 2 y, por debajo de r ≈ 350 m, nodos de grado cero, para
los cuales `L_norm` no está siquiera definido.

#### Por qué unión y no reciprocidad

`knn_mode="mutual"` conecta dos nodos sólo si cada uno elige al otro entre sus k
más cercanos. Con k=4 sobre las seis zonas eso fragmenta casi todo:

| Zona | Con `mutual`, k=4 |
|---|---|
| palogrande | conexa, Fiedler 0,0270 |
| chipre | 2 componentes |
| la_enea | 2 componentes |
| palermo | 3 componentes |
| universitario | 3 componentes |
| centro | 5 componentes, **una de ellas un nodo aislado** |

En centro la reciprocidad deja un medidor con grado cero, para el cual el
Laplaciano normalizado no existe: el constructor levanta `ZeroDegreeNodeError` en
vez de devolver un espectro con NaN. Palogrande, la única que sobrevive conexa,
lo hace con Fiedler 0,0270 — la mitad del peor caso con unión.

#### Los pesos binarios: decisión sin medición

Los pesos binarios (0/1) son lo que validó el notebook E6 y lo que está fijado
como defecto. La alternativa gaussiana, `exp(−d²/2σ²)`, está implementada y
probada en cuanto a corrección —pondera entre 0 y 1, pesa menos a mayor
distancia, deriva σ de la mediana de las aristas cuando no se declara— pero
**nunca se comparó contra los binarios sobre los 150 medidores**.

Se declara como tal: es una decisión por continuidad con E6 y por simplicidad
interpretativa, no un resultado. Lo que falta medir está en §6.

### 3.4 Proyección elipsoidal con los dos radios de curvatura

Todo el monitor trabaja en metros; las coordenadas llegan en grados decimales
WGS84. El paso entre ambos parecía un detalle y resultó tener consecuencia
topológica.

La proyección elegida es equirectangular local con los dos radios de curvatura
del elipsoide evaluados en la latitud de referencia:

```
dx = N(lat0) · cos(lat0) · (lon − lon0)
dy = M(lat0) · (lat − lat0)
```

donde `M` es el radio meridional (norte-sur) y `N` el normal (este-oeste). La
alternativa habitual —y más corta de escribir— es usar una esfera de radio medio
R = 6 371 km para las dos direcciones.

**Error contra distancia geodésica.** Medido con la fórmula inversa de Vincenty
sobre WGS84, en los 1 825 pares intra-zona de los 150 medidores:

| Proyección | Error medio | Error máximo |
|---|---|---|
| Plana esférica, R = 6 371 km | 1,3491 m | **5,4422 m** |
| Plana elipsoidal, (M, N) | 0,0007 m | **0,0062 m** |

Tres órdenes de magnitud, y a cambio de una constante más.

**El error de la esfera es sistemático, no ruido.** A la latitud media de los 150
medidores, 5,0617°, los radios valen M = 6 335 934,6 m y N = 6 378 303,2 m. El
radio medio se desvía **+0,5534 %** respecto del meridional y −0,1145 % respecto
del normal: usar R para las dos direcciones **estira todas las distancias
norte-sur** en medio por ciento. Sobre aristas de vecindad de 100 a 500 m eso son
metros, en una misma dirección, siempre.

**Consecuencia topológica.** Un sesgo direccional sistemático no sólo corre las
distancias: puede cambiar cuál de dos candidatos es el cuarto vecino más cercano.
Reconstruido el k-NN con k=4 contra distancias geodésicas exactas, y contando las
aristas en que cada proyección difiere del resultado geodésico:

| Zona | Aristas | Difieren con esférica | Difieren con elipsoidal |
|---|---|---|---|
| centro | 65 | 0 | 0 |
| chipre | 62 | 0 | 0 |
| la_enea | 61 | **2** | 0 |
| palermo | 61 | 0 | 0 |
| palogrande | 72 | 0 | 0 |
| universitario | 48 | 0 | 0 |
| **Total** | 369 | **2** | **0** |

Dos aristas de 369 es poco, y aun así el punto no es la magnitud: es que **un
detalle de geodesia cambia el grafo sobre el que corre el análisis espectral**,
y lo cambia justamente en la_enea, la zona rala que ya fija el punto de operación
(§3.3). El aparato espectral no tiene forma de avisar que su sustrato salió de
una aproximación demasiado gruesa; los autovalores se calculan igual y no se
quejan. Por eso la proyección se decide midiendo contra un oráculo independiente,
y por eso `geo.geodesic_distance_m` queda en el módulo aunque el constructor no la
use: es la referencia con que se audita una topología nueva.

La aproximación plana en sí es válida acá porque cada zona abarca ~1 km² y el
conjunto no supera los 6 km; sobre esa extensión la curvatura queda por debajo del
error de las propias coordenadas. Si el despliegue creciera a escala
metropolitana, se cambia este módulo y nada más se entera: el resto del paquete
sólo ve metros.

### 3.5 Corrección de signo del Difuminador

El *Difuminador* de Aristizábal (2022) es un filtro paso-bajo sobre el grafo:
atenúa las componentes de alta frecuencia de la señal, es decir el desacuerdo
entre nodos vecinos. Su respuesta en frecuencia, tal como está impresa en el
Capítulo 3 de la fuente, lleva el exponente **positivo**. UrbIA implementa el
**negativo**:

```
g(λ) = exp( −λ / (τ · λmax) )
x_filtrada = U · ( g(λ) ⊙ (Uᵀ · x) )
```

**El argumento formal.** `g` debe decrecer con λ para que el filtro sea
paso-bajo. Con el exponente positivo `g` crece: el modo de frecuencia más alta
queda multiplicado por `exp(1/τ)` mientras el modo constante queda multiplicado
por 1, de modo que el filtro amplifica exactamente lo que un paso-bajo tiene que
atenuar. No es una convención de signo alternativa ni otra parametrización de la
misma familia: invierte el sentido del operador.

**La medición.** Con τ = 0,5, sobre las seis zonas, señal sintética de semilla
fija (base 10 kWh, ruido N(0, 0,3), pico de +5 kWh en un medidor sorteado):

| | Energía de Dirichlet `E_D` | Energía de banda alta |
|---|---|---|
| Exponente negativo | queda en **4,94 % a 7,01 %** de la original | queda en 3,7 % a 5,4 % de la original |
| Exponente positivo | sube a **24,0 a 37,6 veces** la original | sube a 24 a 38 veces la original |

La fracción de energía en alta frecuencia pasa de ~1 % a ~30 % con el exponente
positivo: el filtro concentra la señal justo en lo que debía remover. Las seis
zonas se comportan igual; ninguna invierte el sentido.

**Y hay un problema numérico encima.** `g(λmax) = exp(1/τ)` con el exponente
positivo desborda el punto flotante para τ chico: `exp(1/0,01)` ya vale 2,7e43 y
`exp(1/0,001)` es infinito. La formulación publicada no sólo hace lo contrario de
lo que debe; para τ chico deja de producir un número con el que se pueda seguir
operando.

**Decisión de implementación: el signo no es configurable.** La API pública fija
el exponente negativo. La variante positiva existe únicamente como
`_published_response` y `_diffuse_published`, privadas, para que el experimento
pueda medir la diferencia y los tests puedan afirmarla. Exponerla como opción la
volvería elegible, y no hay ningún caso en que sea la elección correcta.

**Lo que la corrección deja en pie.** El resto del componente se comporta como
predice la teoría, y eso también está medido:

* **Rango operativo de τ: [0,447, 2,239]**, localizado sobre una grilla de 81
  puntos en log(τ) con criterios declarados antes de mirar los datos —por abajo,
  donde las seis zonas dejan de discrepar entre sí (dispersión ≤ 1,5); por
  arriba, donde el filtro todavía remueve al menos la mitad de `E_D`. Dentro del
  rango la sensibilidad `|d ln E_D / d ln τ|` se mantiene entre 0,687 y 2,375: un
  ajuste incremental de τ produce un cambio proporcional en la salida, que es la
  condición para que el Afinador pueda ajustarla por realimentación. El defecto
  de la implementación, τ = 0,5, cae dentro.
* **τ→0 colapsa al núcleo de `L_norm`, que no es la señal constante** sino
  `D^(1/2)·1`. Medido con τ = 1e-3: el coseno de la señal filtrada contra `√d`
  vale 1 a doce decimales en las seis zonas, mientras el coseno contra la
  constante se queda entre 0,992 y 0,996. La consecuencia práctica es que la
  señal filtrada no converge al promedio de los nodos sino a un perfil
  proporcional a `√dᵢ`: el cociente máx/mín vale `√(d_max/d_min)` exacto —1,4142
  en centro, con grados de 4 a 8; 1,5000 en la_enea, con grados de 4 a 9—
  incluso si la entrada fuera perfectamente plana.
* **τ→∞ es la identidad.** Con τ = 1e3 la señal filtrada difiere de la original en
  menos de 1,1e-04 en norma relativa.
* **El filtro es invariante a la degeneración espectral**, que en este grafo no es
  hipotética: λ = 1,25 aparece con multiplicidad 6 en palermo, 3 en centro y 2 en
  palogrande y universitario. Permutando el orden de los nodos de palermo y
  rediagonalizando desde cero, la señal filtrada difiere en 2,7e-14 y la energía
  de Dirichlet en 1,4e-13, mientras el coeficiente de un modo individual del
  subespacio degenerado difiere en 1,3e-01. La última cifra es la que da sentido
  a las otras dos: sigue habiendo rotación de base, y las cantidades que el
  monitor reporta son invariantes de todos modos. Lo son por construcción —el
  operador es `exp(−L_norm/(τ·λmax))`, una función matricial de `L_norm`— y la
  medición confirma que la implementación lo respeta.

Ese último punto es el que fija **la energía de Dirichlet como métrica principal**
del efecto del filtro: es una forma cuadrática del operador y no depende de la
base que `eigh` haya elegido. El reparto por bandas queda como lectura
secundaria, y sólo con el corte ajustado al borde de subespacio propio más
cercano en vez de fijo en λmax/2.

---

## 4. Consecuencias

### 4.1 Lo que habilita

* El ciclo dato → grafo → señal filtrada está cerrado y es reproducible sin
  cluster: parte de un JSON versionado, no de PostgreSQL ni del broker.
* Cada zona es analizable por separado y de forma exacta. Un nodo de borde puede
  construir y diagonalizar su subgrafo sin conocer las otras cinco, que es el
  requisito de la primera línea de contribución doctoral.
* El costo computacional es despreciable a esta escala: 20 a 30 nodos por zona,
  diagonalización densa en microsegundos. No hubo que optimizar nada, y por eso
  el núcleo depende sólo de NumPy y no de PyGSP ni de SciPy.
* El grado mínimo garantizado por la simetrización por unión elimina los nodos
  hoja que E6 identificó como punto ciego del detector.

### 4.2 Lo que queda limitado

* **El monitor no puede afirmar propagación eléctrica.** Es la limitación
  estructural, no la de un parámetro (§3.1).
* **34 pares de medidores geográficamente próximos quedan sin arista** por la
  frontera zonal, el más cercano a 25 m (§3.2).
* **El punto de operación lo fija una sola zona.** k=4 es el mínimo por la_enea;
  si la topología cambia y la_enea se vuelve más rala, k=4 deja de alcanzar.
  Cualquier revisión del padrón de medidores obliga a rehacer el barrido de k.
* **Los resultados están medidos sobre una única topología y una única
  realización de señal sintética.** Los resultados cualitativos —signo, límites
  de τ, invariancia— son estructurales; los cuantitativos —razones exactas,
  ubicación de los codos— describen este grafo y esta señal.

### 4.3 Deuda declarada

* Pesos binarios contra gaussianos: sin medir (§3.3).
* Puente inter-zona: declarado en `GraphConfig` pero no implementado; encenderlo
  levanta `InvalidGraphConfigError`.
* Señal real: el generador de anomalías en operación produce eventos
  independientes por medidor, sin correlación con los vecinos, y sobre esa señal
  un filtro definido por la vecindad no tiene nada que mostrar. El caso con
  telemetría real requiere el inyector de eventos correlacionados, que no existe.

---

## 5. Alternativas descartadas

| Alternativa | Motivo del descarte | Medición |
|---|---|---|
| Grafo global de 150 nodos | Contradice el monitor distribuido y ni siquiera queda conexo: k=4 sobre los 150 deja 3 componentes | §3.2 |
| Puente inter-zona | Inventa conectividad sin correlato físico; el espectro después la reporta como si viniera del dato | §3.2 |
| Radio fijo de vecindad | Ningún radio único sirve a densidades que difieren por 1,852: a r=399 m los grados van de 2 a 17, y por debajo de 350 m aparecen nodos de grado cero | §3.3 |
| k = 3 | la_enea se parte en dos componentes | §3.3 |
| k ≥ 5 | Conecta mejor, pero cada vecino extra agrega aristas que ya no corresponden a proximidad física plausible | §3.3 |
| `knn_mode="mutual"` | Fragmenta cinco de seis zonas y deja un nodo de grado cero en centro | §3.3 |
| Esfera de radio medio R = 6 371 km | Error sistemático de +0,5534 % en las distancias norte-sur; hasta 5,4422 m de error y 2 aristas distintas en la_enea | §3.4 |
| Exponente positivo del Difuminador | Amplifica la alta frecuencia 24 a 38 veces en vez de atenuarla, y desborda a infinito para τ chico | §3.5 |
| Corte de bandas fijo en λmax/2 | Puede caer dentro de un subespacio degenerado y repartir por redondeo una energía que no tiene reparto definido | §3.5 |

---

## 6. Ruta de revisión

Esta decisión se reabre bajo cualquiera de estas cuatro evidencias.

**1. Aparece el catálogo de transformadores.** Es el caso importante. El
constructor acepta una topología externa sin cambiar su interfaz: `build_ami_graph`
recibe medidores y configuración, y la adyacencia se puede inyectar. Con el
catálogo disponible, lo que hay que medir es cuánto se parecen el grafo
geográfico y el eléctrico —índice de Jaccard sobre el conjunto de aristas, y
cuántas de las 369 aristas actuales sobreviven— y cuánto cambia el diagnóstico
del detector al pasar de uno a otro. Ése es el experimento que convierte el
supuesto de §3.1 de limitación declarada en error acotado.

**2. Cambia el padrón de medidores.** Rehacer el barrido de k y el de radio. La
zona a mirar primero es la más rala, hoy la_enea.

**3. Se quiere justificar el peso de las aristas.** Comparar binarios contra
gaussianos sobre los 150: cómo se mueven el espectro, el Fiedler por zona y la
detección de la anomalía inyectada, y si σ derivado de la mediana es una elección
defendible o hay que barrerlo.

**4. Existe el inyector de eventos correlacionados.** Repetir la medición del
Difuminador sobre anomalías extendidas a varios medidores vecinos, que es donde un
filtro definido por la vecindad debería lucirse y donde hoy no hay nada medido.

---

## 7. Trazabilidad

Cada afirmación empírica de este ADR sale de un archivo del repositorio.

| Afirmación | Dónde se sostiene |
|---|---|
| Topología: 150 medidores, seis zonas, procedencia | `data/topologies/manizales_150.json`, `data/topologies/README.md` |
| Barrido de k, Fiedler por zona, k=3 parte la_enea | `services/monitor-gsp/tests/test_builder.py::TestRegresionManizales` |
| r=399 mínimo, r=398 parte la_enea, grados 2 a 17 | `test_builder.py::test_radio_399_es_el_minimo_que_conecta_las_seis_zonas`, `::test_a_radio_399_los_grados_van_de_2_a_17` |
| `mutual` con k=4 sólo deja conexa a palogrande | `test_builder.py::test_mutual_con_k4_solo_deja_conexa_a_palogrande` |
| Multiplicidad de λ=1,25 por zona | `test_builder.py::test_multiplicidad_de_lambda_125_por_nodos_gemelos` |
| Construcción de referencia y barrido de k, en prosa | docstring de `GraphConfig` en `graph/types.py` |
| Error de proyección esférica vs elipsoidal | docstring de módulo de `graph/geo.py`; oráculo en `geo.geodesic_distance_m`, tests en `test_geo.py` |
| Difuminador: signo, codos de τ, límites, invariancia | `experiments/difuminador-tau/RESULTADOS.md`, `results/medicion.json`, reproducible con `run.py` |
| Densidad zonal, aristas inter-zona suprimidas, distancias entre zonas | Medidas para este ADR sobre `manizales_150.json`; ver §3.2 y §3.3 y el notebook `notebooks/02_grafo_ami_150.ipynb` |
| Validación visual de todo lo anterior | `notebooks/02_grafo_ami_150.ipynb` |

**Pendiente de fijar como test de regresión:** las cifras de densidad zonal, de
separación entre zonas y de aristas inter-zona suprimidas se midieron para este
ADR y hoy sólo viven en el notebook y en este documento. Las que ya están fijadas
figuran arriba con su test. Conviene bajarlas a `test_builder.py` en el próximo
paso que toque el constructor.

---

## Referencias

* L. A. Aristizábal Quintero, *tesis doctoral*, Universidad Nacional de Colombia,
  2022. Capítulo 3: Difuminador, Afinador y Adaptador.
* J. S. Giraldo Duque, *tesis de maestría*, Universidad Nacional de Colombia,
  2026. Antecedente experimental de la plataforma AMI.
* `notebooks/01_gsp_hello_world.ipynb` (E6): prototipo del aparato espectral sobre
  grafo de juguete, donde se identificó el punto ciego de los nodos hoja y el
  defecto de la ventana espectral abrupta.
