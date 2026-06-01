export type WorkerHealth = "healthy" | "warning" | "critical" | "pending";

export interface Worker {
  id: string;
  name: string;
  serviceId: string;
  status: "active" | "onboarding" | "attention";
  health: WorkerHealth;
  lastRunAt: string | null;
  errorCount: number;
  averageDurationSeconds: number | null;
}

export const workers: Worker[] = [
  {
    id: "worker-platform-health",
    name: "platform_health_worker",
    serviceId: "svc-team360-observability",
    status: "active",
    health: "healthy",
    lastRunAt: "2026-05-31T12:40:00Z",
    errorCount: 0,
    averageDurationSeconds: 58,
  },
  {
    id: "worker-lead-crm-sync",
    name: "lead_crm_sync_worker",
    serviceId: "svc-carmel-leads-crm",
    status: "active",
    health: "healthy",
    lastRunAt: "2026-05-31T13:05:00Z",
    errorCount: 0,
    averageDurationSeconds: 116,
  },
  {
    id: "worker-executive-report",
    name: "executive_report_worker",
    serviceId: "svc-carmel-weekly-executive-report",
    status: "active",
    health: "healthy",
    lastRunAt: "2026-05-30T08:00:00Z",
    errorCount: 0,
    averageDurationSeconds: 142,
  },
  {
    id: "worker-stock-publications",
    name: "stock_publication_compare_worker",
    serviceId: "svc-galil-stock-publications",
    status: "attention",
    health: "warning",
    lastRunAt: "2026-05-31T12:10:00Z",
    errorCount: 0,
    averageDurationSeconds: 121,
  },
  {
    id: "worker-bank-reconciliation",
    name: "bank_reconciliation_assist_worker",
    serviceId: "svc-carmel-bank-reconciliation",
    status: "onboarding",
    health: "pending",
    lastRunAt: null,
    errorCount: 0,
    averageDurationSeconds: null,
  },
  {
    id: "worker-initial-attention",
    name: "initial_attention_worker",
    serviceId: "svc-galil-initial-attention",
    status: "active",
    health: "healthy",
    lastRunAt: "2026-05-31T12:42:00Z",
    errorCount: 0,
    averageDurationSeconds: 63,
  },
];
