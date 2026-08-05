import type { KnownZone } from '@/api/types';

/**
 * Mapeo de zona AMI a color visual consistente entre MeterCard,
 * Chart y RecentReadingsTable. Si llega una zona desconocida usamos
 * 'neutral'. Mantener en sync con tailwind.config.js si se cambia
 * la paleta.
 */
export const ZONE_COLOR: Record<KnownZone, string> = {
  centro: '#1A3A6E',
  chipre: '#2E5A9E',
  la_enea: '#10B981',
  palermo: '#F59E0B',
  palogrande: '#A855F7',
  universitario: '#0EA5E9',
};

export const ZONE_FALLBACK = '#64748B';

export function colorForZone(zone: string | null | undefined): string {
  if (!zone) return ZONE_FALLBACK;
  return (ZONE_COLOR as Record<string, string>)[zone] ?? ZONE_FALLBACK;
}

export const ZONE_LABEL: Record<KnownZone, string> = {
  centro: 'Centro',
  chipre: 'Chipre',
  la_enea: 'La Enea',
  palermo: 'Palermo',
  palogrande: 'Palogrande',
  universitario: 'Universitario',
};

export function labelForZone(zone: string | null | undefined): string {
  if (!zone) return 'Sin zona';
  return (ZONE_LABEL as Record<string, string>)[zone] ?? zone;
}
