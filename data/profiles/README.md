# Perfiles de señal

Instantáneas versionadas de **cómo se comporta la señal AMI en operación
normal**. Junto con `data/schemas/`, son lo que le da significado a la
magnitud de un evento inyectado.

La distinción entre los dos directorios es deliberada y no es una
formalidad:

* **`data/schemas/`** es el **límite duro**. Fuera de ese rango el mensaje
  no existe: el productor lo rechaza antes de publicarlo.
* **`data/profiles/`** es **dónde vive la señal en la práctica**. Es lo que
  decide qué desviación es sutil. Un 5 % es 2,5σ en voltaje —evidente para
  cualquier umbral— y 0,14σ en corriente —invisible—. Sin el perfil, la
  magnitud de un evento no significa nada.

---

## `manizales_signal_v1.json`

### Qué mide

La cantidad central es la **dispersión espacial**: cuánto difieren los
medidores entre sí en un mismo instante. Es la que ve un detector definido
sobre el grafo, porque es la que produce discordancia entre vecinos.

    σ_espacial² = E_t[ Var_medidores( x(t) ) ]

Se estima como la **raíz de la media de las varianzas por instante**, no
como la media de las desviaciones: esta última subestima por desigualdad de
Jensen, y en corriente la diferencia es de 31 % a 35 %.

No es lo mismo que la dispersión temporal, que incluye la curva de carga
diaria. Esa curva la comparten todos los medidores, así que **no** produce
desacuerdo entre vecinos y no debe contarse. La diferencia es grande: en
corriente la dispersión agrupada es ~60 % y la espacial ~35 %.

### Procedencia

| | |
|---|---|
| Fuente | `ami_telemetry` en el contenedor `urbia-postgres` de `.102` |
| Ventana | 2026-08-07 14:28:28 UTC a 2026-08-08 14:28:28 UTC (24 h) |
| Filtro | `estado = 'activo'` |
| Instantes | ~4 200 por `device_type`, con ≥ 10 medidores cada uno |
| Script | `experiments/perfil-senal/run.py` |
| Medido el | 2026-08-08 |
| md5 | `06796d337df24896d7ef3fe1fffe5c9c` |

**Reproducir:**

```bash
POSTGRES_PASSWORD=$(docker inspect urbia-postgres \
  --format '{{range .Config.Env}}{{println .}}{{end}}' \
  | sed -n 's/^POSTGRES_PASSWORD=//p') \
services/monitor-gsp/.venv/bin/python experiments/perfil-senal/run.py
```

Los estados `anomalia_voltaje` y `falla` se excluyen a propósito: son las
anomalías que el simulador ya produce, y el perfil describe el fondo contra
el cual un evento nuevo tiene que resultar sutil, no mezclarse con ellas.

### Lo medido

| Magnitud | Tipo | Media | σ espacial | σ/media | σ agrupada |
|---|---|---|---|---|---|
| `voltaje_v` | mono | 220,0116 | 4,4012 | **2,00 %** | 4,4000 |
| `voltaje_v` | trifásico | 220,0012 | 4,3980 | **2,00 %** | 4,3964 |
| `corriente_a` | mono | 7,1466 | 2,4732 | **34,61 %** | 4,2748 |
| `corriente_a` | trifásico | 21,4532 | 7,4731 | **34,83 %** | 12,8290 |
| `potencia_kw` | mono | 1,4623 | 0,5099 | **34,87 %** | 0,8769 |
| `potencia_kw` | trifásico | 7,1531 | 2,5314 | **35,39 %** | 4,3004 |

### Tres consecuencias para el inyector

1. **La desviación se especifica en múltiplos de σ espacial, no en
   porcentaje.** El mismo 5 % es 2,5σ en voltaje y 0,14σ en corriente: el
   porcentaje crudo no es comparable entre magnitudes ni entre tipos de
   medidor.

2. **El voltaje es la magnitud adecuada para una desviación colectiva
   sutil.** Con σ/μ del 2 %, una desviación de 1σ es indistinguible del
   ruido para un umbral por medidor y perfectamente coherente entre los
   nodos del grupo. En corriente y potencia, σ/μ ronda el 35 %: para
   esconderse en el ruido haría falta un cambio absoluto enorme.

3. **En voltaje no hay curva diaria.** σ espacial (4,40) y σ agrupada
   (4,40) coinciden, así que toda su variación es ruido por medidor. En
   corriente y potencia, cerca de dos tercios de la varianza temporal es
   la curva de carga compartida.

### Advertencias

* **`device_type` y `zona` están perfectamente confundidos.** centro,
  chipre y palogrande son enteramente `mono` (80 medidores); la_enea,
  palermo y universitario enteramente `trifasico` (70). Ninguna diferencia
  observada puede atribuirse a una de las dos variables sin confundirla
  con la otra. Vale para cualquier resultado del detector, no sólo para
  este perfil.
* **El voltaje no distingue tipo de medidor**: media 220,00 y σ 4,40 en
  ambos, idéntico hasta el segundo decimal. Lo que separa residencial de
  comercial es corriente y potencia, por un factor 3.
* **El estado `falla` no tiene firma eléctrica.** Su voltaje medio es
  220,01 contra 220,00 de `activo`. Es una etiqueta sin correlato en las
  magnitudes: el ~1 % de filas en `falla` no es detectable por ningún
  método que mire voltaje, corriente o potencia.
* **La ventana es de 24 h sobre tres días de datos acumulados.** No cubre
  variación estacional ni de día de semana. Si la serie crece, conviene
  rehacer el perfil sobre una ventana más larga y comparar.
* **En corriente y potencia, σ espacial depende de la hora del día.** Medido
  sobre las últimas 6 h contra las últimas 24 h: la media de `corriente_a`
  trifásica pasa de 21,57 A a 27,44 A (+27 %) y su σ espacial de 7,47 a 8,65
  (+16 %). No es deriva, es la curva de carga: la dispersión escala con el
  nivel. El cociente σ/media es bastante más estable (34,6 % contra 31,5 %).

  Dos consecuencias. Primera, **cualquier recontraste del perfil tiene que
  usar una ventana de 24 h**, o comparará la hora del día con el promedio
  diario; el test de integración del inyector lo hace así por esto.
  Segunda, una desviación expresada en múltiplos de σ sobre corriente o
  potencia queda definida respecto del **promedio de la ventana**, no
  respecto de la dispersión del instante en que se inyecta. En voltaje el
  problema no existe, porque no tiene curva diaria: σ espacial y σ agrupada
  coinciden.
