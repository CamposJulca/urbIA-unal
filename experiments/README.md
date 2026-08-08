# Experimentos

Mediciones reproducibles cuyos resultados sostienen afirmaciones de la
tesis o cifras de los docstrings del código.

Cada experimento vive en su propio directorio con:

* `run.py` — el script que produce las cifras, ejecutable de punta a
  punta sin intervención manual.
* `RESULTADOS.md` — el informe, escrito para leerse sin el código al
  lado: qué se midió, sobre qué, con qué parámetros y qué salió.
* `results/` — salidas crudas (JSON, figuras). **No se versiona**; se
  regenera corriendo el script.

| Experimento | Qué mide | Código medido |
|---|---|---|
| [`difuminador-tau/`](difuminador-tau/RESULTADOS.md) | Signo del exponente del filtro paso-bajo, barrido de τ, límites e invariancia a la degeneración espectral | `services/monitor-gsp/.../graph/filter.py` |

## Reglas

* **Semillas fijas.** Ningún experimento depende de aleatoriedad no
  sembrada ni de la hora de ejecución.
* **Sustrato versionado.** Los datos de entrada salen del repositorio
  —`data/topologies/`— y no de una consulta a la base, para que otra
  persona pueda reproducir el resultado sin acceso al cluster.
* **Toda cifra que llegue a un docstring o a la tesis se mide acá
  primero**, y el documento dice contra qué archivo y con qué parámetros
  se midió.
