# Frontend Team360 Console - Mock context e i18n base

Estado: implementado como base funcional de diseño sin backend.

Fecha: 2026-05-31.

## Objetivo

Preparar una base concreta para diseñar pantallas reales de `console.team360.live` sin esperar autenticación, API, DB ni AG-UI funcional.

La fase materializa:

- configuración frontend centralizada;
- datos mock multi-organización;
- bootstrap por perfil;
- contexto compartido Svelte 5 con Runes;
- i18n liviano para español, inglés y hebreo;
- dirección de texto preparada para `ltr` y `rtl`.

No implementa App Shell visual, dashboards renderizados ni rutas privadas.

## Configuración global

Se creó `astro/src/components/global.js` como equivalente limpio del patrón usado en Vertice360.

Centraliza:

- `APP_NAME`;
- `APP_PUBLIC_NAME`;
- `PUBLIC_SITE_URL`;
- `CONSOLE_SITE_URL`;
- `API_BASE_URL`;
- `AGUI_BASE_URL`;
- `DEFAULT_LOCALE`;
- `SUPPORTED_LOCALES`;
- `LOCALE_DIRECTION`;
- `DEFAULT_DIRECTION`;
- `IS_MOCK_MODE`;
- `MOCK_ACTIVE_PROFILE`;
- `BRAND`;
- `ROUTES`.

`global.d.ts` acompaña el módulo runtime para conservar tipado estricto al consumirlo desde TypeScript.

No contiene secretos, tokens, passwords ni credenciales.

## Mock data

La carpeta `astro/src/lib/mock/` separa fixtures tipados por dominio:

```text
alerts.ts
bootstrap.ts
dashboards.ts
index.ts
organizations.ts
reports.ts
runs.ts
services.ts
tasks.ts
users.ts
workspaces.ts
```

Incluye:

- Team360 como organización raíz;
- cliente directo;
- partners configurables;
- clientes de partner;
- workspaces propios y delegados;
- servicios visibles para cliente e internos;
- reportes;
- alertas;
- tareas;
- ejecuciones técnicas;
- cards de dashboard.

`Mamá Mía 360` aparece como primer dato mock de partner regional para Israel. No existe branching por nombre, región o posición dentro del producto.

## Bootstrap mock

`astro/src/lib/mock/bootstrap.ts` exporta:

```ts
getMockBootstrap(profile, workspaceId?)
getMockProfiles()
getMockWorkspaceContext(workspaceId, options?)
```

Perfiles disponibles:

| Perfil | Alcance |
| --- | --- |
| `team360_admin` | Red completa, profundidad técnica y cambio entre todos los workspaces |
| `team360_operator` | Operación asignada, servicios, workers y ejecuciones permitidas |
| `team360_support` | Contextos delegados, estados visibles, reportes y soporte |
| `partner_admin` | Organización partner y clientes descendientes autorizados |
| `client_admin` | Única empresa y workspace propios, sin workers técnicos |

El bootstrap devuelve:

```text
currentUser
activeMembership
accessibleOrganizations
accessibleWorkspaces
activeOrganization
activeWorkspace
effectivePermissions
enabledModules
contractedServices
authorizedTree
notificationSummary
featureFlags
uiHints
aguiCapabilities
```

Reglas aplicadas:

- el cambio de workspace valida el scope del perfil;
- partner no ve clientes directos ni otros partners;
- cliente no ve workspaces ajenos;
- servicios internos quedan fuera de perfiles de negocio;
- runs técnicos se entregan solo cuando se solicitan explícitamente;
- AG-UI se declara deshabilitado.

## Contexto Svelte 5

Se creó `astro/src/stores/consoleContext.svelte.ts`.

Usa Runes para mantener:

- perfil mock activo;
- bootstrap actual;
- locale;
- direction;
- organización activa;
- workspace activo;
- permisos efectivos;
- servicios contratados;
- resumen de notificaciones.

Al cambiar workspace, reconstruye el bootstrap mock para descartar datos del contexto anterior.

## i18n y RTL

La carpeta `astro/src/lib/i18n/` contiene:

```text
index.ts
locales.ts
messages.es.ts
messages.en.ts
messages.he.ts
```

Expone:

```ts
t(key, locale)
getDirection(locale)
SUPPORTED_LOCALES
DEFAULT_LOCALE
```

Español es el idioma inicial. Inglés y hebreo tienen un conjunto básico de traducciones para validar estructura. Hebreo resuelve `rtl`; la adaptación visual completa queda para una fase posterior del App Shell.

## Límites

No se implementaron:

- App Shell visual;
- dashboards renderizados;
- autenticación;
- autorización frontend real;
- API;
- backend;
- DB;
- migraciones;
- AG-UI o SSE funcional;
- librerías nuevas;
- cambios en la home pública.

## Validación

Desde `SrvRestAstroLS_v1/astro/`:

```bash
corepack pnpm check
corepack pnpm build
```

Desde la raíz del repo:

```bash
git diff --check -- SrvRestAstroLS_v1/astro SrvRestAstroLS_v1/docs docs/frontend
find SrvRestAstroLS_v1/astro -maxdepth 2 \( -name package-lock.json -o -name yarn.lock \) -print
```

Resultado:

- `astro check`: `0 errors`, `0 warnings`, `0 hints`;
- build estático: OK, una ruta existente `/index.html`;
- `git diff --check` acotado: OK;
- búsqueda de whitespace final en archivos agregados: sin hallazgos;
- sin `package-lock.json`;
- sin `yarn.lock`;
- sin secretos en la capa mock;
- sin integración backend ni DB.
