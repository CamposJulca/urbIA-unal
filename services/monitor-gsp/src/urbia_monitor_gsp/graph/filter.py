"""Difuminador: filtro paso-bajo espectral sobre el grafo AMI.

Implementa el componente que Aristizábal (2022) llama *Difuminador*: un
filtro que atenúa las componentes de alta frecuencia de una señal definida
sobre los nodos del grafo, dejando pasar lo que varía suavemente entre
vecinos. Alta frecuencia en un grafo significa desacuerdo entre nodos
adyacentes; atenuarla es lo que separa una fluctuación local del
comportamiento compartido por la vecindad.

    g(λ) = exp( −λ / (τ · λmax) )
    x_filtrada = U · ( g(λ) ⊙ (Uᵀ · x) )

## El signo del exponente

**Qué dice la fuente.** La formulación publicada en la tesis de
Aristizábal (2022, Capítulo 3) escribe el exponente **positivo**,
`exp(+λ/(τ·λmax))`.

**Qué implementa UrbIA.** El exponente **negativo**, `exp(−λ/(τ·λmax))`.

**Por qué.** `g` debe decrecer con λ para que el filtro sea paso-bajo. Con
el exponente positivo `g` crece con λ: el modo de frecuencia más alta
queda multiplicado por `exp(1/τ)` mientras el modo constante queda
multiplicado por 1, de modo que el filtro **amplifica** exactamente lo que
un paso-bajo tiene que atenuar. No es una convención de signo alternativa
ni una parametrización distinta de la misma familia: invierte el sentido
del operador. Para τ chico además desborda —`exp(1/0,01)` ya vale 2,7e43 y
`exp(1/0,001)` es infinito—, así que ni siquiera produce un número con el
que seguir trabajando.

Por eso el signo no es configurable. La API pública lo fija en negativo y
no acepta otra cosa; la variante con exponente positivo existe únicamente
como `_published_response` y `_diffuse_published`, privadas, para que el
experimento de `experiments/difuminador-tau/` pueda medir la diferencia y
para que los tests puedan afirmarla. Exponerla como opción la volvería
elegible, y no hay ningún caso en que sea la elección correcta.

## Qué hace τ

`λmax` normaliza el espectro, así que τ es adimensional y comparable entre
zonas de distinto tamaño y densidad: `g(λmax) = exp(−1/τ)` sin importar el
grafo. Los dos extremos:

* **τ → ∞:** `g → 1` en todo el espectro y el filtro tiende a la
  identidad. No difumina nada.
* **τ → 0:** `g → 0` para todo λ > 0 y `g(0) = 1`. El filtro tiende a la
  **proyección sobre el núcleo de `L_norm`**.

Sobre ese límite conviene ser preciso, porque se lee mal con facilidad: el
núcleo de `L_norm` **no** es la señal constante. Es `D^(1/2)·1`, el vector
cuya componente `i` vale `√dᵢ`, normalizado. La confusión viene del
Laplaciano combinatorio `L = D − A`, donde el núcleo sí es la constante.
Al normalizar, `L_norm = D^(-1/2)·L·D^(-1/2)`, el cambio de variable
`y = D^(1/2)x` arrastra el núcleo con él. Consecuencia concreta: con τ→0
la señal filtrada **no** converge al promedio de los nodos, sino a un
perfil proporcional a `√dᵢ` — los nodos de mayor grado quedan con valor
más alto que los de menor grado, aunque la señal de entrada fuera
perfectamente plana. Quien espere ver un promedio y vea un perfil creciente
con el grado no está mirando un error: está mirando el núcleo correcto del
operador que eligió.

## Cómo se mide el resultado

**Energía de Dirichlet, `E_D(x) = xᵀ·L_norm·x`, como métrica principal.**
Equivale a `Σ_k λ_k · x̂_k²` y también a `Σ_ij w_ij·(xᵢ/√dᵢ − xⱼ/√dⱼ)²`:
mide cuánto desacuerdo hay entre vecinos. La primera igualdad la hace
interpretable como energía de alta frecuencia; la segunda la hace
calculable sin tocar la base de Fourier. Es inmune a la degeneración de
autovalores que documenta `spectral` —multiplicidad 6 en λ=1,25 en
palermo—, porque no depende de qué base devolvió `eigh` dentro de un
subespacio propio.

**Reparto por bandas como lectura secundaria**, pensada para el notebook:
partir el espectro en baja y alta y comparar la energía a cada lado. El
corte **no** va fijo en λmax/2. Se elige entre los bordes de los
subespacios propios que expone `degenerate_groups`, tomando el más cercano
al objetivo `target_ratio·λmax`. Un corte fijo puede caer en mitad de un
subespacio degenerado y repartir entre las dos bandas una energía que no
tiene reparto definido —depende de la base arbitraria—, que es exactamente
el defecto de la ventana abrupta que E6 descartó.

## Por qué el filtro es reproducible pese a la degeneración

`g` depende sólo de λ, así que es constante dentro de cada subespacio
propio. Si `Q` es una rotación de la base dentro de un subespacio
degenerado, `U·Q·diag(g)·Qᵀ·Uᵀ = U·diag(g)·Uᵀ`, porque `diag(g)` es un
múltiplo de la identidad en ese bloque y conmuta con `Q`. Dicho de otro
modo: el operador es `exp(−L_norm/(τ·λmax))`, una función matricial de
`L_norm`, y no depende de la base con que se lo calcule. La arbitrariedad
que `spectral` midió sobre coeficientes individuales no lo toca. El
experimento lo verifica igual, con el mismo experimento de permutación.

## Cifras medidas

Todo lo que sigue está medido sobre el grafo real de los 150 medidores
—k-NN k=4 simetrizado por unión, pesos binarios, seis subgrafos zonales,
sin puente inter-zona— con una señal sintética de semilla fija: base
10 kWh, ruido gaussiano de desviación 0,3 y un pico de +5 kWh en un
medidor sorteado. El procedimiento completo, los parámetros exactos y las
tablas por zona están en `experiments/difuminador-tau/RESULTADOS.md`; el
script que las produce es `run.py` de ese mismo directorio.

**Signo del exponente**, τ=0,5, rango sobre las seis zonas:

    exponente negativo    E_D queda en 4,9 % a 7,0 % del valor original
                          la banda alta queda en 3,7 % a 5,4 % de la suya
    exponente positivo    E_D sube a 24 a 38 veces el valor original
                          la banda alta sube a 24 a 38 veces la suya

Las seis zonas se comportan igual; ninguna invierte el sentido. La
fracción de energía en alta frecuencia pasa de ~1 % a ~30 % con el
exponente positivo: concentra la señal justo en lo que había que remover.

**Barrido de τ**, fracción de `E_D` que sobrevive al filtro, promedio de
las seis zonas y dispersión entre la zona que más retiene y la que menos:

    τ = 0,01     1,1e-06     dispersión 34073
    τ = 0,05     5,7e-04     dispersión  9,49
    τ = 0,10     2,2e-03     dispersión  6,87
    τ = 0,25     1,2e-02     dispersión  2,58
    τ = 0,50     6,0e-02     dispersión  1,42
    τ = 1,00     2,2e-01     dispersión  1,17
    τ = 2,00     4,6e-01     dispersión  1,09
    τ = 5,00     7,3e-01     dispersión  1,04
    τ = 10,0     8,5e-01     dispersión  1,02
    τ = 100      9,8e-01     dispersión  1,00

**El rango estable es τ ∈ [0,45, 2,24]**, con los codos localizados sobre
una grilla de 81 puntos en log(τ) y criterios fijados de antemano: por
abajo, donde las seis zonas dejan de discrepar entre sí (dispersión ≤
1,5); por arriba, donde el filtro todavía remueve al menos la mitad de
`E_D`. Dentro de ese rango la sensibilidad `|d ln E_D / d ln τ|` se
mantiene entre 0,687 y 2,375: un ajuste incremental de τ produce un cambio
proporcional en la salida, que es la condición para que el Afinador pueda
ajustarla por realimentación. Fuera, las dos puntas son degeneradas —por
debajo de τ≈0,25 el resultado es indistinguible del núcleo, por encima de
τ≈5 el filtro no actúa— y no hay nada que ajustar.

**Límite τ→0**, con τ=1e-3, que es donde se ve que el núcleo no es la
constante:

    cos(x_filtrada, √d)          1,000000000000 en las seis zonas
    cos(x_filtrada, 1)           0,992 a 0,996
    max/min de x_filtrada        √(d_max/d_min) exacto: 1,4142 en centro
                                 (grados 4 a 8), 1,5000 en la_enea (4 a 9)
    E_D en el límite             ~1e-14, cero numérico

Con τ=1e3 la señal filtrada difiere de la original en menos de 1,1e-04 en
norma relativa: la identidad.

**Invariancia a la degeneración**, palermo, subespacio de dimensión 6 en
λ=1,25, permutando el orden de los nodos y rediagonalizando desde cero:

    señal filtrada x_filtrada         2,7e-14
    energía de Dirichlet              1,4e-13
    reparto por bandas                6,6e-14 (alta), 1,4e-12 (baja)
    índice y λ del corte              idénticos
    módulo de x̂_k de un modo suelto   1,3e-01

La última fila es la que da sentido a las demás: sigue habiendo rotación
de base dentro del subespacio degenerado, y las cantidades de arriba son
invariantes de todos modos.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
import numpy.typing as npt

from .spectral import degenerate_groups
from .types import InvalidFilterParameterError, ZoneGraph

_NEGATIVE_EXPONENT: Final = -1.0
"""Signo del exponente de la respuesta espectral. Ver el encabezado."""

_PUBLISHED_EXPONENT: Final = 1.0
"""Signo del exponente tal como está impreso en Aristizábal (2022)."""

DEFAULT_TAU: Final = 0.5
"""τ por defecto, dentro del rango estable medido `[0,45, 2,24]`.

No es un valor óptimo: es un punto de partida razonable en la zona donde
el filtro se comporta de forma monótona y suave. El Afinador es quien lo
ajusta con RL.
"""

DEFAULT_BAND_TARGET_RATIO: Final = 0.5
"""Fracción de λmax donde se busca el corte entre banda baja y alta.

Es un objetivo, no el corte: `band_cut_index` lo ajusta al borde de
subespacio propio más cercano.
"""


@dataclass(frozen=True, slots=True)
class BandEnergy:
    """Reparto de la energía espectral de una señal entre dos bandas.

    Lectura secundaria del efecto del filtro, complementaria a la energía
    de Dirichlet. El corte cae siempre en un borde de subespacio propio,
    de modo que ninguna banda parte un subespacio degenerado por la mitad.

    Attributes:
        low: Energía `Σ x̂_k²` sobre los modos por debajo del corte.
        high: Energía `Σ x̂_k²` sobre los modos desde el corte en adelante.
        total: Energía total, `low + high`. Igual a `‖x‖²` porque la base
            es ortonormal.
        cut_index: Primer índice de la banda alta.
        cut_eigenvalue: Autovalor en `cut_index`, el λ donde quedó el corte.
        high_fraction: `high / total`. Vale 0 si la energía total es nula.
    """

    low: float
    high: float
    total: float
    cut_index: int
    cut_eigenvalue: float
    high_fraction: float


def _validate_tau(tau: float) -> float:
    """Valida el parámetro de difusión.

    Args:
        tau: Parámetro de difusión.

    Returns:
        τ como float.

    Raises:
        InvalidFilterParameterError: Si τ no es finito o no es positivo.
    """
    valor = float(tau)
    if not np.isfinite(valor):
        raise InvalidFilterParameterError(f"τ debe ser finito, recibido {tau}")
    if valor <= 0.0:
        raise InvalidFilterParameterError(
            f"τ debe ser > 0, recibido {valor}: τ divide al exponente y en el límite "
            f"τ→0 el filtro degenera en la proyección sobre el núcleo de L_norm"
        )
    return valor


def _resolve_lambda_max(
    eigenvalues: npt.NDArray[np.float64],
    lambda_max: float | None,
) -> float:
    """Determina el λmax con que se normaliza el exponente.

    Args:
        eigenvalues: Autovalores del Laplaciano normalizado.
        lambda_max: Valor explícito, o `None` para tomarlo del espectro.

    Returns:
        λmax positivo.

    Raises:
        InvalidFilterParameterError: Si el espectro está vacío o λmax no
            es finito y positivo.
    """
    if eigenvalues.size == 0:
        raise InvalidFilterParameterError("el espectro está vacío: no hay λmax que normalice")
    valor = float(np.abs(eigenvalues).max()) if lambda_max is None else float(lambda_max)
    if not np.isfinite(valor) or valor <= 0.0:
        raise InvalidFilterParameterError(
            f"λmax debe ser finito y > 0, recibido {valor}: un grafo sin aristas no "
            f"tiene frecuencias que atenuar"
        )
    return valor


def _response(
    eigenvalues: npt.ArrayLike,
    tau: float,
    lambda_max: float | None,
    sign: float,
) -> npt.NDArray[np.float64]:
    """Núcleo compartido de la respuesta espectral `exp(sign·λ/(τ·λmax))`.

    Privada a propósito: `sign` es el parámetro que no debe existir en
    ninguna firma pública. Ver el encabezado del módulo.

    Args:
        eigenvalues: Autovalores del Laplaciano normalizado.
        tau: Parámetro de difusión, positivo.
        lambda_max: Normalizador. Si es `None` sale del espectro.
        sign: `-1` para el filtro paso-bajo, `+1` para la formulación
            impresa en la fuente.

    Returns:
        Vector `g(λ)` del mismo largo que `eigenvalues`.

    Raises:
        InvalidFilterParameterError: Si τ o λmax son inválidos.
    """
    valores = np.asarray(eigenvalues, dtype=np.float64)
    t = _validate_tau(tau)
    escala = _resolve_lambda_max(valores, lambda_max)
    return np.asarray(np.exp(sign * valores / (t * escala)), dtype=np.float64)


def low_pass_response(
    eigenvalues: npt.ArrayLike,
    tau: float = DEFAULT_TAU,
    *,
    lambda_max: float | None = None,
) -> npt.NDArray[np.float64]:
    """Respuesta en frecuencia del Difuminador, `g(λ) = exp(−λ/(τ·λmax))`.

    El signo del exponente es negativo y no es configurable; el encabezado
    del módulo explica por qué la fuente lo escribe al revés.

    Args:
        eigenvalues: Autovalores del Laplaciano normalizado, típicamente
            `zone.eigenvalues`.
        tau: Parámetro de difusión. Chico difumina fuerte, grande deja
            pasar. El rango estable medido es `[0,45, 2,24]`.
        lambda_max: Normalizador del exponente. Si es `None` se toma el
            mayor autovalor en magnitud. Pasarlo explícito sirve para
            comparar zonas con el mismo normalizador.

    Returns:
        Vector `g(λ)` con valores en `(0, 1]`, decreciente en λ y con
        `g(0) = 1`. La cota superior vale hasta el redondeo: `eigh`
        devuelve el autovalor nulo como ±1e-16 y `g` de ese número puede
        quedar un ulp por encima de 1. No se recorta: el recorte
        escondería una asimetría numérica que conviene poder ver.

    Raises:
        InvalidFilterParameterError: Si τ no es finito y positivo, o si
            el espectro no tiene λmax positivo.
    """
    return _response(eigenvalues, tau, lambda_max, _NEGATIVE_EXPONENT)


def _published_response(
    eigenvalues: npt.ArrayLike,
    tau: float = DEFAULT_TAU,
    *,
    lambda_max: float | None = None,
) -> npt.NDArray[np.float64]:
    """Respuesta con el exponente positivo, `exp(+λ/(τ·λmax))`.

    Es la fórmula tal como está impresa en Aristizábal (2022, Capítulo 3).
    Existe sólo para que el experimento de `experiments/difuminador-tau/`
    pueda medir qué hace y para que los tests puedan afirmar que hace lo
    contrario de un paso-bajo: amplifica la alta frecuencia y desborda a
    infinito para τ chico. No hay ningún caso de uso en que sea la
    elección correcta, y por eso no forma parte de la API pública.

    Args:
        eigenvalues: Autovalores del Laplaciano normalizado.
        tau: Parámetro de difusión.
        lambda_max: Normalizador del exponente.

    Returns:
        Vector `g(λ)` con valores en `[1, ∞)`, creciente en λ. Puede
        contener `inf` para τ chico.

    Raises:
        InvalidFilterParameterError: Si τ o λmax son inválidos.
    """
    return _response(eigenvalues, tau, lambda_max, _PUBLISHED_EXPONENT)


def _validate_signal(zone: ZoneGraph, signal: npt.ArrayLike) -> npt.NDArray[np.float64]:
    """Valida que la señal encaje con el grafo.

    Args:
        zone: Subgrafo zonal.
        signal: Señal sobre los nodos, alineada a `zone.device_ids`.

    Returns:
        La señal como vector de float64.

    Raises:
        InvalidFilterParameterError: Si la señal no es un vector del largo
            del grafo, o si tiene NaN o infinitos.
    """
    x = np.asarray(signal, dtype=np.float64)
    if x.ndim != 1 or x.shape[0] != zone.n_meters:
        raise InvalidFilterParameterError(
            f"la señal de la zona '{zone.zona}' debe ser un vector de {zone.n_meters} "
            f"componentes, una por medidor en el orden de device_ids; recibida forma "
            f"{x.shape}"
        )
    if not np.isfinite(x).all():
        malos = np.flatnonzero(~np.isfinite(x))
        ids = ", ".join(zone.device_ids[i] for i in malos[:5])
        raise InvalidFilterParameterError(
            f"la señal tiene {malos.size} valor(es) no finito(s) ({ids}): un NaN se "
            f"propaga por toda la señal filtrada al multiplicar por U"
        )
    return x


def _apply(
    zone: ZoneGraph,
    signal: npt.ArrayLike,
    tau: float,
    sign: float,
) -> npt.NDArray[np.float64]:
    """Aplica `U·diag(g(λ))·Uᵀ·x` con el signo de exponente indicado.

    Args:
        zone: Subgrafo con su base de Fourier ya calculada.
        signal: Señal sobre los nodos.
        tau: Parámetro de difusión.
        sign: Signo del exponente.

    Returns:
        Señal filtrada `(n,)`.

    Raises:
        InvalidFilterParameterError: Si la señal o τ son inválidos.
    """
    x = _validate_signal(zone, signal)
    g = _response(zone.eigenvalues, tau, None, sign)
    espectro = zone.eigenvectors.T @ x
    return np.asarray(zone.eigenvectors @ (g * espectro), dtype=np.float64)


def diffuse(
    zone: ZoneGraph,
    signal: npt.ArrayLike,
    tau: float = DEFAULT_TAU,
) -> npt.NDArray[np.float64]:
    """Difumina una señal sobre el grafo de una zona.

    `x_filtrada = U · ( g(λ) ⊙ (Uᵀ · x) )` con `g(λ) = exp(−λ/(τ·λmax))`.
    Equivale a aplicar `exp(−L_norm/(τ·λmax))`, y por eso el resultado no
    depende de la base que `eigh` haya elegido dentro de un subespacio
    degenerado.

    Args:
        zone: Subgrafo zonal. Aporta la base de Fourier y el espectro; el
            filtro no consulta ni la base de datos ni el broker.
        signal: Señal sobre los nodos, alineada al orden canónico
            `zone.device_ids`. La componente `i` corresponde al medidor
            `zone.device_ids[i]`.
        tau: Parámetro de difusión. Ver `low_pass_response`.

    Returns:
        Señal filtrada `(n,)`, en el mismo orden de nodos que la entrada.

    Raises:
        InvalidFilterParameterError: Si la señal no encaja con el grafo o
            τ no es finito y positivo.
    """
    return _apply(zone, signal, tau, _NEGATIVE_EXPONENT)


def _diffuse_published(
    zone: ZoneGraph,
    signal: npt.ArrayLike,
    tau: float = DEFAULT_TAU,
) -> npt.NDArray[np.float64]:
    """Difumina con el exponente positivo de la fuente. Ver `_published_response`.

    Args:
        zone: Subgrafo zonal.
        signal: Señal sobre los nodos.
        tau: Parámetro de difusión.

    Returns:
        Señal `(n,)` con la alta frecuencia amplificada en vez de atenuada.

    Raises:
        InvalidFilterParameterError: Si la señal o τ son inválidos.
    """
    return _apply(zone, signal, tau, _PUBLISHED_EXPONENT)


def dirichlet_energy(zone: ZoneGraph, signal: npt.ArrayLike) -> float:
    """Energía de Dirichlet `E_D(x) = xᵀ·L_norm·x`: el desacuerdo entre vecinos.

    Métrica principal del efecto del filtro. Tres lecturas del mismo
    número: la forma cuadrática de arriba, `Σ_k λ_k·x̂_k²` sobre el
    espectro, y `Σ_ij w_ij·(xᵢ/√dᵢ − xⱼ/√dⱼ)²` sobre las aristas. Se
    calcula por la primera, que no toca la base de Fourier y por lo tanto
    es inmune a la arbitrariedad de la base en subespacios degenerados.

    Args:
        zone: Subgrafo zonal.
        signal: Señal sobre los nodos, alineada a `zone.device_ids`.

    Returns:
        Energía, siempre ≥ 0. Vale 0 exactamente cuando la señal está en
        el núcleo de `L_norm`, es decir cuando es proporcional a `√dᵢ` en
        cada componente conexa.

    Raises:
        InvalidFilterParameterError: Si la señal no encaja con el grafo.
    """
    x = _validate_signal(zone, signal)
    return float(x @ zone.laplacian_norm @ x)


def band_cut_index(
    eigenvalues: npt.ArrayLike,
    target_ratio: float = DEFAULT_BAND_TARGET_RATIO,
    *,
    tolerance: float | None = None,
) -> int:
    """Índice donde partir el espectro, ajustado al borde de subespacio más cercano.

    Los candidatos son los primeros índices de cada subespacio propio que
    devuelve `degenerate_groups`, salvo el 0, que dejaría vacía la banda
    baja. Entre ellos se elige el que tenga el autovalor más cercano a
    `target_ratio · λmax`, con desempate por el índice más bajo. Así el
    corte nunca parte un subespacio degenerado: repartir entre dos bandas
    la energía de un subespacio cuya base es arbitraria daría un número
    distinto según cómo se hayan ordenado los nodos.

    Args:
        eigenvalues: Autovalores en orden ascendente.
        target_ratio: Fracción de λmax donde se busca el corte, en `(0, 1)`.
        tolerance: Umbral para considerar dos autovalores iguales. Si es
            `None` lo deriva `degenerate_groups`.

    Returns:
        Primer índice de la banda alta, entre 1 y `n-1`.

    Raises:
        InvalidFilterParameterError: Si `target_ratio` no está en `(0, 1)`,
            si el espectro tiene menos de dos valores, o si todos los
            autovalores caen en un único subespacio y no hay dónde cortar.
    """
    valores = np.asarray(eigenvalues, dtype=np.float64)
    if not 0.0 < float(target_ratio) < 1.0:
        raise InvalidFilterParameterError(
            f"target_ratio debe estar en (0, 1), recibido {target_ratio}"
        )
    if valores.size < 2:
        raise InvalidFilterParameterError(
            f"hacen falta al menos 2 autovalores para partir el espectro en dos bandas, "
            f"recibidos {valores.size}"
        )

    objetivo = float(target_ratio) * _resolve_lambda_max(valores, None)
    bordes = [grupo[0] for grupo in degenerate_groups(valores, tolerance) if grupo[0] > 0]
    if not bordes:
        raise InvalidFilterParameterError(
            "todos los autovalores forman un único subespacio degenerado: no hay borde "
            "donde cortar sin partirlo, y el reparto por bandas no estaría definido"
        )
    return min(bordes, key=lambda i: (abs(valores[i] - objetivo), i))


def band_energy(
    zone: ZoneGraph,
    signal: npt.ArrayLike,
    *,
    cut_index: int | None = None,
    target_ratio: float = DEFAULT_BAND_TARGET_RATIO,
) -> BandEnergy:
    """Reparte la energía espectral de una señal en banda baja y banda alta.

    Lectura secundaria, pensada para el notebook: la métrica principal es
    `dirichlet_energy`. Ambas bandas se calculan con la base de Fourier,
    pero el resultado es reproducible porque el corte respeta los bordes
    de los subespacios propios y la energía agregada de un subespacio no
    depende de la base — lo que `spectral` midió.

    Args:
        zone: Subgrafo zonal.
        signal: Señal sobre los nodos, alineada a `zone.device_ids`.
        cut_index: Corte explícito. Si es `None` lo elige `band_cut_index`.
        target_ratio: Fracción de λmax buscada cuando el corte no es
            explícito.

    Returns:
        El reparto, con el corte efectivamente usado.

    Raises:
        InvalidFilterParameterError: Si la señal no encaja con el grafo, o
            si `cut_index` cae fuera de `[1, n-1]`.
    """
    x = _validate_signal(zone, signal)
    n = zone.n_meters
    corte = band_cut_index(zone.eigenvalues, target_ratio) if cut_index is None else int(cut_index)
    if not 1 <= corte <= n - 1:
        raise InvalidFilterParameterError(
            f"cut_index debe estar entre 1 y {n - 1} para que ninguna banda quede vacía, "
            f"recibido {corte}"
        )

    espectro = zone.eigenvectors.T @ x
    energias = espectro**2
    baja = float(energias[:corte].sum())
    alta = float(energias[corte:].sum())
    total = baja + alta
    return BandEnergy(
        low=baja,
        high=alta,
        total=total,
        cut_index=corte,
        cut_eigenvalue=float(zone.eigenvalues[corte]),
        high_fraction=(alta / total if total > 0.0 else 0.0),
    )
