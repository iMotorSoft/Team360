import type { Locale, TextDirection } from "../i18n";

export type WorkspaceType = "platform_operations" | "partner_operations" | "client_operations";
export type WorkspaceStatus = "active" | "onboarding" | "paused";

export interface Workspace {
  id: string;
  name: string;
  organizationId: string;
  type: WorkspaceType;
  status: WorkspaceStatus;
  locale: Locale;
  direction: TextDirection;
}

export const workspaces: Workspace[] = [
  {
    id: "ws-team360-control",
    name: "Control global",
    organizationId: "org-team360",
    type: "platform_operations",
    status: "active",
    locale: "es",
    direction: "ltr",
  },
  {
    id: "ws-carmel-retail",
    name: "Operación comercial",
    organizationId: "org-carmel-retail",
    type: "client_operations",
    status: "active",
    locale: "he",
    direction: "rtl",
  },
  {
    id: "ws-team360-live-public-site",
    name: "Team360.live Public Site",
    organizationId: "org-team360-live",
    type: "client_operations",
    status: "active",
    locale: "es",
    direction: "ltr",
  },
  {
    id: "ws-mama-mia-israel",
    name: "Red Israel",
    organizationId: "org-mama-mia-360",
    type: "partner_operations",
    status: "active",
    locale: "es",
    direction: "ltr",
  },
  {
    id: "ws-netzaj-marketplace",
    name: "Marketplace principal",
    organizationId: "org-netzaj-racing",
    type: "client_operations",
    status: "active",
    locale: "es",
    direction: "ltr",
  },
  {
    id: "ws-galil-commerce",
    name: "Comercio digital",
    organizationId: "org-galil-home",
    type: "client_operations",
    status: "onboarding",
    locale: "he",
    direction: "rtl",
  },
  {
    id: "ws-nexo-onboarding",
    name: "Activación regional",
    organizationId: "org-nexo-iberia",
    type: "partner_operations",
    status: "onboarding",
    locale: "es",
    direction: "ltr",
  },
];
