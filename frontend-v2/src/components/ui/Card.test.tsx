import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from './Card';

describe('Card', () => {
  it('compone Header + Title + Description + Content', () => {
    render(
      <Card>
        <CardHeader>
          <CardTitle>Titulo</CardTitle>
          <CardDescription>Subtitulo</CardDescription>
        </CardHeader>
        <CardContent>cuerpo</CardContent>
      </Card>,
    );
    const title = screen.getByText('Titulo');
    expect(title.tagName).toBe('H3');
    expect(screen.getByText('Subtitulo')).toBeInTheDocument();
    expect(screen.getByText('cuerpo')).toBeInTheDocument();
  });

  it('respeta className adicional en Card', () => {
    const { container } = render(<Card className="extra-x">x</Card>);
    expect(container.firstChild).toHaveClass('extra-x');
  });
});
