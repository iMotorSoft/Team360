// Team360 Flow — datos de demostración para Directorio.
// IMPORTANTE: el backend solo expone el detalle por request_id; la LISTA y los
// KPIs aún no tienen endpoint. Estos datos son de demostración (marcados como
// demo) y respetan el contrato real `ExecutiveView` para que el cambio a una
// API de listado sea directo. No son la fuente de verdad.

import type { ExecutiveCaseListItem, ExecutiveView } from "../t360/flow/types";

function iso(minutesAgo: number): string {
  return new Date(Date.now() - minutesAgo * 60_000).toISOString();
}

export const FLOW_DEMO_CASES: ExecutiveView[] = [
  {
    request_id: "333a15d0-b3cd-4ec1-ba01-b0a9593f087f",
    status: "ACTIVE",
    data_source: "LIVE",
    status_fact: "open",
    request: {
      request_id: "333a15d0-b3cd-4ec1-ba01-b0a9593f087f",
      sector_id: "alumbrado",
      sector_name: "Alumbrado Público",
      category: "alumbrado",
      description: "Luminaria apagada en la calle Olleros al 2200",
      location: "Olleros al 2200",
      origin_channel: "email",
      received_at: iso(40),
      confirmed_at: iso(39),
    },
    routing_history: [
      {
        routing_id: "c88ca6d9-d84f-4036-bc24-3c30bbb65fa6",
        routing_key: "initial_n1",
        level: 1,
        destination: "alumbrado.n1@alquimiablue.com",
        assigned_at: iso(36),
        routing_status: "ASSIGNED",
        work_status: "IN_PROGRESS",
        first_response_at: iso(33),
        first_responder: "mario.rojas@alquimiablue.com",
      },
      {
        routing_id: "cbf3b18d-5d5b-4b74-8581-67fe91ebac6e",
        routing_key: "alumbrado_level_2",
        level: 2,
        destination: "alumbrado.n2@alquimiablue.com",
        assigned_at: iso(24),
        routing_status: "ASSIGNED",
        work_status: "ASSIGNED",
        first_response_at: null,
        first_responder: null,
      },
    ],
    sla: [
      { level: 1, status: "BREACHED", started_at: iso(36), due_at: iso(35), first_response_at: iso(33), breached_at: iso(26) },
      { level: 2, status: "PENDING", started_at: iso(24), due_at: iso(23), first_response_at: null, breached_at: null },
    ],
    escalations: [
      {
        escalation_id: "d1b9960c-a0b1-4c29-9229-28a6ea5f53d2",
        from_level: 1,
        to_level: 2,
        trigger: "FIRST_RESPONSE_SLA_BREACHED",
        created_at: iso(24),
        completed_at: iso(24),
        status: "COMPLETED",
      },
    ],
    operational_events: [
      { event_id: "280aa568-662c-4226-b64f-b9370cdd9485", level: 1, interpretation: "ACK_OR_PROGRESS", received_at: iso(33), sender: "mario.rojas@alquimiablue.com" },
    ],
    resolution: null,
    closure_approval: null,
    result: { request_status: "ACTIVE", resolved_at: null },
    metrics: {
      routing_count: 2,
      escalation_count: 1,
      sla_total: 2,
      sla_met_count: 0,
      sla_breached_count: 1,
      levels_reached: 2,
      current_age_seconds: 40 * 60,
    },
    timeline: [
      { timestamp: iso(39), event_type: "REQUEST_CONFIRMED" },
      { timestamp: iso(36), event_type: "ROUTING_ASSIGNED", level: 1 },
      { timestamp: iso(36), event_type: "SLA_STARTED", level: 1 },
      { timestamp: iso(33), event_type: "REQUEST_RECEIVED" },
      { timestamp: iso(26), event_type: "SLA_BREACHED", level: 1 },
      { timestamp: iso(24), event_type: "ROUTING_ASSIGNED", level: 2 },
      { timestamp: iso(24), event_type: "ESCALATED" },
    ],
    executive_summary: "La solicitud de alumbrado en Olleros al 2200 superó el SLA de primera respuesta de Nivel 1 y fue escalada a Nivel 2. Queda pendiente la primera respuesta de Nivel 2.",
  },
  {
    request_id: "814f38ce-9509-4cd6-a355-fa176e63edb2",
    status: "RESOLVED",
    data_source: "AUDIT_SNAPSHOT",
    status_fact: "closed",
    request: {
      request_id: "814f38ce-9509-4cd6-a355-fa176e63edb2",
      sector_id: "alumbrado",
      sector_name: "Alumbrado Público",
      category: "alumbrado",
      description: "Luminaria apagada en la calle Lavalle",
      location: "Lavalle 1200",
      origin_channel: "email",
      received_at: iso(2880),
      confirmed_at: iso(2879),
    },
    routing_history: [
      { routing_id: "r-n1-814f", routing_key: "initial_n1", level: 1, destination: "alumbrado.n1@alquimiablue.com", assigned_at: iso(2870), routing_status: "ASSIGNED", work_status: "IN_PROGRESS", first_response_at: iso(2865), first_responder: "mario.rojas@alquimiablue.com" },
      { routing_id: "r-n2-814f", routing_key: "alumbrado_level_2", level: 2, destination: "alumbrado.n2@alquimiablue.com", assigned_at: iso(2840), routing_status: "ASSIGNED", work_status: "IN_PROGRESS", first_response_at: iso(2835), first_responder: "mario.rojas@alquimiablue.com" },
    ],
    sla: [
      { level: 1, status: "MET", started_at: iso(2870), due_at: iso(2869), first_response_at: iso(2865), met_at: iso(2865), breached_at: null },
      { level: 2, status: "MET", started_at: iso(2840), due_at: iso(2839), first_response_at: iso(2835), met_at: iso(2835), breached_at: null },
    ],
    escalations: [
      { escalation_id: "esc-814f", from_level: 1, to_level: 2, trigger: "FIRST_RESPONSE_SLA_BREACHED", created_at: iso(2840), completed_at: iso(2840), status: "COMPLETED" },
    ],
    operational_events: [
      { event_id: "ev-814f-1", level: 2, interpretation: "RESOLUTION_PROPOSED", received_at: iso(2830), sender: "mario.rojas@alquimiablue.com" },
    ],
    resolution: { resolution_id: "res-814f", proposed_by: "mario.rojas@alquimiablue.com", proposed_at: iso(2830), routing_id: "r-n2-814f", resolution_text: "La luminaria quedó reparada y verificada en cuadrilla.", resolution_status: "APPROVED" },
    closure_approval: { approval_id: "apr-814f", approver: "alumbrado.n2@alquimiablue.com", approver_level: 2, decision: "APPROVED", decision_at: iso(2820), decision_reason: "Verificado por supervisor.", source_message_id: "gmail-approval-814f" },
    result: { request_status: "RESOLVED", resolved_at: iso(2820) },
    metrics: {
      routing_count: 2,
      escalation_count: 1,
      sla_total: 2,
      sla_met_count: 2,
      sla_breached_count: 0,
      levels_reached: 2,
      total_elapsed_seconds: 60 * 60,
    },
    timeline: [
      { timestamp: iso(2880), event_type: "REQUEST_RECEIVED" },
      { timestamp: iso(2879), event_type: "REQUEST_CONFIRMED" },
      { timestamp: iso(2870), event_type: "ROUTING_ASSIGNED", level: 1 },
      { timestamp: iso(2865), event_type: "SLA_MET", level: 1 },
      { timestamp: iso(2840), event_type: "ESCALATED" },
      { timestamp: iso(2840), event_type: "ROUTING_ASSIGNED", level: 2 },
      { timestamp: iso(2830), event_type: "RESOLUTION_PROPOSED" },
      { timestamp: iso(2820), event_type: "CLOSURE_APPROVED" },
      { timestamp: iso(2820), event_type: "REQUEST_RESOLVED" },
    ],
    audit: { audit_record_id: "a23aa1ec", schema_version: 1, snapshot_sha256: "2f1e…9c" },
    executive_summary: "Caso resuelto: la luminaria fue reparada y el cierre fue autorizado por el supervisor. Registro de auditoría inmutable verificado.",
  },
  {
    request_id: "d16a0a08-315b-47a8-9790-aaece91bde5f",
    status: "RESOLUTION_PENDING_APPROVAL",
    data_source: "LIVE",
    status_fact: "pending_approval",
    request: {
      request_id: "d16a0a08-315b-47a8-9790-aaece91bde5f",
      sector_id: "alumbrado",
      sector_name: "Alumbrado Público",
      category: "alumbrado",
      description: "Poste de luz dañado por temporal",
      location: "Av. Maipú 850",
      origin_channel: "email",
      received_at: iso(90),
      confirmed_at: iso(89),
    },
    routing_history: [
      { routing_id: "r-n1-d16a", routing_key: "initial_n1", level: 1, destination: "alumbrado.n1@alquimiablue.com", assigned_at: iso(80), routing_status: "ASSIGNED", work_status: "IN_PROGRESS", first_response_at: iso(75), first_responder: "mario.rojas@alquimiablue.com" },
    ],
    sla: [{ level: 1, status: "MET", started_at: iso(80), due_at: iso(79), first_response_at: iso(75), met_at: iso(75), breached_at: null }],
    escalations: [],
    operational_events: [{ event_id: "ev-d16a", level: 1, interpretation: "RESOLUTION_PROPOSED", received_at: iso(70), sender: "mario.rojas@alquimiablue.com" }],
    resolution: { resolution_id: "res-d16a", proposed_by: "mario.rojas@alquimiablue.com", proposed_at: iso(70), routing_id: "r-n1-d16a", resolution_text: "Poste reemplazado y cableado asegurado.", resolution_status: "PROPOSED" },
    closure_approval: { approval_id: "apr-d16a", approver: "alumbrado.n2@alquimiablue.com", approver_level: 2, decision: null, decision_at: null, decision_reason: null, source_message_id: null },
    result: { request_status: "RESOLUTION_PENDING_APPROVAL", resolved_at: null },
    metrics: {
      routing_count: 1,
      escalation_count: 0,
      sla_total: 1,
      sla_met_count: 1,
      sla_breached_count: 0,
      levels_reached: 1,
      current_age_seconds: 90 * 60,
    },
    timeline: [
      { timestamp: iso(90), event_type: "REQUEST_RECEIVED" },
      { timestamp: iso(89), event_type: "REQUEST_CONFIRMED" },
      { timestamp: iso(80), event_type: "ROUTING_ASSIGNED", level: 1 },
      { timestamp: iso(75), event_type: "SLA_MET", level: 1 },
      { timestamp: iso(70), event_type: "RESOLUTION_PROPOSED" },
    ],
    executive_summary: "El técnico propuso el cierre del caso. Está pendiente la aprobación del supervisor para resolverlo.",
  },
  {
    request_id: "c92d739c-4e6e-4b84-a65d-99a6a90ef712",
    status: "ACTIVE",
    data_source: "LIVE",
    status_fact: "open",
    request: {
      request_id: "c92d739c-4e6e-4b84-a65d-99a6a90ef712",
      sector_id: "alumbrado",
      sector_name: "Alumbrado Público",
      category: "alumbrado",
      description: "Cuadra a oscuras por varias luminarias apagadas",
      location: "Olavarría entre Donato Álvarez y Sanabria",
      origin_channel: "email",
      received_at: iso(150),
      confirmed_at: iso(149),
    },
    routing_history: [
      { routing_id: "r-n1-c92d", routing_key: "initial_n1", level: 1, destination: "alumbrado.n1@alquimiablue.com", assigned_at: iso(140), routing_status: "ASSIGNED", work_status: "IN_PROGRESS", first_response_at: iso(135), first_responder: "mario.rojas@alquimiablue.com" },
    ],
    sla: [{ level: 1, status: "BREACHED", started_at: iso(140), due_at: iso(139), first_response_at: iso(135), breached_at: iso(120) }],
    escalations: [],
    operational_events: [{ event_id: "ev-c92d", level: 1, interpretation: "ACK_OR_PROGRESS", received_at: iso(135), sender: "mario.rojas@alquimiablue.com" }],
    resolution: { resolution_id: "res-c92d", proposed_by: "mario.rojas@alquimiablue.com", proposed_at: iso(100), routing_id: "r-n1-c92d", resolution_text: "Reemplazo de luminarias en curso.", resolution_status: "REJECTED" },
    closure_approval: { approval_id: "apr-c92d", approver: "alumbrado.n2@alquimiablue.com", approver_level: 2, decision: "REJECTED", decision_at: iso(95), decision_reason: "Falta verificar el sector norte de la cuadra.", source_message_id: "gmail-reject-c92d" },
    result: { request_status: "ACTIVE", resolved_at: null },
    metrics: {
      routing_count: 1,
      escalation_count: 0,
      sla_total: 1,
      sla_met_count: 0,
      sla_breached_count: 1,
      levels_reached: 1,
      current_age_seconds: 150 * 60,
    },
    timeline: [
      { timestamp: iso(150), event_type: "REQUEST_RECEIVED" },
      { timestamp: iso(149), event_type: "REQUEST_CONFIRMED" },
      { timestamp: iso(140), event_type: "ROUTING_ASSIGNED", level: 1 },
      { timestamp: iso(135), event_type: "REQUEST_RECEIVED" },
      { timestamp: iso(120), event_type: "SLA_BREACHED", level: 1 },
      { timestamp: iso(100), event_type: "RESOLUTION_PROPOSED" },
    ],
    executive_summary: "El cierre propuesto fue rechazado por el supervisor: falta verificar el sector norte. El caso continúa activo.",
  },
  {
    // Demo N1→N2→N3: escalado al nivel más alto sin primera respuesta N3.
    // No incluye executive_summary a propósito: ejercita el estado
    // "Resumen ejecutivo no disponible" sin romper la vista estructurada.
    request_id: "9c4e6f21-8b3d-4a2e-9f0c-5d7e1a2b3c4d",
    status: "ACTIVE",
    data_source: "LIVE",
    status_fact: "open",
    request: {
      request_id: "9c4e6f21-8b3d-4a2e-9f0c-5d7e1a2b3c4d",
      sector_id: "alumbrado",
      sector_name: "Alumbrado Público",
      category: "alumbrado",
      description: "Subestación de la plaza sin suministro",
      location: "Plaza San Martín",
      origin_channel: "email",
      received_at: iso(300),
      confirmed_at: iso(299),
    },
    routing_history: [
      { routing_id: "r-n1-9c4e", routing_key: "initial_n1", level: 1, destination: "alumbrado.n1@alquimiablue.com", assigned_at: iso(290), routing_status: "ASSIGNED", work_status: "IN_PROGRESS", first_response_at: iso(285), first_responder: "mario.rojas@alquimiablue.com" },
      { routing_id: "r-n2-9c4e", routing_key: "alumbrado_level_2", level: 2, destination: "alumbrado.n2@alquimiablue.com", assigned_at: iso(269), routing_status: "ASSIGNED", work_status: "IN_PROGRESS", first_response_at: iso(255), first_responder: "mario.rojas@alquimiablue.com" },
      { routing_id: "r-n3-9c4e", routing_key: "alumbrado_level_3", level: 3, destination: "alumbrado.n3@alquimiablue.com", assigned_at: iso(239), routing_status: "ASSIGNED", work_status: "ASSIGNED", first_response_at: null, first_responder: null },
    ],
    sla: [
      { level: 1, status: "BREACHED", started_at: iso(290), due_at: iso(289), first_response_at: iso(285), breached_at: iso(270) },
      { level: 2, status: "BREACHED", started_at: iso(269), due_at: iso(268), first_response_at: iso(255), breached_at: iso(240) },
      { level: 3, status: "PENDING", started_at: iso(239), due_at: iso(209), first_response_at: null, breached_at: null },
    ],
    escalations: [
      { escalation_id: "esc-9c4e-1", from_routing_id: "r-n1-9c4e", from_level: 1, to_routing_id: "r-n2-9c4e", to_level: 2, trigger: "FIRST_RESPONSE_SLA_BREACHED", trigger_sla_id: "sla-9c4e-1", created_at: iso(269), completed_at: iso(269), status: "COMPLETED" },
      { escalation_id: "esc-9c4e-2", from_routing_id: "r-n2-9c4e", from_level: 2, to_routing_id: "r-n3-9c4e", to_level: 3, trigger: "FIRST_RESPONSE_SLA_BREACHED", trigger_sla_id: "sla-9c4e-2", created_at: iso(239), completed_at: iso(239), status: "COMPLETED" },
    ],
    operational_events: [
      { event_id: "ev-9c4e-1", routing_id: "r-n1-9c4e", level: 1, interpretation: "ACK_OR_PROGRESS", received_at: iso(285), sender: "mario.rojas@alquimiablue.com" },
      { event_id: "ev-9c4e-2", routing_id: "r-n2-9c4e", level: 2, interpretation: "ACK_OR_PROGRESS", received_at: iso(255), sender: "mario.rojas@alquimiablue.com" },
    ],
    resolution: null,
    closure_approval: null,
    result: { request_status: "ACTIVE", resolved_at: null },
    metrics: {
      routing_count: 3,
      escalation_count: 2,
      sla_total: 3,
      sla_met_count: 0,
      sla_breached_count: 2,
      levels_reached: 3,
      current_age_seconds: 300 * 60,
    },
    timeline: [
      { timestamp: iso(300), event_type: "REQUEST_RECEIVED" },
      { timestamp: iso(299), event_type: "REQUEST_CONFIRMED" },
      { timestamp: iso(290), event_type: "ROUTING_ASSIGNED", level: 1 },
      { timestamp: iso(290), event_type: "SLA_STARTED", level: 1 },
      { timestamp: iso(285), event_type: "REQUEST_RECEIVED" },
      { timestamp: iso(270), event_type: "SLA_BREACHED", level: 1 },
      { timestamp: iso(269), event_type: "ESCALATED" },
      { timestamp: iso(269), event_type: "ROUTING_ASSIGNED", level: 2 },
      { timestamp: iso(269), event_type: "SLA_STARTED", level: 2 },
      { timestamp: iso(255), event_type: "REQUEST_RECEIVED" },
      { timestamp: iso(240), event_type: "SLA_BREACHED", level: 2 },
      { timestamp: iso(239), event_type: "ESCALATED" },
      { timestamp: iso(239), event_type: "ROUTING_ASSIGNED", level: 3 },
      { timestamp: iso(239), event_type: "SLA_STARTED", level: 3 },
    ],
  },
];

export function listFlowCases(): ExecutiveView[] {
  return FLOW_DEMO_CASES;
}

export interface FlowKpi {
  id: string;
  label: string;
  value: number;
  tone: "neutral" | "success" | "warning" | "danger" | "info";
  hint: string;
}

export function getFlowKpis(cases: Array<ExecutiveView | ExecutiveCaseListItem>): FlowKpi[] {
  const open = cases.filter((c) => c.status_fact === "open").length;
  const breached = cases.filter((c) =>
    "has_breached_sla" in c ? c.has_breached_sla : c.sla.some((s) => s.status === "BREACHED"),
  ).length;
  const escalated = cases.filter((c) =>
    "escalation_count" in c ? c.escalation_count > 0 : c.escalations.length > 0,
  ).length;
  const pendingApproval = cases.filter((c) => c.status_fact === "pending_approval").length;
  const resolved = cases.filter((c) => c.status_fact === "closed").length;

  return [
    { id: "active", label: "Casos activos", value: open, tone: "info", hint: "requieren seguimiento operativo" },
    { id: "breached", label: "SLA comprometidos", value: breached, tone: "danger", hint: "vencidos o con respuesta tardía" },
    { id: "escalated", label: "Escalados", value: escalated, tone: "warning", hint: "avanzaron de nivel" },
    { id: "approval", label: "Pendientes de aprobación", value: pendingApproval, tone: "info", hint: "esperan decisión de supervisor" },
    { id: "resolved", label: "Resueltos", value: resolved, tone: "success", hint: "cerrados con auditoría" },
  ];
}
