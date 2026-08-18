// Cliente read-only del endpoint ejecutivo real de Flow.
// GET /api/team360-flow/executive/{request_id}
// Consume el contrato real (build_executive_view). En modo mock sin token la
// llamada falla de forma controlada y la UI cae a datos de demostración.

import type { ExecutiveView } from "../t360/flow/types";

// El Directorio consulta el backend por el MISMO origen: en producción
// (URL_REST_PRO="") /api es same-origin, y en desarrollo el server de Astro
// proxya /api -> 127.0.0.1:7050 (astro.config.mjs) igual que el fallback
// estático (scripts/serve-dist.mjs). Un fetch absoluto a URL_REST desde el
// puerto de la consola (4321) quedaría bloqueado por CORS.
const API_BASE = "/api/team360-flow";

export type ExecutiveFetchError =
  | "unauthorized"
  | "forbidden"
  | "not_found"
  | "unavailable";

export interface ExecutiveFetchResult {
  data: ExecutiveView | null;
  error: ExecutiveFetchError | null;
}

export interface ExecutiveBatchResult {
  cases: ExecutiveView[];
  failed: { requestId: string; error: ExecutiveFetchError }[];
}

const DEFAULT_TIMEOUT_MS = 8000;

async function fetchOne(
  requestId: string,
  options: { token?: string; question?: string; timeoutMs?: number },
): Promise<ExecutiveFetchResult> {
  const url = new URL(`${API_BASE}/executive/${encodeURIComponent(requestId)}`, window.location.origin);
  if (options.question) {
    url.searchParams.set("question", options.question);
  }

  const headers: Record<string, string> = {};
  if (options.token) {
    headers.Authorization = `Bearer ${options.token}`;
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), options.timeoutMs ?? DEFAULT_TIMEOUT_MS);

  try {
    const res = await fetch(url.toString(), { headers, signal: controller.signal });
    if (res.status === 401) return { data: null, error: "unauthorized" };
    if (res.status === 403) return { data: null, error: "forbidden" };
    if (res.status === 404) return { data: null, error: "not_found" };
    if (!res.ok) return { data: null, error: "unavailable" };
    const data = (await res.json()) as ExecutiveView;
    return { data, error: null };
  } catch {
    return { data: null, error: "unavailable" };
  } finally {
    clearTimeout(timer);
  }
}

export async function fetchExecutiveCase(
  requestId: string,
  options: { token?: string; question?: string; timeoutMs?: number } = {},
): Promise<ExecutiveFetchResult> {
  return fetchOne(requestId, options);
}

// Carga en paralelo con concurrencia limitada. Útil porque el backend expone
// la vista ejecutiva por caso y aún no ofrece listado (gap documentado en
// lib/t360/flow/caseRegistry.ts). Nunca duplica requests para un mismo id.
export async function fetchExecutiveCases(
  requestIds: readonly string[],
  options: { token?: string; concurrency?: number; timeoutMs?: number } = {},
): Promise<ExecutiveBatchResult> {
  const uniqueIds = [...new Set(requestIds)];
  const concurrency = Math.min(Math.max(options.concurrency ?? 6, 1), 12);
  const results: ExecutiveView[] = [];
  const failed: { requestId: string; error: ExecutiveFetchError }[] = [];

  let cursor = 0;
  async function worker() {
    while (cursor < uniqueIds.length) {
      const requestId = uniqueIds[cursor++];
      const { data, error } = await fetchOne(requestId, {
        token: options.token,
        timeoutMs: options.timeoutMs,
      });
      if (data) {
        results.push(data);
      } else if (error) {
        failed.push({ requestId, error });
      }
    }
  }

  await Promise.all(
    Array.from({ length: Math.min(concurrency, uniqueIds.length || 1) }, () => worker()),
  );
  return { cases: results, failed };
}
