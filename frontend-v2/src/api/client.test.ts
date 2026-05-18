import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { fetchJson, ApiError, API_BASE_URL } from './client';

/**
 * Tests del cliente HTTP. Mockeamos `fetch` global con vi.spyOn.
 * jsdom expone `window` y `fetch` lo trae el entorno; lo
 * reemplazamos por test.
 */

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    status: init.status ?? 200,
    headers: { 'content-type': 'application/json' },
  });
}

describe('API_BASE_URL', () => {
  it('por defecto es "/api"', () => {
    expect(API_BASE_URL).toBe('/api');
  });
});

describe('fetchJson', () => {
  beforeEach(() => {
    vi.spyOn(globalThis, 'fetch');
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('devuelve el JSON parseado en 200', async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValue(
      jsonResponse({ status: 'ok' }),
    );
    const out = await fetchJson<{ status: string }>('/health');
    expect(out).toEqual({ status: 'ok' });
  });

  it('lanza ApiError con .status para 404', async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValue(
      new Response('not found', { status: 404 }),
    );
    await expect(fetchJson('/nope')).rejects.toMatchObject({
      name: 'ApiError',
      status: 404,
      path: '/nope',
    });
  });

  it('lanza ApiError para 500', async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValue(
      new Response('boom', { status: 500 }),
    );
    await expect(fetchJson('/x')).rejects.toBeInstanceOf(ApiError);
  });

  it('serializa query params', async () => {
    const spy = (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValue(
      jsonResponse([]),
    );
    await fetchJson('/telemetry/recent', { query: { limit: 600 } });
    const url = spy.mock.calls[0]![0] as string;
    expect(url).toContain('/api/telemetry/recent');
    expect(url).toContain('limit=600');
  });

  it('propaga AbortSignal a fetch', async () => {
    const spy = (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValue(
      jsonResponse({}),
    );
    const ctrl = new AbortController();
    await fetchJson('/health', { signal: ctrl.signal });
    const opts = spy.mock.calls[0]![1] as RequestInit;
    expect(opts.signal).toBe(ctrl.signal);
  });

  it('envia Accept: application/json', async () => {
    const spy = (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValue(
      jsonResponse({}),
    );
    await fetchJson('/health');
    const opts = spy.mock.calls[0]![1] as RequestInit;
    expect((opts.headers as Record<string, string>).Accept).toBe('application/json');
  });
});
