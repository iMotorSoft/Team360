import { fileURLToPath } from "node:url";
import { defineConfig } from "astro/config";
import svelte from "@astrojs/svelte";
import tailwindcss from "@tailwindcss/vite";

function team360DiagnosticadorBrowserAsset() {
  const browserGlobalEntry = fileURLToPath(
    new URL("./src/lib/t360/embed/browser-global.ts", import.meta.url),
  );

  return {
    name: "team360-diagnosticador-browser-asset",
    apply: "build",
    buildStart() {
      this.emitFile({
        type: "chunk",
        id: browserGlobalEntry,
        fileName: "embed/team360-diagnosticador.js",
        preserveSignature: "strict",
      });
    },
  };
}

export default defineConfig({
  site: "https://team360.live",
  integrations: [svelte()],
  server: {
    headers: {},
  },
  vite: {
    plugins: [tailwindcss(), team360DiagnosticadorBrowserAsset()],
    server: {
      proxy: {
        "/api": "http://127.0.0.1:7050",
      },
    },
  },
});
