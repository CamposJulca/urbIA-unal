#!/usr/bin/env python3
"""De llegadas asíncronas a ventanas densas: barrido del ancho de bin.

El detector consume una matriz `(T, n)` densa y la telemetría real no llega
así: cada medidor publica por su cuenta y no hay rejilla temporal
compartida. Este barrido mide, para cada ancho de bin candidato, qué
fracción de las ventanas de 16 bins queda completa — que es lo que decide,
porque un bin incompleto no se imputa ni se detecta.

Los criterios están en `CRITERIOS.md`, commiteados antes de esta corrida.
Acá no se declara ninguno: este archivo los aplica.

Uso:

    POSTGRES_PASSWORD=$(docker inspect urbia-postgres \\
      --format '{{range .Config.Env}}{{println .}}{{end}}' \\
      | sed -n 's/^POSTGRES_PASSWORD=//p') \\
      POSTGRES_HOST=localhost \\
      python experiments/ventana-viva/run.py --json results/medicion.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Final

import numpy as np
import numpy.typing as npt
import psycopg
from psycopg.rows import dict_row

_REPO: Final = Path(__file__).resolve().parents[2]

# C1 — horizonte, el mismo que usó `perfil-senal` para congelar σ.
VENTANA_HORAS: Final = 24

# C2 — anchos barridos, en segundos.
ANCHOS: Final = (4, 5, 6, 7, 8, 10, 12, 15, 20)

# Ventana del detector, en bins. Punto de operación declarado en
# `detector/types.py`; acá entra sólo como largo de la racha que se exige
# completa, no como parámetro a elegir.
VENTANA_BINS: Final = 16

# C6 — umbral de completitud por ventana.
COMPLETITUD_OBJETIVO: Final = 0.95


def _conexion() -> psycopg.Connection[Any]:
    """Abre la conexión a PostgreSQL desde variables de entorno.

    Returns:
        Conexión abierta, con filas como diccionarios.

    Raises:
        RuntimeError: Si falta `POSTGRES_PASSWORD`.
    """
    password = os.environ.get("POSTGRES_PASSWORD")
    if not password:
        raise RuntimeError(
            "falta POSTGRES_PASSWORD. En neusi-stage se puede tomar del contenedor "
            "sin escribirla: POSTGRES_PASSWORD=$(docker inspect urbia-postgres "
            "--format '{{range .Config.Env}}{{println .}}{{end}}' "
            "| sed -n 's/^POSTGRES_PASSWORD=//p')"
        )
    return psycopg.connect(
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=int(os.environ.get("POSTGRES_PORT", "5432")),
        dbname=os.environ.get("POSTGRES_DB", "urbia"),
        user=os.environ.get("POSTGRES_USER", "urbia"),
        password=password,
        connect_timeout=int(os.environ.get("CONNECT_TIMEOUT_S", "10")),
        row_factory=dict_row,
    )


CONSULTA_VENTANA: Final = """
SELECT max(timestamp_utc)                                        AS fin,
       max(timestamp_utc) - make_interval(hours => %(horas)s)     AS inicio
FROM ami_telemetry
"""

CONSULTA_PADRON: Final = """
SELECT zona, count(*) AS medidores
FROM ami_meters
WHERE COALESCE(activo, TRUE) AND zona IS NOT NULL
GROUP BY zona
ORDER BY zona
"""

CONSULTA_VISTOS: Final = """
SELECT zona, count(DISTINCT device_id) AS vistos
FROM ami_telemetry
WHERE timestamp_utc >= %(inicio)s AND timestamp_utc < %(fin)s
GROUP BY zona
ORDER BY zona
"""

CONSULTA_RETARDO: Final = """
SELECT percentile_cont(0.50) WITHIN GROUP (
           ORDER BY EXTRACT(epoch FROM recibido_en - timestamp_utc))  AS p50,
       percentile_cont(0.99) WITHIN GROUP (
           ORDER BY EXTRACT(epoch FROM recibido_en - timestamp_utc))  AS p99,
       max(EXTRACT(epoch FROM recibido_en - timestamp_utc))           AS maximo,
       min(EXTRACT(epoch FROM recibido_en - timestamp_utc))           AS minimo
FROM ami_telemetry
WHERE timestamp_utc >= %(inicio)s AND timestamp_utc < %(fin)s
  AND recibido_en IS NOT NULL
"""

CONSULTA_PERIODO: Final = """
WITH d AS (
    SELECT EXTRACT(epoch FROM timestamp_utc - lag(timestamp_utc)
               OVER (PARTITION BY device_id ORDER BY timestamp_utc)) AS dt
    FROM ami_telemetry
    WHERE timestamp_utc >= %(inicio)s AND timestamp_utc < %(fin)s
)
SELECT percentile_cont(0.50) WITHIN GROUP (ORDER BY dt) AS p50,
       percentile_cont(0.95) WITHIN GROUP (ORDER BY dt) AS p95,
       percentile_cont(0.99) WITHIN GROUP (ORDER BY dt) AS p99,
       min(dt) AS minimo,
       max(dt) AS maximo
FROM d
WHERE dt IS NOT NULL
"""

# C3 — rejilla absoluta anclada a la época Unix, no al arranque del proceso.
# C4 — una celda es (medidor, bin); `lecturas` cuenta cuántas cayeron en
# ella, que es lo que permite cuantificar cuánto dato descarta quedarse con
# la más reciente.
CONSULTA_BINS: Final = """
WITH celdas AS (
    SELECT zona,
           device_id,
           floor(EXTRACT(epoch FROM timestamp_utc) / %(ancho)s)::bigint AS bin,
           count(*) AS lecturas
    FROM ami_telemetry
    WHERE timestamp_utc >= %(inicio)s AND timestamp_utc < %(fin)s
      AND zona IS NOT NULL
    GROUP BY zona, device_id, bin
)
SELECT zona,
       bin,
       count(*)                                  AS medidores,
       sum(lecturas)                             AS lecturas,
       count(*) FILTER (WHERE lecturas > 1)      AS celdas_multiples,
       max(lecturas)                             AS max_lecturas
FROM celdas
GROUP BY zona, bin
ORDER BY zona, bin
"""


def _serie_densa(
    bins: list[int],
    valores: list[int],
) -> npt.NDArray[np.int64]:
    """Rellena con ceros los bins ausentes de la rejilla.

    Un bin sin ninguna lectura de la zona no aparece en el resultado de la
    consulta. Omitirlo haría que dos bins no consecutivos parecieran
    consecutivos, y una racha de 16 "completos" podría abarcar en realidad
    varios minutos con un hueco en el medio.

    Args:
        bins: Índices de bin presentes, ordenados.
        valores: Medidores vistos en cada uno de esos bins.

    Returns:
        Serie de largo `bins[-1] - bins[0] + 1`, con cero donde no hubo
        ninguna lectura.
    """
    primero, ultimo = bins[0], bins[-1]
    serie = np.zeros(ultimo - primero + 1, dtype=np.int64)
    serie[np.asarray(bins, dtype=np.int64) - primero] = np.asarray(valores, dtype=np.int64)
    return serie


def _rachas_completas(completos: npt.NDArray[np.bool_], largo: int) -> float:
    """Fracción de ventanas de `largo` bins consecutivos totalmente completas.

    Args:
        completos: Máscara por bin de la rejilla.
        largo: Bins que exige una ventana.

    Returns:
        Fracción en `[0, 1]`, o 0.0 si no cabe ninguna ventana.
    """
    if completos.size < largo:
        return 0.0
    # Suma móvil sobre la máscara: una ventana es completa si suma `largo`.
    acumulado = np.concatenate(([0], np.cumsum(completos, dtype=np.int64)))
    sumas = acumulado[largo:] - acumulado[:-largo]
    return float((sumas == largo).mean())


def _medir_ancho(
    conn: psycopg.Connection[Any],
    ancho: int,
    inicio: datetime,
    fin: datetime,
    padron: dict[str, int],
) -> dict[str, Any]:
    """Mide completitud y multiplicidad para un ancho de bin.

    Args:
        conn: Conexión abierta.
        ancho: Ancho del bin, en segundos.
        inicio: Primer instante del horizonte.
        fin: Primer instante fuera del horizonte.
        padron: Medidores activos por zona, de `ami_meters`.

    Returns:
        Diccionario con una entrada por zona y el mínimo entre zonas.
    """
    with conn.cursor() as cur:
        cur.execute(CONSULTA_BINS, {"ancho": ancho, "inicio": inicio, "fin": fin})
        filas = cur.fetchall()

    por_zona: dict[str, list[dict[str, Any]]] = {}
    for fila in filas:
        por_zona.setdefault(str(fila["zona"]), []).append(fila)

    zonas: dict[str, Any] = {}
    for zona, registros in sorted(por_zona.items()):
        n = padron.get(zona)
        if n is None:
            continue

        indices = [int(r["bin"]) for r in registros]
        medidores = [int(r["medidores"]) for r in registros]

        # C5.5 — los bins vacíos entran a la rejilla como cero medidores.
        serie = _serie_densa(indices, medidores)
        # Los bins de los extremos están recortados por el horizonte y no
        # representan una unidad completa de tiempo: se descartan.
        serie = serie[1:-1] if serie.size > 2 else serie

        completos = serie == n
        parciales = serie[(serie > 0) & (serie < n)]
        faltantes = (n - parciales).astype(np.int64)

        lecturas = sum(int(r["lecturas"]) for r in registros)
        multiples = sum(int(r["celdas_multiples"]) for r in registros)
        celdas = sum(int(r["medidores"]) for r in registros)

        zonas[zona] = {
            "medidores": n,
            "bins_en_rejilla": int(serie.size),
            "bins_completos": int(completos.sum()),
            "bins_vacios": int((serie == 0).sum()),
            "bins_parciales": int(parciales.size),
            "completitud_por_bin": float(completos.mean()) if serie.size else 0.0,
            "completitud_por_ventana": _rachas_completas(completos, VENTANA_BINS),
            "faltantes_p50": float(np.percentile(faltantes, 50)) if faltantes.size else 0.0,
            "faltantes_p95": float(np.percentile(faltantes, 95)) if faltantes.size else 0.0,
            "faltantes_max": int(faltantes.max()) if faltantes.size else 0,
            "celdas": celdas,
            "celdas_multiples": multiples,
            "fraccion_celdas_multiples": (multiples / celdas) if celdas else 0.0,
            "max_lecturas_por_celda": max(int(r["max_lecturas"]) for r in registros),
            "lecturas": lecturas,
        }

    minimos = [z["completitud_por_ventana"] for z in zonas.values()]
    return {
        "ancho_s": ancho,
        "segundos_por_ventana": ancho * VENTANA_BINS,
        "zonas": zonas,
        "completitud_por_ventana_min": min(minimos) if minimos else 0.0,
        "cumple_objetivo": bool(minimos) and min(minimos) >= COMPLETITUD_OBJETIVO,
    }


def _elegir(barrido: list[dict[str, Any]]) -> dict[str, Any]:
    """Aplica C6 al barrido.

    Args:
        barrido: Mediciones por ancho, en orden creciente de ancho.

    Returns:
        El ancho elegido, la regla que se aplicó y la zona que limita.
    """
    cumplen = [m for m in barrido if m["cumple_objetivo"]]
    if cumplen:
        elegido = min(cumplen, key=lambda m: int(m["ancho_s"]))
        regla = "C6.1"
    else:
        # Máximo del mínimo entre zonas; ante empate, el menor ancho.
        elegido = min(
            barrido,
            key=lambda m: (-float(m["completitud_por_ventana_min"]), int(m["ancho_s"])),
        )
        regla = "C6.2"

    limita = min(
        elegido["zonas"].items(),
        key=lambda kv: float(kv[1]["completitud_por_ventana"]),
    )
    return {
        "ancho_s": int(elegido["ancho_s"]),
        "regla": regla,
        "completitud_por_ventana_min": float(elegido["completitud_por_ventana_min"]),
        "segundos_por_ventana": int(elegido["segundos_por_ventana"]),
        "zona_que_limita": limita[0],
    }


def medir(conn: psycopg.Connection[Any], horas: int) -> dict[str, Any]:
    """Corre el barrido completo.

    Args:
        conn: Conexión abierta.
        horas: Horizonte hacia atrás desde el último dato disponible.

    Returns:
        La medición completa, serializable.

    Raises:
        RuntimeError: Si `ami_telemetry` está vacía.
    """
    with conn.cursor() as cur:
        cur.execute(CONSULTA_VENTANA, {"horas": horas})
        ventana = cur.fetchone()
        if ventana is None or ventana["fin"] is None:
            raise RuntimeError("ami_telemetry está vacía: no hay nada que medir")
        inicio, fin = ventana["inicio"], ventana["fin"]

        cur.execute(CONSULTA_PADRON)
        padron = {str(r["zona"]): int(r["medidores"]) for r in cur.fetchall()}

        cur.execute(CONSULTA_VISTOS, {"inicio": inicio, "fin": fin})
        vistos = {str(r["zona"]): int(r["vistos"]) for r in cur.fetchall()}

        cur.execute(CONSULTA_RETARDO, {"inicio": inicio, "fin": fin})
        retardo = dict(cur.fetchone() or {})

        cur.execute(CONSULTA_PERIODO, {"inicio": inicio, "fin": fin})
        periodo = dict(cur.fetchone() or {})

    # C9 — un medidor que no publicó en todo el horizonte deja incompletos
    # todos los bins de su zona, y contamina cualquier lectura de C5.
    silenciosos = {
        zona: padron[zona] - vistos.get(zona, 0)
        for zona in padron
        if padron[zona] - vistos.get(zona, 0) > 0
    }

    barrido = [_medir_ancho(conn, ancho, inicio, fin, padron) for ancho in ANCHOS]

    return {
        "criterios": "experiments/ventana-viva/CRITERIOS.md",
        "ventana": {
            "inicio_utc": inicio.isoformat(),
            "fin_utc": fin.isoformat(),
            "horas": horas,
        },
        "padron": padron,
        "vistos": vistos,
        "medidores_silenciosos": silenciosos,
        "retardo_transporte_s": {k: (float(v) if v is not None else None)
                                 for k, v in retardo.items()},
        "periodo_entre_mensajes_s": {k: (float(v) if v is not None else None)
                                     for k, v in periodo.items()},
        "ventana_bins": VENTANA_BINS,
        "completitud_objetivo": COMPLETITUD_OBJETIVO,
        "barrido": barrido,
        "eleccion": _elegir(barrido),
    }


def _tabla(medicion: dict[str, Any]) -> str:
    """Arma la tabla resumen para la salida por consola.

    Args:
        medicion: Resultado de `medir`.

    Returns:
        Texto con una fila por ancho.
    """
    lineas = [
        f"{'ancho':>6} {'s/ventana':>10} {'compl.bin min':>14} "
        f"{'compl.ventana min':>18} {'celdas mult.':>13}",
    ]
    for m in medicion["barrido"]:
        zonas = m["zonas"].values()
        bin_min = min((z["completitud_por_bin"] for z in zonas), default=0.0)
        mult = max((z["fraccion_celdas_multiples"] for z in zonas), default=0.0)
        lineas.append(
            f"{m['ancho_s']:>6} {m['segundos_por_ventana']:>10} "
            f"{bin_min:>13.1%} {m['completitud_por_ventana_min']:>17.1%} "
            f"{mult:>12.1%}"
        )
    return "\n".join(lineas)


def main() -> int:
    """Punto de entrada.

    Returns:
        Código de salida del proceso.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json",
        type=Path,
        default=Path(__file__).resolve().parent / "results" / "medicion.json",
        help="destino del JSON con los datos crudos",
    )
    parser.add_argument("--horas", type=int, default=VENTANA_HORAS)
    args = parser.parse_args()

    with _conexion() as conn:
        medicion = medir(conn, args.horas)

    destino = args.json if args.json.is_absolute() else Path.cwd() / args.json
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(
        json.dumps(medicion, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(f"ventana: {medicion['ventana']['inicio_utc']} → {medicion['ventana']['fin_utc']}")
    print(f"padrón: {medicion['padron']}")
    if medicion["medidores_silenciosos"]:
        print(f"MEDIDORES SILENCIOSOS: {medicion['medidores_silenciosos']}")
    else:
        print("medidores silenciosos: ninguno")
    print(f"periodo entre mensajes (s): {medicion['periodo_entre_mensajes_s']}")
    print(f"retardo de transporte (s): {medicion['retardo_transporte_s']}")
    print()
    print(_tabla(medicion))
    print()
    print(f"elección: {medicion['eleccion']}")
    print(f"escrito: {destino}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
