export type ReportStatus = "ready" | "generating" | "scheduled";
export type ReportType = "executive_summary" | "operations" | "alerts" | "reconciliation" | "catalog";

export interface Report {
  id: string;
  title: string;
  workspaceId: string;
  serviceId: string;
  status: ReportStatus;
  generatedAt: string | null;
  period: string;
  type: ReportType;
}

export const reports: Report[] = [
  {
    id: "report-carmel-weekly",
    title: "Resumen comercial semanal",
    workspaceId: "ws-carmel-retail",
    serviceId: "svc-carmel-leads",
    status: "ready",
    generatedAt: "2026-05-30T08:00:00Z",
    period: "23 may - 30 may 2026",
    type: "executive_summary",
  },
  {
    id: "report-netzaj-questions-weekly",
    title: "Actividad semanal de preguntas",
    workspaceId: "ws-netzaj-marketplace",
    serviceId: "svc-netzaj-reporting",
    status: "ready",
    generatedAt: "2026-05-31T09:00:00Z",
    period: "25 may - 31 may 2026",
    type: "operations",
  },
  {
    id: "report-netzaj-alerts",
    title: "Pendientes y alertas de marketplace",
    workspaceId: "ws-netzaj-marketplace",
    serviceId: "svc-netzaj-questions",
    status: "generating",
    generatedAt: null,
    period: "31 may 2026",
    type: "alerts",
  },
  {
    id: "report-mama-mia-network",
    title: "Estado mensual de clientes gestionados",
    workspaceId: "ws-mama-mia-israel",
    serviceId: "svc-mama-mia-network",
    status: "ready",
    generatedAt: "2026-05-31T07:30:00Z",
    period: "mayo 2026",
    type: "executive_summary",
  },
  {
    id: "report-carmel-executive-weekly",
    title: "Reporte Ejecutivo Semanal",
    workspaceId: "ws-carmel-retail",
    serviceId: "svc-carmel-weekly-executive-report",
    status: "ready",
    generatedAt: "2026-05-30T08:00:00Z",
    period: "23 may - 30 may 2026",
    type: "executive_summary",
  },
  {
    id: "report-carmel-leads-funnel",
    title: "Seguimiento de leads y oportunidades",
    workspaceId: "ws-carmel-retail",
    serviceId: "svc-carmel-leads-crm",
    status: "ready",
    generatedAt: "2026-05-31T13:10:00Z",
    period: "mayo 2026",
    type: "operations",
  },
  {
    id: "report-galil-stock-review",
    title: "Diferencias de stock y publicaciones",
    workspaceId: "ws-galil-commerce",
    serviceId: "svc-galil-stock-publications",
    status: "generating",
    generatedAt: null,
    period: "31 may 2026",
    type: "catalog",
  },
  {
    id: "report-carmel-reconciliation-preview",
    title: "Vista previa de conciliación asistida",
    workspaceId: "ws-carmel-retail",
    serviceId: "svc-carmel-bank-reconciliation",
    status: "scheduled",
    generatedAt: null,
    period: "primera ejecución pendiente",
    type: "reconciliation",
  },
];
