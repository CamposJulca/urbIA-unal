"""Tests del medidor AMI virtual y del schema de telemetría."""

from __future__ import annotations

import re
import time
from datetime import datetime

import pytest
from pydantic import ValidationError

from urbia_simulator.meter import (
    CURRENT_MAX,
    CURRENT_MIN,
    FREQUENCY_MAX,
    FREQUENCY_MIN,
    METER_ID_REGEX,
    POWER_FACTOR_MAX,
    POWER_FACTOR_MIN,
    VALID_ZONES,
    VOLTAGE_MAX,
    VOLTAGE_MIN,
    Meter,
    TelemetryPayload,
    build_meter_id,
    zone_for_index,
)


SAMPLE_SIZE = 200


# --- Rangos de magnitudes eléctricas ----------------------------------

def test_meter_generates_valid_voltage() -> None:
    meter = Meter(1)
    for _ in range(SAMPLE_SIZE):
        reading = meter.generate_reading()
        v = reading["voltage_v"]
        assert isinstance(v, float)
        assert VOLTAGE_MIN <= v <= VOLTAGE_MAX, f"voltage_v fuera de rango: {v}"


def test_meter_generates_valid_current() -> None:
    meter = Meter(1)
    for _ in range(SAMPLE_SIZE):
        reading = meter.generate_reading()
        a = reading["current_a"]
        assert isinstance(a, float)
        assert CURRENT_MIN <= a <= CURRENT_MAX, f"current_a fuera de rango: {a}"


def test_meter_generates_valid_frequency() -> None:
    meter = Meter(1)
    for _ in range(SAMPLE_SIZE):
        reading = meter.generate_reading()
        hz = reading["frequency_hz"]
        assert isinstance(hz, float)
        assert FREQUENCY_MIN <= hz <= FREQUENCY_MAX, (
            f"frequency_hz fuera de rango: {hz}"
        )


def test_meter_generates_valid_power_factor() -> None:
    meter = Meter(1)
    for _ in range(SAMPLE_SIZE):
        reading = meter.generate_reading()
        pf = reading["power_factor"]
        assert isinstance(pf, float)
        assert POWER_FACTOR_MIN <= pf <= POWER_FACTOR_MAX, (
            f"power_factor fuera de rango: {pf}"
        )


# --- Estructura del payload -------------------------------------------

EXPECTED_KEYS: frozenset[str] = frozenset({
    "meter_id",
    "timestamp",
    "voltage_v",
    "current_a",
    "power_kw",
    "energy_kwh",
    "frequency_hz",
    "power_factor",
    "zone",
    "status",
})


def test_payload_matches_schema() -> None:
    """Todos los campos del schema están presentes con tipos correctos
    y el payload pasa validación de Pydantic."""
    meter = Meter(1)
    reading = meter.generate_reading()

    assert set(reading.keys()) == EXPECTED_KEYS, (
        f"diferencia de claves: {set(reading.keys()) ^ EXPECTED_KEYS}"
    )
    assert isinstance(reading["meter_id"], str)
    assert isinstance(reading["timestamp"], str)
    assert isinstance(reading["voltage_v"], float)
    assert isinstance(reading["current_a"], float)
    assert isinstance(reading["power_kw"], float)
    assert isinstance(reading["energy_kwh"], float)
    assert isinstance(reading["frequency_hz"], float)
    assert isinstance(reading["power_factor"], float)
    assert isinstance(reading["zone"], str)
    assert isinstance(reading["status"], str)

    # El payload debe pasar Pydantic sin levantar excepción.
    TelemetryPayload.model_validate(reading)


# --- Energía acumulada ------------------------------------------------

def test_energy_kwh_is_monotonic() -> None:
    """La energía acumulada nunca disminuye entre lecturas sucesivas."""
    meter = Meter(1)
    prev = meter.generate_reading()["energy_kwh"]
    for _ in range(20):
        time.sleep(0.01)
        current = meter.generate_reading()["energy_kwh"]
        assert current >= prev, (
            f"energy_kwh decreció: {prev} → {current}"
        )
        prev = current


def test_energy_kwh_actually_grows_when_consuming() -> None:
    """Si esperamos lo suficiente y hay potencia >0, la energía crece."""
    meter = Meter(1)
    meter.generate_reading()  # primera lectura inicializa el reloj
    time.sleep(0.1)
    second = meter.generate_reading()
    assert second["energy_kwh"] > 0.0 or second["power_kw"] == 0.0


# --- meter_id ---------------------------------------------------------

def test_meter_id_format() -> None:
    """Todos los meter_id generados cumplen el regex AMI-MNZ-NNNNN."""
    pattern = re.compile(METER_ID_REGEX)
    for idx in (1, 2, 10, 99, 9999, 99999):
        meter = Meter(idx)
        assert pattern.match(meter.meter_id), (
            f"meter_id {meter.meter_id!r} no matchea {METER_ID_REGEX}"
        )


def test_meter_id_deterministic() -> None:
    """Mismo index → mismo meter_id, entre instancias y reinicios."""
    assert build_meter_id(1) == "AMI-MNZ-00001"
    assert build_meter_id(10) == "AMI-MNZ-00010"
    assert build_meter_id(42) == "AMI-MNZ-00042"
    assert Meter(7).meter_id == Meter(7).meter_id


def test_meter_id_distinct_across_n_meters() -> None:
    """N medidores producen N meter_id distintos."""
    ids = [Meter(i).meter_id for i in range(1, 11)]
    assert len(set(ids)) == 10
    assert ids[0] == "AMI-MNZ-00001"
    assert ids[-1] == "AMI-MNZ-00010"


def test_build_meter_id_rejects_out_of_range() -> None:
    with pytest.raises(ValueError):
        build_meter_id(0)
    with pytest.raises(ValueError):
        build_meter_id(100000)


# --- zone -------------------------------------------------------------

def test_zone_in_valid_enum() -> None:
    """Todas las lecturas reportan una zona del enum permitido."""
    for idx in range(1, 11):
        meter = Meter(idx)
        reading = meter.generate_reading()
        assert reading["zone"] in VALID_ZONES, (
            f"zone {reading['zone']!r} fuera del enum"
        )


def test_zone_two_meters_per_zone_when_n_is_10() -> None:
    """Con 10 medidores hay exactamente 2 medidores por zona."""
    zones = [zone_for_index(i) for i in range(1, 11)]
    counts: dict[str, int] = {}
    for z in zones:
        counts[z] = counts.get(z, 0) + 1
    assert set(counts.keys()) == {
        "MNZ-CENTRO", "MNZ-NORTE", "MNZ-SUR", "MNZ-ESTE", "MNZ-OESTE",
    }
    assert all(v == 2 for v in counts.values()), counts


def test_zone_stable_across_instances() -> None:
    """zone_for_index es determinístico para el mismo índice."""
    for idx in range(1, 21):
        assert zone_for_index(idx) == zone_for_index(idx)
        # También vía la instancia.
        assert Meter(idx).zone == zone_for_index(idx)


# --- Derivaciones físicas y schema strict ------------------------------

def test_power_kw_is_derived_from_v_i_pf() -> None:
    """power_kw ≈ voltage_v * current_a * power_factor / 1000."""
    meter = Meter(1)
    reading = meter.generate_reading()
    expected = (
        reading["voltage_v"]
        * reading["current_a"]
        * reading["power_factor"]
        / 1000.0
    )
    # Tolerancia por redondeo a 3 decimales en cada componente.
    assert abs(reading["power_kw"] - expected) <= 0.05, (
        f"power_kw={reading['power_kw']} vs esperado≈{expected:.5f}"
    )


def test_status_is_normal_in_v1() -> None:
    meter = Meter(1)
    for _ in range(50):
        assert meter.generate_reading()["status"] == "NORMAL"


def test_timestamp_is_iso8601_utc_with_ms() -> None:
    """timestamp tiene formato YYYY-MM-DDTHH:MM:SS.sssZ."""
    meter = Meter(1)
    ts: str = meter.generate_reading()["timestamp"]  # type: ignore[assignment]
    assert ts.endswith("Z"), f"timestamp no termina en Z: {ts}"
    # Pydantic-friendly parseable como ISO 8601 (reemplazo Z→+00:00).
    parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    assert parsed.tzinfo is not None


def test_payload_rejects_invalid_voltage() -> None:
    """El validador rechaza valores fuera de rango."""
    base = {
        "meter_id": "AMI-MNZ-00001",
        "timestamp": "2026-05-04T18:00:00.000Z",
        "voltage_v": 999.0,  # fuera de [100, 130]
        "current_a": 8.0,
        "power_kw": 1.0,
        "energy_kwh": 0.0,
        "frequency_hz": 60.0,
        "power_factor": 0.95,
        "zone": "MNZ-CENTRO",
        "status": "NORMAL",
    }
    with pytest.raises(ValidationError):
        TelemetryPayload.model_validate(base)


def test_payload_rejects_unknown_zone() -> None:
    base = {
        "meter_id": "AMI-MNZ-00001",
        "timestamp": "2026-05-04T18:00:00.000Z",
        "voltage_v": 120.0,
        "current_a": 8.0,
        "power_kw": 1.0,
        "energy_kwh": 0.0,
        "frequency_hz": 60.0,
        "power_factor": 0.95,
        "zone": "MNZ-INEXISTENTE",
        "status": "NORMAL",
    }
    with pytest.raises(ValidationError):
        TelemetryPayload.model_validate(base)
