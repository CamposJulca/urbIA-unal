import pytest
import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from payload_validator import PayloadValidator

v = PayloadValidator()

def payload_valido():
    ahora = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    return {
        "device_id":       "urbia-cen-mono-0001",
        "device_type":     "mono",
        "zona":            "centro",
        "timestamp_utc":   ahora,
        "voltaje_v":       220.5,
        "corriente_a":     5.2,
        "potencia_kw":     round(220.5 * 5.2 * 0.95 / 1000, 4),
        "frecuencia_hz":   60.1,
        "factor_potencia": 0.95,
        "lat":             5.0680,
        "lon":             -75.5120,
        "estado":          "activo",
        "nodo_origen":     "192.168.0.103",
        "lenguaje":        "python",
        "seed":            42
    }

# ── Positivos ────────────────────────────────────────────────────
def test_payload_valido_completo():
    ok, msg = v.validar(payload_valido())
    assert ok, f"Rechazado: {msg}"

def test_payload_trifasico_valido():
    p = payload_valido()
    p.update({
        "device_id":       "urbia-ena-tri-0001",
        "device_type":     "trifasico",
        "zona":            "la_enea",
        "corriente_a":     25.0,
        "factor_potencia": 0.88,
        "potencia_kw":     round(220.5 * 25.0 * 0.88 / 1000, 4),
        "nodo_origen":     "192.168.0.104",
        "lenguaje":        "cpp"
    })
    ok, msg = v.validar(p)
    assert ok, f"Rechazado: {msg}"

def test_todos_los_estados_validos():
    estados = ["activo","falla","mantenimiento","anomalia_voltaje","anomalia_frecuencia","corte","desconectado"]
    for estado in estados:
        p = payload_valido(); p["estado"] = estado
        ok, msg = v.validar(p)
        assert ok, f"Estado '{estado}' rechazado: {msg}"

def test_todas_las_zonas_validas():
    mapa = {"centro":"cen","chipre":"chi","la_enea":"ena","palermo":"pal","palogrande":"pgr","universitario":"uni"}
    for zona, cod in mapa.items():
        p = payload_valido()
        p["zona"] = zona
        p["device_id"] = f"urbia-{cod}-mono-0001"
        ok, msg = v.validar(p)
        assert ok, f"Zona '{zona}' rechazada: {msg}"

# ── Negativos ────────────────────────────────────────────────────
def test_falta_campo_requerido():
    p = payload_valido(); del p["device_id"]
    ok, _ = v.validar(p); assert not ok

def test_device_id_formato_invalido():
    p = payload_valido(); p["device_id"] = "medidor-001"
    ok, _ = v.validar(p); assert not ok

def test_voltaje_fuera_de_rango():
    p = payload_valido(); p["voltaje_v"] = 300.0
    ok, _ = v.validar(p); assert not ok

def test_frecuencia_fuera_de_rango():
    p = payload_valido(); p["frecuencia_hz"] = 55.0
    ok, _ = v.validar(p); assert not ok

def test_zona_invalida():
    p = payload_valido(); p["zona"] = "bogota"
    ok, _ = v.validar(p); assert not ok

def test_nodo_origen_invalido():
    p = payload_valido(); p["nodo_origen"] = "192.168.0.200"
    ok, _ = v.validar(p); assert not ok

def test_coordenadas_fuera_de_manizales():
    p = payload_valido(); p["lat"] = 4.60; p["lon"] = -74.08
    ok, _ = v.validar(p); assert not ok

def test_campo_adicional_no_permitido():
    p = payload_valido(); p["campo_extra"] = "no_permitido"
    ok, _ = v.validar(p); assert not ok

def test_estadisticas():
    vv = PayloadValidator()
    vv.validar(payload_valido())
    p_malo = payload_valido(); del p_malo["device_id"]
    vv.validar(p_malo)
    s = vv.estadisticas()
    assert s["total_procesados"] == 2
    assert s["validos"] == 1
    assert s["errores"] == 1
    assert s["tasa_exito_pct"] == 50.0
