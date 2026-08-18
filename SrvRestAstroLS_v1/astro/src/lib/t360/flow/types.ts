// Team360 Flow — Directorio / Vista Ejecutiva
// Contrato tipado que refleja `build_executive_view` del backend Flow
// (modules/flow/executive_query.py). No se inventan campos: solo se tipa y se
// derivan ayudas de presentación.

export type StatusFact = "open" | "closed" | "pending_approval";
export type DataSource = "LIVE" | "AUDIT_SNAPSHOT";
export type ClosureDecision = "PENDING" | "APPROVED" | "REJECTED";

export interface ExecutiveRequest {
  request_id: string;
  conversation_id?: string;
  sector_id?: string | null;
  sector_name?: string | null;
  category?: string | null;
  description?: string | null;
  location?: string | null;
  citizen_address?: string | null;
  origin_channel?: string | null;
  received_at?: string | null;
  confirmed_at?: string | null;
}

export interface RoutingHistoryItem {
  routing_id: string;
  routing_key?: string;
  level: number;
  destination?: string | null;
  assigned_at?: string | null;
  routing_status?: string | null;
  work_status?: string | null;
  first_response_at?: string | null;
  first_responder?: string | null;
}

export interface SlaItem {
  sla_id?: string;
  sla_type?: string;
  routing_id?: string;
  level: number;
  duration_seconds?: number | null;
  started_at?: string | null;
  due_at?: string | null;
  first_response_at?: string | null;
  status: string; // PENDING | MET | BREACHED
  met_at?: string | null;
  breached_at?: string | null;
}

export interface EscalationItem {
  escalation_id?: string;
  from_routing_id?: string | null;
  from_level: number;
  to_routing_id?: string | null;
  to_level: number;
  trigger?: string | null;
  trigger_sla_id?: string | null;
  created_at?: string | null;
  completed_at?: string | null;
  status?: string | null;
}

export interface OperationalEventItem {
  event_id?: string;
  routing_id?: string | null;
  level?: number | null;
  received_at?: string | null;
  interpretation?: string | null;
  sender?: string | null;
}

export interface ResolutionItem {
  resolution_id?: string;
  proposed_by?: string | null;
  proposed_at?: string | null;
  routing_id?: string | null;
  resolution_text?: string | null;
  resolution_status?: string | null;
}

export interface ClosureApprovalItem {
  approval_id?: string;
  approver?: string | null;
  approver_level?: number | null;
  decision?: ClosureDecision | null;
  decision_at?: string | null;
  decision_reason?: string | null;
  source_message_id?: string | null;
}

export interface TimelineEvent {
  timestamp?: string | null;
  event_type: string;
  routing_id?: string | null;
  level?: number | null;
  reference_id?: string | null;
}

export interface ExecutiveMetrics {
  total_elapsed_seconds?: number | null;
  routing_count?: number;
  escalation_count?: number;
  sla_total?: number;
  sla_met_count?: number;
  sla_breached_count?: number;
  levels_reached?: number;
  first_response_elapsed_seconds?: number | null;
  current_age_seconds?: number | null;
}

export interface ExecutiveView {
  request_id: string;
  status: string;
  data_source: DataSource;
  status_fact: StatusFact;
  request: ExecutiveRequest;
  routing_history: RoutingHistoryItem[];
  sla: SlaItem[];
  escalations: EscalationItem[];
  operational_events: OperationalEventItem[];
  resolution: ResolutionItem | null;
  closure_approval: ClosureApprovalItem | null;
  result: { request_status?: string | null; resolved_at?: string | null };
  metrics: ExecutiveMetrics;
  timeline: TimelineEvent[];
  audit?: { audit_record_id?: string; schema_version?: number; snapshot_sha256?: string } | null;
  executive_summary?: string | null;
}

// --- Derivación de presentación (no es fuente de verdad, solo UI) -----------

export function currentLevel(view: ExecutiveView): number {
  const assigned = view.routing_history.filter((r) => r.routing_status === "ASSIGNED");
  if (assigned.length === 0) {
    return view.metrics.levels_reached ?? 0;
  }
  return Math.max(...assigned.map((r) => r.level));
}

export function currentAssignee(view: ExecutiveView): string | null {
  const assigned = view.routing_history
    .filter((r) => r.routing_status === "ASSIGNED")
    .sort((a, b) => b.level - a.level);
  return assigned[0]?.destination ?? null;
}

export function hasBreachedSla(view: ExecutiveView): boolean {
  return view.sla.some((s) => s.status === "BREACHED");
}

export function hasPendingApproval(view: ExecutiveView): boolean {
  return view.status_fact === "pending_approval";
}

export function isResolved(view: ExecutiveView): boolean {
  return view.status_fact === "closed";
}

// Prioridad visual derivada (para orden/agrupación de la lista), no regla de negocio.
export function caseAttention(view: ExecutiveView): "critical" | "warning" | "info" | "resolved" {
  if (isResolved(view)) return "resolved";
  if (hasPendingApproval(view)) return "info";
  if (hasBreachedSla(view)) return "critical";
  const latestSla = [...view.sla].sort((a, b) => (a.level ?? 0) - (b.level ?? 0)).pop();
  if (latestSla && latestSla.status === "PENDING" && latestSla.due_at) {
    const due = new Date(latestSla.due_at).getTime();
    const now = Date.now();
    const remaining = due - now;
    const duration = (latestSla.duration_seconds ?? 30) * 1000;
    if (remaining < duration * 0.25) return "warning";
  }
  return "info";
}
