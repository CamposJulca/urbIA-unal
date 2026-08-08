# Esquemas de datos externos

Copias versionadas de los contratos de datos que **no se definen en este
repositorio** pero de los que dependen los resultados de la tesis.

Están acá por la misma razón que las topologías de `data/topologies/`: el
productor vive fuera del monorepo, puede cambiar y puede desaparecer, y un
resultado que dice "ningún medidor salió del rango del esquema" no significa
nada si el esquema no está versionado junto al resultado.

---

## `payload_schema_v1.json`

Contrato formal de la telemetría AMI que consume UrbIA. Es un JSON Schema
draft-07. El simulador lo valida con su `PayloadValidator` **antes** de
publicar, así que un valor fuera de estos límites no llega al broker: no es
que sea improbable, es que no existe.

### Procedencia

| | |
|---|---|
| Origen | `urbia-platform`, repositorio hermano (`github.com/CamposJulca/urbia-platform`) |
| Ruta en el origen | `capa1/comun/payload_schema_v1.json` |
| Máquina | `.102` (`innova-pruebas`), `/home/pruebas/urbia-platform` |
| Commit que lo introdujo | `9be65d20` — *feat(capa1-python): Sprint 3 — simulador Python funcional, 50 medidores mono conectados a MQTT .101* (2026-04-20) |
| Copiado el | 2026-08-08 |
| md5 | `edceaecd92c1f04f134f4ce8c974bd69` |
| Tamaño | 2 113 bytes |

El árbol de origen estaba limpio para este archivo al copiarlo (sin cambios
sin commitear), así que la copia corresponde exactamente al commit citado.

**Reverificar:**

```bash
md5sum data/schemas/payload_schema_v1.json
md5sum /home/pruebas/urbia-platform/capa1/comun/payload_schema_v1.json
```

Si difieren, el productor cambió su contrato y hay que revisar qué
resultados dependían del anterior.

### Límites duros de las magnitudes

Son el rango admisible, no el rango observado. Dónde vive la señal en la
práctica es otra cosa, y se mide aparte contra `ami_telemetry`.

| Magnitud | Mínimo | Máximo |
|---|---|---|
| `voltaje_v` | 187,0 | 253,0 |
| `corriente_a` | 0,0 | 60,0 |
| `potencia_kw` | 0,0 | 30,0 |
| `frecuencia_hz` | 57,0 | 63,0 |
| `factor_potencia` | 0,0 | 1,0 |
| `lat` | 5,03 | 5,12 |
| `lon` | −75,55 | −75,44 |

Enums: `device_type` ∈ {`mono`, `trifasico`}; `zona` con las seis de
Manizales; `estado` con los siete valores que documenta
`services/backend/SCHEMA.md` §1.1; `nodo_origen` ∈ {`192.168.0.103`,
`192.168.0.104`, `192.168.0.105`}; `lenguaje` ∈ {`python`, `cpp`, `java`}.

### Divergencias detectadas al copiarlo

Tres, ninguna bloqueante, todas anotadas para que no sorprendan después:

1. **`energia_kwh` no está en el esquema**, y el esquema declara
   `additionalProperties: false`. `services/backend/SCHEMA.md` sí lo lista
   como campo de entrada (nullable, "el productor no siempre reporta
   acumulado"). Un payload que lo incluyera sería rechazado por el
   `PayloadValidator` del productor. O el productor no lo envía, o valida
   contra otra versión del contrato.

2. **`nodo_origen` no incluye la máquina que hoy publica.** El enum admite
   `.103`, `.104` y `.105`; el contenedor en ejecución es `urbia-sim-105`,
   así que hoy emite `192.168.0.105`. `services/backend/SCHEMA.md` todavía
   dice "valor observado: `192.168.0.103`". Es documentación desactualizada
   del backend, no una violación del contrato.

3. **El trifásico ya se está generando.** `services/backend/SCHEMA.md` dice
   "El trifásico no se ha capturado todavía", pero el último commit del
   productor es *feat(capa1-python): instancia .105 (mono+trifásico)*
   (2026-08-06). Importa porque monofásico y trifásico tienen
   distribuciones distintas —residencial contra comercial— y cualquier
   medición de "qué desviación es sutil" tiene que separarlos.
