# Criterios — Detección contra tamaño de grupo

**Commiteado antes de correr el experimento.** Es la práctica que fija
`ESTADO.md` §5.4: el veredicto sale de aplicar reglas declaradas, no de
elegir después las cifras que quedan bien. Cualquier criterio que haga falta
agregar más adelante se marca explícitamente como posterior y no se usa como
veredicto.

| | |
|---|---|
| Fecha | 2026-08-09 |
| Código del inyector | `b6d8f2b` |
| Artefactos | `manizales_150.json`, `payload_schema_v1.json`, `manizales_signal_v1.json` |
| Semilla base | `20260808` |

---

## 1. Qué pregunta

Entre un medidor solo y la zona entera hay un continuo de tamaños de grupo, y
**no se midió ningún punto intermedio**. Todo lo publicado está en `depth=2`,
que da 11–12 nodos sobre zonas de 20 a 30 — es decir `m ≈ n/2`.

Cuatro preguntas, en orden de importancia para la tesis:

1. **La curva completa** de detección contra tamaño de grupo, sobre las seis
   zonas.
2. **Dónde el escaneo cae por debajo del umbral por medidor.** Ése es el
   límite de aplicabilidad del método y va declarado en la tesis.
3. **Si ese límite obedece a la ley del perímetro.**
4. **El caso extremo, zona entera afectada**: confirmar con cifra que el
   estadístico no lo ve. Hoy eso está sostenido por un caso construido a
   mano, sin corrida trazable ni entrada en ningún `medicion.json`.

---

## 2. Las dos predicciones, antes de medir

Se declaran completas porque el experimento existe para distinguirlas.

### A — contraste de dos muestras

Sale del álgebra de `detector/scan.py`. Con grupo `G` de tamaño `m` corrido
`Δ = k·σ` en una zona de `n`, y candidato que coincide con el grupo:

```
z = (Δ/σ_eff)·√(m(n−m)/n) = k·√N·√(m(n−m)/n)
```

**Predictor: `√(m(n−m)/n)`.** Crece hasta `m = n/2` y decae después,
simétrico. En `m = 1` vale 0,98 y en `m = 12` vale 2,50 (con `n = 25`).

### B — perímetro

Sale de `experiments/firma-espectral/RESULTADOS.md` §2, donde el cociente de
Rayleigh correlaciona **`r = 0,9534`** con las aristas de corte por nodo
sobre 600 eventos. De la tabla de esa sección, Rayleigh dividido `corte/nodo`
da 0,203 / 0,187 / 0,210 / 0,211 en `depth` 0–3: es proporcionalidad, y por
eso `r` sale tan alto.

**Predictor: `corte/nodo`.** Decrece monótonamente con `m`. En `m = 1` vale
4,92 y en `m = 12` vale 0,81.

**Lo que B *no* trae puesto.** El `r = 0,9534` relaciona el perímetro con el
cociente de Rayleigh, que es una propiedad de la señal en el espectro y **no
aparece en el estadístico del escaneo**. Que la detección del escaneo siga
esa misma ley es exactamente lo que acá se pone a prueba, no algo que se
herede de aquella medición. Si la sigue, es confirmación independiente del
mecanismo por una ruta distinta.

### Dónde se contradicen

| | `m` = 1 | Tendencia en `m` chico | Máximo | `m` = n |
|---|---|---|---|---|
| **A** | el **peor** caso | sube | `m = n/2` | 0 |
| **B** | el **mejor** caso | baja | `m = 1` | 0 |

Se oponen frontalmente en `m` pequeño y coinciden sólo en el extremo. Por eso
el barrido es denso abajo.

**Forma esperada de las curvas bajo A:** el escaneo dibuja una U invertida y
el umbral por medidor crece monótono con `m` —más medidores afectados, más
oportunidades de que alguno cruce—, así que habría **dos cruces**, uno en `m`
chico y otro en `m` grande. Bajo B habría **uno solo**. El número de cruces
es parte del veredicto y se declara acá para que no se interprete después.

---

## 3. Criterios

### C1 — Calibración
Falso positivo objetivo **1 % por señal**, calibrado por zona sobre señal
limpia. No por ventana: `detector-colectivo` §7 dejó anotado que calibrar por
ventana infla las tasas.

### C2 — Punto de operación
**N = 16, radios {1, 2}, σ = 0,5, ventana deslizante con el evento en
posición sorteada.** Idéntico a `detector-deslizante`, para que el punto
`m ≈ 12` sea comparable contra el 79,4 % ya publicado. Ninguna cifra de este
experimento se compara contra una medida en otra condición.

### C3 — Eje
`m ∈ {1, 2, 3, 4, 5, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24}`, recortado al `n`
de cada zona, **más siempre `m = n`**. Denso abajo por §2. Se reporta contra
`m` y contra `m/n`, porque las zonas tienen `n` distinto (25, 25, 25, 25, 30,
20).

### C4 — Comparador
Umbral por medidor calibrado al mismo falso positivo, medido **en cada `m`**.
No se reutiliza ninguna cifra de umbral de otro experimento.

### C5 — Límite de aplicabilidad
El `m` donde la curva del escaneo cruza por debajo de la del umbral. Se
reportan **todos** los cruces, no el primero. Si no hay ninguno, se dice.

### C6 — Discriminación entre A y B
Correlación de **Spearman** entre cada predictor y la tasa de detección,
sobre todos los puntos `(zona, m)`. Gana el de mayor |ρ|.

**Si la diferencia entre los dos |ρ| es menor que 0,05, el resultado se
declara no concluyente** y así se escribe en `RESULTADOS.md`.

Spearman y no R²: la detección es una función saturante del score, así que
sólo la monotonía es interpretable y ajustar una recta mediría el link, no la
hipótesis.

### C7 — Saturación
Si más del **60 %** de los puntos del barrido caen en 0 % o en 100 %, la
comparación no tiene resolución y no es un resultado (`ESTADO.md` §5.4).

En ese caso se baja σ y **se vuelve a declarar acá antes de mirar nada más**,
dejando registrado el σ original y el motivo del cambio. Que se vea que fue
por falta de resolución y no por buscar un resultado.

> **Registro de cambios de σ.** Ninguno hasta ahora. σ original: **0,5**.

### C8 — El extremo
En `m = n` se espera detección igual al falso positivo objetivo, **1 %**, con
intervalo binomial. Es la cifra que reemplaza al caso construido a mano.

Es la predicción más fuerte del experimento porque es analítica y no
empírica: en `m = n` el corrimiento es una constante sumada a toda la zona,
las dos medias del contraste se corren igual y la diferencia no cambia;
además `candidate_balls` descarta por construcción las bolas que cubren la
zona entera. **Si esta cifra no da 1 %, hay un error en el aparato**, no un
hallazgo.

### C9 — Ensayos
**300 por `(zona, m)`**, igual que `detector-colectivo`. Semilla derivada de
`20260808`.

Si la corrida completa no cierra en tiempo razonable se baja a 200 y **se
declara acá antes de correr**, no después.

### C10 — Contraste de forma
A igual `m`, compacto contra extendido, en **`m ∈ {5, 6, 8}`**.

**Predicción:**

* **Bajo A las dos curvas se superponen**, porque el predictor
  `√(m(n−m)/n)` sólo depende de `m` y las dos formas comparten `m`.
* **Bajo B se separan, y la extendida detecta mejor**, por tener más
  perímetro al mismo tamaño.

Es la única manipulación que desacopla tamaño de perímetro. Sin ella
cualquier conclusión del barrido admite la objeción de que las dos variables
nunca se separaron, y ésa es una objeción que aparece en la defensa.

**Por qué en `m ∈ {5, 6, 8}` y no más abajo.** A y B más se separan en `m`
pequeño, pero ahí la manipulación de forma **no tiene poder**: en `m = 1` el
grupo es un nodo y en `m = 2` una arista, donde compacto y extendido son el
mismo objeto por definición. Medido sobre los 150, aristas de corte medias:

| `m` | compacto | extendido | separación |
|---|---|---|---|
| 2 | 7,99 | 8,11 | +0,12 |
| 3 | 10,34 | 10,13 | −0,21 |
| 4 | 10,98 | 11,59 | +0,61 |
| **5** | 10,45 | 12,03 | **+1,58** |
| **6** | 10,88 | 13,07 | **+2,19** |
| **8** | 12,18 | 14,95 | **+2,77** |

Con error estándar ≈ 0,26, hasta `m = 4` la separación está dentro o al borde
del ruido. `{5, 6, 8}` son los `m` más chicos donde la manipulación separa de
verdad, y siguen estando en el tramo donde A sube y B baja.

---

## 4. Qué se registra

`results/medicion.json` versionado, con una fila por `(zona, m, forma)` y los
campos crudos: `n_nodes`, `boundary_edges`, `zone_size`, `coverage`,
`boundary_per_node`, tasa de escaneo, tasa de umbral, y los dos predictores
evaluados. Los agregados se recalculan desde ahí, para poder volver a
verificar sin rehacer la medición.

`RESULTADOS.md` lleva encabezado de configuración, por `ESTADO.md` §5.3:
ninguna cifra sale de este experimento sin su configuración al lado.

---

## 5. Qué no va a cubrir

Se declara ahora para que no se lea como omisión:

* **Una sola magnitud**, `voltaje_v`. Corriente y potencia tienen σ/media del
  35 % y siguen sin evaluar.
* **Ruido gaussiano independiente entre medidores.** Correlación espacial
  real cambiaría el fondo para los dos métodos.
* **Una sola σ**, salvo que C7 obligue a cambiarla.
* **Sin costo computacional.** Sigue pendiente y es de otro experimento.
* **Grupos dentro de una zona.** Un grupo a caballo de dos zonas necesita
  operar sobre `AmiGraph` y hoy el inyector no lo hace.
