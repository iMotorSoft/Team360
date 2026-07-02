/// <reference path="../.astro/types.d.ts" />
/// <reference types="astro/client" />

import type { Team360DiagnosticadorBrowserGlobal } from "./lib/t360/embed/browser-global";

type Team360DiagnosticadorLoaderGlobal = {
  version: string;
  load: (options?: { assetUrl?: string; manifestUrl?: string }) => Promise<Team360DiagnosticadorBrowserGlobal>;
  defaults: {
    assetUrl: string;
    manifestUrl: string;
  };
};

declare global {
  interface Window {
    Team360DiagnosticadorLoader?: Team360DiagnosticadorLoaderGlobal;
  }
}

export {};
