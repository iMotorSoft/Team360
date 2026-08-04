import { mount, unmount, type Component } from "svelte";
import VeraEmbedWrapper from "../diagnosticador/VeraEmbedWrapper.svelte";

// Props accepted by VeraEmbedWrapper (mirrors its $props declaration).
type VeraEmbedWrapperProps = {
  clientId: string;
  apiBaseUrl: string;
  assistantName?: string;
  compact?: boolean;
  initialMessage?: string;
  sessionStorageKey?: string;
};

// svelte2tsx + TypeScript 6 generate an unusable type for the .svelte module
// (resolves to `Error`), so `ComponentProps<typeof VeraEmbedWrapper>` and the
// plain `mount(VeraEmbedWrapper, ...)` call fail type-checking. Cast the
// component to its real Svelte 5 `Component` shape — runtime is unchanged.
const VeraEmbedWrapperComponent = VeraEmbedWrapper as unknown as Component<VeraEmbedWrapperProps>;

export type Team360DiagnosticadorMountConfig = {
  clientId: string;
  apiBaseUrl: string;
  assistantName?: string;
  compact?: boolean;
  initialMessage?: string;
  sessionStorageKey?: string;
};

export type Team360DiagnosticadorMountHandle = {
  destroy: () => void;
};

const FORBIDDEN_CONFIG_KEYS = [
  "hmac_secret",
  "organization_code",
  "workspace_code",
  "assistant_instance_code",
  "package_code",
  "knowledge_scope_code",
  "allowed_origins",
  "service_code",
  "template_code",
] as const;

const ERROR_PREFIX = "Team360 Diagnosticador mount";

function fail(message: string): never {
  throw new Error(`${ERROR_PREFIX}: ${message}`);
}

function resolveMountTarget(container: string | HTMLElement): HTMLElement {
  if (typeof container === "string") {
    const selector = container.trim();
    if (!selector) {
      fail("container selector is required.");
    }
    const element = document.querySelector(selector);
    if (!(element instanceof HTMLElement)) {
      fail(`container selector did not resolve to an HTMLElement: ${selector}`);
    }
    return element;
  }

  if (!(container instanceof HTMLElement)) {
    fail("container must be an HTMLElement or a selector string.");
  }

  return container;
}

function assertNonEmptyString(
  value: unknown,
  fieldName: "clientId" | "apiBaseUrl",
): string {
  if (typeof value !== "string" || !value.trim()) {
    fail(`${fieldName} is required.`);
  }
  return value.trim();
}

function assertOptionalString(value: unknown, fieldName: string): string | undefined {
  if (value === undefined) {
    return undefined;
  }
  if (typeof value !== "string") {
    fail(`${fieldName} must be a string.`);
  }
  return value;
}

function assertOptionalBoolean(value: unknown, fieldName: string): boolean | undefined {
  if (value === undefined) {
    return undefined;
  }
  if (typeof value !== "boolean") {
    fail(`${fieldName} must be a boolean.`);
  }
  return value;
}

function assertForbiddenKeys(config: Record<string, unknown>): void {
  const forbidden = FORBIDDEN_CONFIG_KEYS.filter((key) => key in config);
  if (forbidden.length > 0) {
    fail(`forbidden config key(s): ${forbidden.join(", ")}`);
  }
}

function buildWrapperProps(
  rawConfig: Team360DiagnosticadorMountConfig,
): VeraEmbedWrapperProps {
  const config = rawConfig as Record<string, unknown>;
  assertForbiddenKeys(config);

  return {
    clientId: assertNonEmptyString(config.clientId, "clientId"),
    apiBaseUrl: assertNonEmptyString(config.apiBaseUrl, "apiBaseUrl"),
    assistantName: assertOptionalString(config.assistantName, "assistantName"),
    compact: assertOptionalBoolean(config.compact, "compact"),
    initialMessage: assertOptionalString(config.initialMessage, "initialMessage"),
    sessionStorageKey: assertOptionalString(config.sessionStorageKey, "sessionStorageKey"),
  };
}

export function mountTeam360Diagnosticador(
  container: string | HTMLElement,
  config: Team360DiagnosticadorMountConfig,
): Team360DiagnosticadorMountHandle {
  const target = resolveMountTarget(container);
  const props = buildWrapperProps(config);
  const instance = mount(VeraEmbedWrapperComponent, {
    target,
    props,
  });

  let destroyed = false;

  return {
    destroy() {
      if (destroyed) {
        return;
      }
      destroyed = true;
      void unmount(instance);
    },
  };
}

export const Team360Diagnosticador = {
  mount: mountTeam360Diagnosticador,
} as const;
