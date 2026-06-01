export interface DashboardCard {
  id: string;
  workspaceId: string;
  label: string;
  value: string;
  trend: string;
  description: string;
}

export const dashboardCards: DashboardCard[] = [
  {
    id: "card-team360-organizations",
    workspaceId: "ws-team360-control",
    label: "Organizaciones activas",
    value: "4",
    trend: "+2 en activación",
    description: "Red completa visible para administración Team360.",
  },
  {
    id: "card-team360-services",
    workspaceId: "ws-team360-control",
    label: "Servicios activos",
    value: "5",
    trend: "+2 este mes",
    description: "Prestaciones activas o en seguimiento operativo.",
  },
  {
    id: "card-team360-alerts",
    workspaceId: "ws-team360-control",
    label: "Alertas abiertas",
    value: "3",
    trend: "-1 esta semana",
    description: "Situaciones que requieren visibilidad o acción.",
  },
  {
    id: "card-mama-mia-clients",
    workspaceId: "ws-mama-mia-israel",
    label: "Clientes gestionados",
    value: "2",
    trend: "+1 este mes",
    description: "Clientes dentro del subárbol autorizado del partner.",
  },
  {
    id: "card-mama-mia-onboarding",
    workspaceId: "ws-mama-mia-israel",
    label: "Onboardings pendientes",
    value: "1",
    trend: "Requiere seguimiento",
    description: "Activaciones que todavía necesitan coordinación.",
  },
  {
    id: "card-netzaj-questions",
    workspaceId: "ws-netzaj-marketplace",
    label: "Preguntas hoy",
    value: "28",
    trend: "+8%",
    description: "Consultas registradas durante el día.",
  },
  {
    id: "card-netzaj-response",
    workspaceId: "ws-netzaj-marketplace",
    label: "Tiempo medio de respuesta",
    value: "14 min",
    trend: "-3 min",
    description: "Promedio observado en preguntas atendidas.",
  },
  {
    id: "card-netzaj-approvals",
    workspaceId: "ws-netzaj-marketplace",
    label: "Aprobaciones pendientes",
    value: "2",
    trend: "Revisión necesaria",
    description: "Acciones que conservan control humano.",
  },
  {
    id: "card-carmel-leads",
    workspaceId: "ws-carmel-retail",
    label: "Leads procesados",
    value: "184",
    trend: "+12%",
    description: "Consultas comerciales ordenadas durante el período.",
  },
  {
    id: "card-galil-setup",
    workspaceId: "ws-galil-commerce",
    label: "Avance de configuración",
    value: "60%",
    trend: "En curso",
    description: "Preparación inicial antes de activar el servicio.",
  },
];
