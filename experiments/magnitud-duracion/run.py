#!/usr/bin/env python3
"""¿Cuánto mejora la detección al integrar sobre la duración del evento?

La medición anterior (`experiments/firma-espectral/`) dejó el problema
acotado: sobre un solo instante y a 1σ, el oráculo que conoce exactamente
qué nodos están afectados llega al 49 % de detección. Es decir, se está
cerca del límite de información y fijar el detector ahí sería optimizarlo
para un régimen sin margen.

Acá se barre magnitud × duración para encontrar el régimen donde sí hay
margen. Cuatro preguntas:

1. ¿Cómo mejora la detección al integrar sobre N instantes?
2. ¿Hay un punto donde la curva se aplana?
3. ¿Cómo se mueve el **oráculo** con la duración? Es el techo real.
4. ¿El umbral también mejora integrando? Si mejora igual, la ventaja de H3
   no crece con la duración, y conviene saberlo antes de diseñar nada.

# CRITERIOS, DECLARADOS ANTES DE MIRAR LOS RESULTADOS

Este bloque se commitea **antes** de correr el experimento. El punto de
operación de la tesis sale de aplicar estas reglas a las cifras, no de
elegir las cifras que quedan bien.

**C1 — Falsos positivos: 1 % por zona y ventana.** El mismo de la medición
anterior, para que las cifras sean comparables entre experimentos.

**C2 — Potencia mínima exigida: 80 %.** Es la convención de diseño
experimental (potencia 0,8), no un número elegido para este problema.

**C3 — Régimen operativo de la tesis:** el par (magnitud, duración) de
**menor magnitud** que alcanza C2 con el detector realizable, el escaneo.
Si varias duraciones empatan en magnitud, la menor. Se prefiere la
magnitud más chica porque es lo que hace al evento sutil, que es la
premisa entera del experimento; la duración es latencia, y se paga una
vez.

**C4 — Aplanamiento:** la curva se declara aplanada en el primer N donde
**duplicar N agrega menos de 5 puntos porcentuales** de detección.

**C5 — H3 aporta** si, en el régimen operativo de C3, la tasa del escaneo
es **a la vez** al menos el doble de la del umbral y mayor que ella en al
menos 20 puntos porcentuales. Las dos condiciones: el cociente solo premia
las tasas bajas y la diferencia sola premia las altas.

**C6 — Regla de integración:** promedio temporal de la señal sobre la
ventana del evento, la misma ventana para todos los estadísticos. Se
asume la ventana **conocida**, lo que favorece por igual a todos los
comparadores. Un detector real tendría que buscarla, y eso queda declarado
como limitación.

Uso:

    python experiments/magnitud-duracion/run.py --json results/medicion.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Final

import numpy as np
import numpy.typing as npt

_REPO: Final = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "services" / "monitor-gsp" / "src"))
sys.path.insert(0, str(_REPO / "services" / "event-injector" / "src"))

from urbia_events import (  # noqa: E402
    CollectiveDeviationSpec,
    EventInjector,
    device_type_of,
    k_hop,
    load_bounds,
    load_profile,
)
from urbia_monitor_gsp.graph import (  # noqa: E402
    GraphConfig,
    MeterNode,
    ZoneGraph,
    build_ami_graph,
    laplacian,
)

TOPOLOGIA: Final = _REPO / "data" / "topologies" / "manizales_150.json"
ESQUEMA: Final = _REPO / "data" / "schemas" / "payload_schema_v1.json"
PERFIL: Final = _REPO / "data" / "profiles" / "manizales_signal_v1.json"

SEMILLA: Final = 20260808
MAGNITUD: Final = "voltaje_v"
DEPTH: Final = 2
"""El punto dulce de la medición anterior: grupo grande y con frontera."""

MAGNITUDES: Final = (0.5, 1.0, 1.5, 2.0, 3.0)
DURACIONES: Final = (1, 2, 5, 10, 20, 50)
N_ENSAYOS: Final = 400

FPR_OBJETIVO: Final = 0.01          # C1
POTENCIA_MINIMA: Final = 0.80       # C2
UMBRAL_APLANAMIENTO: Final = 0.05   # C4
FACTOR_H3: Final = 2.0              # C5
DIFERENCIA_H3: Final = 0.20         # C5
RADIO_ESCANEO: Final = 1


# ───────────────────────────────────────────────────────── preparación


def cargar() -> tuple[Any, Any, Any]:
    """Carga grafo, perfil y límites.

    Returns:
        Tupla `(grafo, perfil, limites)`.
    """
    datos = json.loads(TOPOLOGIA.read_text(encoding="utf-8"))
    meters = [MeterNode(**m) for m in datos["meters"]]
    return (
        build_ami_graph(meters, GraphConfig()),
        load_profile(PERFIL),
        load_bounds(ESQUEMA),
    )


def mascaras(zone: ZoneGraph, radio: int) -> npt.NDArray[np.float64]:
    """Matriz `(n, n)` con la bola de radio dado centrada en cada nodo.

    Args:
        zone: Subgrafo zonal.
        radio: Radio de las bolas.

    Returns:
        Matriz de pertenencia, una fila por bola.
    """
    m = np.zeros((zone.n_meters, zone.n_meters), dtype=np.float64)
    for j in range(zone.n_meters):
        m[j, list(k_hop(zone.adjacency, j, radio))] = 1.0
    return m


def deltas_por_semilla(
    zone: ZoneGraph,
    perfil: Any,
    limites: Any,
    sigma_multiple: float,
) -> npt.NDArray[np.float64]:
    """Desviación que el inyector aplica con cada nodo como semilla.

    Se extrae una vez por configuración, sobre una señal de fondo nula. Con
    `sigma_multiple` la desviación no depende de la señal —es `k·σ` sobre
    el grupo—, así que reutilizarla es exactamente equivalente a inyectar
    en cada realización, y evita 70 000 llamadas.

    Args:
        zone: Subgrafo zonal.
        perfil: Perfil de señal.
        limites: Límites del esquema.
        sigma_multiple: Magnitud de la desviación.

    Returns:
        Matriz `(n, n)`: la fila `j` es la desviación con semilla `j`.
    """
    inyector = EventInjector(perfil, limites, seed=SEMILLA)
    salida = np.zeros((zone.n_meters, zone.n_meters))
    for j, device_id in enumerate(zone.device_ids):
        senal, _ = inyector.inject(
            zone,
            np.zeros(zone.n_meters),
            [
                CollectiveDeviationSpec(
                    magnitude=MAGNITUD,
                    depth=DEPTH,
                    sigma_multiple=sigma_multiple,
                    seed_device_id=device_id,
                )
            ],
        )
        salida[j] = senal[0]
    return salida


# ─────────────────────────────────────────────────────── estadísticos


def escaneo(
    medias: npt.NDArray[np.float64],
    bolas: npt.NDArray[np.float64],
    sigma_eff: float,
) -> npt.NDArray[np.float64]:
    """Mayor contraste grupo-contra-resto sobre las bolas candidatas.

    Args:
        medias: Señal promediada, `(R, n)`.
        bolas: Matriz de pertenencia de las bolas, `(B, n)`.
        sigma_eff: Dispersión efectiva tras promediar, `σ/√N`.

    Returns:
        Vector `(R,)` con el mayor contraste de cada realización.
    """
    return np.asarray(_contrastes(medias, bolas, sigma_eff).max(axis=1))


def _contrastes(
    medias: npt.NDArray[np.float64],
    grupos: npt.NDArray[np.float64],
    sigma_eff: float,
) -> npt.NDArray[np.float64]:
    """Contraste de dos muestras entre cada grupo y su complemento.

    Args:
        medias: Señal promediada, `(R, n)`.
        grupos: Matriz de pertenencia, `(B, n)`.
        sigma_eff: Dispersión efectiva.

    Returns:
        Matriz `(R, B)` de contrastes en unidades de σ.
    """
    n = medias.shape[1]
    dentro = grupos.sum(axis=1)
    fuera = n - dentro
    suma_dentro = medias @ grupos.T
    suma_total = medias.sum(axis=1, keepdims=True)
    media_dentro = suma_dentro / dentro
    media_fuera = (suma_total - suma_dentro) / fuera
    error = sigma_eff * np.sqrt(1.0 / dentro + 1.0 / fuera)
    return np.asarray(np.abs(media_dentro - media_fuera) / error)


def _auc(positivos: npt.NDArray[np.float64], negativos: npt.NDArray[np.float64]) -> float:
    """Área bajo la curva ROC por el estadístico de Mann-Whitney.

    Args:
        positivos: Estadístico con evento.
        negativos: Estadístico sin evento.

    Returns:
        AUC en `[0, 1]`.
    """
    todos = np.concatenate([positivos, negativos])
    rangos = todos.argsort().argsort().astype(np.float64) + 1.0
    n_pos, n_neg = positivos.size, negativos.size
    return (float(rangos[:n_pos].sum()) - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)


def _tasa(positivos: npt.NDArray[np.float64], negativos: npt.NDArray[np.float64]) -> float:
    """Tasa de detección con el corte calibrado al FPR objetivo (C1).

    Args:
        positivos: Estadístico con evento.
        negativos: Estadístico sin evento.

    Returns:
        Tasa de detección en `[0, 1]`.
    """
    corte = float(np.quantile(negativos, 1.0 - FPR_OBJETIVO))
    return float((positivos > corte).mean())


# ────────────────────────────────────────────────────────── medición


def medir_celda(
    zone: ZoneGraph,
    perfil: Any,
    limites: Any,
    l_comb: npt.NDArray[np.float64],
    bolas: npt.NDArray[np.float64],
    sigma_multiple: float,
    duracion: int,
) -> dict[str, float]:
    """Mide una combinación de magnitud y duración sobre una zona.

    Args:
        zone: Subgrafo zonal.
        perfil: Perfil de señal.
        limites: Límites del esquema.
        l_comb: Laplaciano combinatorio precalculado.
        bolas: Bolas candidatas del escaneo.
        sigma_multiple: Magnitud del evento.
        duracion: Instantes sobre los que se integra.

    Returns:
        Tasas y AUC de cada estadístico.
    """
    p = perfil.get(MAGNITUD, device_type_of(zone.device_ids[0]))
    n = zone.n_meters
    rng = np.random.default_rng([SEMILLA, duracion, int(sigma_multiple * 100)])

    ruido = rng.normal(p.mean, p.sigma_spatial, size=(N_ENSAYOS, duracion, n))
    limpio = ruido.mean(axis=1)

    deltas = deltas_por_semilla(zone, perfil, limites, sigma_multiple)
    semillas = np.arange(N_ENSAYOS) % n
    con_evento = limpio + deltas[semillas]

    verdaderos = deltas[semillas] > 0.0
    fuera_de_rango = limites[MAGNITUD].violations(con_evento)
    sigma_eff = p.sigma_spatial / np.sqrt(duracion)

    def paquete(x: npt.NDArray[np.float64]) -> dict[str, npt.NDArray[np.float64]]:
        contrastes = _contrastes(x, verdaderos.astype(np.float64), sigma_eff)
        return {
            "umbral": np.abs(x - p.mean).max(axis=1) / sigma_eff,
            "dirichlet_comb": ((x @ l_comb) * x).sum(axis=1),
            "escaneo": escaneo(x, bolas, sigma_eff),
            "oraculo": contrastes[np.arange(N_ENSAYOS), np.arange(N_ENSAYOS)],
        }

    negativos, positivos = paquete(limpio), paquete(con_evento)
    salida: dict[str, float] = {
        "nodos_afectados": float(verdaderos[0].sum()),
        "fuera_de_rango": float(fuera_de_rango.mean()),
    }
    for nombre in ("umbral", "dirichlet_comb", "escaneo", "oraculo"):
        salida[f"tasa_{nombre}"] = _tasa(positivos[nombre], negativos[nombre])
        salida[f"auc_{nombre}"] = _auc(positivos[nombre], negativos[nombre])
    return salida


def medir(grafo: Any, perfil: Any, limites: Any) -> list[dict[str, Any]]:
    """Barre magnitud × duración sobre las seis zonas.

    Args:
        grafo: Grafo AMI.
        perfil: Perfil de señal.
        limites: Límites del esquema.

    Returns:
        Una fila por zona, magnitud y duración.
    """
    filas: list[dict[str, Any]] = []
    for zona_nombre in grafo.zone_order:
        zona = grafo.zones[zona_nombre]
        l_comb = laplacian(zona.adjacency)
        bolas = mascaras(zona, RADIO_ESCANEO)
        for sigma_multiple in MAGNITUDES:
            for duracion in DURACIONES:
                filas.append(
                    {
                        "zona": zona_nombre,
                        "sigma_multiple": sigma_multiple,
                        "duracion": duracion,
                        **medir_celda(
                            zona, perfil, limites, l_comb, bolas, sigma_multiple, duracion
                        ),
                    }
                )
        print(f"  {zona_nombre} listo")
    return filas


# ──────────────────────────────────────────────── aplicación de reglas


def promediar(filas: list[dict[str, Any]]) -> dict[tuple[float, int], dict[str, float]]:
    """Promedia sobre las seis zonas cada celda del barrido.

    Args:
        filas: Salida de `medir`.

    Returns:
        Promedios indexados por `(magnitud, duración)`.
    """
    claves = sorted({(f["sigma_multiple"], f["duracion"]) for f in filas})
    campos = [k for k in filas[0] if k not in ("zona", "sigma_multiple", "duracion")]
    return {
        clave: {
            c: float(
                np.mean(
                    [
                        f[c]
                        for f in filas
                        if (f["sigma_multiple"], f["duracion"]) == clave
                    ]
                )
            )
            for c in campos
        }
        for clave in claves
    }


def aplicar_criterios(tabla: dict[tuple[float, int], dict[str, float]]) -> dict[str, Any]:
    """Aplica C3, C4 y C5 a las cifras medidas.

    Args:
        tabla: Salida de `promediar`.

    Returns:
        El régimen operativo elegido y el veredicto sobre H3.
    """
    alcanzan = [
        clave for clave, d in tabla.items() if d["tasa_escaneo"] >= POTENCIA_MINIMA
    ]
    regimen = min(alcanzan, key=lambda c: (c[0], c[1])) if alcanzan else None

    aplanamiento: dict[float, int | None] = {}
    for magnitud in MAGNITUDES:
        punto: int | None = None
        for i, duracion in enumerate(DURACIONES[:-1]):
            siguiente = DURACIONES[i + 1]
            if siguiente > 2 * duracion:
                continue
            salto = tabla[(magnitud, siguiente)]["tasa_escaneo"] - tabla[
                (magnitud, duracion)
            ]["tasa_escaneo"]
            if salto < UMBRAL_APLANAMIENTO:
                punto = duracion
                break
        aplanamiento[magnitud] = punto

    veredicto: dict[str, Any] = {"regimen": regimen, "aplanamiento": aplanamiento}
    if regimen is not None:
        d = tabla[regimen]
        cociente = d["tasa_escaneo"] / d["tasa_umbral"] if d["tasa_umbral"] > 0 else np.inf
        diferencia = d["tasa_escaneo"] - d["tasa_umbral"]
        veredicto.update(
            {
                "cociente_h3": float(cociente),
                "diferencia_h3": float(diferencia),
                "h3_aporta": bool(cociente >= FACTOR_H3 and diferencia >= DIFERENCIA_H3),
            }
        )
    return veredicto


def imprimir(tabla: dict[tuple[float, int], dict[str, float]], veredicto: dict[str, Any]) -> None:
    """Imprime el barrido y el resultado de aplicar los criterios.

    Args:
        tabla: Salida de `promediar`.
        veredicto: Salida de `aplicar_criterios`.
    """
    for nombre, clave in (
        ("ESCANEO (detector realizable)", "tasa_escaneo"),
        ("UMBRAL por medidor (comparador de H3)", "tasa_umbral"),
        ("ORACULO (techo de informacion)", "tasa_oraculo"),
    ):
        print(f"\n== {nombre}: tasa de deteccion al {FPR_OBJETIVO:.0%} de FPR ==\n")
        print(f"{'sigma':>7} " + " ".join(f"{'N=' + str(d):>8}" for d in DURACIONES))
        for magnitud in MAGNITUDES:
            celdas = " ".join(
                f"{tabla[(magnitud, d)][clave]:>7.1%} " for d in DURACIONES
            )
            print(f"{magnitud:>7.1f} {celdas}")

    print("\n== APLICACION DE LOS CRITERIOS DECLARADOS ==\n")
    print(f"  C4  aplanamiento (primer N con salto < {UMBRAL_APLANAMIENTO:.0%}):")
    for magnitud, punto in veredicto["aplanamiento"].items():
        print(f"        sigma={magnitud:<4} {'N=' + str(punto) if punto else 'no se aplana'}")

    regimen = veredicto["regimen"]
    if regimen is None:
        print(f"\n  C3  NINGUNA celda alcanza la potencia minima de {POTENCIA_MINIMA:.0%}")
        return
    print(f"\n  C3  regimen operativo: sigma={regimen[0]}, N={regimen[1]}")
    print(f"  C5  escaneo/umbral = {veredicto['cociente_h3']:.2f}x "
          f"(exigido {FACTOR_H3:.0f}x)")
    print(f"      diferencia     = {veredicto['diferencia_h3']:.1%} "
          f"(exigido {DIFERENCIA_H3:.0%})")
    print(f"      H3 APORTA: {veredicto['h3_aporta']}")


def main() -> int:
    """Corre el barrido y aplica los criterios.

    Returns:
        Código de salida del proceso.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args()

    grafo, perfil, limites = cargar()
    print(f"magnitud   {MAGNITUD}   depth={DEPTH}   {N_ENSAYOS} ensayos por celda")
    print(f"criterios  FPR {FPR_OBJETIVO:.0%}, potencia minima {POTENCIA_MINIMA:.0%}, "
          f"H3 exige {FACTOR_H3:.0f}x y {DIFERENCIA_H3:.0%}\n")

    filas = medir(grafo, perfil, limites)
    tabla = promediar(filas)
    veredicto = aplicar_criterios(tabla)
    imprimir(tabla, veredicto)

    if args.json is not None:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(
                {
                    "semilla": SEMILLA,
                    "magnitud": MAGNITUD,
                    "depth": DEPTH,
                    "n_ensayos": N_ENSAYOS,
                    "criterios": {
                        "C1_fpr": FPR_OBJETIVO,
                        "C2_potencia_minima": POTENCIA_MINIMA,
                        "C4_umbral_aplanamiento": UMBRAL_APLANAMIENTO,
                        "C5_factor": FACTOR_H3,
                        "C5_diferencia": DIFERENCIA_H3,
                    },
                    "barrido": filas,
                    "veredicto": {
                        k: (list(v) if isinstance(v, tuple) else v)
                        for k, v in veredicto.items()
                    },
                },
                indent=2,
                ensure_ascii=False,
                default=str,
            ),
            encoding="utf-8",
        )
        print(f"\nJSON escrito en {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
