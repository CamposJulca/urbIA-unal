#!/usr/bin/env python3
"""Mide el perfil de la señal AMI y lo congela como artefacto versionado.

El perfil responde a una sola pregunta: **qué desviación es sutil**. Un 5 %
es 2,5σ en voltaje —evidente para cualquier umbral— y 0,16σ en corriente
—invisible—, así que sin este perfil la magnitud de un evento inyectado no
significa nada.

La cantidad que importa es la **dispersión espacial**: cuánto difieren los
medidores entre sí en un mismo instante. Es lo que ve un detector definido
sobre el grafo. No es lo mismo que la dispersión temporal, que incluye la
curva de carga diaria compartida por todos los medidores y por lo tanto no
produce discordancia entre vecinos.

    σ_espacial² = E_t[ Var_medidores( x(t) ) ]

Se estima como la raíz de la media de las varianzas por instante, no como
la media de las desviaciones, que subestima.

Uso:

    POSTGRES_PASSWORD=... python experiments/perfil-senal/run.py \
        --salida data/profiles/manizales_signal_v1.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Final

import psycopg
from psycopg.rows import dict_row

_REPO_ROOT: Final = Path(__file__).resolve().parents[2]

MAGNITUDES: Final = ("voltaje_v", "corriente_a", "potencia_kw")
"""Magnitudes sobre las que el inyector puede desviar una señal."""

ESTADO_NORMAL: Final = "activo"
"""El perfil describe operación normal.

Los estados `anomalia_voltaje` y `falla` se excluyen a propósito: son las
anomalías que ya produce el simulador, y el perfil tiene que describir el
fondo contra el cual un evento nuevo debe resultar sutil, no mezclarse con
ellas.
"""

MIN_MEDIDORES_POR_INSTANTE: Final = 10
"""Instantes con menos medidores no dan una varianza espacial estable."""

VENTANA_HORAS: Final = 24
"""Ventana de medición, hacia atrás desde el último dato disponible."""


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
            "falta POSTGRES_PASSWORD. En .102 se puede tomar del contenedor sin "
            "escribirla: POSTGRES_PASSWORD=$(docker inspect urbia-postgres "
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
SELECT max(timestamp_utc) AS fin,
       max(timestamp_utc) - make_interval(hours => %(horas)s) AS inicio
FROM ami_telemetry
"""

CONSULTA_PERFIL: Final = """
WITH cortes AS (
    SELECT date_trunc('second', timestamp_utc) AS instante,
           device_type,
           count(*)                AS medidores,
           avg({magnitud})         AS media,
           var_samp({magnitud})    AS varianza
    FROM ami_telemetry
    WHERE estado = %(estado)s
      AND timestamp_utc > %(inicio)s
      AND timestamp_utc <= %(fin)s
    GROUP BY 1, 2
    HAVING count(*) >= %(min_medidores)s
)
SELECT device_type,
       count(*)          AS instantes,
       avg(medidores)    AS medidores_por_instante,
       avg(media)        AS media,
       sqrt(avg(varianza)) AS sigma_espacial
FROM cortes
GROUP BY 1
ORDER BY 1
"""

CONSULTA_GLOBAL: Final = """
SELECT device_type,
       count(*)          AS filas,
       count(DISTINCT device_id) AS medidores,
       avg({magnitud})   AS media,
       stddev_samp({magnitud}) AS sigma_agrupada,
       min({magnitud})   AS minimo,
       percentile_cont(0.01) WITHIN GROUP (ORDER BY {magnitud}) AS p1,
       percentile_cont(0.50) WITHIN GROUP (ORDER BY {magnitud}) AS p50,
       percentile_cont(0.99) WITHIN GROUP (ORDER BY {magnitud}) AS p99,
       max({magnitud})   AS maximo
FROM ami_telemetry
WHERE estado = %(estado)s
  AND timestamp_utc > %(inicio)s
  AND timestamp_utc <= %(fin)s
GROUP BY 1
ORDER BY 1
"""

CONSULTA_ZONAS: Final = """
SELECT zona, device_type, count(DISTINCT device_id) AS medidores
FROM ami_telemetry
WHERE timestamp_utc > %(inicio)s AND timestamp_utc <= %(fin)s
GROUP BY 1, 2
ORDER BY 1
"""


def medir(conn: psycopg.Connection[Any], horas: int) -> dict[str, Any]:
    """Mide el perfil sobre la ventana declarada.

    Args:
        conn: Conexión abierta a la base.
        horas: Ancho de la ventana, hacia atrás desde el último dato.

    Returns:
        El perfil completo, listo para serializar.
    """
    with conn.cursor() as cur:
        cur.execute(CONSULTA_VENTANA, {"horas": horas})
        ventana = cur.fetchone()
        assert ventana is not None
        parametros = {
            "estado": ESTADO_NORMAL,
            "inicio": ventana["inicio"],
            "fin": ventana["fin"],
            "min_medidores": MIN_MEDIDORES_POR_INSTANTE,
        }

        magnitudes: dict[str, Any] = {}
        for magnitud in MAGNITUDES:
            cur.execute(CONSULTA_PERFIL.format(magnitud=magnitud), parametros)
            espacial = {f["device_type"]: f for f in cur.fetchall()}
            cur.execute(CONSULTA_GLOBAL.format(magnitud=magnitud), parametros)
            global_ = {f["device_type"]: f for f in cur.fetchall()}

            magnitudes[magnitud] = {
                tipo: {
                    "media": round(float(global_[tipo]["media"]), 6),
                    "sigma_espacial": round(float(espacial[tipo]["sigma_espacial"]), 6),
                    "sigma_agrupada": round(float(global_[tipo]["sigma_agrupada"]), 6),
                    "minimo_observado": round(float(global_[tipo]["minimo"]), 6),
                    "p1": round(float(global_[tipo]["p1"]), 6),
                    "p50": round(float(global_[tipo]["p50"]), 6),
                    "p99": round(float(global_[tipo]["p99"]), 6),
                    "maximo_observado": round(float(global_[tipo]["maximo"]), 6),
                    "filas": int(global_[tipo]["filas"]),
                    "medidores": int(global_[tipo]["medidores"]),
                    "instantes": int(espacial[tipo]["instantes"]),
                    "medidores_por_instante": round(
                        float(espacial[tipo]["medidores_por_instante"]), 3
                    ),
                }
                for tipo in sorted(global_)
            }

        cur.execute(CONSULTA_ZONAS, {"inicio": ventana["inicio"], "fin": ventana["fin"]})
        zonas = {f["zona"]: f["device_type"] for f in cur.fetchall()}

    return {
        "version": "manizales-signal-v1",
        "fuente": "ami_telemetry en urbia-postgres (.102)",
        "ventana": {
            "inicio_utc": ventana["inicio"].isoformat(),
            "fin_utc": ventana["fin"].isoformat(),
            "horas": horas,
        },
        "estado_incluido": ESTADO_NORMAL,
        "min_medidores_por_instante": MIN_MEDIDORES_POR_INSTANTE,
        "definicion_sigma_espacial": (
            "raiz de la media sobre instantes de la varianza entre medidores del "
            "mismo device_type en ese instante; es la dispersion que ve un "
            "detector definido sobre el grafo"
        ),
        "zona_a_device_type": zonas,
        "magnitudes": magnitudes,
    }


def _imprimir(perfil: dict[str, Any]) -> None:
    """Imprime el perfil medido en forma legible.

    Args:
        perfil: Salida de `medir`.
    """
    v = perfil["ventana"]
    print(f"ventana     {v['inicio_utc']}  a  {v['fin_utc']}  ({v['horas']} h)")
    print(f"estado      {perfil['estado_incluido']}")
    print(f"zonas       {perfil['zona_a_device_type']}\n")
    for magnitud, por_tipo in perfil["magnitudes"].items():
        print(f"== {magnitud} ==")
        print(
            f"  {'tipo':<11} {'media':>10} {'sigma_esp':>11} {'sigma/media':>12} "
            f"{'sigma_agr':>11} {'p1':>9} {'p99':>9} {'min':>9} {'max':>9}"
        )
        for tipo, d in por_tipo.items():
            print(
                f"  {tipo:<11} {d['media']:>10.4f} {d['sigma_espacial']:>11.4f} "
                f"{d['sigma_espacial'] / d['media']:>11.2%} "
                f"{d['sigma_agrupada']:>11.4f} {d['p1']:>9.3f} {d['p99']:>9.3f} "
                f"{d['minimo_observado']:>9.3f} {d['maximo_observado']:>9.3f}"
            )
        print()


def main() -> int:
    """Mide el perfil y lo escribe como JSON versionado.

    Returns:
        Código de salida del proceso.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--horas", type=int, default=VENTANA_HORAS)
    parser.add_argument(
        "--salida",
        type=Path,
        default=_REPO_ROOT / "data" / "profiles" / "manizales_signal_v1.json",
    )
    args = parser.parse_args()

    with _conexion() as conn:
        perfil = medir(conn, args.horas)

    _imprimir(perfil)

    args.salida.parent.mkdir(parents=True, exist_ok=True)
    texto = json.dumps(perfil, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    args.salida.write_text(texto, encoding="utf-8")
    digest = hashlib.md5(texto.encode("utf-8")).hexdigest()
    print(f"escrito {args.salida.relative_to(_REPO_ROOT)}")
    print(f"md5     {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
