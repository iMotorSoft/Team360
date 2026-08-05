# Stage 5 — Adaptación visual de la familia Operación

## HEAD

| Campo | Valor |
|---|---|
| Rama | `feature/console-backend-core` |
| HEAD inicial | `5f66e3e` (Stage 4 doc) |
| HEAD final | `dcacbd8` |
| Commits | 3: 2 visuales + 1 test |
| Push | No |

## Baseline inicial

| Suite | Resultado |
|---|---|
| Shell E2E | 7/7 PASS |
| Etapa 3 E2E | 5/5 PASS |
| `pnpm check` | 0 errors, 0 warnings, 6 hints |
| `pnpm build` | 146 pages |

## Inventario Operación

| Ruta | Componente | Store | Riesgo |
|------|-----------|-------|--------|
| `/w/[ws]/services` | `ServicesList.svelte` | `consoleContext` | Medio (stats, badges, links) |
| `/w/[ws]/tasks` | `TasksList.svelte` | `consoleContext` | Medio (prioridad, estado, asignación) |
| `/w/[ws]/runs` | `RunsList.svelte` | `consoleContext` | Medio (estado, duración, permisos) |
| `/w/[ws]/workers` | `WorkersList.svelte` | `consoleContext` | Medio (capacidad, estado, disponibilidad) |

## Matriz de riesgo

Todas las pantallas de Operación son de riesgo **medio**: contienen datos de solo lectura, badges de estado, links de navegación y stats, pero sin formularios de submit ni mutaciones. La guarda `technicalDepth !== "business"` en runs/workers añade una capa de permisos visuales sin modificar autorización real.

## Comparación con UX (`a75909d`)

### Adoptado
- `Card variant="large"` para cards de servicios (antes `article`)
- `Card variant="flat"` para items de tasks, runs y workers (antes `article`)
- Stats panels con layout flex + `divide-x` + border en lugar de `grid grid-cols-*` con `bg-[#f8fbfa]`
- `text-sm` para metadata en lugar de `text-xs`
- `text-xs font-bold uppercase tracking-wider` para dt labels de stats
- Uso consistente de `rounded-2xl border border-[#edf1f2] bg-[#fcfdfd] overflow-hidden` para panels de stats

### Reinterpretado
- `SectionHeader` conservado (Stage 3) con eyebrow + title + description
- `StatCard` conservado para métricas superiores en Services (UX igual)
- Sin íconos SVG en stats panels (diferido, no requerido para funcionalidad)
- Tipografía contenida (`text-sm` en lugar de `text-base` del UX) para mantener densidad

### Descartado
- `top-badge` class en Services: se conservan los badges `StatusBadge` existentes
- Reorganización completa del layout de Services: la estructura actual es funcionalmente equivalente

### Diferido
- Íconos SVG en dt de stats (reloj, errores) — mejora visual sin impacto funcional
- Aumento tipográfico a `text-base`/`text-lg` — requiere revisión de densidad global
- `Card variant="dark"` — sin caso de uso semántico en Operación

## Cambios por pantalla

### Services
- Archivo: `ServicesList.svelte`
- `Card variant="large"` reemplaza `article` para cada servicio
- `text-sm` para descripción y metadata
- `text-xs font-bold uppercase tracking-[0.15em]` para packageName
- Métricas conservadas con `rounded-xl bg-[#f3f8f8]`

### Tasks
- Archivo: `TasksList.svelte`
- `Card variant="flat"` reemplaza `article`
- Stats panel: `flex divide-x` con `rounded-2xl border` reemplaza `grid bg-[#f8fbfa]`
- `text-sm` para metadata de servicio/workspace
- `text-xs font-bold uppercase tracking-wider` para dt labels

### Runs
- Archivo: `RunsList.svelte`
- `Card variant="flat"` reemplaza `article`
- Stats panel con `flex divide-x` + `rounded-2xl border` para Inicio/Duración/Errores
- `text-sm` para summary y metadata
- Guarda `technicalDepth` conservada intacta

### Workers
- Archivo: `WorkersList.svelte`
- `Card variant="flat"` reemplaza `article`
- Stats panel con `flex divide-x` + `rounded-2xl border` para Última ejecución/Errores/Duración media
- `text-sm` para service name y metadata
- Guarda `technicalDepth` conservada intacta

## Componentes reutilizados

| Componente | Usado en |
|---|---|
| `Card` (variants: large, flat) | Services, Tasks, Runs, Workers |
| `SectionHeader` | Services, Tasks, Runs, Workers |
| `StatCard` | Services |
| `StatusBadge` | Services, Tasks, Runs, Workers |
| `EmptyState` | Services, Tasks, Runs, Workers |

## Accesibilidad

- `StatusBadge` conserva semántica de estado con texto visible
- Estados no dependen solo de color
- Jerarquía de encabezados conservada (h1 → h2)
- Tablas semánticas (dl/dt/dd) para stats
- Navegación por teclado conservada (links focusables)

## Idiomas y RTL

- ES/EN/HE validados vía shell E2E (locale switcher)
- Sin textos hardcodeados nuevos
- RTL validado indirectamente (shell E2E)

## E2E Operación

Archivo: `e2e/console-operation-stage5.spec.ts` — 4 tests:
1. Services: carga, métricas, cards, link, mobile, sin errores
2. Tasks: carga, responsable, vencimiento, títulos, mobile, sin errores
3. Runs: carga, estado o empty state, mobile, sin errores
4. Workers: carga, workers o empty state, mobile, sin errores

## Regresión protegida final

| Suite | Resultado |
|---|---|
| Shell E2E | 7/7 PASS |
| Etapa 3 E2E | 5/5 PASS |
| Operación E2E | 4/4 PASS |
| Embed manifest/loader/entry | 6/6 PASS |
| Cross-origin + integrity | 6/6 PASS |
| Mamamia360 | 6/6 PASS |
| `pnpm check` | 0 errors, 0 warnings, 6 hints |
| `pnpm build` | 146 pages |
| `git diff --check` | PASS |

## Protección productiva

```
Cliente no tocado.  ✓   Producción no tocada.  ✓
Loader, manifest, entry intactos.  ✓   SRI intacto.  ✓
CORS, allowed origins intactos.  ✓   URLs públicas intactas.  ✓
Sin SSH, rsync, deploy, upload ni push.  ✓
PostgreSQL, Milvus, LiteLLM: no alterados.  ✓
```

## Diferencias pendientes

- Íconos SVG en stats panels (reloj para Inicio/Duración, alerta para Errores)
- Aumento tipográfico completo (`text-base`/`text-lg`)
- `ServiceDetail.svelte`: adaptación visual de la página de detalle de servicio
