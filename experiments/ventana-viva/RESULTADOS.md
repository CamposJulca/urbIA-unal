# El ancho de bin: de llegadas asíncronas a ventanas densas

| | |
|---|---|
| Fecha | 2026-08-09 |
| Script | `experiments/ventana-viva/run.py` |
| Criterios | `CRITERIOS.md`, commiteado antes de la corrida |
| Ventana | 2026-08-08T23:32:04Z → 2026-08-09T23:32:04Z (24 h) |
| Fuente | `ami_telemetry` en `urbia-postgres` (neusi-stage), 2 503 450 filas |
| Padrón | 150 medidores en 6 zonas; **ningún medidor silencioso** (C9) |

Mide disponibilidad de datos, no desempeño de detección. Ninguna cifra de
acá dice nada sobre si el detector acierta.

---

## 1. El barrido

Mínimo entre las seis zonas en cada columna:

| Ancho (s) | s/ventana | Completitud por bin | **Completitud por ventana** | Celdas con >1 lectura |
|---|---|---|---|---|
| 4 | 64 | 69,6 % | 0,0 % | 0,0 % |
| 5 | 80 | 88,1 % | 0,0 % | 0,0 % |
| **6** | **96** | **99,9 %** | **99,6 %** | 18,8 % |
| 7 | 112 | 99,9 % | 99,5 % | 38,5 % |
| 8 | 128 | 99,9 % | 99,5 % | 58,3 % |
| 10 | 160 | 99,9 % | 99,4 % | 97,9 % |
| 12 | 192 | 99,9 % | 99,3 % | 99,9 % |
| 15 | 240 | 99,9 % | 99,1 % | 99,9 % |
| 20 | 320 | 99,9 % | 98,9 % | 99,9 % |

**Ancho elegido: 6 s, por C6.1** — el menor con completitud por ventana
≥ 95 % en las seis zonas. Zona que limita: `centro`, con 99,58 %.

La predicción de §2 de `CRITERIOS.md` se cumple: la transición está entre 5
y 7 s y la completitud por bin es prácticamente 1 desde 6 s. El periodo
entre mensajes medido sobre 24 h —p50 5,052 s, p95 5,432, p99 5,442— es
consistente con los cinco minutos que la sostenían.

### Por qué la completitud por ventana era la métrica correcta

A 5 s la completitud por bin es 88,1 % y **la completitud por ventana es
cero**. No "baja": es cero, en las seis zonas. Elegir por la métrica por bin
habría dado un ancho con el que el servicio no habría producido **ninguna**
detección, y el error habría aparecido recién en operación.

La caída no es la que predecía `p¹⁶` con bins independientes —0,88¹⁶ ≈ 0,13,
no 0— y la razón está en la sección siguiente.

---

## 2. El hallazgo: los bins son todo o nada

A 6 s, sobre 14 398 bins por zona y 24 h:

| Zona | n | Bins completos | Bins **parciales** | Bins vacíos | Faltantes máx. |
|---|---|---|---|---|---|
| centro | 25 | 14 383 | **0** | 15 | 0 |
| chipre | 25 | 14 383 | **0** | 15 | 0 |
| la_enea | 25 | 14 383 | **0** | 15 | 0 |
| palermo | 25 | 14 383 | **0** | 15 | 0 |
| palogrande | 30 | 14 383 | **0** | 15 | 0 |
| universitario | 20 | 14 383 | **0** | 15 | 0 |

**No hay un solo bin parcial.** Cada bin tiene los `n` medidores de su zona
o no tiene ninguno, y los 15 bins vacíos son los mismos en las seis zonas.

El productor publica los 150 medidores en ráfaga. La consecuencia es que el
modo de falla real no es "a un medidor le falta la lectura" sino "el
productor se detuvo": ~90 s de silencio total en 24 h, simultáneo en todas
las zonas.

A 5 s el mismo mecanismo explica el desastre: la ráfaga cruza el borde del
bin y lo parte en dos mitades. De ahí que la mediana de faltantes en un bin
parcial sea exactamente `n/2` —12 sobre 25, 15 sobre 30, 10 sobre 20— y que
las rachas de 16 bins completos no existan.

**Esto es una propiedad de este simulador, no de la AMI real.** En un
despliegue real los medidores se caen de a uno y la lógica de saltar la
ventana por zona sí discrimina entre zonas. Acá va a disparar en las seis a
la vez o en ninguna. Queda declarado para que nadie lea la métrica de
Prometheus como si midiera salud por zona.

### Los huecos largos

450 huecos de más de 10 s en 24 h, repartidos sobre los 150 medidores, con
máximo de 38,03 s. Son ~3 por medidor por día y ya están dentro del 99,58 %:
un hueco de 38 s deja ~7 bins vacíos y con eso caen ~22 ventanas.

---

## 3. Lo que cuesta la regla de llenado

A 6 s, el 10,6 % de las celdas de `centro` y `chipre` y el 18,8 % de las
otras cuatro contienen 2 lecturas, y C4 descarta la más vieja. Nunca hay 3.

Ese descarte es deliberado y no es una pérdida a lamentar: promediar las 2
lecturas reduciría la dispersión espacial en `√2` en el 19 % de las celdas,
y el umbral congelado —calibrado con la σ del perfil— quedaría alto sin que
nada avise. El costo de preservar la calibración es tirar una lectura de
cada cinco.

Es también el argumento contra los anchos mayores: a 10 s el 97,9 % de las
celdas tiene múltiples lecturas y se estaría descartando casi la mitad del
dato recibido, sin ganar completitud.

---

## 4. La gracia de cierre (C7)

C7 pedía medir el retardo de transporte y declarar la gracia; la regla se
fija acá, **después** de ver la medición, y se marca como posterior según
§5.4 de `ESTADO.md`. No participa en la elección del ancho, que salió de
C6 sin tocar esto.

Retardo `recibido_en − timestamp_utc` sobre 2 503 450 mensajes:

| | |
|---|---|
| p50 | 0,033 s |
| p99 | 0,152 s |
| máximo | 4,206 s |
| mínimo | **−0,676 s** |
| Mensajes sobre 1 s | 216 (0,0086 %) |
| Mensajes sobre 2 s | 70 |
| Mensajes sobre 3 s | 21 |

**Gracia declarada: 5 s**, por encima del máximo observado.

El razonamiento es asimétrico a propósito. La gracia sólo cuesta latencia —5 s
sobre una ventana que ya cubre 96 s— mientras que quedarse corto cuesta
ventanas enteras: por el hallazgo de §2 un mensaje que llega tarde no deja
un bin parcial sino que, si es de la ráfaga, arrastra la zona completa, y un
bin perdido invalida las 16 ventanas que lo contienen. Con gracia de 2 s los
70 mensajes que exceden ese umbral podrían costar hasta ~1 120
ventana-zonas por día; con 5 s, ninguno de los observados.

El mínimo negativo indica que el reloj del productor adelanta al del host de
la base hasta 0,68 s. No afecta el cierre —un mensaje "del futuro" llega
antes de que su bin cierre, no después— pero sí implica que `timestamp_utc`
no es un reloj común confiable a escala de sub-segundo. Con bins de 6 s hay
margen de sobra; a bins de 1 s habría que revisarlo.

Advertencia de lectura: `recibido_en` lo estampa el **backend**, no el
monitor, e incluye el encolado por asyncio. Es una cota superior del retardo
broker → proceso, que es lo que la gracia necesita acotar, así que usarla es
conservador.

---

## 5. Qué queda fijado

| Parámetro | Valor | De dónde sale |
|---|---|---|
| Ancho de bin | 6 s | C6.1 sobre este barrido |
| Ventana | 16 bins = 96 s de reloj | Punto de operación de `DEFAULT_WINDOW` |
| Gracia de cierre | 5 s | §4, posterior a la medición |
| Rejilla | absoluta, `floor(epoch/6)` | C3 |
| Llenado | lectura más reciente del bin | C4 |
| Ciclo útil esperado | 99,6 % de las ventanas | Este barrido |

El ciclo útil es una **expectativa medida sobre 24 h de este productor**, no
una garantía. Lo que el servicio informe por Prometheus es el dato de
operación; esta cifra es la línea contra la cual compararlo.
