# El detector en condición realista: deslizamiento y FPR por señal

| | |
|---|---|
| Fecha | 2026-08-08 |
| Script | `experiments/detector-deslizante/run.py` |
| Criterios | commit previo a la corrida, E1–E5 en el docstring |
| Configuración | `voltaje_v`, σ=0,5, `depth=2`, 200 realizaciones, 6 zonas |
| Condición | `step=1`, evento en posición sorteada, FPR calibrado **por señal** |

Rehace bajo deslizamiento lo que `experiments/detector-colectivo/` había
medido con ventana conocida. Aquella curva daba una sola ventana
perfectamente alineada con el evento; ésta recorre `4N` instantes sin saber
dónde está.

---

## 1. La curva de ventaja, en condición real

| Radios | N | Ventanas/señal | Escaneo | Umbral | Ventaja | FPR esc. | FPR umb. |
|---|---|---|---|---|---|---|---|
| {1} | 4 | 13 | 6,9 % | 2,3 % | +4,7 % | 1,3 % | 1,0 % |
| {1} | 8 | 25 | 19,2 % | 7,8 % | +11,4 % | 0,8 % | 1,0 % |
| {1} | 16 | 49 | 55,2 % | 29,6 % | +25,7 % | 1,1 % | 1,0 % |
| {1} | 32 | 97 | 93,5 % | 68,0 % | +25,5 % | 0,9 % | 1,0 % |
| {1,2} | 4 | 13 | 8,4 % | 2,8 % | +5,6 % | 1,1 % | 1,0 % |
| {1,2} | 8 | 25 | 32,5 % | 9,4 % | +23,1 % | 1,5 % | 1,0 % |
| **{1,2}** | **16** | **49** | **79,4 %** | **29,8 %** | **+49,6 %** | 1,0 % | 1,0 % |
| {1,2} | 32 | 97 | 99,5 % | 70,2 % | +29,3 % | 0,8 % | 1,0 % |

El FPR empírico queda entre 0,8 % y 1,5 % contra el 1 % declarado, para los
dos comparadores: la calibración por señal funciona.

### N=16 sobrevive, y con más margen

**E3 confirma N=16**, con ventaja de +49,6 puntos. Es el mismo punto de
operación que había elegido la medición con ventana conocida, así que el
defecto del módulo no cambia.

**Lo que sí cambia es el tamaño de la ventaja, y hacia arriba:**

| Condición | Escaneo | Umbral | Ventaja |
|---|---|---|---|
| Ventana conocida | 93,6 % | 54,8 % | +38,8 |
| **Deslizante** | 79,4 % | 29,8 % | **+49,6** |

Deslizar cuesta detección a los dos —el escaneo baja 14 puntos y el umbral
25— pero **le cuesta bastante más al umbral**. La razón es de comparaciones
múltiples: el umbral toma el máximo sobre 49 ventanas × 25 medidores, todas
sus comparaciones prácticamente independientes, y su distribución nula se
infla mucho. El escaneo toma el máximo sobre 49 ventanas × 41 bolas, pero
las bolas se solapan fuertemente y el número efectivo de comparaciones es
mucho menor.

**Es el resultado que más favorece a H3 de todos los medidos**, y aparece
justamente al pasar a la condición realista. Los experimentos anteriores,
al suponer la ventana conocida, estaban **subestimando** la ventaja del
método.

---

## 2. Confusión por nodo en el punto de operación

Medida sólo sobre las señales detectadas (E5), uniendo los nodos que
marcaron todas las ventanas que se solapan con el evento:

| Radios | N | Recall | Precisión | F1 |
|---|---|---|---|---|
| {1} | 4 | 38,1 % | 64,8 % | 0,479 |
| {1} | 8 | 45,7 % | 70,5 % | 0,554 |
| {1} | 16 | 49,2 % | 67,8 % | 0,570 |
| {1} | 32 | 56,9 % | 66,1 % | 0,611 |
| {1,2} | 4 | 69,2 % | 67,0 % | 0,678 |
| {1,2} | 8 | 80,3 % | 76,1 % | 0,781 |
| **{1,2}** | **16** | **92,1 %** | **77,2 %** | **0,839** |
| {1,2} | 32 | 99,1 % | 79,5 % | 0,881 |

**En el punto de operación el detector localiza bien: recall 92,1 % y
precisión 77,2 %.** Cuando detecta un evento, marca casi todos sus nodos y
tres de cada cuatro nodos marcados son correctos.

La precisión se estanca cerca del 77–80 % y no sube con N. Es el techo que
impone escanear bolas: el grupo verdadero tiene ~12 nodos y la bola de
radio 2 que mejor lo cubre tiene ~12 también, pero no son los mismos doce.
Subir de ahí requeriría grupos candidatos que no sean bolas.

---

## 3. Radios: la confirmación fuerte

En el punto de operación, pasar de {1} a {1,2}:

| | {1} | {1,2} |
|---|---|---|
| Detección | 55,2 % | **79,4 %** |
| Ventaja sobre el umbral | +25,7 | **+49,6** |
| Recall por nodo | 49,2 % | **92,1 %** |
| F1 | 0,570 | **0,839** |

Escanear sólo radio 1 **cuesta la mitad de la ventaja y casi la mitad del
recall**. Es el argumento más fuerte que apareció para el defecto `{1, 2}`,
y viene de la condición realista, no de la idealizada.

---

## 4. Qué queda sin cubrir

* **Una sola magnitud (σ=0,5) y una sola profundidad.** El punto de
  operación se re-eligió sobre la misma σ que lo había elegido antes; la
  regla `N ≈ (2/σ)²` no se re-verificó bajo deslizamiento.
* **El evento dura exactamente una ventana.** Eventos más cortos que la
  ventana quedan diluidos y no se midió cuánto.
* **200 realizaciones por celda**, la mitad que en los experimentos
  previos, por el costo de recorrer 49 a 97 ventanas por señal.
* **El modo común sigue sin familia en el inyector.** Se probó a mano en
  `detector-colectivo` y descartó el prefiltro; sigue sin verdad de
  referencia.
* **Sin costo computacional.** 49 ventanas × 41 bolas por señal y por zona
  es lo que un nodo de borde tendría que sostener, y no está medido.
