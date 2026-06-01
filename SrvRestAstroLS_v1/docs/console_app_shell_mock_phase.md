# Frontend Team360 Console - App Shell navegable con mock data

Estado: implementado como primera versión navegable de diseño sin backend.

Fecha: 2026-05-31.

## Objetivo

Construir la primera experiencia navegable de `console.team360.live` sobre la base mock de la fase anterior.

La implementación permite revisar visualmente tres experiencias:

- Team360 Admin;
- Partner / Distribuidor;
- Cliente Final.

No implementa auth real, backend, DB, migraciones ni AG-UI funcional.

## App Shell

Se creó `astro/src/layouts/ConsoleAppLayout.astro` como layout privado mock separado de `PublicMarketingLayout.astro`.

El shell Svelte principal vive en:

```text
astro/src/components/console/AppShell.svelte
```

Incluye:

- sidebar contextual;
- topbar;
- switcher de perfil mock;
- switcher de workspace;
- breadcrumbs;
- banner de contexto propio o delegado;
- centro de notificaciones;
- área principal;
- panel lateral de pendientes y reportes;
- soporte inicial `dir=ltr|rtl`.

## Componentes creados

```text
astro/src/components/console/
├── AppShell.svelte
├── Breadcrumbs.svelte
├── ConsoleIcon.svelte
├── ConsoleSectionPage.svelte
├── ContextBanner.svelte
├── NotificationCenter.svelte
├── ProfileSwitcher.svelte
├── Sidebar.svelte
├── Topbar.svelte
├── WorkspaceSwitcher.svelte
└── dashboard/
    └── ConsoleDashboard.svelte
```

`ProfileSwitcher` está rotulado como herramienta mock de diseño. No representa login ni impersonation productivo.

## Navegación declarativa

Se creó:

```text
astro/src/lib/navigation/registry.ts
astro/src/lib/navigation/derive.ts
```

La navegación visible se deriva desde:

- tipo de organización activa;
- permisos efectivos;
- módulos habilitados;
- workspace activo;
- servicios contratados;
- audiencia inferida desde capacidades.

No se crean consolas separadas por rol. No hay branching por nombre de partner.

### Team360 Admin

- Inicio
- Organizaciones
- Partners
- Clientes
- Workspaces
- Servicios
- Workers
- Ejecuciones
- Reportes
- Alertas
- Tareas
- Usuarios
- Configuración

### Partner

- Inicio
- Mis clientes
- Servicios
- Servicios de clientes
- Resultados
- Reportes
- Alertas
- Tareas
- Equipo
- Soporte
- Configuración

### Cliente

- Inicio
- Servicios contratados
- Resultados
- Reportes
- Alertas
- Tareas
- Equipo
- Soporte
- Configuración

## Dashboard

`ConsoleDashboard.svelte` adapta copy, KPIs y profundidad según capacidades:

- Team360 Admin observa red, partners, clientes, servicios, runs y alertas.
- Partner observa clientes propios, servicios, reportes, alertas y tareas.
- Cliente observa prestaciones contratadas, reportes, pendientes y próximos pasos en lenguaje operativo.

## Rutas

Rutas principales:

```text
/w/[workspaceId]
/w/[workspaceId]/services
/w/[workspaceId]/reports
/w/[workspaceId]/alerts
/w/[workspaceId]/tasks
/w/[workspaceId]/team
/w/[workspaceId]/settings
/w/[workspaceId]/organizations
/w/[workspaceId]/partners
/w/[workspaceId]/clients
/w/[workspaceId]/workers
/w/[workspaceId]/runs
```

Rutas adicionales para evitar navegación rota:

```text
/w/[workspaceId]/workspaces
/w/[workspaceId]/client-services
/w/[workspaceId]/results
/w/[workspaceId]/support
```

Todas se generan estáticamente para los workspaces mock mediante `getWorkspaceStaticPaths()`.

## Descripción visual

Wireframe materializado:

```text
+-----------------------------------------------------------------------+
| Sidebar premium      | Topbar: perfil, contexto, locale, alertas      |
|                      +------------------------------------------------+
| perfil mock          | Breadcrumbs                                    |
| workspace            | Banner de contexto propio o delegado           |
| navegación derivada  +----------------------------------+-------------+
|                      | Dashboard o vista principal      | Resumen     |
| modo diseño          | cards, listas, tablas, estados   | lateral     |
+----------------------+----------------------------------+-------------+
```

La estética mantiene relación con `team360.live`: azul profundo, acento teal, superficies claras, cards suaves, jerarquía B2B y complejidad técnica progresiva.

## i18n y RTL

- El shell aplica `dir` desde `consoleContext.direction`.
- Sidebar usa `t()` para navegación y grupos.
- Topbar permite alternar `es`, `en` y `he`.
- Hebreo activa `rtl`; la revisión visual exhaustiva RTL queda pendiente.

## Límites

- Mock data no es lógica definitiva.
- Las rutas privadas son accesibles sin auth solo para diseño local.
- No existe API real.
- No existe persistencia.
- No se ejecutan acciones reales.
- No existe transporte AG-UI/SSE.
- Ocultar navegación no representa autorización backend.

## Validación

Ejecutado desde `SrvRestAstroLS_v1/astro/`:

```bash
corepack pnpm check
corepack pnpm build
corepack pnpm dev --host 127.0.0.1 --port 4321
```

Resultado:

- `astro check`: `0 errors`, `0 warnings`, `0 hints`;
- build estático: OK;
- páginas generadas: `97`;
- smoke HTTP local: `200` para home, Admin, Partner, Cliente y rutas internas;
- smoke Chrome headless local: contenido hidratado diferenciado para Admin, Partner, Cliente y Reportes Cliente;
- `agent-browser` no estaba instalado; no se instaló ninguna herramienta.

Auditorías:

```bash
git diff --check -- SrvRestAstroLS_v1/astro SrvRestAstroLS_v1/docs docs/frontend
find SrvRestAstroLS_v1/astro -maxdepth 2 \( -name package-lock.json -o -name yarn.lock \) -print
```

Resultado:

- sin errores de whitespace;
- sin `package-lock.json`;
- sin `yarn.lock`;
- sin referencias Vertice360 en la nueva consola;
- sin fetch, SSE, WebSocket, auth o backend real;
- sin perfiles temporales del smoke;
- `Mamá Mía 360` permanece únicamente como fixture mock configurable.

## Pendientes

- Diseñar vista detalle de servicio.
- Revisar mobile con captura visual dedicada.
- Revisar RTL visual completo.
- Incorporar empty states ilustrados y skeletons.
- Reemplazar bootstrap mock por contrato backend cuando exista auth y autorización reales.
