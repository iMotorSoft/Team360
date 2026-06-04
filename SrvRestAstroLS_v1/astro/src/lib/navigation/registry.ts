import type { OrganizationType } from "../mock";

export type ConsoleAudience = "owner" | "operator" | "partner" | "client";
export type ConsoleNavigationGroup = "overview" | "network" | "operations" | "results" | "administration";
export type ConsoleView =
  | "home"
  | "organizations"
  | "partners"
  | "clients"
  | "workspaces"
  | "services"
  | "client-services"
  | "results"
  | "workers"
  | "runs"
  | "reports"
  | "alerts"
  | "tasks"
  | "team"
  | "support"
  | "settings"
  | "diagnosis";

export interface NavigationRegistryItem {
  id: string;
  view: ConsoleView;
  labelKey: string;
  icon: string;
  group: ConsoleNavigationGroup;
  module: string;
  audiences: ConsoleAudience[];
  organizationTypes?: OrganizationType[];
  requiredPermissionsAny?: string[];
  requiresWorkspace?: boolean;
  requiresContractedServices?: boolean;
}

export const navigationGroupLabelKeys: Record<ConsoleNavigationGroup, string> = {
  overview: "nav.group.overview",
  network: "nav.group.network",
  operations: "nav.group.operations",
  results: "nav.group.results",
  administration: "nav.group.administration",
};

export const navigationRegistry: NavigationRegistryItem[] = [
  {
    id: "home",
    view: "home",
    labelKey: "nav.home",
    icon: "home",
    group: "overview",
    module: "home",
    audiences: ["owner", "operator", "partner", "client"],
    requiresWorkspace: true,
  },
  {
    id: "organizations",
    view: "organizations",
    labelKey: "nav.organizations",
    icon: "network",
    group: "network",
    module: "organizations",
    audiences: ["owner"],
    requiredPermissionsAny: ["organizations.read"],
  },
  {
    id: "partners",
    view: "partners",
    labelKey: "nav.partners",
    icon: "partner",
    group: "network",
    module: "partners",
    audiences: ["owner"],
    requiredPermissionsAny: ["organizations.read"],
  },
  {
    id: "clients",
    view: "clients",
    labelKey: "nav.clients",
    icon: "clients",
    group: "network",
    module: "clients",
    audiences: ["owner", "partner"],
    requiredPermissionsAny: ["organizations.read", "organizations.read_descendants"],
  },
  {
    id: "workspaces",
    view: "workspaces",
    labelKey: "nav.workspaces",
    icon: "workspace",
    group: "network",
    module: "workspaces",
    audiences: ["owner"],
    requiredPermissionsAny: ["workspaces.read"],
  },
  {
    id: "services",
    view: "services",
    labelKey: "nav.services",
    icon: "services",
    group: "operations",
    module: "services",
    audiences: ["owner", "operator", "partner", "client"],
    requiredPermissionsAny: ["services.read"],
    requiresWorkspace: true,
  },
  {
    id: "client-services",
    view: "client-services",
    labelKey: "nav.clientServices",
    icon: "clients",
    group: "operations",
    module: "services",
    audiences: ["partner"],
    requiredPermissionsAny: ["organizations.read_descendants"],
  },
  {
    id: "workers",
    view: "workers",
    labelKey: "nav.workers",
    icon: "automation",
    group: "operations",
    module: "workers",
    audiences: ["owner", "operator"],
    requiredPermissionsAny: ["workers.read"],
  },
  {
    id: "runs",
    view: "runs",
    labelKey: "nav.runs",
    icon: "activity",
    group: "operations",
    module: "runs",
    audiences: ["owner", "operator"],
    requiredPermissionsAny: ["runs.read"],
  },
  {
    id: "results",
    view: "results",
    labelKey: "nav.results",
    icon: "chart",
    group: "results",
    module: "results",
    audiences: ["operator", "partner", "client"],
    requiredPermissionsAny: ["services.read"],
    requiresWorkspace: true,
    requiresContractedServices: true,
  },
  {
    id: "reports",
    view: "reports",
    labelKey: "nav.reports",
    icon: "report",
    group: "results",
    module: "reports",
    audiences: ["owner", "operator", "partner", "client"],
    requiredPermissionsAny: ["reports.read"],
    requiresWorkspace: true,
  },
  {
    id: "alerts",
    view: "alerts",
    labelKey: "nav.alerts",
    icon: "alert",
    group: "results",
    module: "alerts",
    audiences: ["owner", "operator", "partner", "client"],
    requiredPermissionsAny: ["alerts.read"],
    requiresWorkspace: true,
  },
  {
    id: "tasks",
    view: "tasks",
    labelKey: "nav.tasks",
    icon: "tasks",
    group: "results",
    module: "tasks",
    audiences: ["owner", "operator", "partner", "client"],
    requiredPermissionsAny: ["tasks.read"],
    requiresWorkspace: true,
  },
  {
    id: "team",
    view: "team",
    labelKey: "nav.team",
    icon: "team",
    group: "administration",
    module: "team",
    audiences: ["operator", "partner", "client"],
    requiredPermissionsAny: ["team.manage"],
  },
  {
    id: "users",
    view: "team",
    labelKey: "nav.users",
    icon: "team",
    group: "administration",
    module: "users",
    audiences: ["owner"],
    requiredPermissionsAny: ["users.manage"],
  },
  {
    id: "support",
    view: "support",
    labelKey: "nav.support",
    icon: "support",
    group: "administration",
    module: "support",
    audiences: ["operator", "partner", "client"],
    requiredPermissionsAny: ["support.read"],
  },
  {
    id: "settings",
    view: "settings",
    labelKey: "nav.settings",
    icon: "settings",
    group: "administration",
    module: "settings",
    audiences: ["owner", "operator", "partner", "client"],
  },
  {
    id: "diagnosis",
    view: "diagnosis",
    labelKey: "nav.diagnosis",
    icon: "automation",
    group: "operations",
    module: "diagnosis",
    audiences: ["owner", "operator", "partner"],
    requiresWorkspace: true,
  },
];
