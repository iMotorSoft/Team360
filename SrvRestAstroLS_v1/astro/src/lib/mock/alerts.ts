export type AlertSeverity = "info" | "warning" | "critical";
export type AlertStatus = "open" | "acknowledged" | "resolved";
export type AlertType = "technical" | "business" | "approval";

export interface Alert {
  id: string;
  title: string;
  type: AlertType;
  severity: AlertSeverity;
  workspaceId: string;
  serviceId: string;
  status: AlertStatus;
  createdAt: string;
  suggestedAction: string;
}

export const alerts: Alert[] = [
  {
    id: "alert-netzaj-approval",
    title: "Dos borradores requieren aprobación",
    type: "approval",
    severity: "warning",
    workspaceId: "ws-netzaj-marketplace",
    serviceId: "svc-netzaj-questions",
    status: "open",
    createdAt: "2026-05-31T12:21:00Z",
    suggestedAction: "Revisar borradores y aprobar solo las respuestas correctas.",
  },
  {
    id: "alert-netzaj-response-time",
    title: "Tiempo de respuesta por encima del objetivo",
    type: "business",
    severity: "info",
    workspaceId: "ws-netzaj-marketplace",
    serviceId: "svc-netzaj-questions",
    status: "acknowledged",
    createdAt: "2026-05-31T10:40:00Z",
    suggestedAction: "Revisar el volumen reciente y priorizar consultas pendientes.",
  },
  {
    id: "alert-galil-onboarding",
    title: "Configuración inicial pendiente",
    type: "technical",
    severity: "warning",
    workspaceId: "ws-galil-commerce",
    serviceId: "svc-galil-catalog",
    status: "open",
    createdAt: "2026-05-30T15:20:00Z",
    suggestedAction: "Completar datos de configuración con soporte.",
  },
  {
    id: "alert-carmel-weekly-review",
    title: "Reporte semanal listo para revisión",
    type: "approval",
    severity: "info",
    workspaceId: "ws-carmel-retail",
    serviceId: "svc-carmel-leads",
    status: "open",
    createdAt: "2026-05-30T08:05:00Z",
    suggestedAction: "Validar el resumen antes de compartirlo internamente.",
  },
  {
    id: "alert-galil-stock-differences",
    title: "Siete publicaciones tienen diferencias de stock",
    type: "business",
    severity: "warning",
    workspaceId: "ws-galil-commerce",
    serviceId: "svc-galil-stock-publications",
    status: "open",
    createdAt: "2026-05-31T12:12:00Z",
    suggestedAction: "Revisar las publicaciones señaladas antes de actualizar información.",
  },
  {
    id: "alert-carmel-bank-connection",
    title: "Conexión demo pendiente de aprobación",
    type: "approval",
    severity: "info",
    workspaceId: "ws-carmel-retail",
    serviceId: "svc-carmel-bank-reconciliation",
    status: "open",
    createdAt: "2026-05-31T09:20:00Z",
    suggestedAction: "Aprobar la conexión demo para completar el onboarding.",
  },
  {
    id: "alert-galil-attention-faq",
    title: "Dos respuestas frecuentes requieren confirmación",
    type: "approval",
    severity: "info",
    workspaceId: "ws-galil-commerce",
    serviceId: "svc-galil-initial-attention",
    status: "open",
    createdAt: "2026-05-31T11:30:00Z",
    suggestedAction: "Confirmar el contenido antes de habilitar nuevas respuestas.",
  },
];
