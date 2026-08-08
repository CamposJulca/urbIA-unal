# Dónde está la firma de un evento colectivo en el espectro

Medición previa al diseño del detector: qué mira el detector tiene que
salir de acá y no de una suposición.

| | |
|---|---|
| Fecha | 2026-08-08 |
| Script | `experiments/firma-espectral/run.py` |
| Sustrato | `data/topologies/manizales_150.json`, `data/profiles/manizales_signal_v1.json` |
| Eventos | `services/event-injector`, familia desviación colectiva |
| Magnitud | `voltaje_v` (σ/media 2,00 %) |
| Realizaciones | 500 por zona y configuración |
| Reproducir | `services/event-injector/.venv/bin/python experiments/firma-espectral/run.py` |

---

## 1. La forma de la firma no depende de su magnitud

Mismo nodo semilla, misma profundidad, cuatro magnitudes:

| σ pedidos | Norma | Modo 0 | Banda alta | Rayleigh |
|---|---|---|---|---|
| 0,5 | 4,9207 | 15,38 % | 6,42 % | 0,2000 |
| 1,0 | 9,8415 | 15,38 % | 6,42 % | 0,2000 |
| 2,0 | 19,6829 | 15,38 % | 6,42 % | 0,2000 |
| 6,0 | 59,0487 | 15,38 % | 6,42 % | 0,2000 |

Idénticos hasta el último dígito. Con `sigma_multiple` la desviación es
constante sobre el grupo, así que la firma es `k·σ·1_S` y **la magnitud
sólo escala**: no mueve la energía a otro lado del espectro.

**Consecuencia:** dónde mirar se decide una sola vez. El barrido de
magnitud sirve para la relación señal-ruido, no para el diseño.

*(Con `fraction` en lugar de `sigma_multiple` esto no vale: la desviación
pasa a depender del valor de cada nodo y la forma varía con la señal.)*

---

## 2. La firma se mueve a baja frecuencia cuando el grupo crece

Promedio sobre las 150 semillas posibles, magnitud 1σ. "Corte" son las
aristas con exactamente un extremo dentro del grupo.

| `depth` | Nodos | Corte | Corte/nodo | Modo 0 | Banda alta | Rayleigh |
|---|---|---|---|---|---|---|
| 0 | 1,0 | 4,9 | 4,92 | 4,00 % | **79,20 %** | **1,0000** |
| 1 | 5,9 | 9,2 | 1,59 | 24,38 % | 16,39 % | 0,2981 |
| 2 | 11,9 | 9,5 | 0,81 | 47,98 % | 18,59 % | 0,1698 |
| 3 | 18,0 | 9,3 | 0,54 | 71,48 % | 30,09 % | 0,1145 |

El cociente de Rayleigh `E_D(x)/‖x‖²` resume dónde cae la energía: 0 es
todo en el núcleo, λmax todo en el modo más alto.

**Lo que lo gobierna es la frontera, no el tamaño.** La correlación entre
el cociente de Rayleigh y las aristas de corte por nodo es **r = 0,9534**
sobre 600 eventos. Se ve en la tabla: el corte se queda en ~9 aristas
mientras el grupo crece de 6 a 18 nodos, así que la energía de alta
frecuencia se mantiene y la de baja se dispara. En el límite —el grupo es
la zona entera— el corte es 0 y el evento se vuelve modo común, invisible
para cualquier método definido sobre la vecindad.

Eso da la razón cuantitativa de por qué `depth ≥ 3` es degenerado: no es
sólo que quede poco vecindario sano, es que **la firma detectable escala
con el perímetro del grupo, no con su área**.

El valor exacto `Rayleigh = 1,0000` en `depth 0` es estructural: para el
indicador de un solo nodo, `E_D/‖·‖²` es el elemento diagonal de `L_norm`,
que vale 1 en todo nodo no aislado.

---

## 3. Colectiva contra individual: se distinguen

| Configuración | Banda alta | Rayleigh |
|---|---|---|
| Individual (`depth 0`) | **79,20 % ± 5,76 %** | **1,0000 ± 0,0000** |
| Colectiva (`depth 1`) | 16,39 % ± 10,04 % | 0,2981 ± 0,0899 |
| Colectiva (`depth 2`) | 18,59 % ± 8,85 % | 0,1698 ± 0,0549 |

Factor 4 a 5 en la fracción de banda alta, y factor 3 a 6 en el cociente de
Rayleigh, con dispersiones que no se solapan. **Las dos clases de anomalía
ocupan regiones distintas del espectro.**

La respuesta a la pregunta que decide H3 es entonces afirmativa: la firma
colectiva y la individual **no** se ven iguales. Pero con un matiz que
importa, y va invertido respecto de la intuición: la anomalía individual es
la que vive en **alta** frecuencia, y la colectiva en **baja**.

### 3.1 Resultado de tesis: qué era la "firma de banda ancha" de E6

**El notebook E6 observó que la firma de anomalía no se concentraba en alta
frecuencia sino que se repartía por el espectro, y lo registró como una
firma de banda ancha. Esta medición dice que no era una firma sin patrón:
eran dos firmas distintas mezcladas.**

Sobre el grafo de juguete de E6 no había forma de separarlas, porque las
anomalías inyectadas eran individuales y el grafo tenía 10 nodos. Con los
150 medidores reales y eventos colectivos construidos aparte, las dos
poblaciones se separan sin solapamiento:

* Anomalía **individual**: banda alta 79,20 % ± 5,76 %, Rayleigh 1,0000. Es
  un impulso en el dominio de los nodos, y un impulso es plano en el
  dominio de la frecuencia del grafo — de ahí que su energía llegue hasta
  el modo más alto.
* Evento **colectivo**: banda alta 16,39 % a 18,59 %, Rayleigh 0,17 a 0,30.
  Es una meseta sobre un subconjunto conexo, y su energía de alta
  frecuencia proviene sólo del **perímetro** del grupo.

Lo que se leía como una única firma dispersa es la superposición de una
componente de alta frecuencia —los eventos individuales— y una de baja —los
colectivos—. Promediarlas produce un espectro aparentemente plano y sin
estructura.

### 3.2 Consecuencia sobre el aparato heredado

**El detector paso-alto que E6 validó está afinado para el caso que un
umbral por medidor ya resuelve.** No es que funcione mal: funciona bien, y
funciona bien para lo que no hace falta.

Las cifras lo cierran. Sobre la anomalía individual, a un punto de
operación del 1 % de falsos positivos, un umbral por medidor detecta el
99,0 % de los eventos. Cualquier ganancia que un detector espectral pueda
aportar ahí está acotada por ese 1 % restante. Sobre los eventos
colectivos, que son los que el umbral no ve —3,8 % a 9,2 %—, el paso-alto
mira justamente la banda donde la firma colectiva **no** está: su energía
de banda alta es del 16 % al 19 %, contra el 79 % de la individual.

Esto no invalida el trabajo de E6, que era correcto para lo que evaluó. Lo
que hace es reubicarlo: el paso-alto es el detector adecuado para
anomalías puntuales, un caso que ya tiene solución barata, y el detector de
eventos colectivos tiene que construirse mirando otra cosa.

**Va al capítulo, y amerita un ADR propio** que registre la decisión de no
continuar con el detector paso-alto como núcleo del monitor y la evidencia
que la sostiene.

---

## 4. El problema del Laplaciano: `L_norm` penaliza el estado normal

Energía de una señal **perfectamente plana** de 220 V:

| Zona | `L_norm` | `L = D − A` |
|---|---|---|
| centro | 14 656 | 0 |
| chipre | 12 120 | 0 |
| la_enea | 21 671 | 0 |
| palermo | 14 256 | 0 |
| palogrande | 12 094 | 0 |
| universitario | 8 876 | 0 |

El ruido real aporta ~286. El 98 % de `E_D_norm` de una señal AMI es una
penalización al estado normal, que depende sólo de la irregularidad de los
grados.

La causa: el núcleo de `L_norm` es `D^(1/2)·1`, y el estado físicamente
normal de una señal AMI es **constante**. La constante no está en ese
núcleo. El Laplaciano combinatorio sí la tiene.

Se ve en la detección de la anomalía individual, AUC:

| Estadístico | AUC |
|---|---|
| `E_D` normalizado, señal cruda | 0,661 |
| `E_D` normalizado, señal centrada | 0,986 |
| `E_D` combinatorio | 0,982 |

**Corrige lo que este repositorio afirmaba.** La regla escrita antes de
esta medición decía que `E_D` no necesita centrado porque ya es invariante
al modo cero. La invariancia es cierta —al **núcleo**— pero no al **nivel
medio**, que es otra cosa y es la que domina. La documentación de
`graph/filter` y del README quedó corregida.

---

## 5. Detección: los escalares globales no sirven

AUC sobre 500 realizaciones por zona. 0,5 es indistinguible.

| Configuración | Umbral | `E_D` norm | `E_D` norm cent. | `E_D` comb | Residuo local |
|---|---|---|---|---|---|
| Colectiva `d1` | 0,6499 | 0,4848 | 0,5614 | 0,5633 | 0,5345 |
| Colectiva `d2` | 0,7436 | 0,5392 | 0,5702 | 0,5669 | 0,5400 |
| Colectiva `d3` | 0,8046 | 0,5637 | 0,5673 | 0,5641 | 0,5419 |
| Individual | **0,9996** | 0,6613 | 0,9864 | 0,9819 | 0,9980 |

Ningún escalar que resuma la zona entera pasa de 0,57 en los eventos
colectivos. La razón es de dilución: el evento toca ~9 aristas de corte de
las 61 a 72 que tiene una zona, y el estadístico global integra el ruido de
todas.

### Localizados, y el techo de información

| Configuración | Escaneo | **Oráculo** |
|---|---|---|
| Colectiva `d1` | 0,7563 | 0,8757 |
| Colectiva `d2` | 0,8051 | 0,9241 |
| Colectiva `d3` | 0,7297 | 0,8532 |
| Individual | 0,8969 | 1,0000 |

El **oráculo** conoce exactamente qué nodos están afectados y contrasta su
media contra la del resto. No es un detector: es la cota superior de lo que
cualquier detector podría extraer. El **escaneo** hace lo mismo recorriendo
las bolas de radio 1 centradas en cada nodo, sin conocer el grupo.

### Al punto de operación que importa

Tasa de detección con el umbral calibrado al **1 % de falsos positivos**:

| Configuración | Umbral | `E_D` comb | Escaneo | **Oráculo** |
|---|---|---|---|---|
| Colectiva `d1` | 3,8 % | 2,1 % | **14,7 %** | 33,4 % |
| Colectiva `d2` | 6,7 % | 2,2 % | **18,9 %** | 49,4 % |
| Colectiva `d3` | 9,2 % | 2,1 % | **13,0 %** | 43,2 % |
| Individual | **99,0 %** | 75,5 % | 33,4 % | 100,0 % |

El AUC engaña: el umbral llega a 0,80 en `d3` y detecta el 9 % de los
eventos a un punto de operación usable. `E_D` combinatorio tiene 2,1 %,
apenas por encima del 1 % del propio piso de falsos positivos: no detecta
nada.

---

## 6. Qué dicen estas mediciones

1. **H3 es demostrable, con alcance acotado.** Un método de grafo localizado
   triplica al umbral en los eventos colectivos —18,9 % contra 6,7 % en
   `depth 2`— y las dos firmas ocupan regiones espectrales distintas. Pero
   el mismo método es **peor** que el umbral en las anomalías individuales
   (33,4 % contra 99,0 %). La afirmación defendible es "mejor en eventos
   colectivos", no "mejor en detección".

2. **El detector no puede ser un escalar por zona.** Todos los estadísticos
   globales están entre 0,48 y 0,57 de AUC. La firma es local y hay que
   mirarla localmente.

3. **A 1σ sobre un instante se está cerca del límite de información.** El
   oráculo llega al 49 % en el mejor caso. Ningún detector va a superar eso
   con una sola muestra. Las salidas son subir la magnitud, **integrar sobre
   la duración del evento** —el inyector ya la soporta— o ambas. Conviene
   medir la curva magnitud × duración antes de fijar el punto de operación
   de la tesis.

4. **`depth 2` es el punto dulce.** Detecta mejor que `depth 1` porque el
   grupo es mayor, y mejor que `depth 3` porque conserva frontera. Coincide
   con lo que anticipaba la geometría del vecindario.

---

## 7. Qué no cubre esta medición

* **Un solo instante por realización.** No hay integración temporal, que es
  precisamente la vía más prometedora según el punto 3.
* **Una sola magnitud.** Voltaje, por ser la única con σ/media del 2 %.
  Corriente y potencia tienen 35 % y su caso está sin medir.
* **Ruido gaussiano independiente.** La señal de fondo se simula con el
  perfil medido, no es telemetría real. Correlaciones espaciales reales
  entre medidores vecinos cambiarían el fondo contra el que se detecta.
* **El escaneo usa bolas de radio 1.** No se barrió el radio del escaneo ni
  se corrigió por múltiples comparaciones, que es lo que hace falta para
  que su punto de operación sea honesto a escala.
* **Sin costo computacional.** No se midieron tiempos.
