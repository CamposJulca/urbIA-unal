import { describe, it, expect } from 'vitest';
import {
  METER_STATUSES,
  METER_STATUS_FAULT,
  statusLabel,
  statusTone,
} from './status';

describe('statusTone', () => {
  it('verde solo para activo', () => {
    expect(statusTone('activo')).toBe('success');
    const otros = METER_STATUSES.filter((s) => s !== 'activo');
    for (const s of otros) {
      expect(statusTone(s)).not.toBe('success');
    }
  });

  it('ambar para mantenimiento', () => {
    expect(statusTone('mantenimiento')).toBe('warning');
  });

  it('rojo para los cinco estados de falla', () => {
    expect(METER_STATUS_FAULT).toHaveLength(5);
    for (const s of METER_STATUS_FAULT) {
      expect(statusTone(s)).toBe('danger');
    }
  });

  it('rojo para un estado fuera del enum', () => {
    // Preferimos un falso rojo visible a pintar de verde algo que este
    // frontend no sabe interpretar.
    expect(statusTone('estado_futuro')).toBe('danger');
  });

  it('neutral para null/undefined', () => {
    expect(statusTone(null)).toBe('neutral');
    expect(statusTone(undefined)).toBe('neutral');
  });
});

describe('statusLabel', () => {
  it('reemplaza guiones bajos', () => {
    expect(statusLabel('anomalia_voltaje')).toBe('anomalia voltaje');
    expect(statusLabel('activo')).toBe('activo');
  });

  it('etiqueta explicita para null', () => {
    expect(statusLabel(null)).toBe('Sin clasificar');
  });
});
