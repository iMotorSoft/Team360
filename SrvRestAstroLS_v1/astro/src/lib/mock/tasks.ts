export type TaskAssigneeType = "team360_operator" | "team360_support" | "partner_admin" | "client_admin";
export type TaskStatus = "pending" | "in_progress" | "completed";
export type TaskPriority = "low" | "medium" | "high";

export interface Task {
  id: string;
  title: string;
  assigneeType: TaskAssigneeType;
  assigneeLabel: string;
  workspaceId: string;
  serviceId: string;
  dueDate: string;
  status: TaskStatus;
  priority: TaskPriority;
}

export const tasks: Task[] = [
  {
    id: "task-netzaj-review-drafts",
    title: "Revisar borradores de respuesta pendientes",
    assigneeType: "client_admin",
    assigneeLabel: "Responsable cliente",
    workspaceId: "ws-netzaj-marketplace",
    serviceId: "svc-netzaj-questions",
    dueDate: "2026-05-31",
    status: "pending",
    priority: "high",
  },
  {
    id: "task-netzaj-check-latency",
    title: "Verificar causa del aumento de tiempo de respuesta",
    assigneeType: "team360_operator",
    assigneeLabel: "Operación Team360",
    workspaceId: "ws-netzaj-marketplace",
    serviceId: "svc-netzaj-questions",
    dueDate: "2026-06-01",
    status: "in_progress",
    priority: "medium",
  },
  {
    id: "task-galil-complete-setup",
    title: "Coordinar datos faltantes para activación",
    assigneeType: "partner_admin",
    assigneeLabel: "Admin partner",
    workspaceId: "ws-galil-commerce",
    serviceId: "svc-galil-catalog",
    dueDate: "2026-06-03",
    status: "pending",
    priority: "high",
  },
  {
    id: "task-carmel-review-report",
    title: "Revisar resumen comercial semanal",
    assigneeType: "client_admin",
    assigneeLabel: "Responsable cliente",
    workspaceId: "ws-carmel-retail",
    serviceId: "svc-carmel-leads",
    dueDate: "2026-06-01",
    status: "pending",
    priority: "medium",
  },
  {
    id: "task-carmel-approve-bank-connection",
    title: "Aprobar conexión de cuenta demo",
    assigneeType: "client_admin",
    assigneeLabel: "Administración cliente",
    workspaceId: "ws-carmel-retail",
    serviceId: "svc-carmel-bank-reconciliation",
    dueDate: "2026-06-02",
    status: "pending",
    priority: "high",
  },
  {
    id: "task-carmel-confirm-lead-rule",
    title: "Confirmar regla de automatización para leads sin respuesta",
    assigneeType: "client_admin",
    assigneeLabel: "Responsable comercial",
    workspaceId: "ws-carmel-retail",
    serviceId: "svc-carmel-leads-crm",
    dueDate: "2026-06-03",
    status: "pending",
    priority: "medium",
  },
  {
    id: "task-galil-review-stock",
    title: "Revisar diferencias de stock detectadas",
    assigneeType: "client_admin",
    assigneeLabel: "Responsable de catálogo",
    workspaceId: "ws-galil-commerce",
    serviceId: "svc-galil-stock-publications",
    dueDate: "2026-06-01",
    status: "in_progress",
    priority: "high",
  },
  {
    id: "task-galil-confirm-faq",
    title: "Confirmar respuestas frecuentes nuevas",
    assigneeType: "client_admin",
    assigneeLabel: "Responsable de atención",
    workspaceId: "ws-galil-commerce",
    serviceId: "svc-galil-initial-attention",
    dueDate: "2026-06-02",
    status: "pending",
    priority: "medium",
  },
];
