# ESTADO — Punto de partida para retomar

Estado descrito: árbol en **`b3ed026`**, verificado el **2026-08-09**.

La referencia es al árbol sobre el que se tomaron las mediciones de acá, no
al commit que edita este archivo: un archivo no puede citar su propio hash,
y las dos veces que se intentó quedó desactualizado al commitear.

Este archivo existe para que alguien —el autor incluido, dentro de dos
semanas— pueda retomar sin releer toda la historia. Si algo de acá
contradice al código, gana el código y hay que actualizar esto.

---

## 1. Dónde está todo

| Paquete | Qué es | Tests |
|---|---|---|
| `services/monitor-gsp` | Grafo AMI, aparato espectral, Difuminador y **detector** | 295, cobertura 98,3 % |
| `services/event-injector` | Inyector de eventos correlacionados con verdad de referencia | 77 + 13 de integración |

Los dos con `ruff` y `mypy --strict` limpios. La dependencia va en un solo
sentido: `event-injector` → `monitor-gsp`, y **nunca al revés**. Hay un test
que falla si el inyector importa algo del detector.

### Artefactos versionados de los que dependen todos los resultados

| Archivo | Qué fija | Procedencia |
|---|---|---|
| `data/topologies/manizales_150.json` | Los 150 medidores | `data/topologies/README.md` |
| `data/schemas/payload_schema_v1.json` | Límites duros del productor | `data/schemas/README.md` |
| `data/profiles/manizales_signal_v1.json` | Dónde vive la señal: μ y σ espacial | `data/profiles/README.md` |

Ninguna cifra de la tesis debería existir sin poder rastrearse a uno de
estos tres.

---

## 2. Qué está construido

### `graph/` — el sustrato (ADR-003)

`geo` (proyección elipsoidal), `types`, `spectral` (`A → L → L_norm → eigh
→ GFT`), `builder` (k-NN k=4 por unión, seis subgrafos zonales) y `filter`
(el Difuminador, `exp(−λ/(τ·λmax))`).

Commits: `26df917`, `6be2378`, `cef4b5a`, `b2498f8`.

### `detector/` — el núcleo de detección (ADR-004)

Escaneo local sobre ventana: contrasta cada vecindario contra el resto de
su zona y **reporta qué nodos marcó**.

```python
from urbia_monitor_gsp.detector import CollectiveScanDetector, DetectorConfig
det = CollectiveScanDetector(zona, sigma_spatial=4.4012, config=DetectorConfig())
det.calibrate(seed=20260808, n_instants=len(lecturas))   # por señal
detecciones = det.detect(lecturas)
det.node_mask(detecciones, len(lecturas))                # para la confusión
```

Punto de operación por defecto: **ventana 16, radios {1, 2}, 1 % de falsos
positivos**. Commits `ed2986f`, `49a62f3`, `10f23b1`.

### `services/event-injector` — los eventos

Familia implementada: desviación colectiva sutil. Magnitud en **múltiplos
de σ espacial**, no en porcentaje. Commit `c1ffdab`.

---

## 3. Qué se midió y dónde está

| Experimento | Pregunta | Resultado central |
|---|---|---|
| `difuminador-tau` | ¿Cómo se comporta el filtro? | Signo del exponente invertido en la fuente; rango estable τ ∈ [0,447, 2,239] |
| `perfil-senal` | ¿Dónde vive la señal? | σ/media 2,00 % en voltaje, 35 % en corriente y potencia |
| `firma-espectral` | ¿Dónde está la firma en el espectro? | Individual en alta frecuencia, colectiva en baja |
| `magnitud-duracion` | ¿Cuánto ayuda integrar? | Ayuda mucho, **y al umbral también** |
| `detector-colectivo` | Punto de operación, radios, τ | N=16; prefiltro rechazado |
| `detector-deslizante` | ¿Y en condición realista? | N=16 sobrevive y la ventaja **sube** a +49,6 |

Cada uno tiene su `RESULTADOS.md` con las tablas y su `results/medicion.json`
con los datos crudos. Todos reproducibles sin cluster.

**Aviso de lectura.** Las cifras de detección de `firma-espectral` son las
del instrumento de entonces —radio 1, un instante— y no las del detector.
Sus mediciones **espectrales** no caducan.

### Las cifras que hay que saber

| | |
|---|---|
| Punto de operación | ventana 16, radios {1,2}, 1 % FPR por señal |
| Detección de eventos colectivos | **79,4 %** contra 29,8 % del umbral |
| Localización por nodo | recall **92,1 %**, precisión 77,2 %, F1 0,839 |
| Dónde pierde | anomalía individual: **33,3 %** contra 99,7 % del umbral |
| Ley del punto de operación | la ventaja es máxima donde `σ·√N ≈ 2`, o sea `N ≈ (2/σ)²` |

---

## 4. Qué quedó decidido

| ADR | Decisión |
|---|---|
| **ADR-003** | Construcción del grafo: vecindad geográfica declarada, seis subgrafos, k-NN k=4 por unión, proyección elipsoidal, corrección de signo del Difuminador |
| **ADR-004** | Detector por escaneo local; paso-alto de E6 descartado como núcleo; punto de operación; sin preprocesado espectral; **H3 reformulada** |

`ADR-001` y `ADR-002` siguen vacíos (0 bytes, del 1 de mayo). Hay
`TEMPLATE.md` si se los quiere escribir.

### H3, como quedó enunciada

> Sobre eventos donde la anomalía es la **coherencia de un grupo conectado**
> del grafo y no el valor de ningún medidor individual, un escaneo local
> detecta significativamente más que un umbral por medidor calibrado al
> mismo falso positivo. La ventaja es máxima cuando `σ·√N ≈ 2` y se anula al
> alejarse. El método además **localiza** el grupo afectado.

Con su alcance declarado: **peor que el umbral en anomalías individuales**,
33,3 % contra 99,7 %. El punto de operación se eligió por **máxima ventaja
sobre el umbral**, no por máxima detección — son criterios distintos y dan
respuestas distintas (N=16 contra N=32).

---

## 5. Advertencias metodológicas

Lo que más caro salió de aprender. Quien toque el preprocesado, el escaneo
o cualquier cifra de la tesis debería leer esto antes que el código.

Las tres primeras son formas de equivocarse que **ningún test detecta**,
porque en las tres el código está bien y lo que falla es el razonamiento
sobre lo que el código significa.

### 5.1 Cuatro veces un argumento de invariancia sonó correcto y falló

Cuatro veces se razonó sobre invariancia o filtrado, el argumento era
formalmente correcto, y la conclusión que se sacó resultó falsa al medirla.

1. *"`E_D` es invariante al modo cero, no hay que centrar."* Invariante al
   **núcleo** (`√d`), no al **nivel medio**. Una señal plana de 220 V da
   `E_D_norm` de 8 876 a 21 672 contra ~286 del ruido: el 98 % penaliza el
   estado normal.
2. *"Centrar por la media corrompe `E_D`."* Lo que remueve es estorbo:
   removerlo sube el AUC de 0,661 a 0,986.
3. *"El contraste ya es invariante al nivel medio, proyectar fuera de `u₀`
   da lo mismo."* Cuesta de 40 a 77 puntos de detección: `u₀ ∝ √d` no es
   constante y deja un sesgo determinista de hasta 42σ por bola.
4. *"La firma es de baja frecuencia y el Difuminador es paso-bajo, luego
   ayuda."* Sube la detección de 55,8 % a 100 % **y marca el 100 % de los
   modos comunes**, que debe ignorar. La ganancia era dejar de distinguir.

**El patrón.** Una invariancia siempre lo es *respecto de un subespacio*, y
el estado físicamente normal de esta señal —todos los medidores en 220 V—
no vive en el núcleo del operador que se estaba usando.

**La regla.** Ninguna decisión de preprocesado entra sin medirla contra la
tasa de detección. El argumento formal sirve para saber qué medir.

### 5.2 No mezclar los dos lados de la frontera

El contraste que mide el detector es la diferencia entre la media del grupo
afectado y la del resto. **Cualquier operación que mezcle los dos lados de
esa frontera destruye la señal.** Tres vías, medidas contra un evento a
profundidad 2:

| Vía | Efecto | Contraste conservado |
|---|---|---|
| Filtrar a través de la frontera | El paso-bajo suaviza la discontinuidad | — (rompe además el rechazo de modo común) |
| Candidato más chico que el evento | Los afectados que quedan fuera contaminan la muestra de control | **59 %** (radio 1) |
| Candidato del tamaño del evento | — | **100 %** (radio 2) |
| Candidato más grande | Los sanos diluyen la muestra afectada | **60 %** (radio 3) |

Las dos formas de errar el tamaño cuestan casi lo mismo, 41 % y 40 %: la
contaminación entra por una muestra o por la otra y el estadístico las trata
igual. **Corolario**: el escaneo tiene que ofrecer candidatos que puedan
coincidir con el tamaño del evento, y nada en la ruta de detección puede
promediar a través de la frontera.

### 5.3 Una cifra correcta, citada fuera de su configuración

**Es la forma de error que más veces apareció en este desarrollo, y la
única que ningún test detecta.** No hay número mal calculado ni cuenta mal
hecha: la cifra reproduce exacto contra su medición. Lo que está mal es
que se la lee en un contexto que no es el suyo.

Ejemplos reales, todos corregidos:

* El README del módulo decía que el detector rinde **33,4 %** en anomalías
  individuales. Correcto — para `firma-espectral`, que escaneaba radio 1
  sobre un instante. El módulo tiene por defecto radios {1,2}, donde la
  cifra es 33,3 %, y el evento colectivo pasa de 18,9 % a 23,4 %.
* El docstring de `DEFAULT_WINDOW` justificaba N=16 con 93,6 % contra
  54,8 %. Correcto — con ventana conocida y falso positivo por ventana. En
  la condición realista es 79,4 % contra 29,8 %, y la ventaja **crece** de
  +38,8 a +49,6.
* Se afirmó que "la ventaja del método está en N ≤ 2". Correcto para σ=1,5;
  falso en general, porque el óptimo obedece a `σ·√N ≈ 2` y para σ=0,5 cae
  en N=16.
* Se propuso cambiar el defecto de radios a {1} citando que {1,2} costaba
  51 puntos y que r=1 daba 100 % de recall. Ninguna de las dos cifras
  existe en ninguna medición; el recall con r=1 va de 29,6 % a 67,8 %.

Los cuatro casos tienen la misma forma: una cifra tomada de un mensaje o de
un documento anterior, sin volver a la medición que la produjo.

**La regla.** Ninguna cifra se cita sin su configuración al lado. Cuando
una cifra viaja de un documento a otro hay que preguntar de qué corrida
salió y con qué parámetros, no si el número está bien copiado. Los
`RESULTADOS.md` llevan encabezado de configuración por esto, y los
`results/medicion.json` están versionados para poder volver a verificar sin
rehacer la medición.

### 5.4 Sobre la disciplina de medición

Dos prácticas que se adoptaron sobre la marcha y conviene mantener:

* **Los criterios de un experimento se commitean antes de correrlo** (ver
  `58c7d2f` y `526dc40`). El punto de operación sale de aplicar reglas
  declaradas, no de elegir las cifras que quedan bien. Cuando hizo falta
  agregar un criterio después, se marcó explícitamente como posterior y no
  se usó como veredicto.
* **Una comparación medida en un punto saturado no es un resultado**: si
  las dos configuraciones aciertan siempre, no distinguen nada. Las
  comparaciones van donde hay resolución.

---

## 6. Qué está pendiente, por prioridad

### 6.1 La curva de degradación por tamaño de grupo — **lo más urgente**

Durante un tiempo esto se anotó como "falta la familia de modo común en el
inyector". Está mal planteado, y el planteo equivocado escondía el problema
real.

**El modo común no es una familia aparte: es el régimen de grupo grande de
la desviación colectiva.** Un corrimiento uniforme de toda la zona es el
caso límite `m = n` de un grupo que crece, no un tipo distinto de evento. No
hay discordancia con la vecindad y el detector no debe marcarlo. En medio
—entre el medidor solo y la zona entera— hay un continuo del que **no se
midió ningún punto**.

Lo que falta, entonces, no es implementar una familia sino **medir la curva
de detección contra tamaño de grupo**. El caso extremo se construyó a mano
para evaluar el prefiltro, y con eso se **descartó un componente entero**
—el Difuminador como prefiltro— sobre dos puntos saturados, 0 % y 100 %,
sin verdad de referencia y sin nada medido entre ellos.

Tres consecuencias, y ninguna se ve desde el planteo viejo:

* Las cifras por zona que sostienen ese descarte (0,0–0,7 % contra 100 %)
  **no tienen corrida trazable**: no hay código en `run.py` que las produzca
  ni entrada en `results/medicion.json`. Sólo existe el test de mecanismo
  sobre una rejilla sintética.
* La comparación está **saturada en los dos extremos**, y por §5.4 eso no es
  un resultado. El mecanismo (`diffuse(1)` no es constante) es sólido; la
  medición que lo acompaña no tiene resolución.
* **El punto de operación publicado está medido en el tamaño más favorable.**
  La familia actual a `depth=2` da 11–12 nodos sobre zonas de 20 a 30, o sea
  `m ≈ n/2`, que es donde el contraste de dos muestras predice su máximo. El
  79,4 % es correcto y su configuración de tamaño no está declarada.

El límite de aplicabilidad del método —a partir de qué tamaño de grupo el
escaneo cae por debajo de un umbral por medidor— es material de tesis y hoy
no existe.

Lo mide `experiments/tamano-grupo/`. El contrato ya lo prevé:
`InjectedEvent.expected_detectable` existe desde el principio, y con el
tamaño como eje se deriva por álgebra (`m < n`) en vez de fijarse a mano.

### 6.2 Qué optimiza el Afinador — ADR-004 §7

Se pensaba el ciclo Difuminador → detección, y **ese ciclo está roto**: el
filtro no participa en la detección, así que τ no tiene función de
recompensa por ese lado. Tres lecturas posibles, ninguna medida:

* τ optimiza el filtrado y el filtrado sirve para otra cosa (QoS, tráfico).
* El Afinador ajusta otro parámetro — la ventana, con `N ≈ (2/σ)²` y σ
  estimable en línea, tiene recompensa clara.
* El filtro entra en otro lugar del ciclo.

### 6.3 Costo computacional

49 ventanas × 41 bolas por señal y por zona es lo que un nodo de borde
tendría que sostener. **Sin medir.** Importa para la primera línea de
contribución —bajar el monitor al borde— y hoy no hay ninguna cifra.

### 6.4 Ampliar la evaluación

* Otras magnitudes: todo está medido sobre `voltaje_v`, la única con σ/media
  del 2 %. Corriente y potencia tienen 35 % y están sin evaluar.
* Otras profundidades de vecindario.
* Eventos más cortos que la ventana.
* Ruido con correlación espacial: hoy la señal de fondo es gaussiana
  independiente entre medidores.

### 6.5 Deudas menores registradas

* Pesos binarios contra gaussianos sobre los 150: sin medir (ADR-003 §4.3).
* Precisión por nodo estancada en 77–80 %: es el techo de escanear bolas.
  Subir requiere candidatos que no sean bolas.
* `energia_kwh`: el contrato del productor declara
  `additionalProperties: false` y no lo incluye, pero el backend lo lista
  como campo de entrada. A revisar cuando se toque `urbia-platform`.
* `ADR-001` y `ADR-002` vacíos.

---

## 7. Cómo verificar que todo sigue en pie

```bash
cd services/monitor-gsp && .venv/bin/python -m pytest -q -m "not integration"
cd services/event-injector && .venv/bin/python -m pytest -q

# con base de datos: recontrasta el perfil congelado contra la base viva
POSTGRES_PASSWORD=$(docker inspect urbia-postgres \
  --format '{{range .Config.Env}}{{println .}}{{end}}' \
  | sed -n 's/^POSTGRES_PASSWORD=//p') \
  services/event-injector/.venv/bin/python -m pytest -q -m integration
```

Los experimentos se rehacen con `run.py` de cada directorio y no necesitan
cluster salvo `perfil-senal`.
