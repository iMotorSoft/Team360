# Auditoría Etapa 1 — Base visual global del handoff UX

Fecha: 2026-08-02

## 1. Contexto

| Rol | Rama / commit |
| --- | --- |
| Rama funcional (base obligatoria) | `feature/console-backend-core` @ `086abfd` |
| Rama de diseño (solo fuente visual) | `ux/team360-console-design-handoff` @ `a75909d` |

La rama de diseño se trata únicamente como fuente visual y de UX. No es la nueva
base. No se realizó merge, rebase ni reemplazo masivo.

## 2. Metodología

Comparación sin cambiar de base de trabajo:

```bash
git diff --stat feature/console-backend-core..a75909d
git diff --name-status feature/console-backend-core..a75909d
git diff feature/console-backend-core..a75909d -- <archivo>
git show a75909d:<ruta>
```

## 3. Resumen del diff

- **475 archivos** comparados (6520 inserciones, 91902 eliminaciones).
- La gran mayoría de eliminaciones son archivos creados en la rama funcional
  después del punto de divergencia de la rama UX (tests, labs, knowledge,
  políticas `lat.md`, E2E, documentación). No son pérdidas de la rama funcional.
- **Único archivo de estilos globales modificado:** `src/styles/global.css`
  (+264 líneas). `src/styles/marketing.css` no cambió.
- **Únicos cambios de configuración frontend:** `astro.config.mjs` y
  `package.json`, ambos con cambios peligrosos para la funcional (ver C).

## 4. Clasificación de diferencias

### A. Base visual segura — adoptada

| Elemento | Detalle |
| --- | --- |
| Import de tipografías | Google Fonts: Inter 400–700 + Poppins 400–800 |
| Tokens de color DaisyUI | Paleta completa `team360` reemplazada: oklch → rgba/hex (base-100..error-content) |
| Variables de tarjetas | `--color-card-border`, `--color-card-border-light`, `--color-card-border-mini`, `--color-card-bg`, `--color-card-bg-light`, `--color-card-bg-dark` |
| Sombras de tarjetas | `--shadow-card-default`, `--shadow-card-large` |
| Colores semánticos de consola | `--color-console-title`, `--color-console-subtitle`, `--color-console-muted`, `--color-console-brand` |
| Tipografía de marca | `--font-poppins` |
| Clases utilitarias | `.title-h1`, `.title-h2`, `.top-badge`, `.top-badge-neutral`, `.details-text` |

Detalle de la paleta adoptada (design tokens):

- `--color-primary: #168b88` (verde teal) — color de marca.
- `--color-secondary: rgba(9,35,62,1)` (azul marino oscuro).
- `--color-base-content: #123653` (azul oscuro para texto).
- `--color-base-100..300`: blancos azulados (fondos).
- `info/success/warning/error` con sus `-content` para contraste.

Ubicación: variables dentro de `@theme` para generar utilidades Tailwind
(`bg-card-bg`, `shadow-card-default`, `text-console-title`, `font-poppins`).

**No adoptado dentro de A:** el bloque `.custom-select-*` (~150 líneas) porque
en la rama funcional no existe markup que use esas clases (0 coincidencias en
`src/`). Copiarlo sería CSS muerto. Se migra junto con los componentes en la
Etapa 2 (LocalePicker, ProfileSwitcher, WorkspaceSwitcher).

### B. Componentes visuales adaptables — documentados, NO copiados

Contienen lógica funcional distinta o pertenecen a pantallas completas. Se
rediseñan en etapas posteriores preservando la lógica funcional.

| Archivo | Delta | Nota |
| --- | --- | --- |
| `components/console/AppShell.svelte` | 119± | Shell de consola autenticada |
| `components/console/Sidebar.svelte` | 74± | Navegación lateral |
| `components/console/Topbar.svelte` | 66± | Barra superior |
| `components/console/ConsoleSectionPage.svelte` | 617± | Página genérica de consola |
| `components/console/ConsoleDashboard.svelte` | 389± | Dashboard |
| `components/console/services/ServiceDetail.svelte` | 371± | Detalle de servicio |
| `components/console/services/ServicesList.svelte` | 197± | Lista de servicios |
| `components/console/alerts/AlertsList.svelte` | 86± | Lista de alertas |
| `components/console/reports/ReportsList.svelte` | 154± | Lista de reportes |
| `components/console/runs/RunsList.svelte` | 109± | Lista de runs |
| `components/console/settings/WorkspaceSettings.svelte` | 101± | Configuración |
| `components/console/tasks/TasksList.svelte` | 59± | Lista de tareas |
| `components/console/team/TeamList.svelte` | ± | Lista de equipo |
| `components/console/workers/WorkersList.svelte` | ± | Lista de workers |
| `components/console/Breadcrumbs.svelte`, `ContextBanner.svelte`, `NotificationCenter.svelte`, `ProfileSwitcher.svelte`, `WorkspaceSwitcher.svelte` | ± | Subcomponentes de shell |
| `components/marketing/*` | ± | Header/Footer/hero/section marketing |
| `layouts/MockAccessLayout.astro`, `layouts/PublicMarketingLayout.astro` | ± | Layouts públicos |
| `pages/index.astro`, `pages/login.astro`, `pages/select-workspace.astro` | ± | Pantallas públicas funcionales |
| `pages/t360.astro` | ± | **Página pública protegida** del Diagnosticador/Vera |

Total: 44 archivos, +3591/−3750.

### C. Cambios funcionales peligrosos — descartados

| Archivo | Cambio en UX | Riesgo si se adopta |
| --- | --- | --- |
| `astro/astro.config.mjs` | Elimina plugin del browser-global del embed (`team360DiagnosticadorBrowserAsset`) | Rompe la distribución del Diagnosticador embebible |
| `astro/package.json` | Quita `@playwright/test`, scripts `test:e2e`, agrega `design:smoke` | Degrada el gate E2E reproducible |
| `components/console/diagnosis/ConsoleDiagnosis.svelte` | Eliminado | Borraría pantalla funcional de diagnóstico |
| `pages/w/[workspaceId]/diagnosis/index.astro` | Eliminado | Borraría ruta funcional |
| Todos los tests/labs/knowledge/`lat.md` ausentes en UX | Ausentes por divergencia | No son cambios; la rama funcional los conserva |
| `global.js` / rutas API | — | No modificado; `global.js` sigue siendo fuente de verdad de URLs |

### D. Archivos nuevos potencialmente reutilizables

| Archivo | Propósito | Lógica | Riesgo | Recomendación |
| --- | --- | --- | --- | --- |
| `components/console/CustomSelect.svelte` (119) | Select estilizado con teclado/aria | Sí (interacción) | Bajo | Etapa 2, junto con switchers |
| `components/console/alerts/AlertCard.svelte` (223) | Card de alerta rediseñada | Parcial | Bajo | Etapa 2 |
| `components/diagnosis/HeroVisual.astro` | Visual del hero de diagnóstico | No | Bajo | Etapa 2/3 |
| `components/diagnosis/OrientationExample.astro` | Ejemplo de orientación | No | Bajo | Etapa 2/3 |
| `components/marketing/Team360Logo.astro` | Logo de marca | No | Bajo | Etapa 2 |
| `components/marketing/HeroProcessVisual.astro` (M) | Visual de proceso | No | Bajo | Etapa 2 |
| `scripts/design-smoke.mjs` | Smoke visual del handoff | Parcial | Bajo | Evaluar reutilización |
| `docs/design-review/screenshots/*.png` (18) | Evidencia visual desktop/mobile | No | Ninguno | Referencia de intención de diseño |

## 5. Matriz de riesgo por archivo/componente

| Archivo/área | Riesgo | Acción en Etapa 1 |
| --- | --- | --- |
| `src/styles/global.css` | Bajo (tokens/utilitarias, sin selectores destructivos) | **Adoptado selectivamente** |
| `src/styles/marketing.css` | Ninguno (sin diff) | Sin cambios |
| Componentes console (shell/listas) | Alto si se copian (lógica distinta) | Solo documentar |
| `astro.config.mjs` | Crítico (embed) | No tocar |
| `package.json` | Alto (E2E) | No tocar |
| `pages/t360.astro` | Crítico (público protegido) | No tocar |
| `global.js` | Crítico (URLs) | No tocar |
| Backend / PostgreSQL / Milvus / LiteLLM | — | No tocar |

## 6. Fuente de verdad funcional

```
Lógica y comportamiento: feature/console-backend-core
Diseño y presentación:   ux/team360-console-design-handoff
```

- Cada pantalla funcional conserva su lógica actual; el diseño se adapta
  alrededor de ella.
- En conflicto, gana la funcionalidad actual.
- La sección pública del Diagnosticador/Vera (`/t360`) queda intacta.

## 7. Implementación realizada

Archivo modificado: `SrvRestAstroLS_v1/astro/src/styles/global.css`.

1. Import de Google Fonts (Inter + Poppins) — degradación elegante a
   system-ui si falla la red.
2. Paleta `team360` completa reemplazada por los tokens del handoff.
3. Variables de tarjetas, sombras, colores semánticos de consola y
   `--font-poppins` añadidas en `@theme`.
4. Clases utilitarias `.title-h1`, `.title-h2`, `.top-badge`,
   `.top-badge-neutral`, `.details-text` añadidas.
5. `:root`, `body`, `:focus-visible`, `prefers-reduced-motion` y reglas base
   existentes conservadas sin cambios.

Excluido deliberadamente: CSS `.custom-select-*` (sin markup en la rama
funcional; se migra en Etapa 2) y todo cambio de componentes/páginas/config.

## 8. Validaciones

| Validación | Resultado |
| --- | --- |
| `git diff --check` | PASS |
| `pnpm check` | 3 errores preexistentes en `src/lib/t360/embed/mount.ts` (embed Vera), ajenos a esta etapa |
| `pnpm build` | PASS — 146 páginas |
| Tests E2E | No ejecutados en Etapa 1 (requieren servicios; smoke visual en su lugar) |
| PostgreSQL / Milvus / LiteLLM | No iniciados, detenidos ni reiniciados |

## 9. Riesgos pendientes (etapas posteriores)

- Rediseño del shell de consola (AppShell, Sidebar, Topbar, switchers) con el
  sistema CustomSelect del handoff.
- Migración de listas y cards (alerts, services, reports, runs, tasks, team,
  workers) a los tokens de tarjeta y sombras nuevos.
- Hero visual de diagnóstico y componentes de marketing.
- Revisión de contraste en pantallas funcionales que hoy usan valores
  hardcodeados.
- Evaluar self-hosting de fuentes si Google Fonts no es aceptable en el
  entorno productivo del cliente.

## 10. Próxima etapa

**Etapa 2: migración controlada del shell de consola — header, navegación y
layout principal, preservando rutas, autenticación y estado.**
