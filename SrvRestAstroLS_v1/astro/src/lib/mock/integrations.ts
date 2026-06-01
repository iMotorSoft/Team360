export interface MockIntegration {
  id: string;
  workspaceId: string;
  name: string;
  category: string;
  status: "connected" | "pending" | "review";
  note: string;
}

export const integrations: MockIntegration[] = [
  {
    id: "integration-carmel-crm",
    workspaceId: "ws-carmel-retail",
    name: "CRM demo",
    category: "crm",
    status: "connected",
    note: "Configuración visual simulada. Sin conexión API real.",
  },
  {
    id: "integration-carmel-bank",
    workspaceId: "ws-carmel-retail",
    name: "Cuenta bancaria demo",
    category: "administration",
    status: "pending",
    note: "Placeholder de onboarding. No contiene credenciales ni acceso bancario.",
  },
  {
    id: "integration-galil-marketplace",
    workspaceId: "ws-galil-commerce",
    name: "Marketplace demo",
    category: "marketplace",
    status: "review",
    note: "Datos simulados para revisar UX de catálogo.",
  },
  {
    id: "integration-galil-attention",
    workspaceId: "ws-galil-commerce",
    name: "Canal de atención demo",
    category: "messaging",
    status: "connected",
    note: "Canal visual simulado. Sin transporte de mensajes.",
  },
];
