import {
  mountTeam360Diagnosticador,
  type Team360DiagnosticadorMountConfig,
  type Team360DiagnosticadorMountHandle,
} from "./mount";

export const TEAM360_DIAGNOSTICADOR_BROWSER_GLOBAL_VERSION = "experimental-9c";

export type Team360DiagnosticadorBrowserGlobal = {
  mount: (
    container: string | HTMLElement,
    config: Team360DiagnosticadorMountConfig,
  ) => Team360DiagnosticadorMountHandle;
  version: typeof TEAM360_DIAGNOSTICADOR_BROWSER_GLOBAL_VERSION;
};

declare global {
  interface Window {
    Team360Diagnosticador?: Team360DiagnosticadorBrowserGlobal;
  }
}

const browserGlobalApi: Team360DiagnosticadorBrowserGlobal = Object.freeze({
  mount: mountTeam360Diagnosticador,
  version: TEAM360_DIAGNOSTICADOR_BROWSER_GLOBAL_VERSION,
});

export function registerTeam360DiagnosticadorBrowserGlobal(
  targetWindow: Window = window,
): Team360DiagnosticadorBrowserGlobal {
  if (targetWindow.Team360Diagnosticador) {
    return targetWindow.Team360Diagnosticador;
  }

  targetWindow.Team360Diagnosticador = browserGlobalApi;
  return targetWindow.Team360Diagnosticador;
}

if (typeof window !== "undefined") {
  registerTeam360DiagnosticadorBrowserGlobal(window);
}

export type {
  Team360DiagnosticadorMountConfig,
  Team360DiagnosticadorMountHandle,
};

export { browserGlobalApi as Team360DiagnosticadorBrowserGlobalApi };
