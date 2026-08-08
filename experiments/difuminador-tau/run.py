#!/usr/bin/env python3
"""Mide el Difuminador sobre el grafo AMI de los 150 medidores.

Cuatro mediciones, descritas en detalle en `RESULTADOS.md`:

1. **Signo del exponente.** Qué le pasa a la energía de alta frecuencia
   con `exp(−λ/(τ·λmax))` y con `exp(+λ/(τ·λmax))`, la formulación
   impresa en Aristizábal (2022).
2. **Barrido de τ.** Dónde está el codo y en qué rango el comportamiento
   es estable — el rango que después explora el Afinador.
3. **Límites de τ.** Que τ→0 colapsa al núcleo de `L_norm`, que es
   `D^(1/2)·1` y no la señal constante, y que τ→∞ es la identidad.
4. **Invariancia a la degeneración.** El mismo experimento de permutación
   del paso 3, sobre palermo, que tiene un subespacio propio de dimensión
   6 en λ=1,25.

No lee de PostgreSQL: parte de la instantánea versionada
`data/topologies/manizales_150.json`, que es lo que permite reproducir
estas cifras sin el cluster. Ver `data/topologies/README.md`.

Uso:

    python experiments/difuminador-tau/run.py
    python experiments/difuminador-tau/run.py --json results/medicion.json
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Final

import numpy as np
import numpy.typing as npt

_REPO_ROOT: Final = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "services" / "monitor-gsp" / "src"))

from urbia_monitor_gsp.graph.builder import build_ami_graph  # noqa: E402
from urbia_monitor_gsp.graph.filter import (  # noqa: E402
    _diffuse_published,
    band_cut_index,
    band_energy,
    diffuse,
    dirichlet_energy,
)
from urbia_monitor_gsp.graph.spectral import (  # noqa: E402
    degenerate_groups,
    fiedler_value,
    graph_fourier_basis,
    normalized_laplacian,
)
from urbia_monitor_gsp.graph.types import (  # noqa: E402
    AmiGraph,
    GraphConfig,
    MeterNode,
    ZoneGraph,
)

DEFAULT_TOPOLOGY: Final = _REPO_ROOT / "data" / "topologies" / "manizales_150.json"

SEED: Final = 20260807
"""Semilla base de la señal sintética. Fija: las cifras van a la tesis."""

BASELINE_KWH: Final = 10.0
"""Consumo base de todos los medidores, en kWh."""

NOISE_STD_KWH: Final = 0.3
"""Desviación del ruido gaussiano por medidor, en kWh."""

SPIKE_KWH: Final = 5.0
"""Magnitud de la anomalía inyectada en un único medidor, en kWh."""

TAU_GRID: Final = (0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 100.0)
SIGN_TAU: Final = 0.5
"""τ con que se compara el signo del exponente. Dentro del barrido."""

PERMUTATION_ZONE: Final = "palermo"
PERMUTATION_SEED: Final = 11


@dataclass(frozen=True, slots=True)
class ZoneSignal:
    """Señal sintética de una zona, con la anomalía ya inyectada."""

    zona: str
    values: npt.NDArray[np.float64]
    spike_index: int
    spike_device_id: str


def load_topology(path: Path) -> list[MeterNode]:
    """Lee la instantánea de medidores.

    Args:
        path: Ruta al JSON de topología.

    Returns:
        Los medidores como nodos del grafo.
    """
    datos = json.loads(path.read_text(encoding="utf-8"))
    return [
        MeterNode(
            device_id=m["device_id"],
            zona=m["zona"],
            lat=float(m["lat"]),
            lon=float(m["lon"]),
        )
        for m in datos["meters"]
    ]


def build_signal(zone: ZoneGraph, zone_index: int) -> ZoneSignal:
    """Genera la señal sintética de una zona.

    Consumo base uniforme, ruido gaussiano independiente por medidor y un
    pico en un único medidor elegido por la misma semilla. El medidor del
    pico no se elige a mano: eso permitiría acomodar el resultado.

    Args:
        zone: Subgrafo zonal.
        zone_index: Posición de la zona en el orden canónico, que entra en
            la semilla para que cada zona tenga su propia realización.

    Returns:
        La señal alineada al orden canónico de `zone.device_ids`.
    """
    rng = np.random.default_rng([SEED, zone_index])
    n = zone.n_meters
    valores = BASELINE_KWH + NOISE_STD_KWH * rng.standard_normal(n)
    indice = int(rng.integers(n))
    valores[indice] += SPIKE_KWH
    return ZoneSignal(
        zona=zone.zona,
        values=valores,
        spike_index=indice,
        spike_device_id=zone.device_ids[indice],
    )


def permuted_zone(zone: ZoneGraph, perm: npt.NDArray[np.int64]) -> ZoneGraph:
    """Reconstruye un subgrafo con los nodos en otro orden.

    Reordena la adyacencia y vuelve a diagonalizar desde cero, que es la
    única forma de que la base de Fourier se recalcule y pueda rotar
    dentro de los subespacios degenerados. Reordenar la base guardada no
    mediría nada.

    Args:
        zone: Subgrafo original.
        perm: Permutación de los índices de nodo.

    Returns:
        El mismo grafo con los nodos permutados.
    """
    ix = np.ix_(perm, perm)
    adyacencia = np.array(zone.adjacency)[ix]
    l_norm = normalized_laplacian(adyacencia)
    valores, vectores = graph_fourier_basis(l_norm)
    return ZoneGraph(
        zona=zone.zona,
        device_ids=tuple(zone.device_ids[i] for i in perm),
        coords_m=np.array(zone.coords_m)[perm],
        frame=zone.frame,
        distances_m=np.array(zone.distances_m)[ix],
        adjacency=adyacencia,
        degrees=np.array(zone.degrees)[perm],
        laplacian=np.array(zone.laplacian)[ix],
        laplacian_norm=l_norm,
        eigenvalues=valores,
        eigenvectors=vectores,
        stats=zone.stats,
    )


def measure_sign(graph: AmiGraph, signals: dict[str, ZoneSignal]) -> list[dict[str, Any]]:
    """Compara el exponente negativo contra el positivo de la fuente.

    Args:
        graph: Grafo AMI completo.
        signals: Señal sintética por zona.

    Returns:
        Una fila por zona con las energías antes y después de cada
        variante.
    """
    filas: list[dict[str, Any]] = []
    for zona in graph.zone_order:
        z = graph.zones[zona]
        x = signals[zona].values

        x_neg = diffuse(z, x, SIGN_TAU)
        with np.errstate(over="ignore", invalid="ignore"):
            x_pos = _diffuse_published(z, x, SIGN_TAU)

        banda = band_energy(z, x)
        banda_neg = band_energy(z, x_neg)
        banda_pos = band_energy(z, x_pos)

        filas.append(
            {
                "zona": zona,
                "n": z.n_meters,
                "dirichlet_original": dirichlet_energy(z, x),
                "dirichlet_negativo": dirichlet_energy(z, x_neg),
                "dirichlet_positivo": dirichlet_energy(z, x_pos),
                "banda_alta_original": banda.high,
                "banda_alta_negativo": banda_neg.high,
                "banda_alta_positivo": banda_pos.high,
                "fraccion_alta_original": banda.high_fraction,
                "fraccion_alta_negativo": banda_neg.high_fraction,
                "fraccion_alta_positivo": banda_pos.high_fraction,
                "corte_indice": banda.cut_index,
                "corte_lambda": banda.cut_eigenvalue,
            }
        )
    return filas


def measure_cuts(graph: AmiGraph) -> list[dict[str, Any]]:
    """Registra dónde cae el corte de bandas en cada zona.

    Args:
        graph: Grafo AMI completo.

    Returns:
        Una fila por zona con el corte, el λ del corte y la verificación
        de que no parte ningún subespacio degenerado.
    """
    filas: list[dict[str, Any]] = []
    for zona in graph.zone_order:
        z = graph.zones[zona]
        corte = band_cut_index(z.eigenvalues)
        grupos = degenerate_groups(z.eigenvalues)
        bordes = {g[0] for g in grupos}
        multiplicidad = next(len(g) for g in grupos if corte in g)
        filas.append(
            {
                "zona": zona,
                "n": z.n_meters,
                "lambda_max": float(z.eigenvalues[-1]),
                "objetivo": 0.5 * float(z.eigenvalues[-1]),
                "corte_indice": corte,
                "corte_lambda": float(z.eigenvalues[corte]),
                "es_borde_de_subespacio": corte in bordes,
                "multiplicidad_en_el_corte": multiplicidad,
                "max_multiplicidad_zona": max(len(g) for g in grupos),
            }
        )
    return filas


def measure_tau_sweep(
    graph: AmiGraph,
    signals: dict[str, ZoneSignal],
) -> list[dict[str, Any]]:
    """Barre τ y mide qué fracción de cada energía sobrevive al filtro.

    Args:
        graph: Grafo AMI completo.
        signals: Señal sintética por zona.

    Returns:
        Una fila por τ, con la retención por zona y sus agregados.
    """
    filas: list[dict[str, Any]] = []
    for tau in TAU_GRID:
        por_zona: dict[str, float] = {}
        retencion_alta: list[float] = []
        retencion_baja: list[float] = []

        for zona in graph.zone_order:
            z = graph.zones[zona]
            x = signals[zona].values
            x_f = diffuse(z, x, tau)

            e_original = dirichlet_energy(z, x)
            por_zona[zona] = dirichlet_energy(z, x_f) / e_original

            banda = band_energy(z, x)
            banda_f = band_energy(z, x_f)
            retencion_alta.append(banda_f.high / banda.high)
            retencion_baja.append(banda_f.low / banda.low)

        razones = np.array(list(por_zona.values()))
        filas.append(
            {
                "tau": tau,
                "por_zona": por_zona,
                "dirichlet_media": float(razones.mean()),
                "dirichlet_min": float(razones.min()),
                "dirichlet_max": float(razones.max()),
                "dispersion": float(razones.max() / razones.min()),
                "retencion_banda_alta_media": float(np.mean(retencion_alta)),
                "retencion_banda_baja_media": float(np.mean(retencion_baja)),
            }
        )

    _add_log_sensitivity(filas)
    return filas


def _add_log_sensitivity(filas: list[dict[str, Any]]) -> None:
    """Agrega la sensibilidad `|d ln(E_D) / d ln(τ)|` a cada fila del barrido.

    Es la elasticidad de la respuesta: cuántos por ciento cambia la
    energía retenida por cada por ciento de cambio en τ. Sirve para
    delimitar el rango estable sin elegirlo a ojo — donde vale mucho más
    que 1 el filtro es hipersensible a τ, y donde vale casi 0 τ ya no hace
    nada.

    Args:
        filas: Filas del barrido, en orden creciente de τ. Se modifican
            en el lugar.
    """
    log_tau = np.log(np.array([f["tau"] for f in filas]))
    log_e = np.log(np.array([f["dirichlet_media"] for f in filas]))
    pendiente = np.gradient(log_e, log_tau)
    for fila, valor in zip(filas, pendiente, strict=True):
        fila["sensibilidad_log"] = float(abs(valor))


def _interior_extrema(
    taus: npt.NDArray[np.float64],
    curva: npt.NDArray[np.float64],
) -> list[dict[str, Any]]:
    """Localiza máximos y mínimos locales de una curva muestreada.

    Args:
        taus: Abscisas, crecientes.
        curva: Valores en cada abscisa.

    Returns:
        Un registro por extremo interior, con su τ, su valor y su tipo.
    """
    extremos: list[dict[str, Any]] = []
    for i in range(1, curva.size - 1):
        if curva[i] > curva[i - 1] and curva[i] >= curva[i + 1]:
            extremos.append({"tipo": "maximo", "tau": float(taus[i]), "valor": float(curva[i])})
        elif curva[i] < curva[i - 1] and curva[i] <= curva[i + 1]:
            extremos.append({"tipo": "minimo", "tau": float(taus[i]), "valor": float(curva[i])})
    return extremos


def measure_knees(graph: AmiGraph, signals: dict[str, ZoneSignal]) -> dict[str, Any]:
    """Localiza los codos del barrido sobre una grilla fina.

    La grilla de reporte tiene diez puntos y sirve para leer la tabla,
    pero es demasiado gruesa para derivar: donde la curvatura es extrema
    —el régimen de colapso— la diferencia finita subestima la pendiente.
    Acá se repite el barrido sobre 81 puntos equiespaciados en log(τ) y se
    localizan tres cruces con criterios declarados de antemano:

    * **Codo inferior:** el τ más chico donde las seis zonas dejan de
      discrepar entre sí, `dispersión ≤ 1,5`. Por debajo, la misma τ
      produce resultados de órdenes de magnitud distintos según la zona.
    * **Codo superior:** el τ más grande donde el filtro todavía remueve
      al menos la mitad de la energía de Dirichlet.
    * **Sensibilidad:** `|d ln E_D / d ln τ|`, la elasticidad de la
      respuesta. Para τ chico la energía retenida queda dominada por el
      primer modo no nulo, `ratio ≈ c·exp(−2λ₁/(τ·λmax))`, de donde la
      sensibilidad vale `2λ₁/(τ·λmax)` y diverge cuando τ→0. Se compara
      la medida contra esa predicción, calculada con el λ₁ y el λmax de
      la zona que domina el promedio —la de Fiedler más chico, que es la
      que decae más lento y por lo tanto aporta casi toda la media.

    Args:
        graph: Grafo AMI completo.
        signals: Señal sintética por zona.

    Returns:
        La curva fina y los tres cruces.
    """
    taus = np.logspace(-2.0, 2.0, 81)
    medias: list[float] = []
    dispersiones: list[float] = []

    for tau in taus:
        razones = np.array(
            [
                dirichlet_energy(graph.zones[z], diffuse(graph.zones[z], signals[z].values, tau))
                / dirichlet_energy(graph.zones[z], signals[z].values)
                for z in graph.zone_order
            ]
        )
        medias.append(float(razones.mean()))
        dispersiones.append(float(razones.max() / razones.min()))

    media = np.array(medias)
    dispersion = np.array(dispersiones)
    sensibilidad = np.abs(np.gradient(np.log(media), np.log(taus)))

    concuerdan = np.flatnonzero(dispersion <= 1.5)
    remueve = np.flatnonzero(media <= 0.5)

    dominante = min(
        graph.zone_order,
        key=lambda z: float(fiedler_value(graph.zones[z].eigenvalues)),
    )
    z_dom = graph.zones[dominante]
    lambda_1 = float(fiedler_value(z_dom.eigenvalues))
    lambda_max = float(z_dom.eigenvalues[-1])

    return {
        "n_puntos": int(taus.size),
        "codo_inferior_tau": float(taus[concuerdan[0]]) if concuerdan.size else None,
        "codo_inferior_criterio": "dispersion entre zonas <= 1.5",
        "codo_superior_tau": float(taus[remueve[-1]]) if remueve.size else None,
        "codo_superior_criterio": "E_D retenida <= 0.5",
        "sensibilidad_extremos_interiores": _interior_extrema(taus, sensibilidad),
        "sensibilidad_en_tau_min": float(sensibilidad[0]),
        "sensibilidad_en_tau_max": float(sensibilidad[-1]),
        "zona_dominante": dominante,
        "zona_dominante_lambda_1": lambda_1,
        "zona_dominante_lambda_max": lambda_max,
        "sensibilidad_teorica_en_tau_min": 2.0 * lambda_1 / (float(taus[0]) * lambda_max),
        "curva": [
            {
                "tau": float(t),
                "dirichlet_media": float(m),
                "dispersion": float(d),
                "sensibilidad_log": float(s),
            }
            for t, m, d, s in zip(taus, media, dispersion, sensibilidad, strict=True)
        ],
    }


def measure_limits(graph: AmiGraph, signals: dict[str, ZoneSignal]) -> list[dict[str, Any]]:
    """Mide los dos límites: τ→0 colapsa al núcleo, τ→∞ es la identidad.

    El punto de interés está en el límite chico. El núcleo de `L_norm` es
    `D^(1/2)·1` —componente `i` igual a `√dᵢ`—, no la señal constante, que
    sí es el núcleo del Laplaciano combinatorio. Se mide el coseno de la
    señal filtrada contra los dos vectores para que la diferencia quede en
    números y no sólo en el argumento.

    Args:
        graph: Grafo AMI completo.
        signals: Señal sintética por zona.

    Returns:
        Una fila por zona con ambos límites.
    """
    tau_chico = 1e-3
    tau_grande = 1e3
    filas: list[dict[str, Any]] = []

    for zona in graph.zone_order:
        z = graph.zones[zona]
        x = signals[zona].values

        x_cero = diffuse(z, x, tau_chico)
        x_inf = diffuse(z, x, tau_grande)

        nucleo = np.sqrt(z.degrees)
        nucleo = nucleo / np.linalg.norm(nucleo)
        constante = np.ones(z.n_meters) / np.sqrt(z.n_meters)
        unitaria = x_cero / np.linalg.norm(x_cero)

        filas.append(
            {
                "zona": zona,
                "tau_chico": tau_chico,
                "coseno_con_sqrt_d": float(unitaria @ nucleo),
                "coseno_con_constante": float(unitaria @ constante),
                "grado_min": float(z.degrees.min()),
                "grado_max": float(z.degrees.max()),
                "dispersion_del_perfil": float(
                    x_cero.max() / x_cero.min(),
                ),
                "dirichlet_en_el_limite": dirichlet_energy(z, x_cero),
                "tau_grande": tau_grande,
                "error_relativo_identidad": float(
                    np.linalg.norm(x_inf - x) / np.linalg.norm(x),
                ),
            }
        )
    return filas


def measure_permutation(graph: AmiGraph) -> dict[str, Any]:
    """Verifica que el filtro no dependa de la base en subespacios degenerados.

    Args:
        graph: Grafo AMI completo.

    Returns:
        Las diferencias máximas entre la corrida original y la permutada.
    """
    z = graph.zones[PERMUTATION_ZONE]
    indice = graph.zone_order.index(PERMUTATION_ZONE)
    x = build_signal(z, indice).values

    rng = np.random.default_rng(PERMUTATION_SEED)
    perm = rng.permutation(z.n_meters)
    inversa = np.argsort(perm)
    z_perm = permuted_zone(z, perm)

    x_f = diffuse(z, x, SIGN_TAU)
    x_f_perm = diffuse(z_perm, x[perm], SIGN_TAU)

    banda = band_energy(z, x_f)
    banda_perm = band_energy(z_perm, x_f_perm)
    grupos = degenerate_groups(z.eigenvalues)

    return {
        "zona": PERMUTATION_ZONE,
        "n": z.n_meters,
        "max_multiplicidad": max(len(g) for g in grupos),
        "lambda_de_la_multiplicidad": float(
            z.eigenvalues[max(grupos, key=len)[0]],
        ),
        "diff_senal_filtrada": float(np.abs(x_f - x_f_perm[inversa]).max()),
        "diff_dirichlet": abs(dirichlet_energy(z, x_f) - dirichlet_energy(z_perm, x_f_perm)),
        "diff_banda_alta": abs(banda.high - banda_perm.high),
        "diff_banda_baja": abs(banda.low - banda_perm.low),
        "mismo_corte_indice": banda.cut_index == banda_perm.cut_index,
        "diff_corte_lambda": abs(banda.cut_eigenvalue - banda_perm.cut_eigenvalue),
        "diff_coeficiente_modo_suelto": float(
            np.abs(
                np.abs(z.eigenvectors.T @ x) - np.abs(z_perm.eigenvectors.T @ x[perm]),
            ).max()
        ),
    }


def _print_sign(filas: list[dict[str, Any]]) -> None:
    """Imprime la tabla de comparación de signos.

    Args:
        filas: Salida de `measure_sign`.
    """
    print(f"\n== 1. SIGNO DEL EXPONENTE (tau={SIGN_TAU}) ==\n")
    print(
        f"{'zona':<14} {'E_D orig':>10} {'E_D neg':>10} {'razon':>9} "
        f"{'E_D pos':>11} {'razon':>9} {'alta neg':>9} {'alta pos':>9}"
    )
    for f in filas:
        print(
            f"{f['zona']:<14} {f['dirichlet_original']:>10.4f} "
            f"{f['dirichlet_negativo']:>10.4f} "
            f"{f['dirichlet_negativo'] / f['dirichlet_original']:>9.2e} "
            f"{f['dirichlet_positivo']:>11.4f} "
            f"{f['dirichlet_positivo'] / f['dirichlet_original']:>9.2e} "
            f"{f['banda_alta_negativo'] / f['banda_alta_original']:>9.2e} "
            f"{f['banda_alta_positivo'] / f['banda_alta_original']:>9.2e}"
        )


def _print_cuts(filas: list[dict[str, Any]]) -> None:
    """Imprime dónde quedó el corte de bandas por zona.

    Args:
        filas: Salida de `measure_cuts`.
    """
    print("\n== 2. CORTE DE BANDAS (target_ratio=0.5) ==\n")
    print(
        f"{'zona':<14} {'n':>3} {'lambda_max':>11} {'objetivo':>9} {'corte':>6} "
        f"{'lambda':>9} {'borde':>6} {'mult_max':>9}"
    )
    for f in filas:
        print(
            f"{f['zona']:<14} {f['n']:>3} {f['lambda_max']:>11.6f} {f['objetivo']:>9.4f} "
            f"{f['corte_indice']:>6} {f['corte_lambda']:>9.4f} "
            f"{f['es_borde_de_subespacio']!s:>6} {f['max_multiplicidad_zona']:>9}"
        )


def _print_sweep(filas: list[dict[str, Any]], zonas: tuple[str, ...]) -> None:
    """Imprime el barrido de τ.

    Args:
        filas: Salida de `measure_tau_sweep`.
        zonas: Orden canónico de las zonas.
    """
    print("\n== 3. BARRIDO DE TAU: fraccion de E_D que sobrevive al filtro ==\n")
    encabezado = " ".join(f"{z[:9]:>10}" for z in zonas)
    print(
        f"{'tau':>7} {encabezado} {'media':>10} {'disp':>7} {'sens':>7} "
        f"{'ret_alta':>9} {'ret_baja':>9}"
    )
    for f in filas:
        celdas = " ".join(f"{f['por_zona'][z]:>10.3e}" for z in zonas)
        print(
            f"{f['tau']:>7g} {celdas} {f['dirichlet_media']:>10.3e} "
            f"{f['dispersion']:>7.2f} {f['sensibilidad_log']:>7.2f} "
            f"{f['retencion_banda_alta_media']:>9.2e} "
            f"{f['retencion_banda_baja_media']:>9.3f}"
        )


def _print_knees(datos: dict[str, Any]) -> None:
    """Imprime los codos localizados sobre la grilla fina.

    Args:
        datos: Salida de `measure_knees`.
    """
    print(f"\n== 3b. CODOS (grilla fina de {datos['n_puntos']} puntos en log tau) ==\n")
    print(
        f"  codo inferior          tau = {datos['codo_inferior_tau']:.4f}   "
        f"({datos['codo_inferior_criterio']})"
    )
    print(
        f"  codo superior          tau = {datos['codo_superior_tau']:.4f}   "
        f"({datos['codo_superior_criterio']})"
    )
    print("\n  sensibilidad |d ln E_D / d ln tau|:")
    for extremo in datos["sensibilidad_extremos_interiores"]:
        print(
            f"    {extremo['tipo']} local  tau = {extremo['tau']:.4f}   "
            f"valor {extremo['valor']:.3f}"
        )
    print(
        f"    en tau=0.01   medida {datos['sensibilidad_en_tau_min']:.2f}   "
        f"teorica 2*lambda_1/(tau*lambda_max) = "
        f"{datos['sensibilidad_teorica_en_tau_min']:.2f}   "
        f"(zona {datos['zona_dominante']}, lambda_1={datos['zona_dominante_lambda_1']:.4f}, "
        f"lambda_max={datos['zona_dominante_lambda_max']:.4f})"
    )
    print(f"    en tau=100    medida {datos['sensibilidad_en_tau_max']:.3f}")


def _print_limits(filas: list[dict[str, Any]]) -> None:
    """Imprime los dos límites de τ.

    Args:
        filas: Salida de `measure_limits`.
    """
    print("\n== 4. LIMITES DE TAU (tau=1e-3 y tau=1e3) ==\n")
    print(
        f"{'zona':<14} {'cos(x_f, sqrt d)':>17} {'cos(x_f, 1)':>12} {'d_min':>6} "
        f"{'d_max':>6} {'max/min x_f':>12} {'E_D':>10} {'err ident':>10}"
    )
    for f in filas:
        print(
            f"{f['zona']:<14} {f['coseno_con_sqrt_d']:>17.12f} "
            f"{f['coseno_con_constante']:>12.6f} {f['grado_min']:>6.0f} "
            f"{f['grado_max']:>6.0f} {f['dispersion_del_perfil']:>12.4f} "
            f"{f['dirichlet_en_el_limite']:>10.2e} "
            f"{f['error_relativo_identidad']:>10.2e}"
        )


def _print_permutation(datos: dict[str, Any]) -> None:
    """Imprime el resultado del experimento de permutación.

    Args:
        datos: Salida de `measure_permutation`.
    """
    print(
        f"\n== 5. INVARIANCIA A LA DEGENERACION ({datos['zona']}, "
        f"multiplicidad {datos['max_multiplicidad']} en "
        f"lambda={datos['lambda_de_la_multiplicidad']:.6f}) ==\n"
    )
    for clave, etiqueta in (
        ("diff_senal_filtrada", "senal filtrada x_f"),
        ("diff_dirichlet", "energia de Dirichlet"),
        ("diff_banda_alta", "banda alta"),
        ("diff_banda_baja", "banda baja"),
        ("diff_corte_lambda", "lambda del corte"),
        ("diff_coeficiente_modo_suelto", "|x_hat[k]| de un modo suelto"),
    ):
        print(f"  {etiqueta:<30} {datos[clave]:.3e}")
    print(f"  {'mismo indice de corte':<30} {datos['mismo_corte_indice']}")


def main() -> int:
    """Corre las cuatro mediciones e imprime las tablas.

    Returns:
        Código de salida del proceso.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--topology", type=Path, default=DEFAULT_TOPOLOGY)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args()

    meters = load_topology(args.topology)
    config = GraphConfig()
    graph = build_ami_graph(meters, config)

    print(f"topologia   {args.topology.relative_to(_REPO_ROOT)}")
    print(f"medidores   {graph.n_meters} en {graph.n_zones} zonas")
    print(f"grafo       k-NN k={config.k} {config.knn_mode}, pesos {config.weighting}")
    print(
        f"senal       base {BASELINE_KWH} kWh + N(0, {NOISE_STD_KWH}) "
        f"+ pico {SPIKE_KWH} kWh, semilla {SEED}"
    )

    signals = {zona: build_signal(graph.zones[zona], i) for i, zona in enumerate(graph.zone_order)}
    print("\npico inyectado por zona:")
    for zona in graph.zone_order:
        s = signals[zona]
        print(f"  {zona:<14} indice {s.spike_index:>3}  {s.spike_device_id}")

    sign = measure_sign(graph, signals)
    cuts = measure_cuts(graph)
    sweep = measure_tau_sweep(graph, signals)
    knees = measure_knees(graph, signals)
    limits = measure_limits(graph, signals)
    permutation = measure_permutation(graph)

    _print_sign(sign)
    _print_cuts(cuts)
    _print_sweep(sweep, graph.zone_order)
    _print_knees(knees)
    _print_limits(limits)
    _print_permutation(permutation)

    if args.json is not None:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(
                {
                    "topologia": str(args.topology.relative_to(_REPO_ROOT)),
                    "config": asdict(config),
                    "semilla": SEED,
                    "senal": {
                        "base_kwh": BASELINE_KWH,
                        "ruido_std_kwh": NOISE_STD_KWH,
                        "pico_kwh": SPIKE_KWH,
                        "por_zona": {
                            z: {
                                "indice": s.spike_index,
                                "device_id": s.spike_device_id,
                            }
                            for z, s in signals.items()
                        },
                    },
                    "signo": sign,
                    "cortes": cuts,
                    "barrido_tau": sweep,
                    "codos": knees,
                    "limites": limits,
                    "permutacion": permutation,
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
