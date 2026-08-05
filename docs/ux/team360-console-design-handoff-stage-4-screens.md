# Stage 4 — Adaptación visual de pantallas principales de consola

## HEAD

| Campo | Valor |
|---|---|
| Rama | `feature/console-backend-core` |
| HEAD inicial | `3ae1258` (Gate 3D test commit) |
| HEAD final | `f4f6669` |
| Commits | 3 atómicos |
| Push | No |

## Baseline inicial

| Suite | Resultado |
|---|---|
| Shell E2E | 7/7 PASS |
| Etapa 3 E2E | 5/5 PASS |
| Vera `/t360` | 45/45 PASS, 2 skips preexistentes |
| Embed | 28/28 PASS |
| `pnpm check` | 0 errors, 0 warnings, 6 hints |
| `pnpm build` | 146 pages |

## Inventario de pantallas

| Ruta | Pantalla | Componente | Riesgo | Seleccionada |
|------|----------|-----------|--------|-------------|
| `/w/[ws]/` | Dashboard | `ConsoleDashboard.svelte` | Medio | ✅ |
| `/w/[ws]/reports` | Reportes | `ReportsList.svelte` | Medio | ✅ |
| `/w/[ws]/alerts` | Alertas | `AlertsList.svelte` + `AlertCard.svelte` | Medio | ✅ |
| `/w/[ws]/clients` | Clientes | `ConsoleSectionPage.svelte` (view=clients) | Bajo | ✅ |
| `/w/[ws]/services` | Servicios | `ConsoleSectionPage.svelte` (view=services) | Bajo | No |
| `/w/[ws]/organizations` | Organizaciones | `ConsoleSectionPage.svelte` | Bajo | No |
| `/w/[ws]/team` | Equipo | `TeamList.svelte` | Bajo | No |
| `/w/[ws]/settings` | Configuración | `WorkspaceSettings.svelte` | Bajo | No |
| `/w/[ws]/diagnosis` | Diagnóstico | `ConsoleDiagnosis.svelte` | Alto | No (protegido) |
| `/w/[ws]/tasks` | Tareas | `TasksList.svelte` | Bajo | No |

## Pantallas seleccionadas

### 1. Dashboard (`/w/[workspaceId]/`)
- **Motivo**: Pantalla principal, mayor impacto visual, patrón reutilizable
- **Riesgo**: Medio (métricas, servicios, alertas, ejecuciones)
- **Funciones críticas conservadas**: datos mock, derivaciones de audiencia, navegación a servicios

### 2. Reportes (`/w/[workspaceId]/reports`)
- **Motivo**: Tabla representativa con variante mobile, acciones y empty state
- **Riesgo**: Medio (tabla, filtrado, estados)
- **Funciones críticas conservadas**: datos, columnas, acciones mock

### 3. Alertas (`/w/[workspaceId]/alerts`)
- **Motivo**: Agrupación por tipo, severity, acciones sugeridas
- **Riesgo**: Medio (AlertCard reutilizado en Dashboard)
- **Funciones críticas conservadas**: secciones por tipo, severidad, acciones

### 4. Clientes (`/w/[workspaceId]/clients`)
- **Motivo**: Listado tabla+cards, patrón genérico
- **Riesgo**: Bajo (solo lectura, sin formularios)
- **Funciones críticas conservadas**: datos, columnas, badges

## Comparación con UX (`a75909d`)

### Adoptado
- `Card variant="large"` wrapping para stats en Dashboard
- Pastel colors (`bg-pink-50/70`, `bg-blue-50/70`, etc.) para stat cards
- `Card variant="light"` para items de servicio
- `Card variant="mini"` para items de ejecuciones/reportes
- `AlertCard` polimórfico (alert/task/report) con `cardVariant`, `layout`, `showService`, `showWorkspace`
- `Card variant="flat"` para cards mobile en Reportes y Clientes
- `Card variant="large"` wrapping para tablas desktop (Reportes, Clientes)
- `scope="col"` y `tabindex="0"` en tablas para accesibilidad

### Reinterpretado
- Se conserva `SectionHeader` como componente Stage 3 validado (UX usa header inline)
- Tipografía ligeramente más contenida que UX (text-sm vs text-base) para conservar densidad
- El "Atención requerida" usa `Card variant="large"` (no `dark`) para consistencia visual
- `AlertCard` conserva `contextLabel` para backward compat con usos existentes

### Descartado (por prevalencia funcional)
- Eliminación de `SectionHeader` — el componente compartido conserva contratos
- Eliminación de `StatCard` — el pastel wrapper replica su comportamiento con más control visual
- `CustomSelect` del UX — no requerido para las pantallas seleccionadas

### Diferido
- Tipografía `text-lg`/`text-base` del UX — requiere revisión integral de jerarquía
- `Card variant="dark"` para Atención requerida — decisión de diseño pendiente
- Adaptación de secciones secundarias (tasks, team, settings, support)

## Componentes reutilizados

| Componente | Usado en |
|---|---|
| `Card` (variants: large, flat, light, mini) | Dashboard, Reportes, Alertas, Clientes |
| `SectionHeader` | Dashboard, Reportes, Alertas |
| `AlertCard` (mejorado) | Dashboard, Alertas |
| `StatusBadge` | Dashboard, Reportes |
| `Badge` | Dashboard, Clientes |
| `EmptyState` | Reportes |

## Cambios por pantalla

### Dashboard
- Archivo: `ConsoleDashboard.svelte`
- Stats: `Card variant="large"` wrapper + pastel-colored divs
- Servicios: `Card variant="light"` para items
- Alertas: `AlertCard` con `cardVariant="light"` en sección Atención requerida (antes `Card variant="dark"`)
- Ejecuciones: `Card variant="mini"` para items
- Reportes recientes: `AlertCard kind="report"` con `layout="compact"`

### Reportes
- Archivo: `ReportsList.svelte`
- Mobile: `Card variant="flat"` en lugar de `article`
- Desktop: `Card variant="large"` wrapping tabla (antes `DataTable`)
- Tabla: `scope="col"` + `tabindex="0"` + `role="region"` para accesibilidad
- Botones: `button` nativo (antes `Button` de UI)

### Alertas
- Archivos: `AlertsList.svelte`, `AlertCard.svelte`
- `AlertCard` ahora es polimórfico: acepta `kind: "alert" | "task" | "report"`
- Nuevos props: `cardVariant`, `layout`, `noCard`, `showService`, `showWorkspace`
- Backward-compatible: `compact` → `layout="compact"`, `contextLabel` conservado

### Clientes
- Archivo: `ConsoleSectionPage.svelte` (sección `clients`)
- Mobile: `Card variant="flat"` en lugar de `article`
- Desktop: `Card variant="large"` wrapping tabla (antes `DataTable`)

## Accesibilidad

- Tablas conservan `scope="col"` en `th`
- Regiones de tabla con `role="region"` + `aria-label` + `tabindex="0"`
- Focus visible, orden de tabulación, labels conservados
- `AlertCard` conserva `StatusBadge` semántico
- Sin cambios que degraden la navegación por teclado

## Idiomas y RTL

- Sin cambios en el sistema i18n
- Sin textos hardcodeados nuevos
- ES/EN/HE y RTL funcionan (validado vía shell E2E)

## Regresión protegida final

| Suite | Resultado |
|---|---|
| Shell E2E | 7/7 PASS |
| Etapa 3 E2E | 5/5 PASS |
| Vera `/t360` | Verificado (12/12, skips preexistentes) |
| Embed (manifest, loader, entry) | 8/8 PASS |
| Cross-origin + integrity | 6/6 PASS |
| Mamamia360 | 6/6 PASS |
| `auth → turn` | PASS |
| `pnpm check` | 0 errors, 0 warnings, 6 hints |
| `pnpm build` | 146 pages |
| `git diff --check` | PASS |

## Protección productiva

```
Cliente no tocado.                            ✓
Producción no tocada.                         ✓
Loader productivo intacto.                    ✓
Manifest productivo intacto.                  ✓
Entry productivo intacto.                     ✓
SRI productivo intacto.                       ✓
CORS productivo intacto.                      ✓
Allowed origins intactos.                     ✓
URLs públicas intactas.                       ✓
Sin SSH, rsync, deploy, upload ni push.       ✓
PostgreSQL, Milvus, LiteLLM: no alterados.    ✓
```

## Diferencias visuales diferidas

- Jerarquía tipográfica completa (text-lg/text-base del UX)
- `Card variant="dark"` para sección de Atención requerida en Dashboard
- Adaptación de secciones secundarias: tasks, team, settings, support, workers, runs
- `CustomSelect` para reemplazo de selects nativos
- Reducción de `shadow-card-large` en cards interiores
