import { describe, it, expect } from 'vitest';
import { colorForZone, labelForZone, ZONE_COLOR, ZONE_FALLBACK } from './zones';

describe('colorForZone', () => {
  it('devuelve color mapeado para zonas conocidas', () => {
    expect(colorForZone('MNZ-CENTRO')).toBe(ZONE_COLOR['MNZ-CENTRO']);
    expect(colorForZone('MNZ-NORTE')).toBe(ZONE_COLOR['MNZ-NORTE']);
    expect(colorForZone('MNZ-SUR')).toBe(ZONE_COLOR['MNZ-SUR']);
  });

  it('devuelve fallback para zona desconocida', () => {
    expect(colorForZone('MNZ-FANTASIA')).toBe(ZONE_FALLBACK);
  });

  it('devuelve fallback para null/undefined', () => {
    expect(colorForZone(null)).toBe(ZONE_FALLBACK);
    expect(colorForZone(undefined)).toBe(ZONE_FALLBACK);
  });
});

describe('labelForZone', () => {
  it('devuelve label legible para zonas conocidas', () => {
    expect(labelForZone('MNZ-CENTRO')).toBe('Centro');
    expect(labelForZone('MNZ-NORTE')).toBe('Norte');
    expect(labelForZone('MNZ-OESTE')).toBe('Oeste');
  });

  it('devuelve el string crudo para zona desconocida', () => {
    expect(labelForZone('MNZ-FANTASIA')).toBe('MNZ-FANTASIA');
  });

  it('devuelve "Sin zona" para null/undefined', () => {
    expect(labelForZone(null)).toBe('Sin zona');
    expect(labelForZone(undefined)).toBe('Sin zona');
  });
});
