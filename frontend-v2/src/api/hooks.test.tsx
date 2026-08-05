import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { useSystemHealth, useMeters, useRecentTelemetry } from './hooks';

/**
 * Tests de los hooks de React Query. Reemplazamos `globalThis.fetch`
 * por una funcion vi.fn() en cada test (vi.stubGlobal asegura limpieza
 * automatica entre tests).
 */

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, refetchInterval: false, gcTime: 0 } },
  });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

function jsonRes(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

function stubFetch(impl: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>): ReturnType<typeof vi.fn> {
  const fn = vi.fn(impl);
  vi.stubGlobal('fetch', fn);
  return fn;
}

describe('useSystemHealth', () => {
  beforeEach(() => vi.unstubAllGlobals());
  afterEach(() => vi.unstubAllGlobals());

  it("estado 'ok' cuando backend responde status ok + db + mqtt", async () => {
    stubFetch(async () => jsonRes({ status: 'ok', db: true, mqtt: true }));
    const { result } = renderHook(() => useSystemHealth(), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(result.current.state).toBe('ok');
  });

  it("estado 'degraded' cuando db === false", async () => {
    stubFetch(async () => jsonRes({ status: 'ok', db: false, mqtt: true }));
    const { result } = renderHook(() => useSystemHealth(), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(result.current.state).toBe('degraded');
  });

  it("estado 'down' cuando fetch falla", async () => {
    stubFetch(async () => { throw new Error('boom'); });
    const { result } = renderHook(() => useSystemHealth(), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.state).toBe('down');
  });
});

describe('useMeters', () => {
  beforeEach(() => vi.unstubAllGlobals());
  afterEach(() => vi.unstubAllGlobals());

  it('devuelve la lista del backend', async () => {
    stubFetch(async () =>
      jsonRes([
        {
          meter_id: 'urbia-cen-mon-0001',
          device_type: 'mon',
          zone: 'centro',
          lat: 5.0689,
          lon: -75.5174,
          nodo_origen: '192.168.0.103',
          installed_at: null,
          last_seen: null,
          is_active: true,
        },
      ]),
    );
    const { result } = renderHook(() => useMeters(), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.data).toHaveLength(1));
    expect(result.current.data![0]!.meter_id).toBe('urbia-cen-mon-0001');
    expect(result.current.data![0]!.zone).toBe('centro');
  });
});

describe('useRecentTelemetry', () => {
  beforeEach(() => vi.unstubAllGlobals());
  afterEach(() => vi.unstubAllGlobals());

  it('envia el parametro limit al backend', async () => {
    const spy = stubFetch(async () => jsonRes([]));
    const { result } = renderHook(() => useRecentTelemetry(123), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.data).toBeDefined());
    const firstCall = spy.mock.calls[0]!;
    const url = String(firstCall[0]);
    expect(url).toContain('limit=123');
  });
});
