# Difuminador: signo del exponente, barrido de τ e invariancia espectral

Medición del filtro paso-bajo sobre grafos (*Difuminador*) del monitor GSP
de UrbIA, sobre la topología AMI de 150 medidores de Manizales.

| | |
|---|---|
| Fecha de la medición | 2026-08-07 |
| Script | `experiments/difuminador-tau/run.py` |
| Código medido | `services/monitor-gsp/src/urbia_monitor_gsp/graph/filter.py` |
| Sustrato | `data/topologies/manizales_150.json` (`manizales-v1`) |
| Reproducir | `python experiments/difuminador-tau/run.py` |

El script no lee de PostgreSQL ni del broker MQTT: parte de la
instantánea de topología versionada en el repositorio, de modo que estas
cifras se reproducen sin acceso al cluster.

---

## 1. Qué se midió

El Difuminador atenúa las componentes de alta frecuencia de una señal
definida sobre los nodos del grafo. Alta frecuencia, en un grafo, es
desacuerdo entre nodos vecinos. Su respuesta en frecuencia es

```
g(λ) = exp( −λ / (τ · λmax) )
x_filtrada = U · ( g(λ) ⊙ (Uᵀ · x) )
```

donde `λ` y `U` son los autovalores y autovectores del Laplaciano
normalizado `L_norm = D^(-1/2)·(D−A)·D^(-1/2)`, `λmax` es el mayor
autovalor y `τ` es el parámetro de difusión.

Cuatro preguntas:

1. **¿El signo del exponente importa?** La formulación publicada en la
   tesis de Aristizábal (2022, Capítulo 3) escribe el exponente
   **positivo**. UrbIA implementa el **negativo**. Se mide qué hace cada
   uno con la energía de alta frecuencia.
2. **¿Cómo se comporta τ?** Dónde están los codos y en qué rango la
   respuesta es estable — el rango que después debe explorar el
   componente de ajuste automático (*Afinador*).
3. **¿Los límites son los esperados?** Que τ→0 colapse al núcleo de
   `L_norm` y τ→∞ tienda a la identidad.
4. **¿El resultado es reproducible pese a la degeneración espectral?** El
   grafo tiene autovalores repetidos, y dentro de un subespacio propio
   degenerado la base que devuelve `eigh` es arbitraria.

---

## 2. Sobre qué se midió

### 2.1 El grafo

150 medidores sintéticos en seis zonas de Manizales (centro 25, chipre
25, la_enea 25, palermo 25, palogrande 30, universitario 20). Un subgrafo
independiente por zona, sin aristas entre zonas.

| Parámetro | Valor |
|---|---|
| Vecindad | k-NN, k=4, simetrizado por unión |
| Pesos | binarios (0/1) |
| Distancias | euclídeas en metros, sobre proyección plana local por zona |
| Laplaciano | normalizado simétrico, espectro en `[0, 2]` |
| Puente inter-zona | desactivado |

k=4 es el mínimo que deja las seis zonas conexas; la justificación
completa, con el barrido de k, está en el docstring de `GraphConfig` en
`services/monitor-gsp/src/urbia_monitor_gsp/graph/types.py`.

Una arista significa "estos dos medidores están geográficamente
próximos", **no** "comparten conductor". La topología eléctrica real no
está en los datos.

### 2.2 La señal

Sintética, con semilla fija. Por cada zona:

```
x[i] = 10,0 kWh + ruido gaussiano N(0, 0,3)      para todo medidor i
x[j] += 5,0 kWh                                   en un único medidor j
```

Semilla base `20260807`, combinada con el índice de la zona. El medidor
que recibe el pico se sortea con la misma semilla y no se elige a mano:
elegirlo permitiría acomodar el resultado.

| Zona | Índice | Medidor con el pico |
|---|---|---|
| centro | 2 | `urbia-cen-mon-0003` |
| chipre | 21 | `urbia-chi-mon-0022` |
| la_enea | 22 | `urbia-ena-tri-0023` |
| palermo | 17 | `urbia-pal-tri-0018` |
| palogrande | 0 | `urbia-pgr-mon-0001` |
| universitario | 14 | `urbia-uni-tri-0015` |

**Por qué sintética y no telemetría real.** El generador de anomalías en
operación produce eventos independientes por medidor, sin correlación con
los vecinos. Sobre esa señal un filtro definido por la vecindad del grafo
no tiene nada que mostrar: no hay estructura espacial que preservar ni
que remover. El caso con datos reales entra cuando exista el inyector de
eventos correlacionados.

### 2.3 Las métricas

**Energía de Dirichlet — métrica principal.**

```
E_D(x) = xᵀ·L_norm·x = Σ_k λ_k·x̂_k² = Σ_ij w_ij·(x_i/√d_i − x_j/√d_j)²
```

Mide el desacuerdo entre vecinos. Se usa como métrica principal porque
**no depende de la base de autovectores**: es una forma cuadrática del
operador. Eso importa acá, porque el grafo tiene subespacios propios
degenerados de hasta dimensión 6 (§6), donde los autovectores
individuales no son reproducibles.

**Reparto por bandas — lectura secundaria.** Se parte el espectro en dos
y se compara la energía a cada lado. El corte no va fijo en λmax/2: se
elige entre los bordes de los subespacios propios el más cercano a ese
objetivo (§3.2).

---

## 3. Resultado 1 — el signo del exponente

τ = 0,5. `E_D` es la energía de Dirichlet, "banda alta" es la energía
espectral por encima del corte.

| Zona | `E_D` original | `E_D` con exp. negativo | razón | `E_D` con exp. positivo | razón |
|---|---|---|---|---|---|
| centro | 45,02 | 3,156 | 0,070 | 1 081,9 | 24,0 × |
| chipre | 42,79 | 2,357 | 0,055 | 1 313,6 | 30,7 × |
| la_enea | 57,67 | 3,703 | 0,064 | 1 622,4 | 28,1 × |
| palermo | 51,67 | 2,553 | 0,049 | 1 581,6 | 30,6 × |
| palogrande | 62,33 | 3,585 | 0,058 | 1 760,5 | 28,2 × |
| universitario | 19,72 | 1,240 | 0,063 | 740,6 | 37,6 × |

Banda alta, misma corrida:

| Zona | fracción alta original | con exp. negativo | con exp. positivo | razón banda alta, negativo | razón banda alta, positivo |
|---|---|---|---|---|---|
| centro | 1,30 % | 0,071 % | 23,7 % | 0,054 | 23,8 × |
| chipre | 1,18 % | 0,051 % | 26,5 % | 0,042 | 30,2 × |
| la_enea | 1,68 % | 0,084 % | 31,8 % | 0,049 | 27,6 × |
| palermo | 1,59 % | 0,071 % | 32,0 % | 0,044 | 29,3 × |
| palogrande | 1,45 % | 0,058 % | 29,5 % | 0,039 | 28,5 × |
| universitario | 0,65 % | 0,025 % | 20,1 % | 0,037 | 38,4 × |

### 3.1 Lectura

Con el exponente **negativo** la energía de Dirichlet cae a entre el 4,9 %
y el 7,0 % de su valor original, y la banda alta a entre el 3,7 % y el
5,4 % de la suya. Es el comportamiento de un filtro paso-bajo.

Con el exponente **positivo** la energía de Dirichlet sube a entre 24 y
38 veces la original, y la banda alta entre 24 y 38 veces la suya. La
fracción de energía en alta frecuencia pasa de ~1 % a ~30 %: el filtro
concentra la señal justamente en lo que debía remover.

Las seis zonas se comportan igual. Ninguna invierte el sentido. La
diferencia no es de grado ni de convención de signo: **el exponente
positivo invierte el operador**.

Hay además un problema numérico. `g(λmax) = exp(1/τ)` con el exponente
positivo desborda el rango de punto flotante para τ chico: `exp(1/0,01)`
ya vale 2,7e43 y `exp(1/0,001)` es infinito. La formulación publicada no
sólo hace lo contrario de lo que debe: para τ chico deja de producir un
número con el que se pueda seguir operando.

**Decisión de implementación.** El signo no es configurable. La API
pública fija el exponente negativo; la variante positiva existe sólo como
función privada, usada por este experimento y por los tests, para poder
medir y afirmar la diferencia. Exponerla como opción la volvería
elegible, y no hay ningún caso en que sea la elección correcta.

### 3.2 Dónde quedó el corte de bandas

El corte se busca en `target_ratio · λmax` (por defecto `target_ratio =
0,5`) y se ajusta al borde de subespacio propio más cercano.

| Zona | λmax | objetivo | índice del corte | λ del corte | ¿borde de subespacio? | multiplicidad máxima de la zona |
|---|---|---|---|---|---|---|
| centro | 1,5795 | 0,790 | 6 | 0,795 | sí | 3 |
| chipre | 1,5570 | 0,779 | 6 | 0,775 | sí | 1 |
| la_enea | 1,5512 | 0,776 | 6 | 0,798 | sí | 1 |
| palermo | 1,5037 | 0,752 | 6 | 0,905 | sí | 6 |
| palogrande | 1,6004 | 0,800 | 8 | 0,830 | sí | 2 |
| universitario | 1,5058 | 0,753 | 4 | 0,667 | sí | 2 |

El ajuste hace trabajo real: en palermo mueve el corte de 0,752 a 0,905
para no caer dentro de un subespacio.

**Por qué no un corte fijo.** Un corte por valor puede caer exactamente
sobre un autovalor degenerado, y entonces el redondeo decide qué miembros
del subespacio van a cada banda. El caso se reproduce en un grafo de
juguete: en la estrella `S6` el espectro exacto es 0, 1, 1, 1, 1, 2, así
que λmax/2 vale justo 1; `eigh` devuelve el primer autovalor del grupo
como 0,9999999999999998 y los otros tres como 1,0 exacto, de modo que
comparar contra 1,0 manda uno a la banda baja y tres a la alta. La
energía atribuida a cada banda quedaría decidida por el error de
redondeo. Es el mismo defecto de la ventana espectral abrupta que ya se
había descartado en el trabajo exploratorio previo.

---

## 4. Resultado 2 — barrido de τ

Fracción de la energía de Dirichlet que **sobrevive** al filtro,
`E_D(x_filtrada) / E_D(x)`. Valores chicos = filtrado agresivo.

| τ | centro | chipre | la_enea | palermo | palogrande | universitario | media | dispersión | ret. banda alta | ret. banda baja |
|---|---|---|---|---|---|---|---|---|---|---|
| 0,01 | 1,9e-07 | 5,7e-06 | 1,2e-07 | 5,9e-09 | 5,4e-07 | 1,7e-10 | 1,1e-06 | 34 073 | 3,4e-29 | 0,997 |
| 0,05 | 5,1e-04 | 1,0e-03 | 1,3e-03 | 1,4e-04 | 2,8e-04 | 1,5e-04 | 5,7e-04 | 9,49 | 2,1e-10 | 0,997 |
| 0,10 | 2,8e-03 | 2,1e-03 | 4,4e-03 | 6,4e-04 | 1,5e-03 | 1,7e-03 | 2,2e-03 | 6,87 | 2,6e-06 | 0,997 |
| 0,25 | 1,4e-02 | 9,2e-03 | 1,4e-02 | 6,0e-03 | 1,1e-02 | 1,5e-02 | 1,2e-02 | 2,58 | 2,7e-03 | 0,998 |
| 0,50 | 7,0e-02 | 5,5e-02 | 6,4e-02 | 4,9e-02 | 5,8e-02 | 6,3e-02 | 6,0e-02 | 1,42 | 4,4e-02 | 0,998 |
| 1,00 | 0,241 | 0,212 | 0,226 | 0,206 | 0,215 | 0,209 | 0,218 | 1,17 | 0,203 | 0,999 |
| 2,00 | 0,482 | 0,452 | 0,465 | 0,447 | 0,455 | 0,442 | 0,457 | 1,09 | 0,446 | 0,999 |
| 5,00 | 0,744 | 0,725 | 0,733 | 0,723 | 0,727 | 0,716 | 0,728 | 1,04 | 0,723 | 1,000 |
| 10,0 | 0,862 | 0,851 | 0,856 | 0,850 | 0,852 | 0,845 | 0,853 | 1,02 | 0,850 | 1,000 |
| 100 | 0,985 | 0,984 | 0,985 | 0,984 | 0,984 | 0,983 | 0,984 | 1,00 | 0,984 | 1,000 |

"Dispersión" es el cociente entre la zona que más energía retiene y la
que menos: cuánto discrepan entre sí las seis zonas ante la misma τ.

### 4.1 Los codos

Localizados sobre una grilla fina de 81 puntos equiespaciados en log(τ)
entre 0,01 y 100, con criterios declarados antes de mirar los datos:

| Codo | τ | Criterio |
|---|---|---|
| Inferior | **0,447** | dispersión entre zonas ≤ 1,5 |
| Superior | **2,239** | el filtro todavía remueve al menos la mitad de `E_D` |

La sensibilidad `|d ln E_D / d ln τ|` —cuántos por ciento cambia la
energía retenida por cada por ciento de cambio en τ— no es monótona:

| Punto | τ | Valor |
|---|---|---|
| Borde izquierdo de la grilla | 0,01 | 6,34 |
| Mínimo local | 0,126 | 1,71 |
| Máximo local | 0,355 | 2,43 |
| Borde derecho de la grilla | 100 | 0,017 |

El valor en τ=0,01 no es un máximo: la sensibilidad **diverge** cuando
τ→0. La divergencia es predecible en forma cerrada. Para τ chico la
energía retenida queda dominada por el primer modo no nulo,
`E_D(x_f)/E_D(x) ≈ c·exp(−2λ₁/(τ·λmax))`, de donde la sensibilidad vale
`2λ₁/(τ·λmax)`. Con la zona que domina el promedio —chipre, la de Fiedler
más chico, λ₁ = 0,0505 y λmax = 1,5570— eso predice **6,48** en τ=0,01
contra **6,34** medido. La discrepancia es el efecto de las demás zonas,
que aún aportan algo a la media.

El máximo local en τ ≈ 0,355 es el codo propiamente dicho: la transición
entre el régimen donde sólo sobrevive el modo de Fiedler y el régimen
donde participa todo el espectro.

### 4.2 El rango estable

**τ ∈ [0,45, 2,24].** Sostenido por tres cifras de la tabla:

* **Las zonas concuerdan.** La dispersión baja de 2,58 en τ=0,25 a 1,42 en
  τ=0,5 y 1,09 en τ=2. Por debajo del codo inferior la misma τ produce
  resultados de órdenes de magnitud distintos según la zona: en τ=0,01 la
  dispersión es 3,4e4. Una τ que no significa lo mismo en las seis zonas
  no sirve para un monitor distribuido, que es precisamente el caso de
  uso.
* **La respuesta es suave y monótona.** La sensibilidad se mantiene entre
  0,687 en el extremo superior y 2,375 en el inferior, sin divergencias.
  Un ajuste incremental de τ produce un cambio proporcional en la salida:
  es la condición para que un agente pueda ajustarla por realimentación.
  (El 2,375 es el valor en el codo inferior, τ=0,447. El 2,384 que se lee
  un punto más a la izquierda, en τ=0,316, ya cae fuera del rango.)
* **El filtro efectivamente filtra.** La banda alta retiene entre 4,4 % y
  45 % de su energía, mientras la energía total se conserva casi intacta.

Fuera de ese rango las dos puntas son degeneradas y no hay nada que
ajustar: por debajo de τ≈0,25 el resultado es indistinguible del núcleo
del operador (la retención de banda alta es 2,7e-3 en τ=0,25 y 3,4e-29 en
τ=0,01: numéricamente aniquilada), y por encima de τ≈5 el filtro deja de
actuar (retiene el 72 % de `E_D` en τ=5 y el 98 % en τ=100).

**Este es el rango que debe explorar el Afinador.** El valor por defecto
de la implementación, τ = 0,5, cae dentro.

### 4.3 Advertencia sobre la retención de banda baja

La última columna de la tabla vale entre 0,997 y 1,000 en todo el
barrido, incluso donde el filtro aniquila la señal. **No es una medida
útil**, y se incluye sólo para dejar constancia de por qué no lo es: la
banda baja está dominada por el coeficiente de frecuencia cero, que
concentra entre el 97,8 % y el 99,1 % de la energía total de la señal
—consecuencia de que la señal tenga media 10 kWh y desviación 0,3—. Ese
coeficiente lo multiplica `g(0) = 1` para cualquier τ, así que la
retención de banda baja mide sobre todo la media de la señal. Las
métricas informativas son la energía de Dirichlet y la banda alta.

---

## 5. Resultado 3 — los límites de τ

τ = 1e-3 y τ = 1e3. `x_f` es la señal filtrada.

| Zona | cos(`x_f`, `√d`) | cos(`x_f`, `1`) | grado mín | grado máx | max/min de `x_f` | `E_D` en el límite | error rel. vs identidad (τ=1e3) |
|---|---|---|---|---|---|---|---|
| centro | 1,000000000000 | 0,99289 | 4 | 8 | 1,4142 | −6,4e-16 | 8,9e-05 |
| chipre | 1,000000000000 | 0,99561 | 4 | 7 | 1,3229 | −6,5e-14 | 9,1e-05 |
| la_enea | 1,000000000000 | 0,99208 | 4 | 9 | 1,5000 | −1,6e-14 | 1,1e-04 |
| palermo | 1,000000000000 | 0,99436 | 4 | 7 | 1,3229 | 3,4e-14 | 1,0e-04 |
| palogrande | 1,000000000000 | 0,99640 | 4 | 7 | 1,3229 | −9,7e-15 | 1,0e-04 |
| universitario | 1,000000000000 | 0,99519 | 4 | 7 | 1,3229 | −1,9e-14 | 7,3e-05 |

### 5.1 τ→0 colapsa al núcleo, y el núcleo no es la señal constante

Es la distinción que se lee mal con más facilidad, y estas cifras la
fijan.

El núcleo de `L_norm` **no** es el vector constante. Es `D^(1/2)·1`, el
vector cuya componente `i` vale `√dᵢ`, normalizado. La confusión viene
del Laplaciano combinatorio `L = D − A`, donde el núcleo sí es la
constante; al normalizar, el cambio de variable `y = D^(1/2)x` se lleva
el núcleo con él.

Medido: el coseno entre la señal filtrada y `√d` vale 1 a doce decimales
en las seis zonas, mientras que el coseno contra la constante se queda
entre 0,992 y 0,996 — cerca, pero distinguible, y sistemáticamente por
debajo.

La consecuencia práctica se ve mejor en la columna `max/min`. Con τ→0 la
señal filtrada **no converge al promedio de los nodos**: converge a un
perfil proporcional a `√dᵢ`. En centro, donde los grados van de 4 a 8, el
medidor más conectado queda con un valor `√(8/4) = 1,4142` veces el del
menos conectado, aunque la señal de entrada fuera perfectamente plana. En
la_enea, con grados de 4 a 9, el cociente es `√(9/4) = 1,5000` exacto.
Quien espere ver un promedio y encuentre un perfil creciente con el grado
no está mirando un error: está mirando el núcleo correcto del operador.

La energía de Dirichlet en ese límite es del orden de 1e-14 —cero
numérico, con signos arbitrarios de redondeo—, que es lo que confirma que
la señal quedó dentro del núcleo.

### 5.2 τ→∞ es la identidad

Con τ = 1e3 la señal filtrada difiere de la original en menos de 1,1e-04
en norma relativa, en las seis zonas. El filtro no hace nada, como debe.

---

## 6. Resultado 4 — invariancia a la degeneración espectral

El grafo tiene autovalores repetidos: con k-NN k=4 sobre los 150
medidores, λ=1,25 aparece con multiplicidad 6 en palermo, 3 en centro y 2
en palogrande y universitario. Dentro de un subespacio propio degenerado
**la base es arbitraria**: `eigh` devuelve una cualquiera, y permutar el
orden de los nodos la cambia.

Experimento sobre palermo (25 medidores, subespacio de dimensión 6 en
λ=1,250000): se permuta el orden de los nodos con una semilla fija, se
reconstruye el Laplaciano y se rediagonaliza desde cero, se filtra con
τ=0,5, y se compara contra la corrida sin permutar deshaciendo la
permutación.

| Cantidad | Diferencia |
|---|---|
| Señal filtrada `x_f` | 2,7e-14 |
| Energía de Dirichlet | 1,4e-13 |
| Energía de banda alta | 6,6e-14 |
| Energía de banda baja | 1,4e-12 |
| λ del corte | 5,6e-16 |
| Índice del corte | idéntico |
| **Módulo del coeficiente `x̂_k` de un modo individual** | **1,3e-01** |

Las primeras seis filas son ruido de redondeo. La última es una
discrepancia real, y está incluida a propósito: si también fuera cero,
las demás filas estarían pasando por una razón trivial —que la
permutación no hubiera rotado nada— en vez de por la razón que se quiere
demostrar.

**Por qué el filtro es invariante.** `g` depende únicamente de λ, así que
es constante dentro de cada subespacio propio. Si `Q` es una rotación de
la base dentro de un subespacio degenerado, entonces
`U·Q·diag(g)·Qᵀ·Uᵀ = U·diag(g)·Uᵀ`, porque en ese bloque `diag(g)` es un
múltiplo de la identidad y conmuta con `Q`. Dicho de otro modo: el
operador es `exp(−L_norm/(τ·λmax))`, una función matricial de `L_norm`, y
no depende de la base con que se lo calcule. La invariancia no es una
propiedad afortunada de estos datos: es estructural, y la medición
confirma que la implementación la respeta.

Lo mismo vale para la energía de Dirichlet, que es una forma cuadrática
del operador. El reparto por bandas sí pasa por los autovectores, pero
resulta invariante porque el corte respeta los bordes de los subespacios
y la energía agregada de un subespacio completo no depende de la base.

---

## 7. Conclusiones

1. **El exponente de la formulación publicada está invertido.** Con signo
   positivo el filtro amplifica la alta frecuencia entre 24 y 38 veces en
   vez de atenuarla, y desborda a infinito para τ chico. La
   implementación de UrbIA usa el signo negativo y no expone el otro como
   opción configurable.
2. **El rango operativo de τ es [0,45, 2,24].** Fuera de él el filtro o
   destruye la señal o no hace nada, y por debajo del codo inferior deja
   además de significar lo mismo en zonas distintas. Es el rango que debe
   explorar el Afinador.
3. **El filtro es reproducible pese a la degeneración espectral**, por
   construcción y no por casualidad, y las mediciones lo confirman a
   ~1e-14 sobre el subespacio de dimensión 6 de palermo.
4. **La energía de Dirichlet es la métrica correcta** para reportar el
   efecto del filtro. El reparto por bandas sirve de lectura secundaria
   siempre que el corte respete los bordes de los subespacios propios, y
   su componente de banda baja no es informativa mientras la señal tenga
   una media que domine el espectro.

---

## 8. Qué no cubre esta medición

* **Datos reales.** La señal es sintética (§2.2). El caso con telemetría
  real requiere el inyector de eventos correlacionados, que no existe
  todavía.
* **Una sola realización de la señal.** No hay barrido de semillas ni
  intervalos de confianza: las cifras describen esta señal sobre este
  grafo. Los resultados cualitativos (signo, límites, invariancia) son
  estructurales y no dependen de la realización; los cuantitativos
  (razones exactas, ubicación de los codos) sí.
* **Una sola construcción del grafo.** k=4, unión, pesos binarios. No se
  midió cómo se mueven los codos con otras construcciones.
* **Anomalías de un solo medidor.** El pico es puntual. El comportamiento
  del filtro ante anomalías extendidas sobre varios medidores vecinos
  —que es donde un filtro definido por la vecindad debería lucirse— no
  está medido acá.
* **Costo computacional.** No se midieron tiempos. Con 20 a 30 nodos por
  zona la diagonalización es de microsegundos y no fue una preocupación.
