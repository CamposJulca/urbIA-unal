"""Verifica que el perfil congelado siga describiendo la base viva.

El perfil de `data/profiles/` es lo que decide qué desviación es sutil, así
que si la señal deriva y el perfil no, todos los resultados del detector
quedan descritos por un fondo que ya no existe. Esto es lo que lo detecta.

Mismo patrón que la verificación de la topología en `monitor-gsp`: los
tests van marcados `integration` y no corren sin base.

    POSTGRES_HOST=localhost POSTGRES_PASSWORD=... pytest -m integration
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

import pytest

from conftest import PERFIL
from urbia_events import SignalProfile, load_profile
from urbia_events.types import DEVICE_TYPES, MAGNITUDES

if TYPE_CHECKING:
    import psycopg

pytestmark = pytest.mark.integration

TOLERANCIA_RELATIVA = 0.10
"""Cuánto puede derivar el perfil antes de dejar de servir.

Un 10 % es holgado a propósito: la ventana es de 24 h y la señal tiene
variación natural entre días. Lo que este test busca no es ruido de
muestreo, es un cambio de régimen del productor.
"""


def _conexion() -> psycopg.Connection[Any]:
    """Abre la conexión a PostgreSQL, o salta el test si no hay credenciales."""
    import psycopg
    from psycopg.rows import dict_row

    password = os.environ.get("POSTGRES_PASSWORD")
    if not password:
        pytest.skip("sin POSTGRES_PASSWORD: el perfil no se puede recontrastar")
    return psycopg.connect(
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=int(os.environ.get("POSTGRES_PORT", "5432")),
        dbname=os.environ.get("POSTGRES_DB", "urbia"),
        user=os.environ.get("POSTGRES_USER", "urbia"),
        password=password,
        connect_timeout=int(os.environ.get("CONNECT_TIMEOUT_S", "10")),
        row_factory=dict_row,
    )


CONSULTA = """
WITH cortes AS (
    SELECT date_trunc('second', timestamp_utc) AS instante,
           device_type,
           avg({magnitud})      AS media,
           var_samp({magnitud}) AS varianza
    FROM ami_telemetry
    WHERE estado = 'activo'
      AND timestamp_utc > (SELECT max(timestamp_utc) - interval '24 hours' FROM ami_telemetry)
    GROUP BY 1, 2
    HAVING count(*) >= 10
)
SELECT device_type, avg(media) AS media, sqrt(avg(varianza)) AS sigma_espacial
FROM cortes GROUP BY 1
"""


class TestIntegracionPerfil:
    @pytest.fixture(scope="class")
    def vivo(self) -> dict[tuple[str, str], dict[str, float]]:
        """Mide el perfil actual sobre las últimas 24 horas de la base.

        La ventana tiene que ser la misma que la del perfil congelado.
        Corriente y potencia siguen una curva de carga diaria: medido,
        la media de corriente sobre 6 h es 27,4 A contra 21,6 A sobre
        24 h, un 27 % de diferencia que no es deriva sino la hora del
        día. Comparar ventanas distintas haría fallar el test siempre.
        """
        medido: dict[tuple[str, str], dict[str, float]] = {}
        with _conexion() as conn, conn.cursor() as cur:
            for magnitud in MAGNITUDES:
                cur.execute(CONSULTA.format(magnitud=magnitud))
                for fila in cur.fetchall():
                    medido[(magnitud, fila["device_type"])] = {
                        "media": float(fila["media"]),
                        "sigma_espacial": float(fila["sigma_espacial"]),
                    }
        return medido

    def test_el_perfil_congelado_cubre_lo_que_la_base_produce(
        self, vivo: dict[tuple[str, str], dict[str, float]]
    ) -> None:
        congelado = load_profile(PERFIL)
        assert set(vivo) == set(congelado.entries)

    @pytest.mark.parametrize("magnitud", MAGNITUDES)
    @pytest.mark.parametrize("tipo", DEVICE_TYPES)
    def test_la_dispersion_espacial_no_derivo(
        self,
        vivo: dict[tuple[str, str], dict[str, float]],
        magnitud: str,
        tipo: str,
    ) -> None:
        """Si esto falla, el perfil describe un fondo que ya no existe."""
        congelado: SignalProfile = load_profile(PERFIL)
        esperado = congelado.get(magnitud, tipo).sigma_spatial  # type: ignore[arg-type]
        actual = vivo[(magnitud, tipo)]["sigma_espacial"]
        assert actual == pytest.approx(esperado, rel=TOLERANCIA_RELATIVA), (
            f"σ espacial de {magnitud}/{tipo} derivó de {esperado:.4f} a {actual:.4f}: "
            f"rehacer el perfil con experiments/perfil-senal/run.py"
        )

    @pytest.mark.parametrize("magnitud", MAGNITUDES)
    @pytest.mark.parametrize("tipo", DEVICE_TYPES)
    def test_la_media_no_derivo(
        self,
        vivo: dict[tuple[str, str], dict[str, float]],
        magnitud: str,
        tipo: str,
    ) -> None:
        congelado: SignalProfile = load_profile(PERFIL)
        esperado = congelado.get(magnitud, tipo).mean  # type: ignore[arg-type]
        actual = vivo[(magnitud, tipo)]["media"]
        assert actual == pytest.approx(esperado, rel=TOLERANCIA_RELATIVA)
