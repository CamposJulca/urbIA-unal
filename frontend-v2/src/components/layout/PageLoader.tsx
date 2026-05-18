import urbiaLogo from '@/assets/logos/urbia-logo.svg';

/**
 * Fallback de carga para chunks lazy: logo UrbIA pequeno + barra
 * de progreso indeterminada con el azul institucional.
 */
export function PageLoader(): JSX.Element {
  return (
    <div
      className="flex h-[60vh] items-center justify-center"
      role="status"
      aria-live="polite"
    >
      <div className="flex w-64 flex-col items-center gap-4">
        <img src={urbiaLogo} alt="" aria-hidden="true" className="h-10 w-auto opacity-90" />
        <div className="h-1.5 w-full overflow-hidden rounded-full bg-neutral-200">
          <div className="h-full w-1/3 animate-loader rounded-full bg-primary" />
        </div>
        <p className="text-sm text-ink-muted">Cargando modulo...</p>
      </div>
    </div>
  );
}
