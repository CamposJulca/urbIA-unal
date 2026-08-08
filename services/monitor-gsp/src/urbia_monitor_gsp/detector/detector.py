"""Detector de eventos colectivos por escaneo local sobre ventana.

## Qué mira, y por qué eso

Cada decisión de diseño sale de una medición, no de una suposición. El
resumen, con puntero al experimento que lo sostiene:

| Decisión | Medición |
|---|---|
| Escaneo local, no escalar por zona | Todo escalar global da AUC 0,48–0,57 |
| Contraste de dos muestras | AUC 0,73–0,81 contra 0,65–0,80 del umbral |
| Sobre ventana promediada | Integrar N instantes mejora la detección en `√N` |
| Sin centrado | Proyectar fuera de `u₀` cuesta de 40 a 77 puntos |
| Radios 1 y 2 | Un evento a profundidad 2 abarca ~12 nodos; radio 1 da ~6 |

## Dónde pierde

**Este detector es peor que un umbral por medidor en anomalías
individuales, y eso no es un defecto a corregir sino el alcance del
método.** Medido sobre un instante, a un punto de operación del 1 % de
falsos positivos:

    anomalía individual de +6σ    umbral 99,0 %    escaneo 33,4 %
    evento colectivo, depth 2     umbral  6,7 %    escaneo 18,9 %

La razón es estructural y está medida en `experiments/firma-espectral/`: la
anomalía individual es un impulso en el dominio de los nodos, con el 79,2 %
de su energía en banda alta, y promediar una bola de vecinos la diluye. El
evento colectivo es una meseta sobre un subconjunto conexo, con 16–19 % en
banda alta, y promediar la bola es exactamente lo que lo concentra.

**La conclusión operativa es que hacen falta los dos.** Un monitor completo
corre una regla por medidor para lo puntual y este escaneo para lo
colectivo. Reclamar que el método espectral "detecta mejor" sin acotar a
qué es una afirmación que las mediciones no sostienen.

## Y una advertencia sobre el punto de operación

Con el valor por defecto `window=32`, este detector alcanza prácticamente
el 100 % sobre eventos de σ ≥ 0,5 — **y también lo alcanza un umbral por
medidor**, porque integrar 32 instantes convierte un evento colectivo sutil
en uno individualmente visible. En ese punto la ventaja del método es nula.
Donde aporta es en `window ≤ 2`. Ver `DEFAULT_WINDOW`.
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

from ..graph.filter import diffuse
from ..graph.types import ZoneGraph
from .scan import candidate_balls, contrasts
from .types import Detection, DetectorConfig, DetectorError


class CollectiveScanDetector:
    """Escaneo local sobre ventanas, con umbral calibrado por Monte Carlo.

    No consulta base de datos ni broker, y no sabe de dónde salió `σ`: lo
    recibe. Eso lo mantiene independiente del paquete que genera los
    eventos, que es lo que hace creíble la evaluación.

    Args:
        zone: Subgrafo zonal que define la vecindad.
        sigma_spatial: Dispersión de la magnitud **entre medidores en un
            mismo instante**. No es la dispersión temporal: esa incluye la
            curva de carga diaria, que todos los medidores comparten y que
            por lo tanto no produce desacuerdo entre vecinos.
        config: Punto de operación.

    Raises:
        DetectorError: Si `sigma_spatial` no es finita y positiva.
    """

    def __init__(
        self,
        zone: ZoneGraph,
        sigma_spatial: float,
        config: DetectorConfig | None = None,
    ) -> None:
        """Prepara las bolas candidatas del escaneo."""
        if not np.isfinite(sigma_spatial) or sigma_spatial <= 0.0:
            raise DetectorError(f"sigma_spatial debe ser finita y > 0, recibida {sigma_spatial}")
        self._zone = zone
        self._sigma = float(sigma_spatial)
        self._config = config if config is not None else DetectorConfig()
        self._masks, self._meta = candidate_balls(zone, self._config.scan_radii)
        self._threshold: float | None = None

    @property
    def config(self) -> DetectorConfig:
        """Punto de operación en uso."""
        return self._config

    @property
    def n_candidates(self) -> int:
        """Bolas candidatas que evalúa cada ventana."""
        return int(self._masks.shape[0])

    @property
    def threshold(self) -> float:
        """Corte calibrado.

        Raises:
            DetectorError: Si todavía no se llamó a `calibrate`.
        """
        if self._threshold is None:
            raise DetectorError(
                "el detector no está calibrado: llamá a calibrate(seed) antes de "
                "detect(), o el umbral no significa nada"
            )
        return self._threshold

    @property
    def _sigma_eff(self) -> float:
        """Dispersión tras promediar la ventana, `σ/√N`."""
        return self._sigma / float(np.sqrt(self._config.window))

    def _prepare(self, window: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
        """Promedia la ventana y aplica el preprocesado configurado.

        Args:
            window: Señal `(N, n)` de una ventana.

        Returns:
            Vector `(n,)` listo para puntuar.
        """
        media = np.asarray(window.mean(axis=0), dtype=np.float64)
        if self._config.prefilter_tau is not None:
            media = diffuse(self._zone, media, self._config.prefilter_tau)
        if self._config.project_out_kernel:
            u0 = self._zone.eigenvectors[:, 0]
            media = media - float(u0 @ media) * u0
        return media

    def calibrate(self, seed: int) -> float:
        """Calibra el umbral bajo la hipótesis nula, por Monte Carlo.

        Simula ventanas sin evento con la dispersión declarada, las pasa
        por el **mismo** preprocesado que usará en operación —incluido el
        Difuminador y la proyección si están activos— y toma el cuantil que
        deja el `fpr_target` por ventana.

        Se calibra por simulación y no analíticamente porque el máximo
        sobre bolas solapadas no tiene distribución cerrada, y porque así
        el prefiltro queda incluido sin razonar aparte cómo cambia el ruido.

        Args:
            seed: Semilla del generador. Fija el umbral de forma
                reproducible.

        Returns:
            El corte calibrado.
        """
        rng = np.random.default_rng(seed)
        ventanas = rng.normal(
            0.0,
            self._sigma,
            size=(self._config.calibration_samples, self._config.window, self._zone.n_meters),
        )
        maximos = np.array(
            [contrasts(self._prepare(v), self._masks, self._sigma_eff).max() for v in ventanas]
        )
        self._threshold = float(np.quantile(maximos, 1.0 - self._config.fpr_target))
        return self._threshold

    def _windows(self, n_instants: int) -> list[tuple[int, int]]:
        """Ventanas que cubren la señal.

        Args:
            n_instants: Instantes de la señal.

        Returns:
            Pares `(inicio, fin)`.
        """
        paso = self._config.effective_step
        ancho = self._config.window
        return [(i, i + ancho) for i in range(0, n_instants - ancho + 1, paso)]

    def _score_window(
        self,
        signal: npt.NDArray[np.float64],
        inicio: int,
        fin: int,
    ) -> Detection:
        """Puntúa una ventana y arma su detección.

        Args:
            signal: Señal completa `(T, n)`.
            inicio: Primer instante de la ventana.
            fin: Primer instante fuera de la ventana.

        Returns:
            La detección de esa ventana.
        """
        valores = contrasts(self._prepare(signal[inicio:fin]), self._masks, self._sigma_eff)[0]
        mejor = int(valores.argmax())
        centro, radio = self._meta[mejor]
        nodos = tuple(int(i) for i in np.flatnonzero(self._masks[mejor] > 0.0))
        estadistico = float(valores[mejor])
        detectado = estadistico > self.threshold

        return Detection(
            zona=self._zone.zona,
            window_start=inicio,
            window_end=fin,
            statistic=estadistico,
            threshold=self.threshold,
            detected=detectado,
            seed_index=centro if detectado else None,
            seed_device_id=self._zone.device_ids[centro] if detectado else None,
            radius=radio if detectado else None,
            node_indices=nodos if detectado else (),
            device_ids=(tuple(self._zone.device_ids[i] for i in nodos) if detectado else ()),
        )

    def detect(self, signal: npt.ArrayLike) -> tuple[Detection, ...]:
        """Recorre la señal por ventanas y puntúa cada una.

        Args:
            signal: Señal `(n,)` de un instante o `(T, n)` de varios,
                alineada al orden canónico `zone.device_ids`.

        Returns:
            Una detección por ventana, en orden temporal.

        Raises:
            DetectorError: Si el detector no está calibrado, si la forma no
                encaja con el grafo, si la señal tiene valores no finitos,
                o si es más corta que la ventana.
        """
        x = np.array(signal, dtype=np.float64, copy=True)
        if x.ndim == 1:
            x = x.reshape(1, -1)
        if x.ndim != 2 or x.shape[1] != self._zone.n_meters:
            raise DetectorError(
                f"la señal de '{self._zone.zona}' debe tener forma (n,) o (T, n) con "
                f"n={self._zone.n_meters}; recibida {x.shape}"
            )
        if not np.isfinite(x).all():
            raise DetectorError(
                f"la señal de '{self._zone.zona}' tiene valores no finitos: un NaN se "
                f"propagaría al estadístico sin que nada avise"
            )
        if x.shape[0] < self._config.window:
            raise DetectorError(
                f"la señal tiene {x.shape[0]} instantes y la ventana es de "
                f"{self._config.window}: no alcanza para una sola ventana. Bajá "
                f"window o pasá una señal más larga"
            )
        return tuple(self._score_window(x, i, f) for i, f in self._windows(x.shape[0]))

    def node_mask(
        self,
        detections: tuple[Detection, ...],
        n_instants: int,
    ) -> npt.NDArray[np.bool_]:
        """Proyecta las detecciones a una máscara `(T, n)` por nodo e instante.

        Es lo que permite comparar contra la verdad de referencia nodo a
        nodo. Los instantes que ninguna ventana cubre quedan en `False`.

        Args:
            detections: Salida de `detect`.
            n_instants: Instantes de la señal original.

        Returns:
            Máscara booleana `(n_instants, n)`.
        """
        mascara = np.zeros((n_instants, self._zone.n_meters), dtype=np.bool_)
        for deteccion in detections:
            if not deteccion.detected:
                continue
            fin = min(deteccion.window_end, n_instants)
            mascara[deteccion.window_start : fin, list(deteccion.node_indices)] = True
        return mascara
