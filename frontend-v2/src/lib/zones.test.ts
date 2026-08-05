import { describe, it, expect } from 'vitest';
import { colorForZone, labelForZone, ZONE_COLOR, ZONE_FALLBACK } from './zones';
import { KNOWN_ZONES } from '@/api/types';

describe('colorForZone', () => {
  it('devuelve color mapeado para zonas conocidas', () => {
    expect(colorForZone('centro')).toBe(ZONE_COLOR.centro);
    expect(colorForZone('chipre')).toBe(ZONE_COLOR.chipre);
    expect(colorForZone('la_enea')).toBe(ZONE_COLOR.la_enea);
  });

  it('cubre todas las zonas del esquema v2', () => {
    // Si KNOWN_ZONES crece y ZONE_COLOR no, las series por zona del
    // grafico quedarian con stroke undefined.
    for (const z of KNOWN_ZONES) {
      expect(colorForZone(z)).not.toBe(ZONE_FALLBACK);
    }
  });

  it('devuelve fallback para zona desconocida', () => {
    expect(colorForZone('zona_fantasia')).toBe(ZONE_FALLBACK);
  });

  it('devuelve fallback para null/undefined', () => {
    expect(colorForZone(null)).toBe(ZONE_FALLBACK);
    expect(colorForZone(undefined)).toBe(ZONE_FALLBACK);
  });
});

describe('labelForZone', () => {
  it('devuelve label legible para zonas conocidas', () => {
    expect(labelForZone('centro')).toBe('Centro');
    expect(labelForZone('la_enea')).toBe('La Enea');
    expect(labelForZone('universitario')).toBe('Universitario');
  });

  it('devuelve el string crudo para zona desconocida', () => {
    expect(labelForZone('zona_fantasia')).toBe('zona_fantasia');
  });

  it('devuelve "Sin zona" para null/undefined', () => {
    expect(labelForZone(null)).toBe('Sin zona');
    expect(labelForZone(undefined)).toBe('Sin zona');
  });
});
