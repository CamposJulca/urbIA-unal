"""Escaneo local: el estadístico que las mediciones dejaron validado.

## Por qué local y no global

Medido en `experiments/firma-espectral/`: **ningún escalar que resuma la
zona entera separa un evento colectivo del ruido.** La energía de Dirichlet
—normalizada, centrada o combinatoria— y el residuo local agregado dan AUC
entre 0,48 y 0,57, es decir azar. La razón es de dilución: un evento a
profundidad 2 toca unas 9 aristas de corte de las 61 a 72 que tiene una
zona, y un estadístico global integra el ruido de todas.

El escaneo, en cambio, contrasta cada vecindario contra el resto de su zona
y se queda con el mayor desacuerdo. Sobre el mismo material da 0,73 a 0,81
de AUC, y al 1 % de falsos positivos detecta el 18,9 % contra el 6,7 % del
umbral por medidor —cifras del instrumento de aquella medición, radio 1
sobre un instante, no del detector que salió después—.

## El estadístico

Para un grupo `S` y su complemento, sobre la señal ya promediada en la
ventana:

    z(S) = |media(x[S]) − media(x[Sᶜ])| / (σ_eff · √(1/|S| + 1/|Sᶜ|))

con `σ_eff = σ_espacial / √N`. Es un contraste de dos muestras, y el
detector se queda con `max_S z(S)` sobre las bolas candidatas.

**Es invariante a sumar una constante a toda la señal**, porque las dos
medias se corren igual y la diferencia no cambia. Por eso el escaneo no
necesita centrado de ninguna clase: el nivel medio de 220 V, que arruina
cualquier medida de rugosidad basada en `L_norm`, acá se cancela solo.
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

from ..graph.types import ZoneGraph
from .types import DetectorError


def k_hop_indices(
    adjacency: npt.NDArray[np.float64],
    seed_index: int,
    depth: int,
) -> tuple[int, ...]:
    """Nodos a lo sumo a `depth` saltos de la semilla.

    Recorrido en anchura sobre la adyacencia. Sólo mira si la arista
    existe: los pesos no cambian quién es vecino de quién.

    Args:
        adjacency: Matriz `(n, n)` simétrica.
        seed_index: Nodo central.
        depth: Saltos máximos. `0` devuelve sólo la semilla.

    Returns:
        Posiciones del vecindario, en orden creciente.
    """
    vistos = {seed_index}
    frontera = [seed_index]
    for _ in range(depth):
        siguiente: list[int] = []
        for nodo in frontera:
            for vecino in np.flatnonzero(adjacency[nodo] > 0.0):
                posicion = int(vecino)
                if posicion not in vistos:
                    vistos.add(posicion)
                    siguiente.append(posicion)
        if not siguiente:
            break
        frontera = siguiente
    return tuple(sorted(vistos))


def candidate_balls(
    zone: ZoneGraph,
    radii: tuple[int, ...],
) -> tuple[npt.NDArray[np.float64], tuple[tuple[int, int], ...]]:
    """Bolas candidatas del escaneo, deduplicadas.

    Se descartan las bolas que cubren la zona entera: sin complemento no
    hay contraste que calcular, y además un grupo que abarca todo es un
    modo común, no una discordancia local.

    Args:
        zone: Subgrafo zonal.
        radii: Radios a escanear.

    Returns:
        Par `(máscaras, metadatos)`. Las máscaras son `(B, n)` con 1 donde
        el nodo pertenece; los metadatos son `(centro, radio)` por fila.

    Raises:
        DetectorError: Si no queda ninguna bola candidata, lo que ocurre
            en grafos demasiado chicos para el radio pedido.
    """
    filas: list[npt.NDArray[np.float64]] = []
    metadatos: list[tuple[int, int]] = []
    vistas: set[tuple[int, ...]] = set()

    for radio in sorted(set(radii)):
        for centro in range(zone.n_meters):
            nodos = k_hop_indices(zone.adjacency, centro, radio)
            if len(nodos) >= zone.n_meters or nodos in vistas:
                continue
            vistas.add(nodos)
            fila = np.zeros(zone.n_meters, dtype=np.float64)
            fila[list(nodos)] = 1.0
            filas.append(fila)
            metadatos.append((centro, radio))

    if not filas:
        raise DetectorError(
            f"la zona '{zone.zona}' con {zone.n_meters} medidores no admite ninguna "
            f"bola candidata para los radios {radii}: todas cubren la zona entera y "
            f"no dejan complemento contra el cual contrastar"
        )
    return np.vstack(filas), tuple(metadatos)


def contrasts(
    values: npt.NDArray[np.float64],
    masks: npt.NDArray[np.float64],
    sigma_eff: float,
) -> npt.NDArray[np.float64]:
    """Contraste de dos muestras entre cada grupo y su complemento.

    Vectorizado sobre realizaciones y sobre grupos: una sola multiplicación
    de matrices resuelve todas las sumas por grupo.

    Args:
        values: Señal ya promediada, `(R, n)` o `(n,)`.
        masks: Máscaras de los grupos, `(B, n)`.
        sigma_eff: Dispersión efectiva tras promediar la ventana.

    Returns:
        Matriz `(R, B)` de contrastes en unidades de σ.

    Raises:
        DetectorError: Si `sigma_eff` no es finita y positiva, o si la
            señal no encaja con las máscaras.
    """
    if not np.isfinite(sigma_eff) or sigma_eff <= 0.0:
        raise DetectorError(
            f"sigma_eff debe ser finita y > 0, recibida {sigma_eff}: sin dispersión "
            f"no hay escala contra la cual medir un contraste"
        )
    x = np.atleast_2d(np.asarray(values, dtype=np.float64))
    if x.shape[1] != masks.shape[1]:
        raise DetectorError(f"la señal tiene {x.shape[1]} nodos y las máscaras {masks.shape[1]}")

    n = x.shape[1]
    dentro = masks.sum(axis=1)
    fuera = n - dentro
    suma_dentro = x @ masks.T
    suma_total = x.sum(axis=1, keepdims=True)
    media_dentro = suma_dentro / dentro
    media_fuera = (suma_total - suma_dentro) / fuera
    error = sigma_eff * np.sqrt(1.0 / dentro + 1.0 / fuera)
    return np.asarray(np.abs(media_dentro - media_fuera) / error, dtype=np.float64)
