# Astro Scripts

- `design-smoke.mjs`: smoke visual y funcional reproducible para el snapshot de diseño. Requiere la demo local en `http://127.0.0.1:4321` y usa Chromium local vía CDP sin dependencias npm adicionales.

```bash
corepack pnpm dev --host 127.0.0.1 --port 4321
corepack pnpm design:smoke
```
