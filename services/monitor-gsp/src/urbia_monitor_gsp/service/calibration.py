"""Calibración congelada: el archivo versionado y su verificación.

## Por qué se congela

El umbral **no se calibra sobre datos vivos**. Si lo hiciera, una anomalía
que persista se volvería parte de la hipótesis nula: el corte subiría hasta
acomodarla y el detector dejaría de verla. El método quedaría midiendo su
propia desviación en vez de la del sistema, y el fallo sería invisible
—cuanto peor la anomalía, más normal parecería—.

Por eso la hipótesis nula es **sintética**: ruido gaussiano con la σ espacial
del perfil versionado, pasado por el mismo preprocesado que usará en
operación. Es la misma disciplina que ya se aplicó a la topología y al
perfil: lo que sostiene un resultado se versiona.

## El supuesto que esto introduce

Congelar el umbral contra un nulo sintético **supone que la dispersión
espacial de la telemetría real se parece a la que declara el perfil**. Es un
supuesto, no un hecho verificado, y tiene consecuencia directa: si la
dispersión real fuera mayor, la tasa de falsos positivos en operación sería
mayor que el 1 % declarado; si fuera menor, el detector sería más
conservador de lo que dice.

Es medible y no está medido. La forma de medirlo es contrastar la
distribución del estadístico en operación contra la distribución nula
simulada; queda anotado en el README del servicio como limitación, no
enterrado acá.

## Qué verifica el archivo, y por qué cada cosa

Cada zona lleva su umbral, la σ con la que se lo obtuvo, el punto de
operación completo y la **huella de la topología**. `CollectiveScanDetector.
load_threshold` verifica las tres primeras; la huella la verifica el
servicio, porque el detector no conoce el grafo del que salió el suyo.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from ..detector.types import DetectorError, FrozenThreshold
from ..graph.types import MonitorGspError

FORMAT_VERSION: Final = "urbia-calibration-v1"
"""Versión del formato del archivo, no de su contenido."""


class CalibrationError(MonitorGspError, ValueError):
    """El archivo de calibración falta, está mal formado o no corresponde."""


class TopologyMismatchError(MonitorGspError, RuntimeError):
    """El grafo vivo no es el grafo con el que se calibró.

    **Es bloqueante a propósito.** Un umbral calibrado sobre otra topología
    produce detecciones que no corresponden al sistema real, y no hay forma
    de notarlo mirando la salida: los números siguen saliendo, con la misma
    pinta de siempre. Seguir andando sería peor que no andar.

    Attributes:
        diferencias: Por zona, el par `(esperada, viva)` de huellas que no
            coincidieron.
        faltantes: Zonas que la calibración declara y el grafo vivo no tiene.
        sobrantes: Zonas que el grafo vivo tiene y la calibración no declara.
    """

    def __init__(
        self,
        diferencias: dict[str, tuple[str, str]],
        faltantes: tuple[str, ...],
        sobrantes: tuple[str, ...],
    ) -> None:
        """Inicializa el desajuste con su detalle.

        Args:
            diferencias: Huellas que no coincidieron, por zona.
            faltantes: Zonas de la calibración ausentes del grafo vivo.
            sobrantes: Zonas del grafo vivo ausentes de la calibración.
        """
        self.diferencias = diferencias
        self.faltantes = faltantes
        self.sobrantes = sobrantes

        partes: list[str] = []
        if diferencias:
            detalle = ", ".join(
                f"{zona} (calibrada {esperada[:8]}, viva {viva[:8]})"
                for zona, (esperada, viva) in sorted(diferencias.items())
            )
            partes.append(f"topología cambiada en {detalle}")
        if faltantes:
            partes.append(f"zonas calibradas que ya no existen: {', '.join(faltantes)}")
        if sobrantes:
            partes.append(f"zonas nuevas sin calibrar: {', '.join(sobrantes)}")

        super().__init__(
            f"el grafo vivo no es el que se calibró — {'; '.join(partes)}. "
            f"Las detecciones dejarían de corresponder al sistema real. "
            f"Recalibrá con scripts/calibracion/congelar_umbrales.py y volvé a "
            f"desplegar; no hay forma segura de seguir con el umbral viejo"
        )


@dataclass(frozen=True, slots=True)
class ZoneCalibration:
    """Calibración de una zona.

    Attributes:
        frozen: Umbral con sus condiciones.
        fingerprint: Huella de la topología sobre la que se calibró.
        n_meters: Medidores de la zona al calibrar. Redundante con la
            huella y se guarda igual: un mensaje de error que dice "25
            contra 26" se entiende, uno que dice "a1b2 contra c3d4" no.
    """

    frozen: FrozenThreshold
    fingerprint: str
    n_meters: int

    def to_dict(self) -> dict[str, Any]:
        """Serializa la calibración de la zona.

        Returns:
            Diccionario serializable.
        """
        return {
            **self.frozen.to_dict(),
            "fingerprint": self.fingerprint,
            "n_meters": self.n_meters,
        }

    @classmethod
    def from_dict(cls, datos: dict[str, Any]) -> ZoneCalibration:
        """Reconstruye la calibración de una zona.

        Args:
            datos: Diccionario con la forma que produce `to_dict`.

        Returns:
            La calibración.

        Raises:
            CalibrationError: Si falta alguna clave o el umbral está mal
                formado.
        """
        try:
            return cls(
                frozen=FrozenThreshold.from_dict(datos),
                fingerprint=str(datos["fingerprint"]),
                n_meters=int(datos["n_meters"]),
            )
        except (KeyError, TypeError, ValueError, DetectorError) as exc:
            raise CalibrationError(f"calibración de zona mal formada: {exc}") from exc


@dataclass(frozen=True, slots=True)
class Calibration:
    """El archivo de calibración completo.

    Attributes:
        version: Etiqueta de contenido, del estilo `manizales-scan-v1`.
        magnitude: Magnitud sobre la que se calibró. Todo lo medido del
            detector está sobre `voltaje_v`; corriente y potencia tienen
            σ/media del 35 % y están sin evaluar.
        profile: Perfil del que salió σ.
        topology: Topología sobre la que se construyó el grafo.
        zones: Calibración por zona.
        notes: Texto libre con lo que haga falta saber para leer esto.
        validation: Falsas alarmas medidas contra señal nula **con otra
            semilla** que la de calibración, por zona. Viaja con el umbral
            a propósito: la pregunta operativa no es "1 % de qué" sino
            cuántas alarmas por hora hay que esperar sin que pase nada, y
            esa cifra sólo significa algo al lado del corte que la produjo.
    """

    version: str
    magnitude: str
    profile: str
    topology: str
    zones: dict[str, ZoneCalibration]
    notes: str = ""
    validation: dict[str, dict[str, float]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serializa el archivo entero.

        Returns:
            Diccionario serializable.
        """
        return {
            "format": FORMAT_VERSION,
            "version": self.version,
            "magnitude": self.magnitude,
            "profile": self.profile,
            "topology": self.topology,
            "notes": self.notes,
            "validation": self.validation,
            "zones": {zona: cal.to_dict() for zona, cal in sorted(self.zones.items())},
        }

    @classmethod
    def from_dict(cls, datos: dict[str, Any]) -> Calibration:
        """Reconstruye la calibración completa.

        Args:
            datos: Diccionario con la forma que produce `to_dict`.

        Returns:
            La calibración.

        Raises:
            CalibrationError: Si el formato no es el esperado o falta algo.
        """
        formato = datos.get("format")
        if formato != FORMAT_VERSION:
            raise CalibrationError(
                f"formato de calibración desconocido: {formato!r}, se esperaba {FORMAT_VERSION!r}"
            )
        try:
            zonas = {
                str(zona): ZoneCalibration.from_dict(crudo)
                for zona, crudo in datos["zones"].items()
            }
        except (KeyError, TypeError, AttributeError) as exc:
            raise CalibrationError(f"calibración mal formada: {exc}") from exc

        if not zonas:
            raise CalibrationError("la calibración no declara ninguna zona")

        return cls(
            version=str(datos.get("version", "")),
            magnitude=str(datos.get("magnitude", "")),
            profile=str(datos.get("profile", "")),
            topology=str(datos.get("topology", "")),
            zones=zonas,
            notes=str(datos.get("notes", "")),
            validation=dict(datos.get("validation") or {}),
        )

    def verify_topology(self, fingerprints: dict[str, str]) -> None:
        """Contrasta la topología viva contra la que se calibró.

        Args:
            fingerprints: Huella por zona del grafo recién construido.

        Raises:
            TopologyMismatchError: Si alguna zona falta, sobra o cambió.
        """
        diferencias = {
            zona: (cal.fingerprint, fingerprints[zona])
            for zona, cal in self.zones.items()
            if zona in fingerprints and fingerprints[zona] != cal.fingerprint
        }
        faltantes = tuple(sorted(z for z in self.zones if z not in fingerprints))
        sobrantes = tuple(sorted(z for z in fingerprints if z not in self.zones))

        if diferencias or faltantes or sobrantes:
            raise TopologyMismatchError(diferencias, faltantes, sobrantes)


def load_calibration(path: Path) -> Calibration:
    """Lee el archivo de calibración versionado.

    Args:
        path: Ruta del archivo.

    Returns:
        La calibración.

    Raises:
        CalibrationError: Si el archivo no existe o no se puede leer como
            la calibración esperada.
    """
    try:
        crudo = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CalibrationError(
            f"no existe la calibración en {path}: el servicio no puede arrancar sin "
            f"umbral, y calibrar en caliente sobre datos vivos volvería normal a "
            f"cualquier anomalía persistente. Generala con "
            f"scripts/calibracion/congelar_umbrales.py"
        ) from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise CalibrationError(f"no se pudo leer la calibración en {path}: {exc}") from exc

    if not isinstance(crudo, dict):
        raise CalibrationError(f"la calibración en {path} no es un objeto JSON")
    return Calibration.from_dict(crudo)


def save_calibration(calibration: Calibration, path: Path) -> None:
    """Escribe el archivo de calibración, ordenado y estable.

    Ordenado y con salto final para que dos corridas idénticas produzcan
    bytes idénticos y el diff de git muestre sólo lo que cambió de verdad.

    Args:
        calibration: Calibración a escribir.
        path: Destino.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    texto = json.dumps(calibration.to_dict(), indent=2, ensure_ascii=False, sort_keys=True)
    path.write_text(texto + "\n", encoding="utf-8")
