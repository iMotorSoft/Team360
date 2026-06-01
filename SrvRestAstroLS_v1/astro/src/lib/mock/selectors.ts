import type { ConsoleBootstrap } from "./bootstrap";
import { organizations } from "./organizations";
import { services, type Service } from "./services";
import { workspaces } from "./workspaces";

export function getAccessibleWorkspaceIds(bootstrap: ConsoleBootstrap): Set<string> {
  return new Set(bootstrap.accessibleWorkspaces.map(({ id }) => id));
}

export function getVisibleServices(bootstrap: ConsoleBootstrap): Service[] {
  const workspaceIds = getAccessibleWorkspaceIds(bootstrap);
  const canViewInternalServices = bootstrap.uiHints.technicalDepth !== "business";

  return services.filter(
    ({ visibleToClient, workspaceId }) => workspaceIds.has(workspaceId) && (canViewInternalServices || visibleToClient),
  );
}

export function getVisibleServiceById(bootstrap: ConsoleBootstrap, serviceId: string): Service | undefined {
  return getVisibleServices(bootstrap).find(({ id }) => id === serviceId);
}

export function getWorkspaceName(workspaceId: string): string {
  return workspaces.find(({ id }) => id === workspaceId)?.name ?? workspaceId;
}

export function getOrganizationNameForWorkspace(workspaceId: string): string {
  const workspace = workspaces.find(({ id }) => id === workspaceId);
  return organizations.find(({ id }) => id === workspace?.organizationId)?.name ?? "Organización no disponible";
}
