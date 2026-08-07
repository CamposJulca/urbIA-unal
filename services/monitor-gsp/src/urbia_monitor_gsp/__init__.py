"""Monitor espectral GSP de UrbIA-UNAL.

Este paquete se organiza en dos capas con la dependencia apuntando siempre
hacia adentro:

* `urbia_monitor_gsp.graph` — núcleo puro. Recibe medidores con coordenadas
  y devuelve el grafo con su Laplaciano y descomposición espectral. Sólo
  depende de numpy: no importa drivers de base de datos ni configuración,
  de modo que puede usarse desde un notebook sin levantar el servicio.
* `urbia_monitor_gsp.io` — adaptadores de entrada/salida. Único punto que
  habla con PostgreSQL. Requiere el extra `[db]`.
"""

__version__ = "0.1.0"
