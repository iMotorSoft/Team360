export const APP_NAME = "Team360";
export const APP_PUBLIC_NAME = "Team360 Console";

export const PUBLIC_SITE_URL = "https://team360.live";
export const CONSOLE_SITE_URL = "https://console.team360.live";

export const API_BASE_URL = "/api";
export const AGUI_BASE_URL = "/api/agui";

export const DEFAULT_LOCALE = "es";
export const SUPPORTED_LOCALES = ["es", "en", "he"];
export const LOCALE_DIRECTION = {
  es: "ltr",
  en: "ltr",
  he: "rtl",
};
export const DEFAULT_DIRECTION = LOCALE_DIRECTION[DEFAULT_LOCALE];

export const IS_MOCK_MODE = true;
export const MOCK_ACTIVE_PROFILE = "team360_admin";

export const BRAND = {
  name: APP_NAME,
  consoleName: APP_PUBLIC_NAME,
  tagline: "Operaciones inteligentes",
  supportEmail: "contacto@team360.live",
};

export const ROUTES = {
  home: "/",
  login: "/login",
  selectWorkspace: "/select-workspace",
  workspace: (workspaceId) => `/w/${workspaceId}`,
  workspaceServices: (workspaceId) => `/w/${workspaceId}/services`,
  workspaceReports: (workspaceId) => `/w/${workspaceId}/reports`,
  workspaceDiagnosis: (workspaceId) => `/w/${workspaceId}/diagnosis`,
};
