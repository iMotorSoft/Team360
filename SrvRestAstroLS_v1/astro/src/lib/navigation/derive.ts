import type { ConsoleBootstrap, MockProfileId } from "../mock";
import { ROUTES } from "../../components/global.js";
import {
  navigationRegistry,
  type ConsoleAudience,
  type ConsoleNavigationGroup,
  type ConsoleView,
  type NavigationRegistryItem,
} from "./registry";

export interface DerivedNavigationItem extends NavigationRegistryItem {
  href: string;
}

export interface DerivedNavigationGroup {
  id: ConsoleNavigationGroup;
  items: DerivedNavigationItem[];
}

const routeSuffixByView: Record<ConsoleView, string> = {
  home: "",
  organizations: "/organizations",
  partners: "/partners",
  clients: "/clients",
  workspaces: "/workspaces",
  services: "/services",
  "client-services": "/client-services",
  results: "/results",
  workers: "/workers",
  runs: "/runs",
  reports: "/reports",
  alerts: "/alerts",
  tasks: "/tasks",
  team: "/team",
  support: "/support",
  settings: "/settings",
};

export function deriveConsoleAudience(bootstrap: ConsoleBootstrap): ConsoleAudience {
  if (bootstrap.effectivePermissions.includes("organizations.read")) {
    return "owner";
  }

  if (bootstrap.membershipOrganization.type === "team360_owner") {
    return "operator";
  }

  if (bootstrap.effectivePermissions.includes("organizations.read_descendants")) {
    return "partner";
  }

  return "client";
}

export function buildConsoleRoute(workspaceId: string, view: ConsoleView, profile?: MockProfileId): string {
  const path = `${ROUTES.workspace(workspaceId)}${routeSuffixByView[view]}`;
  return profile && profile !== "team360_admin" ? `${path}?profile=${profile}` : path;
}

export function buildServiceDetailRoute(workspaceId: string, serviceId: string, profile?: MockProfileId): string {
  const path = `${ROUTES.workspaceServices(workspaceId)}/${serviceId}`;
  return profile && profile !== "team360_admin" ? `${path}?profile=${profile}` : path;
}

function hasRequiredPermission(item: NavigationRegistryItem, permissions: Set<string>): boolean {
  return !item.requiredPermissionsAny?.length || item.requiredPermissionsAny.some((permission) => permissions.has(permission));
}

export function deriveNavigation(bootstrap: ConsoleBootstrap): DerivedNavigationGroup[] {
  const audience = deriveConsoleAudience(bootstrap);
  const modules = new Set(bootstrap.enabledModules);
  const permissions = new Set(bootstrap.effectivePermissions);
  const groups = new Map<ConsoleNavigationGroup, DerivedNavigationItem[]>();

  for (const item of navigationRegistry) {
    const isVisible =
      item.audiences.includes(audience) &&
      modules.has(item.module) &&
      hasRequiredPermission(item, permissions) &&
      (!item.organizationTypes || item.organizationTypes.includes(bootstrap.activeOrganization.type)) &&
      (!item.requiresWorkspace || Boolean(bootstrap.activeWorkspace)) &&
      (!item.requiresContractedServices || bootstrap.contractedServices.length > 0);

    if (!isVisible) {
      continue;
    }

    const groupItems = groups.get(item.group) ?? [];
    groupItems.push({
      ...item,
      href: buildConsoleRoute(bootstrap.activeWorkspace.id, item.view, bootstrap.profile),
    });
    groups.set(item.group, groupItems);
  }

  return Array.from(groups, ([id, items]) => ({ id, items }));
}

export function getViewLabelKey(view: ConsoleView): string {
  return navigationRegistry.find((item) => item.view === view)?.labelKey ?? "nav.home";
}
