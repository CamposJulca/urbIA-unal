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

DEFAULT_WINDOW: Final = 32
"""Instantes sobre los que se integra. Punto de operación declarado.

**Lo que implica, medido.** El barrido de `experiments/magnitud-duracion/`
dice que integrar mejora la detección en `√N` y que **el umbral por medidor
mejora igual**: a σ=0,5 y N=20 el escaneo da 90,9 % contra 79,2 % del
umbral, y a N mayor los dos saturan. Con N=32 este detector alcanza
prácticamente el 100 % sobre eventos de σ ≥ 0,5, y **su ventaja sobre un
umbral simple en ese punto es nula**.

La región donde el método de grafo aporta de verdad es la contraria:
N ≤ 2, donde detecta entre 2,3 y 2,5 veces más que el umbral, a costa de
una tasa absoluta cercana al 45 %. Cuál de los dos regímenes conviene
depende de si la tesis reclama "detecta eventos sutiles" o "el método
aporta sobre el umbral". Por eso es configurable.
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
            `None` para no filtrar. La firma colectiva es de baja
            frecuencia y el Difuminador es un paso-bajo, así que en
            principio debería mejorar la relación señal-ruido; pero suaviza
            la frontera del grupo, que es de donde sale la señal. Es una
            pregunta medible y por eso es opción, no supuesto.
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

    @property
    def instants(self) -> range:
        """Instantes que cubre la ventana."""
        return range(self.window_start, self.window_end)

    def to_dict(self) -> dict[str, Any]:
        """Serializa la detección a tipos JSON.

        Returns:
            Diccionario serializable.
        """
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
