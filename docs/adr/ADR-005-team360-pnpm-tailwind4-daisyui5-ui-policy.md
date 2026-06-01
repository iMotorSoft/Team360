# ADR-005 - pnpm, Tailwind CSS 4, DaisyUI 5 y wrappers UI Team360

Estado: aprobado.

Fecha: 2026-05-31.

## Contexto

Team360 necesita una base frontend reproducible y desacoplada de la configuracion legacy de Vertice360. DaisyUI 5 es compatible con Tailwind CSS 4 mediante integracion CSS-first.

## Decision

1. `pnpm` es el package manager oficial y obligatorio del frontend Team360.
2. El proyecto debe declarar `packageManager` y versionar `pnpm-lock.yaml`.
3. No se deben versionar `package-lock.json` ni `yarn.lock`.
4. Team360 adopta Tailwind CSS 4 + DaisyUI 5 como stack UI inicial obligatorio.
5. La integracion usa CSS-first:

```css
@import "tailwindcss";
@plugin "daisyui";
```

6. DaisyUI debe quedar encapsulado detras de wrappers Team360 en `src/components/ui/`.
7. Las pantallas de negocio no deben dispersar clases DaisyUI.
8. No se reutilizan `tailwind.config.cjs`, `postcss.config.cjs` ni el tema `vertice360` como configuracion base.
9. No se hardcodea `Mamá Mía 360`: es una instancia configurable de partner regional.

## Consecuencias

- Las instalaciones frontend son reproducibles con pnpm.
- DaisyUI acelera el MVP sin convertirse en la API visual publica de la consola.
- Cambios futuros de libreria o tema se concentran principalmente en `src/components/ui/`.
- Astro/Vite y Tailwind CSS 4 parten de configuracion moderna, no de archivos legacy copiados.

## Referencias

- Documento completo: `../frontend/team360-package-manager-and-ui-policy.md`
- Base frontend: `../frontend/team360-frontend-technical-base-from-vertice360.md`
- App Shell: `../ux/team360-console-app-shell-and-layout-system.md`
