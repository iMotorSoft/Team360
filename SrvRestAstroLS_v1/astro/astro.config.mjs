import { defineConfig } from "astro/config";
import svelte from "@astrojs/svelte";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  site: "https://team360.live",
  integrations: [svelte()],
  vite: {
    plugins: [tailwindcss()],
  },
});

