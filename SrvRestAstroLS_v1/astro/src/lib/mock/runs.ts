export type RunStatus = "completed" | "running" | "attention" | "failed";

export interface Run {
  id: string;
  serviceId: string;
  workerName: string;
  status: RunStatus;
  startedAt: string;
  finishedAt: string | null;
  summary: string;
  durationSeconds: number | null;
  errorCount: number;
  health: "healthy" | "warning" | "critical";
}

export const runs: Run[] = [
  {
    id: "run-netzaj-questions-1042",
    serviceId: "svc-netzaj-questions",
    workerName: "meli_questions_draft_worker",
    status: "attention",
    startedAt: "2026-05-31T12:17:00Z",
    finishedAt: "2026-05-31T12:18:00Z",
    summary: "Se prepararon dos borradores que requieren aprobación humana.",
    durationSeconds: 60,
    errorCount: 0,
    health: "warning",
  },
  {
    id: "run-netzaj-report-193",
    serviceId: "svc-netzaj-reporting",
    workerName: "marketplace_reporting_worker",
    status: "completed",
    startedAt: "2026-05-31T08:58:00Z",
    finishedAt: "2026-05-31T09:00:00Z",
    summary: "Reporte semanal generado correctamente.",
    durationSeconds: 120,
    errorCount: 0,
    health: "healthy",
  },
  {
    id: "run-carmel-leads-826",
    serviceId: "svc-carmel-leads",
    workerName: "sales_followup_worker",
    status: "completed",
    startedAt: "2026-05-31T12:30:00Z",
    finishedAt: "2026-05-31T12:32:00Z",
    summary: "Se actualizaron seguimientos y prioridades comerciales.",
    durationSeconds: 120,
    errorCount: 0,
    health: "healthy",
  },
  {
    id: "run-team360-observability-321",
    serviceId: "svc-team360-observability",
    workerName: "platform_health_worker",
    status: "completed",
    startedAt: "2026-05-31T12:39:00Z",
    finishedAt: "2026-05-31T12:40:00Z",
    summary: "Supervisión interna completada sin incidentes críticos nuevos.",
    durationSeconds: 60,
    errorCount: 0,
    health: "healthy",
  },
  {
    id: "run-carmel-leads-crm-918",
    serviceId: "svc-carmel-leads-crm",
    workerName: "lead_crm_sync_worker",
    status: "completed",
    startedAt: "2026-05-31T13:03:00Z",
    finishedAt: "2026-05-31T13:05:00Z",
    summary: "Se capturaron y normalizaron nuevas oportunidades comerciales.",
    durationSeconds: 120,
    errorCount: 0,
    health: "healthy",
  },
  {
    id: "run-galil-stock-411",
    serviceId: "svc-galil-stock-publications",
    workerName: "stock_publication_compare_worker",
    status: "attention",
    startedAt: "2026-05-31T12:08:00Z",
    finishedAt: "2026-05-31T12:10:00Z",
    summary: "Se detectaron siete diferencias de stock para revisión.",
    durationSeconds: 120,
    errorCount: 0,
    health: "warning",
  },
  {
    id: "run-galil-attention-552",
    serviceId: "svc-galil-initial-attention",
    workerName: "initial_attention_worker",
    status: "completed",
    startedAt: "2026-05-31T12:41:00Z",
    finishedAt: "2026-05-31T12:42:00Z",
    summary: "Se orientaron consultas frecuentes y se derivaron excepciones.",
    durationSeconds: 60,
    errorCount: 0,
    health: "healthy",
  },
];
