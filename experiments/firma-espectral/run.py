#!/usr/bin/env python3
"""¿Dónde está la firma de un evento colectivo en el espectro del grafo?

Se mide **antes** de escribir el detector, para que lo que el detector mire
salga de una medición y no de una suposición. Cuatro preguntas:

1. **¿La forma de la firma depende de su magnitud?** Si no, el barrido de
   magnitud sólo cambia la relación señal-ruido y no dónde mirar.
2. **¿Dónde cae la energía, y de qué depende?** Reparto entre modos por
   profundidad de vecindario, y qué propiedad del grupo afectado lo
   gobierna.
3. **¿Se distingue de una anomalía individual?** Es la pregunta que decide
   si H3 es demostrable: si la firma colectiva y la individual se ven
   iguales en el espectro, el método no aporta sobre un umbral.
4. **¿Qué hace un umbral simple sobre estos mismos eventos?** Es el
   comparador de H3 y tiene que estar desde el principio.

Sobre el centrado, se aplica la regla que documenta `graph/filter`: la
energía de Dirichlet **no** se centra —ya es invariante al modo cero— y
cualquier lectura por modo proyecta fuera de `u₀`, nunca resta la media.

Uso:

    python experiments/firma-espectral/run.py --json results/medicion.json
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
    band_cut_index,
    build_ami_graph,
    dirichlet_energy,
    gft,
    laplacian,
)

TOPOLOGIA: Final = _REPO / "data" / "topologies" / "manizales_150.json"
ESQUEMA: Final = _REPO / "data" / "schemas" / "payload_schema_v1.json"
PERFIL: Final = _REPO / "data" / "profiles" / "manizales_signal_v1.json"

SEMILLA: Final = 20260808
MAGNITUD: Final = "voltaje_v"
"""Voltaje: σ/media del 2 %, la única magnitud donde 1σ es a la vez sutil
para un umbral y coherente entre los nodos del grupo."""

PROFUNDIDADES: Final = (0, 1, 2, 3)
SIGMA_INDIVIDUAL: Final = 6.0
"""La anomalía que el simulador ya produce: 246,5 V de media, +6,0σ."""
SIGMA_COLECTIVA: Final = 1.0

N_ENSAYOS: Final = 500
"""Realizaciones independientes por configuración, para las curvas ROC."""


# ─────────────────────────────────────────────────────── utilidades


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


def sin_modo_cero(zone: ZoneGraph, x: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    """Proyecta la señal fuera del núcleo de `L_norm`.

    Es la operación correcta para leer el espectro por modo: restar la
    media dejaría residuo, porque el núcleo es `D^(1/2)·1` y no la
    constante. Ver el docstring de `graph/filter`.

    Args:
        zone: Subgrafo zonal.
        x: Señal sobre los nodos.

    Returns:
        La señal sin componente en `u₀`.
    """
    u0 = zone.eigenvectors[:, 0]
    return np.asarray(x - (u0 @ x) * u0, dtype=np.float64)


def perfil_espectral(zone: ZoneGraph, x: npt.NDArray[np.float64]) -> dict[str, float]:
    """Dónde cae la energía de una señal en el espectro del grafo.

    Args:
        zone: Subgrafo zonal.
        x: Señal sobre los nodos.

    Returns:
        Fracción en el modo cero, reparto por bandas del resto, y el
        cociente de Rayleigh `E_D(x)/‖x‖²`, que resume en un solo número
        dónde está la energía (0 = todo en el núcleo, λmax = todo en el
        modo más alto).
    """
    espectro = gft(x, zone.eigenvectors)
    energia = espectro**2
    total = float(energia.sum())
    if total == 0.0:
        return {"modo_cero": 0.0, "banda_alta": 0.0, "rayleigh": 0.0}

    corte = band_cut_index(zone.eigenvalues)
    sin_dc = energia[1:]
    total_sin_dc = float(sin_dc.sum())
    alta = float(energia[corte:].sum())

    return {
        "modo_cero": float(energia[0]) / total,
        "banda_alta": alta / total_sin_dc if total_sin_dc > 0 else 0.0,
        "rayleigh": float(dirichlet_energy(zone, x)) / total,
    }


def frontera(zone: ZoneGraph, nodos: tuple[int, ...]) -> dict[str, float]:
    """Tamaño y frontera del grupo afectado.

    Args:
        zone: Subgrafo zonal.
        nodos: Posiciones de los nodos del grupo.

    Returns:
        Cantidad de nodos, aristas de corte, y su cociente.
    """
    dentro = np.zeros(zone.n_meters, dtype=bool)
    dentro[list(nodos)] = True
    corte = float(((zone.adjacency > 0) & dentro[:, None] & ~dentro[None, :]).sum())
    return {
        "n_nodos": float(len(nodos)),
        "aristas_de_corte": corte,
        "corte_por_nodo": corte / len(nodos),
    }


# ─────────────────────────────────────────────── 1. forma vs magnitud


def medir_forma_vs_magnitud(grafo: Any, perfil: Any, limites: Any) -> list[dict[str, Any]]:
    """¿Cambia la forma del espectro con la magnitud del evento?

    Args:
        grafo: Grafo AMI.
        perfil: Perfil de señal.
        limites: Límites del esquema.

    Returns:
        Una fila por magnitud probada, con su perfil espectral normalizado.
    """
    zona = grafo.zones["centro"]
    semilla = zona.device_ids[0]
    filas: list[dict[str, Any]] = []

    for sigma in (0.5, 1.0, 2.0, 6.0):
        inyector = EventInjector(perfil, limites, seed=SEMILLA)
        base = np.zeros(zona.n_meters)
        senal, verdad = inyector.inject(
            zona,
            base,
            [
                CollectiveDeviationSpec(
                    magnitude=MAGNITUD, depth=1, sigma_multiple=sigma, seed_device_id=semilla
                )
            ],
            on_violation="scale",
        )
        delta = senal[0]
        filas.append({"sigma_multiple": sigma, "norma": float(np.linalg.norm(delta)),
                      **perfil_espectral(zona, delta)})
        del verdad
    return filas


# ────────────────────────────────────── 2 y 3. dónde cae la firma


def medir_firma(grafo: Any, perfil: Any, limites: Any) -> list[dict[str, Any]]:
    """Perfil espectral de la firma, por zona y profundidad, sobre todas las semillas.

    La firma es la desviación aplicada, es decir la diferencia entre la
    señal con evento y sin él. Se mide sobre una señal de fondo nula para
    aislarla del ruido: lo que se busca acá es la forma de la firma, no su
    detectabilidad.

    Args:
        grafo: Grafo AMI.
        perfil: Perfil de señal.
        limites: Límites del esquema.

    Returns:
        Una fila por zona, profundidad y nodo semilla.
    """
    filas: list[dict[str, Any]] = []
    for zona_nombre in grafo.zone_order:
        zona = grafo.zones[zona_nombre]
        sigma = SIGMA_COLECTIVA
        for depth in PROFUNDIDADES:
            for indice, device_id in enumerate(zona.device_ids):
                nodos = k_hop(zona.adjacency, indice, depth)
                inyector = EventInjector(perfil, limites, seed=SEMILLA)
                senal, _ = inyector.inject(
                    zona,
                    np.zeros(zona.n_meters),
                    [
                        CollectiveDeviationSpec(
                            magnitude=MAGNITUD,
                            depth=depth,
                            sigma_multiple=sigma,
                            seed_device_id=device_id,
                        )
                    ],
                    on_violation="scale",
                )
                filas.append(
                    {
                        "zona": zona_nombre,
                        "depth": depth,
                        "semilla": device_id,
                        **frontera(zona, nodos),
                        **perfil_espectral(zona, senal[0]),
                    }
                )
    return filas


# ──────────────────────────────────────────── 4. umbral y separabilidad


def _auc(positivos: npt.NDArray[np.float64], negativos: npt.NDArray[np.float64]) -> float:
    """Área bajo la curva ROC por el estadístico de Mann-Whitney.

    Args:
        positivos: Estadístico en las realizaciones con evento.
        negativos: Estadístico en las realizaciones sin evento.

    Returns:
        AUC en `[0, 1]`. 0,5 es indistinguible.
    """
    todos = np.concatenate([positivos, negativos])
    rangos = todos.argsort().argsort().astype(np.float64) + 1.0
    n_pos, n_neg = positivos.size, negativos.size
    suma = float(rangos[:n_pos].sum())
    return (suma - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)


def estadisticos(
    zone: ZoneGraph,
    x: npt.NDArray[np.float64],
    l_comb: npt.NDArray[np.float64],
    media: float,
    sigma: float,
) -> dict[str, float]:
    """Los cuatro estadísticos que se comparan.

    La distinción central está entre los dos Laplacianos, y no es
    cosmética. El núcleo de `L_norm` es `D^(1/2)·1`, pero el estado
    físicamente normal de una señal AMI es **constante**: todos los
    medidores cerca de 220 V. La constante no está en ese núcleo, así que
    `L_norm` penaliza el estado normal — medido, una señal plana de 220 V
    da entre 8 876 y 21 672 según la zona, contra ~286 que aporta el ruido.
    El Laplaciano combinatorio `L = D − A` sí tiene a la constante en su
    núcleo, y una señal plana le da cero exacto.

    Args:
        zone: Subgrafo zonal.
        x: Señal sobre los nodos.
        l_comb: Laplaciano combinatorio de la zona, precalculado.
        media: Media de la magnitud según el perfil.
        sigma: Dispersión espacial según el perfil.

    Returns:
        Los cuatro estadísticos.
    """
    centrada = x - float(x.mean())
    return {
        "umbral": float(np.abs(x - media).max() / sigma),
        "dirichlet_norm": float(dirichlet_energy(zone, x)),
        "dirichlet_norm_centrada": float(dirichlet_energy(zone, centrada)),
        "dirichlet_comb": float(x @ l_comb @ x),
        "residuo_local": float(np.abs(l_comb @ x / zone.degrees).max() / sigma),
    }


def _z_dos_muestras(x: npt.NDArray[np.float64], dentro: npt.NDArray[np.bool_], sigma: float) -> float:
    """Contraste entre un grupo y el resto de la zona, en unidades de σ.

    Args:
        x: Señal sobre los nodos.
        dentro: Máscara del grupo.
        sigma: Dispersión espacial de la magnitud.

    Returns:
        El estadístico z de dos muestras, en valor absoluto.
    """
    n_dentro = int(dentro.sum())
    n_fuera = int((~dentro).sum())
    if n_dentro == 0 or n_fuera == 0:
        return 0.0
    diferencia = float(x[dentro].mean() - x[~dentro].mean())
    error = sigma * np.sqrt(1.0 / n_dentro + 1.0 / n_fuera)
    return abs(diferencia) / float(error)


def oraculo(x: npt.NDArray[np.float64], afectados: npt.NDArray[np.bool_], sigma: float) -> float:
    """Techo de detectabilidad: el contraste sabiendo exactamente qué nodos.

    No es un detector —nadie conoce el grupo de antemano— sino la cota
    superior de lo que cualquier detector podría extraer. Si el oráculo es
    débil, no hay información y H3 no se sostiene con esta magnitud. Si es
    fuerte y los estadísticos globales son débiles, el problema es de forma
    del detector, no de información.

    Args:
        x: Señal sobre los nodos.
        afectados: Máscara verdadera del grupo afectado.
        sigma: Dispersión espacial.

    Returns:
        El contraste en unidades de σ.
    """
    return _z_dos_muestras(x, afectados, sigma)


def escaneo(
    zone: ZoneGraph,
    x: npt.NDArray[np.float64],
    vecindarios: tuple[npt.NDArray[np.bool_], ...],
    sigma: float,
) -> float:
    """Escaneo sobre vecindarios candidatos, sin conocer el grupo verdadero.

    Recorre las bolas de radio fijo centradas en cada nodo y devuelve el
    mayor contraste. Es la versión realizable del oráculo.

    Args:
        zone: Subgrafo zonal.
        x: Señal sobre los nodos.
        vecindarios: Máscaras precalculadas de las bolas candidatas.
        sigma: Dispersión espacial.

    Returns:
        El mayor contraste hallado, en unidades de σ.
    """
    del zone
    return max(_z_dos_muestras(x, mascara, sigma) for mascara in vecindarios)


ESTADISTICOS: Final = (
    "umbral",
    "dirichlet_norm",
    "dirichlet_norm_centrada",
    "dirichlet_comb",
    "residuo_local",
)


def _tasa_al_uno_por_ciento(
    positivos: npt.NDArray[np.float64], negativos: npt.NDArray[np.float64]
) -> float:
    """Fracción de eventos detectados con el umbral calibrado al 1 % de FPR.

    El AUC resume la curva entera; esto mide el punto de operación en que
    un monitor real trabajaría. Un estadístico puede tener AUC alto y ser
    inútil acá, que es exactamente lo que le pasa al umbral por medidor.

    Args:
        positivos: Estadístico en las realizaciones con evento.
        negativos: Estadístico en las realizaciones sin evento.

    Returns:
        Tasa de detección en `[0, 1]`.
    """
    corte = float(np.quantile(negativos, 0.99))
    return float((positivos > corte).mean())


def medir_deteccion(grafo: Any, perfil: Any, limites: Any) -> list[dict[str, Any]]:
    """Compara un umbral por medidor contra tres formas de medir rugosidad.

    Por cada configuración se generan `N_ENSAYOS` realizaciones
    independientes de ruido, y en cada una se calculan los estadísticos
    sobre la señal limpia y sobre la misma señal con el evento. El AUC de
    cada uno dice cuánta información hay disponible para separar evento de
    no-evento, sin comprometerse todavía con un detector.

    El umbral por medidor es el comparador de H3: lo que puede ver una
    regla que mire cada medidor por separado.

    Args:
        grafo: Grafo AMI.
        perfil: Perfil de señal.
        limites: Límites del esquema.

    Returns:
        Una fila por zona y configuración.
    """
    filas: list[dict[str, Any]] = []
    configuraciones = (
        ("individual", 0, SIGMA_INDIVIDUAL),
        ("colectiva_d1", 1, SIGMA_COLECTIVA),
        ("colectiva_d2", 2, SIGMA_COLECTIVA),
        ("colectiva_d3", 3, SIGMA_COLECTIVA),
    )

    for zona_nombre in grafo.zone_order:
        zona = grafo.zones[zona_nombre]
        p = perfil.get(MAGNITUD, device_type_of(zona.device_ids[0]))
        l_comb = laplacian(zona.adjacency)
        rng = np.random.default_rng([SEMILLA, 99])
        limpio = rng.normal(p.mean, p.sigma_spatial, size=(N_ENSAYOS, zona.n_meters))

        bolas = []
        for j in range(zona.n_meters):
            mascara = np.zeros(zona.n_meters, dtype=bool)
            mascara[list(k_hop(zona.adjacency, j, 1))] = True
            bolas.append(mascara)
        candidatos = tuple(bolas)

        negativos = {
            nombre: np.array(
                [
                    estadisticos(zona, fila, l_comb, p.mean, p.sigma_spatial)[nombre]
                    for fila in limpio
                ]
            )
            for nombre in ESTADISTICOS
        }
        negativos["escaneo"] = np.array(
            [escaneo(zona, fila, candidatos, p.sigma_spatial) for fila in limpio]
        )

        for etiqueta, depth, sigma in configuraciones:
            inyector = EventInjector(perfil, limites, seed=SEMILLA)
            con_evento = np.empty_like(limpio)
            afectados = np.zeros((N_ENSAYOS, zona.n_meters), dtype=bool)
            for i in range(N_ENSAYOS):
                senal, verdad = inyector.inject(
                    zona,
                    limpio[i],
                    [
                        CollectiveDeviationSpec(
                            magnitude=MAGNITUD,
                            depth=depth,
                            sigma_multiple=sigma,
                            seed_device_id=zona.device_ids[i % zona.n_meters],
                        )
                    ],
                    on_violation="scale",
                )
                con_evento[i] = senal[0]
                afectados[i, list(verdad.events[0].node_indices)] = True

            positivos = {
                nombre: np.array(
                    [
                        estadisticos(zona, fila, l_comb, p.mean, p.sigma_spatial)[nombre]
                        for fila in con_evento
                    ]
                )
                for nombre in ESTADISTICOS
            }

            positivos["escaneo"] = np.array(
                [escaneo(zona, fila, candidatos, p.sigma_spatial) for fila in con_evento]
            )
            oraculo_pos = np.array(
                [
                    oraculo(con_evento[i], afectados[i], p.sigma_spatial)
                    for i in range(N_ENSAYOS)
                ]
            )
            oraculo_neg = np.array(
                [oraculo(limpio[i], afectados[i], p.sigma_spatial) for i in range(N_ENSAYOS)]
            )

            # Umbral por medidor calibrado al 1 % de falsos positivos.
            corte = float(np.quantile(negativos["umbral"], 0.99))
            z_todos = np.abs(con_evento - p.mean) / p.sigma_spatial
            marcados = z_todos > corte

            filas.append(
                {
                    "zona": zona_nombre,
                    "configuracion": etiqueta,
                    "depth": depth,
                    "sigma_multiple": sigma,
                    "nodos_afectados": float(afectados[0].sum()),
                    **{
                        f"auc_{nombre}": _auc(positivos[nombre], negativos[nombre])
                        for nombre in (*ESTADISTICOS, "escaneo")
                    },
                    "auc_oraculo": _auc(oraculo_pos, oraculo_neg),
                    **{
                        f"deteccion_{nombre}": _tasa_al_uno_por_ciento(
                            positivos[nombre], negativos[nombre]
                        )
                        for nombre in ("umbral", "dirichlet_comb", "escaneo")
                    },
                    "deteccion_oraculo": _tasa_al_uno_por_ciento(oraculo_pos, oraculo_neg),
                    "umbral_corte_sigma": corte,
                    "recall_nodos_umbral": float(marcados[afectados].mean()),
                    "fpr_nodos_umbral": float(marcados[~afectados].mean()),
                }
            )
    return filas


# ───────────────────────────────────────────────────────── impresión


def _agrupar(filas: list[dict[str, Any]], clave: str, campos: tuple[str, ...]) -> dict[Any, dict[str, float]]:
    """Promedia campos numéricos agrupando por una clave.

    Args:
        filas: Filas a agrupar.
        clave: Campo por el que agrupar.
        campos: Campos numéricos a promediar.

    Returns:
        Promedios por valor de la clave.
    """
    salida: dict[Any, dict[str, float]] = {}
    for valor in sorted({f[clave] for f in filas}):
        grupo = [f for f in filas if f[clave] == valor]
        salida[valor] = {c: float(np.mean([f[c] for f in grupo])) for c in campos}
    return salida


def imprimir(forma: list[dict[str, Any]], firma: list[dict[str, Any]],
             deteccion: list[dict[str, Any]]) -> None:
    """Imprime las cuatro mediciones.

    Args:
        forma: Salida de `medir_forma_vs_magnitud`.
        firma: Salida de `medir_firma`.
        deteccion: Salida de `medir_deteccion`.
    """
    print("\n== 1. ¿LA FORMA DE LA FIRMA DEPENDE DE SU MAGNITUD? ==\n")
    print(f"{'sigma':>7} {'norma':>10} {'modo 0':>10} {'banda alta':>12} {'Rayleigh':>10}")
    for f in forma:
        print(
            f"{f['sigma_multiple']:>7.1f} {f['norma']:>10.4f} {f['modo_cero']:>9.2%} "
            f"{f['banda_alta']:>11.2%} {f['rayleigh']:>10.4f}"
        )

    print("\n== 2. DÓNDE CAE LA FIRMA, POR PROFUNDIDAD ==")
    print("   (promedio sobre las 150 semillas posibles, magnitud 1σ)\n")
    campos = ("n_nodos", "aristas_de_corte", "corte_por_nodo", "modo_cero",
              "banda_alta", "rayleigh")
    por_depth = _agrupar(firma, "depth", campos)
    print(
        f"{'depth':>6} {'nodos':>7} {'corte':>8} {'corte/nodo':>11} {'modo 0':>9} "
        f"{'banda alta':>12} {'Rayleigh':>10}"
    )
    for depth, d in por_depth.items():
        print(
            f"{depth:>6} {d['n_nodos']:>7.1f} {d['aristas_de_corte']:>8.1f} "
            f"{d['corte_por_nodo']:>11.2f} {d['modo_cero']:>8.2%} "
            f"{d['banda_alta']:>11.2%} {d['rayleigh']:>10.4f}"
        )

    print("\n  correlación entre el cociente de Rayleigh y corte/nodo:")
    r = float(np.corrcoef([f["corte_por_nodo"] for f in firma],
                          [f["rayleigh"] for f in firma])[0, 1])
    print(f"    r = {r:.4f}  sobre {len(firma)} eventos")

    print("\n== 3. COLECTIVA CONTRA INDIVIDUAL ==\n")
    individual = [f for f in firma if f["depth"] == 0]
    for etiqueta, filas in (
        ("individual (depth 0)", individual),
        ("colectiva (depth 1)", [f for f in firma if f["depth"] == 1]),
        ("colectiva (depth 2)", [f for f in firma if f["depth"] == 2]),
    ):
        alta = np.array([f["banda_alta"] for f in filas])
        ray = np.array([f["rayleigh"] for f in filas])
        print(
            f"  {etiqueta:<22} banda alta {alta.mean():6.2%} ± {alta.std():.2%}   "
            f"Rayleigh {ray.mean():.4f} ± {ray.std():.4f}"
        )

    print("\n== 4. UMBRAL POR MEDIDOR CONTRA TRES MEDIDAS DE RUGOSIDAD ==")
    print(f"   ({N_ENSAYOS} realizaciones por zona; AUC, 0,5 = indistinguible)\n")
    campos_d = ("nodos_afectados", *(f"auc_{n}" for n in ESTADISTICOS),
                "auc_escaneo", "auc_oraculo", "recall_nodos_umbral", "fpr_nodos_umbral",
                "deteccion_umbral", "deteccion_dirichlet_comb", "deteccion_escaneo",
                "deteccion_oraculo")
    por_config = _agrupar(deteccion, "configuracion", campos_d)
    print("  Estadisticos GLOBALES (un escalar por zona):\n")
    print(
        f"{'configuración':<16} {'nodos':>7} {'umbral':>9} {'E_D norm':>10} "
        f"{'E_D n.cent':>11} {'E_D comb':>10} {'resid.local':>12}"
    )
    for config, d in por_config.items():
        print(
            f"{config:<16} {d['nodos_afectados']:>7.1f} {d['auc_umbral']:>9.4f} "
            f"{d['auc_dirichlet_norm']:>10.4f} {d['auc_dirichlet_norm_centrada']:>11.4f} "
            f"{d['auc_dirichlet_comb']:>10.4f} {d['auc_residuo_local']:>12.4f}"
        )
    print("\n  Estadisticos LOCALIZADOS, y el techo de informacion (AUC):\n")
    print(f"{'configuración':<16} {'escaneo':>9} {'ORACULO':>9}")
    for config, d in por_config.items():
        print(f"{config:<16} {d['auc_escaneo']:>9.4f} {d['auc_oraculo']:>9.4f}")

    print("\n  TASA DE DETECCION al punto de operacion de 1 % de falsos positivos:\n")
    print(
        f"{'configuración':<16} {'umbral':>9} {'E_D comb':>10} {'escaneo':>9} "
        f"{'ORACULO':>9}"
    )
    for config, d in por_config.items():
        print(
            f"{config:<16} {d['deteccion_umbral']:>8.1%} {d['deteccion_dirichlet_comb']:>10.1%} "
            f"{d['deteccion_escaneo']:>9.1%} {d['deteccion_oraculo']:>9.1%}"
        )


def main() -> int:
    """Corre las cuatro mediciones.

    Returns:
        Código de salida del proceso.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args()

    grafo, perfil, limites = cargar()
    print(f"topologia   {TOPOLOGIA.relative_to(_REPO)}")
    print(f"perfil      {PERFIL.relative_to(_REPO)}")
    print(f"magnitud    {MAGNITUD}")
    print(f"medidores   {grafo.n_meters} en {grafo.n_zones} zonas")

    forma = medir_forma_vs_magnitud(grafo, perfil, limites)
    firma = medir_firma(grafo, perfil, limites)
    deteccion = medir_deteccion(grafo, perfil, limites)

    imprimir(forma, firma, deteccion)

    if args.json is not None:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(
                {
                    "semilla": SEMILLA,
                    "magnitud": MAGNITUD,
                    "n_ensayos": N_ENSAYOS,
                    "forma_vs_magnitud": forma,
                    "firma": firma,
                    "deteccion": deteccion,
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        print(f"\nJSON escrito en {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
