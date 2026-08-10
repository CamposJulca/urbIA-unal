"""Qué publica el monitor, y en qué forma.

## Las tres cosas que salen

| Topic | Cuándo | Para quién |
|---|---|---|
| `<prefijo>/ventana/<zona>` | cada ventana producida | quien reconstruye el punto de operación |
| `<prefijo>/deteccion/<zona>` | sólo si superó el corte | quien alerta |
| `<prefijo>/sin-ventana/<zona>` | cada zona sin datos | quien mira el panel en blanco |

La detección viaja por dos topics con el mismo cuerpo. Es deliberado: un
consumidor que alerta no debería tener que parsear 5 kB/s para encontrar un
evento por hora —medido en `experiments/ciclo-deteccion/`: 0,05 a 0,18
episodios falsos por hora y por zona bajo nulo—. La duplicación cuesta bytes
sólo cuando hay detección, que es justo cuando no importan.

## Por qué se publica también la ventana sin detección

Porque el estadístico y su ranking son lo que permite reconstruir después
bajo qué condiciones se decidió. Publicar sólo las detecciones dejaría un
registro en el que no se puede distinguir "no pasó nada" de "el detector
estaba mirando para otro lado", y las dos cosas se ven igual desde afuera:
silencio.

## Y por qué se publica el motivo cuando no hay ventana

Una zona sin datos no produce detección —no se imputa ni se excluye a
nadie— y ese silencio es indistinguible del silencio de una zona tranquila.
Publicar el motivo es lo que vuelve visible el problema en vez de
esconderlo detrás de una detección degradada.

## Lo que viaja con cada mensaje, y por qué

Cada payload lleva la **procedencia del umbral** y la **huella del grafo**.
Un corte sin procedencia no se puede auditar después, y es exactamente la
trampa de `ESTADO.md` §5.3: una cifra correcta leída fuera de la
configuración que la produjo. Acá la configuración viaja pegada al número.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any, Final

from ..graph.types import MonitorGspError
from .calibration import Calibration
from .metrics import MonitorMetrics, NullMetrics
from .runtime import CycleResult, ZoneResult

logger: Final = logging.getLogger(__name__)

SCHEMA_VENTANA: Final = "urbia-monitor-ventana-v1"
SCHEMA_SIN_VENTANA: Final = "urbia-monitor-sin-ventana-v1"


class PublishError(MonitorGspError, RuntimeError):
    """El broker no aceptó el mensaje."""


class DetectionPayload:
    """Arma los cuerpos de los mensajes que publica el monitor.

    Separado del transporte para poder verificar la forma del payload sin
    broker, que es lo que hacen los tests.

    Args:
        calibration: Calibración en uso, de la que salen la versión y la
            topología que se declaran en cada mensaje.
        fingerprints: Huella de la topología por zona.
        top_k: Candidatas del ranking a incluir. `None` publica el ranking
            completo.
    """

    def __init__(
        self,
        calibration: Calibration,
        fingerprints: dict[str, str],
        top_k: int | None = None,
    ) -> None:
        """Guarda lo que se repite en todos los mensajes."""
        self._calibration = calibration
        self._fingerprints = fingerprints
        self._top_k = top_k

    def _procedencia(self, zona: str) -> dict[str, Any]:
        """Bajo qué condiciones se decidió, para poder auditarlo después.

        Args:
            zona: Zona de la que se toma el umbral.

        Returns:
            Diccionario serializable con la procedencia.
        """
        cal = self._calibration.zones[zona]
        return {
            "calibracion": self._calibration.version,
            "topologia": self._calibration.topology,
            "perfil": self._calibration.profile,
            "magnitud": self._calibration.magnitude,
            "fuente": cal.frozen.source,
            "sigma_spatial": cal.frozen.sigma_spatial,
            "fpr_target": cal.frozen.config.fpr_target,
            "semilla": cal.frozen.seed,
            "n_instants": cal.frozen.n_instants,
            "fingerprint": self._fingerprints.get(zona, cal.fingerprint),
        }

    def ventana(self, resultado: ZoneResult, emitido: datetime) -> dict[str, Any]:
        """Cuerpo del mensaje de una ventana analizada.

        Args:
            resultado: Zona que produjo ventana.
            emitido: Instante de publicación.

        Returns:
            Diccionario serializable.

        Raises:
            PublishError: Si el resultado no trae ventana ni detección.
        """
        if resultado.window is None or resultado.detection is None:
            raise PublishError(f"'{resultado.zona}' no produjo ventana: nada que publicar")
        return {
            "schema": SCHEMA_VENTANA,
            "zona": resultado.zona,
            "emitido_utc": emitido.isoformat(),
            "ventana": resultado.window.to_dict(),
            "deteccion": resultado.detection.to_dict(top_k=self._top_k),
            "procedencia": self._procedencia(resultado.zona),
        }

    def sin_ventana(self, resultado: ZoneResult, emitido: datetime) -> dict[str, Any]:
        """Cuerpo del mensaje de una zona que no produjo resultado.

        Args:
            resultado: Zona sin datos suficientes.
            emitido: Instante de publicación.

        Returns:
            Diccionario serializable.

        Raises:
            PublishError: Si el resultado no trae motivo.
        """
        if resultado.missing is None:
            raise PublishError(f"'{resultado.zona}' no declara motivo: nada que publicar")
        return {
            "schema": SCHEMA_SIN_VENTANA,
            "zona": resultado.zona,
            "emitido_utc": emitido.isoformat(),
            "sin_ventana": resultado.missing.to_dict(),
            "procedencia": self._procedencia(resultado.zona),
        }


class Publisher(ABC):
    """Adónde van los mensajes.

    Abstracto para que los tests corran el ciclo entero recolectando en
    memoria, sin broker.
    """

    @abstractmethod
    def publish(self, topic: str, payload: dict[str, Any]) -> None:
        """Publica un mensaje.

        Args:
            topic: Topic completo.
            payload: Cuerpo serializable.

        Raises:
            PublishError: Si el mensaje no salió.
        """


class CollectingPublisher(Publisher):
    """Acumula en memoria lo que se publicaría. Para tests y para `--dry-run`."""

    def __init__(self) -> None:
        """Prepara la lista."""
        self.messages: list[tuple[str, dict[str, Any]]] = []

    def publish(self, topic: str, payload: dict[str, Any]) -> None:
        """Guarda el mensaje.

        Args:
            topic: Topic completo.
            payload: Cuerpo serializable.
        """
        self.messages.append((topic, payload))

    def topics(self) -> list[str]:
        """Topics publicados, en orden.

        Returns:
            La lista de topics.
        """
        return [t for t, _ in self.messages]


class CycleDispatcher:
    """Reparte el resultado de un ciclo a los topics que corresponden.

    Args:
        payload: Constructor de cuerpos de mensaje.
        publisher: Adónde van.
        prefix: Raíz de los topics del monitor.
        metrics: Dónde registrar las publicaciones que no salieron. `None`
            no registra nada.
    """

    def __init__(
        self,
        payload: DetectionPayload,
        publisher: Publisher,
        prefix: str,
        metrics: MonitorMetrics | None = None,
    ) -> None:
        """Guarda las piezas."""
        self._payload = payload
        self._publisher = publisher
        self._prefix = prefix.rstrip("/")
        self._metrics = metrics if metrics is not None else NullMetrics()
        self.failures = 0

    def _enviar(self, topic: str, cuerpo: dict[str, Any]) -> None:
        """Publica anotando el fallo en vez de propagarlo.

        Un broker caído no puede tumbar el ciclo de detección: la ventana
        siguiente llega en 6 s y el atraso se acumularía. El fallo queda en
        el contador y en la métrica, porque un monitor que dejó de publicar
        se ve desde afuera igual que uno que no tiene nada que decir.

        Args:
            topic: Topic completo.
            cuerpo: Cuerpo del mensaje.
        """
        try:
            self._publisher.publish(topic, cuerpo)
        except PublishError:
            self.failures += 1
            self._metrics.observe_publish_failure()
            logger.exception("no se pudo publicar en %s", topic)

    def dispatch(self, ciclo: CycleResult, emitido: datetime | None = None) -> int:
        """Publica todo lo que produjo un ciclo.

        Args:
            ciclo: Resultado del ciclo.
            emitido: Instante de publicación. `None` usa el reloj.

        Returns:
            Mensajes que se intentaron publicar.
        """
        momento = emitido if emitido is not None else datetime.now(UTC)
        enviados = 0

        for resultado in ciclo.results:
            if resultado.status == "ventana":
                cuerpo = self._payload.ventana(resultado, momento)
                self._enviar(f"{self._prefix}/ventana/{resultado.zona}", cuerpo)
                enviados += 1
                if resultado.detected:
                    self._enviar(f"{self._prefix}/deteccion/{resultado.zona}", cuerpo)
                    enviados += 1
            elif resultado.status == "sin_datos":
                cuerpo = self._payload.sin_ventana(resultado, momento)
                self._enviar(f"{self._prefix}/sin-ventana/{resultado.zona}", cuerpo)
                enviados += 1

        return enviados


def encode(payload: dict[str, Any]) -> bytes:
    """Serializa un cuerpo para mandarlo por el broker.

    `ensure_ascii=False` para que los nombres de zona y los mensajes en
    español viajen legibles en vez de escapados.

    Args:
        payload: Cuerpo serializable.

    Returns:
        El cuerpo en UTF-8.
    """
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")
