import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Button } from './Button';

describe('Button', () => {
  it('renderiza un <button> por defecto con el texto recibido', () => {
    render(<Button>Click</Button>);
    const btn = screen.getByRole('button', { name: 'Click' });
    expect(btn.tagName).toBe('BUTTON');
  });

  it('aplica clases de la variant accent', () => {
    render(<Button variant="accent">A</Button>);
    expect(screen.getByRole('button')).toHaveClass('bg-accent');
  });

  it('aplica clases de la variant outline-white', () => {
    render(<Button variant="outline-white">B</Button>);
    expect(screen.getByRole('button')).toHaveClass('border-white/70');
  });

  it('respeta la prop disabled', () => {
    render(<Button disabled>X</Button>);
    expect(screen.getByRole('button')).toBeDisabled();
  });

  it('asChild delega en el hijo y no renderiza un <button>', () => {
    render(
      <Button asChild>
        <a href="/foo">Link</a>
      </Button>,
    );
    const link = screen.getByRole('link', { name: 'Link' });
    expect(link.tagName).toBe('A');
    expect(link).toHaveAttribute('href', '/foo');
  });
});
