import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ConceptualBanner } from './ConceptualBanner';

describe('ConceptualBanner', () => {
  it('renderiza titulo y cuerpo con rol note', () => {
    render(
      <ConceptualBanner title="Visualizacion conceptual">
        Texto descriptivo de prueba.
      </ConceptualBanner>,
    );
    expect(screen.getByRole('note')).toBeInTheDocument();
    expect(screen.getByText('Visualizacion conceptual')).toBeInTheDocument();
    expect(screen.getByText('Texto descriptivo de prueba.')).toBeInTheDocument();
  });
});
