import type { Locale } from "../i18n";

export type UserRole =
  | "team360_admin"
  | "team360_operator"
  | "team360_support"
  | "partner_admin"
  | "partner_operator"
  | "client_admin"
  | "client_viewer";

export interface User {
  id: string;
  name: string;
  email: string;
  role: UserRole;
  organizationId: string;
  workspaceIds: string[];
  avatarInitials: string;
  locale: Locale;
  status: "active" | "invited";
  permissionSummary: string[];
}

export const users: User[] = [
  {
    id: "user-team360-admin",
    name: "Mario Rojas",
    email: "mario.rojas@alquimiablue.com",
    role: "team360_admin",
    organizationId: "org-team360",
    workspaceIds: [
      "ws-team360-control",
      "ws-team360-live-public-site",
      "ws-carmel-retail",
      "ws-mama-mia-israel",
      "ws-netzaj-marketplace",
      "ws-galil-commerce",
      "ws-nexo-onboarding",
    ],
    avatarInitials: "MR",
    locale: "es",
    status: "active",
    permissionSummary: ["Plataforma", "Red completa", "Servicios", "Usuarios"],
  },
  {
    id: "user-team360-operator",
    name: "Martín Paz",
    email: "martin.operator@example.test",
    role: "team360_operator",
    organizationId: "org-team360",
    workspaceIds: ["ws-team360-control", "ws-carmel-retail", "ws-netzaj-marketplace"],
    avatarInitials: "MP",
    locale: "es",
    status: "active",
    permissionSummary: ["Servicios asignados", "Runs", "Alertas", "Tareas"],
  },
  {
    id: "user-team360-support",
    name: "Lucía Ferrer",
    email: "lucia.support@example.test",
    role: "team360_support",
    organizationId: "org-team360",
    workspaceIds: ["ws-carmel-retail", "ws-netzaj-marketplace", "ws-galil-commerce"],
    avatarInitials: "LF",
    locale: "es",
    status: "active",
    permissionSummary: ["Soporte", "Reportes", "Alertas visibles"],
  },
  {
    id: "user-mama-mia-admin",
    name: "Yael Cohen",
    email: "yael.partner@example.test",
    role: "partner_admin",
    organizationId: "org-mama-mia-360",
    workspaceIds: ["ws-mama-mia-israel", "ws-netzaj-marketplace", "ws-galil-commerce"],
    avatarInitials: "YC",
    locale: "es",
    status: "active",
    permissionSummary: ["Clientes propios", "Servicios visibles", "Equipo partner"],
  },
  {
    id: "user-team360-live-admin",
    name: "Mario Rojas Marconi",
    email: "mario.rojas.marconi@gmail.com",
    role: "client_admin",
    organizationId: "org-team360-live",
    workspaceIds: ["ws-team360-live-public-site"],
    avatarInitials: "MR",
    locale: "es",
    status: "active",
    permissionSummary: ["Servicio Vera", "Leads propios", "Resultados", "Configuración cliente"],
  },
  {
    id: "user-netzaj-admin",
    name: "Daniel Levi",
    email: "daniel.client@example.test",
    role: "client_admin",
    organizationId: "org-netzaj-racing",
    workspaceIds: ["ws-netzaj-marketplace"],
    avatarInitials: "DL",
    locale: "es",
    status: "active",
    permissionSummary: ["Servicios contratados", "Reportes", "Aprobaciones"],
  },
  {
    id: "user-galil-viewer",
    name: "Noa Mizrahi",
    email: "noa.viewer@example.test",
    role: "client_viewer",
    organizationId: "org-galil-home",
    workspaceIds: ["ws-galil-commerce"],
    avatarInitials: "NM",
    locale: "he",
    status: "invited",
    permissionSummary: ["Lectura de resultados", "Reportes"],
  },
];
