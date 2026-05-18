import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Badge } from './Badge';

describe('Badge', () => {
  it('renderiza el contenido', () => {
    render(<Badge>NORMAL</Badge>);
    expect(screen.getByText('NORMAL')).toBeInTheDocument();
  });

  it('variant default = neutral', () => {
    render(<Badge>X</Badge>);
    expect(screen.getByText('X')).toHaveClass('bg-neutral-100');
  });

  it('variant success aplica clases verdes', () => {
    render(<Badge variant="success">ok</Badge>);
    expect(screen.getByText('ok')).toHaveClass('text-success');
  });

  it('variant danger aplica clases rojas', () => {
    render(<Badge variant="danger">bad</Badge>);
    expect(screen.getByText('bad')).toHaveClass('text-danger');
  });
});
