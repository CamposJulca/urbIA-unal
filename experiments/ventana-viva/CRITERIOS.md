# Criterios — De llegadas asíncronas a ventanas densas

**Commiteado antes de correr el experimento.** Es la práctica que fija
`ESTADO.md` §5.4: el veredicto sale de aplicar reglas declaradas, no de
elegir después las cifras que quedan bien. Cualquier criterio que haga falta
agregar más adelante se marca explícitamente como posterior y no se usa como
veredicto.

| | |
|---|---|
| Fecha | 2026-08-09 |
| Artefactos | `manizales_150.json`, `manizales_signal_v1.json` |
| Fuente | `ami_telemetry` en `urbia-postgres` (neusi-stage) |

---

## 1. Qué pregunta, y por qué hace falta preguntarlo

El detector consume una matriz `(T, n)` **densa**: cada instante con los `n`
medidores de la zona, alineados al orden canónico del grafo. La telemetría
real no llega así. Cada medidor publica por su cuenta y **no hay rejilla
temporal compartida**: en los cinco minutos previos a escribir esto, 8 700
filas traían 8 622 valores distintos de `timestamp_utc`.

Construir la ventana pide entonces agrupar en bins de ancho fijo. El ancho
del bin es el único parámetro libre, y de él dependen dos cosas que se
oponen:

* **Bin angosto** — la ventana cubre menos tiempo de reloj, la detección es
  más ágil, y aumenta la probabilidad de que algún medidor no haya publicado
  dentro del bin.
* **Bin ancho** — casi todos los bins quedan completos, y la ventana de 16
  bins pasa a cubrir varios minutos de reloj.

Este experimento mide esa curva. **No mide nada sobre detección**: mide
disponibilidad de datos.

### La restricción que lo vuelve crítico

Está decidido que un bin incompleto **no se imputa ni se detecta**: la zona
no produce resultado y publica el motivo. Imputar inventaría justamente el
dato que el estadístico va a contrastar, y excluir al medidor cambiaría el
grafo, cuyo espectro está calculado sobre la topología completa.

La consecuencia es que la métrica que decide **no es la completitud por
bin sino la completitud por ventana**. Con completitud por bin `p` y bins
independientes, una ventana de 16 bins queda completa con probabilidad
`p¹⁶`: a `p = 0,99` eso es 0,85, y a `p = 0,95` es 0,44. Medir sólo `p`
llevaría a elegir un ancho con el que casi la mitad de las ventanas no
producen nada.

---

## 2. Predicción, antes de medir

Se declara para que el experimento pueda contradecirla.

El periodo entre mensajes de un mismo medidor, medido sobre cinco minutos,
va de 4,98 a 5,70 s con p50 5,06 y p95 5,46. Si el periodo estuviera acotado
por 5,70 s, **todo bin de ancho ≥ 5,70 s contendría al menos una lectura de
cada medidor vivo** y la completitud por bin sería 1 salvo por medidores
caídos.

Predicción: la transición ocurre entre 5 y 7 s, la completitud por bin es
prácticamente 1 a partir de 8 s, y la región interesante —donde la
completitud por ventana cae de forma visible— es 5–7 s.

Si la predicción falla, lo más probable es que la cola del periodo sea más
pesada de lo que muestran cinco minutos. Por eso se mide sobre 24 h.

---

## 3. Criterios

### C1 — Fuente y horizonte

`ami_telemetry`, las **24 h** anteriores al último `timestamp_utc`
disponible. Mismo horizonte que usó `perfil-senal` para congelar σ, para que
las dos mediciones hablen del mismo tramo de operación.

Sólo `voltaje_v`: es la magnitud sobre la que está medido todo el detector.
La disponibilidad no depende de la magnitud —llegan en el mismo mensaje—
así que la elección no cambia el resultado, pero se declara igual.

### C2 — Anchos barridos

`4, 5, 6, 7, 8, 10, 12, 15, 20` segundos.

Cubre la región predicha con resolución de 1 s y se extiende hasta 20 s, que
con 16 bins ya son 320 s de reloj por ventana.

### C3 — Rejilla absoluta

El bin de una lectura es `floor(epoch(timestamp_utc) / w)`, anclado a la
época Unix y **no** al arranque del proceso. Dos ejecuciones distintas —el
servicio en vivo y una reproducción offline— tienen que producir los mismos
bins sobre los mismos datos. Una rejilla relativa al arranque haría
irreproducible cualquier verificación posterior.

### C4 — Regla de llenado: la más reciente, nunca el promedio

Una celda `(medidor, bin)` se llena con la lectura de **mayor
`timestamp_utc`** dentro del bin. Si no hay ninguna, la celda queda vacía y
el bin es incompleto.

**Promediar las lecturas de un bin está prohibido, y no es una cuestión de
gusto.** El umbral del detector se congela con la σ espacial del perfil
versionado. Promediar `k` lecturas dentro del bin reduciría la dispersión
observada en `√k` sin que la calibración se entere, y el umbral quedaría
sistemáticamente alto: menos detecciones, con la tasa de falsos positivos
declarada dejando de corresponder a la real. Es la forma de §5.3 —una cifra
correcta operando fuera de su configuración— pero ocurriendo en silencio y
en producción.

Tomar la más reciente preserva la distribución marginal de la señal, que es
lo que la calibración supone.

### C5 — Qué se mide, por ancho y por zona

1. **Completitud por bin**: fracción de bins con los `n` medidores de la
   zona presentes.
2. **Completitud por ventana**: fracción de ventanas de 16 bins
   **consecutivos en la rejilla** con los 16 bins completos. Es la métrica
   que decide.
3. **Celdas con más de una lectura**: fracción, y máximo de lecturas en una
   celda. Cuantifica cuánto dato descarta C4.
4. **Medidores faltantes en un bin incompleto**: p50, p95 y máximo. Un
   faltante aislado y recurrente apunta a un medidor enfermo; muchos
   faltantes repartidos apuntan a que el ancho es corto.
5. **Bins vacíos en la rejilla**: bins sin ninguna lectura de la zona. Se
   cuentan aparte porque no son lo mismo que un bin parcial.

### C6 — Criterio de elección del ancho

En orden, sin excepciones:

1. El **menor** ancho con completitud por ventana ≥ 95 % en **las seis
   zonas**.
2. Si ninguno lo alcanza: el ancho que **maximiza el mínimo entre zonas** de
   la completitud por ventana; ante empate, el menor. Se declara el ciclo
   útil resultante y qué zona lo limita.

El 95 % no es arbitrario en su forma pero sí en su valor: es el umbral por
debajo del cual una de cada veinte ventanas no produce resultado, que es
donde el panel empieza a verse roto en vez de honesto. Queda declarado como
elección, no como derivación.

**Un ciclo útil menor que 1 no es un defecto del método.** Por la decisión
de no imputar, una ventana sin datos completos no produce detección, y eso
es visible en la métrica de Prometheus. Lo que este criterio evita es
elegirlo sin saberlo.

### C7 — Gracia de cierre de bin

Un bin no se puede cerrar en el instante de su borde: entre que un medidor
estampa `timestamp_utc` y el proceso recibe el mensaje hay transporte. Se
mide el p99 y el máximo de `recibido_en − timestamp_utc` sobre las 24 h y se
declara la gracia con la que el servicio cerrará cada bin.

Sobre cinco minutos ese retardo dio p50 0,03 s y máximo 0,28 s, pero cinco
minutos no dicen nada de la cola.

### C8 — Qué NO responde este experimento

* **Nada sobre tasa de detección.** No hay verdad de referencia en la
  telemetría real: si el detector marca algo acá, es una marca, no un
  acierto.
* **Nada sobre σ espacial.** El perfil congelado sigue siendo la fuente.
* **Nada sobre el intervalo del ciclo de detección**, que depende del costo
  de cómputo y se mide aparte.

### C9 — Medidor caído

Un medidor que deja de publicar deja incompletos **todos** los bins de su
zona, y por la decisión de no imputar esa zona deja de producir detecciones
mientras dure. Es el comportamiento buscado, no un caso a mitigar acá.

Se reporta si ocurrió durante las 24 h medidas, porque de haber ocurrido
contamina las cifras de C5 y hay que leerlas sabiéndolo.

---

## 4. Salida

`results/medicion.json` con los datos crudos por ancho y por zona, y
`RESULTADOS.md` con las tablas y el ancho elegido aplicando C6.
