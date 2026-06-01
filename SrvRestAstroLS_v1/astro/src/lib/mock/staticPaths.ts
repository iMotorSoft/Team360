import { workspaces } from "./workspaces";
import { services } from "./services";

export function getWorkspaceStaticPaths() {
  return workspaces.map(({ id }) => ({
    params: {
      workspaceId: id,
    },
  }));
}

export function getServiceStaticPaths() {
  return services.map(({ id: serviceId, workspaceId }) => ({
    params: {
      workspaceId,
      serviceId,
    },
  }));
}
