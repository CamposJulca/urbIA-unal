# Evaluación del detector: punto de operación, radios, τ y confusión

| | |
|---|---|
| Fecha | 2026-08-08 |
| Script | `experiments/detector-colectivo/run.py` |
| Criterios | commit `526dc40`, **antes** de correr |
| Bajo prueba | `urbia_monitor_gsp.detector`, el módulo, no una reimplementación |
| Configuración | `voltaje_v`, `depth=2`, 300 realizaciones por celda, 6 zonas |

---

## 1. La ventaja tiene un máximo, y no está donde se creía

Tasa de detección al 1 % de falsos positivos por ventana, escaneo con
radios {1, 2} contra umbral por medidor.

**σ = 0,5**

| N | Escaneo | Umbral | Ventaja |
|---|---|---|---|
| 1 | 4,4 % | 4,3 % | +0,1 % |
| 2 | 8,8 % | 7,9 % | +0,8 % |
| 4 | 22,0 % | 6,4 % | +15,6 % |
| 8 | 58,1 % | 29,7 % | +28,4 % |
| **16** | **93,6 %** | **54,8 %** | **+38,8 %** ← D1 |
| 32 | 99,9 % | 90,2 % | +9,7 % |
| 64 | 100 % | 100 % | +0,0 % ← D4 |

**σ = 1,0**

| N | Escaneo | Umbral | Ventaja |
|---|---|---|---|
| 1 | 23,4 % | 6,3 % | +17,1 % |
| 2 | 57,4 % | 17,1 % | +40,3 % |
| **4** | **92,6 %** | **49,3 %** | **+43,3 %** ← D1 |
| 8 | 99,9 % | 93,8 % | +6,1 % |
| 16 | 100 % | 100 % | +0,0 % ← D4 |

**σ = 1,5**

| N | Escaneo | Umbral | Ventaja |
|---|---|---|---|
| **1** | **66,8 %** | **19,2 %** | **+47,6 %** ← D1 |
| 2 | 95,3 % | 73,8 % | +21,6 % |
| 4 | 99,9 % | 98,9 % | +1,1 % |
| 8 | 100 % | 100 % | +0,0 % ← D4 |

### La ley que gobierna el máximo

Los tres máximos caen donde **`σ·√N ≈ 2`**:

| σ | N óptimo | `σ·√N` |
|---|---|---|
| 0,5 | 16 | 2,00 |
| 1,0 | 4 | 2,00 |
| 1,5 | 1 | 1,50 |

La lectura es directa: `σ·√N` es la magnitud efectiva por medidor después
de integrar, y **la ventaja del método de grafo es máxima justo por debajo
del punto donde un umbral por medidor empieza a funcionar**. Por debajo de
ese punto ninguno de los dos ve nada; por encima, los dos ven todo.

### Corrige lo que se había afirmado

Al cerrar el experimento anterior se dijo que "donde el método aporta es en
N ≤ 2". **Es falso como afirmación general.** Depende de σ: para σ=1,5 el
óptimo sí es N=1, pero para σ=0,5 es N=16. Lo que no depende de σ es
`σ·√N ≈ 2`.

Dos cosas cambiaron respecto de aquella medición. La primera es el radio:
el instrumento escaneaba sólo radio 1 y el detector escanea {1, 2}, lo que
sube la detección de 42,6 % a 57,4 % en σ=1,0 con N=2. La segunda es que
aquel barrido no tenía N=16 en la grilla para σ=0,5.

### El punto de operación

**D1–D3 eligen N = 16** para σ=0,5: el mayor de los que pasan el piso del
50 % de detección, con ventaja de +38,8 puntos.

**D4: el N de máxima detección sería 64**, con ventaja +0,0. La distancia
entre los dos objetivos es exactamente el punto: perseguir detección lleva
a un régimen donde el método no aporta nada, y el N=32 que se había fijado
antes está en esa pendiente, con ventaja de sólo +9,7 puntos.

---

## 2. La ventana deslizante no cuesta detección: cuesta falsos positivos

Medido en el punto de resolución (σ=1,0, N=2), señal de cuatro ventanas con
el evento ocupando una, `step=1`:

| Configuración | Detección | Falsos positivos |
|---|---|---|
| Ventana conocida (lo que suponían los experimentos previos) | 57,4 % | 1 % por ventana |
| Deslizante, evento alineado al borde | 59,3 % | **7,1 % por señal** |
| Deslizante, evento desplazado media ventana | 59,9 % | **7,1 % por señal** |

Dos resultados, los dos contra lo esperado:

**El desalineamiento no cuesta nada.** Se esperaba que una ventana cubriendo
el evento a medias lo diluyera; con `step=1` siempre hay alguna ventana bien
puesta, y la diferencia entre alineado y desplazado (59,3 % contra 59,9 %)
está dentro del ruido de 300 ensayos.

**El costo real es de especificidad.** Deslizar multiplica las
oportunidades de disparar: con un objetivo del 1 % por ventana, la tasa por
señal sube a 7,1 %. Ése es el precio de no saber dónde está el evento, y
aparece en los falsos positivos, no en el recall. Si el punto de operación
se declara por señal y no por ventana, hay que recalibrar.

---

## 3. Radios: {1, 2} es el punto justo

Medido en σ=1,0, N=2, confusión por nodo sobre 300 realizaciones × 6 zonas:

| Radios | Candidatos | Detección | Recall | Precisión | F1 |
|---|---|---|---|---|---|
| {1} | 22 | 43,9 % | 16,8 % | 67,3 % | 0,267 |
| **{1, 2}** | **41** | **54,6 %** | **42,0 %** | **82,6 %** | **0,554** |
| {1, 2, 3} | 56 | 57,1 % | 43,1 % | 77,0 % | 0,549 |

**Escanear sólo radio 1 tira la mitad de la detección y dos tercios del
recall.** Es la confirmación de lo que motivó el cambio: un evento a
profundidad 2 abarca ~12 nodos y una bola de radio 1 tiene ~6, así que ni
acertando de lleno puede cubrirlo.

**Agregar radio 3 no compensa.** Sube la detección 2,5 puntos y el recall
1,1, pero baja la precisión 5,6 —hay más candidatos, y más candidatos es
más oportunidad de que uno grande acierte por casualidad— y el F1 empeora.
El defecto `{1, 2}` queda confirmado por medición.

---

## 4. El Difuminador como prefiltro: rechazado, y por qué importa

### Lo que parecía

| τ | Detección |
|---|---|
| **Sin filtro** | **55,8 %** |
| 0,05 – 1,5 | **100 %** |
| 2,239 | 99,7 % |
| 3,0 | 96,0 % |
| 5,0 | 82,3 % |
| 10,0 | 64,1 % |
| 20,0 | 60,6 % |

De 55,8 % a 100 %. Sobre esa tabla, el Difuminador sería el mejor
componente del detector.

### Respuesta a la pregunta declarada en D5

**El óptimo de detección no coincide con el rango estable de filtrado.** El
óptimo es una meseta que va de τ=0,05 a τ=1,5, mientras el rango estable
medido para filtrar es `[0,447, 2,239]`. La meseta se extiende **muy por
debajo** del rango estable —toda la región que para filtrar se declaró
degenerada, porque la señal colapsa al núcleo, para detectar es óptima— y
se corta justo en el extremo superior del rango estable.

Tiene sentido: para filtrar importa preservar la señal, y para detectar sólo
importa el contraste entre el grupo y el resto. La región donde el filtro
"destruye la señal" es la región donde destruye sobre todo el ruido.

**Es el resultado propio que anticipaba D5: el τ que el Afinador debe
ajustar depende de para qué se use el filtro.** Optimizar τ para calidad de
filtrado y usarlo para detectar sería optimizar el objetivo equivocado.

### Y por qué el prefiltro queda rechazado igual

La ganancia es espuria. **El Difuminador rompe la invariancia a sumar una
constante**, que es la propiedad que hacía robusto al escaneo.

`diffuse(1)` no es constante: a τ=0,05 va de 0,8524 a 1,2426, y a τ=2,239
de 0,9563 a 1,0714. El vector constante no está en el núcleo de `L_norm`,
así que el filtro lo deforma, y el contraste después detecta esa deformación.

Consecuencia, medida sobre un **modo común** —toda la zona corrida 2σ, que
el detector *no* debe marcar porque no hay discordancia con la vecindad—:

| Zona | Sin filtro | τ=0,05 | τ=0,447 | τ=1,0 |
|---|---|---|---|---|
| centro | 0,0 % | 100 % | 100 % | 100 % |
| chipre | 0,0 % | 100 % | 100 % | 100 % |
| la_enea | 0,7 % | 100 % | 100 % | 100 % |
| palermo | 0,3 % | 100 % | 100 % | 100 % |
| palogrande | 0,3 % | 100 % | 100 % | 100 % |
| universitario | 0,3 % | 100 % | 100 % | 100 % |

**Sin filtro el detector rechaza el modo común correctamente. Con filtro lo
marca siempre, con cualquier τ.** Lo que la tabla de detección mostraba como
mejora no era detectar mejor los eventos colectivos: era detectar cualquier
corrimiento, incluidos los que debe ignorar. El prefiltro convierte un
detector de discordancia local en un detector de nivel medio.

**`prefilter_tau` queda apagado por defecto, con esta medición detrás.**

Es el cuarto caso del patrón que documenta el README del monitor: un
argumento sobre invariancia y filtrado que sonaba correcto —la firma es de
baja frecuencia, el filtro es paso-bajo, luego debería ayudar— y que la
medición desmiente por una razón lateral que el argumento no contemplaba.

---

## 5. Dónde pierde: anomalías individuales

Anomalía de un solo medidor a +6σ, la que el simulador ya produce:

| N | Umbral por medidor | Escaneo | Ventaja |
|---|---|---|---|
| 1 | **99,7 %** | 33,3 % | **−66,3 %** |
| 16 | 100 % | 100 % | +0,0 % |

Con un instante el detector pierde por 66 puntos. Con la ventana de
operación los dos saturan y la diferencia desaparece, pero eso no rescata al
método: significa que en ese régimen el umbral resuelve el caso solo.

La conclusión operativa no cambia: **un monitor completo necesita los dos**,
una regla por medidor para lo puntual y este escaneo para lo colectivo.
Reclamar que el método espectral "detecta mejor" sin acotar a qué no lo
sostienen las mediciones.

---

## 6. Qué se lleva la tesis

1. **El punto de operación es N=16 con σ=0,5**, elegido por ventaja (D1–D3)
   y no por detección. A ese punto el escaneo detecta el 93,6 % contra el
   54,8 % del umbral: **+38,8 puntos**. El N=32 que se había fijado antes
   deja la ventaja en +9,7.

2. **La ventaja obedece a `σ·√N ≈ 2`.** Es máxima justo por debajo del
   umbral de visibilidad individual. Da una regla de diseño transferible:
   ante un evento de magnitud conocida, la ventana que más aporta es
   `N ≈ (2/σ)²`.

3. **El Difuminador no sirve como prefiltro de este detector**, y la razón
   es de especificidad, no de sensibilidad. Es un resultado negativo con
   evidencia, no una omisión.

4. **El τ óptimo depende del uso.** Para filtrar, `[0,447, 2,239]`; para
   detectar, la meseta llega hasta τ=0,05. El Afinador tiene que saber para
   qué está ajustando.

5. **Radios {1, 2}** confirmado por medición, con {1} y {1,2,3} peores por
   razones distintas.

---

## 7. Qué no cubre esta medición

* **El modo común se probó como corrimiento uniforme de toda la zona**,
  construido a mano. La familia de evento correspondiente no existe en el
  inyector, así que no hay verdad de referencia ni casos negativos
  etiquetados. Es la familia que más urge después de esta medición.
* **Sólo `depth=2` y sólo `voltaje_v`.**
* **Ruido gaussiano independiente entre medidores.** Correlación espacial
  real cambiaría el fondo para los dos métodos.
* **La calibración del deslizante es por ventana, no por señal.** Si el
  punto de operación se declara por señal hay que recalibrar, y las tasas
  de detección bajarían.
* **Sin costo computacional.** El escaneo evalúa 41 candidatos por ventana
  y por zona; en un nodo de borde eso importa y no está medido.
