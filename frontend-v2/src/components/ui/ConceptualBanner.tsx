import { Info } from 'lucide-react';
import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';

/**
 * Banner suave en ambar para etiquetar paginas con visualizaciones
 * conceptuales (datos sinteticos hasta integracion real).
 * Reutilizable en SDN y Edge.
 */
export function ConceptualBanner({
  title,
  children,
  className,
}: {
  title: string;
  children: ReactNode;
  className?: string;
}): JSX.Element {
  return (
    <aside
      role="note"
      className={cn(
        'flex items-start gap-3 rounded-md border border-warning/40 bg-warning/10 px-4 py-3 text-warning-foreground',
        className,
      )}
    >
      <Info className="mt-0.5 h-5 w-5 shrink-0 text-warning" aria-hidden="true" />
      <div className="text-sm text-ink">
        <p className="font-semibold text-ink">{title}</p>
        <div className="text-ink-muted">{children}</div>
      </div>
    </aside>
  );
}
