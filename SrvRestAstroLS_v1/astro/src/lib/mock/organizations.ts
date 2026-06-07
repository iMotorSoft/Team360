export type OrganizationType = "team360_owner" | "partner" | "direct_client" | "partner_client";
export type OrganizationStatus = "active" | "onboarding" | "paused";

export interface Organization {
  id: string;
  name: string;
  type: OrganizationType;
  region: string;
  parentOrganizationId: string | null;
  status: OrganizationStatus;
}

export const organizations: Organization[] = [
  {
    id: "org-team360",
    name: "Team360",
    type: "team360_owner",
    region: "Global",
    parentOrganizationId: null,
    status: "active",
  },
  {
    id: "org-carmel-retail",
    name: "Carmel Retail",
    type: "direct_client",
    region: "Israel",
    parentOrganizationId: "org-team360",
    status: "active",
  },
  {
    id: "org-team360-live",
    name: "Team360.live",
    type: "direct_client",
    region: "Global",
    parentOrganizationId: "org-team360",
    status: "active",
  },
  {
    // First regional partner fixture. The product architecture never branches on this name.
    id: "org-mama-mia-360",
    name: "Mamá Mía 360",
    type: "partner",
    region: "Israel",
    parentOrganizationId: "org-team360",
    status: "active",
  },
  {
    id: "org-netzaj-racing",
    name: "NETZAJ Racing",
    type: "partner_client",
    region: "Israel",
    parentOrganizationId: "org-mama-mia-360",
    status: "active",
  },
  {
    id: "org-galil-home",
    name: "Galil Home",
    type: "partner_client",
    region: "Israel",
    parentOrganizationId: "org-mama-mia-360",
    status: "onboarding",
  },
  {
    id: "org-nexo-iberia",
    name: "Nexo 360 Iberia",
    type: "partner",
    region: "Spain",
    parentOrganizationId: "org-team360",
    status: "onboarding",
  },
];
