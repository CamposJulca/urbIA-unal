"""Ventana temporal densa a partir de llegadas asíncronas.

El detector consume `(T, n)`: cada instante con los `n` medidores de la zona
alineados al orden canónico del grafo. La telemetría real no trae esa
rejilla —en 24 h de operación, 2 503 450 mensajes con casi tantos valores
distintos de `timestamp_utc`— y este módulo la construye.

## La ventana es temporal, no por conteo

Guardar "las últimas 16 lecturas de cada medidor" parece equivalente y no lo
es. Un medidor que deja de publicar llenaría su columna con lecturas viejas
y el detector compararía épocas distintas creyendo que compara vecinos.

El estadístico del escaneo contrasta la media de un grupo contra la del
resto **suponiendo que todas las columnas corresponden al mismo instante**.
Con una ventana desalineada esa suposición se rompe en silencio: las
diferencias temporales —la curva de carga, que todos los medidores
comparten— entran al contraste como si fueran diferencias espaciales. No hay
NaN, no hay excepción, no hay nada que avise; sólo un estadístico que ya no
mide lo que dice medir.

Por eso la celda `(medidor, bin)` se llena **sólo** con una lectura cuyo
`timestamp_utc` cae dentro de ese bin. La frescura queda acotada por
construcción al ancho del bin, y ese ancho viaja en el payload publicado.

## Bin incompleto: no se detecta, y se dice por qué

Si a un bin de la ventana le falta cualquier medidor, la ventana no se
produce y el motivo sale como `BinIncompleteError`. Las dos alternativas son
peores:

* **Imputar** inventa justamente el dato que el estadístico va a contrastar.
* **Excluir al medidor** cambia el grafo, cuyo espectro está calculado sobre
  la topología completa. El detector quedaría escaneando bolas de otro grafo.

No producir resultado hace visible el problema en vez de esconderlo detrás
de una detección degradada.

## Los parámetros salen de una medición

Ancho de bin y gracia de cierre están medidos en
`experiments/ventana-viva/`, sobre 24 h de la telemetría real. No son
valores elegidos a ojo; ver `WindowConfig`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final

import numpy as np
import numpy.typing as npt

from ..detector.types import DEFAULT_WINDOW
from ..graph.types import MonitorGspError

# Bins que se conservan por encima de los que pide la ventana. Da lugar a
# que una lectura atrasada dentro de la gracia encuentre su bin todavía en
# memoria, y a que el diagnóstico de un fallo pueda mirar un poco hacia
# atrás. Cuesta `n` float64 por bin: irrelevante.
_MARGEN_BINS: Final = 4


class WindowError(MonitorGspError, ValueError):
    """La configuración o la entrada de la ventana son inválidas."""


@dataclass(frozen=True, slots=True)
class WindowConfig:
    """Parámetros de construcción de la ventana.

    Los tres valores por defecto salen de `experiments/ventana-viva/`,
    medido sobre 24 h de `ami_telemetry` en neusi-stage. Citarlos fuera de
    esa configuración es el error de `ESTADO.md` §5.3: son propiedades del
    productor actual, no constantes del método.

    Attributes:
        bin_seconds: Ancho del bin. El defecto de 6 s es el **menor** ancho
            con completitud por ventana ≥ 95 % en las seis zonas (dio
            99,6 %). A 5 s la completitud por bin todavía es 88,1 % pero la
            completitud por ventana es **cero**, porque la ráfaga del
            productor cruza el borde y parte cada bin en dos mitades.
            También acota la frescura: ninguna celda puede ser más vieja
            que esto respecto del instante que representa.
        window_bins: Bins que pide una ventana. Es el punto de operación del
            detector; se importa de `DEFAULT_WINDOW` en vez de repetirse
            para que no puedan quedar desincronizados.
        close_grace_seconds: Espera antes de dar un bin por cerrado. El
            defecto de 5 s está por encima del máximo retardo de transporte
            observado, 4,206 s sobre 2 503 450 mensajes. La asimetría es
            deliberada: la gracia sólo cuesta latencia sobre una ventana que
            ya cubre 96 s, mientras que quedarse corto pierde bins enteros y
            cada bin perdido invalida las 16 ventanas que lo contienen.
        max_future_seconds: Tolerancia a lecturas con marca de tiempo
            adelantada. El reloj del productor adelantaba hasta 0,68 s al de
            la base, así que rechazar todo lo que venga del futuro
            descartaría tráfico legítimo. Lo que esto ataja es una marca
            absurda, que envenenaría la rejilla ocupando bins lejanos.
    """

    bin_seconds: float = 6.0
    window_bins: int = DEFAULT_WINDOW
    close_grace_seconds: float = 5.0
    max_future_seconds: float = 60.0

    def __post_init__(self) -> None:
        """Valida los parámetros.

        Raises:
            WindowError: Si algún parámetro cae fuera de su rango.
        """
        if not np.isfinite(self.bin_seconds) or self.bin_seconds <= 0.0:
            raise WindowError(f"bin_seconds debe ser finito y > 0, recibido {self.bin_seconds}")
        if self.window_bins < 1:
            raise WindowError(f"window_bins debe ser >= 1, recibido {self.window_bins}")
        if not np.isfinite(self.close_grace_seconds) or self.close_grace_seconds < 0.0:
            raise WindowError(
                f"close_grace_seconds debe ser finito y >= 0, recibido {self.close_grace_seconds}"
            )
        if not np.isfinite(self.max_future_seconds) or self.max_future_seconds < 0.0:
            raise WindowError(
                f"max_future_seconds debe ser finito y >= 0, recibido {self.max_future_seconds}"
            )

    @property
    def span_seconds(self) -> float:
        """Segundos de reloj que cubre una ventana completa."""
        return self.bin_seconds * self.window_bins


@dataclass(frozen=True, slots=True)
class Window:
    """Una ventana densa, lista para el detector.

    Attributes:
        zona: Zona a la que pertenece.
        matrix: Señal `(window_bins, n)` en el orden canónico del grafo.
        first_bin: Índice absoluto del primer bin de la rejilla.
        last_bin: Índice absoluto del último bin, inclusive.
        start_utc: Borde izquierdo del primer bin.
        end_utc: Borde derecho del último bin.
        skipped_bins: Bins que se cerraron desde la emisión anterior y sobre
            los que **no** se emitió ventana. Distinto de cero significa que
            el ciclo de detección tarda más que el bin y el servicio se está
            atrasando de forma acumulativa.
    """

    zona: str
    matrix: npt.NDArray[np.float64]
    first_bin: int
    last_bin: int
    start_utc: datetime
    end_utc: datetime
    skipped_bins: int

    def to_dict(self) -> dict[str, Any]:
        """Serializa los metadatos de la ventana, sin la matriz.

        Returns:
            Diccionario serializable.
        """
        return {
            "zona": self.zona,
            "first_bin": self.first_bin,
            "last_bin": self.last_bin,
            "inicio_utc": self.start_utc.isoformat(),
            "fin_utc": self.end_utc.isoformat(),
            "bins": int(self.matrix.shape[0]),
            "medidores": int(self.matrix.shape[1]),
            "skipped_bins": self.skipped_bins,
        }


class BinIncompleteError(MonitorGspError, RuntimeError):
    """La ventana no se puede armar porque falta dato, y dice qué falta.

    No es un fallo del servicio: es el resultado honesto de que la
    telemetría necesaria no llegó. Se levanta para que el llamador publique
    el motivo en vez de producir una detección degradada.

    Attributes:
        zona: Zona afectada.
        motivo: Código estable para el consumidor. `"calentamiento"` cuando
            el servicio todavía no acumuló bins suficientes desde que
            arrancó; `"bins_incompletos"` cuando la ventana cae sobre bins a
            los que les falta algún medidor.
        first_bin: Primer bin de la ventana que se intentó armar.
        last_bin: Último bin, inclusive.
        start_utc: Borde izquierdo de la ventana.
        end_utc: Borde derecho de la ventana.
        incomplete_bins: Cuántos bins de la ventana no estaban completos.
        missing_device_ids: Unión de los medidores que faltaron, ordenada.
    """

    def __init__(
        self,
        zona: str,
        motivo: str,
        first_bin: int,
        last_bin: int,
        start_utc: datetime,
        end_utc: datetime,
        incomplete_bins: int,
        missing_device_ids: tuple[str, ...],
    ) -> None:
        """Inicializa el motivo con su detalle.

        Args:
            zona: Zona afectada.
            motivo: Código estable del motivo.
            first_bin: Primer bin de la ventana.
            last_bin: Último bin, inclusive.
            start_utc: Borde izquierdo de la ventana.
            end_utc: Borde derecho de la ventana.
            incomplete_bins: Bins incompletos dentro de la ventana.
            missing_device_ids: Medidores faltantes, sin repetir.
        """
        self.zona = zona
        self.motivo = motivo
        self.first_bin = first_bin
        self.last_bin = last_bin
        self.start_utc = start_utc
        self.end_utc = end_utc
        self.incomplete_bins = incomplete_bins
        self.missing_device_ids = missing_device_ids

        muestra = ", ".join(missing_device_ids[:5])
        resto = f" y {len(missing_device_ids) - 5} más" if len(missing_device_ids) > 5 else ""
        detalle = f" sin dato de {muestra}{resto}" if missing_device_ids else ""
        super().__init__(
            f"'{zona}' no produce ventana ({motivo}): {incomplete_bins} de "
            f"{last_bin - first_bin + 1} bins incompletos entre "
            f"{start_utc.isoformat()} y {end_utc.isoformat()}{detalle}"
        )

    def to_dict(self) -> dict[str, Any]:
        """Serializa el motivo para publicarlo.

        Returns:
            Diccionario serializable.
        """
        return {
            "zona": self.zona,
            "motivo": self.motivo,
            "first_bin": self.first_bin,
            "last_bin": self.last_bin,
            "inicio_utc": self.start_utc.isoformat(),
            "fin_utc": self.end_utc.isoformat(),
            "bins_incompletos": self.incomplete_bins,
            "medidores_faltantes": list(self.missing_device_ids),
        }


def _require_utc(momento: datetime, campo: str) -> float:
    """Convierte a epoch exigiendo que el instante traiga zona horaria.

    Un `datetime` ingenuo se interpretaría como hora local del proceso, y el
    contenedor puede correr en otra zona que el productor. El bin quedaría
    corrido varias horas sin que nada avise.

    Args:
        momento: Instante a convertir.
        campo: Nombre del argumento, para el mensaje de error.

    Returns:
        Segundos desde la época Unix.

    Raises:
        WindowError: Si el instante no tiene zona horaria.
    """
    if momento.tzinfo is None or momento.tzinfo.utcoffset(momento) is None:
        raise WindowError(
            f"{campo} debe traer zona horaria: un datetime ingenuo se leería como "
            f"hora local del proceso y correría el bin sin que nada avise"
        )
    return momento.timestamp()


class ZoneWindow:
    """Acumula lecturas sueltas de una zona y emite ventanas densas.

    No sabe de MQTT ni de PostgreSQL: recibe lecturas y entrega ventanas.
    Quién se las trae es problema del servicio.

    La rejilla de bins es **absoluta**, anclada a la época Unix
    (`floor(epoch / bin_seconds)`), y no al arranque del proceso. Dos
    ejecuciones distintas sobre los mismos datos producen los mismos bins,
    que es lo que permite reproducir offline lo que pasó en vivo.

    Args:
        zona: Nombre de la zona.
        device_ids: Medidores en el **orden canónico del grafo**
            (`ZoneGraph.device_ids`). Ese orden indexa las columnas de la
            matriz emitida y tiene que coincidir con el del detector.
        config: Parámetros de la ventana.

    Raises:
        WindowError: Si `device_ids` está vacío o tiene repetidos.
    """

    def __init__(
        self,
        zona: str,
        device_ids: tuple[str, ...],
        config: WindowConfig | None = None,
    ) -> None:
        """Prepara los buffers de la zona."""
        if not device_ids:
            raise WindowError(f"la zona '{zona}' no tiene medidores")
        if len(set(device_ids)) != len(device_ids):
            raise WindowError(f"la zona '{zona}' tiene device_ids repetidos")

        self._zona = zona
        self._device_ids = device_ids
        self._config = config if config is not None else WindowConfig()
        self._columna = {device_id: i for i, device_id in enumerate(device_ids)}

        # Por bin absoluto: valores, marca de tiempo de la lectura que ocupa
        # cada celda, y máscara de ocupación.
        self._valores: dict[int, npt.NDArray[np.float64]] = {}
        self._marcas: dict[int, npt.NDArray[np.float64]] = {}
        self._ocupadas: dict[int, npt.NDArray[np.bool_]] = {}

        self._ultimo_emitido: int | None = None
        self._primer_bin_visto: int | None = None

        # Contadores para las métricas del servicio.
        self.accepted_count: int = 0
        self.unknown_device_count: int = 0
        self.late_count: int = 0
        self.future_count: int = 0
        self.superseded_count: int = 0

    @property
    def zona(self) -> str:
        """Zona que acumula esta ventana."""
        return self._zona

    @property
    def config(self) -> WindowConfig:
        """Parámetros en uso."""
        return self._config

    @property
    def n_meters(self) -> int:
        """Medidores que exige un bin completo."""
        return len(self._device_ids)

    @property
    def buffered_bins(self) -> int:
        """Bins que hay en memoria. Acotado por la poda."""
        return len(self._valores)

    def _bin_de(self, epoch: float) -> int:
        """Índice absoluto del bin que contiene un instante.

        Args:
            epoch: Segundos desde la época Unix.

        Returns:
            Índice del bin en la rejilla absoluta.
        """
        return int(np.floor(epoch / self._config.bin_seconds))

    def _bordes(self, indice: int) -> tuple[datetime, datetime]:
        """Bordes de un bin, como instantes UTC.

        Args:
            indice: Índice absoluto del bin.

        Returns:
            Par `(izquierdo, derecho)`; el derecho es el primer instante
            fuera del bin.
        """
        ancho = self._config.bin_seconds
        return (
            datetime.fromtimestamp(indice * ancho, tz=UTC),
            datetime.fromtimestamp((indice + 1) * ancho, tz=UTC),
        )

    def observe(
        self,
        device_id: str,
        timestamp_utc: datetime,
        value: float,
        now: datetime | None = None,
    ) -> bool:
        """Incorpora una lectura.

        Si ya había una lectura de ese medidor en ese bin, gana la de
        `timestamp_utc` mayor y la otra se descarta. **Nunca se promedian.**
        Promediar `k` lecturas reduciría la dispersión espacial en `√k` sin
        que la calibración congelada se entere, y el umbral quedaría
        sistemáticamente alto: menos detecciones, con la tasa de falsos
        positivos declarada dejando de corresponder a la real. Sobre el
        productor actual eso afectaría al 18,8 % de las celdas.

        Args:
            device_id: Medidor que publica.
            timestamp_utc: Instante de la lectura, con zona horaria.
            value: Valor de la magnitud monitoreada.
            now: Instante actual, para acotar cuán adelantada puede venir la
                marca. `None` desactiva ese control, que es lo que quiere
                una reproducción offline de datos históricos.

        Returns:
            `True` si la lectura ocupó una celda; `False` si se descartó por
            medidor ajeno a la zona, bin ya cerrado, marca absurda, o por
            haber sido superada por una lectura más reciente del mismo bin.

        Raises:
            WindowError: Si `timestamp_utc` no trae zona horaria o el valor
                no es finito.
        """
        columna = self._columna.get(device_id)
        if columna is None:
            self.unknown_device_count += 1
            return False

        epoch = _require_utc(timestamp_utc, "timestamp_utc")
        if not np.isfinite(value):
            raise WindowError(
                f"lectura no finita de '{device_id}' en '{self._zona}': un NaN se "
                f"propagaría al estadístico sin que nada avise"
            )

        # Una marca absurdamente adelantada ocuparía un bin lejano que
        # sobrevive a la poda y quedaría esperando a que el reloj llegue,
        # para entonces ser dato viejo presentado como fresco.
        if now is not None:
            adelanto = epoch - _require_utc(now, "now")
            if adelanto > self._config.max_future_seconds:
                self.future_count += 1
                return False

        indice = self._bin_de(epoch)

        # Un bin ya emitido no se puede corregir: la ventana que lo contenía
        # ya salió publicada.
        if self._ultimo_emitido is not None and indice <= self._ultimo_emitido:
            self.late_count += 1
            return False

        arreglos = self._valores.get(indice)
        if arreglos is None:
            arreglos = np.zeros(self.n_meters, dtype=np.float64)
            self._valores[indice] = arreglos
            self._marcas[indice] = np.full(self.n_meters, -np.inf, dtype=np.float64)
            self._ocupadas[indice] = np.zeros(self.n_meters, dtype=np.bool_)

        if self._ocupadas[indice][columna] and self._marcas[indice][columna] >= epoch:
            self.superseded_count += 1
            return False
        if self._ocupadas[indice][columna]:
            self.superseded_count += 1

        arreglos[columna] = float(value)
        self._marcas[indice][columna] = epoch
        self._ocupadas[indice][columna] = True
        self.accepted_count += 1

        if self._primer_bin_visto is None or indice < self._primer_bin_visto:
            self._primer_bin_visto = indice
        return True

    def observe_many(
        self,
        lecturas: list[tuple[str, datetime, float]],
    ) -> int:
        """Incorpora varias lecturas.

        Args:
            lecturas: Tuplas `(device_id, timestamp_utc, valor)`.

        Returns:
            Cuántas ocuparon una celda.
        """
        return sum(1 for d, t, v in lecturas if self.observe(d, t, v))

    def last_closed_bin(self, now: datetime) -> int | None:
        """Último bin que ya se puede dar por cerrado.

        Un bin cierra cuando pasó su borde derecho **más la gracia**: entre
        que un medidor estampa su marca y el proceso recibe el mensaje hay
        transporte, y cerrar en el borde exacto perdería las lecturas
        atrasadas.

        Args:
            now: Instante actual, con zona horaria.

        Returns:
            Índice del último bin cerrado, o `None` si todavía no cerró
            ninguno de la rejilla.

        Raises:
            WindowError: Si `now` no trae zona horaria.
        """
        epoch = _require_utc(now, "now")
        limite = epoch - self._config.close_grace_seconds
        indice = self._bin_de(limite) - 1
        return indice if indice >= 0 else None

    def _faltantes(self, indice: int) -> tuple[str, ...]:
        """Medidores sin celda ocupada en un bin.

        Args:
            indice: Índice absoluto del bin.

        Returns:
            Identificadores faltantes, en el orden canónico.
        """
        ocupadas = self._ocupadas.get(indice)
        if ocupadas is None:
            return self._device_ids
        return tuple(self._device_ids[i] for i in np.flatnonzero(~ocupadas).tolist())

    def _podar(self, ultimo: int) -> None:
        """Descarta los bins que ya no puede necesitar ninguna ventana.

        Args:
            ultimo: Último bin cerrado.
        """
        piso = ultimo - self._config.window_bins - _MARGEN_BINS
        for indice in [i for i in self._valores if i < piso]:
            del self._valores[indice]
            del self._marcas[indice]
            del self._ocupadas[indice]

    def emit(self, now: datetime) -> Window | None:
        """Emite la ventana que termina en el último bin cerrado.

        Emite **una vez por bin**: llamarla varias veces dentro del mismo
        bin devuelve `None` en las llamadas siguientes.

        Args:
            now: Instante actual, con zona horaria.

        Returns:
            La ventana densa, o `None` si no cerró ningún bin nuevo desde la
            emisión anterior.

        Raises:
            BinIncompleteError: Si la ventana cae sobre bins a los que les falta
                algún medidor, o si todavía no hay historia suficiente
                desde que arrancó el proceso.
            WindowError: Si `now` no trae zona horaria.
        """
        ultimo = self.last_closed_bin(now)
        if ultimo is None:
            return None
        if self._ultimo_emitido is not None and ultimo <= self._ultimo_emitido:
            return None

        saltados = 0 if self._ultimo_emitido is None else ultimo - self._ultimo_emitido - 1
        primero = ultimo - self._config.window_bins + 1
        izquierdo, _ = self._bordes(primero)
        _, derecho = self._bordes(ultimo)

        # El bin se marca como emitido pase lo que pase: si faltó dato, la
        # ventana no se reintenta más adelante con las lecturas que lleguen
        # tarde. Reintentarla publicaría dos resultados distintos para el
        # mismo tramo de tiempo.
        self._ultimo_emitido = ultimo
        self._podar(ultimo)

        faltantes: set[str] = set()
        incompletos = 0
        for indice in range(primero, ultimo + 1):
            ausentes = self._faltantes(indice)
            if ausentes:
                incompletos += 1
                faltantes.update(ausentes)

        if incompletos:
            calentando = self._primer_bin_visto is None or primero < self._primer_bin_visto
            raise BinIncompleteError(
                zona=self._zona,
                motivo="calentamiento" if calentando else "bins_incompletos",
                first_bin=primero,
                last_bin=ultimo,
                start_utc=izquierdo,
                end_utc=derecho,
                incomplete_bins=incompletos,
                missing_device_ids=tuple(sorted(faltantes)),
            )

        matriz = np.stack([self._valores[i] for i in range(primero, ultimo + 1)])
        return Window(
            zona=self._zona,
            matrix=matriz,
            first_bin=primero,
            last_bin=ultimo,
            start_utc=izquierdo,
            end_utc=derecho,
            skipped_bins=saltados,
        )
