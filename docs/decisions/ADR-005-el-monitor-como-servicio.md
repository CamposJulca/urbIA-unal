# ADR-005 — El monitor como servicio: ventana, silencio, ranking y topología

| | |
|---|---|
| Estado | Aceptado |
| Fecha | 2026-08-10 |
| Autor | Cristhiam Daniel Campos Julca |
| Ámbito | El monitor GSP corriendo como proceso: ingesta, ciclo, publicación y observabilidad |
| Código afectado | `services/monitor-gsp/src/urbia_monitor_gsp/service/`, `stream/window.py`, `infra/observability/prometheus.yml`, `docker-compose.yml` |
| Depende de | ADR-003 (construcción del grafo), ADR-004 (detector y punto de operación) |
| Cifras medidas en | `experiments/ventana-viva/`, `experiments/ciclo-deteccion/` |

---

## 1. Contexto

Al cerrar ADR-004 el detector estaba medido y documentado, pero era **una
biblioteca que sólo se usaba desde experimentos**. Nadie la ejecutaba. El
panel Edge de la consola pública era una maqueta, y la primera línea de
contribución —bajar el monitor del datacenter al nodo de borde— no se podía
ni empezar a medir, porque no había un proceso cuyo costo medir.

Volverlo un servicio obliga a decidir cuatro cosas que en un experimento no
se plantean, porque en un experimento los datos están todos, llegaron todos
a tiempo y el grafo no cambia mientras uno mira.

Este ADR registra esas cuatro decisiones. **Las cuatro tienen la misma
forma**: en cada una hay una opción que hace que el servicio siga
produciendo números cuando no debería, y esos números no se distinguen de
los buenos mirando la salida. Por eso las cuatro se resuelven del mismo
lado: **fallar ruidosamente antes que producir un resultado degradado**.

---

## 2. Decisión 1 — La ventana es temporal, no por conteo

**Se acumula por bins de reloj de 6 s sobre una rejilla absoluta anclada a
la época Unix, y una ventana son 16 bins consecutivos completos.**

La alternativa era una ventana por conteo: las últimas 16 lecturas de cada
medidor. Es más simple y está mal.

Un medidor que deja de publicar **no vacía su ventana por conteo: la deja
llena de instantes viejos.** El detector entonces compara la lectura de las
14:22 de un medidor contra la de las 14:19 de su vecino. El estadístico que
usa el escaneo local supone que todos los nodos de la zona corresponden al
mismo instante —es un contraste **espacial**—, así que una ventana
desalineada mide diferencias temporales y las reporta como si fueran
espaciales.

Nada avisa. El detector sigue devolviendo un número con la pinta de
siempre.

La rejilla es absoluta y no relativa al arranque del proceso para que dos
ejecuciones sobre los mismos datos produzcan los mismos bins, que es lo que
permite reproducir offline lo que pasó en vivo.

### 2.1 Los parámetros salen de una medición

| Parámetro | Valor | De dónde sale |
|---|---|---|
| Ancho de bin | 6 s | El **menor** ancho con completitud por ventana ≥ 95 % en las seis zonas; dio 99,6 %. A 5 s la completitud por bin todavía es 88,1 % pero la de ventana es **cero**, porque la ráfaga del productor cruza el borde y parte cada bin en dos. |
| Gracia de cierre | 5 s | Por encima del máximo retardo de transporte observado, 4,206 s sobre 2 503 450 mensajes. |
| Bins por ventana | 16 | El punto de operación de ADR-004, importado de `DEFAULT_WINDOW` para que no puedan desincronizarse. |

La asimetría de la gracia es deliberada: cuesta latencia sobre una ventana
que ya cubre 96 s, mientras que quedarse corto pierde bins enteros.

---

## 3. Decisión 2 — Una zona sin dato no produce resultado, y publica por qué

**Si a algún bin de la ventana le falta algún medidor de la zona, la zona no
produce detección. Publica el motivo en `<prefijo>/sin-ventana/<zona>` con
qué medidores faltaron y en cuántos bins.**

Se consideraron tres opciones y dos se descartan por la misma razón de
fondo: **cambian la cosa que se está midiendo**.

| Opción | Por qué no |
|---|---|
| **Imputar** el dato faltante | Inventa precisamente el dato que el estadístico va a contrastar. Se estaría midiendo el interpolador, no la red. |
| **Excluir** al medidor de la zona | Cambia el grafo. El espectro y el umbral están calculados sobre la topología completa; un subgrafo distinto tiene otra distribución nula y el corte deja de corresponder. |
| **No producir y decir por qué** | ✔ |

Hay además una razón operativa. Las dos primeras opciones **esconden** el
problema detrás de una detección degradada, que se ve exactamente igual que
una buena. La tercera lo vuelve visible: hay un topic, hay un contador de
Prometheus por zona y motivo, y hay una línea de log.

### 3.1 Calentamiento no es lo mismo que un medidor caído

El motivo distingue dos casos que un panel tiene que poder separar:

* `calentamiento` — la ventana alcanza hacia atrás más allá del primer bin
  que el proceso vio. Es historia que nunca existió. Dura los primeros 96 s
  y se resuelve sola.
* `bins_incompletos` — la ventana cae entera dentro de lo observado y aun
  así falta dato. Alguien dejó de publicar.

Sin esa distinción, un monitor recién arrancado y una zona con un medidor
muerto se ven idénticos.

---

## 4. Decisión 3 — Se publica el ranking completo de candidatas

**Cada ventana analizada se publica, haya o no detección, con el ranking
completo de bolas evaluadas y no sólo la ganadora.**

Tres cosas separadas, y conviene no confundirlas:

**Se publica la ventana sin detección** porque publicar sólo las detecciones
deja un registro en el que "no pasó nada" y "el detector estaba mirando para
otro lado" se ven igual: los dos son silencio. Con el estadístico y su
umbral en cada mensaje se puede reconstruir después bajo qué condiciones se
decidió.

**Se publica el ranking entero** porque ya está calculado —el escaneo evalúa
todas las bolas de radio 1 y 2 y las ordena— y guardar sólo el máximo impide
reconstruir el punto de operación a posteriori. Es la misma disciplina que
llevó a versionar la calibración: lo que sostiene un resultado se guarda.

**La detección sale además por un topic propio**, `<prefijo>/deteccion/<zona>`,
con el mismo cuerpo. Quien alerta no debería parsear 5,1 kB/s para encontrar
un evento por hora. La duplicación cuesta bytes sólo cuando hay detección,
que es cuando no importan.

### 4.1 El tamaño está medido, no estimado

De `experiments/ciclo-deteccion/` §6, sobre `manizales_150`:

| `top_k` | B por ciclo |
|---|---|
| 0 | 1 571 |
| 1 | 2 259 |
| 10 | 8 555 |
| **completo** | **30 632** |

Con una ventana cada 6 s son **5,1 kB/s**, contra los ~12 kB/s de la
telemetría que el monitor consume: agrega alrededor de un 40 % sobre lo que
ya circula. El broker de `192.168.40.12` es compartido con proyectos cliente
(`CLAUDE.md` §10.4), así que la cifra importa.

**El defecto queda en el ranking completo.** `top_k` existe para recortarlo
si la topología crece, porque el payload crece aproximadamente lineal en el
número de medidores. Medido en operación: 5 517 B por mensaje con 25
medidores y 39 candidatas.

---

## 5. Decisión 4 — La topología es bloqueante

**Si el grafo construido desde el padrón vivo no es el grafo con el que se
calibró el umbral, el servicio no arranca. Si cambia mientras corre, se
cae.**

Un umbral calibrado sobre otra topología produce detecciones que no
corresponden al sistema real. Y es el peor caso de todos los de este ADR,
porque **los números siguen saliendo con la misma pinta de siempre**: mismo
rango, misma frecuencia, mismo aspecto en el panel. No hay forma de notarlo
mirando la salida.

La verificación se hace por **huella de la topología** por zona: un hash del
padrón y de la adyacencia. La calibración la lleva guardada, y se
recontrasta al arrancar y cada `topology_check_seconds` (300 s por defecto).

Seguir andando con el umbral viejo sería peor que no andar, así que la
excepción se propaga y el proceso sale con código 2 —distinto del 1 del
fallo de arranque, para que el operador los separe sin leer los logs—.
Volverá a caerse al arrancar hasta que alguien recalibre con
`scripts/calibracion/congelar_umbrales.py`.

### 5.1 Una base inalcanzable no es una topología cambiada

Se distinguen a propósito. Si PostgreSQL no responde, la reverificación
**no concluye nada**: se anota como aviso, se incrementa
`urbia_monitor_verificaciones_topologia{resultado="fallo"}` y se reintenta al
turno siguiente.

Confundir las dos cosas haría que un corte de red apagara el monitor.

---

## 6. Consecuencias

### 6.1 Lo que esto habilita

* **Se puede empezar a medir H1.** Las series de Prometheus son la línea
  base contra la cual comparar el mismo servicio en neusi-edge-x86. La que
  importa no es el contador de detecciones sino
  `urbia_monitor_ciclo_segundos`.
* El panel Edge de la consola pública deja de tener que ser una maqueta:
  hay topics reales de los que leer.
* El ciclo es probable sin broker, sin base y sin registro global.
  `runtime` y `publisher` no importan paho ni prometheus, que es lo que
  permite que lo que se mude al borde sea el detector y no el andamiaje.

### 6.2 Lo que esto cuesta

* **Cuatro formas de que el servicio se niegue a arrancar.** Es lo buscado,
  pero significa que un despliegue con la calibración desactualizada no
  arranca en vez de arrancar a medias. Está documentado en el README.
* **Un medidor caído silencia su zona entera.** Es la consecuencia
  declarada de no imputar, y hay que poder verla: por eso
  `urbia_monitor_sin_ventana` está entre las dos series a vigilar.
* El monitor lee PostgreSQL para el padrón. En un nodo de borde sin base
  esto hay que resolverlo —padrón cacheado o servido por otra vía—, y hoy
  no está resuelto.

### 6.3 El intervalo del ciclo, y por qué no está elegido a ojo

3 s sale de aplicar la regla C6 de `experiments/ciclo-deteccion/`
—criterios commiteados **antes** de correr, en `6ec0e62`— al costo medido
del ciclo sobre las seis zonas: p99 de **1,39 ms** en neusi-stage. Los dos
límites son `t ≤ b/2`, para que ningún bin de 6 s se cierre sin que el
servicio despierte dentro de él, y `t ≥ 20·c`, para que el ciclo no pase del
5 % del intervalo. Con `c` tan chico manda el primero y da `t = 3 s`, donde
el ciclo consume el 0,047 %.

Si un ciclo tardara más que el bin, el servicio perdería bins de forma
**acumulativa** y no se recuperaría solo. La pérdida no es silenciosa
—`urbia_monitor_bins_saltados` la cuenta— pero es evitable de entrada, y
`validate_coherence` la rechaza al arrancar.

> **La cifra vale para neusi-stage y esta topología.** En la RPi5 ARM de H1
> hay que rehacer la medición con el mismo `run.py` antes de reusar el
> valor. Leerlo allá sería exactamente el error de `ESTADO.md` §5.3.

---

## 7. Lo que este ADR no decide

* **Cómo consume el backend estas anomalías.** Queda decidido que el
  consumidor se agrega sin tocar el de telemetría —ese backend sostiene el
  sitio público— pero no está implementado.
* **Si el umbral congelado corresponde a la dispersión real.** La hipótesis
  nula es sintética, con la σ del perfil versionado. Si la dispersión real
  fuera mayor, la tasa de falsos positivos en operación superaría el 1 %
  declarado. **Es medible y no está medido**: hay que contrastar la
  distribución del estadístico en operación contra la nula simulada. El
  servicio ya publica el estadístico de cada ventana, así que los datos para
  hacerlo se están acumulando.
* **Qué magnitudes además de `voltaje_v`.** Corriente y potencia tienen
  σ/media del 35 % contra el 2 % del voltaje y están sin evaluar.

---

## 8. Verificación en operación

Corrido en neusi-stage contra el broker de `192.168.40.12` el 2026-08-10,
sobre los 150 medidores reales:

| | |
|---|---|
| Padrón leído | 150 medidores, 6 zonas, huella coincidente con la calibración |
| Ventanas producidas | 416, las 6 zonas, una cada 6 s |
| Lecturas ingeridas | 14 800 aceptadas, 2 000 superadas dentro de su bin |
| Detecciones bajo tráfico normal | **0** |
| Bins saltados | 0 |
| Publicaciones fallidas | 0 |
| Reverificación de topología | 1, contra la base viva, sin desajuste |
| Duración del ciclo | 171 ciclos, media 0,833 ms, 98,2 % < 2 ms, 100 % < 5 ms |
| Tamaño del payload | 5 517 B con ranking completo de 39 candidatas |

La duración del ciclo en servicio es consistente con el p99 de 1,39 ms que
midió `experiments/ciclo-deteccion/` aislando el ciclo, lo cual era el
supuesto sobre el que se eligió el intervalo.

Las 2 000 lecturas "superadas" no son un problema: el productor publica cada
5 s sobre bins de 6 s, así que uno de cada seis bins recibe dos lecturas del
mismo medidor y la segunda reemplaza a la primera. Es el 11,9 %, cerca del
1/6 que predice la aritmética.

**Cero detecciones bajo tráfico normal no es prueba de que el detector
funcione** —para eso está la evaluación con verdad de referencia de
ADR-004—, sino de que el umbral congelado no dispara sobre la señal viva.
Es la mitad barata de la verificación; la otra mitad es la limitación de
§7 que sigue sin medir.
