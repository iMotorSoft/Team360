# Stage 6 — Adaptación visual de la familia Organización

## HEAD

| Campo | Valor |
|---|---|
| Rama | `feature/console-backend-core` |
| HEAD inicial | `1444cd3` (Stage 5 doc) |
| HEAD final | `c20c2b7` |
| Commits | 2: visual + test |
| Push | No |

## Baseline inicial

| Suite | Resultado |
|---|---|
| Shell E2E | 7/7 PASS |
| Etapa 3 E2E | 5/5 PASS |
| Operación E2E | 4/4 PASS |
| `pnpm check` | 0 errors, 0 warnings, 6 hints |
| `pnpm build` | 146 pages |

## Inventario Organización

| Ruta | Componente | Store | Datos | Riesgo |
|------|-----------|-------|-------|--------|
| `/w/[ws]/organizations` | `ConsoleSectionPage` (view=organizations) | `consoleContext` | `accessibleOrganizations`, `workspaces` | Bajo |
| `/w/[ws]/partners` | `ConsoleSectionPage` (view=partners) | `consoleContext` | `accessibleOrganizations` (type=partner) | Bajo |
| `/w/[ws]/workspaces` | `ConsoleSectionPage` (view=workspaces) | `consoleContext` | `accessibleWorkspaces` | Medio (contexto) |
| `/w/[ws]/team` | `ConsoleSectionPage` (view=team) | `consoleContext` | `users` (filtered) | Bajo |

Todas las pantallas son de solo lectura en el estado mock actual. Sin formularios de create/edit/delete ni mutaciones.

## Matriz de riesgo

- **Bajo**: organizations, partners, team — cards informativas, badges de estado, métricas, avatares. Sin acciones que muten datos.
- **Medio**: workspaces — toca `accessibleWorkspaces`, el workspace activo se cambia mediante `WorkspaceSwitcher` (componente independiente no modificado). La vista solo lista workspaces.

## Comparación con UX (`a75909d`)

### Adoptado
- `Card variant="flat"` para organizations, workspaces, team (antes `article`)
- `Card variant="large"` para partners (antes `article`)
- Tipografía ligeramente mayor: `text-sm` en lugar de `text-xs` para subtítulos y metadata
- Badge con `text-xs` en lugar de `text-[0.62rem]`

### Reinterpretado
- Tipografía contenida (no se subió a `text-lg`/`text-xl`/`text-2xl` como en UX) para mantener densidad
- `SectionHeader` conservado intacto
- Sin cambios en el header (eyebrow, title, description)

### Descartado
- Sin cambios en stores, contexto, navegación ni selectores
- Sin nuevos mocks ni roles

### Diferido
- Aumento tipográfico completo del UX
- Íconos o badges de rol diferenciados por color

## Cambios

| Pantalla | Cambio |
|----------|--------|
| **Organizations** | `article` → `Card variant="flat"`, text-sm type/metadata, badge text-xs |
| **Partners** | `article` → `Card variant="large"`, text-sm subtitle, badge text-xs |
| **Workspaces** | `article` → `Card variant="flat"`, text-sm org/metadata, badge text-xs |
| **Team** | `article` → `Card variant="flat" class="flex items-center gap-4 p-4"`, role text-xs |

## Contexto y permisos

- `WorkspaceSwitcher`: no modificado
- `ProfileSwitcher`: no modificado
- `consoleContext`: no modificado
- `buildConsoleRoute`: no modificado
- Workspace activo: preservado (validado vía E2E con workspace switcher)
- Roles y permisos: no alterados (solo lectura en todas las pantallas)

## E2E Organización

Archivo: `e2e/console-organization-stage6.spec.ts` — 5 tests:
1. Organizations: cards, nombre, tipo, estado, workspace count, mobile
2. Partners: métricas clientes/workspaces, mobile
3. Workspaces: nombre, organización, tipo/locale, mobile
4. Workspace switcher: cambio de contexto, URL, breadcrumb, refresh
5. Team: miembros, avatar, nombre, email, rol, mobile

## Regresión protegida final

| Suite | Resultado |
|---|---|
| Shell E2E | 7/7 PASS |
| Etapa 3 E2E | 5/5 PASS |
| Operación E2E | 4/4 PASS |
| Organización E2E | 5/5 PASS |
| Embed manifest/loader/entry | 6/6 PASS |
| SRI + cross-origin | 6/6 PASS |
| Mamamia360 | 6/6 PASS |
| **Total** | **39/39 PASS** |

## Comandos

| Comando | Resultado |
|---|---|
| `pnpm check` | 0 errors |
| `pnpm build` | 146 pages |
| `git diff --check` | PASS |

## Protección productiva

```
Cliente no tocado.  ✓   Producción no tocada.  ✓
Loader, manifest, entry intactos.  ✓
SRI, CORS, allowed origins intactos.  ✓
Sin SSH, rsync, deploy, upload ni push.  ✓
PostgreSQL, Milvus, LiteLLM: no alterados.  ✓
```

## Diferencias pendientes

- Aumento tipográfico completo (`text-lg`/`text-xl`/`text-2xl`)
- `Card variant="dark"` (sin caso semántico en Organización)
- Adaptación de `settings` y `support`
