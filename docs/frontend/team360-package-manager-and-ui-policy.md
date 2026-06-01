# Team360 Frontend - Politica de package manager y componentes UI

Estado: aprobado como politica tecnica frontend inicial.

## Resumen ejecutivo

El frontend de Team360 usa `pnpm` como package manager oficial, Tailwind CSS 4 como base utility-first y DaisyUI 5 como dependencia obligatoria del stack UI inicial.

DaisyUI acelera la construccion de la interfaz, pero no define la API visual publica de la aplicacion. Las pantallas de negocio y los modulos de Team360 Console deben consumir componentes propios de Team360 ubicados en `src/components/ui/`. Esos wrappers pueden usar clases DaisyUI internamente.

Esta politica evita copiar configuracion legacy de Vertice360, dispersar clases de una libreria externa por toda la consola y hardcodear branding o casos particulares.

## Alcance

Esta politica aplica al frontend de:

- `team360.live`, sitio comercial publico;
- `console.team360.live`, Team360 Console privada multi-organizacion;
- futuros paquetes frontend compartidos si el repositorio evoluciona a workspace o monorepo.

Define convenciones previas a la implementacion. No crea componentes, rutas, configuracion de build ni dependencias.

## Decision 1: pnpm

`pnpm` es el package manager oficial y obligatorio para el frontend Team360.

### Reglas pnpm

- Declarar `packageManager` en `package.json` cuando se inicialice el frontend.
- Versionar `pnpm-lock.yaml`.
- No versionar `package-lock.json` ni `yarn.lock`.
- No usar `npm` ni `yarn` para instalar dependencias o ejecutar scripts del frontend Team360.
- Mantener la estructura preparada para un futuro `pnpm-workspace.yaml` si aparecen paquetes compartidos.
- Para pnpm 11, declarar ajustes por proyecto en `pnpm-workspace.yaml`.
- Autorizar scripts transitivos solo mediante `allowBuilds` revisado; no usar `dangerouslyAllowAllBuilds`.
- No arrastrar `package-lock.json` al tomar referencias o codigo de Vertice360.

### Comandos estandar

```bash
pnpm install
pnpm dev
pnpm build
pnpm check
pnpm lint
```

`pnpm lint` aplica cuando el proyecto defina su script de lint.

## Decision 2: Tailwind CSS 4 + DaisyUI 5

Team360 adopta Tailwind CSS 4 y DaisyUI 5 como combinacion oficial para la primera etapa frontend.

- Tailwind CSS 4 es la base utility-first.
- DaisyUI 5 es obligatorio como acelerador UI inicial.
- DaisyUI no debe quedar expuesto como dependencia visual dispersa en las pantallas.
- Astro/Vite debe integrar Tailwind CSS 4 mediante `@tailwindcss/vite`.

### Integracion CSS-first recomendada

El CSS global debe incluir:

```css
@import "tailwindcss";
@plugin "daisyui";
```

Los design tokens propios pueden declararse con `@theme` cuando deban generar utilities:

```css
@theme {
  --color-brand-primary: var(--team360-color-primary);
  --color-brand-secondary: var(--team360-color-secondary);
}
```

DaisyUI puede configurarse mediante CSS-first config. El tema inicial debe llamarse `team360` o construirse sobre tokens neutrales.

### Se permite

- Usar DaisyUI 5 dentro de wrappers Team360.
- Usar `@theme` para tokens propios.
- Definir un tema DaisyUI `team360`.
- Reutilizar de Vertice360 aprendizajes UX, patrones de interaccion y criterios de layout.
- Reemplazar internamente una primitive DaisyUI sin modificar las pantallas consumidoras.

### Se prohibe

- Reutilizar `tailwind.config.cjs` legacy de Vertice360 como fuente principal.
- Reutilizar `postcss.config.cjs` legacy salvo necesidad concreta y justificada.
- Reutilizar el tema hardcodeado `vertice360`.
- Dispersar clases DaisyUI directamente por pantallas de negocio.
- Tratar DaisyUI como motivo para permanecer en Tailwind CSS 3.
- Retirar DaisyUI argumentando una incompatibilidad inexistente con Tailwind CSS 4.

## Decision 3: wrappers UI propios

DaisyUI debe quedar encapsulado detras de componentes propios:

```text
src/components/ui/
├── Alert.svelte
├── Badge.svelte
├── Button.svelte
├── Card.svelte
├── DataTable.svelte
├── Drawer.svelte
├── EmptyState.svelte
├── FormField.svelte
├── Loading.svelte
├── Modal.svelte
├── Select.svelte
├── Tabs.svelte
├── Textarea.svelte
└── TextInput.svelte
```

La lista es el conjunto minimo sugerido, no una instruccion de implementarlo completo en una sola fase.

### Reglas de consumo

- Las pantallas de negocio consumen componentes Team360, no clases DaisyUI directamente.
- DaisyUI puede usarse internamente dentro de `src/components/ui/`.
- La logica de negocio no pertenece a componentes UI base.
- Los wrappers deben aceptar composicion y props suficientemente claras para no duplicar markup.
- Si DaisyUI cambia o se reemplaza, el impacto principal debe concentrarse en `src/components/ui/`.

### Variantes minimas

Los componentes que correspondan deben soportar:

- `primary`;
- `secondary`;
- `ghost`;
- `neutral`;
- `danger` o `error`;
- `success`;
- `warning`;
- `info`.

### Estados minimos

Los componentes que correspondan deben contemplar:

- `loading`;
- `disabled`;
- `readonly`;
- `selected`;
- `error`;
- `empty`.

Cada wrapper debe exponer solo variantes y estados que tengan sentido para su responsabilidad. No todos los estados aplican a todos los componentes.

## Relacion con Vertice360

Vertice360 es referencia tecnica y UX, no plantilla para copiar sin migracion.

Se pueden reutilizar criterios de layout, patrones y aprendizajes. No se deben copiar:

- `package-lock.json`;
- configuracion npm;
- `tailwind.config.cjs` legacy;
- `postcss.config.cjs` legacy;
- configuracion DaisyUI legacy dentro del config Tailwind;
- tema `vertice360`;
- clases DaisyUI dispersas sin wrappers;
- nombres, rutas o branding hardcodeados.

## Relacion con App Shell

El App Shell adaptable debe consumir los wrappers Team360 para sidebar, topbar, badges, alerts, drawers, loading states y estados vacios.

La navegacion sigue derivandose de organizacion, workspace, permisos efectivos, modulos, servicios contratados y subarbol autorizado. DaisyUI resuelve primitives visuales internas; no decide autorizacion, tenancy ni navegacion.

## Relacion con AG-UI

AG-UI y SSE pueden alimentar actividad, estados de ejecucion, notificaciones y respuestas progresivas. Los wrappers UI deben representar estados como `loading`, `error`, `empty` o `disabled`, pero no deben contener la logica de transporte AG-UI ni decisiones de negocio.

La capa de estado Svelte 5 con Runes traduce eventos y contexto a props de componentes UI.

## Reglas multi-tenant

- Ningun componente UI autoriza acceso por si mismo.
- Ocultar o deshabilitar acciones en frontend no reemplaza validacion backend.
- El tema, contenido y navegacion no deben hardcodear organizaciones concretas.
- `Mamá Mía 360` es una instancia configurable de partner regional, no una regla de UI.

## Riesgos

1. Copiar configuracion legacy de Vertice360 y bloquear la migracion limpia a Tailwind CSS 4.
2. Dispersar clases DaisyUI y elevar el costo de cambios visuales futuros.
3. Convertir wrappers en componentes con logica de negocio.
4. Versionar lockfiles incompatibles y generar instalaciones no reproducibles.
5. Confundir ocultamiento visual con autorizacion multi-tenant.
6. Intentar implementar todo el catalogo UI antes de definir el MVP.

## Proximos pasos

1. Inicializar el frontend con pnpm y declarar `packageManager`.
2. Versionar exclusivamente `pnpm-lock.yaml`.
3. Configurar Astro/Vite con `@tailwindcss/vite`.
4. Crear CSS global con Tailwind CSS 4, DaisyUI 5 y tokens Team360.
5. Definir el tema `team360`.
6. Priorizar wrappers necesarios para el primer App Shell y primer flujo funcional.
7. Definir pruebas visuales y de accesibilidad para primitives criticas.

## Referencias

- `team360-frontend-technical-base-from-vertice360.md`
- `../ux/team360-console-app-shell-and-layout-system.md`
- `../adr/ADR-004-team360-frontend-base-vertice360-modern-stack.md`
- `../adr/ADR-005-team360-pnpm-tailwind4-daisyui5-ui-policy.md`
- DaisyUI 5: `https://daisyui.com/docs/v5/`
- DaisyUI install: `https://daisyui.com/docs/install/`
- DaisyUI config: `https://daisyui.com/docs/config/`
- Tailwind CSS with Vite: `https://tailwindcss.com/docs/installation/using-vite`
- Tailwind CSS `@theme`: `https://tailwindcss.com/docs/theme`
