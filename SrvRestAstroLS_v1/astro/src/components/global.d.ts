export const APP_NAME: "Team360";
export const APP_PUBLIC_NAME: "Team360 Console";

export const PUBLIC_SITE_URL: "https://team360.live";
export const CONSOLE_SITE_URL: "https://console.team360.live";

export const URL_REST: "http://localhost:7050" | "";
export const getRestBaseUrl: () => string;

export const API_BASE_URL: string;
export const AGUI_BASE_URL: string;
export const URL_SSE: string;

export const DEFAULT_LOCALE: "es";
export const SUPPORTED_LOCALES: readonly ["es", "en", "he"];
export const LOCALE_DIRECTION: Readonly<{
  es: "ltr";
  en: "ltr";
  he: "rtl";
}>;
export const DEFAULT_DIRECTION: "ltr";

export const IS_MOCK_MODE: true;
export const MOCK_ACTIVE_PROFILE: "team360_admin";

export const BRAND: Readonly<{
  name: "Team360";
  consoleName: "Team360 Console";
  tagline: "Operaciones inteligentes";
  supportEmail: "contacto@team360.live";
}>;

export const ROUTES: Readonly<{
  home: "/";
  login: "/login";
  selectWorkspace: "/select-workspace";
  workspace: (workspaceId: string) => string;
  workspaceServices: (workspaceId: string) => string;
  workspaceReports: (workspaceId: string) => string;
  workspaceDiagnosis: (workspaceId: string) => string;
}>;
