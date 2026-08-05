# Stage 7 — Adaptación visual de Configuración y Soporte

## HEAD

| Campo | Valor |
|---|---|
| Rama | `feature/console-backend-core` |
| HEAD inicial | `e8ae093` (Stage 6 doc) |
| HEAD final | `80085fe` |
| Commits | 2: visual + test |
| Push | No |

## Baseline inicial

| Suite | Resultado |
|---|---|
| Shell E2E | 7/7 PASS |
| Etapa 3 E2E | 5/5 PASS |
| Operación E2E | 4/4 PASS |
| Organización E2E | 5/5 PASS |
| `pnpm check` | 0 errors |
| `pnpm build` | 146 pages |

## Inventario

| Pantalla | Componente | Tipo | Riesgo |
|----------|-----------|------|--------|
| **Support** | `ConsoleSectionPage` (view=support) | Read-only, links | Bajo |
| **Settings** | `WorkspaceSettings.svelte` | Read-only mock, sin formularios | Medio |

Settings es un componente independiente (`WorkspaceSettings.svelte`) con cards informativas de solo lectura: contexto operativo, módulos, servicios contratados e integraciones previstas. Sin formularios, submit ni persistencia real en el estado mock actual. Soporte está en `ConsoleSectionPage.svelte`.

## Comparación con UX (`a75909d`)

### Adoptado
- `Card variant="large"` para panel de solicitudes en Support (antes `section`)
- `Card variant="dark"` para panel de escalamiento en Support (antes `section bg-[#123653]`) — **primera adopción de la variante dark diferida desde Stage 4**
- `Card variant="mini"` para items de tareas en Support (antes `article`)
- `Card variant="large"` para las 4 cards de Settings (antes `article`)
- `text-sm` para títulos de tareas y contenido de settings

### Reinterpretado
- Tipografía contenida (no se usó `text-lg`/`text-base` del UX) para mantener densidad
- `SectionHeader` conservado en Settings
- Labels de sección con `text-xs font-bold uppercase tracking-[0.16em] text-[#168b88]` (no `top-badge` class)

### Descartado
- Sin `Badge` para módulos (se conservan `span` estilizados)
- Sin `Card variant="flat-large"` (se usó `large` que ya existe y es visualmente equivalente)

### Diferido
- Aumento tipográfico completo del UX

## Cambios

### Support
- Panel izquierdo: `section` → `Card variant="large"`, items `article` → `Card variant="mini"`
- Panel derecho: `section bg-[#123653]` → `Card variant="dark"`
- Link de email: más grande (`text-sm`)
- Email link: `BRAND.supportEmail` conservado de `global.js`

### Settings
- 4 cards: `article` → `Card variant="large"`
- `text-sm` para dl items, nombres de servicio, texto de nota
- Sin cambios en datos, bindings ni store

## Card variant="dark"

Primera adopción productiva en consola. Usada en el panel de escalamiento de Support:
- Fondo oscuro con texto blanco
- Label de sección en teal claro
- Badge de email en teal/bg-oscuro
- Contraste AA validado visualmente
- Sin impacto en otras pantallas (es variante explícita)

## E2E Stage 7

Archivo: `e2e/console-settings-support-stage7.spec.ts` — 3 tests:
1. Support: solicitudes, escalamiento, email mailto, mobile
2. Settings: contexto operativo, módulos, servicios, integraciones, mobile
3. Settings: valores coherentes (locale, direction reales)

## Regresión protegida final

| Suite | Resultado |
|---|---|
| Shell | 7/7 PASS |
| Etapa 3 | 5/5 PASS |
| Operación | 4/4 PASS |
| Organización | 5/5 PASS |
| Stage 7 | 3/3 PASS |
| Embed manifest/loader/entry | 6/6 PASS |
| SRI + cross-origin | 6/6 PASS |
| Mamamia360 | 6/6 PASS |
| **Total** | **42/42 PASS** |

## Comandos

| Comando | Resultado |
|---|---|
| `pnpm check` | 0 errors |
| `pnpm build` | 146 pages |
| `git diff --check` | PASS |

## Protección productiva

```
Cliente y producción: intactos  ✓
Loader, manifest, entry, SRI, CORS: intactos  ✓
Sin SSH, rsync, deploy, upload ni push  ✓
PostgreSQL, Milvus, LiteLLM: no alterados  ✓
```

## Diferencias pendientes

- Aumento tipográfico completo
- Adaptación de `ServiceDetail.svelte` y `results`
