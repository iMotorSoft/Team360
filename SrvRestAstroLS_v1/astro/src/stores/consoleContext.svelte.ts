import { MOCK_ACTIVE_PROFILE } from "../components/global.js";
import { getDirection, normalizeLocale, type Locale } from "../lib/i18n";
import {
  getMockBootstrap,
  getMockProfiles,
  type ConsoleBootstrap,
  type MockProfileId,
} from "../lib/mock";

export function createConsoleContext() {
  const initialBootstrap = getMockBootstrap(MOCK_ACTIVE_PROFILE);

  let activeProfile = $state<MockProfileId>(MOCK_ACTIVE_PROFILE);
  let bootstrap = $state<ConsoleBootstrap>(initialBootstrap);
  let locale = $state<Locale>(initialBootstrap.currentUser.locale);

  const direction = $derived(getDirection(locale));
  const activeWorkspace = $derived(bootstrap.activeWorkspace);
  const activeOrganization = $derived(bootstrap.activeOrganization);
  const effectivePermissions = $derived(bootstrap.effectivePermissions);
  const contractedServices = $derived(bootstrap.contractedServices);
  const notificationSummary = $derived(bootstrap.notificationSummary);
  const mockProfiles = getMockProfiles();

  function setActiveProfile(profile: MockProfileId) {
    activeProfile = profile;
    bootstrap = getMockBootstrap(profile);
    locale = bootstrap.currentUser.locale;
  }

  function setActiveWorkspace(workspaceId: string) {
    bootstrap = getMockBootstrap(activeProfile, workspaceId);
  }

  function setLocale(nextLocale: string) {
    locale = normalizeLocale(nextLocale);
  }

  function initialize(profile: MockProfileId, workspaceId?: string) {
    activeProfile = profile;
    bootstrap = getMockBootstrap(profile);

    if (workspaceId && bootstrap.accessibleWorkspaces.some(({ id }) => id === workspaceId)) {
      bootstrap = getMockBootstrap(profile, workspaceId);
    }

    locale = bootstrap.currentUser.locale;
  }

  return {
    get activeProfile() {
      return activeProfile;
    },
    get bootstrap() {
      return bootstrap;
    },
    get locale() {
      return locale;
    },
    get direction() {
      return direction;
    },
    get activeWorkspace() {
      return activeWorkspace;
    },
    get activeOrganization() {
      return activeOrganization;
    },
    get effectivePermissions() {
      return effectivePermissions;
    },
    get contractedServices() {
      return contractedServices;
    },
    get notificationSummary() {
      return notificationSummary;
    },
    mockProfiles,
    setActiveProfile,
    setActiveWorkspace,
    setLocale,
    initialize,
  };
}

export const consoleContext = createConsoleContext();
