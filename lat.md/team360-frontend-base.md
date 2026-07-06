# Team360 Frontend Base

Team360 usa una base frontend propia inspirada en Vertice360, modernizada y desacoplada de su configuración legacy.

## Decisión

Esta sección define el stack frontend estable que deben respetar nuevas pantallas, componentes y flujos conectados.

- Astro 6 y Svelte 5 con Runes.
- TypeScript estricto.
- Tailwind CSS 4 mediante `@tailwindcss/vite`.
- DaisyUI 5 con integración CSS-first.
- `pnpm` como package manager.
- AG-UI/SSE como frontera de integración progresiva con backend.

## Límites

Esta base reutiliza patrones técnicos y de experiencia, pero no copia configuración, branding ni código legacy de Vertice360.

- No reutilizar `tailwind.config.cjs`, `postcss.config.cjs` ni el tema `vertice360` como fuente de verdad.
- No hardcodear partners, tenants ni marcas de instalaciones particulares.
- Mantener un App Shell adaptable según organización, workspace y permisos.
- Consumir URLs frontend desde la fuente canónica definida en [[team360-frontend-url-source-of-truth]].
- Aplicar la encapsulación visual definida en [[team360-frontend-ui-policy]].

## Fuentes canónicas

Esta decisión resume fuentes extensas existentes y no reemplaza sus detalles de implementación o contexto histórico.

- `docs/adr/ADR-004-team360-frontend-base-vertice360-modern-stack.md`
- `docs/frontend/team360-frontend-technical-base-from-vertice360.md`
- [[console-multi-organization]]
