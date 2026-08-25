// Cliente read-only de los endpoints ejecutivos reales de Flow.
// GET /api/team360-flow/executive              -> resumen paginado
// GET /api/team360-flow/executive/{request_id} -> detalle completo

import type {
  DataSource,
  ExecutiveCaseListItem,
  ExecutiveCaseListPagination,
  ExecutiveCaseListSector,
  ExecutiveRequest,
  ExecutiveView,
  StatusFact,
} from "../t360/flow/types";

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

export type ExecutiveListFetchError = ExecutiveFetchError | "validation";

export type ApprovalResendError =
  | "unauthorized"
  | "forbidden"
  | "not_found"
  | "conflict"
  | "invalid"
  | "unavailable";

export interface ApprovalResendResult {
  request_id: string;
  approval_id: string;
  status: string;
  approver_level: number;
  approver_destination: string;
  subject: string;
  outbound_external_message_id: string;
  correlation_preserved: boolean;
}

export interface ExecutiveFetchResult {
  data: ExecutiveView | null;
  error: ExecutiveFetchError | null;
}

export interface ExecutiveCaseListResult {
  data: {
    items: ExecutiveCaseListItem[];
    sectors: ExecutiveCaseListSector[];
    pagination: ExecutiveCaseListPagination;
  } | null;
  error: ExecutiveListFetchError | null;
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

export async function fetchExecutiveCaseList(
  options: {
    page?: number;
    pageSize?: number;
    status?: string;
    sectorId?: string;
    search?: string;
    slaStatus?: string;
    escalated?: boolean;
    token?: string;
    timeoutMs?: number;
  } = {},
): Promise<ExecutiveCaseListResult> {
  const params = new URLSearchParams();
  if (options.page !== undefined) params.set("page", String(options.page));
  if (options.pageSize !== undefined) params.set("page_size", String(options.pageSize));
  if (options.status) params.set("status", options.status);
  if (options.sectorId) params.set("sector_id", options.sectorId);
  if (options.search) params.set("search", options.search);
  if (options.slaStatus) params.set("sla_status", options.slaStatus);
  if (options.escalated !== undefined) params.set("escalated", String(options.escalated));

  const url = new URL(`${API_BASE}/executive`, window.location.origin);
  url.search = params.toString();
  const headers: Record<string, string> = {};
  if (options.token) headers.Authorization = `Bearer ${options.token}`;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), options.timeoutMs ?? DEFAULT_TIMEOUT_MS);

  try {
    const res = await fetch(url.toString(), { headers, signal: controller.signal });
    if (res.status === 401) return { data: null, error: "unauthorized" };
    if (res.status === 403) return { data: null, error: "forbidden" };
    if (res.status === 422) return { data: null, error: "validation" };
    if (!res.ok) return { data: null, error: "unavailable" };
    const payload = (await res.json()) as {
      items: Record<string, unknown>[];
      sectors?: ExecutiveCaseListSector[];
      pagination: ExecutiveCaseListPagination;
    };
    return {
      data: {
        items: payload.items.map(mapListItem),
        sectors: payload.sectors ?? [],
        pagination: payload.pagination,
      },
      error: null,
    };
  } catch {
    return { data: null, error: "unavailable" };
  } finally {
    clearTimeout(timer);
  }
}

export async function resendApprovalRequest(
  requestId: string,
  options: { token?: string; timeoutMs?: number } = {},
): Promise<{ data: ApprovalResendResult | null; error: ApprovalResendError | null }> {
  const url = new URL(
    `${API_BASE}/executive/${encodeURIComponent(requestId)}/resend-approval`,
    window.location.origin,
  );
  const headers: Record<string, string> = {};
  if (options.token) headers.Authorization = `Bearer ${options.token}`;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), options.timeoutMs ?? DEFAULT_TIMEOUT_MS);

  try {
    const res = await fetch(url.toString(), { method: "POST", headers, signal: controller.signal });
    if (res.status === 401) return { data: null, error: "unauthorized" };
    if (res.status === 403) return { data: null, error: "forbidden" };
    if (res.status === 404) return { data: null, error: "not_found" };
    if (res.status === 409) return { data: null, error: "conflict" };
    if (res.status === 422) return { data: null, error: "invalid" };
    if (!res.ok) return { data: null, error: "unavailable" };
    return { data: (await res.json()) as ApprovalResendResult, error: null };
  } catch {
    return { data: null, error: "unavailable" };
  } finally {
    clearTimeout(timer);
  }
}

function mapListItem(item: Record<string, unknown>): ExecutiveCaseListItem {
  const request: ExecutiveRequest = {
    request_id: String(item.request_id ?? ""),
    conversation_id: asString(item.conversation_id) ?? undefined,
    sector_id: asString(item.sector_id),
    sector_name: asString(item.sector_name),
    category: asString(item.category),
    description: asString(item.description),
    location: asString(item.location),
    received_at: asString(item.received_at),
    confirmed_at: asString(item.confirmed_at),
  };
  return {
    request_id: request.request_id,
    conversation_id: request.conversation_id,
    status: String(item.status ?? ""),
    data_source: String(item.data_source ?? "LIVE") as DataSource,
    status_fact: String(item.status_fact ?? "open") as StatusFact,
    request,
    current_routing_id: asString(item.current_routing_id),
    current_level: asNumber(item.current_level),
    current_destination: asString(item.current_destination),
    current_routing_status: asString(item.current_routing_status),
    current_work_status: asString(item.current_work_status),
    sla_status: asString(item.sla_status),
    sla_due_at: asString(item.sla_due_at),
    has_breached_sla: Boolean(item.has_breached_sla),
    first_response_at: asString(item.first_response_at),
    resolved_at: asString(item.resolved_at),
    escalation_count: Number(item.escalation_count ?? 0),
    updated_at: asString(item.updated_at),
  };
}

function asString(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

function asNumber(value: unknown): number | null {
  return typeof value === "number" ? value : null;
}
