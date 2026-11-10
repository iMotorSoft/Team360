import { fileURLToPath } from "node:url";
import { defineConfig } from "astro/config";
import baseConfig from "./astro.config.mjs";
import { team360EmbedDevAssets } from "./scripts/embed-dev-assets.mjs";

const astroDir = fileURLToPath(new URL(".", import.meta.url));
const telchiPort = process.env.TEAM360_TELCHIAI_PORT ?? '7060';
if (!/^\d+$/.test(telchiPort) || Number(telchiPort) < 1 || Number(telchiPort) > 65535) {
  throw new Error('Invalid TEAM360_TELCHIAI_PORT');
}
const telchiTarget = `http://127.0.0.1:${telchiPort}`;
const telchiProxy = {
  target: telchiTarget,
  timeout: 0, // The research engine enforces its own analytical wall budget.
  proxyTimeout: 0, // Do not truncate a healthy stream with transport heartbeats.
  configure(proxy) {
    proxy.on('proxyRes', (upstream, _request, response) => {
      response.on('close', () => {
        if (!upstream.complete) upstream.destroy();
      });
    });
  },
};

export default defineConfig({
  ...baseConfig,
  vite: {
    ...baseConfig.vite,
    server: {
      ...baseConfig.vite?.server,
      // Specific rules must precede the inherited /api -> central backend rule.
      proxy: {
        '/api/telchiai': telchiProxy,
        '/api/telchi/luna': telchiProxy,
        ...baseConfig.vite?.server?.proxy,
      },
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
