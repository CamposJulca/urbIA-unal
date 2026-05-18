import { describe, it, expect, beforeAll, afterAll, vi } from 'vitest';
import { formatNumber, formatRelative, formatClock, ageSeconds } from './format';

describe('formatNumber', () => {
  it('devuelve guion para null', () => {
    expect(formatNumber(null)).toBe('—');
  });

  it('devuelve guion para undefined', () => {
    expect(formatNumber(undefined)).toBe('—');
  });

  it('devuelve guion para NaN', () => {
    expect(formatNumber(Number.NaN)).toBe('—');
  });

  it('formatea con los digitos pedidos (default 2)', () => {
    expect(formatNumber(120.5)).toMatch(/120[,.]50/);
  });

  it('respeta el numero de digitos solicitado', () => {
    expect(formatNumber(7.123456, 3)).toMatch(/7[,.]123/);
  });

  it('redondea valores grandes', () => {
    expect(formatNumber(1234.5678, 1)).toMatch(/1[.,]?234[,.]6/);
  });
});

describe('formatRelative', () => {
  it('devuelve guion para entrada vacia', () => {
    expect(formatRelative(null)).toBe('—');
    expect(formatRelative(undefined)).toBe('—');
  });

  it('devuelve guion para string invalido', () => {
    expect(formatRelative('no-es-fecha')).toBe('—');
  });

  it('para una fecha valida arranca con "hace"', () => {
    const iso = new Date(Date.now() - 5_000).toISOString();
    expect(formatRelative(iso)).toMatch(/^hace /);
  });
});

describe('formatClock', () => {
  it('devuelve HH:MM:SS para fecha valida', () => {
    const iso = '2026-05-17T12:34:56Z';
    expect(formatClock(iso)).toMatch(/^\d{2}:\d{2}:\d{2}$/);
  });

  it('devuelve un marcador para fecha no valida (no lanza)', () => {
    // parseISO retorna Invalid Date y toLocaleTimeString lo serializa
    // como 'Invalid Date' sin lanzar. Documentamos el comportamiento.
    expect(formatClock('basura')).toBe('Invalid Date');
  });
});

describe('ageSeconds', () => {
  beforeAll(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-05-17T00:00:00Z'));
  });
  afterAll(() => {
    vi.useRealTimers();
  });

  it('null para entrada vacia', () => {
    expect(ageSeconds(null)).toBeNull();
    expect(ageSeconds(undefined)).toBeNull();
  });

  it('cero o casi cero para ahora', () => {
    const a = ageSeconds(new Date().toISOString());
    expect(a).toBeGreaterThanOrEqual(0);
    expect(a).toBeLessThan(1);
  });

  it('calcula segundos en el pasado', () => {
    const iso = new Date(Date.now() - 12_000).toISOString();
    expect(ageSeconds(iso)).toBeCloseTo(12, 0);
  });

  it('clampea a 0 si la fecha es futura', () => {
    const iso = new Date(Date.now() + 5_000).toISOString();
    expect(ageSeconds(iso)).toBe(0);
  });
});
