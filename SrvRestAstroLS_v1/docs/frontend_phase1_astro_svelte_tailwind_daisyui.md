# Frontend Team360 - Fase 1 base Astro, Svelte, Tailwind y DaisyUI

Estado: implementado como scaffold tecnico inicial.

Fecha: 2026-05-31.

## Objetivo

Preparar la base real del frontend Team360 sin implementar pantallas finales, App Shell, autenticacion, navegacion contextual ni integracion backend funcional.

## Ubicacion

El frontend vive en:

```text
SrvRestAstroLS_v1/astro/
```

Se reutilizo la carpeta minima ya existente en Team360. Vertice360 se uso solo como referencia de experiencia previa; no se copiaron branding, rutas, tema, componentes especificos ni configuracion legacy.

## Stack inicial

| Paquete | Version inicial |
| --- | --- |
| pnpm | 11.5.0 |
| astro | 6.4.2 |
| @astrojs/svelte | 8.1.2 |
| svelte | 5.56.0 |
| tailwindcss | 4.3.0 |
| @tailwindcss/vite | 4.3.0 |
| daisyui | 5.5.20 |
| typescript | 6.0.3 |

Las versiones se verificaron con `pnpm view` antes de instalar.

## Politica pnpm aplicada

- `package.json` declara `packageManager: pnpm@11.5.0`.
- Se versiona `pnpm-lock.yaml`.
- No se creo `package-lock.json` ni `yarn.lock`.
- `pnpm-workspace.yaml` deja preparada la evolucion a workspace y declara `allowBuilds` de forma restrictiva.
- Solo se permiten scripts transitivos revisados de Astro:
  - `esbuild: true`;
  - `sharp: true`.
- No se habilito `dangerouslyAllowAllBuilds`.

pnpm 11 reemplazo `onlyBuiltDependencies` por `allowBuilds`. Referencia oficial: `https://pnpm.io/settings#allowbuilds`.

## Base tecnica creada

- `astro.config.mjs`: Astro con Svelte y `@tailwindcss/vite`.
- `tsconfig.json`: extiende `astro/tsconfigs/strict`.
- `src/styles/global.css`: CSS-first con Tailwind CSS 4, DaisyUI 5 y tema neutral `team360`.
- `src/layouts/BaseLayout.astro`: layout tecnico minimo para smoke visual.
- `src/pages/index.astro`: pagina minima de verificacion, no home final.
- `src/components/ui/`: wrappers propios Team360 iniciales.
- `src/lib/agui/README.md`: reserva estructural para AG-UI/SSE futuro, sin implementacion funcional.

## Wrappers UI iniciales

La Fase 1 materializa solo primitives suficientes para validar la politica de encapsulamiento DaisyUI:

- `Alert.svelte`;
- `Badge.svelte`;
- `Button.svelte`;
- `Card.svelte`;
- `Loading.svelte`.

Las pantallas futuras deben consumir wrappers Team360, no clases DaisyUI dispersas.

## Limites de esta fase

No se implementaron:

- layouts finales de sitio comercial o consola;
- App Shell;
- login o autorizacion;
- navegacion contextual;
- bootstrap multi-tenant;
- AG-UI/SSE funcional;
- rutas finales de producto;
- cambios backend, DB o migraciones.

## Validacion

Ejecutar desde `SrvRestAstroLS_v1/astro/`:

```bash
corepack pnpm install
corepack pnpm check
corepack pnpm build
```
