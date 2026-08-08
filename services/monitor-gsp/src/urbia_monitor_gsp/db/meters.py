"""Lectura de `ami_meters` y construcción del grafo desde la base.

Cierra el ciclo dato → grafo: `load_meters` devuelve `MeterNode` y
`load_ami_graph` devuelve directamente el `AmiGraph`. Entre medio no hay
nada más que el constructor de `graph.builder`.

**Sincrónico a propósito.** El backend usa async porque sirve peticiones
HTTP concurrentes; acá no hay concurrencia que ganar: se lee un padrón de
150 filas una vez, al arrancar el monitor o al abrir un notebook. Un
`async def` obligaría a todo consumidor —incluida una celda de Jupyter— a
tener un bucle de eventos para leer una tabla.

**Qué se lee y qué no.** Sólo `device_id`, `zona`, `lat` y `lon`: lo que
un nodo del grafo necesita. `device_type`, `nodo_origen` e
`instalado_en` no entran porque el grafo no los usa, y traerlos invitaría
a que alguien construyera aristas con ellos. `nodo_origen` en particular
registra por qué nodo del cluster llegó el mensaje MQTT: es procedencia de
red, no conectividad eléctrica.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any, Final

import psycopg

from ..graph.builder import build_ami_graph
from ..graph.types import AmiGraph, GraphConfig, MeterNode, MonitorGspError
from .config import DatabaseSettings, get_settings

logger: Final = logging.getLogger(__name__)

_QUERY: Final = """
    SELECT device_id, zona, lat, lon
    FROM ami_meters
    WHERE (NOT %(solo_activos)s OR COALESCE(activo, TRUE))
      AND (%(zonas)s::text[] IS NULL OR zona = ANY(%(zonas)s::text[]))
    ORDER BY device_id
"""
"""Consulta única y estática: los filtros viajan como parámetros.

Escrita así, y no componiendo el `WHERE` con f-strings, para que no haya
superficie de inyección aunque `zonas` venga de la línea de comandos.
`COALESCE(activo, TRUE)` respeta el `DEFAULT true` de la columna: una fila
con `activo` nulo se considera activa.
"""


class IncompleteMeterError(MonitorGspError, ValueError):
    """Hay medidores sin los datos mínimos para ser nodos del grafo.

    Un medidor sin coordenadas o sin zona no se puede ubicar en ningún
    subgrafo. Descartarlo en silencio cambiaría la topología —y con ella
    el espectro— sin que nadie se entere.
    """

    def __init__(self, device_ids: tuple[str, ...]) -> None:
        """Inicializa el error con los medidores incompletos.

        Args:
            device_ids: Identificadores de las filas incompletas.
        """
        self.device_ids = device_ids
        muestra = ", ".join(device_ids[:5])
        resto = f" y {len(device_ids) - 5} más" if len(device_ids) > 5 else ""
        super().__init__(
            f"{len(device_ids)} medidor(es) sin zona o sin coordenadas ({muestra}{resto}): "
            f"no se pueden ubicar en el grafo. Corregí los datos, acotá la consulta con "
            f"zonas=, o pasá skip_incomplete=True para descartarlos con un aviso en el log"
        )


class NoMetersFoundError(MonitorGspError, ValueError):
    """La consulta no devolvió ningún medidor."""


def _to_meter_nodes(
    rows: Sequence[tuple[Any, ...]],
    skip_incomplete: bool,
) -> list[MeterNode]:
    """Convierte filas de `ami_meters` en nodos del grafo.

    Args:
        rows: Filas `(device_id, zona, lat, lon)`.
        skip_incomplete: Si es `True`, descarta las filas sin zona o sin
            coordenadas dejando un aviso en el log. Si es `False`,
            levanta `IncompleteMeterError`.

    Returns:
        Los medidores, en el mismo orden en que llegaron las filas.

    Raises:
        IncompleteMeterError: Si hay filas incompletas y no se pidió
            descartarlas.
    """
    completos: list[MeterNode] = []
    incompletos: list[str] = []

    for device_id, zona, lat, lon in rows:
        if zona is None or lat is None or lon is None:
            incompletos.append(str(device_id))
            continue
        completos.append(
            MeterNode(device_id=str(device_id), zona=str(zona), lat=float(lat), lon=float(lon))
        )

    if incompletos:
        if not skip_incomplete:
            raise IncompleteMeterError(tuple(incompletos))
        logger.warning(
            "descartados %d medidor(es) sin zona o sin coordenadas: %s",
            len(incompletos),
            ", ".join(incompletos[:10]),
        )

    return completos


def _fetch_rows(
    settings: DatabaseSettings,
    zonas: Sequence[str] | None,
    solo_activos: bool,
) -> list[tuple[Any, ...]]:
    """Ejecuta la consulta contra PostgreSQL.

    Args:
        settings: Parámetros de conexión.
        zonas: Zonas a incluir, o `None` para todas.
        solo_activos: Si se filtran los medidores dados de baja.

    Returns:
        Las filas crudas, ordenadas por `device_id`.
    """
    parametros = {
        "solo_activos": solo_activos,
        "zonas": list(zonas) if zonas is not None else None,
    }
    logger.debug("leyendo ami_meters de %s", settings.safe_summary)
    with psycopg.connect(settings.conninfo) as conexion, conexion.cursor() as cursor:
        cursor.execute(_QUERY, parametros)
        return cursor.fetchall()


def load_meters(
    settings: DatabaseSettings | None = None,
    *,
    zonas: Sequence[str] | None = None,
    solo_activos: bool = True,
    skip_incomplete: bool = False,
) -> list[MeterNode]:
    """Lee el padrón de medidores desde `ami_meters`.

    Args:
        settings: Parámetros de conexión. Si es `None` se leen del
            entorno.
        zonas: Zonas a incluir. `None` trae todas. Acotar acá es
            preferible a filtrar después: el subgrafo de una zona no
            depende de las demás, así que un nodo de borde puede pedir
            sólo la suya.
        solo_activos: Si se excluyen los medidores dados de baja.
        skip_incomplete: Si se descartan —con aviso en el log— las filas
            sin zona o sin coordenadas, en vez de levantar error.

    Returns:
        Los medidores ordenados por `device_id`.

    Raises:
        NoMetersFoundError: Si la consulta no devuelve ninguna fila.
        IncompleteMeterError: Si hay filas incompletas y no se pidió
            descartarlas.
    """
    settings = settings or get_settings()
    rows = _fetch_rows(settings, zonas, solo_activos)

    if not rows:
        raise NoMetersFoundError(
            f"ninguna fila en ami_meters para zonas={zonas} y solo_activos={solo_activos} "
            f"en {settings.safe_summary}: revisá que el simulador haya publicado y que "
            f"el backend esté ingiriendo"
        )

    meters = _to_meter_nodes(rows, skip_incomplete)
    if not meters:
        raise NoMetersFoundError(
            f"las {len(rows)} filas leídas de ami_meters estaban todas incompletas: "
            f"ninguna tiene zona y coordenadas"
        )

    logger.info(
        "leídos %d medidores de %s en %d zona(s)",
        len(meters),
        settings.safe_summary,
        len({m.zona for m in meters}),
    )
    return meters


def load_ami_graph(
    config: GraphConfig | None = None,
    settings: DatabaseSettings | None = None,
    *,
    zonas: Sequence[str] | None = None,
    solo_activos: bool = True,
    skip_incomplete: bool = False,
) -> AmiGraph:
    """Lee los medidores y construye el grafo AMI de una sola vez.

    Atajo para el caso habitual. Quien necesite inspeccionar o filtrar el
    padrón antes de construir puede encadenar `load_meters` con
    `graph.build_ami_graph`.

    Args:
        config: Configuración de construcción. Si es `None` se usan los
            valores por defecto de `GraphConfig`.
        settings: Parámetros de conexión. Si es `None` se leen del
            entorno.
        zonas: Zonas a incluir. `None` trae todas.
        solo_activos: Si se excluyen los medidores dados de baja.
        skip_incomplete: Si se descartan las filas incompletas.

    Returns:
        El grafo AMI, con un subgrafo por zona.

    Raises:
        NoMetersFoundError: Si la consulta no devuelve medidores usables.
        IncompleteMeterError: Si hay filas incompletas y no se pidió
            descartarlas.
    """
    meters = load_meters(
        settings,
        zonas=zonas,
        solo_activos=solo_activos,
        skip_incomplete=skip_incomplete,
    )
    return build_ami_graph(meters, config)
