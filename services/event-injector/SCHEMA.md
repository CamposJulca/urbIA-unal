# SCHEMA — Verdad de referencia del inyector

Contrato de lo que el inyector escribe a disco. Es tan parte del entregable
como la señal modificada: **sin la verdad no hay forma de contar aciertos ni
errores**, y sin un formato estable el puntaje del detector deja de ser
comparable entre corridas.

Versión: `ground-truth-v1`.

---

## Artefactos por corrida

`urbia-inject --spec <spec.json> --salida <dir>` escribe, por cada zona:

| Archivo | Contenido |
|---|---|
| `base_<zona>.npy` | Señal de fondo, `(T, n)` float64, **sin** eventos |
| `senal_<zona>.npy` | Señal con los eventos aplicados, misma forma |
| `verdad_<zona>.json` | La verdad de referencia |
| `resumen.json` | Semilla, versión del perfil y conteo por zona |

Conservar la señal de fondo no es redundante: es lo que permite medir el
efecto de un evento contra el mismo ruido, sin que la comparación mezcle
dos realizaciones distintas.

---

## `verdad_<zona>.json`

```json
{
  "zona": "centro",
  "seed": 20260808,
  "n_instants": 50,
  "device_ids": ["urbia-cen-mon-0001", "..."],
  "events": [ { "...": "ver abajo" } ]
}
```

| Campo | Tipo | Significado |
|---|---|---|
| `zona` | string | Zona del subgrafo |
| `seed` | int | Semilla base de la corrida |
| `n_instants` | int | Instantes de la señal |
| `device_ids` | string[] | **Orden canónico del grafo.** Indexa las columnas de los `.npy` y los `node_indices` |
| `events` | object[] | Eventos aplicados, en orden de aplicación |

### Un evento

| Campo | Tipo | Significado |
|---|---|---|
| `event_id` | string | Único dentro de la corrida: `<familia>-<zona>-<NNN>` |
| `family` | string | Familia. Hoy sólo `desviacion_colectiva` |
| `zona` | string | Zona afectada |
| `magnitude` | string | `voltaje_v`, `corriente_a` o `potencia_kw` |
| `seed_device_id` | string | Nodo semilla del vecindario |
| `device_ids` | string[] | Nodos afectados |
| `node_indices` | int[] | Posiciones de esos nodos en el orden canónico |
| `start` | int | Primer instante afectado |
| `duration` | int | Instantes consecutivos afectados |
| `depth` | int | Profundidad del vecindario en saltos |
| `sigma_multiple` | float\|null | Magnitud **efectiva** en múltiplos de σ espacial |
| `fraction` | float\|null | Magnitud **efectiva** como fracción del valor |
| `delta` | float[][] | Desviación aplicada, `(duration, len(device_ids))` |
| `max_abs_delta` | float | Mayor desviación en valor absoluto |
| `scaled` | bool | Si hubo que reducirla para respetar el esquema |
| `expected_detectable` | bool | Si el evento **debe** ser detectado |

### Invariantes

1. **`delta` reconstruye el original.** Restar `delta` a `senal` en las
   filas `[start, start+duration)` y las columnas `node_indices` devuelve
   `base` exactamente. Es lo que hace verificable la verdad en vez de
   confiable.
2. **`sigma_multiple` y `fraction` son mutuamente excluyentes**: uno de los
   dos es `null`, nunca los dos ni ninguno.
3. **Son la magnitud efectiva, no la pedida.** Si `scaled` es `true`, el
   valor registrado es el que se aplicó tras reducirlo, no el que declaraba
   la especificación.
4. **`node_indices` y `device_ids` están alineados** entre sí y con el
   orden canónico de la corrida.
5. **Los eventos se acumulan.** Si dos afectan al mismo nodo en el mismo
   instante, la señal lleva la suma y cada evento queda registrado por
   separado con su propio `delta`.

### `expected_detectable`

Existe porque no todos los eventos deben dispararse. Un corrimiento de la
zona entera es un **modo común**: no hay discordancia con la vecindad, y un
detector de grafo que lo marque está produciendo un falso positivo. Esos
casos entran a la verdad con `expected_detectable: false` y cuentan al
revés al puntuar.

Hoy la única familia implementada lo trae siempre en `true`; el campo está
en el contrato desde el principio para que agregar la familia de control no
rompa los archivos ya generados.

---

## `spec.json` de entrada

```json
{
  "topologia": "data/topologies/manizales_150.json",
  "esquema":   "data/schemas/payload_schema_v1.json",
  "perfil":    "data/profiles/manizales_signal_v1.json",
  "seed": 20260808,
  "n_instantes": 50,
  "zonas": ["centro", "la_enea"],
  "on_violation": "raise",
  "eventos": [
    {"magnitude": "voltaje_v", "depth": 1, "sigma_multiple": 1.0, "start": 10, "duration": 5}
  ]
}
```

Las tres rutas se resuelven contra la raíz del repositorio. Declararlas en
la especificación y no dentro del código es lo que permite responder, un año
después, contra qué contrato y qué perfil se produjo un resultado.

`zonas` omitido significa todas. `on_violation` es `"raise"` por defecto:
una magnitud que no cabe en el rango del esquema es un error de la
especificación, no algo que se recorta en silencio.
