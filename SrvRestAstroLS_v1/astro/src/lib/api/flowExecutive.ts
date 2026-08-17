// Cliente read-only del endpoint ejecutivo real de Flow.
// GET /api/team360-flow/executive/{request_id}
// Consume el contrato real (build_executive_view). En modo mock sin token la
// llamada falla de forma controlada y la UI cae a datos de demostración.

import { API_BASE_URL } from "../../components/global.js";
import type { ExecutiveView } from "../t360/flow/types";

const API_BASE = `${API_BASE_URL}/team360-flow`;

export type ExecutiveFetchError = "unauthorized" | "forbidden" | "not_found" | "unavailable";

export interface ExecutiveFetchResult {
  data: ExecutiveView | null;
  error: ExecutiveFetchError | null;
}

export async function fetchExecutiveCase(
  requestId: string,
  options: { token?: string; question?: string } = {},
): Promise<ExecutiveFetchResult> {
  const url = new URL(`${API_BASE}/executive/${encodeURIComponent(requestId)}`);
  if (options.question) {
    url.searchParams.set("question", options.question);
  }

  const headers: Record<string, string> = {};
  if (options.token) {
    headers.Authorization = `Bearer ${options.token}`;
  }

  try {
    const res = await fetch(url.toString(), { headers });
    if (res.status === 401) return { data: null, error: "unauthorized" };
    if (res.status === 403) return { data: null, error: "forbidden" };
    if (res.status === 404) return { data: null, error: "not_found" };
    if (!res.ok) return { data: null, error: "unavailable" };
    const data = (await res.json()) as ExecutiveView;
    return { data, error: null };
  } catch {
    return { data: null, error: "unavailable" };
  }
}
