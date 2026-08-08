# Magnitud × duración: dónde hay margen, y dónde H3 aporta

Medición previa al diseño del detector. La anterior
(`experiments/firma-espectral/`) dejó el problema acotado: sobre un instante
y a 1σ el oráculo llega al 49 %, así que fijar el detector ahí sería
optimizarlo para un régimen sin margen.

| | |
|---|---|
| Fecha | 2026-08-08 |
| Script | `experiments/magnitud-duracion/run.py` |
| Criterios declarados en | commit `58c7d2f`, **antes** de correr el experimento |
| Sustrato | topología de los 150, perfil `manizales-signal-v1` |
| Configuración | `voltaje_v`, `depth=2`, 400 realizaciones por celda, 6 zonas |
| Reproducir | `services/event-injector/.venv/bin/python experiments/magnitud-duracion/run.py` |

Los criterios C1 a C6 están en el docstring del script y se commitearon
antes de que existiera ninguna cifra. Lo que sigue es aplicarlos.

---

## 1. El barrido

Tasa de detección con el umbral calibrado al 1 % de falsos positivos (C1).

**Escaneo — el detector realizable**

| σ | N=1 | N=2 | N=5 | N=10 | N=20 | N=50 |
|---|---|---|---|---|---|---|
| 0,5 | 4,3 % | 6,9 % | 22,5 % | 53,8 % | 90,9 % | 100 % |
| 1,0 | 15,9 % | 42,6 % | 93,8 % | 99,8 % | 100 % | 100 % |
| 1,5 | 47,1 % | 87,8 % | 99,9 % | 100 % | 100 % | 100 % |
| 2,0 | 76,5 % | 98,7 % | 100 % | 100 % | 100 % | 100 % |
| 3,0 | 99,7 % | 100 % | 100 % | 100 % | 100 % | 100 % |

**Umbral por medidor — el comparador de H3**

| σ | N=1 | N=2 | N=5 | N=10 | N=20 | N=50 |
|---|---|---|---|---|---|---|
| 0,5 | 4,3 % | 3,5 % | 13,5 % | 34,5 % | 79,2 % | 100 % |
| 1,0 | 7,9 % | 17,1 % | 77,1 % | 99,5 % | 100 % | 100 % |
| 1,5 | 20,1 % | 70,1 % | 99,9 % | 100 % | 100 % | 100 % |
| 2,0 | 46,6 % | 97,7 % | 100 % | 100 % | 100 % | 100 % |
| 3,0 | 98,2 % | 100 % | 100 % | 100 % | 100 % | 100 % |

**Oráculo — el techo de información**

| σ | N=1 | N=2 | N=5 | N=10 | N=20 | N=50 |
|---|---|---|---|---|---|---|
| 0,5 | 7,6 % | 22,9 % | 59,2 % | 87,1 % | 99,8 % | 100 % |
| 1,0 | 48,2 % | 82,0 % | 99,6 % | 100 % | 100 % | 100 % |
| 1,5 | 85,5 % | 98,8 % | 100 % | 100 % | 100 % | 100 % |
| 2,0 | 98,3 % | 99,9 % | 100 % | 100 % | 100 % | 100 % |
| 3,0 | 100 % | 100 % | 100 % | 100 % | 100 % | 100 % |

---

## 2. Las cuatro respuestas

**La integración mejora muchísimo.** A 1σ el escaneo pasa de 15,9 % con un
instante a 93,8 % con cinco. Promediar N instantes reduce la dispersión del
ruido en `√N` mientras la desviación colectiva permanece constante, así que
el efecto es el esperado y es grande.

**El techo deja de ser el límite enseguida.** El oráculo pasa de 48,2 % a
99,6 % entre N=1 y N=5 a 1σ. A partir de ahí no hay información faltante:
lo que separe a un detector del 100 % es su forma, no la física del
problema.

**El umbral también mejora, y ése es el resultado que importa.** No sólo
mejora: mejora lo suficiente para alcanzar al escaneo. A 1σ y N=5 el
escaneo va 93,8 % contra 77,1 %; a N=10, 99,8 % contra 99,5 %. La razón es
estructural — integrar convierte un evento colectivo sutil en uno
individualmente visible. Con N=20 y σ=0,5, cada medidor afectado está a
`0,5·√20 = 2,24σ` de su media, y eso ya lo ve una regla por medidor.

**La ventaja de H3 no crece con la duración: se encoge.** El escaneo agrupa
los ~12 medidores del vecindario y gana un factor fijo en relación
señal-ruido; la integración da `√N` **a los dos**. Medido, el escaneo
equivale a un umbral con la magnitud multiplicada por **1,25 a 1,35**: a
N=1, el escaneo con 1,5σ (47,1 %) rinde como el umbral con 2,0σ (46,6 %).
Es una ganancia constante en magnitud equivalente, no una ley de escala
distinta.

---

## 3. Aplicación de los criterios declarados

**C4 — aplanamiento.** Primer N donde duplicar N agrega menos de 5 puntos:

| σ | Aplana en |
|---|---|
| 0,5 | N=1 |
| 1,0 | **N=10** |
| 1,5 | **N=5** |
| 2,0 | **N=5** |
| 3,0 | N=1 |

**C4 falla en los dos extremos, y es un defecto del criterio, no de los
datos.** A 0,5σ dice "aplana en N=1" porque el salto de 4,3 % a 6,9 % es
chico — pero es chico porque no se detecta nada, no porque se haya llegado
a algún régimen. A 3,0σ dice lo mismo porque ya está saturado. El criterio
no distingue "plano porque no pasa nada" de "plano porque ya está todo
detectado". Sirve en el rango intermedio, que es donde hacía falta.

**C3 — régimen operativo: σ=0,5, N=20.** Es la menor magnitud que alcanza
la potencia del 80 % con el detector realizable (90,9 %).

**C5 — veredicto sobre H3 en ese régimen: NO APORTA.**

| | Medido | Exigido |
|---|---|---|
| Cociente escaneo / umbral | 1,15× | ≥ 2× |
| Diferencia absoluta | 11,7 puntos | ≥ 20 puntos |

Las dos condiciones fallan. **Bajo los criterios declarados antes de mirar
los datos, H3 no aporta en el régimen operativo elegido.**

---

## 4. Por qué falla, y qué sí es cierto

El barrido tiene una estructura que explica el resultado y que no depende
de dónde se pongan los cortes:

| σ | N | Escaneo | Umbral | Cociente | Diferencia | ¿C5? |
|---|---|---|---|---|---|---|
| 1,0 | 2 | 42,6 % | 17,1 % | **2,49×** | **25,5 pts** | **sí** |
| 1,5 | 1 | 47,1 % | 20,1 % | **2,35×** | **27,0 pts** | **sí** |
| 2,0 | 1 | 76,5 % | 46,6 % | 1,64× | 29,9 pts | no |
| 0,5 | 10 | 53,8 % | 34,5 % | 1,56× | 19,2 pts | no |
| 1,5 | 2 | 87,8 % | 70,1 % | 1,25× | 17,7 pts | no |
| 1,0 | 5 | 93,8 % | 77,1 % | 1,22× | 16,7 pts | no |
| 0,5 | 20 | 90,9 % | 79,2 % | 1,15× | 11,7 pts | no |

**Las dos únicas celdas que cumplen C5 detectan el 42,6 % y el 47,1 %.**
Están muy por debajo de la potencia exigida. Y donde la potencia llega al
80 %, los dos métodos ya convergieron.

Dicho sin rodeos: **la ventaja del método de grafo es máxima justo donde el
sistema no sirve, y desaparece donde el sistema funciona.** No es un
artefacto de los cortes elegidos: es la forma de la superficie.

---

## 5. Una crítica a mis propios criterios, marcada como posterior

Lo que sigue se observó **después** de ver los resultados y por lo tanto
**no puede usarse como veredicto**. Se registra porque afecta el diseño de
la próxima medición, no la conclusión de ésta.

**C5 usa el cociente de tasas de detección, que es la escala equivocada
cerca de la saturación.** En el régimen elegido, el escaneo baja la tasa de
**fallo** del 20,8 % al 9,1 %: un cociente de **2,29×**, que sí superaría un
umbral de 2×. La forma convencional de comparar detectores cerca del techo
es por la tasa de fallo, no por la de acierto.

**C3 empuja hacia la región donde H3 no puede ganar.** Al pedir la menor
magnitud, fuerza la mayor duración, y la duración es precisamente lo que
permite al umbral alcanzar al escaneo. C3 responde bien a "cuál es el evento
más sutil que se puede detectar", que es una pregunta legítima, pero no a
"dónde aporta el método", que es la de H3.

**Ninguna de las dos cosas cambia el resultado reportado en §3.** Cambiar el
criterio después de ver los datos es exactamente lo que estos criterios
existían para impedir. Si en una próxima ronda se decide medir contra tasa
de fallo, hay que declararlo antes y volver a correr.

---

## 6. Qué se lleva la tesis

1. **H3 hay que reformularla.** "El método espectral detecta mejor que un
   umbral" no se sostiene como afirmación general: es falsa en anomalías
   individuales (33,4 % contra 99,0 %, medición anterior) y no alcanza el
   listón declarado en el régimen operativo colectivo. Lo que sí se
   sostiene, y está medido, es una afirmación más chica y más precisa: **el
   método de grafo equivale a un umbral con la magnitud multiplicada por
   1,25 a 1,35, y esa ganancia es constante — no crece con la duración del
   evento.**

2. **La duración es la variable dominante, y beneficia a los dos métodos.**
   Cualquier arquitectura de monitor gana más integrando que eligiendo
   detector. Eso es un resultado de ingeniería útil aunque sea incómodo
   para la hipótesis.

3. **Hay una región de interés real, aunque no cumpla el listón:** eventos
   cortos y de magnitud media (σ≈1,0–1,5, N≤2), donde el escaneo detecta
   entre 2,3× y 2,5× más que el umbral. Si la tesis quiere reclamar la
   ventaja del método, es ahí, y hay que argumentar por qué ese régimen
   importa operativamente — por ejemplo, si la latencia de detección tiene
   valor propio, detectar el 47 % en un instante puede valer más que el
   91 % en veinte.

---

## 7. Qué no cubre esta medición

* **La ventana del evento se supone conocida** (C6). Un detector real
  tendría que buscarla, lo que agrega comparaciones múltiples y baja las
  tasas. Favorece por igual a los tres comparadores, así que no invalida
  la comparación, pero sí infla los valores absolutos.
* **Sólo `depth=2` y sólo `voltaje_v`.** Las otras profundidades y las
  magnitudes con σ/media del 35 % están sin barrer.
* **Ruido gaussiano independiente entre medidores.** Correlación espacial
  real en la señal de fondo cambiaría el problema para los dos métodos, y
  probablemente no por igual.
* **El escaneo usa bolas de radio 1 y no corrige por comparaciones
  múltiples.** Un escaneo con radio adaptativo podría acercarse más al
  oráculo, que a N=1 y 1σ tiene 32 puntos de margen sobre él.
* **Sin costo computacional.** El escaneo evalúa `n` grupos por instante y
  por zona; en un nodo de borde eso importa y no está medido.
