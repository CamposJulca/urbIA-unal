import type { KnownZone } from '@/api/types';

/**
 * Mapeo de zona AMI a color visual consistente entre MeterCard,
 * Chart y RecentReadingsTable. Si llega una zona desconocida usamos
 * 'neutral'. Mantener en sync con tailwind.config.js si se cambia
 * la paleta.
 */
export const ZONE_COLOR: Record<KnownZone, string> = {
  'MNZ-CENTRO': '#1A3A6E',
  'MNZ-NORTE': '#2E5A9E',
  'MNZ-SUR': '#10B981',
  'MNZ-ESTE': '#F59E0B',
  'MNZ-OESTE': '#A855F7',
};

export const ZONE_FALLBACK = '#64748B';

export function colorForZone(zone: string | null | undefined): string {
  if (!zone) return ZONE_FALLBACK;
  return (ZONE_COLOR as Record<string, string>)[zone] ?? ZONE_FALLBACK;
}

export const ZONE_LABEL: Record<KnownZone, string> = {
  'MNZ-CENTRO': 'Centro',
  'MNZ-NORTE': 'Norte',
  'MNZ-SUR': 'Sur',
  'MNZ-ESTE': 'Este',
  'MNZ-OESTE': 'Oeste',
};

export function labelForZone(zone: string | null | undefined): string {
  if (!zone) return 'Sin zona';
  return (ZONE_LABEL as Record<string, string>)[zone] ?? zone;
}
