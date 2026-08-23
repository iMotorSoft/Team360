// Cliente read/write de la configuración real de Flow.
// GET  /api/team360-flow/configuration
// GET  /api/team360-flow/configuration/{sector_id}
// PATCH /api/team360-flow/configuration/{sector_id}
// Consume el contrato real (flow_sectors / flow_sector_levels). En modo diseño
// sin token la llamada falla de forma controlada y la UI queda en modo demo.

import type { FlowSectorConfiguration } from "../t360/flow/configuration";

// Mismo-origen: en producción /api es same-origin y en desarrollo el server de
// Astro proxya /api -> 127.0.0.1:7050 (igual que el fallback estático). Un
// fetch absoluto a URL_REST quedaría bloqueado por CORS en el puerto de la
// consola.
const API_BASE = "/api/team360-flow/configuration";

export type FlowConfigurationError = "unauthorized" | "forbidden" | "not_found" | "validation" | "unavailable";

export interface FlowApiLevel {
  level: number;
  channel: string;
  destination: string;
  active: boolean;
  first_response_sla_seconds: number | null;
}

export interface FlowApiSector {
  sector_id: string;
  display_name: string;
  active: boolean;
  closure_approval_level: number | null;
  levels: FlowApiLevel[];
}

export interface FlowApiConfiguration {
  sectors: FlowApiSector[];
}

export interface FlowApiUpdatePayload {
  levels: { level: number; destination: string; first_response_sla_seconds?: number | null }[];
  closure_approval_level: number | null;
}

export interface FlowApiResult<T> {
  data: T | null;
  error: FlowConfigurationError | null;
}

function mapApiSector(sector: FlowApiSector): FlowSectorConfiguration {
  const closureLevel = sector.closure_approval_level;
  const closureLevelRow = sector.levels.find((level) => level.level === closureLevel);
  return {
    sectorId: sector.sector_id,
    displayName: sector.display_name,
    active: sector.active,
    closureApprovalLevel: sector.closure_approval_level,
    closureSupervisorDestination: closureLevelRow?.destination ?? "",
    levels: sector.levels.map((level) => ({
      id: `${sector.sector_id}-level-${level.level}`,
      level: level.level,
      label: `Nivel ${level.level}`,
      channel: level.channel,
      destination: level.destination,
      active: level.active,
      role: level.level === 1 ? "Primera respuesta" : level.level === 2 ? "Escalamiento" : "Escalamiento avanzado",
      firstResponseSlaSeconds: level.first_response_sla_seconds ?? null,
    })),
  };
}

export function mapFlowSectors(api: FlowApiConfiguration): FlowSectorConfiguration[] {
  return api.sectors.map(mapApiSector);
}

async function handleResponse<T>(res: Response): Promise<FlowApiResult<T>> {
  if (res.status === 401) return { data: null, error: "unauthorized" };
  if (res.status === 403) return { data: null, error: "forbidden" };
  if (res.status === 404) return { data: null, error: "not_found" };
  if (res.status === 422) return { data: null, error: "validation" };
  if (!res.ok) return { data: null, error: "unavailable" };
  const data = (await res.json()) as T;
  return { data, error: null };
}

function headers(token?: string): Record<string, string> {
  const result: Record<string, string> = { "Content-Type": "application/json" };
  if (token) result.Authorization = `Bearer ${token}`;
  return result;
}

export async function fetchFlowConfigurations(
  token?: string,
): Promise<FlowApiResult<FlowApiConfiguration>> {
  try {
    const res = await fetch(API_BASE, { headers: headers(token) });
    return handleResponse<FlowApiConfiguration>(res);
  } catch {
    return { data: null, error: "unavailable" };
  }
}

export async function fetchFlowConfiguration(
  sectorId: string,
  token?: string,
): Promise<FlowApiResult<FlowApiSector>> {
  try {
    const res = await fetch(`${API_BASE}/${encodeURIComponent(sectorId)}`, {
      headers: headers(token),
    });
    return handleResponse<FlowApiSector>(res);
  } catch {
    return { data: null, error: "unavailable" };
  }
}

export async function updateFlowConfiguration(
  sectorId: string,
  payload: FlowApiUpdatePayload,
  token?: string,
): Promise<FlowApiResult<FlowApiSector>> {
  try {
    const res = await fetch(`${API_BASE}/${encodeURIComponent(sectorId)}`, {
      method: "PATCH",
      headers: headers(token),
      body: JSON.stringify(payload),
    });
    return handleResponse<FlowApiSector>(res);
  } catch {
    return { data: null, error: "unavailable" };
  }
}

// --- Operational Settings API ---

const OPS_API_BASE = "/api/team360-flow/operational-settings";
const SCHEDULER_API_BASE = "/api/team360-flow/scheduler/status";

export interface FlowOperationalSettings {
  automation_enabled: boolean;
  scheduler_interval_seconds: number;
  mail_intake_enabled: boolean;
  mail_batch_limit: number;
  mail_after_cutoff: boolean;
  mail_cutoff_epoch: number;
}

export interface FlowSchedulerState {
  last_started_at_utc: string | null;
  last_finished_at_utc: string | null;
  last_result: string | null;
  last_error_class: string | null;
  processed_count: number;
  cycle_count: number;
}

export async function fetchOperationalSettings(
  token?: string,
): Promise<FlowApiResult<FlowOperationalSettings>> {
  try {
    const res = await fetch(OPS_API_BASE, { headers: headers(token) });
    return handleResponse<FlowOperationalSettings>(res);
  } catch {
    return { data: null, error: "unavailable" };
  }
}

export async function updateOperationalSettings(
  payload: Partial<FlowOperationalSettings>,
  token?: string,
): Promise<FlowApiResult<FlowOperationalSettings>> {
  try {
    const res = await fetch(OPS_API_BASE, {
      method: "PATCH",
      headers: headers(token),
      body: JSON.stringify(payload),
    });
    return handleResponse<FlowOperationalSettings>(res);
  } catch {
    return { data: null, error: "unavailable" };
  }
}

export async function fetchSchedulerStatus(
  token?: string,
): Promise<FlowApiResult<FlowSchedulerState>> {
  try {
    const res = await fetch(SCHEDULER_API_BASE, { headers: headers(token) });
    return handleResponse<FlowSchedulerState>(res);
  } catch {
    return { data: null, error: "unavailable" };
  }
}
