"""Contrato del detector: configuración, detección y matriz de confusión.

El punto de operación es una **decisión declarada**, no una constante
enterrada: todo lo que lo fija vive en `DetectorConfig` y se puede cambiar
desde afuera.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

import numpy as np
import numpy.typing as npt

from ..graph.types import MonitorGspError

DEFAULT_WINDOW: Final = 16
"""Instantes sobre los que se integra. Punto de operación declarado.

Elegido por **ventaja sobre el umbral por medidor**, no por detección
absoluta: el segundo objetivo ya lo resuelve un método más barato.

Medido en **condición realista** —ventana deslizante, evento en posición
sorteada, 1 % de falsos positivos **por señal**— en
`experiments/detector-deslizante/`, sobre eventos de σ=0,5 y profundidad 2:

    N=16    escaneo 79,4 %   umbral 29,8 %   ventaja +49,6   <- este
    N=32    escaneo 99,5 %   umbral 70,2 %   ventaja +29,3   <- maxima deteccion

La elección se había hecho antes con ventana conocida y 1 % por ventana
(`experiments/detector-colectivo/`), donde N=16 daba 93,6 % contra 54,8 % y
ventaja +38,8. N=16 sobrevive a las dos condiciones; lo que cambia es que
la condición realista **agranda** la ventaja, porque deslizar penaliza más
al umbral —49 ventanas × 25 medidores casi independientes— que al escaneo,
cuyas bolas se solapan.

**La ventaja obedece a `σ·√N ≈ 2`**, la magnitud efectiva por medidor tras
integrar: es máxima justo por debajo del punto donde un umbral por medidor
empieza a funcionar. Por debajo ninguno ve nada; por encima los dos ven
todo. De ahí una regla transferible: ante un evento de magnitud σ conocida,
la ventana que más aporta es `N ≈ (2/σ)²`.

Perseguir detección en vez de ventaja lleva a N=64, donde el método no
aporta nada. Por eso es configurable y por eso el defecto es 16.
"""


class DetectorError(MonitorGspError, ValueError):
    """La configuración o la entrada del detector son inválidas."""


@dataclass(frozen=True, slots=True)
class DetectorConfig:
    """Punto de operación del detector.

    Attributes:
        window: Instantes sobre los que se promedia antes de puntuar.
        step: Desplazamiento entre ventanas. `None` las deja sin solapar.
        scan_radii: Radios de las bolas candidatas. Un evento a
            profundidad 2 abarca ~12 nodos y una bola de radio 1 tiene ~6,
            así que escanear sólo radio 1 techa el recall por nodo cerca
            del 50 % por construcción.
        fpr_target: Falsos positivos **por ventana** que admite la
            calibración. Con ventanas deslizantes, una señal larga tiene
            muchas oportunidades: la tasa por señal es mayor y hay que
            leerla como tal.
        prefilter_tau: τ del Difuminador aplicado antes de puntuar, o
            `None` para no filtrar. **Apagado por defecto, y medido: no
            usarlo.** Sube la detección de 55,8 % a 100 %, pero la ganancia
            es espuria. El filtro **rompe la invariancia a sumar una
            constante**, que es lo que hacía robusto al escaneo:
            `diffuse(1)` no es constante —va de 0,8524 a 1,2426 con
            τ=0,05— porque el vector constante no está en el núcleo de
            `L_norm`. Consecuencia medida sobre un modo común, toda la zona
            corrida 2σ, que el detector *no* debe marcar: sin filtro lo
            marca en el 0,0–0,7 % de los casos, con filtro en el 100 % con
            cualquier τ probado. Convierte un detector de discordancia
            local en uno de nivel medio.
        project_out_kernel: Proyectar la señal fuera de `u₀` antes de
            puntuar. **Apagado por defecto, y con medición detrás.** El
            contraste de dos muestras ya es invariante al nivel medio, así
            que la proyección no aporta nada y sí introduce un sesgo
            determinista por bola: `(u₀ᵀx)` vale ~1 092 en una señal de
            220 V, y multiplicado por el desbalance de grado del grupo da
            hasta 42σ de corrimiento. Medido sobre las seis zonas a σ=1,0 y
            N=5, encenderlo baja la detección de 78,8–97,2 % a 19,0–55,0 %.
        calibration_samples: Realizaciones de Monte Carlo para calibrar el
            umbral bajo la hipótesis nula.
    """

    window: int = DEFAULT_WINDOW
    step: int | None = None
    scan_radii: tuple[int, ...] = (1, 2)
    fpr_target: float = 0.01
    prefilter_tau: float | None = None
    project_out_kernel: bool = False
    calibration_samples: int = 2000

    def __post_init__(self) -> None:
        """Valida la coherencia del punto de operación.

        Raises:
            DetectorError: Si algún parámetro cae fuera de su rango.
        """
        if self.window < 1:
            raise DetectorError(f"window debe ser >= 1, recibido {self.window}")
        if self.step is not None and self.step < 1:
            raise DetectorError(f"step debe ser >= 1, recibido {self.step}")
        if not self.scan_radii:
            raise DetectorError("hace falta al menos un radio de escaneo")
        if any(r < 0 for r in self.scan_radii):
            raise DetectorError(f"los radios deben ser >= 0, recibidos {self.scan_radii}")
        if not 0.0 < self.fpr_target < 1.0:
            raise DetectorError(f"fpr_target debe estar en (0, 1), recibido {self.fpr_target}")
        if self.prefilter_tau is not None and self.prefilter_tau <= 0.0:
            raise DetectorError(f"prefilter_tau debe ser > 0, recibido {self.prefilter_tau}")
        if self.calibration_samples < 100:
            raise DetectorError(
                f"calibration_samples debe ser >= 100 para que el cuantil del "
                f"{self.fpr_target:.0%} signifique algo, recibido "
                f"{self.calibration_samples}"
            )

    @property
    def effective_step(self) -> int:
        """Desplazamiento efectivo entre ventanas."""
        return self.window if self.step is None else self.step


@dataclass(frozen=True, slots=True)
class FrozenThreshold:
    """Un umbral calibrado, con todo lo que hace falta para saber si aplica.

    Un servicio en línea no puede recalibrar al arrancar: el umbral tiene
    que ser el mismo entre reinicios, o dos ventanas idénticas darían
    veredictos distintos según cuándo arrancó el proceso. Pero un umbral
    suelto es exactamente la trampa de `ESTADO.md` §5.3 —una cifra correcta
    operando fuera de su configuración— así que acá el número viaja siempre
    con las condiciones bajo las que se lo obtuvo, y `load_threshold` las
    verifica en vez de confiar.

    **La calibración no se hace sobre datos vivos.** Una anomalía
    persistente se volvería parte de la hipótesis nula y el detector
    dejaría de verla: el umbral subiría hasta acomodarla. Por eso el nulo
    es sintético y la σ sale del perfil congelado.

    Attributes:
        zona: Zona para la que vale. Un umbral de otra zona no aplica: el
            estadístico depende del grafo, y los grados y el tamaño
            cambian entre zonas.
        threshold: El corte.
        sigma_spatial: Dispersión espacial con la que se simuló el nulo.
        config: Punto de operación con el que se calibró.
        seed: Semilla del Monte Carlo, para poder rehacerlo.
        n_instants: Largo de la señal si el objetivo era por señal, o
            `None` si el objetivo era por ventana. **No son
            intercambiables**: ver `CollectiveScanDetector.calibrate`.
        source: De dónde salió, para poder rastrearlo. Típicamente el
            archivo versionado y su versión.
    """

    zona: str
    threshold: float
    sigma_spatial: float
    config: DetectorConfig
    seed: int
    n_instants: int | None
    source: str

    def to_dict(self) -> dict[str, Any]:
        """Serializa el umbral y su procedencia.

        Returns:
            Diccionario serializable.
        """
        return {
            "zona": self.zona,
            "threshold": self.threshold,
            "sigma_spatial": self.sigma_spatial,
            "seed": self.seed,
            "n_instants": self.n_instants,
            "source": self.source,
            "config": {
                "window": self.config.window,
                "step": self.config.step,
                "scan_radii": list(self.config.scan_radii),
                "fpr_target": self.config.fpr_target,
                "prefilter_tau": self.config.prefilter_tau,
                "project_out_kernel": self.config.project_out_kernel,
                "calibration_samples": self.config.calibration_samples,
            },
        }

    @classmethod
    def from_dict(cls, datos: dict[str, Any]) -> FrozenThreshold:
        """Reconstruye un umbral congelado desde su forma serializada.

        Args:
            datos: Diccionario con la forma que produce `to_dict`.

        Returns:
            El umbral con su configuración.

        Raises:
            DetectorError: Si falta alguna clave o el punto de operación
                serializado es inválido.
        """
        try:
            crudo = datos["config"]
            config = DetectorConfig(
                window=int(crudo["window"]),
                step=None if crudo["step"] is None else int(crudo["step"]),
                scan_radii=tuple(int(r) for r in crudo["scan_radii"]),
                fpr_target=float(crudo["fpr_target"]),
                prefilter_tau=(
                    None if crudo["prefilter_tau"] is None else float(crudo["prefilter_tau"])
                ),
                project_out_kernel=bool(crudo["project_out_kernel"]),
                calibration_samples=int(crudo["calibration_samples"]),
            )
            return cls(
                zona=str(datos["zona"]),
                threshold=float(datos["threshold"]),
                sigma_spatial=float(datos["sigma_spatial"]),
                config=config,
                seed=int(datos["seed"]),
                n_instants=(None if datos["n_instants"] is None else int(datos["n_instants"])),
                source=str(datos["source"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise DetectorError(f"umbral congelado mal formado: {exc}") from exc


@dataclass(frozen=True, slots=True)
class ScanCandidate:
    """Una bola candidata con el contraste que se midió sobre ella.

    El escaneo evalúa todas las bolas y se queda con el máximo. Guardar
    sólo la ganadora impediría reconstruir después el punto de operación:
    con un solo número no se sabe si el máximo se despegó del resto —una
    discordancia localizada— o si toda la zona rondaba el mismo valor y la
    ganadora salió por azar. Son dos situaciones distintas que producen la
    misma cifra.

    La bola no lleva su lista de nodos: **el centro y el radio la
    determinan sin ambigüedad dado el grafo**, y la huella del grafo viaja
    con la calibración, así que el consumidor puede reconstruirla. Repetir
    los identificadores por cada candidata multiplicaría el payload por el
    tamaño de la bola sin agregar información.

    Attributes:
        seed_index: Centro de la bola, en el orden canónico de la zona.
        seed_device_id: Identificador de ese centro.
        radius: Saltos que abarca la bola desde el centro.
        size: Nodos que contiene.
        statistic: Contraste de dos muestras, en unidades de σ.
    """

    seed_index: int
    seed_device_id: str
    radius: int
    size: int
    statistic: float

    def to_dict(self) -> dict[str, Any]:
        """Serializa la candidata.

        Returns:
            Diccionario serializable.
        """
        return {
            "seed_index": self.seed_index,
            "seed_device_id": self.seed_device_id,
            "radius": self.radius,
            "size": self.size,
            "statistic": self.statistic,
        }


@dataclass(frozen=True, slots=True)
class Detection:
    """Lo que el detector afirma sobre una ventana.

    Reporta **qué nodos** marcó, no sólo que hubo algo. Sin eso no se puede
    comparar contra una verdad de referencia por nodo, y la matriz de
    confusión queda incompleta.

    Attributes:
        zona: Zona analizada.
        window_start: Primer instante de la ventana.
        window_end: Primer instante **fuera** de la ventana.
        statistic: Mayor contraste hallado entre las bolas candidatas.
        threshold: Corte con el que se comparó.
        detected: Si el estadístico superó el corte.
        seed_index: Centro de la bola ganadora, o `None` si no hubo
            candidatos válidos.
        seed_device_id: Identificador de ese centro.
        radius: Radio de la bola ganadora.
        node_indices: Nodos de la bola ganadora, en orden canónico.
        device_ids: Identificadores de esos nodos.
        ranking: **Todas** las bolas candidatas ordenadas por contraste
            descendente, no sólo la ganadora. `ranking[0]` es siempre la
            bola de la que salen `statistic`, `seed_index` y `radius`. La
            construcción cuesta 34–49 µs por ventana según la zona —medido
            sobre las seis de `manizales_150`, 35 a 50 bolas— contra los
            6 s que dura un bin: irrelevante en operación. Quien publique
            decide cuánto del ranking manda; ver `to_dict`.
    """

    zona: str
    window_start: int
    window_end: int
    statistic: float
    threshold: float
    detected: bool
    seed_index: int | None
    seed_device_id: str | None
    radius: int | None
    node_indices: tuple[int, ...]
    device_ids: tuple[str, ...]
    ranking: tuple[ScanCandidate, ...] = ()

    @property
    def instants(self) -> range:
        """Instantes que cubre la ventana."""
        return range(self.window_start, self.window_end)

    def to_dict(self, top_k: int | None = None) -> dict[str, Any]:
        """Serializa la detección a tipos JSON.

        Args:
            top_k: Cuántas candidatas del ranking incluir, de mayor a
                menor contraste. `None` las incluye todas, que es el
                defecto: recortar es una decisión de quien publica —por
                tamaño de payload— y no del detector.

        Returns:
            Diccionario serializable.

        Raises:
            DetectorError: Si `top_k` es negativo.
        """
        if top_k is not None and top_k < 0:
            raise DetectorError(f"top_k debe ser >= 0 o None, recibido {top_k}")
        candidatas = self.ranking if top_k is None else self.ranking[:top_k]
        return {
            "zona": self.zona,
            "window_start": self.window_start,
            "window_end": self.window_end,
            "statistic": self.statistic,
            "threshold": self.threshold,
            "detected": self.detected,
            "seed_device_id": self.seed_device_id,
            "radius": self.radius,
            "node_indices": list(self.node_indices),
            "device_ids": list(self.device_ids),
            "candidatas_evaluadas": len(self.ranking),
            "ranking": [c.to_dict() for c in candidatas],
        }


@dataclass(frozen=True, slots=True)
class ConfusionMatrix:
    """Conteos de una comparación contra la verdad de referencia.

    Attributes:
        true_positive: Marcados y anómalos.
        false_positive: Marcados y normales.
        false_negative: No marcados y anómalos.
        true_negative: No marcados y normales.
    """

    true_positive: int
    false_positive: int
    false_negative: int
    true_negative: int

    @property
    def total(self) -> int:
        """Elementos comparados."""
        return self.true_positive + self.false_positive + self.false_negative + self.true_negative

    @property
    def recall(self) -> float:
        """Fracción de lo anómalo que se marcó. Vale 0 si no había nada."""
        positivos = self.true_positive + self.false_negative
        return self.true_positive / positivos if positivos else 0.0

    @property
    def precision(self) -> float:
        """Fracción de lo marcado que era anómalo. Vale 0 si no se marcó nada."""
        marcados = self.true_positive + self.false_positive
        return self.true_positive / marcados if marcados else 0.0

    @property
    def false_positive_rate(self) -> float:
        """Fracción de lo normal que se marcó."""
        negativos = self.false_positive + self.true_negative
        return self.false_positive / negativos if negativos else 0.0

    @property
    def f1(self) -> float:
        """Media armónica de precisión y recall."""
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) > 0 else 0.0

    def to_dict(self) -> dict[str, Any]:
        """Serializa los conteos y las tasas derivadas.

        Returns:
            Diccionario serializable.
        """
        return {
            "true_positive": self.true_positive,
            "false_positive": self.false_positive,
            "false_negative": self.false_negative,
            "true_negative": self.true_negative,
            "recall": self.recall,
            "precision": self.precision,
            "false_positive_rate": self.false_positive_rate,
            "f1": self.f1,
        }


def confusion_matrix(
    predicted: npt.NDArray[np.bool_],
    truth: npt.NDArray[np.bool_],
) -> ConfusionMatrix:
    """Compara una predicción booleana contra la verdad, elemento a elemento.

    Trabaja sobre arrays planos a propósito: no sabe nada del inyector ni
    de cómo se generó la verdad. Sirve igual para una máscara por nodo e
    instante que para un vector de decisiones por ventana.

    Args:
        predicted: Máscara de lo marcado.
        truth: Máscara de lo realmente anómalo, de la misma forma.

    Returns:
        Los cuatro conteos.

    Raises:
        DetectorError: Si las dos máscaras no tienen la misma forma.
    """
    p = np.asarray(predicted, dtype=bool)
    t = np.asarray(truth, dtype=bool)
    if p.shape != t.shape:
        raise DetectorError(
            f"la predicción y la verdad deben tener la misma forma: {p.shape} != {t.shape}"
        )
    return ConfusionMatrix(
        true_positive=int((p & t).sum()),
        false_positive=int((p & ~t).sum()),
        false_negative=int((~p & t).sum()),
        true_negative=int((~p & ~t).sum()),
    )
