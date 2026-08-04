import { fileURLToPath } from "node:url";
import { defineConfig } from "astro/config";
import baseConfig from "./astro.config.mjs";
import { team360EmbedDevAssets } from "./scripts/embed-dev-assets.mjs";

const astroDir = fileURLToPath(new URL(".", import.meta.url));

export default defineConfig({
  ...baseConfig,
  vite: {
    ...baseConfig.vite,
    server: {
      ...baseConfig.vite?.server,
      watch: {
        ...baseConfig.vite?.server?.watch,
        ignored: ["**/playwright-report/**", "**/test-results/**"],
      },
    },
    plugins: [
      ...(baseConfig.vite?.plugins ?? []),
      team360EmbedDevAssets({ astroDir }),
    ],
  },
});
