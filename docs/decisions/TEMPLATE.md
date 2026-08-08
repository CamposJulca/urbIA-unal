# ADR-NNN — Título en una línea

| | |
|---|---|
| Estado | Propuesto \| Aceptado \| Reemplazado por ADR-NNN \| Obsoleto |
| Fecha | AAAA-MM-DD |
| Autor | |
| Ámbito | Qué parte del sistema queda comprometida por esta decisión |
| Código afectado | Rutas de los módulos que la implementan |
| Cifras medidas sobre | Archivo de datos y script que las reproduce, si la decisión tiene respaldo empírico |

---

## 1. Contexto

Qué problema hay que resolver y por qué hace falta decidir. Qué restricciones
vienen dadas y no se negocian: los datos disponibles, el hardware, los plazos,
el trabajo previo que se continúa.

Si la decisión responde a varias preguntas independientes, enumerarlas acá.
Cada una debería tener su decisión en §2 y su justificación en §3.

---

## 2. Decisión

Enunciado corto y numerado, sin argumentación. Una persona que sólo lea esta
sección debe quedar en condiciones de implementar lo decidido.

1. …
2. …

---

## 3. Justificación

Una subsección por decisión de §2, con el mismo número.

**Regla del proyecto:** ninguna afirmación empírica sin medición contra los
datos reales (CLAUDE.md §8.2). Cada cifra que aparezca acá lleva puntero al
test de regresión, al experimento o al script que la reproduce. Una decisión
tomada por criterio y no por medición se declara como tal — es legítima, pero
no se disfraza de resultado.

---

## 4. Consecuencias

Qué habilita la decisión, qué cierra, y qué queda como limitación declarada.
Incluir lo que se vuelve difícil, no sólo lo que se vuelve posible.

---

## 5. Alternativas descartadas

Una por bloque, con el motivo del descarte y su medición si la hubo. Sirve
para no volver a discutirlas y para que el descarte sea auditable.

---

## 6. Ruta de revisión

Bajo qué evidencia futura habría que reabrir esta decisión, y qué habría que
medir para cerrarla de otro modo.

---

## 7. Trazabilidad

Tabla que mapea cada afirmación de este ADR al archivo que la sostiene.
