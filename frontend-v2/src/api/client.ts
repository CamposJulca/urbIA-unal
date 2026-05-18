/**
 * Cliente HTTP minimalista para el backend FastAPI de UrbIA.
 *
 * Estrategia de origen:
 *  - En dev y en prod servimos el frontend y el backend bajo el mismo
 *    origen mediante un proxy en `/api/*` (Vite proxy en dev,
 *    nginx en prod). Asi evitamos CORS sin tocar el backend.
 *  - La base se puede sobreescribir con VITE_API_BASE_URL para
 *    despliegues alternativos.
 */
const RAW_BASE = import.meta.env.VITE_API_BASE_URL ?? '/api';
export const API_BASE_URL = RAW_BASE.replace(/\/$/, '');

/** Error de transporte HTTP enriquecido para el manejador de UI. */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly path: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

/**
 * Wrapper tipado sobre fetch. Acepta un AbortSignal externo (el que
 * React Query inyecta a cada query) para cancelar al desmontar o al
 * disparar un nuevo intervalo de polling.
 */
export async function fetchJson<T>(
  path: string,
  options: { signal?: AbortSignal; query?: Record<string, string | number> } = {},
): Promise<T> {
  const url = new URL(`${API_BASE_URL}${path}`, window.location.origin);
  if (options.query) {
    for (const [k, v] of Object.entries(options.query)) {
      url.searchParams.set(k, String(v));
    }
  }

  const res = await fetch(url.toString(), {
    method: 'GET',
    headers: { Accept: 'application/json' },
    signal: options.signal,
  });

  if (!res.ok) {
    throw new ApiError(`HTTP ${res.status} en ${path}`, res.status, path);
  }
  return (await res.json()) as T;
}
