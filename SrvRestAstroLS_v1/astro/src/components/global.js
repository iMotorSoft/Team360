export const APP_NAME = "Team360";
export const APP_PUBLIC_NAME = "Team360 Console";

export const PUBLIC_SITE_URL = "https://team360.live";
export const CONSOLE_SITE_URL = "https://console.team360.live";

// -- Backend REST endpoint (dev/pro conmutable) --
// Todos los API clients en src/lib/ deben importar URL_REST desde aquí,
// no hardcodear URLs. Es la única fuente de verdad para el endpoint REST.
// Desarrollo local / Browser MCP sobre /t360: IS_REST_PRO debe quedar false
// para usar el backend local en 7050. Producción con URL_REST_PRO="" requiere
// reverse proxy /api configurado en el host público.
const URL_REST_DEV = "http://localhost:7050";
const URL_REST_PRO = "";
const IS_REST_PRO = true; // toggle: cambiar a true para producción

export const URL_REST = IS_REST_PRO ? URL_REST_PRO : URL_REST_DEV;

export const getRestBaseUrl = () => String(URL_REST || "").replace(/\/+$/, "");

export const API_BASE_URL = `${getRestBaseUrl()}/api`;
export const AGUI_BASE_URL = `${getRestBaseUrl()}/api/agui`;
export const URL_SSE = `${getRestBaseUrl()}/api/agui/stream`;

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
