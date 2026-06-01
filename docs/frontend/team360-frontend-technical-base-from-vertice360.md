# Team360 Frontend - Base tecnica desde Vertice360

Estado: `propuesta-tecnica`

Ultima actualizacion: `2026-05-31`

Objetivo: documentar el analisis de Vertice360 como base UX/frontend para Team360, detectar brechas tecnicas, proponer stack objetivo, estructura frontend y estrategia de migracion.

Audiencia: frontend, backend, arquitectura, direccion tecnica.

---

## Contexto

Team360 necesita su propia experiencia de frontend. Vertice360 es el proyecto hermano que mas experiencia acumula en el stack Astro + Svelte + Tailwind + DaisyUI, con integracion backend via REST y SSE, patrones de workflow, CRM demo y AI workflow studio.

Este documento analiza que tomar, que modernizar, que abstraer y que evitar de Vertice360 para construir la base frontend de Team360 Console y team360.live.

## Proyecto Vertice360 analizado

- Ruta: `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Vertice360/SrvRestAstroLS_v1/astro`
- Package name: `vertice360-astro`
- Version: `0.1.0`
- Package manager: `npm` (package-lock.json, sin pnpm-lock)

## Stack objetivo Team360

| Componente | Version objetivo | Origen |
|---|---|---|
| pnpm | 11.5.0 | Package manager del proyecto Team360 |
| Astro | 6.4.2 | Latest estable |
| @astrojs/svelte | 8.1.2 | Latest compatible con Astro 6 |
| Svelte | 5.56.0 | Latest Svelte 5 con Runes |
| tailwindcss | 4.3.0 | Latest Tailwind 4 |
| @tailwindcss/vite | 4.3.0 | Plugin Vite para Tailwind 4 |
| daisyui | 5.5.20 | Dependencia UI inicial obligatoria, encapsulada sobre Tailwind 4 |
| vite | 8.0.14 | Incluido con Astro |
| typescript | 5.6.3 | Latest TS 5 |
| postcss | 8.5.15 | Para compat legacy si se requiere |
| autoprefixer | 10.5.0 | Para compat legacy si se requiere |

## Estado tecnico encontrado en Vertice360

### Versiones actuales (package.json)

| Dependencia | Version en Vertice360 | Latest disponible | Brecha |
|---|---|---|---|
| astro | ^5.17.1 | 6.4.2 | Menor (5 a 6) |
| @astrojs/svelte | ^7.2.5 | 8.1.2 | Menor |
| svelte | ^5.0.0 | 5.56.0 | Major actualizada (5.x) |
| tailwindcss | ^3.4.3 | 4.3.0 | **Major (3 a 4)** |
| typescript | ^5.4.0 | 5.6.3 | Menor |
| postcss | ^8.4.38 | 8.5.15 | Menor |
| autoprefixer | ^10.4.19 | 10.5.0 | Menor |
| daisyui (dev) | ^5.5.5 | 5.5.20 | Menor |

### Paquetes no presentes en Vertice360

| Paquete | Necesario para | Prioridad |
|---|---|---|
| @tailwindcss/vite | Tailwind 4 en Astro/Vite | Alta |
| svelte-check | Validacion Svelte en CI | Media |
| @astrojs/check | Validacion Astro en CI | Media |

### Configuracion detectada

- `astro.config.mjs`: solo integracion Svelte, sin Tailwind plugin, sin Vite config adicional.
- `tailwind.config.cjs`: config tradicional CJS con DaisyUI plugin, tema personalizado `vertice360`, colores vía CSS variables.
- `postcss.config.cjs`: PostCSS con tailwindcss + autoprefixer (legacy, obsoleto para Tailwind 4).
- `tsconfig.json`: extends `astro/tsconfigs/strict`.
- Sin `pnpm-lock.yaml`, sin `packageManager` definido en package.json.

### TypeScript

- Si, TypeScript configurado via `astro/tsconfigs/strict`.
- Componentes Svelte usan `<script lang="ts">`.
- Archivos `.svelte.js` con Runes (`$state`, `$derived`).

### Svelte 5 / Runes

- Vertice360 ya usa Svelte 5 con Runes (`$state`, `$derived`).
- Archivos `state.svelte.js` con funciones fabrica `createXxxState()` y export singleton.
- Patron de getters para mantener reactividad: `get conversations() { return conversations; }`.
- Componentes usan `$state` para UI state local y `$derived` para computaciones.
- Compatibilidad Svelte 5: buena.

### DaisyUI

- DaisyUI presente como devDependency.
- Tema personalizado `vertice360` en tailwind.config.
- Componentes DaisyUI usados en demos: `card`, `btn`, `badge`, `loading`, `form-control`, `textarea`, `divider`.
- DaisyUI 5 es compatible con Tailwind CSS 4.
- La integracion moderna se declara desde CSS con `@plugin "daisyui"`, no como plugin dentro del `tailwind.config.cjs` legacy.

### Estructura de rutas

```
src/pages/
  index.astro            -> landing Vertice360
  demo/
    index.astro          -> dashboard demo Codex
    modal.astro          -> dashboard con chat modal
    sse-test/index.astro -> prueba SSE
    vertice360-ai-workflow-studio/index.astro
    vertice360-orquestador/index.astro
    vertice360-orquestador/admin.astro
    vertice360-orquestador/infografia.astro
    vertice360-orquestador/infografia-poster.astro
    vertice360-orquestador/orquestador.astro
    vertice360-orquestador/ux.astro
```

### Layouts

Solo existe `BaseLayout.astro`. Unico layout que recibe `brand` como prop, renderiza header con logo y nombre, y main con slot. Usa `data-theme="vertice360"` para DaisyUI.

### Componentes Svelte destacados

| Componente | Funcion |
|---|---|
| HelloPozo.svelte | Health check al backend REST |
| AguiPozoFlowV01.svelte | Laboratorio AG-UI con POST a endpoint |
| SseTestCard.svelte | Smoke test SSE |
| CodexDemoDashboard.svelte | Dashboard CRM demo |
| CodexDemoChat.svelte | Chat conversacional |
| OrquestadorAppLive.svelte | App completa orquestador |
| Vertice360AiWorkflowStudioApp.svelte | AI workflow studio full |

### Patron SSE (Server-Sent Events)

Vertice360 implementa SSE de forma consistente:

- **Endpoint unico**: `GET /api/agui/stream` (URL_SSE global)
- **Payload envelope**: `{ type: "CUSTOM", name: string, timestamp, value: {}, correlationId? }`
- **Event types**: `conversation.*`, `deal.*`, `task.*`, `ticket.*`, `messaging.*`, `workflow.*`, `ai_workflow.*`
- **Reconnection**: backoff exponencial 500ms-5s
- **Idempotent connection**: singleton EventSource
- **Teardown**: `beforeunload` cleanup
- **Status tracking**: `crm.sse`, `workflow.sse`, `studio.sse` con `{ connected, lastChangeMs }`

Hay tres implementaciones de SSE:
1. `src/lib/shared/sse.js` - gestor compartido con backoff, parseEvent, factory `createSseManager`
2. `src/lib/crm/sse.js` - especifico CRM con eventos de conversation/deal/task
3. `src/lib/vertice360_workflow/sse.js` - especifico workflow con eventos de ticket/messaging/workflow
4. `src/lib/vertice360_ai_workflow_studio/sse.js` - especifico AI workflow studio

### API client pattern

- `src/lib/shared/http.js`: wrapper fetch con AbortController, timeout 12s, `request()` y `requestJson()`.
- Cada modulo define su propia capa API (`src/lib/crm/api.js`, `src/lib/vertice360_workflow/api.js`, `src/lib/vertice360_ai_workflow_studio/api.js`).
- URL base desde `src/components/global.js` con `URL_REST` (dev/pro conmutable).
- Sin autenticacion token/session en los demos (solo API key de Cloudflare).

### Dependencias de UI adicionales

- Google Fonts: `Outfit`, `Space Grotesk`, `Poppins` (cargadas desde CSS).
- Sin icon library (usos inline de SVG).

### Deuda tecnica visible

1. **Tailwind 3 con PostCSS legacy**: la configuracion CJS actual no debe reutilizarse como fuente principal en Tailwind 4.
2. **DaisyUI legacy**: el tema `vertice360` y la configuracion dentro de `tailwind.config.cjs` deben migrarse al formato CSS-first de DaisyUI 5.
3. **Unico layout**: `BaseLayout` es generico, no hay separacion public/auth/console.
4. **global.js** contiene URL de Svelte heritage (SITE_TITLE de Astrofy template), URLs de fuentes y Cloudflare sitekeys mezcladas.
5. **Sin autenticacion**: los demos son publicos, sin login, sesion ni proteccion de rutas.
6. **SSE fragmentado**: 4 implementaciones similares en lugar de 1 compartida.
7. **API client sin tipado**: `api.js` usa `fetch` crudo, sin tipos de entrada/salida.
8. **Sin testing**: no hay tests de frontend visibles.
9. **npm en lugar de pnpm**: no alineado con Team360.
10. **CSS con !important**: uso de `!important` en `.btn-ghost` y selectores sobrescritos.
11. **Sin barrel exports**: imports con rutas relativas largas.
12. **Branding hardcodeado**: `vertice360` en tema DaisyUI, strings en `config/strings.ts`.

## Que reutilizar de Vertice360

### Arquitectura y patrones

- Estructura Astro base (srcDir, pages, layouts, components, lib).
- Integracion Svelte 5 con Runes ya probada.
- Patron de estados modulares `createXxxState()` con export singleton.
- SSE con backoff exponencial y reconexion.
- Patron API client con URL base configurable.
- Separacion entre modulos de negocio (crm, workflow, ai_workflow_studio).

### Componentes conceptuales

- Estructura de dashboard con grid layout.
- Chat conversacional embebido.
- Pantalla de health check.
- Componente de prueba SSE.
- Timeline de eventos en vivo.

### Estilos y configuracion

- CSS variables para branding y colores base.
- Patron de capas `@layer components` en CSS.
- Uso de `@screen md` en media queries.
- Font imports organizados en CSS.
- Esquema de paleta con --brand-primary, --brand-secondary, --brand-accent.

### Servicios frontend

- `shared/http.js` como base robusta para API client.
- `shared/sse.js` `createSseManager` como base unificada SSE.
- `shared/format.js` para utilidades.

### Scripts

- `scripts/check_no_hardcoded_urls.mjs`: util para validar URLS hardcodeadas.

## Que no reutilizar directamente

- **Branding Vertice360**: colores, fuentes, logos, textos, tema DaisyUI.
- **Nombre en URLS**: `/api/demo/vertice360-*`, `/api/demo/crm/*`, `vertice360-*` en rutas.
- **Tema DaisyUI `vertice360`**: no reutilizar branding ni tokens hardcodeados.
- **Configuracion DaisyUI legacy**: no reutilizar DaisyUI como plugin dentro de `tailwind.config.cjs`.
- **Clases DaisyUI dispersas**: no acoplar pantallas Team360 directamente a clases DaisyUI sin wrappers propios.
- **tailwind.config.cjs y postcss.config.cjs legacy**: no reutilizarlos como fuente principal de configuracion Team360.
- **Componentes demasiado especificos**: `AguiPozoFlowV01.svelte`, `HelloPozo.svelte` (Pozo Flow es de Vertice360).
- **global.js** con SITE_TITLE y URLs heredadas de Astrofy.
- **Modulos `vertice360_*`** en `src/lib/`: nombres y logica especifica de Vertice360.
- **Demos de CRM, workflow, AI studio**: son funcionales pero de Vertice360.
- **Autenticacion ausente**: no hay sesion, token, ni proteccion de rutas.
- **SSE fragmentado**: consolidar en una sola implementacion.

## Que abstraer

- **Branding**: tema, colores, tipografia, logo, favicon como configuracion, no hardcodeado.
- **Navegacion**: registro declarativo de items, filtrado por permisos y contexto.
- **Layouts**: base, auth, console, minimal, marketing.
- **Modulos**: `navigation`, `permissions`, `workspace`, `organization`, `services`.
- **Estado global**: `currentUser`, `activeOrganization`, `activeWorkspace`, `effectivePermissions`, `enabledModules`, `contractedServices`, `navigationItems`, `notifications`, `serviceContext`.
- **API client**: cliente generico con tipos, auth, error handling, timeout.
- **SSE**: gestor unificado con tipos de eventos, reconexion, estado y teardown.
- **AG-UI**: capa de transporte, normalizacion de eventos, sesion, error handling.
- **Componentes base**: crear wrappers Team360 en `components/ui/`: Button, Input, Card, Badge, Modal, Table, Tabs, Alert, Drawer, Loading, Empty y ErrorBoundary. Usan clases DaisyUI internamente; el resto de la app consume componentes Team360, no clases DaisyUI dispersas.
- **Contrato backend/frontend**: estructura de bootstrap, tipos compartidos.

## Propuesta de estructura frontend Team360

### Arbol sugerido

```
src/
├── layouts/
│   ├── PublicMarketingLayout.astro     # team360.live
│   ├── ConsoleAuthLayout.astro         # login, recovery, select-workspace
│   ├── ConsoleAppLayout.astro          # App Shell autenticado completo
│   └── ConsoleMinimalLayout.astro      # errores, acciones puntuales
├── pages/
│   ├── (public marketing routes)
│   │   └── index.astro
│   ├── (console auth routes)
│   │   ├── login.astro
│   │   └── select-workspace.astro
│   └── (console app routes)
│       └── w/
│           └── [workspaceId]/
│               ├── index.astro
│               ├── services/
│               ├── reports/
│               └── settings/
├── components/
│   ├── console/
│   │   ├── AppShell.svelte
│   │   ├── Sidebar.svelte
│   │   ├── Topbar.svelte
│   │   ├── WorkspaceSwitcher.svelte
│   │   ├── Breadcrumbs.svelte
│   │   ├── NotificationCenter.svelte
│   │   └── UserMenu.svelte
│   ├── marketing/
│   │   └── (componentes del sitio publico)
│   ├── ui/
│   │   ├── Button.svelte
│   │   ├── Card.svelte
│   │   ├── Badge.svelte
│   │   ├── Modal.svelte
│   │   ├── DataTable.svelte
│   │   ├── Tabs.svelte
│   │   ├── Loading.svelte
│   │   ├── EmptyState.svelte
│   │   └── ErrorBoundary.svelte
│   └── agui/
│       ├── AguiProvider.svelte
│       ├── AgentSessionPanel.svelte
│       ├── AgentEventStream.svelte
│       ├── AgentRunStatus.svelte
│       ├── AgentToolCallCard.svelte
│       ├── AgentHumanApprovalCard.svelte
│       └── AgentErrorBoundary.svelte
├── lib/
│   ├── api/
│   │   ├── client.ts              # fetch wrapper genérico con auth
│   │   └── bootstrap.ts           # llamada al bootstrap context
│   ├── agui/
│   │   ├── client.ts              # AG-UI client (SSE + command)
│   │   ├── types.ts               # tipos de eventos
│   │   ├── transport.ts           # adaptadores SSE/WS/HTTP
│   │   ├── normalize.ts           # normalizacion de eventos
│   │   └── session.ts             # manejo de sesion AG-UI
│   ├── auth/
│   │   ├── session.svelte.ts      # sesion actual
│   │   └── token.ts               # manejo de tokens
│   ├── navigation/
│   │   ├── registry.ts            # registro declarativo
│   │   └── derive.svelte.ts       # derivacion desde permisos
│   ├── permissions/
│   │   └── types.ts               # tipos de permisos
│   └── workspace/
│       └── context.ts             # utilidades de workspace
├── stores/
│   ├── currentUser.svelte.ts
│   ├── activeOrganization.svelte.ts
│   ├── activeWorkspace.svelte.ts
│   ├── permissions.svelte.ts
│   ├── navigation.svelte.ts
│   ├── aguiSession.svelte.ts
│   ├── notifications.svelte.ts
│   ├── serviceContext.svelte.ts
│   └── uiPreferences.svelte.ts
└── styles/
    ├── global.css                  # Tailwind 4 + tokens
    └── tokens.css                  # design tokens CSS
```

### Notas sobre la estructura

- `stores/` usa archivos `.svelte.ts` (Runes module) con `$state` y `$derived`.
- `lib/api/` no toca Svelte, es TypeScript puro.
- `lib/agui/` separa transporte, normalizacion y sesion.
- `components/ui/` son primitives sin logica de negocio.
- `components/console/` son componentes de App Shell.
- `components/agui/` son componentes AG-UI futuros.

## Estrategia Astro

### Configuracion base sugerida

```ts
// astro.config.ts
import { defineConfig } from "astro/config";
import svelte from "@astrojs/svelte";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  srcDir: "./src",
  output: "server",           // o "static" + "hybrid" segun necesidad
  devToolbar: { enabled: false },
  integrations: [svelte()],
  vite: {
    plugins: [tailwindcss()], // Tailwind 4 via Vite plugin
  },
});
```

### Decisiones

- `output: "server"` si Team360 Console necesita SSR para auth, sesion y bootstrap dinamico.
- Si team360.live es principalmente estatico, usar `hybrid` con rutas estaticas para marketing y SSR para rutas de consola.
- La integracion `@astrojs/svelte` ya esta probada en Vertice360.
- Tailwind 4 se configura via Vite plugin, NO via PostCSS.
- No usar `tailwindcss.config` (obsoleto en TW4).
- No usar PostCSS a menos que se necesite compat con algo legacy.

### Layouts Astro

Astro maneja la estructura de paginas y layouts. Svelte se encarga de la interactividad.

- `PublicMarketingLayout.astro`: layout publico para team360.live, sin JS interactivo pesado.
- `ConsoleAuthLayout.astro`: layout minimal para login, recovery, select-workspace.
- `ConsoleAppLayout.astro`: App Shell completo con sidebar, topbar, breadcrumbs, contenido.
- `ConsoleMinimalLayout.astro`: errores 401/403/404, loading global, pantallas sin navegacion completa.

## Estrategia Svelte 5 con Runes

### Donde usar Svelte 5

Svelte se usa para componentes con interactividad del lado del cliente:

- App Shell: Sidebar, Topbar, WorkspaceSwitcher, NotificationCenter
- Componentes de UI: modales, tabs, tablas con filtros, dashboards interactivos
- Componentes AG-UI: provider, event stream, run status, tool call cards
- Formularios y configuracion
- Estados de carga, error y empty

No se necesita Svelte para contenido estatico de marketing.

### Manejo de estado con Runes

```ts
// stores/activeWorkspace.svelte.ts
import { bootstrap } from "$lib/api/bootstrap";

let _activeWorkspaceId = $state<string | null>(null);
let _activeWorkspace = $derived(
  _activeWorkspaceId ? bootstrap.accessibleWorkspaces.find(w => w.id === _activeWorkspaceId) : null
);

export const activeWorkspace = {
  get id() { return _activeWorkspaceId; },
  get data() { return _activeWorkspace; },
  set: (id: string | null) => { _activeWorkspaceId = id; },
};
```

### Reglas de estado

1. **Estado compartido**: solo lo que necesita >1 componente no emparentado (usuario activo, workspace, permisos).
2. **Estado local**: $state dentro del componente para UI ephemeral.
3. **Estado derivado**: $derived para computaciones desde estado compartido.
4. **Sin stores globales innecesarios**: no crear un store para cada cosa.
5. **Cache local**: solo si reduce latencia real y se invalida explicitamente.
6. **Descarte al cambiar workspace**: al cambiar `activeWorkspace.set()`, los stores que dependen de el deben resetearse.

### Modulos de estado sugeridos

| Modulo | Contenido | Depende de |
|---|---|---|
| currentUser | id, name, email, avatar, rol | bootstrap |
| activeOrganization | org actual, tipo, arbol | bootstrap, seleccion |
| activeWorkspace | ws actual, servicios, modulos | bootstrap, seleccion |
| effectivePermissions | permisos computados | currentUser + activeOrganization |
| enabledModules | modulos habilitados | effectivePermissions + activeWorkspace |
| contractedServices | servicios del workspace | activeWorkspace |
| navigationItems | items de navegacion derivados | todo lo anterior |
| aguiSession | sesion AG-UI, estado | currentUser |
| notifications | resumen de notificaciones | bootstrap periodic |

### Como derivar navegacion desde permisos

```ts
// stores/navigation.svelte.ts
import { effectivePermissions } from "./permissions.svelte";
import { enabledModules } from "./enabledModules.svelte";
import { navigationRegistry } from "$lib/navigation/registry";

const navigationItems = $derived(
  navigationRegistry
    .filter(item => item.requiredPermissions.every(p => effectivePermissions.list.includes(p)))
    .filter(item => !item.requiredModule || enabledModules.list.includes(item.requiredModule))
    .map(item => ({
      ...item,
      children: item.children?.filter(child =>
        child.requiredPermissions.every(p => effectivePermissions.list.includes(p))
      ),
    }))
);
```

### Como manejar cambio de workspace

```ts
// Evento: usuario cambia workspace
const switchWorkspace = async (newWorkspaceId: string) => {
  // 1. Validar contra backend
  const valid = await api.validateWorkspaceAccess(newWorkspaceId);
  if (!valid) return;

  // 2. Limpiar estado dependiente
  aguiSession.reset();      // descartar sesion AG-UI
  notifications.clear();    // descartar notificaciones
  serviceContext.clear();   // descartar contexto de servicios

  // 3. Actualizar contexto
  activeWorkspace.set(newWorkspaceId);

  // 4. Recargar datos del nuevo contexto
  await Promise.all([
    bootstrap.refresh(newWorkspaceId),
    aguiSession.reconnect(),
  ]);
};
```

## Estrategia Tailwind 4

### Configuracion

Tailwind 4 en Astro se configura preferentemente via Vite plugin:

```ts
// astro.config.ts
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  vite: {
    plugins: [tailwindcss()],
  },
});
```

No se necesita:
- mantener `tailwind.config.js/cjs` legacy como fuente principal
- mantener `postcss.config.js/cjs` legacy salvo necesidad puntual
- `@tailwind base/components/utilities` directives (reemplazado por `@import "tailwindcss"`)

El CSS global debe declarar Tailwind y DaisyUI 5 con su plugin CSS-first:

```css
@import "tailwindcss";
@plugin "daisyui";
```

### Migracion desde Tailwind 3

Pasos:
1. Dejar de reutilizar `tailwind.config.cjs` y `postcss.config.cjs` legacy como fuente principal.
2. Configurar `@tailwindcss/vite` en Astro/Vite.
3. Reemplazar `@tailwind base/components/utilities` por `@import "tailwindcss"` en CSS.
4. Migrar DaisyUI a v5 y declarar `@plugin "daisyui"` en CSS.
5. Migrar el tema hardcodeado `vertice360` a un tema Team360 propio o a tokens neutrales.
6. Encapsular usos de `btn`, `card`, `badge`, `loading`, `modal`, `tabs`, `alert` y `drawer` detras de componentes Team360.
7. Revisar `@layer`, `@screen` y `@apply` legacy caso por caso.
8. Migrar tokens que deban generar utilities desde `tailwind.config` a CSS nativo con `@theme`.

### Design tokens iniciales (CSS)

```css
/* styles/tokens.css */
@import "tailwindcss";

@theme {
  --color-brand-primary: #1F7A63;
  --color-brand-secondary: #4FAF9A;
  --color-brand-accent: #22C55E;
  --color-text-primary: #2E2E2E;
  --color-text-secondary: #6B7280;
  --color-bg-main: #F5F7F8;
  --color-bg-card: #FFFFFF;
  --color-bg-card-secondary: #F7F7F7;
  --font-family-sans: "Inter", system-ui, sans-serif;
  --font-family-heading: "Poppins", system-ui, sans-serif;
}
```

### DaisyUI: decision

**Decision vigente: Team360 adopta Tailwind CSS 4 + DaisyUI 5 como combinacion obligatoria para la primera etapa UX/frontend.**

Integracion moderna:

```css
@import "tailwindcss";
@plugin "daisyui";
```

Reglas:

- DaisyUI 5 es el acelerador UI obligatorio de la primera etapa frontend.
- DaisyUI se configura desde CSS. No reutilizar la configuracion legacy dentro de `tailwind.config.cjs`.
- No reutilizar el tema hardcodeado `vertice360`.
- Definir tokens Team360 con `@theme` cuando deban generar utilities.
- Configurar temas DaisyUI desde CSS-first config o migrar a un tema Team360 propio.
- Encapsular DaisyUI detras de componentes de `components/ui/`.
- Mantener la opcion de reemplazar implementaciones internas sin afectar pantallas consumidoras.

### Riesgos TW4

- Clases con variantes `@screen` no existen en TW4 (reemplazar por media queries estandar).
- Plugins PostCSS como `autoprefixer` no son necesarios con TW4 (Vite maneja prefixing).
- `@layer components` no funciona igual (usar `@utility`).
- Mixins `@apply` dentro de `@layer` pueden no migrar directamente.
- Componentes Vertice360 acoplados a clases DaisyUI requieren migracion a wrappers Team360.

## Estrategia AG-UI

### Contexto actual

AG-UI es mencionado en la documentacion de Team360 como capa estructural de eventos y streaming backend/frontend. En Vertice360 se implementa de forma ad-hoc con:

1. **Backend**: `agui_stream` module con `broadcaster.py` (pub/sub en memoria) y `routes.py` (endpoint SSE, trigger debug).
2. **Frontend**: conexion SSE directa via `EventSource`, eventos con envelope `CUSTOM { name, value, timestamp }`.
3. **Sin SDK formal**: Vertice360 no usa `@ag-ui/client` ni `@ag-ui/core`.

### Hipotesis

- AG-UI (Agent-User Interface) en el contexto Team360/Vertice360 se refiere al canal de eventos en tiempo real entre agentes/workers y la UI.
- No parece haber un paquete oficial `@ag-ui/*` en el registro publico; es un protocolo/convencion interna.
- La implementacion actual (SSE + envelope CUSTOM) funciona como AG-UI de facto.
- Para Team360, AG-UI debe ser una capa formal pero sin sobredisenar.

### Que necesita Team360 para AG-UI frontend

No se requieren paquetes externos para AG-UI. La implementacion se basa en:

| Componente | Descripcion |
|---|---|
| `EventSource` (navegador) | Transporte SSE nativo |
| `fetch` (navegador) | Comandos POST/REST |
| Capa de normalizacion | Convertir eventos raw a tipos internos |
| Capa de sesion | Reconexion, estado, teardown |

### Estructura sugerida

```
src/lib/agui/
├── client.ts              # Cliente AG-UI principal (conexion, comando, eventos)
├── types.ts               # Tipos de eventos AG-UI
├── transport.ts           # Adaptadores SSE/WebSocket segun necesidad
├── normalize.ts           # Normalizacion de eventos raw a tipos internos
└── session.ts             # Manejo de sesion, reconexion, heartbeat
```

### Componentes Svelte AG-UI sugeridos (futuros)

| Componente | Funcion |
|---|---|
| `AguiProvider.svelte` | Proveedor de contexto AG-UI para arbol de componentes |
| `AgentSessionPanel.svelte` | Panel de estado de sesion con agente |
| `AgentEventStream.svelte` | Stream en vivo de eventos AG-UI |
| `AgentRunStatus.svelte` | Estado de ejecucion actual |
| `AgentToolCallCard.svelte` | Card de tool call con argumentos y resultado |
| `AgentHumanApprovalCard.svelte` | Solicitud de aprobacion humana |
| `AgentErrorBoundary.svelte` | Manejo de errores de agente |

### Separacion UI state / Agent state

```
UI State (Svelte stores)
  ├── reactive, sincrono, local
  ├── loading, error, empty states
  └── permisos, workspace, navegacion

Agent State (AG-UI session)
  ├── asincrono, streaming, efimero
  ├── tool calls, run status, events
  ├── human approval requests
  └── no persiste entre cambios de workspace
```

### Event types sugeridos para Team360

```
agent.run.started
agent.run.step
agent.run.completed
agent.run.failed
agent.tool.call
agent.tool.result
agent.human.approval.required
agent.human.approval.granted
agent.human.approval.denied
agent.error
agent.heartbeat
```

### Contrato de eventos AG-UI (propuesta)

```ts
interface AguiEvent {
  type: "CUSTOM";
  name: string;
  timestamp: number;
  correlationId?: string;
  value: Record<string, unknown>;
}
```

Este contrato es compatible con la implementacion actual de Vertice360 y permite migracion gradual.

## Bootstrap contract frontend/backend

### Principio

Antes de renderizar datos privados, la consola debe recibir del backend un payload de bootstrap que define el contexto completo del usuario.

### Payload esperado

```ts
interface ConsoleBootstrap {
  currentUser: {
    id: string;
    name: string;
    email: string;
    avatarUrl?: string;
    role: string;
    locale: string;
  };
  activeMembership: {
    organizationId: string;
    organizationType: "team360" | "partner" | "direct_client" | "partner_client";
    workspaceId: string;
    role: string;
  };
  accessibleOrganizations: Array<{
    id: string;
    name: string;
    type: string;
    parentId?: string;
  }>;
  accessibleWorkspaces: Array<{
    id: string;
    name: string;
    organizationId: string;
    services: string[];
  }>;
  effectivePermissions: string[];
  enabledModules: string[];
  contractedServices: Array<{
    id: string;
    name: string;
    status: string;
    module: string;
  }>;
  authorizedTree: {                              // arbol de organizaciones autorizadas
    id: string;
    name: string;
    type: string;
    children: Array<{ id: string; name: string; type: string; }>;
  };
  notificationSummary: {
    unread: number;
    critical: number;
  };
  featureFlags: Record<string, boolean>;
  uiHints?: {                                    // opcional, no autoriza nada
    welcomeMessage?: string;
    quickActions?: string[];
    defaultDashboard?: string;
  };
  aguiCapabilities?: {                           // opcional
    enabled: boolean;
    transport: "sse" | "ws";
    endpoint: string;
  };
}
```

### Reglas

- El frontend **deriva UI** desde este payload, pero **no autoriza por si mismo**.
- Cada request privada debe re-validar identidad, workspace, permisos y alcance en backend.
- `uiHints` es opcional informativo, nunca reemplaza autorizacion.
- `aguiCapabilities` informa al frontend que transporte AG-UI usar.
- Workspace changes deben solicitar nuevo bootstrap o refresh parcial.

## Riesgos tecnicos

1. **Migracion Tailwind 3 -> 4**: exige migrar configuracion legacy, tema DaisyUI `vertice360`, clases @screen, @apply y @layer. Requiere plan de migracion.
2. **Acoplamiento DaisyUI**: usar clases DaisyUI dispersas dificultaria reemplazos o ajustes visuales. Encapsular en `components/ui/`.
3. **SSE + autenticacion**: el SSE actual es publico. Team360 necesita SSE autenticado por workspace.
4. **Multi-tenant en SSE**: un solo canal SSE no escala para multi-organizacion. Disenar por sesion/workspace.
5. **Astro 5 -> 6**: cambios menores en API, revisar compatibilidad de integraciones.
6. **Estado global SSR/CSR**: hidratacion de estado Svelte desde server. Astro puede pasar props serializadas.
7. **Testing**: no hay test infrastructure. Agregar Vitest + svelte-testing-library.
8. **Rendimiento**: demasiados stores Svelte compartidos pueden crear cascadas de reactividad. Disenar stores granulares.
9. **Iconos**: no hay icon library definido. Evaluar Lucide, Phosphor, o Heroicons.
10. **Tema oscuro**: si se requiere, disenar desde el inicio con variables CSS.

## Plan de migracion por fases

### Fase 0: Analisis y documentacion (esta fase)

- [x] Inspeccionar Vertice360
- [x] Detectar versiones y brechas
- [x] Verificar versions latest
- [x] Documentar estrategias
- [x] Crear ADR-004
- [x] Actualizar referencias

### Fase 1: Base del stack

1. `pnpm create astro` con template minimal en Team360.
2. Configurar `@astrojs/svelte`, `@tailwindcss/vite` y DaisyUI 5 como acelerador UI obligatorio.
3. Configurar `tsconfig.json` strict.
4. Crear `src/styles/global.css` con `@import "tailwindcss"`, `@plugin "daisyui"` y design tokens.
5. Verificar build y dev server funcionando.
6. Migrar layout base desde Vertice360 (adaptado a Team360).

### Fase 2: Layouts y App Shell

1. Crear `PublicMarketingLayout.astro`, `ConsoleAuthLayout.astro`, `ConsoleAppLayout.astro`, `ConsoleMinimalLayout.astro`.
2. Implementar App Shell Svelte con sidebar, topbar, breadcrumbs, user menu.
3. Implementar WorkspaceSwitcher.
4. Conectar stores `currentUser`, `activeOrganization`, `activeWorkspace`.
5. Integrar bootstrap context (mock inicial, real despues).

### Fase 3: Componentes base UI

1. Crear wrappers Team360: Button, Card, Badge, Modal, DataTable, Tabs, Alert, Drawer, Loading, EmptyState y ErrorBoundary. Pueden usar DaisyUI internamente.
2. Crear paginas placeholder para rutas de consola.
3. Implementar sistema de navegacion declarativa + derivacion por permisos.

### Fase 4: AG-UI integration

1. Crear `src/lib/agui/` con cliente, types, normalize.
2. Crear `AguiProvider.svelte`.
3. Integrar SSE autenticado por workspace.
4. Crear `AgentEventStream.svelte`, `AgentRunStatus.svelte`.
5. Probar con backend AG-UI de Team360.

### Fase 5: Refinamiento

1. Testing con Vitest + svelte-testing-library.
2. Accesibilidad basica.
3. Performance profiling.
4. Documentacion de componentes.
5. CI/CD setup para frontend.

## Proximos pasos

1. Aprobar o ajustar esta propuesta.
2. Ejecutar Fase 1: crear proyecto Astro con stack moderno, verificar build.
3. Ejecutar Fase 2: layouts, App Shell, stores, bootstrap mock.
4. Definir primer conjunto de paginas y servicios demo para Team360 Console.
5. Definir icon library.
6. Coordinar con backend el contrato de bootstrap y eventos AG-UI.

## Referencias

- DaisyUI 5 release notes: `https://daisyui.com/docs/v5/`
- DaisyUI install: `https://daisyui.com/docs/install/`
- DaisyUI config CSS-first: `https://daisyui.com/docs/config/`
- DaisyUI themes CSS-first: `https://daisyui.com/docs/themes/`
- Tailwind CSS con Vite: `https://tailwindcss.com/docs/installation/using-vite`
- Tailwind CSS `@theme`: `https://tailwindcss.com/docs/theme`
- Astro: Tailwind 4 via Vite plugin: `https://docs.astro.build/en/guides/integrations-guide/tailwind/`

- `docs/adr/ADR-004-team360-frontend-base-vertice360-modern-stack.md`
- `docs/ux/team360-console-app-shell-and-layout-system.md`
- `docs/ux/team360-console-navigation-model.md`
- `docs/ux/team360-domains-and-console-strategy.md`
- `lat.md/console-multi-organization.md`
- `SrvRestAstroLS_v1/docs/status_actual.md`
- Vertice360: `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Vertice360/SrvRestAstroLS_v1/astro`
