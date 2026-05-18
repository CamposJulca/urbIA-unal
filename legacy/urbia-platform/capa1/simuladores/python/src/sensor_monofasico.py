from sensor_base import SensorBase


class SensorMonofasico(SensorBase):
    """
    Simulador de medidor monofásico.
    Voltaje nominal: 220V · Corriente: 0–20A · Uso: residencial
    Zonas: Centro histórico y Chipre — Manizales
    """

    VOLTAJE_NOMINAL  = 220.0
    CORRIENTE_MAX    = 20.0
    FRECUENCIA_NOM   = 60.0

    def _generar_valores(self) -> dict:
        factor = self._perfil_horario()

        # Voltaje: 220V ±5% con ruido gaussiano
        voltaje = float(self.rng.normal(
            self.VOLTAJE_NOMINAL,
            self.VOLTAJE_NOMINAL * 0.02
        ))
        voltaje = max(198.0, min(242.0, voltaje))

        # Corriente según perfil horario
        corriente = float(self.rng.uniform(
            self.CORRIENTE_MAX * factor * 0.3,
            self.CORRIENTE_MAX * factor
        ))
        corriente = max(0.0, min(self.CORRIENTE_MAX, corriente))

        # Factor de potencia residencial
        fp = float(self.rng.uniform(0.88, 0.98))

        # Frecuencia: 60Hz ±0.3Hz
        frecuencia = float(self.rng.normal(self.FRECUENCIA_NOM, 0.15))
        frecuencia = max(59.0, min(61.0, frecuencia))

        # Potencia activa
        potencia_kw = voltaje * corriente * fp / 1000.0

        # Estado: 98% activo, 1% anomalía voltaje, 1% falla
        r = float(self.rng.random())
        if r < 0.01:
            estado = "anomalia_voltaje"
            voltaje = float(self.rng.uniform(243.0, 250.0))
        elif r < 0.02:
            estado = "falla"
        else:
            estado = "activo"

        return {
            "voltaje_v":       voltaje,
            "corriente_a":     corriente,
            "potencia_kw":     potencia_kw,
            "frecuencia_hz":   frecuencia,
            "factor_potencia": fp,
            "estado":          estado,
        }
