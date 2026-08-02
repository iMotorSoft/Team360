# Etapa 2 — Mapa del shell funcional y comparación con el handoff UX

Fecha: 2026-08-02

Base: `feature/console-backend-core` @ `5d8ca08` (cierre Etapa 1).
Referencia visual: `ux/team360-console-design-handoff` @ `a75909d`.

## 1. Mapa del shell funcional real

| Pieza | Archivo funcional | Responsabilidad | Lógica a preservar | Cambio visual permitido | Riesgo |
| --- | --- | --- | --- | --- | --- |
| Layout raíz | `src/layouts/ConsoleAppLayout.astro` | HTML, theme, skip-link, monta AppShell | skip-link, `data-theme`, props | ninguno (ya alineado) | bajo |
| Shell | `src/components/console/AppShell.svelte` | Grid: Sidebar + Topbar + contenido + aside | `mobileOpen`, `consoleContext.initialize`, dispatch de vistas por `view`, slots, aside contextual | `lg:ps-[20rem]`, tokens en aside, tipografía | medio |
| Sidebar | `src/components/console/Sidebar.svelte` | Drawer fijo + nav por grupos | enlaces `item.href`, `onclick={onClose}`, estado activo `item.view === view`, alert badge, dirección RTL del drawer | ancho 20rem, header h-24 + logo, `.top-badge-neutral`, iconos 1.5rem, spacing | alto |
| Topbar | `src/components/console/Topbar.svelte` | Header sticky: menú mobile, contexto org/workspace, locale, search, notificaciones, avatar | `onMenu`, `setLocale`, org/workspace visibles, avatar con usuario real del store | h-24, `.top-badge`, `.details-text`, botones redondos, avatar redondo | alto |
| ProfileSwitcher | `src/components/console/ProfileSwitcher.svelte` | Select de perfil mock | `changeProfile` → `buildConsoleRoute` | ninguno (requiere CustomSelect → se difiere) | medio |
| WorkspaceSwitcher | `src/components/console/WorkspaceSwitcher.svelte` | Select de workspace | navegación a workspace real | ninguno (requiere CustomSelect → se difiere) | medio |
| NotificationCenter | `src/components/console/NotificationCenter.svelte` | Dropdown de alertas abiertas | filtro `status !== "resolved"`, cierre, `formatDateTime` | ancho dropdown, tamaños de texto, botón redondo | medio |
| Breadcrumbs | `src/components/console/Breadcrumbs.svelte` | Ruta de navegación | `getViewLabelKey`, i18n | text-sm | bajo |
| ContextBanner | `src/components/console/ContextBanner.svelte` | Banner contexto operativo (delegado/propio) | `showDelegatedAccessNotice`, `audience` | `.top-badge-neutral`, tamaños | bajo |
| Store | `src/stores/consoleContext.svelte` | bootstrap, workspace/org activos, locale, direction, initialize/setLocale | todo (no se toca) | — | — |
| Navegación | `src/lib/navigation/registry.ts`, `derive.ts` | tipos ConsoleView, grupos, hrefs | todo (no se toca) | — | — |
| Mock | `src/lib/mock/*` | perfiles, workspaces, datos | todo (no se toca) | — | — |

Rutas del shell: `w/[workspaceId]/*` (32 páginas), `login`, `select-workspace`.

## 2. Comparación con el handoff (a75909d)

### Piezas visuales adoptadas

| Pieza | Cambio | Justificación |
| --- | --- | --- |
| Contenedor | `lg:ps-[18.5rem]` → `lg:ps-[20rem]` | Acompaña el nuevo ancho del sidebar |
| Sidebar ancho | `w-[18.5rem]` → `w-[20rem]` | Intención del handoff |
| Sidebar header | `h-[4.75rem]` → `h-24` + logo `team360_logo_t.png` + nombre 2 líneas | Asset existe en la rama funcional; nombre `"Team360 Console"` dividido sin pérdida |
| Sidebar nav | grupos `.top-badge-neutral`, items `text-lg` + iconos `size-[1.5rem]`, `hover:bg-base-200` | Clases utilitarias de la Etapa 1 |
| Sidebar footer | `.top-badge` "Modo diseño" | Consistencia de tokens |
| Topbar altura | `h-[4.75rem]` → `h-24` | Alineación con sidebar |
| Topbar contexto | `text-some` (typo UX) → `.top-badge` real; org/workspace con `.details-text` | Clase correcta; se **conserva** el texto org/workspace |
| Topbar acciones | search/notificación redondos (`size-11`, `hover:bg-slate-100`, iconos `size-7`), avatar redondo `size-12` | Intención visual |
| NotificationCenter | dropdown `min(24rem,…)`, `p-3`, títulos `text-xl`/`text-base` | Intención visual |
| Breadcrumbs | `text-sm` | Legibilidad |
| ContextBanner | `.top-badge-neutral`, `text-base`/`text-sm` | Tokens |
| Aside (AppShell) | títulos `.top-badge`/`.top-badge-neutral`, bordes/fondos con tokens `card-border`/`card-bg`, tamaños moderados | Tokens de la Etapa 1 |

### Piezas reinterpretadas (desviación deliberada)

| Pieza | Handoff | Decisión funcional |
| --- | --- | --- |
| Locale/Profile/Workspace selects | `CustomSelect.svelte` | Se mantiene el `<select>` nativo funcional (accesible, teclado, labels); CustomSelect se difiere a Etapa 3/4 con su CSS de Etapa 1 |
| Topbar contexto | Punto decorativo pulsante en lugar del texto org/workspace | Se conserva el texto `organización / workspace` (requisito: conservar contexto visible) |
| Sidebar logo | `background-image` con path literal `/src/assets/…` | Se usa import real del asset (el path literal no sobrevive `astro build`) |
| NotificationCenter items | `AlertCard` | Se mantiene el `article` funcional (AlertCard es componente de pantalla interna) |
| Sidebar tagline | Comentado en UX | No se copia código comentado; se conserva el nombre de marca completo |

### Piezas descartadas

- `ConsoleSectionPage` rediseño (617±) — contenido interno (tablas), fuera de alcance de esta etapa.
- `AlertCard`, `CustomSelect` — pantallas internas / interacción nueva.
- `ConsoleDashboard` rediseño — pantalla interna.
- Eliminación de `ConsoleDiagnosis` y su ruta en el handoff — no se adopta (funcionalidad real).
- Comentarios `<!-- Inicio -->`, `<!-- Servicios -->` del handoff — basura de autoría, no se copia.
- Cambios de `package.json` / `astro.config.mjs` — rompen E2E y embed.

## 3. Riesgos y protecciones

- El embed Vera y `/t360` no se tocan; solo se verifica.
- `global.js` no se modifica.
- No se tocan stores, rutas, handlers ni props de componentes.
- E2E del shell con Playwright sobre runtime dev (backend-dev.sh + astro-dev.sh).
