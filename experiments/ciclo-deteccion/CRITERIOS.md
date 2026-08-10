# Criterios — Cuánto tarda un ciclo de detección, y qué intervalo se elige

**Commiteado antes de correr el experimento.** Es la práctica que fija
`ESTADO.md` §5.4: el veredicto sale de aplicar reglas declaradas, no de
elegir después las cifras que quedan bien. Cualquier criterio que haga falta
agregar más adelante se marca explícitamente como posterior y no se usa como
veredicto.

| | |
|---|---|
| Fecha | 2026-08-09 |
| Artefactos | `manizales_150.json`, `manizales_signal_v1.json`, `manizales_scan_v1.json` |
| Máquina | neusi-stage (`192.168.40.11`, Ryzen 7 5700G, 15 GB) |
| Deuda que cierra | `ESTADO.md` §6.3, la mitad en línea |

---

## 1. Qué pregunta, y por qué hace falta preguntarlo

El servicio del monitor despierta cada tanto, arma una ventana por zona y
corre el detector sobre las seis. **Ese intervalo no se puede fijar a ojo.**
Si un ciclo tarda más que el intervalo, el servicio no se atrasa una vez: se
atrasa de forma acumulativa, y la distancia entre el instante que analiza y
el instante que corre crece sin techo hasta que la memoria o el operador lo
noten.

La estructura de la ventana ya pone un límite duro: `ZoneWindow.emit`
entrega **una ventana por bin cerrado**, y `Window.skipped_bins` cuenta los
bins que se cerraron sin que nadie los mirara. Con el bin de 6 s que fijó
`experiments/ventana-viva/`, un ciclo que no quepa en 6 s pierde bins, y
cada bin perdido invalida las 16 ventanas que lo contenían.

Lo que falta es la otra mitad: **cuánto tarda el ciclo de verdad**. Hoy no
hay ninguna cifra. `ESTADO.md` §6.3 lo anota como pendiente y dice por qué
importa más allá de esto —es la línea base contra la cual se va a medir H1
cuando el monitor baje al nodo de borde—.

### Lo que este experimento NO puede responder

**La cifra que salga vale para neusi-stage y para nadie más.** El nodo de
borde de H1 es una RPi5 ARM de 8 GB contra un Ryzen 7 5700G: citar acá un
número y leerlo allá es exactamente el error de `ESTADO.md` §5.3. Lo que
transfiere es el **método** —el mismo `run.py` corrido en la RPi5— y la
descomposición por componente, que dice qué parte del ciclo escala con qué.

---

## 2. Qué es un ciclo, exactamente

Se declara antes de medir para que la cifra no dependa de dónde se ponga la
frontera. Un ciclo es, **por cada una de las seis zonas**:

1. `ZoneWindow.emit(now)` — cerrar el bin, verificar completitud, apilar la
   matriz densa `(16, n)`.
2. `CollectiveScanDetector.detect(matriz)` — promediar la ventana, calcular
   el contraste sobre todas las bolas candidatas, ordenar el ranking y armar
   la `Detection`.
3. `Detection.to_dict()` y `json.dumps` — serializar lo que se publica.

**No entra** la ingesta: `ZoneWindow.observe` corre en el hilo de red de
paho a medida que llegan los mensajes, no dentro del ciclo. Se mide aparte
(C4) porque compite por el GIL con el ciclo y ese costo es real.

**No entra** la publicación por MQTT ni el scrape de Prometheus: son E/S y
su latencia no la manda el detector.

**No entra** el arranque —leer el padrón, construir el grafo, diagonalizar,
enumerar las bolas—: es una sola vez. Se mide aparte (C5) porque en el nodo
de borde importa para el tiempo de arranque.

---

## 3. Predicción, antes de medir

Se declara para que el experimento pueda contradecirla.

El trabajo por zona y ventana es: una media sobre `(16, n)`, un producto
`(1, n) × (n, B)` con `B` entre 35 y 50 bolas, y la construcción de `B`
objetos `ScanCandidate`. Lo único ya medido es lo último: **34–49 µs por
ventana** según la zona (`6120be1`). El álgebra sobre matrices de 25 a 30
columnas debería costar menos que eso, porque a ese tamaño NumPy está
dominado por el overhead de la llamada y no por las operaciones.

Predicción: el ciclo completo de seis zonas cae entre **0,5 y 2 ms**, con la
construcción del ranking como componente mayor, y el margen contra el bin de
6 s es de tres órdenes de magnitud.

Si la predicción falla por mucho, el sospechoso es `emit`: apilar la matriz
densa recorre 16 diccionarios por zona y eso es Python puro.

---

## 4. Criterios

### C1 — Condición de medición

Sobre la topología versionada `manizales_150.json` y la calibración
versionada `manizales_scan_v1.json`, **no** contra la base ni el broker: el
costo de cómputo no depende de dónde salieron los medidores, y depender de
la base haría el experimento irreproducible sin cluster.

Las ventanas se alimentan con lecturas sintéticas que llenan todos los bins,
porque **el ciclo que interesa medir es el caro**: un bin incompleto corta
antes de llegar al detector y cuesta menos. Medir el caso barato daría un
intervalo que no aguanta el caso normal.

La señal es ruido gaussiano con la σ del perfil versionado. No importa si
detecta o no: **el costo del escaneo no depende del valor de la señal**
—recorre las mismas bolas—, y elegir una señal con evento sólo cambiaría
qué bola gana.

### C2 — Repeticiones y estadísticos

**1 000 ciclos** completos, precedidos de **100 de calentamiento** que se
descartan: la primera pasada paga la caché fría de NumPy y no representa el
régimen.

Se reportan p50, p95, p99 y máximo. **El estadístico que decide es el p99**,
no la media: lo que rompe el servicio no es el ciclo típico sino la cola.

`time.perf_counter_ns` y no `time.time`: el segundo puede saltar hacia atrás
con un ajuste de NTP y produciría duraciones negativas.

### C3 — Descomposición por componente y por zona

Se mide por separado `emit`, `detect` y la serialización, y dentro de
`detect` se reporta el costo por zona junto a su `n_meters` y su número de
bolas candidatas.

Sin esto la cifra global no transfiere a otra máquina ni a otra topología:
saber que el ciclo tarda `x` no dice qué pasa con doce zonas o con 300
medidores. Con la descomposición sí, porque el número de bolas es conocido
de antemano.

### C4 — Costo de la ingesta

`ZoneWindow.observe` sobre lecturas sintéticas, en µs por mensaje.

El productor actual publica 150 medidores cada ~5 s, o sea unos **30 msg/s**
en régimen. La ingesta corre en el hilo de red de paho, que compite por el
GIL con el ciclo, así que su costo agregado es tiempo que el ciclo no tiene.

Se reporta la fracción de segundo que consume la ingesta a 30 msg/s.

### C5 — Costo del arranque

Construir el grafo desde los 150 medidores —proyección, k-NN, Laplaciano,
`eigh` por zona— y enumerar las bolas candidatas de las seis zonas.

Es una sola vez por proceso, pero es lo que tarda el servicio en estar listo
después de un reinicio, y en la RPi5 es donde más va a doler.

### C6 — Regla de elección del intervalo

En orden, sin excepciones. Sea `c` el **p99** de la duración del ciclo
completo y `b = 6 s` el ancho de bin de `ventana-viva`.

1. **Condición de viabilidad:** `c ≤ b/10`, es decir 600 ms. Si no se
   cumple, **no se elige intervalo**: se declara que el ciclo no cabe y que
   hay que repartir las zonas entre procesos o subir el ancho de bin. El
   factor 10 es una elección declarada, no una derivación: deja al servicio
   nueve décimas partes de cada bin ociosas para absorber una ráfaga, un
   scrape o una máquina cargada por otro contenedor.
2. **Intervalo:** el mayor `t` tal que `t = b/k` con `k` entero, `t ≤ b/2` y
   `t ≥ 20·c`.
   * `t ≤ b/2` garantiza que ningún bin se cierre sin que el servicio
     despierte al menos una vez dentro de él, que es la condición para que
     `skipped_bins` se mantenga en cero.
   * `t ≥ 20·c` mantiene el ciclo por debajo del 5 % del intervalo.
   * `t = b/k` mantiene el despertar en fase con la rejilla de bins, que es
     absoluta.
3. **Si los dos límites de (2) son incompatibles** —esto es, si `20·c >
   b/2`— gana `t = b/2` y se declara explícitamente qué fracción del
   intervalo consume el ciclo.

La latencia que agrega la granularidad del intervalo es a lo sumo `t`, sobre
una ventana que ya cubre 96 s de reloj y que espera 5 s de gracia. Se
reporta como fracción de esos 96 s para que quede claro que no es el término
que manda.

### C7 — Qué se hace con el resultado

El intervalo elegido entra al servicio como **valor por defecto declarado**,
con puntero a este experimento, del mismo modo que `WindowConfig` lleva los
suyos. No se copia el número a ningún otro lado sin su configuración al
lado.

Y una consecuencia operativa: como el margen se mide acá y el mundo cambia,
el servicio expone la duración del ciclo como métrica de Prometheus. Este
experimento fija el punto de partida; la métrica dice si dejó de valer.

### C8 — Qué NO responde este experimento

* **Nada sobre el nodo de borde.** Ver §1. La cifra es de neusi-stage.
* **Nada sobre tasa de detección.** No hay verdad de referencia acá; que el
  detector marque o no marque es irrelevante para el costo.
* **Nada sobre el costo de la evaluación offline** —2 000 realizaciones de
  Monte Carlo por zona—, que es la otra mitad de `ESTADO.md` §6.3 y tiene
  otro régimen: allá el trabajo está vectorizado sobre realizaciones y acá
  es una ventana por vez.
* **Nada sobre concurrencia.** Se mide un proceso con las seis zonas en
  serie, que es como está escrito el servicio.

---

## 5. Salida

`results/medicion.json` con los tiempos crudos por componente y por zona, y
`RESULTADOS.md` con las tablas y el intervalo elegido aplicando C6.
