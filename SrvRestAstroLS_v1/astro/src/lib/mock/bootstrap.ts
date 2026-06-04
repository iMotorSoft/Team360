import { MOCK_ACTIVE_PROFILE } from "../../components/global.js";
import { alerts, type Alert } from "./alerts";
import { dashboardCards, type DashboardCard } from "./dashboards";
import { organizations, type Organization, type OrganizationStatus } from "./organizations";
import { reports, type Report } from "./reports";
import { runs, type Run } from "./runs";
import { services, type Service } from "./services";
import { tasks, type Task } from "./tasks";
import { users, type User, type UserRole } from "./users";
import { workspaces, type Workspace } from "./workspaces";

export type MockProfileId =
  | "team360_admin"
  | "team360_operator"
  | "team360_support"
  | "partner_admin"
  | "client_admin";

export interface MockProfile {
  id: MockProfileId;
  label: string;
  description: string;
  defaultWorkspaceId: string;
}

export interface ActiveMembership {
  userId: string;
  role: UserRole;
  membershipOrganizationId: string;
  activeOrganizationId: string;
  activeWorkspaceId: string;
  accessMode: "own" | "delegated";
  delegatedByOrganizationId: string | null;
}

export interface AuthorizedTreeNode {
  organizationId: string;
  name: string;
  status: OrganizationStatus;
  children: AuthorizedTreeNode[];
}

export interface NotificationSummary {
  unreadAlerts: number;
  criticalAlerts: number;
  pendingTasks: number;
  activeWorkspaceAlerts: number;
}

export interface ConsoleBootstrap {
  profile: MockProfileId;
  currentUser: User;
  activeMembership: ActiveMembership;
  membershipOrganization: Organization;
  accessibleOrganizations: Organization[];
  accessibleWorkspaces: Workspace[];
  activeOrganization: Organization;
  activeWorkspace: Workspace;
  effectivePermissions: string[];
  enabledModules: string[];
  contractedServices: Service[];
  authorizedTree: AuthorizedTreeNode[];
  notificationSummary: NotificationSummary;
  featureFlags: {
    mockMode: true;
    organizationSwitcher: boolean;
    workspaceSwitcher: boolean;
    rtlPreview: true;
  };
  uiHints: {
    profileLabel: string;
    accessMode: ActiveMembership["accessMode"];
    technicalDepth: "full" | "operational" | "business";
    showDelegatedAccessNotice: boolean;
  };
  aguiCapabilities: {
    enabled: false;
    transport: "disabled";
    events: [];
  };
}

export interface MockWorkspaceContext {
  organization: Organization;
  workspace: Workspace;
  services: Service[];
  reports: Report[];
  alerts: Alert[];
  tasks: Task[];
  runs: Run[];
  dashboardCards: DashboardCard[];
}

interface MockProfileDefinition extends MockProfile {
  userId: string;
  accessibleOrganizationIds: string[];
  accessibleWorkspaceIds: string[];
  effectivePermissions: string[];
  enabledModules: string[];
  technicalDepth: ConsoleBootstrap["uiHints"]["technicalDepth"];
}

const profileDefinitions: Record<MockProfileId, MockProfileDefinition> = {
  team360_admin: {
    id: "team360_admin",
    label: "Team360 Admin",
    description: "Administración global de red, clientes, servicios y operación técnica.",
    userId: "user-team360-admin",
    defaultWorkspaceId: "ws-team360-control",
    accessibleOrganizationIds: organizations.map(({ id }) => id),
    accessibleWorkspaceIds: workspaces.map(({ id }) => id),
    effectivePermissions: [
      "organizations.read",
      "organizations.manage",
      "workspaces.read",
      "workspaces.switch",
      "services.read",
      "services.manage",
      "workers.read",
      "runs.read",
      "reports.read",
      "alerts.read",
      "tasks.read",
      "users.manage",
      "billing.read",
      "audit.read",
    ],
    enabledModules: [
      "home",
      "organizations",
      "partners",
      "clients",
      "workspaces",
      "packages",
      "services",
      "workers",
      "runs",
      "dashboards",
      "reports",
      "alerts",
      "tasks",
      "integrations",
      "users",
      "roles",
      "billing",
      "support",
      "audit",
      "settings",
      "diagnosis",
    ],
    technicalDepth: "full",
  },
  team360_operator: {
    id: "team360_operator",
    label: "Operador Team360",
    description: "Operación diaria sobre servicios y clientes asignados.",
    userId: "user-team360-operator",
    defaultWorkspaceId: "ws-netzaj-marketplace",
    accessibleOrganizationIds: ["org-team360", "org-carmel-retail", "org-netzaj-racing"],
    accessibleWorkspaceIds: ["ws-team360-control", "ws-carmel-retail", "ws-netzaj-marketplace"],
    effectivePermissions: [
      "workspaces.read",
      "workspaces.switch",
      "services.read",
      "workers.read",
      "runs.read",
      "runs.retry",
      "alerts.read",
      "alerts.acknowledge",
      "tasks.read",
      "tasks.manage",
      "support.read",
    ],
    enabledModules: ["home", "work_queue", "clients", "services", "workers", "runs", "alerts", "tasks", "support", "diagnosis"],
    technicalDepth: "operational",
  },
  team360_support: {
    id: "team360_support",
    label: "Soporte Team360",
    description: "Seguimiento delegado de solicitudes, evidencias y estados visibles.",
    userId: "user-team360-support",
    defaultWorkspaceId: "ws-galil-commerce",
    accessibleOrganizationIds: ["org-carmel-retail", "org-netzaj-racing", "org-galil-home"],
    accessibleWorkspaceIds: ["ws-carmel-retail", "ws-netzaj-marketplace", "ws-galil-commerce"],
    effectivePermissions: [
      "workspaces.read",
      "workspaces.switch",
      "services.read",
      "reports.read",
      "alerts.read",
      "tasks.read",
      "support.read",
      "support.manage",
    ],
    enabledModules: ["home", "clients", "services", "reports", "alerts", "tasks", "support"],
    technicalDepth: "business",
  },
  partner_admin: {
    id: "partner_admin",
    label: "Admin Distribuidor",
    description: "Gestión de la organización partner y su subárbol autorizado.",
    userId: "user-mama-mia-admin",
    defaultWorkspaceId: "ws-mama-mia-israel",
    accessibleOrganizationIds: ["org-mama-mia-360", "org-netzaj-racing", "org-galil-home"],
    accessibleWorkspaceIds: ["ws-mama-mia-israel", "ws-netzaj-marketplace", "ws-galil-commerce"],
    effectivePermissions: [
      "organizations.read_descendants",
      "workspaces.read",
      "workspaces.switch",
      "services.read",
      "reports.read",
      "alerts.read",
      "tasks.read",
      "team.manage",
      "support.read",
    ],
    enabledModules: ["home", "clients", "leads", "services", "results", "reports", "alerts", "tasks", "team", "support", "settings"],
    technicalDepth: "business",
  },
  client_admin: {
    id: "client_admin",
    label: "Admin Cliente",
    description: "Consulta y operación de servicios contratados en un único cliente.",
    userId: "user-netzaj-admin",
    defaultWorkspaceId: "ws-netzaj-marketplace",
    accessibleOrganizationIds: ["org-netzaj-racing"],
    accessibleWorkspaceIds: ["ws-netzaj-marketplace"],
    effectivePermissions: [
      "workspaces.read",
      "services.read",
      "reports.read",
      "alerts.read",
      "tasks.read",
      "tasks.approve",
      "team.manage",
      "support.read",
    ],
    enabledModules: ["home", "services", "results", "reports", "automations", "files", "alerts", "tasks", "team", "support", "settings"],
    technicalDepth: "business",
  },
};

function requireById<T extends { id: string }>(items: T[], id: string, entityName: string): T {
  const item = items.find((candidate) => candidate.id === id);

  if (!item) {
    throw new Error(`Mock ${entityName} not found: ${id}`);
  }

  return item;
}

function buildAuthorizedTree(accessibleOrganizations: Organization[]): AuthorizedTreeNode[] {
  const allowedIds = new Set(accessibleOrganizations.map(({ id }) => id));

  function buildNode(organization: Organization): AuthorizedTreeNode {
    return {
      organizationId: organization.id,
      name: organization.name,
      status: organization.status,
      children: accessibleOrganizations
        .filter(({ parentOrganizationId }) => parentOrganizationId === organization.id)
        .map(buildNode),
    };
  }

  return accessibleOrganizations
    .filter(({ parentOrganizationId }) => !parentOrganizationId || !allowedIds.has(parentOrganizationId))
    .map(buildNode);
}

function getNotificationSummary(accessibleWorkspaceIds: string[], activeWorkspaceId: string): NotificationSummary {
  const allowedWorkspaceIds = new Set(accessibleWorkspaceIds);
  const visibleAlerts = alerts.filter(({ status, workspaceId }) => status !== "resolved" && allowedWorkspaceIds.has(workspaceId));
  const visibleTasks = tasks.filter(({ status, workspaceId }) => status !== "completed" && allowedWorkspaceIds.has(workspaceId));

  return {
    unreadAlerts: visibleAlerts.filter(({ status }) => status === "open").length,
    criticalAlerts: visibleAlerts.filter(({ severity }) => severity === "critical").length,
    pendingTasks: visibleTasks.length,
    activeWorkspaceAlerts: visibleAlerts.filter(({ workspaceId }) => workspaceId === activeWorkspaceId).length,
  };
}

export function getMockProfiles(): MockProfile[] {
  return Object.values(profileDefinitions).map(({ id, label, description, defaultWorkspaceId }) => ({
    id,
    label,
    description,
    defaultWorkspaceId,
  }));
}

export function getMockBootstrap(
  profile: MockProfileId = MOCK_ACTIVE_PROFILE,
  requestedWorkspaceId?: string,
): ConsoleBootstrap {
  const definition = profileDefinitions[profile];
  const activeWorkspaceId = requestedWorkspaceId ?? definition.defaultWorkspaceId;

  if (!definition.accessibleWorkspaceIds.includes(activeWorkspaceId)) {
    throw new Error(`Workspace ${activeWorkspaceId} is outside mock profile scope: ${profile}`);
  }

  const currentUser = requireById(users, definition.userId, "user");
  const membershipOrganization = requireById(organizations, currentUser.organizationId, "membership organization");
  const activeWorkspace = requireById(workspaces, activeWorkspaceId, "workspace");
  const activeOrganization = requireById(organizations, activeWorkspace.organizationId, "organization");
  const accessibleOrganizations = organizations.filter(({ id }) => definition.accessibleOrganizationIds.includes(id));
  const accessibleWorkspaces = workspaces.filter(({ id }) => definition.accessibleWorkspaceIds.includes(id));
  const accessMode = currentUser.organizationId === activeOrganization.id ? "own" : "delegated";
  const canViewInternalServices = definition.technicalDepth !== "business";

  return {
    profile,
    currentUser,
    activeMembership: {
      userId: currentUser.id,
      role: currentUser.role,
      membershipOrganizationId: currentUser.organizationId,
      activeOrganizationId: activeOrganization.id,
      activeWorkspaceId: activeWorkspace.id,
      accessMode,
      delegatedByOrganizationId: accessMode === "delegated" ? currentUser.organizationId : null,
    },
    membershipOrganization,
    accessibleOrganizations,
    accessibleWorkspaces,
    activeOrganization,
    activeWorkspace,
    effectivePermissions: definition.effectivePermissions,
    enabledModules: definition.enabledModules,
    contractedServices: services.filter(
      ({ visibleToClient, workspaceId }) => workspaceId === activeWorkspace.id && (canViewInternalServices || visibleToClient),
    ),
    authorizedTree: buildAuthorizedTree(accessibleOrganizations),
    notificationSummary: getNotificationSummary(definition.accessibleWorkspaceIds, activeWorkspace.id),
    featureFlags: {
      mockMode: true,
      organizationSwitcher: accessibleOrganizations.length > 1,
      workspaceSwitcher: accessibleWorkspaces.length > 1,
      rtlPreview: true,
    },
    uiHints: {
      profileLabel: definition.label,
      accessMode,
      technicalDepth: definition.technicalDepth,
      showDelegatedAccessNotice: accessMode === "delegated",
    },
    aguiCapabilities: {
      enabled: false,
      transport: "disabled",
      events: [],
    },
  };
}

export function getMockWorkspaceContext(
  workspaceId: string,
  { includeTechnicalDetails = false }: { includeTechnicalDetails?: boolean } = {},
): MockWorkspaceContext {
  const workspace = requireById(workspaces, workspaceId, "workspace");
  const organization = requireById(organizations, workspace.organizationId, "organization");
  const workspaceServices = services.filter((service) => service.workspaceId === workspaceId);
  const serviceIds = new Set(workspaceServices.map(({ id }) => id));

  return {
    organization,
    workspace,
    services: workspaceServices.filter(({ visibleToClient }) => includeTechnicalDetails || visibleToClient),
    reports: reports.filter((report) => report.workspaceId === workspaceId),
    alerts: alerts.filter((alert) => alert.workspaceId === workspaceId),
    tasks: tasks.filter((task) => task.workspaceId === workspaceId),
    runs: includeTechnicalDetails ? runs.filter(({ serviceId }) => serviceIds.has(serviceId)) : [],
    dashboardCards: dashboardCards.filter((card) => card.workspaceId === workspaceId),
  };
}
