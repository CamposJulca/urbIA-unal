import { useQuery, type UseQueryResult } from '@tanstack/react-query';
import { fetchJson } from './client';
import type {
  HealthResponse,
  MeterInfo,
  SystemHealthState,
  TelemetryRecord,
} from './types';

const HEALTH_INTERVAL_MS = 5_000;
const METERS_INTERVAL_MS = 10_000;
const TELEMETRY_INTERVAL_MS = 2_000;

/**
 * Salud del backend (db + mqtt). Polling cada 5 s.
 */
export function useSystemHealth(): UseQueryResult<HealthResponse> & {
  state: SystemHealthState;
} {
  const result = useQuery({
    queryKey: ['health'],
    queryFn: ({ signal }) => fetchJson<HealthResponse>('/health', { signal }),
    refetchInterval: HEALTH_INTERVAL_MS,
    staleTime: HEALTH_INTERVAL_MS / 2,
  });

  let state: SystemHealthState = 'unknown';
  if (result.isError) state = 'down';
  else if (result.data) {
    state =
      result.data.status === 'ok' && result.data.db && result.data.mqtt
        ? 'ok'
        : 'degraded';
  }
  return Object.assign(result, { state });
}

/**
 * Lista de medidores activos. Polling cada 10 s (cambia muy poco).
 */
export function useMeters(): UseQueryResult<MeterInfo[]> {
  return useQuery({
    queryKey: ['meters'],
    queryFn: ({ signal }) => fetchJson<MeterInfo[]>('/meters', { signal }),
    refetchInterval: METERS_INTERVAL_MS,
    staleTime: METERS_INTERVAL_MS / 2,
  });
}

/**
 * Telemetria global reciente — unica fuente de verdad para cards,
 * grafico y tabla. limit=600 cubre ~60 s a 10 msg/s.
 * Polling cada 2 s con cancelacion via AbortSignal.
 */
export function useRecentTelemetry(limit = 600): UseQueryResult<TelemetryRecord[]> {
  return useQuery({
    queryKey: ['telemetry-recent', limit],
    queryFn: ({ signal }) =>
      fetchJson<TelemetryRecord[]>('/telemetry/recent', {
        signal,
        query: { limit },
      }),
    refetchInterval: TELEMETRY_INTERVAL_MS,
    staleTime: TELEMETRY_INTERVAL_MS / 2,
  });
}
