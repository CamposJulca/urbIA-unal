"""Carga de los límites duros desde el contrato del productor.

Los límites salen de `data/schemas/payload_schema_v1.json`, la copia
versionada del JSON Schema contra el que el `PayloadValidator` del
simulador valida **antes** de publicar. Un valor fuera de ese rango no
llega al broker: no es improbable, es que no existe.

Se leen del archivo y no se escriben acá a mano. Un límite hardcodeado se
desincroniza del contrato en silencio, y una afirmación del tipo "ningún
medidor salió del rango del esquema" dejaría de ser verificable.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .types import MAGNITUDES, InvalidSpecError, Magnitude, SignalBounds


def _limite(propiedades: dict[str, Any], magnitude: Magnitude, clave: str) -> float:
    """Extrae un límite del JSON Schema.

    Args:
        propiedades: Bloque `properties` del esquema.
        magnitude: Magnitud buscada.
        clave: `"minimum"` o `"maximum"`.

    Returns:
        El límite declarado.

    Raises:
        InvalidSpecError: Si la magnitud o el límite no están declarados.
    """
    if magnitude not in propiedades:
        raise InvalidSpecError(
            f"el esquema no declara la magnitud '{magnitude}': sin límite declarado "
            f"no se puede garantizar que un evento no saque al medidor del contrato"
        )
    if clave not in propiedades[magnitude]:
        raise InvalidSpecError(f"el esquema declara '{magnitude}' pero sin '{clave}'")
    return float(propiedades[magnitude][clave])


def load_bounds(path: Path) -> dict[Magnitude, SignalBounds]:
    """Lee los límites de las magnitudes desde el JSON Schema del productor.

    Args:
        path: Ruta a `data/schemas/payload_schema_v1.json`.

    Returns:
        Los límites indexados por magnitud.

    Raises:
        InvalidSpecError: Si el esquema no declara alguna magnitud o algún
            límite.
    """
    esquema = json.loads(path.read_text(encoding="utf-8"))
    propiedades = esquema.get("properties", {})
    return {
        magnitude: SignalBounds(
            magnitude=magnitude,
            minimum=_limite(propiedades, magnitude, "minimum"),
            maximum=_limite(propiedades, magnitude, "maximum"),
        )
        for magnitude in MAGNITUDES
    }
