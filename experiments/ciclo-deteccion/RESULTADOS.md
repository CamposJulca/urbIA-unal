# Resultados — Costo del ciclo de detección

| | |
|---|---|
| Criterios | `CRITERIOS.md`, commiteados en `6ec0e62` antes de esta corrida |
| Fecha | 2026-08-09 |
| Máquina | neusi-stage (`192.168.40.11`, Ryzen 7 5700G, 15 GB) |
| Artefactos | `manizales-v1`, `manizales-signal-v1`, `manizales-scan-v1` |
| Punto de operación | ventana 16 bins, `step=1`, radios {1, 2}, bin de 6 s |
| Repeticiones | 1 000 ciclos medidos, 100 de calentamiento descartados |
| Datos crudos | `results/medicion.json` |

**Todas las cifras de acá valen para esta máquina y esta topología.** El
nodo de borde de H1 es una RPi5 ARM: leer estos números allá sería el error
de `ESTADO.md` §5.3. Lo que transfiere es el método y la descomposición.

Las duraciones son de reloj y no son deterministas: dos corridas del mismo
código dieron p99 de 1,458 ms y 1,394 ms. Las tablas son las de la corrida
guardada en `results/medicion.json`.

---

## 1. La cifra que decide

**El ciclo completo sobre las seis zonas tarda 1,39 ms en el p99.** El
límite de viabilidad de C6 es 600 ms. Cabe con **430 veces de margen**.

| | µs |
|---|---|
| p50 | 1 164 |
| p95 | 1 265 |
| **p99** | **1 394** |
| máx | 1 619 |

La cola es corta: el máximo sobre 1 000 ciclos está a 1,4× del p50. No hay
un régimen lento escondido que el p50 tape.

---

## 2. Intervalo elegido, aplicando C6

**3 segundos.**

| Paso de C6 | Valor |
|---|---|
| Condición de viabilidad: `c ≤ b/10` | 1,394 ms ≤ 600 ms ✓ |
| Techo `t ≤ b/2` | 3 s |
| Piso `t ≥ 20·c` | 27,9 ms |
| Mayor `t = b/k` entre los dos | **3 s** (`k = 2`) |

Consecuencias, para poder auditarlas después:

* El ciclo consume el **0,047 %** del intervalo. El servicio pasa
  esencialmente todo su tiempo dormido.
* La latencia que agrega la granularidad es de a lo sumo 3 s, sobre una
  ventana que cubre 96 s de reloj: **3,1 %**. No es el término que manda; la
  gracia de cierre de bin ya aporta 5 s por sí sola.
* Con `t = b/2` el servicio despierta dos veces por bin, así que ningún bin
  se cierra sin ser visto y `Window.skipped_bins` debe mantenerse en cero.
  Si deja de estarlo, no es este intervalo lo que falló: es que el ciclo
  dejó de caber, y la métrica de Prometheus lo va a decir.

---

## 3. Dónde se va el tiempo

| Componente | p50 µs | p99 µs | % del ciclo |
|---|---|---|---|
| `emit` — cerrar bin y apilar la matriz densa | 309 | 371 | 26,6 % |
| `detect` — promediar, escanear, ordenar el ranking | 543 | 653 | 46,6 % |
| serializar — `to_dict` + `json.dumps` | 306 | 358 | 26,3 % |

### La predicción, contrastada

La predicción de §3 de `CRITERIOS.md` fue *"entre 0,5 y 2 ms, con la
construcción del ranking como componente mayor"*.

**El total acertó y la descomposición no.** Ningún componente domina: los
tres están dentro de un factor de dos. La construcción del ranking —medida
aparte en `6120be1` en 34–49 µs por ventana, o sea unos 250 µs por ciclo—
es aproximadamente la mitad de `detect`, y por lo tanto **un 21 % del
ciclo**, no la parte mayor.

Lo que no estaba previsto es que **serializar el ranking cuesta casi tanto
como calcularlo**, 306 µs contra 250 µs. Es el mismo material recorrido dos
veces: una para construir los objetos y otra para volcarlos a JSON.

No cambia ninguna decisión —el margen es de 430×— pero sí dice dónde habría
que mirar si algún día no cupiera: el camino barato no es recortar el
escaneo sino no materializar el ranking dos veces.

---

## 4. Por zona

| Zona | n | bolas | p50 µs | p99 µs |
|---|---|---|---|---|
| centro | 25 | 39 | 145,3 | 228,7 |
| chipre | 25 | 43 | 143,9 | 178,8 |
| la_enea | 25 | 43 | 141,1 | 178,0 |
| palermo | 25 | 38 | 135,4 | 168,8 |
| palogrande | 30 | 50 | 146,1 | 186,1 |
| universitario | 20 | 35 | 132,1 | 173,2 |

`emit` + `detect`, sin serialización.

**El costo casi no depende del tamaño.** Entre `universitario` (20
medidores, 35 bolas) y `palogrande` (30 medidores, 50 bolas) hay un 43 % más
de bolas y un 11 % más de tiempo. A esta escala el trabajo lo domina el
overhead de las llamadas de Python y NumPy, no el álgebra: las matrices
tienen 20 a 30 columnas.

**Cómo extrapolar, con cuidado.** La parte que sí escala con el número de
bolas es la construcción del ranking, y crece lineal. La parte fija —16
diccionarios recorridos en `emit`, una media, una multiplicación de
matrices— no. Una topología con el doble de zonas duplica el ciclo, porque
las zonas se recorren en serie; una topología con el doble de medidores por
zona no lo duplica.

---

## 5. Arranque e ingesta

### Arranque (C5)

**10,4 ms** hasta el primer ciclo: 4,0 ms de construcción del grafo
—proyección, k-NN, Laplaciano y `eigh` de las seis zonas— y 6,4 ms de
enumerar las bolas candidatas y adoptar los umbrales congelados.

No incluye leer el padrón de PostgreSQL, que es E/S y depende de la red.

Importa para el nodo de borde: la diagonalización es `O(n³)` por zona y es
lo primero que se va a notar en ARM. Con 20 a 30 nodos por zona es
irrelevante acá.

### Ingesta (C4)

**3,33 µs por mensaje.** A los 30 msg/s del productor actual eso es el
**0,010 % de cada segundo**.

La ingesta corre en el hilo de red de paho y compite por el GIL con el
ciclo, así que ese tiempo es tiempo que el ciclo no tiene. A esta tasa el
efecto no es medible. La cifra que hay que vigilar si el padrón crece: a
30 000 msg/s la ingesta sola consumiría el 10 % de un núcleo.

---

## 6. Tamaño del payload — **posterior a los criterios**

Se agregó **después** de la primera corrida y **no participa del veredicto**
de C6, que ya estaba decidido con tres órdenes de margen. Se mide porque la
corrida mostró que serializar cuesta un cuarto del ciclo, y porque el
defecto de `top_k` del publicador hay que elegirlo con una cifra en vez de a
ojo.

| `top_k` | B por detección (máx) | B por ciclo |
|---|---|---|
| 0 | 265 | 1 571 |
| 1 | 379 | 2 259 |
| 5 | 847 | 5 058 |
| 10 | 1 431 | 8 555 |
| **completo** | **6 130** | **30 632** |

Con el ranking completo y un ciclo cada 6 s, el monitor publica **5,1 kB/s**.
La telemetría que consume son unos 12 kB/s a 30 msg/s, así que el monitor
agrega alrededor de un 40 % sobre lo que ya circula.

El broker de `192.168.40.12` es compartido con proyectos cliente
(`CLAUDE.md` §10.4). 5 kB/s no es un problema con esta topología, y la
proporcionalidad es la que importa: el payload crece con el número de bolas,
o sea aproximadamente lineal en el número de medidores. **El defecto queda
en el ranking completo** —es lo que permite reconstruir el punto de
operación a posteriori— y `top_k` existe para recortarlo si la topología
crece.

---

## 7. Qué NO dice esto

* **Nada sobre el nodo de borde.** Ver el encabezado.
* **Nada sobre tasa de detección.** La señal es ruido; el costo del escaneo
  no depende de su valor.
* **Nada sobre el costo de la evaluación offline** —2 000 realizaciones de
  Monte Carlo por zona—, que es la otra mitad de `ESTADO.md` §6.3 y está
  vectorizada sobre realizaciones, otro régimen. Como referencia suelta:
  congelar los umbrales de las seis zonas tarda unos 2 s por zona, y validar
  100 h de nulo por zona lleva el script entero a 40 s.
* **Nada sobre concurrencia.** Un proceso, seis zonas en serie.
* **Nada sobre el caso incompleto.** Se midió el ciclo caro a propósito
  (C1); un bin incompleto corta antes del detector y cuesta menos.
