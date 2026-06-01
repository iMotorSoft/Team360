# ADR-004: Base frontend Team360 desde Vertice360 con stack moderno

Estado: `aceptado`

Fecha: `2026-05-31`

## Contexto

Team360 necesita su propia experiencia frontend. Vertice360 tiene el stack tecnico mas cercano (Astro + Svelte 5 + Tailwind) con integracion backend via REST/SSE, patrones de workflow, CRM demo, AI workflow studio y manejo de eventos AG-UI.

Sin embargo, Vertice360 usa npm, Tailwind 3, configuracion DaisyUI/PostCSS legacy y no tiene autenticacion, multi-tenant ni la separacion de dominios que Team360 requiere.

## Decision

1. Tomar Vertice360 como **referencia tecnica y UX inicial**, no como codigo directo.
2. Modernizar el stack hacia:
   - pnpm como package manager.
   - Astro latest (6.4.2).
   - Svelte 5 latest (5.56.0) con Runes.
   - Tailwind CSS 4 latest (4.3.0) via `@tailwindcss/vite`.
   - DaisyUI 5 como acelerador UI inicial obligatorio, con integracion CSS-first.
   - TypeScript strict.
3. AG-UI como capa central de integracion backend/frontend, basada en el patron SSE + envelope `CUSTOM` que Vertice360 ya implementa, pero formalizada en `src/lib/agui/`.
4. No hardcodear `Mama Mia 360` ni ningun partner en arquitectura, rutas, navegacion o codigo.
5. Mantener App Shell unico adaptable segun `ADR-003`.
6. No implementar pantallas, componentes, rutas ni migraciones en esta fase.
7. No reutilizar `tailwind.config.cjs`, `postcss.config.cjs` ni el tema DaisyUI `vertice360` como configuracion base de Team360.

Integracion CSS-first esperada:

```css
@import "tailwindcss";
@plugin "daisyui";
```

## Consecuencias

- Vertice360 sirve como catalogo de patrones, no como codigo copiado.
- La migracion Tailwind 3 -> 4 requiere migrar DaisyUI a v5 con integracion CSS-first. DaisyUI se mantiene como acelerador UI inicial obligatorio, siempre encapsulado detras de componentes propios y sin reutilizar el tema/configuracion legacy de Vertice360.
- AG-UI se construye como capa propia, no como dependencia externa.
- El bootstrap contract backend/frontend debe definirse antes de implementar la consola.
- La implementacion queda para fases posteriores.

## Fuera de alcance

- Implementar codigo, rutas o componentes.
- Migrar codigo de Vertice360 directamente.
- Modificar DB o migraciones.
- Definir branding final.
- Cambiar configuracion de build existente.

## Referencias

- DaisyUI 5: `https://daisyui.com/docs/v5/`
- DaisyUI install: `https://daisyui.com/docs/install/`
- DaisyUI config: `https://daisyui.com/docs/config/`
- Tailwind CSS con Vite: `https://tailwindcss.com/docs/installation/using-vite`
- Astro Tailwind 4: `https://docs.astro.build/en/guides/integrations-guide/tailwind/`

- Documento completo: `../frontend/team360-frontend-technical-base-from-vertice360.md`
- App Shell: `ADR-003-team360-console-app-shell-and-layout-system.md`
- Navegacion: `ADR-002-team360-console-navigation-by-role.md`
- Dominios: `ADR-001-team360-domain-separation-and-console.md`
- Arquitectura viva: `../../lat.md/console-multi-organization.md`
