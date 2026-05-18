import { describe, it, expect } from 'vitest';
import { cn } from './utils';

describe('cn (clsx + tailwind-merge)', () => {
  it('concatena clases simples', () => {
    expect(cn('a', 'b')).toBe('a b');
  });

  it('ignora valores falsy', () => {
    expect(cn('a', false, null, undefined, '', 'b')).toBe('a b');
  });

  it('deduplica utilidades Tailwind conflictivas', () => {
    expect(cn('text-red-500', 'text-blue-500')).toBe('text-blue-500');
  });

  it('respeta clases con prefijos responsive', () => {
    const out = cn('p-2', 'md:p-4', 'p-3');
    // tailwind-merge gana la ultima de cada categoria
    expect(out).toContain('md:p-4');
    expect(out).toContain('p-3');
    expect(out).not.toContain('p-2');
  });

  it('acepta array y objeto de clsx', () => {
    expect(cn(['a', 'b'], { c: true, d: false })).toBe('a b c');
  });
});
