"""Carga del perfil de señal medido.

El perfil dice **dónde vive la señal en la práctica**, y es lo que le da
significado a la magnitud de un evento: sin él, una desviación del 5 % es
un número sin interpretación, porque son 2,5σ en voltaje y 0,14σ en
corriente.

Se lee de `data/profiles/`, no se recalcula desde la base: un experimento
tiene que ser reproducible sin acceso al cluster. La verificación de que
el perfil congelado sigue describiendo la base viva es un test de
integración aparte, igual que con la topología.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .types import (
    DEVICE_TYPES,
    MAGNITUDES,
    DeviceType,
    InvalidSpecError,
    Magnitude,
    MagnitudeProfile,
)


@dataclass(frozen=True, slots=True, eq=False)
class SignalProfile:
    """Perfil de la señal AMI en operación normal.

    Attributes:
        version: Versión declarada del perfil.
        window_start_utc: Inicio de la ventana de medición.
        window_end_utc: Fin de la ventana de medición.
        zone_to_device_type: Tipo de medidor de cada zona. En esta
            topología cada zona es enteramente de un tipo, así que
            `device_type` y `zona` están perfectamente confundidos: nada
            observado puede atribuirse a uno sin confundirlo con el otro.
        entries: Perfil por magnitud y tipo de medidor.
    """

    version: str
    window_start_utc: str
    window_end_utc: str
    zone_to_device_type: dict[str, DeviceType] = field(default_factory=dict)
    entries: dict[tuple[Magnitude, DeviceType], MagnitudeProfile] = field(default_factory=dict)

    def get(self, magnitude: Magnitude, device_type: DeviceType) -> MagnitudeProfile:
        """Devuelve el perfil de una magnitud para un tipo de medidor.

        Args:
            magnitude: Magnitud buscada.
            device_type: Tipo de medidor.

        Returns:
            El perfil correspondiente.

        Raises:
            InvalidSpecError: Si el perfil no cubre esa combinación.
        """
        try:
            return self.entries[(magnitude, device_type)]
        except KeyError:
            disponibles = sorted(f"{m}/{t}" for m, t in self.entries)
            raise InvalidSpecError(
                f"el perfil '{self.version}' no cubre '{magnitude}' para "
                f"'{device_type}'. Disponibles: {', '.join(disponibles)}"
            ) from None

    def sigma_spatial(self, magnitude: Magnitude, device_type: DeviceType) -> float:
        """Dispersión entre medidores en un mismo instante.

        Args:
            magnitude: Magnitud buscada.
            device_type: Tipo de medidor.

        Returns:
            La desviación espacial, en las unidades de la magnitud.
        """
        return self.get(magnitude, device_type).sigma_spatial


def _entrada(datos: dict[str, Any], magnitude: Magnitude, tipo: DeviceType) -> MagnitudeProfile:
    """Construye un `MagnitudeProfile` desde el JSON.

    Args:
        datos: Diccionario de esa magnitud y tipo.
        magnitude: Magnitud descrita.
        tipo: Tipo de medidor.

    Returns:
        El perfil ya validado.
    """
    return MagnitudeProfile(
        magnitude=magnitude,
        device_type=tipo,
        mean=float(datos["media"]),
        sigma_spatial=float(datos["sigma_espacial"]),
        sigma_pooled=float(datos["sigma_agrupada"]),
        p1=float(datos["p1"]),
        p99=float(datos["p99"]),
        minimum_observed=float(datos["minimo_observado"]),
        maximum_observed=float(datos["maximo_observado"]),
    )


def load_profile(path: Path) -> SignalProfile:
    """Lee un perfil congelado desde su JSON.

    Args:
        path: Ruta al archivo de `data/profiles/`.

    Returns:
        El perfil cargado.

    Raises:
        InvalidSpecError: Si el archivo no trae ninguna magnitud conocida.
    """
    datos = json.loads(path.read_text(encoding="utf-8"))
    entradas: dict[tuple[Magnitude, DeviceType], MagnitudeProfile] = {}
    for magnitude in MAGNITUDES:
        por_tipo = datos.get("magnitudes", {}).get(magnitude, {})
        for tipo in DEVICE_TYPES:
            if tipo in por_tipo:
                entradas[(magnitude, tipo)] = _entrada(por_tipo[tipo], magnitude, tipo)

    if not entradas:
        raise InvalidSpecError(
            f"el perfil {path} no contiene ninguna de las magnitudes conocidas "
            f"({', '.join(MAGNITUDES)})"
        )

    ventana = datos.get("ventana", {})
    return SignalProfile(
        version=str(datos.get("version", "desconocida")),
        window_start_utc=str(ventana.get("inicio_utc", "")),
        window_end_utc=str(ventana.get("fin_utc", "")),
        zone_to_device_type=dict(datos.get("zona_a_device_type", {})),
        entries=entradas,
    )
