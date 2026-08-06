# Team360 Console — Consolidación UX Stages 1-8

Fecha de consolidación: 2026-08-06.
Rama: `feature/console-backend-core` (HEAD inicial `a89924a`).
Este documento es la fuente de consulta consolidada de la migración UX de
Console. Los informes detallados por etapa permanecen en los documentos
enlazados; aquí se registra el mapa, la línea de tiempo, los commits, las rutas,
el sistema compartido, las superficies protegidas y el baseline de cierre.

## 1. Objetivo de la migración

Adaptar visualmente Team360 Console al sistema de diseño del handoff
(`ux/team360-console-design-handoff`) sin cambiar lógica funcional, rutas,
tabs, handlers, stores, autenticación, permisos, contratos ni artefactos
públicos del embed/Vera.

## 2. Regla de prioridad funcional

```
PREVALECE LA FUNCIONALIDAD EXISTENTE
```

- Lógica y comportamiento: `feature/console-backend-core` (fuente de verdad).
- Diseño y presentación: `ux/team360-console-design-handoff` (fuente visual).
- En conflicto, gana la funcionalidad actual; no se reemplazan controles
  interactivos sin demostrar equivalencia de teclado/foco/mobile.

## 3. Línea de tiempo de Stages 1-8

| Fecha | Stage | Contenido |
| --- | --- | --- |
| 2026-08-02 | 1 | Foundation visual: tokens de color, tipografías, cards, utilidades en `global.css` |
| 2026-08-02 | 2 | Shell funcional: Sidebar 20rem + logo, Topbar h-24, breadcrumbs, context banner, NotificationCenter |
| 2026-08-04 | 3 | Componentes compartidos: Card (6 variantes), SectionHeader, StatCard, Badge, Alert, AlertCard, Button, Select, Textarea, DataTable, EmptyState, Loading, Tabs |
| 2026-08-04 | Gate 3B | Serving DEV del entry embed por runtime oficial (`astro.config.dev.mjs` + `embed-dev-assets.mjs`) |
| 2026-08-05 | Gate 3C/3D | Corrección del logo del Sidebar + alineación del assertion E2E |
| 2026-08-05 | 4 | Dashboard, Reportes, Alertas, Clientes |
| 2026-08-05 | 5 | Operación: Services, Tasks, Runs, Workers |
| 2026-08-05 | 6 | Organización: Organizations, Partners, Workspaces, Team |
| 2026-08-05 | 7 | Settings y Support (primera adopción `Card variant="dark"`) |
| 2026-08-05 | 8 | Results y ServiceDetail (8 tabs) |

## 4. Commits

| Stage | Commits (feat/fix) | Commits (test) | Commits (docs) |
| --- | --- | --- | --- |
| 1 | `5d8ca08` | — | (contenido en stage-1 doc, commit `5d8ca08`) |
| 2 | `546e945` | — | (contenido en stage-2 doc, commit `546e945`) |
| 3 | `807a9a4` | `console-shared-components-stage3.spec.ts` (en 807a9a4) | (contenido en stage-3 doc) |
| Gate 3B | `7527a24` | `diagnosticador-dev-serving.spec.ts` (en 7527a24) | `docs/diagnosticador_embed_dev_serving_v1.md` |
| Gate 3C/3D | `b6f152c` | `3ae1258` | — |
| 4 | `847f37f`, `e17b60b`, `f4f6669` | (regresión protegida en stage-4 doc) | `5f66e3e` |
| 5 | `30119fa`, `40003e7` | `dcacbd8` | `1444cd3` |
| 6 | `a09aa4b` | `c20c2b7` | `e8ae093` |
| 7 | `a511be9` | `80085fe` | `0c7101e` |
| 8 | `8c9af41` | `67bdbac` | `a89924a` |

Gate 3D: ejecutado y cerrado como el commit de alineación del assertion del logo
(`3ae1258`), confirmado por el HEAD inicial del documento Stage 4.

## 5. Rutas migradas

| Ruta | Stage | Componente principal | Variantes visuales | Funciones protegidas | E2E |
| --- | --- | --- | --- | --- | --- |
| `/w/[ws]/` | 3+4 | `ConsoleDashboard.svelte` | Card large/light/mini, AlertCard polimórfico | stats, links, derivaciones por audiencia | shell + stage3 + smoke visual |
| `/w/[ws]/clients` | 4 | `ConsoleSectionPage` (view=clients) | Card flat (mobile), Card large (tabla) | columnas, badges, wrapping | smoke visual |
| `/w/[ws]/reports` | 3+4 | `ReportsList.svelte` | Card flat/large, DataTable | columnas, acciones, empty state | stage3 |
| `/w/[ws]/alerts` | 3+4 | `AlertsList.svelte` + `AlertCard.svelte` | Card flat/large, AlertCard | severidad, acciones, agrupación | stage3 |
| `/w/[ws]/services` | 5 | `ServicesList.svelte` | Card large, StatCard | stats, badges, links a detalle | stage5 |
| `/w/[ws]/tasks` | 5 | `TasksList.svelte` | Card flat, stats panel | prioridad, estado, asignación | stage5 |
| `/w/[ws]/runs` | 5 | `RunsList.svelte` | Card flat, stats panel | guarda `technicalDepth`, estado | stage5 |
| `/w/[ws]/workers` | 5 | `WorkersList.svelte` | Card flat, stats panel | guarda `technicalDepth`, disponibilidad | stage5 |
| `/w/[ws]/organizations` | 6 | `ConsoleSectionPage` (view=organizations) | Card flat | datos solo lectura | stage6 |
| `/w/[ws]/partners` | 6 | `ConsoleSectionPage` (view=partners) | Card large | métricas clientes/workspaces | stage6 |
| `/w/[ws]/workspaces` | 6 | `ConsoleSectionPage` (view=workspaces) | Card flat | contexto, switcher | stage6 |
| `/w/[ws]/team` | 6 | `ConsoleSectionPage` (view=team) | Card flat | miembros, roles | stage6 |
| `/w/[ws]/settings` | 7 | `WorkspaceSettings.svelte` | Card large | contexto operativo, módulos, servicios | stage7 |
| `/w/[ws]/support` | 7 | `ConsoleSectionPage` (view=support) | Card large/mini/dark | email mailto, escalamiento | stage7 |
| `/w/[ws]/results` | 8 | `ConsoleSectionPage` (view=results) | Card flat | métricas, valores | stage8 |
| `/w/[ws]/services/[serviceId]` | 8 | `ServiceDetail.svelte` | Card large/flat/dark | 8 tabs, `?tab=`, refresh, back | stage8 |
| `/w/[ws]/diagnosis` | 3 | `ConsoleDiagnosis.svelte` | Button, Textarea, loading/error | binding, submit, clasificación (backend real) | diagnosis.spec |

Tabs reales de ServiceDetail (extraídas del código): `summary`, `results`,
`reports`, `alerts`, `tasks`, `history` (o "Historial y soporte" para
audiencia client), `configuration` (no-client), `technical` (owner/operator).

## 6. Componentes compartidos

| Componente | Props | Variantes | Consumidores | Accesibilidad | Riesgo |
| --- | --- | --- | --- | --- | --- |
| `Card` | children, title, tag, variant, class | default, large, flat, light, dark, mini | todas las pantallas | tag semántico | bajo |
| `SectionHeader` | eyebrow, title, description, actions, level | level 1/2 | casi todas | h1/h2 | bajo |
| `StatCard` | label, value, description, trend | — | Services, Dashboard | label + valor | bajo |
| `Badge` | children, variant, ariaLabel | neutral/primary/secondary/success/warning/info/danger | Dashboard, Clientes | texto de estado visible | medio |
| `StatusBadge` | status | estados semánticos | todas las listas | estado con texto | medio |
| `Alert` | children, variant | neutral/success/warning/info/danger | errores | `role=alert` | medio |
| `AlertCard` | kind, cardVariant, layout, showService, showWorkspace, noCard | alert/task/report | Dashboard, Alertas, ServiceDetail | badges semánticos | medio |
| `EmptyState` | title, description, nextStep, actions | compact | listas | — | bajo |
| `Loading` | label | — | Diagnosticador | `role=status` | bajo |
| `Button` | type, disabled, loading, variants, sizes | tamaños táctiles | formularios, acciones | `aria-busy` | alto (form) |
| `Select` | control nativo envuelto | — | Topbar, switchers | nombre accesible | alto |
| `Textarea` | bind:value + atributos nativos | — | ConsoleDiagnosis | aria-labelledby/describedby | alto |
| `DataTable` | columnas, acciones | región con aria-label | Reportes, Clientes | `scope=col`, teclado | medio |
| `Tabs` | tabs, activeTab, onChange | — | ServiceDetail | navegación por teclado | medio |
| `NotificationCenter` | open/close | — | Topbar | Escape, click externo, foco | alto |

## 7. Variantes visuales

- `Card`: `default`, `large`, `flat`, `light`, `dark`, `mini`.
- `dark` adoptada productivamente por primera vez en Stage 7 (Support escalamiento)
  y reutilizada en Stage 8 (ServiceDetail "Próximo paso"/soporte).
- Tokens: `--color-primary #168b88`, `--color-secondary rgba(9,35,62,1)`,
  `--color-base-content #123653`, `--color-card-border[-light|-mini]`,
  `--color-card-bg[-light|-dark]`, `--shadow-card-default|large`,
  `--color-console-title|subtitle|muted|brand`, `--font-poppins`.

## 8. Pruebas por stage

| Suite E2E | Casos | Resultado Stage 9 (con backend disponible) |
| --- | --- | --- |
| `console-shell.spec.ts` | 7 | PASS |
| `console-shared-components-stage3.spec.ts` | 5 | PASS |
| `console-operation-stage5.spec.ts` | 4 | PASS |
| `console-organization-stage6.spec.ts` | 5 | PASS |
| `console-settings-support-stage7.spec.ts` | 3 | PASS |
| `console-results-service-detail-stage8.spec.ts` | 3 | PASS |
| `public-vera.spec.ts` | 14 (12 + 2 skips preexistentes) | PASS (mock turn) |
| `t360-interaction-lab.spec.ts` | 1 | PASS |
| smoke visual 390/768/1280 × 16 rutas | 48 | PASS (tras fix overflow) |

Los tests que requieren backend real (`diagnosis.spec.ts`, contrato embed
`auth -> turn`, smoke real `/t360`) quedaron bloqueados en Stage 9 por la
caída ambiental de Milvus; se detalla en `status_actual.md`.

## 9. Superficies protegidas

- `/t360`, `PublicVeraEntry.svelte`, `global.js` (URLs): sin cambios.
- Loader, manifest, entry, SRI, CORS, allowed origins, URLs públicas: sin cambios.
- Backend, stores, rutas, auth, permisos, contratos, DEV/PRO: sin cambios.
- PostgreSQL, Milvus, LiteLLM: no iniciados, detenidos ni reiniciados por la
  migración UX.
- Cliente Mamamia360 y producción: no tocados.

## 10. Diferencias pendientes

- Aumento tipográfico integral del UX (`text-lg`/`text-base`) — diferido por
  densidad.
- Íconos SVG en stats panels (reloj, alerta).
- `CustomSelect` completo (solo wrapper del select nativo adoptado).
- Modales compartidos sin consumidor real.
- Localización integral del contenido interno de consola.
- Corrección aislada pendiente: ninguna en Stage 9 (la única regresión
  encontrada, overflow del dashboard, fue corregida).

## 11. Riesgos

- Regresión menor corregida en Stage 9: overflow horizontal de 19 px en
  dashboard 390 px (token de worker name + bump tipográfico). Fix `min-w-0` +
  `overflow-wrap:anywhere` con commit separado.
- La caída ambiental de Milvus impide validar los contratos reales
  `auth -> turn` y el smoke real `/t360` hasta que el servicio vuelva.
- El test `public-vera-mobile-sequential-blocks.spec.ts` conserva un flaky
  móvil preexistente (1/2).

## 12. Baseline final

- `pnpm check`: 0 errors, 0 warnings, 6 hints preexistentes.
- `pnpm build`: 146 pages.
- Console E2E: 27/27 PASS.
- Vera mock: 12/12 + 2 skips preexistentes; `:230` resuelto (comportamiento
  intencional, sin defecto).
- Smoke visual: 48/48 PASS (390/768/1280).
- LAT: 0 errores.
- Worktree final limpio; push no realizado.

## Recomendación del siguiente frente

Stage 10: polish visual final y localización integral de Console (o PASETO
Phase 1 en flujo separado de UX, según prioridad de negocio). Ninguna de las
dos líneas se inició dentro de Stage 9.

## Enlaces a documentos detallados

- `docs/ux/team360-console-design-handoff-stage-1-audit.md`
- `docs/ux/team360-console-design-handoff-stage-2-shell.md`
- `docs/ux/team360-console-design-handoff-stage-3-components.md`
- `docs/ux/team360-console-design-handoff-stage-4-screens.md`
- `docs/ux/team360-console-design-handoff-stage-5-operation.md`
- `docs/ux/team360-console-design-handoff-stage-6-organization.md`
- `docs/ux/team360-console-design-handoff-stage-7-settings-support.md`
- `docs/ux/team360-console-design-handoff-stage-8-results-service-detail.md`
- `SrvRestAstroLS_v1/docs/diagnosticador_embed_dev_serving_v1.md`
- `SrvRestAstroLS_v1/docs/status_actual.md` (sección Stage 9)
