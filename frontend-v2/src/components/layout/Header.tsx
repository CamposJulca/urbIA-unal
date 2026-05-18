import { NavLink } from 'react-router-dom';
import { CircleDot } from 'lucide-react';
import { Badge } from '@/components/ui/Badge';
import { cn } from '@/lib/utils';
import urbiaLogo from '@/assets/logos/urbia-logo.svg';
import { useSystemHealth } from '@/api/hooks';
import { formatRelative } from '@/lib/format';

/**
 * Header institucional UrbIA: logo + navegacion + badge de salud del
 * backend (conectado/desconectado/degradado) con tooltip de timestamp
 * de la ultima verificacion.
 */

type NavItem = { to: string; label: string; end?: boolean };
const NAV_ITEMS: readonly NavItem[] = [
  { to: '/', label: 'Inicio', end: true },
  { to: '/telemetria', label: 'Telemetria' },
  { to: '/sdn', label: 'SDN' },
  { to: '/edge', label: 'Edge' },
  { to: '/acerca', label: 'Acerca' },
];

export function Header(): JSX.Element {
  const health = useSystemHealth();

  const badge =
    health.state === 'ok'
      ? { variant: 'success' as const, label: 'Sistema operativo' }
      : health.state === 'degraded'
        ? { variant: 'warning' as const, label: 'Backend degradado' }
        : health.state === 'down'
          ? { variant: 'danger' as const, label: 'Sistema desconectado' }
          : { variant: 'neutral' as const, label: 'Verificando...' };

  const tooltip = health.dataUpdatedAt
    ? `Verificado ${formatRelative(new Date(health.dataUpdatedAt).toISOString())}`
    : 'Sin verificacion aun';

  return (
    <header
      className={cn(
        'sticky top-0 z-40 h-16 w-full border-b border-border/80',
        'bg-surface/85 backdrop-blur-md supports-[backdrop-filter]:bg-surface/70',
      )}
    >
      <div className="mx-auto flex h-full max-w-7xl items-center justify-between px-6">
        <NavLink to="/" className="flex items-center gap-2" aria-label="UrbIA — inicio">
          <img src={urbiaLogo} alt="UrbIA" className="h-9 w-auto" />
        </NavLink>

        <nav className="hidden items-center gap-1 md:flex" aria-label="Navegacion principal">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                cn(
                  'rounded-md px-3 py-2 text-sm font-medium transition-colors',
                  isActive
                    ? 'bg-primary/10 text-primary'
                    : 'text-ink-muted hover:bg-neutral-100 hover:text-ink',
                )
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="flex items-center gap-3">
          <Badge
            variant={badge.variant}
            className="hidden sm:inline-flex"
            title={tooltip}
          >
            <CircleDot
              className={cn(
                'h-3 w-3',
                health.state === 'ok' ? 'animate-pulse-soft' : '',
              )}
              aria-hidden="true"
            />
            {badge.label}
          </Badge>
        </div>
      </div>
    </header>
  );
}
