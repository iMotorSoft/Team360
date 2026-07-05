# Status actual - Team360

Objetivo: `desarrollo`

Ultima actualizacion: 2026-07-03 (Fase 10A — guia externa de instalacion + handoff interno para cliente tecnico)

Este documento es un tablero del estado vigente. La bitacora detallada previa, incluidas las fases actuales aun sin commit, se conserva en `status_historico_hasta_2026-06-28.md` y en Git.

## Directorio y rama

- raiz: `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360`
- rama funcional actual: `feature/console-backend-core`
- las Fases 3 a 5 del Diagnosticador embebible quedaron confirmadas en `cdd1b1b` y publicadas en `origin/feature/console-backend-core`

## Estado general

- Team360 mantiene frontend Astro 6 + Svelte 5 y backend Litestar.
- PostgreSQL 18 es la verdad operacional del estado conversacional.
- Milvus 2.6 es el indice vectorial derivado para retrieval.
- El benchmark Milvus 2.6 vs. pgvector ya fue ejecutado y versionado en `804547d` (`feature/knowledge-ingestion-service`): ambos obtuvieron 44,0% de pass rate, mientras Milvus promedio 13,9 ms frente a 859,2 ms de pgvector (~61,8x; 98,4% menos latencia). No debe volver a figurar como pendiente salvo que cambien corpus, escala o condiciones de prueba.
- LiteLLM es el gateway de modelos mediante aliases y adapters.
- El runtime publico de Vera usa `/t360 -> Litestar -> PostgreSQL -> Milvus -> LiteLLM`.
- Las migraciones `001` a `004` y la Fase 1 de `automation_diagnosis` fueron validadas anteriormente.
- La politica DB vigente exige `psycopg 3 async`, pools separados y SQL dentro de repositories.

Referencias canonicas:

- `lat.md/team360-runtime-operational-policy.md`
- `lat.md/postgres-driver-policy.md`
- `lat.md/service-preflight-methodology.md`
- `lat.md/diagnosticador-embeddable-component-architecture.md`

## Trabajo anterior - Diagnosticador embebible

Estado: Fases 1 a 5 implementadas; confirmadas en `cdd1b1b`.

## Trabajo actual - Separacion factibilidad/implementacion

Estado: Fase 7 a 9A implementadas y confirmadas en `15e3e98`. Fases 9B, 9C, 9D,
9E, 9C-ext, 9D-ext y 9F implementadas y validadas en este worktree.

## Fase 10A — Guía externa de instalación + paquete mínimo para cliente técnico PHP/WordPress/HTML

Estado: CLIENT INSTALLATION GUIDE IMPLEMENTADO Y VALIDADO.

### Decisión técnica

- Se crea documentación externa clara para clientes técnicos sin requerir
  plug-and-play absoluto.
- El formato de entrega es `div + script + clientId + origin autorizado`,
  compatible con HTML estático, PHP, WordPress y builders.
- No se crea package npm, Web Component ni plugin WordPress productivo en esta
  fase.
- El cliente técnico recibe solo `clientId` público, snippet recomendado y guía
  de troubleshooting.
- `hmac_secret`, tenant/scope, `allowed_origins` se administran server-side.
- `global.js` no fue modificado.
- `/t360` y `PublicVeraEntry.svelte` no fueron modificados.

### Implementación

Documentos creados:

- `docs/diagnosticador_embed_installation_guide_v1.md` — guía externa completa
  con snippets recomendado, simple, HTML, PHP, WordPress bloque HTML,
  shortcode/plugin mínimo conceptual, parámetros permitidos/prohibidos,
  troubleshooting, checklist cliente, checklist Team360.
- `docs/diagnosticador_embed_client_handoff_v1.md` — handoff interno
  comercial/técnico con flujo de alta, criterio de "listo para cliente" y
  referencias.

Documentos actualizados:

- `docs/diagnosticador_external_integrity_snippet_v1.md` — referencia cruzada
  a la guía de instalación.
- `docs/status_actual.md` — esta sección.
- `lat.md/status_actual.md` — sección equivalente.

### Contenido de la guía de instalación

- snippet recomendado con integrity;
- snippet simple compatible;
- HTML estático completo;
- PHP tradicional;
- WordPress bloque HTML;
- shortcode/plugin mínimo conceptual;
- tabla de parámetros permitidos;
- lista de parámetros prohibidos;
- flujo de alta de cliente;
- troubleshooting;
- checklist técnico del cliente;
- checklist Team360.

### Contenido del handoff interno

- qué se entrega al cliente;
- qué NO se entrega;
- flujo de alta;
- mensaje breve para técnico del cliente;
- criterio de "listo para cliente".

### Validación 10A

| Validación | Resultado |
| ---------- | --------- |
| `git diff --check` | PASS |
| `pnpm check` | PASS |
| `pnpm build` | PASS |
| Secret/no-leak search | PASS — sin secretos reales ni códigos internos en snippets |
| Protección `/t360` | Sin diff |
| Protección `PublicVeraEntry.svelte` | Sin diff |
| Protección `global.js` | Sin diff |

Servicios permanentes no reiniciados: PostgreSQL, Milvus, LiteLLM.

### Seguridad

- `clientId` tratado como público.
- Sin `hmac_secret` real en documentación.
- Sin `organization_code`, `workspace_code`, `package_code`,
  `knowledge_scope_code`, `assistant_instance_code` en snippets públicos.
- `allowed_origins` no expuesto como editable por cliente.
- Parámetros prohibidos documentados explícitamente.

### Compatibilidad

- HTML estático.
- PHP tradicional.
- WordPress bloque HTML.
- WordPress shortcode/plugin mínimo conceptual.
- Gutenberg, Elementor, Divi, builders similares (con advertencia de
  optimizadores).
- Limitación conocida: plugins de seguridad/minificación/caché pueden alterar
  scripts.

### Deuda restante documentada

- package npm.
- Web Component nativo.
- CSS encapsulado final.
- Eventos públicos `t360:*` definitivos.
- Plugin WordPress productivo completo.
- Publicación en marketplace.
- UI/admin para `embed_clients`.
- E2E móvil flaky.
- Deuda LAT preexistente.

## Fase 9I — sync automatizado de loaderIntegrity en snippets/fixtures

Estado: IMPLEMENTADO Y VALIDADO. MCP limitado; gate efectivo con Playwright
CLI sobre runtime fallback local.

### Decision tecnica

- se elige Opcion C minima:
  - fixture literal sincronizado por script;
  - test anti-drift contra `manifest.loaderIntegrity`;
- la fuente de verdad queda en
  `astro/public/embed/team360-diagnosticador.manifest.json`;
- no cambia la API publica:
  - `window.Team360DiagnosticadorLoader.load()`;
  - `window.Team360Diagnosticador.mount(...)`;
- `entryIntegrity` se valida como prerequisito del sync, pero no se copia al
  host;
- el fixture 9H deja de depender del placeholder
  `__TEAM360_LOADER_INTEGRITY__` inyectado por el spec.

### Implementacion

- helper nuevo:
  `astro/scripts/sync-embed-integrity-snippets.mjs`;
- fixture literal sincronizado:
  `astro/e2e/fixtures/cross-origin-host/t360-cross-origin-integrity-loader.html`;
- spec endurecido:
  `e2e/diagnosticador-cross-origin-integrity-loader-fixture.spec.ts`;
- documentacion actualizada:
  - `docs/diagnosticador_external_integrity_snippet_v1.md`;
  - `docs/diagnosticador_loader_distribution_v1.md`;
  - `docs/diagnosticador_loader_integrity_v1.md`;
  - `docs/diagnosticador_loader_integrity_enforcement_v1.md`.

### Validacion 9I

Preflight:

- Git limpio al inicio: PASS.
- Runtime local:
  - `backend-dev.sh`: PASS;
  - fallback estatico local sobre `astro/dist` en `3050` con proxy `/api` a
    `127.0.0.1:7050`: PASS.

Backend:

- `uv run pytest tests/test_diagnosis_public_router.py tests/test_embed_clients_contract.py`:
  `83/83 PASS`.
- `uv run pytest tests/ -x --ignore=tests/test_db_module.py`:
  `1089 PASS, 9 skipped`.

Frontend:

- `pnpm check`: `0 errors`, `0 warnings`, `5 hints`.
- `pnpm build`: `146 pages`.
- helpers:
  - `node scripts/update-embed-integrity.mjs`: PASS;
  - `node scripts/sync-embed-integrity-snippets.mjs`: PASS.

Playwright CLI local (`PLAYWRIGHT_BASE_URL=http://127.0.0.1:3050`):

- `e2e/diagnosticador-cross-origin-integrity-loader-fixture.spec.ts`:
  `4 PASS`.
- `loader-integrity fixture + manifest + cross-origin + browser + mount + external + embed`:
  `16 PASS`.
- suite focalizada con Vera/lab/embed/external/mount/loader/fixture/manifest:
  `30 PASS, 2 skipped`.

Seguridad:

- fixture/snippet sincronizado no contiene `hmac_secret`;
- fixture/snippet sincronizado no contiene tenant, scope ni
  `allowed_origins`;
- `/t360`, `PublicVeraEntry.svelte` y `global.js` siguen fuera del diff.

## Fase 9H — fixture externo E2E con loaderIntegrity + verifyEntryIntegrity

Estado: IMPLEMENTADO Y VALIDADO. MCP limitado; gate efectivo con Playwright
CLI sobre runtime fallback local.

### Decision tecnica

- se crea fixture nuevo dedicado, sin reemplazar el fixture cross-origin
  default;
- el host recomendado usa `loaderIntegrity` en el `<script>` remoto;
- el host recomendado usa `crossorigin="anonymous"` en ese `<script>`;
- el loader resuelve el manifest default relativo a su propio `src`, por lo que
  el snippet externo puede omitir `manifestUrl`;
- el host recomendado activa `load({ verifyEntryIntegrity: true })`;
- el entry dinamico sigue usando `entryIntegrity` + `crossorigin="anonymous"`;
- `loaderIntegrity` invalido bloquea antes de `auth/turn`;
- `entryIntegrity` invalido rechaza antes de mount.

### Implementacion

- loader actualizado:
  `astro/public/embed/team360-diagnosticador-loader.js`;
- manifest actualizado:
  `astro/public/embed/team360-diagnosticador.manifest.json`;
- fixture nuevo:
  `astro/e2e/fixtures/cross-origin-host/t360-cross-origin-integrity-loader.html`;
- spec nuevo:
  `e2e/diagnosticador-cross-origin-integrity-loader-fixture.spec.ts`;
- documentacion nueva:
  `docs/diagnosticador_external_integrity_snippet_v1.md`;
- documentacion actualizada:
  - `docs/diagnosticador_loader_distribution_v1.md`;
  - `docs/diagnosticador_loader_manifest_v1.md`;
  - `docs/diagnosticador_loader_integrity_v1.md`;
  - `docs/diagnosticador_loader_integrity_enforcement_v1.md`.

### Validacion 9H

Preflight:

- Git limpio al inicio: PASS.
- DB real:
  - `embed_clients`: presente;
  - `local_embed_demo`: activo;
  - `allowed_origins`: `127.0.0.1:3050`, `localhost:3050`, `127.0.0.1:3060`;
  - secret presente (sin imprimirlo).
- Runtime local:
  - `backend-dev.sh`: PASS;
  - fallback estatico local sobre `astro/dist` en `3050` con proxy `/api` a
    `127.0.0.1:7050`: PASS;
  - assets embed servidos con CORS abierto para SRI cross-origin.

Backend:

- `uv run pytest tests/test_diagnosis_public_router.py tests/test_embed_clients_contract.py`:
  `83/83 PASS`.
- `uv run pytest tests/ -x --ignore=tests/test_db_module.py`:
  `1089 PASS, 9 skipped`.

Frontend:

- `pnpm check`: `0 errors`, `0 warnings`, `5 hints`.
- `pnpm build`: `146 pages`.
- helper:
  `node scripts/update-embed-integrity.mjs`: PASS.

Playwright CLI local (`PLAYWRIGHT_BASE_URL=http://127.0.0.1:3050`):

- `e2e/diagnosticador-cross-origin-integrity-loader-fixture.spec.ts`:
  `3 PASS`.
- `loader-integrity fixture + manifest + cross-origin + browser + mount + external + embed`:
  `15 PASS`.
- suite focalizada con Vera/lab/embed/external/mount/loader/fixture/manifest:
  `29 PASS, 2 skipped`.

Seguridad:

- fixture/snippet nuevos no contienen `hmac_secret`;
- fixture/snippet nuevos no contienen tenant, scope ni `allowed_origins`;
- `loaderIntegrity` invalido bloquea antes de `auth/turn`;
- `/t360`, `PublicVeraEntry.svelte` y `global.js` siguen fuera del diff.

MCP:

- endpoint intentado: `http://localhost:8931/mcp`;
- si no expone herramientas navegables en la sesion, el gate real sigue siendo
  Playwright CLI.

## Fase 9G — enforcement opt-in de entryIntegrity en el loader

Estado: IMPLEMENTADO Y VALIDADO. MCP limitado; gate efectivo con Playwright
CLI sobre runtime fallback local.

### Decision tecnica

- `window.Team360DiagnosticadorLoader.load()` sigue compatible;
- `window.Team360Diagnosticador.mount(...)` no cambia;
- se agrega `verifyEntryIntegrity: true` como modo opt-in explicito;
- el loader conserva el camino default sin enforcement;
- en modo opt-in el loader aplica `integrity` y `crossorigin="anonymous"` al
  script dinamico del entry;
- si falta `entryIntegrity`, rechaza antes de cargar;
- si el browser bloquea el entry por mismatch, rechaza con error controlado;
- si el global ya existe, resuelve idempotente y no revalida esa carga previa.

### Implementacion

- loader actualizado:
  `astro/public/embed/team360-diagnosticador-loader.js`;
- typing actualizado:
  `astro/src/env.d.ts`;
- spec endurecido:
  `e2e/diagnosticador-loader-manifest.spec.ts`;
- documentacion nueva:
  `docs/diagnosticador_loader_integrity_enforcement_v1.md`;
- documentacion actualizada:
  - `docs/diagnosticador_loader_distribution_v1.md`;
  - `docs/diagnosticador_loader_manifest_v1.md`;
  - `docs/diagnosticador_loader_integrity_v1.md`.

### Validacion 9G

Preflight:

- Git limpio al inicio: PASS.
- DB real:
  - `embed_clients`: presente;
  - `local_embed_demo`: activo;
  - `allowed_origins`: `127.0.0.1:3050`, `localhost:3050`, `127.0.0.1:3060`;
  - secret presente (sin imprimirlo).
- Runtime local:
  - `backend-dev.sh`: PASS;
  - fallback estatico local sobre `astro/dist` en `3050` con proxy `/api` a
    `127.0.0.1:7050`: PASS;
  - assets `loader`, `manifest` y `entry` servidos con CORS abierto para
    validar el fixture cross-origin.

Backend:

- `uv run pytest tests/test_diagnosis_public_router.py tests/test_embed_clients_contract.py`:
  `83/83 PASS`.
- `uv run pytest tests/ -x --ignore=tests/test_db_module.py`:
  `1089 PASS, 9 skipped`.

Frontend:

- `pnpm check`: `0 errors`, `0 warnings`, `5 hints`.
- `pnpm build`: `146 pages`.
- helper:
  `node scripts/update-embed-integrity.mjs`: PASS.

Playwright CLI local (`PLAYWRIGHT_BASE_URL=http://127.0.0.1:3050`):

- `e2e/diagnosticador-loader-manifest.spec.ts`:
  `6 PASS`.
- `loader-manifest + fixture + cross-origin + mount + external + embed`:
  `12 PASS`.
- suite focalizada con Vera/lab/embed/external/mount/loader/fixture/manifest:
  `26 PASS, 2 skipped`.

Seguridad:

- manifest/loader/asset estables no contienen `hmac_secret`;
- manifest/loader/asset estables no contienen tenant, scope ni
  `allowed_origins`;
- `/t360`, `PublicVeraEntry.svelte` y `global.js` siguen sin cambios.

MCP:

- endpoint intentado: `http://localhost:8931/mcp`;
- si no expone herramientas navegables en la sesion, el gate real sigue siendo
  Playwright CLI.

## Fase 9F — integrity/checksum opcional para loader distribution

Estado: IMPLEMENTADO Y VALIDADO. MCP limitado; gate efectivo con Playwright
CLI sobre runtime fallback local.

### Decision tecnica

Se eligio Opcion C:

- checksums `SHA-256` hex en manifest;
- SRI `sha256-...` en manifest;
- sin enforcement runtime del asset dinamico cargado por el loader;
- helper deterministico para recalculo despues de `build`;
- sin tocar `/t360`, `PublicVeraEntry.svelte` ni `global.js`.

### Implementacion

- manifest actualizado:
  `astro/public/embed/team360-diagnosticador.manifest.json`;
- helper nuevo:
  `astro/scripts/update-embed-integrity.mjs`;
- spec endurecido:
  `e2e/diagnosticador-loader-manifest.spec.ts`;
- documentacion nueva:
  `docs/diagnosticador_loader_integrity_v1.md`;
- documentacion actualizada:
  - `docs/diagnosticador_loader_distribution_v1.md`;
  - `docs/diagnosticador_loader_manifest_v1.md`.

### Contrato de integridad

Campos nuevos en el manifest:

- `entrySha256`;
- `entryIntegrity`;
- `loaderSha256`;
- `loaderIntegrity`.

Fuente de verdad:

- `loader`: `public/embed/team360-diagnosticador-loader.js`;
- `entry`: `dist/embed/team360-diagnosticador.js`.

### Snippet externo

Se documentan dos caminos:

- simple:
  `<script type="module" src="https://team360.live/embed/team360-diagnosticador-loader.js"></script>`;
- con integrity:
  `<script type="module" src="https://team360.live/embed/team360-diagnosticador-loader.js" integrity="sha256-..." crossorigin="anonymous"></script>`.

Notas:

- `loaderIntegrity` sale del manifest;
- `clientId` es publico;
- `hmac_secret` nunca se entrega;
- tenant/scope y `allowed_origins` quedan server-side.

### Validacion 9F

Preflight:

- Git limpio al inicio: PASS.
- DB real:
  - `embed_clients`: presente;
  - `local_embed_demo`: activo;
  - `allowed_origins`: `127.0.0.1:3050`, `localhost:3050`, `127.0.0.1:3060`;
  - secret presente (sin imprimirlo).
- Runtime local:
  - `backend-dev.sh`: PASS;
  - fallback estatico local sobre `astro/dist` en `3050` con proxy `/api` a
    `127.0.0.1:7050`: PASS.

Backend:

- `uv run pytest tests/test_diagnosis_public_router.py tests/test_embed_clients_contract.py`:
  `83/83 PASS`.
- `uv run pytest tests/ -x --ignore=tests/test_db_module.py`:
  `1089 PASS, 9 skipped`.

Frontend:

- `pnpm check`: `0 errors`, `0 warnings`, `5 hints`.
- `pnpm build`: `146 pages`.
- helper:
  `node scripts/update-embed-integrity.mjs`: PASS.

Playwright CLI local (`PLAYWRIGHT_BASE_URL=http://127.0.0.1:3050`):

- `e2e/diagnosticador-loader-manifest.spec.ts`:
  `2 PASS`.
- `loader-manifest + fixture + cross-origin + mount + external + embed`:
  `8 PASS`.
- suite focalizada con Vera/lab/embed/external/mount/loader/fixture/manifest:
  `22 PASS, 2 skipped`.

Seguridad:

- manifest/loader/asset estables no contienen `hmac_secret`;
- manifest/loader/asset estables no contienen tenant, scope ni
  `allowed_origins`;
- `/t360`, `PublicVeraEntry.svelte` y `global.js` siguen sin cambios.

MCP:

- endpoint intentado: `http://localhost:8931/mcp`;
- reachability HTTP: `400 Bad Request`;
- sin herramientas MCP navegables expuestas en esta sesion;
- cierre efectivo con Playwright CLI.

## Fase 9D-ext — fixture cross-origin controlado para validar Origin/CORS real

Estado: IMPLEMENTADO Y VALIDADO. MCP limitado; gate efectivo con Playwright
CLI sobre runtime fallback local.

### Decision tecnica

Se eligio host cross-origin controlado:

- fixture HTML estatico fuera de `public/`, servido por test en `3060/3061`;
- loader, manifest y asset remotos en `127.0.0.1:3050`;
- API real en `127.0.0.1:7050`;
- CORS backend local habilitado para `3050`, `3060` y `3061`;
- `local_embed_demo.allowed_origins` actualizado solo en DB local para agregar
  `http://127.0.0.1:3060`;
- `3061` queda fuera de `allowed_origins` y se rechaza con `403`;
- sin tocar `/t360`, `PublicVeraEntry.svelte` ni `global.js`.

### Implementacion

- nuevo fixture HTML:
  `astro/e2e/fixtures/cross-origin-host/t360-cross-origin-loader.html`;
- nueva session key aislada:
  `team360.embed.cross_origin.fixture.session.v1`;
- nuevo E2E:
  `e2e/diagnosticador-cross-origin-loader-fixture.spec.ts`;
- nueva documentacion:
  `docs/diagnosticador_cross_origin_fixture_v1.md`.

### Contrato validado

- host permitido:
  `http://127.0.0.1:3060/t360-cross-origin-loader.html`;
- host rechazado:
  `http://127.0.0.1:3061/t360-cross-origin-loader.html`;
- `window.Team360DiagnosticadorLoader.load()`;
- `window.Team360Diagnosticador.mount(...)`;
- `destroy()` operativo;
- `POST /api/diagnosis/embed/auth`;
- `POST /api/diagnosis/turn` con `client_id`, `timestamp`,
  `Origin` real y `X-T360-Signature`;
- rechazo `403` para origin no permitido sin `turn` exitoso.

### Seguridad

- el fixture cross-origin no expone `hmac_secret`;
- el fixture cross-origin no expone tenant/scope ni `allowed_origins`;
- `3060` se habilita solo en la DB local del cliente de prueba;
- `3061` queda fuera de `allowed_origins`;
- la sesion del fixture no toca `team360.vera.session.v1`.

## Fase 9C-ext — validacion externa real del browser loader publico

Estado: IMPLEMENTADO Y VALIDADO. MCP limitado; gate efectivo con Playwright
CLI sobre runtime fallback local.

### Decision tecnica

Se eligio Opcion A same-origin:

- fixture HTML estatico en `astro/public/embed-fixtures/`;
- mismo origin `127.0.0.1:3050` ya permitido por `embed_clients`;
- sin tocar DB ni `allowed_origins`;
- sin npm/package;
- sin Web Component;
- sin tocar `/t360`, `PublicVeraEntry.svelte` ni `global.js`.

### Implementacion

- nuevo fixture HTML:
  `astro/public/embed-fixtures/t360-external-loader.html`;
- nueva session key aislada:
  `team360.embed.loader.fixture.session.v1`;
- nuevo E2E:
  `e2e/diagnosticador-browser-loader-fixture.spec.ts`;
- nueva documentacion:
  `docs/diagnosticador_browser_loader_fixture_v1.md`.

### URLs locales validadas

- fixture:
  `/embed-fixtures/t360-external-loader.html`
- manifest:
  `/embed/team360-diagnosticador.manifest.json`
- loader:
  `/embed/team360-diagnosticador-loader.js`
- asset:
  `/embed/team360-diagnosticador.js`

### Contrato validado

- host HTML de tercero controlado con `div + script`;
- `window.Team360DiagnosticadorLoader.load()`;
- `window.Team360Diagnosticador.mount(...)`;
- `destroy()` operativo;
- `POST /api/diagnosis/embed/auth`;
- `POST /api/diagnosis/turn` con `client_id`, `timestamp` y
  `X-T360-Signature`;
- rechazo de `mount()` sin `clientId` sin requests extra.

### Seguridad

- el fixture HTML no expone `hmac_secret`;
- el fixture HTML no expone tenant/scope ni `allowed_origins`;
- `public/embed-fixtures/` y `dist/embed-fixtures/` no contienen tenant/scope;
- la busqueda amplia sobre `dist/` sigue mostrando strings tecnicos
  preexistentes en bundles compartidos del proyecto, fuera del alcance de esta
  fase;
- el fixture no toca `team360.vera.session.v1`,
  `team360.embed.mount.demo.session.v1` ni
  `team360.embed.external.demo.session.v1`.

### Validacion 9C-ext

Preflight:

- Git limpio al inicio: PASS.
- DB real:
  - `embed_clients`: presente;
  - seed `local_embed_demo`: activo;
  - `allowed_origins`: `127.0.0.1:3050` y `localhost:3050`;
  - secret presente (sin imprimirlo).

Backend:

- `uv run pytest tests/test_diagnosis_public_router.py tests/test_embed_clients_contract.py`:
  83/83 PASS.
- `uv run pytest tests/ -x --ignore=tests/test_db_module.py`:
  1089 PASS, 9 skipped.

Frontend:

- `pnpm check`: 0 errors, 0 warnings, 5 hints.
- `pnpm build`: 146 pages.

Playwright CLI local (`PLAYWRIGHT_BASE_URL=http://127.0.0.1:3050`):

- `e2e/diagnosticador-browser-loader-fixture.spec.ts`:
  1 PASS.
- `fixture + loader + mount + external + embed`:
  5 PASS.
- suite focalizada con Vera/lab/embed/external/mount/loader/fixture:
  19 PASS, 2 skipped.

Runtime local:

- `backend-dev.sh`: PASS.
- fallback usado para Playwright CLI: backend real `7050` + servidor estatico
  local sobre `astro/dist` con proxy `/api` a `127.0.0.1:7050`.
- `curl -I /embed-fixtures/t360-external-loader.html`: 200 OK.

MCP:

- endpoint intentado: `http://localhost:8931/mcp`;
- reachability HTTP: `400 Bad Request`;
- sin herramientas MCP navegables expuestas en esta sesion;
- cierre efectivo con Playwright CLI.

## Fase 9E — manifest/loader externo minimo con versionado explicito

Estado: IMPLEMENTADO Y VALIDADO. MCP limitado; gate efectivo con Playwright
CLI sobre runtime fallback local.

### Decision tecnica

Se eligio Opcion A minima:

- manifest publico estable en `/embed/team360-diagnosticador.manifest.json`;
- loader publico estable en `/embed/team360-diagnosticador-loader.js`;
- asset estable conservado en `/embed/team360-diagnosticador.js`;
- sin tocar `mount.ts` ni `browser-global.ts` como fuentes de verdad;
- sin npm/package;
- sin Web Component;
- sin tocar `/t360`, `PublicVeraEntry.svelte` ni `global.js`.

### Implementacion

- nuevo manifest:
  `astro/public/embed/team360-diagnosticador.manifest.json`;
- nuevo loader:
  `astro/public/embed/team360-diagnosticador-loader.js`;
- nueva ruta host controlada:
  `src/pages/t360-loader-demo.astro`;
- nueva session key aislada:
  `team360.embed.loader.demo.session.v1`;
- nuevo E2E:
  `e2e/diagnosticador-loader-demo.spec.ts`;
- nuevo E2E de contrato:
  `e2e/diagnosticador-loader-manifest.spec.ts`;
- nueva documentacion:
  `docs/diagnosticador_loader_manifest_v1.md`;
- nueva documentacion de distribucion:
  `docs/diagnosticador_loader_distribution_v1.md`.

### URLs publicas

- manifest:
  `/embed/team360-diagnosticador.manifest.json`
- loader:
  `/embed/team360-diagnosticador-loader.js`
- asset:
  `/embed/team360-diagnosticador.js`

### Versionado explicito

- manifest:
  `0.9.0-experimental`
- loader:
  `experimental-9e`
- global del asset:
  `experimental-9c`

El versionado explicito nuevo vive en manifest y loader. El global del asset no
se cambio porque 9E no introduce una segunda implementacion del embed.

### Contrato publico endurecido

- el manifest expone `asset` y `entry` hacia la misma ruta publica estable;
- el manifest ahora explicita `format = browser-global`;
- el loader acepta `manifest.asset` o `manifest.entry`;
- `load()` sigue siendo idempotente: si el global ya existe, no recarga;
- el host externo sigue usando solo `clientId`, `apiBaseUrl` y props visuales
  seguras.

### Seguridad

- manifest/loader/asset estables no contienen `hmac_secret`;
- manifest/loader/asset estables no contienen tenant, scope ni
  `allowed_origins`;
- el loader no contiene `clientId` ni `apiBaseUrl`;
- el loader no hace mount automatico; solo resuelve el asset y deja el mount
  explicito al host;
- el contrato embed sigue pasando por `POST /api/diagnosis/embed/auth` y
  `POST /api/diagnosis/turn` con `client_id`, `timestamp` y
  `X-T360-Signature`.

### Validacion 9E

Backend:

- `uv run pytest tests/test_diagnosis_public_router.py tests/test_embed_clients_contract.py`:
  83/83 PASS.
- `uv run pytest tests/ -x --ignore=tests/test_db_module.py`:
  1089 PASS, 9 skipped.

Frontend:

- `pnpm check`: 0 errors, 0 warnings, 5 hints.
- `pnpm build`: 146 pages.

Playwright CLI local (`PLAYWRIGHT_BASE_URL=http://127.0.0.1:3050`):

- `e2e/diagnosticador-loader-manifest.spec.ts`:
  2 PASS.
- `e2e/diagnosticador-loader-demo.spec.ts`:
  1 PASS.
- `loader-manifest + loader + fixture + cross-origin + mount + external + embed`:
  9 PASS.
- suite focalizada con Vera/lab/embed/external/mount/loader/fixture/manifest:
  24 PASS, 1 skipped.

Runtime local:

- `backend-dev.sh`: PASS.
- fallback usado para Playwright CLI: backend real `7050` + servidor estatico
  local sobre `astro/dist` con proxy `/api` a `127.0.0.1:7050`.

MCP:

- endpoint intentado: `http://localhost:8931/mcp`;
- reachability HTTP: `400 Bad Request`;
- sin herramientas MCP navegables expuestas en esta sesion;
- cierre efectivo con Playwright CLI.

## Fase 9D — asset JS browser real servido por Astro

Estado: IMPLEMENTADO Y VALIDADO. MCP limitado; gate efectivo con Playwright
CLI sobre runtime fallback local.

### Decision tecnica

Se eligio una variante minima de Opcion C:

- asset estable emitido por el build en `/embed/team360-diagnosticador.js`;
- salida controlada desde `astro.config.mjs` con Rollup/Vite;
- reutilizando `browser-global.ts` como capa global y `mount.ts` como unica
  fuente de verdad;
- sin npm/package;
- sin Web Component;
- sin tocar `/t360`, `PublicVeraEntry.svelte` ni `global.js`.

### Implementacion

- nuevo asset estable de build:
  `dist/embed/team360-diagnosticador.js`;
- cambio minimo de build:
  `astro.config.mjs`;
- nueva pagina Astro:
  `src/pages/t360-asset-demo.astro`;
- nueva session key aislada:
  `team360.embed.asset.demo.session.v1`;
- nuevo E2E:
  `e2e/diagnosticador-asset-demo.spec.ts`;
- nueva documentacion:
  `docs/diagnosticador_browser_asset_v1.md`.

### URL publica y carga

- URL estable:
  `/embed/team360-diagnosticador.js`
- carga esperada:
  - `<script type="module" src="/embed/team360-diagnosticador.js"></script>`
- internamente el asset puede importar chunks hasheados `/_astro/*`.

### Seguridad

- el asset estable no embebe `clientId` ni `apiBaseUrl`;
- no expone `hmac_secret`, tenant, scope ni `allowed_origins`;
- mantiene `POST /api/diagnosis/embed/auth` y `POST /api/diagnosis/turn`;
- mantiene `client_id`, `timestamp` y `X-T360-Signature`;
- `dist/embed/team360-diagnosticador.js` no contiene tenant/scope;
- los chunks compartidos de `/_astro/*` siguen arrastrando contexto tecnico
  historico de Vera, preexistente y fuera del alcance de esta fase.

### Validacion 9D

Backend:

- `uv run pytest tests/test_diagnosis_public_router.py tests/test_embed_clients_contract.py`:
  83/83 PASS.
- `uv run pytest tests/ -x --ignore=tests/test_db_module.py`:
  1089 PASS, 9 skipped.

Frontend:

- `pnpm check`: 0 errors, 0 warnings, 5 hints.
- `pnpm build`: 145 pages.

Playwright CLI local (`PLAYWRIGHT_BASE_URL=http://127.0.0.1:3050`):

- `e2e/diagnosticador-asset-demo.spec.ts`:
  1 PASS.
- `asset + script + mount + external + embed`:
  6 PASS.
- suite focalizada con Vera/lab/embed/external/mount/script/asset:
  20 PASS, 2 skipped.

Runtime local:

- `backend-dev.sh`: PASS.
- `astro-dev.sh`: sigue bloqueado por el diff preexistente `IS_REST_PRO=true`
  en `global.js`.
- fallback usado para Playwright CLI: backend real `7050` + servidor estatico
  local sobre `astro/dist` con proxy `/api` a `127.0.0.1:7050`.

MCP:

- endpoint intentado: `http://localhost:8931/mcp`;
- reachability HTTP: `400 Bad Request`;
- sin herramientas MCP navegables expuestas en esta sesion;
- cierre efectivo con Playwright CLI.

## Fase 9C — script browser global controlado sobre mount

Estado: IMPLEMENTADO Y VALIDADO. MCP limitado; gate efectivo con Playwright
CLI sobre runtime fallback local.

### Decision tecnica

Se eligio Opcion A:

- entrypoint TS interno `browser-global.ts`;
- `window.Team360Diagnosticador.mount(...)` como global experimental;
- `mount.ts` sigue siendo la unica fuente de verdad;
- sin npm/package;
- sin Web Component;
- sin tocar `/t360`, `PublicVeraEntry.svelte` ni `global.js`.

### Implementacion

- nuevo registro global:
  `src/lib/t360/embed/browser-global.ts`;
- nueva pagina Astro:
  `src/pages/t360-script-demo.astro`;
- nueva session key aislada:
  `team360.embed.script.demo.session.v1`;
- nuevo E2E:
  `e2e/diagnosticador-script-demo.spec.ts`;
- nueva documentacion:
  `docs/diagnosticador_browser_global_adapter_v1.md`.

### API global experimental v1

- `window.Team360Diagnosticador.mount(container, config)`;
- `window.Team360Diagnosticador.version = "experimental-9c"`;
- handle devuelto:
  - `destroy()`.

Config permitida:

- `clientId`;
- `apiBaseUrl`;
- `assistantName`;
- `compact`;
- `initialMessage`;
- `sessionStorageKey`.

Config prohibida:

- `hmac_secret`;
- `organization_code`;
- `workspace_code`;
- `assistant_instance_code`;
- `package_code`;
- `knowledge_scope_code`;
- `allowed_origins`;
- `service_code`;
- `template_code`.

### Seguridad

- el global delega completamente en `mount.ts`;
- conserva `POST /api/diagnosis/embed/auth` y `POST /api/diagnosis/turn`;
- mantiene `client_id`, `timestamp` y `X-T360-Signature`;
- no expone `hmac_secret`, tenant, scope ni `allowed_origins`;
- conserva el global ya registrado si el script se carga dos veces;
- `/t360`, `PublicVeraEntry.svelte` y `global.js` quedaron sin cambios
  atribuibles a 9C.

### Validacion 9C

Backend:

- `uv run pytest tests/test_diagnosis_public_router.py tests/test_embed_clients_contract.py`:
  83/83 PASS.
- `uv run pytest tests/ -x --ignore=tests/test_db_module.py`:
  1089 PASS, 9 skipped.

Frontend:

- `pnpm check`: 0 errors, 0 warnings, 5 hints.
- `pnpm build`: 144 pages.

Playwright CLI local (`PLAYWRIGHT_BASE_URL=http://127.0.0.1:3050`):

- `e2e/diagnosticador-script-demo.spec.ts`:
  2 PASS.
- `script + mount + external + embed`:
  5 PASS.
- suite focalizada con Vera/lab/embed/external/mount/script:
  19 PASS, 2 skipped.

Runtime local:

- `backend-dev.sh`: PASS.
- `astro-dev.sh`: sigue bloqueado por el diff preexistente `IS_REST_PRO=true`
  en `global.js`.
- fallback usado para Playwright CLI: backend real `7050` + servidor estatico
  local sobre `astro/dist` con proxy `/api` a `127.0.0.1:7050`.

MCP:

- endpoint intentado: `http://localhost:8931/mcp`;
- reachability HTTP: `400 Bad Request`;
- sin herramientas MCP navegables expuestas en esta sesion;
- cierre efectivo con Playwright CLI.

## Fase 9B — `mount()` JavaScript experimental controlado

Estado: IMPLEMENTADO Y VALIDADO. MCP limitado; gate efectivo con Playwright
CLI sobre runtime fallback local.

### Decision tecnica

Se eligio Opcion A:

- adapter TS interno importable;
- sin `window.Team360Diagnosticador`;
- sin npm/package;
- sin Web Component;
- reutilizando `EmbedDiagnosticadorWrapper.svelte`.

### Implementacion

- nuevo adapter:
  `src/lib/t360/embed/mount.ts`;
- nuevo componente cliente demo:
  `src/lib/t360/embed/MountDiagnosticadorDemo.svelte`;
- nueva pagina Astro:
  `src/pages/t360-mount-demo.astro`;
- nueva session key aislada:
  `team360.embed.mount.demo.session.v1`;
- nuevo E2E:
  `e2e/diagnosticador-mount-demo.spec.ts`;
- nueva documentacion:
  `docs/diagnosticador_mount_adapter_v1.md`.

### API experimental v1

- `mountTeam360Diagnosticador(container, config)`;
- `Team360Diagnosticador.mount(container, config)` como namespace exportado
  interno, no global;
- handle devuelto:
  - `destroy()`.

Config permitida:

- `clientId`;
- `apiBaseUrl`;
- `assistantName`;
- `compact`;
- `initialMessage`;
- `sessionStorageKey`.

Config prohibida:

- `hmac_secret`;
- `organization_code`;
- `workspace_code`;
- `assistant_instance_code`;
- `package_code`;
- `knowledge_scope_code`;
- `allowed_origins`;
- `service_code`;
- `template_code`.

### Seguridad

- el mount reutiliza `POST /api/diagnosis/embed/auth` y
  `POST /api/diagnosis/turn`;
- mantiene `client_id`, `timestamp` y `X-T360-Signature`;
- no expone `hmac_secret`;
- no acepta tenant/scope aunque el host los intente pasar;
- `/t360`, `PublicVeraEntry.svelte` y `global.js` quedaron sin cambios
  atribuibles a 9B;
- el bundle compartido de `DiagnosticadorCore` sigue cargando strings tecnicos
  historicos de Vera, preexistentes y fuera del alcance de esta fase.

### Validacion 9B

Preflight DB real:

- `to_regclass('public.embed_clients')`: `embed_clients`
- seed `local_embed_demo`: presente, `is_active=true`
- `hmac_secret <> ''`: `true`

Backend:

- `uv run pytest tests/test_diagnosis_public_router.py tests/test_embed_clients_contract.py`:
  83/83 PASS.
- `uv run pytest tests/ -x --ignore=tests/test_db_module.py`:
  1089 PASS, 9 skipped.

Frontend:

- `pnpm check`: 0 errors, 0 warnings, 5 hints.
- `pnpm build`: 143 pages.

Playwright CLI local (`PLAYWRIGHT_BASE_URL=http://127.0.0.1:3050`):

- `e2e/diagnosticador-mount-demo.spec.ts`: PASS.
- `e2e/diagnosticador-mount-demo.spec.ts + diagnosticador-external-host-demo.spec.ts + diagnosticador-embed-demo.spec.ts`:
  3 PASS.
- suite focalizada con Vera/lab/embed/external/mount:
  17 PASS, 2 skipped.

Runtime local:

- `backend-dev.sh`: PASS.
- `astro-dev.sh`: sigue bloqueado por el diff preexistente `IS_REST_PRO=true`
  en `global.js`.
- fallback usado para Playwright CLI: backend real `7050` + servidor estatico
  local sobre `astro/dist` con proxy `/api` a `127.0.0.1:7050`.

MCP:

- endpoint intentado: `http://localhost:8931/mcp`;
- reachability HTTP: `400 Bad Request`;
- sin herramientas MCP navegables expuestas en esta sesion;
- cierre efectivo con Playwright CLI.

## Fase 9A — Adapter externo controlado del embed

Estado: IMPLEMENTADO Y GATE ESTABILIZADO. Validacion objetivo del host externo:
PASS. Suite focalizada Vera/lab/embed/external: PASS. MCP limitado.

### Causa raiz 9A-Fix

- el fallo no era una regresion del adapter externo;
- `e2e/public-vera-new-conversation.spec.ts` fallaba tambien en aislado;
- la causa fue un spec fragil: dependia del backend real, usaba
  `waitForTimeout()` fijos y no limpiaba `team360.vera.session.v1` antes de
  ejecutar el reset;
- `astro-dev.sh` sigue bloqueado de forma intencional por el diff preexistente
  `IS_REST_PRO=true` en `global.js`, por eso el gate se cerro con fallback
  estatico + proxy `/api`.

### Decision tecnica

Se eligio Opcion A:

- nueva ruta controlada `/t360-external-host-demo`;
- sin SDK publico;
- sin `mount()` JS estable;
- reutilizando `EmbedDiagnosticadorWrapper.svelte`.

### Implementacion

- nueva pagina Astro:
  `src/pages/t360-external-host-demo.astro`;
- `EmbedDiagnosticadorWrapper.svelte` ahora acepta `sessionStorageKey`
  opcional;
- nueva session key aislada:
  `team360.embed.external.demo.session.v1`;
- nueva prueba E2E:
  `e2e/diagnosticador-external-host-demo.spec.ts`;
- documentacion nueva:
  `docs/diagnosticador_external_host_demo_v1.md`.

### Seguridad

- el host externo usa `client_id=local_embed_demo`;
- mantiene `POST /api/diagnosis/embed/auth` y `POST /api/diagnosis/turn`;
- `X-T360-Signature` sigue viajando solo en header;
- no se agregan secretos al frontend;
- el HTML de `/t360-external-host-demo` no embebe tenant/scope;
- los bundles compartidos del Core siguen cargando contexto publico historico
  de Vera, ya presente antes de 9A.

### Validacion 9A

Backend:

- `uv run pytest tests/test_diagnosis_public_router.py tests/test_embed_clients_contract.py`:
  83/83 PASS.
- `uv run pytest tests/ -x --ignore=tests/test_db_module.py`:
  1089 PASS, 9 skipped.

Frontend:

- `pnpm check`: 0 errors, 0 warnings, 5 hints.
- `pnpm build`: 142 pages.

Playwright CLI local (`PLAYWRIGHT_BASE_URL=http://127.0.0.1:3050`):

- `e2e/diagnosticador-external-host-demo.spec.ts`: PASS.
- `e2e/diagnosticador-embed-demo.spec.ts`: PASS.
- `e2e/public-vera-new-conversation.spec.ts`: PASS en aislado.
- suite focalizada con Vera/lab/embed/external:
  16 PASS, 2 skipped bajo runtime fallback local.

Runtime local:

- `backend-dev.sh`: PASS.
- `astro-dev.sh`: bloqueado por el diff preexistente `IS_REST_PRO=true` en
  `global.js`.
- fallback usado para Playwright CLI: backend real `7050` + servidor estatico
  local sobre `astro/dist` con proxy `/api` a `127.0.0.1:7050`.

## Fase 8C — Endurecimiento operativo embed auth

Estado: IMPLEMENTADO Y VALIDADO EN BACKEND. MCP limitado en esta sesion; el
launcher oficial de Astro quedo bloqueado por el diff preexistente
`IS_REST_PRO=true` en `global.js`, fuera de alcance de esta fase.

### Decision tecnica

Se eligio Opcion C:

- interfaz minima + rate limiter in-memory por proceso;
- auditoria segura via logs estructurados internos;
- sin Redis;
- sin nueva tabla ni migracion para auditoria.

### Refuerzos 8C

- nuevo modulo backend `modules/embed_clients/rate_limit.py`;
- nuevo modulo backend `modules/embed_clients/audit.py`;
- `POST /api/diagnosis/embed/auth` ahora aplica rate limit antes del lookup en
  DB usando clave `client_id + origin + remote_ip`;
- defaults v1:
  - `TEAM360_EMBED_AUTH_RATE_LIMIT_WINDOW_SECONDS=60`
  - `TEAM360_EMBED_AUTH_RATE_LIMIT_MAX_REQUESTS=20`
  - `TEAM360_EMBED_AUTH_RATE_LIMIT_MAX_KEYS=10000`
- exceso de limite:
  - `429 Too Many Requests`
  - detail generico `Too many embed authentication requests.`
  - header `Retry-After`
  - sin `signature`, sin sesion y sin leak de `client_id`/tenant/scope/secret;
- auditoria segura por intento:
  - `embed_auth_allowed`
  - `embed_auth_rejected`
  - `embed_auth_rate_limited`
- payload auditado:
  - `timestamp_utc`
  - `event_type`
  - `reason_code`
  - `status_code`
  - hashes de `client_id`, `origin`, `remote_ip`, `user_agent`
  - `request_id` si existe
- payload prohibido:
  - `hmac_secret`
  - mensaje completo
  - tenant/scope
  - `allowed_origins`
  - firma completa.

### Validacion 8C

Backend:

- `uv run pytest tests/test_diagnosis_public_router.py tests/test_embed_clients_contract.py`:
  83/83 PASS.
- `uv run pytest tests/ -x --ignore=tests/test_db_module.py`:
  1089 PASS, 9 skipped.

Frontend:

- `pnpm check`: 0 errors, 0 warnings, 5 hints.
- `pnpm build`: 141 pages.

Preflight DB real:

- `SELECT to_regclass('public.embed_clients')`: `embed_clients`
- seed `local_embed_demo`: presente, `is_active=true`
- `hmac_secret <> ''`: `true`

Browser / E2E:

- MCP oficial `http://localhost:8931/mcp`: no expuso herramientas navegables
  en esta sesion.
- baseline Playwright oficial con `astro-dev.sh`: bloqueado por el diff
  preexistente `IS_REST_PRO=true` en `global.js`; no se modifico por estar
  fuera de alcance y protegido para `/t360`.

## Fase 8B — Contrato publico controlado v1

Estado: IMPLEMENTADO Y VALIDADO. MCP limitado a reachability HTTP en esta
sesion; cierre efectivo con Playwright CLI.

### Decision tecnica

Se eligio Opcion B: firma delegada por turno.

- se mantiene `POST /api/diagnosis/embed/auth`;
- no se introduce token efimero/JWT/store temporal en esta fase;
- el contrato publico controlado v1 reutiliza `embed_clients` como fuente de
  contexto y mantiene `hmac_secret` solo server-side.

### Refuerzos 8B

- test backend nuevo: firma emitida para un mensaje no autoriza otro mensaje;
- `e2e/diagnosticador-embed-demo.spec.ts` ahora verifica tambien que la
  respuesta de `/api/diagnosis/embed/auth` no filtre tenant/scope ni secret;
- `e2e/public-vera.spec.ts` se estabilizo para validar el request traducido por
  interaction block sin exigir un bubble de usuario sintetico;
- `e2e/public-vera-new-conversation.spec.ts` ignora ruido 404 del server local
  estatico/proxy que no afecta el flujo;
- `e2e/diagnosticador-embed-lab.spec.ts` se aislo del diff preexistente de
  `global.js` usando route mocking de `/diagnosis/turn`, conservando la
  verificacion de session keys y payload del lab.

### Validacion 8B

Backend:

- `uv run pytest tests/test_diagnosis_public_router.py tests/test_embed_clients_contract.py`:
  74/74 PASS.

Playwright CLI local (`PLAYWRIGHT_BASE_URL=http://127.0.0.1:3050`):

- `e2e/diagnosticador-embed-demo.spec.ts`: PASS.
- suite focalizada
  `public-vera.spec.ts + public-vera-new-conversation.spec.ts + diagnosticador-embed-lab.spec.ts + diagnosticador-embed-demo.spec.ts`:
  15 PASS, 2 skipped.

Contrato embed real:

- `POST /api/diagnosis/embed/auth`: `200 OK`;
- auth → turn real sobre backend `7050`: `201 Created`;
- firma para mensaje distinto: `403`;
- body embed sin tenant/scope cuando hay `embedAuth`.

## Fase 8A — Wrapper embebible interno/demo seguro

Estado: IMPLEMENTADO Y VALIDADO. MCP pendiente como herramienta navegable.

### Resultado operativo

Se implemento un wrapper embebible interno/demo que usa `client_id` y firma
server-side sin exponer `hmac_secret` al navegador.

- endpoint backend nuevo:
  `POST /api/diagnosis/embed/auth`;
- wrapper frontend nuevo:
  `src/lib/t360/diagnosticador/EmbedDiagnosticadorWrapper.svelte`;
- pagina demo nueva:
  `/t360-embed-demo`;
- API client extendido con `embedAuth` y `requestEmbedTurnAuth()`;
- `DiagnosticadorCore.svelte` extendido con `turnAuthProvider` opcional.

### Flujo implementado

```text
/t360-embed-demo
  -> EmbedDiagnosticadorWrapper
  -> requestEmbedTurnAuth()
  -> POST /api/diagnosis/embed/auth
  -> sendPublicTurn(embedAuth)
  -> POST /api/diagnosis/turn
  -> context resolved from embed_clients (PostgreSQL)
```

### Seguridad

- el navegador nunca recibe `hmac_secret`;
- `embed/auth` devuelve solo `client_id`, `timestamp`, `signature`;
- cuando `embedAuth` existe, `sendPublicTurn()` ya no mezcla
  `publicDiagnosisContext`;
- el body al turn incluye solo `client_id`, `timestamp`, `session_id`,
  `message`, `locale`, `interaction_response`;
- `X-T360-Signature` viaja solo en header;
- key de sesion aislada:
  `team360.embed.demo.session.v1`.

### Validacion

Backend:

- `uv run pytest tests/test_diagnosis_public_router.py tests/test_embed_clients_contract.py`:
  73/73 PASS.
- `uv run pytest tests/ -x --ignore=tests/test_db_module.py`:
  1079 PASS, 9 skipped, 1 warning.

Frontend:

- `pnpm check`: 0 errors, 0 warnings, 5 hints.
- `pnpm build`: 141 pages.
- `git diff --check`: PASS.

Smokes reales:

- `POST /api/diagnosis/embed/auth` con `local_embed_demo` y origin permitido:
  `200 OK`.
- auth → turn real contra backend `7050`: `201 Created`.
- request con body malicioso y firma valida: `201 Created`, con estado
  persistido desde DB (`team360_sales_diagnosis/pkg_sales_diagnosis/ks_team360_sales_diagnosis`).
- `client_id` desconocido: `403`.
- origin invalido: `403`.

Playwright:

- MCP oficial `http://localhost:8931/mcp` quedo reachable a nivel HTTP, pero
  no hubo herramientas MCP navegables expuestas en esta sesion.
- Fallback oficial usado: Playwright CLI.
- `e2e/diagnosticador-embed-demo.spec.ts`: PASS real.
- `e2e/diagnosticador-embed-lab.spec.ts` fallo bajo servidor local proxyeado
  por asumir URL absoluta `http://localhost:7050/...`.
- `e2e/public-vera-new-conversation.spec.ts` fallo bajo el mismo servidor de
  prueba; no se uso como criterio de aprobacion de Fase 8A.

### Notas de entorno

- `global.js` conserva un diff preexistente con `IS_REST_PRO=true`; no se
  modifico.
- para validar navegador real sin tocar `/t360`, se sirvio `astro/dist` en
  `127.0.0.1:3050` con un proxy local temporal `/api -> 127.0.0.1:7050`.
- `/t360` y `PublicVeraEntry.svelte` quedaron sin diff.

## Fase 7C — Aplicacion controlada de migracion 008 + seed local + smoke real

Estado: DB REAL APLICADA Y VALIDADA EN BACKEND. Playwright pendiente.

### Resultado operativo

La migracion `008_create_embed_clients.sql` se aplico manualmente sobre la DB
local/controlada `team360` y se valido el flujo embed contra backend real con
PostgreSQL persistente.

- DB target verificada antes de aplicar: `postgresql://localhost:5432/team360`
  (usuario `administrator`, entorno local/controlado).
- Backup logico minimo previo generado localmente, no versionado.
- `public.embed_clients` no existia antes de la migracion; luego quedo creada y
  verificada.
- Seed local insertado con UPSERT:
  - `client_id`: `local_embed_demo`
  - `allowed_origins`:
    `["http://127.0.0.1:3050", "http://localhost:3050"]`
  - contexto fijo:
    `team360_sales_diagnosis/team360_live/team360_public_site/pkg_sales_diagnosis/ks_team360_sales_diagnosis`
  - secret: no real, solo local.

### Verificacion de tabla

- columnas: `client_id`, `hmac_secret`, contexto fijo, `allowed_origins`,
  `is_active`, `label`, `metadata_jsonb`, timestamps UTC;
- indices:
  - `embed_clients_pkey`
  - `idx_ec_client_id` unico
  - `idx_ec_is_active` parcial para activos
- constraints:
  - `chk_ec_client_id_not_empty`
  - `chk_ec_hmac_secret_not_empty`
  - `chk_ec_allowed_origins_is_array`
  - `chk_ec_metadata_jsonb_is_object`

### Smokes reales

Contra `http://127.0.0.1:7050/api/diagnosis/turn`:

- sin `client_id`: `201 Created`;
- `client_id` valido + HMAC + origin permitido: `201 Created`;
- mismo request con `workspace_code` / `package_code` /
  `knowledge_scope_code` maliciosos en body: `201 Created`, pero el estado
  persistido en `sales_diagnosis_conversation_states` quedo con
  `team360_sales_diagnosis/pkg_sales_diagnosis/ks_team360_sales_diagnosis`;
- `client_id` desconocido: `403 Forbidden`;
- firma invalida: `403 Forbidden`;
- origin invalido: `403 Forbidden`;
- timestamp vencido: `403 Forbidden`;
- timestamp futuro excesivo: `403 Forbidden`.

Los `403` devolvieron detalle generico
`Embed client request is not authorized.` y no crearon estado conversacional.

### Validacion post-migracion

- `uv run pytest tests/test_diagnosis_public_router.py tests/test_embed_clients_contract.py`:
  66/66 PASS.
- `uv run pytest tests/ -x --ignore=tests/test_db_module.py`:
  1072 PASS, 9 skipped, 1 warning.
- `pnpm check`: 0 errors, 0 warnings, 5 hints preexistentes.
- `pnpm build`: 140 pages.
- `git diff --check`: PASS.

### Limites de cierre

- `/t360`, `PublicVeraEntry.svelte` y `global.js` no fueron modificados.
- Browser MCP no usado.
- Playwright focalizado no corrio porque Astro runtime local no estaba
  levantado y `global.js` conserva un diff preexistente ajeno a esta fase que
  no corresponde tocar para forzar `astro-dev.sh`.

## Fase 7B — Produccion multi-cliente para embed

Estado: IMPLEMENTADA Y VALIDADA EN BACKEND. Migracion preparada y no aplicada.

### Problema

La Fase 7A bloqueaba contextos publicos arbitrarios, pero todavia no existia un
contrato real multi-cliente para embebidos externos: faltaban `client_id`,
lookup persistente en PostgreSQL, firma HMAC y validacion de origins.

### Solucion

Se implemento autorizacion embed v1 en backend basada en PostgreSQL:

- migracion `backend/db/migrations/008_create_embed_clients.sql`;
- seed de ejemplo no automatico `008_create_embed_clients_seed_example.sql`;
- modulo `backend/modules/embed_clients/` con modelo, repo PostgreSQL,
  canonical string HMAC y validacion de origin/timestamp/signature;
- `public_turn()` ahora recibe `Request`, lee `Origin`, `Referer` y
  `X-T360-Signature`;
- cuando el body incluye `client_id`, el backend:
  - carga el cliente desde DB;
  - valida `is_active`;
  - valida origin exacto;
  - valida timestamp;
  - valida HMAC;
  - resuelve contexto desde `embed_clients`;
  - ignora `assistant_instance_code`, `organization_code`, `workspace_code`,
    `package_code`, `knowledge_scope_code` enviados por frontend;
- cuando el request no incluye `client_id`, Vera mantiene el flujo anterior
  con defaults + allowlist minima de Fase 7A.

### Contrato v1

- body: `client_id`, `timestamp`, `session_id`, `message`;
- header: `X-T360-Signature: sha256=<hex>`;
- canonical string: `client_id.timestamp.session_id.message`;
- ventana timestamp default: `±300s`
  (`TEAM360_EMBED_CLIENT_TIMESTAMP_TOLERANCE_SECONDS`);
- `session_id` es obligatorio para requests con `client_id`.

### Storage de secret

Se adopto `hmac_secret` en plaintext en PostgreSQL como decision pragmatica v1.
No hay secretos reales en el repo. La deuda de rotacion/vault/cifrado quedo
documentada en `docs/diagnosticador_embed_auth_v1.md`.

### Archivos modificados/creados

Modificados:

- `backend/routes/diagnosis.py`
- `backend/modules/embed_clients/__init__.py`
- `backend/modules/embed_clients/errors.py`
- `backend/tests/test_diagnosis_public_router.py`
- `lat.md/status_actual.md`
- `docs/status_actual.md`

Nuevos:

- `backend/modules/embed_clients/auth.py`
- `backend/tests/test_embed_clients_contract.py`
- `backend/db/migrations/008_create_embed_clients.sql`
- `backend/db/migrations/008_create_embed_clients_seed_example.sql`
- `docs/diagnosticador_embed_auth_v1.md`

### Validacion

- `uv run pytest tests/test_diagnosis_public_router.py tests/test_embed_clients_contract.py`: 66/66 PASS.
- `uv run pytest tests/test_diagnosis_public_router.py`: 60/60 PASS.
- `pnpm check`: 0 errors, 0 warnings, 5 hints preexistentes.
- `pnpm build`: 140 pages.
- `git diff --check`: PASS.
- `/t360` sin diff.
- `PublicVeraEntry.svelte` sin diff.
- `global.js` no fue tocado en esta fase (permanece con diff preexistente ajeno a 7B).

### Smokes y limites

- No se aplico la migracion 008 sobre PostgreSQL real.
- No se levanto backend productivo ni se hizo smoke real con `embed_clients`
  persistidos porque faltaria aplicar la migracion manualmente.
- La validacion de 7B queda cerrada en nivel backend/unit-contract. El smoke DB
  real queda pendiente del apply manual de migracion.

## Fase 7A — Allowlist minima backend para PublicDiagnosisContext

Estado: IMPLEMENTADA Y VALIDADA.

### Problema

El backend aceptaba contextos publicos arbitrarios desde el request (`assistant_instance_code`, `organization_code`, `workspace_code`, `package_code`, `knowledge_scope_code`). Esto abria riesgo de invasion multi-tenant si un cliente manipulaba el request.

### Solucion

Se implemento una allowlist minima backend que valida la tupla completa de 5 campos contra un unico contexto permitido (el default actual de Vera/Team360).

**`backend/routes/diagnosis.py`**:
- `ALLOWED_PUBLIC_DIAGNOSIS_CONTEXTS`: `frozenset` con la unica tupla permitida `(team360_sales_diagnosis, team360_live, team360_public_site, pkg_sales_diagnosis, ks_team360_sales_diagnosis)`.
- `_validate_public_turn_context_allowed()`: recibe el contexto ya resuelto y completo; compara la tupla de 5 campos contra la allowlist; si no coincide, lanza `HTTP 403` con mensaje generico.
- Integracion en `public_turn()`: validacion inmediatamente despues de `_resolve_public_turn_context()`, antes de crear sesion o contactar LLM.

### Reglas de validacion

1. Request sin contexto explicito → resuelve defaults → pasa allowlist → OK.
2. Request con contexto explicito igual al default → pasa allowlist → OK.
3. Request con contexto parcial → completa defaults → tupla completa igual al default → pasa allowlist → OK.
4. Request con contexto invalido → tupla completa no coincide → `403` con mensaje generico.
5. Error 403 no filtra valores de la allowlist.

### Archivos modificados

- `backend/routes/diagnosis.py` — +40 lineas (constante, funcion validacion, integracion)
- `backend/tests/test_diagnosis_public_router.py` — +109 lineas (7 tests nuevos)

### Validacion

- Backend unit tests: 49/49 PASS (42 existentes + 7 nuevos).
- Backend suite completa: 1055 PASS, 9 skipped (mismo baseline).
- `pnpm check`: 0 errors, 0 warnings.
- `pnpm build`: 140 pages.
- `git diff --check`: PASS.
- Smoke sin contexto: HTTP 201.
- Smoke contexto permitido explicito: HTTP 201.
- Smoke contexto invalido (`knowledge_scope_code` cambiado): HTTP 403, mensaje generico sin leak.
- Smoke contexto invalido (`workspace_code` cambiado): HTTP 403.
- Playwright: requiere LiteLLM para LLM real; no ejecutado por entorno parcial (validacion E2E completa realizada en Fase 8-9).

### No implementado en esta fase

- token/HMAC/client_id
- `embed_clients` table
- allowed_domains
- wrapper embebible publico
- Web Component / SDK / iframe / postMessage
- alta dinamica de tenants
- cambios frontend
- cambios en `t360.astro`, `PublicVeraEntry.svelte`, `global.js`

### Problema

Vera continuaba preguntando por detalles de implementacion (OAuth, APIs, pestañas exactas, credenciales) aun cuando ya tenia contexto suficiente para un diagnostico de factibilidad, y no cerraba el diagnostico para dejar implementacion para despues.

### Causa raiz (FASE 7)

Cuatro issues en `runtime.py`:
1. `_is_ready_to_diagnose()` solo detectaba proceso + canal + sistema; casos con management+volumen o con goal+channel no activaban readiness.
2. `_decide_turn()` no tenia guard para `status == "sufficient"`, permitiendo que el LLM preguntara de nuevo.
3. `_build_missing_requirements_block()` incluia items de implementacion como requisitos pendientes, empujando al usuario a responderlos.
4. LLM prompt no instruia separar factibilidad de implementacion.

### Solucion implementada (FASE 8-9)

**`runtime.py`** — 5 metodos modificados:

- `_is_ready_to_diagnose()`: ruta secundaria que detecta channel + (system o management) + (process o goal) + 1 senial extra (volumen, aprobacion, entidad).
- `_decide_turn()`: guard `status == "sufficient"` → retorna True inmediatamente para forzar diagnostico.
- `_build_missing_requirements_block()`: filtra solo items `preliminary_diagnosis` / `full_diagnosis`; items de implementacion colapsados en un unico requisito `post_diagnosis` con nota "Corresponde a etapa posterior de analisis de flujo".
- `_build_next_step_choice_if_ready()` / `_build_pause_block()`: titulo "Diagnostico de factibilidad listo" cuando status es sufficient, descripcion senala que detalles tecnicos son posteriores.

**`policies.py`** — prompt de sistema:
- Encabezado "DIAGNOSTICO DE FACTIBILIDAD" (no solo "DIAGNOSTICO").
- 8-secciones de salida: hechos, factibilidad, modo recomendado, que automatizar, que no, riesgos, puntos a validar despues, proximo paso.
- Prohibicion explicita de terminos de implementacion (OAuth, API, webhook, pestaña exacta, columnas, credenciales, service account).
- Regla de cierre: con canal + sistema + objetivo + 1 dato extra, cerrar diagnostico.

### Archivos modificados/creados

Modificados:
- `backend/modules/sales_diagnosis_runtime/runtime.py`
- `backend/modules/sales_diagnosis_runtime/policies.py`

Nuevos:
- `backend/tests/test_sales_diagnosis_feasibility_scope.py` — 13 tests unitarios
- `astro/e2e/public-vera-feasibility-diagnosis-scope.spec.ts` — 4 tests E2E

### Entorno de validacion

- Backend: `systemd-run --user --unit=team360-backend-dev` puerto 7050 con `TEAM360_AI_PROVIDER=litellm`, `TEAM360_LITELLM_BASE_URL=http://127.0.0.1:4000`, `LITELLM_MASTER_KEY`, `AUTOMATION_DIAGNOSIS_REPOSITORY=memory`.
- Astro: puerto 3050 con `IS_REST_PRO=false`.
- LiteLLM: puerto 4000, modelo `openai_gpt-5-nano`.

### Validacion

Backend unit tests (desde `backend/`):

- `uv run pytest tests/test_sales_diagnosis_feasibility_scope.py -v`: 13/13 PASS.
- `uv run pytest tests/ -x --ignore=tests/test_db_module.py`: 1070/1079 PASS (9 skipped, 2 pre-existing db_module failures).

Frontend E2E (desde `astro/` con `PLAYWRIGHT_SKIP_WEBSERVER=1 PLAYWRIGHT_BASE_URL=http://localhost:3050`):

- `public-vera-feasibility-diagnosis-scope.spec.ts`: 4/4 PASS (real LLM, no fallback).
- `public-vera-email-postsale-short-answers.spec.ts`: 7/7 PASS.
- `public-vera-phone-problems-interaction-priority.spec.ts`: 5/5 PASS.
- `public-vera-new-conversation.spec.ts`: 1/1 PASS.
- `public-vera.spec.ts` (excepto `:230`): 21/22 PASS (1 pre-existing failure: `renderiza interaction_block y traduce accion` — `appendUserMessage = false` no relacionado).
- `public-vera-mobile-sequential-blocks.spec.ts`: 1/2 PASS (1 pre-existing flaky mobile touch test).
- `public-vera.spec.ts:555` smoke test: PASS.
- Total focalizado: 38/40 PASS, 2 pre-existentes fallos no relacionados.
- Sin errores 5xx ni console errors.
- `git diff --check`: PASS.

## Calidad documental y operativa

- `AGENTS.md` es ahora la fuente operativa canonica compartida por Codex, OpenCode y Crush.
- la reorganizacion de `AGENTS.md`, status compacto e historial quedo confirmada en `8c51dca` y publicada.
- `.opencode-rules` queda como legado no cargado por la configuracion efectiva de OpenCode; debe retirarse o migrarse en una tarea posterior.
- `lat check` tiene una deuda preexistente de 129 errores: 110 secciones sin leading paragraph, 10 summaries extensos, 6 links rotos y 3 errores adicionales de indice.
- `lat search` requiere configurar `LAT_LLM_KEY`, `LAT_LLM_KEY_FILE` o `LAT_LLM_KEY_HELPER`; mientras tanto se usa `lat locate`.
- No existe CI ni task runner raiz; las validaciones siguen dependiendo de ejecucion local.

## Pendientes prioritarios

1. Investigar y corregir el test preexistente `public-vera.spec.ts:230` (`appendUserMessage = false` en interacciones via `t360action`).
2. Corregir `lat check` hasta cero errores.
3. Reducir o retirar reglas duplicadas en `.agents/skills/team360-project/SKILL.md` y `.opencode-rules`.
4. Crear comandos canonicos y CI para backend, frontend, LAT y E2E.
5. Corregir evidencia hardcodeada, I/O sincronico dentro de handlers async y posibles fallbacks silenciosos del runtime.
6. Hacer que LiteLLM registre tokens, coste, latencia y provider efectivo.

## Notas de seguridad

- No guardar secretos en el repositorio ni imprimirlos en comandos o documentacion.
- Las credenciales expuestas previamente deben rotarse.
- Evitar exportar todas las credenciales globalmente desde `~/.bashrc`; preferir carga acotada al proyecto o un gestor de secretos.

## Fase 11 — PASETO v4.public como estándar de tokens Team360

Estado: IMPLEMENTADO Y VALIDADO.

### Decisión técnica

- PASETO v4.public adoptado como estándar Team360 para tokens firmados propios.
- JWT queda reservado solo para integración externa obligatoria.
- HMAC embed actual queda como compatibilidad transitoria.
- Ed25519 como curva asimétrica; private key nunca llega al frontend.
- `pyseto 1.9.3` elegido como librería PASETO Python (compatible con v4.public).

### Documentación creada

- `docs/adr_paseto_v4_public_standard_v1.md` — ADR formal con decisión, motivos, política y riesgos.
- `docs/paseto_embed_auth_migration_plan_v1.md` — Plan de migración en 5 fases (F0–F4), de fundación a deprecación HMAC.

### Módulo backend

- `backend/modules/security/__init__.py` — paquete nuevo.
- `backend/modules/security/paseto_tokens.py` — API pública:
  - `PasetoKeyPair.generate(key_id)` — genera par Ed25519 en PEM.
  - `issue_paseto_v4_public(claims, *, private_key_pem, key_id, ttl_seconds, issuer, token_type)` — emite token `v4.public...`.
  - `verify_paseto_v4_public(token, *, public_keys_by_id, issuer, expected_type)` — verifica y extrae payload, con validación de `typ`, `iss`, `exp`, `iat`, `jti` y leeway configurable.
  - `PasetoVerificationError` — excepción canónica para fallos.

### Tests

- `tests/test_paseto_tokens.py` — 12 tests, todos PASS:
  1. issue + verify valid token
  2. expired token rejected
  3. wrong issuer rejected
  4. wrong typ rejected
  5. unknown key_id rejected
  6. malformed PASETO rejected
  7. tampered payload/signature rejected
  8. custom claims preserved
  9. format is v4.public, not JWT
  10. keys are Ed25519, not HMAC
  11. kid in footer selects correct key across multiple keys
  12. iat and jti auto-included

### Dependencia

- `pyseto` agregado vía `uv add pyseto`.

### No implementado en esta fase

- Fase 1 del plan migración (Console integration) — pendiente.
- Fase 2 (Embed Dual Support) — pendiente.
- Fases 3 y 4 (nuevo snippet, deprecación HMAC) — pendientes.
- Sin cambios en `global.js`, `/t360`, `PublicVeraEntry.svelte`, embed existente, runtime, Milvus, LiteLLM ni PostgreSQL.

### Validación

| Validación | Resultado |
| ---------- | --------- |
| `git diff --check` | PASS |
| `uv run pytest tests/test_paseto_tokens.py -v` | 12/12 PASS |
| `uv run pytest tests/test_embed_clients_contract.py -v` | 6/6 PASS (no regresión) |
| Secret/no-leak search | PASS — sin secretos reales; keys de test marcadas explícitamente como no-productivas |
| Protección `/t360` | Sin diff |
| Protección `PublicVeraEntry.svelte` | Sin diff |
| Protección `global.js` | Sin diff |

## 2026-07-05 — P4A: ConsoleBootstrap PASETO access_token experimental

Se implementó la Fase P4A del plan de migración HMAC→PASETO: `ConsoleBootstrapService`
emite un PASETO v4.public `access_token` firmado (Ed25519) como campo opcional de la
respuesta `POST /api/console/bootstrap`.

### Nuevo módulo/archivos

- **`routes/console_bootstrap.py`** — nuevo handler `POST /api/console/bootstrap`:
  - Lee `workspace_id` + `user_id` del body JSON.
  - Lee `PasetoConsoleSettings` desde env vars.
  - Delega en `ConsoleBootstrapService.build_bootstrap()`.
  - Serializa respuesta incluyendo `access_token`, `token_type`, `expires_in`.
  - Manejo de errores: `HTTP_500` con detail del dominio.
- **`modules/security/paseto_tokens.py`** (ampliado):
  - `PasetoConsoleSettings` — dataclass frozen con `enabled`, `issuer`, `key_id`, `private_key_pem`, `public_key_pem`, `ttl_seconds`.
  - `paseto_console_settings_from_env()` — factory desde `TEAM360_PASETO_*` env vars.
  - `issue_console_access_token(user_id, settings)` — emite PASETO v4.public con claims `sub:user:<id>`, `user_id`, `typ=console_access`, `iat`, `exp`, `jti`.
  - `_get_dev_key_pair()` — genera par Ed25519 dinámico si no hay env keys (solo dev).
- **`modules/console/types.py`** (ampliado): `ConsoleBootstrap` con 3 campos opcionales:
  `access_token: str | None`, `token_type: str | None`, `expires_in: int | None`.
- **`modules/console/service.py`** (ampliado): `build_bootstrap()` acepta `paseto_settings: PasetoConsoleSettings | None`. Si `enabled=True`, llama `issue_console_access_token()` y lo agrega al resultado.
- **`ls_iMotorSoft_Srv01.py`** (ampliado): import + registro de `console_bootstrap`.
- **`tests/test_console_bootstrap_service.py`** (ampliado): 6 nuevos tests P4A.

### Tests P4A (6 nuevos, sobre 6 originales = 12 total)

| Test | Lo que valida |
| ---- | ------------- |
| `test_bootstrap_still_returns_user_id_without_paseto` | Sin settings → `access_token: None` |
| `test_bootstrap_returns_access_token_when_paseto_enabled` | Token presente, formato `v4.public.` |
| `test_access_token_verifies_with_public_key` | `verify_paseto_v4_public` pasa |
| `test_no_access_token_when_paseto_disabled` | `enabled=False` → sin token |
| `test_bootstrap_user_id_preserved_with_paseto` | `user_id` preservado con token + debug |

### Decisión técnica

- `PasetoConsoleSettings` se pasa como kwarg opcional — no es obligatorio, no rompe existing tests.
- Dev keys: `PasetoKeyPair.generate()` dinámico, sin secretos en código.
- TTL default 900s (15 min), configurable vía env.
- `token_type` en respuesta: `"paseto_v4_public"` (no es un claim del PASETO, es metadato HTTP).
- Claims del token: `sub=user:<id>`, `user_id`, `typ=console_access`, `iss=team360`, `iat`, `exp`, `jti`.
- Footer: `{"kid":"local-dev-key-1"}`.

### Validación

| Validación | Resultado |
| ---------- | --------- |
| `git diff --check` | PASS |
| `uv run pytest tests/test_paseto_tokens.py -v` | 12/12 PASS |
| `uv run pytest tests/test_console_bootstrap_service.py -v` | 12/12 PASS (6 originales + 6 P4A) |
| `uv run pytest tests/test_embed_clients_contract.py -v` | 6/6 PASS (sin regresión embed) |
| `uv run pytest tests/test_diagnosis_public_router.py -v` | No corrido (sin cambios en `diagnosis.py`) |
| Secret/no-leak search | PASS — sin secretos reales; dev keys dinámicas |
| Protección `/t360` | Sin diff |
| Protección `PublicVeraEntry.svelte` | Sin diff |
| Protección `global.js` | Sin diff |
| Protección `embed_clients/` | Sin diff |
| Protección `routes/diagnosis.py` | Sin diff |

### Documentación creada

- `docs/paseto_console_bootstrap_access_token_v1.md` — documento específico P4A.

### No implementado en esta fase

- DB table para jti revocation.
- Endpoint de validación/verificación de token.
- Frontend mock consumer (no cambia `global.js` ni frontend).
- Producción env keys persistentes.
- Fases P4B (revocation DB), P5 (frontend integration).

## 2026-07-05 — P4B: Verificador PASETO para Console protegida

Se implementó la Fase P4B del plan de migración HMAC→PASETO: verificador
PASETO reutilizable para endpoints Console. Cierra el circuito P4A→P4B:
`POST /api/console/bootstrap` emite token → `GET /api/console/me` lo verifica.

### Módulos nuevos

- **`modules/console/auth.py`** — auth de Console:
  - `ConsolePrincipal` — dataclass frozen con `user_id`, `subject`, `claims`.
  - `ConsoleAuthError` — excepción canónica para fallos.
  - `extract_bearer_token(header)` — parsea `Authorization: Bearer <token>`.
  - `verify_console_access_token(token, public_keys_by_id, issuer)` — verifica
    PASETO v4.public con `typ=console_access`, `sub=user:<id>`, `user_id`.
  - Errores específicos: header ausente, scheme no Bearer, token vacío,
    typ/iss incorrecto, sub sin `user:`, `user_id` ausente, kid desconocido,
    expirado, malformado.
- **`modules/console/__init__.py`** — exporta `ConsoleAuthError`, `ConsolePrincipal`.
- **`modules/security/paseto_tokens.py`** (ampliado):
  - `get_dev_public_keys_by_id()` — helper público que expone la key pública
    dev para el verificador (mismo singleton que usa `issue_console_access_token`).
- **`routes/console_me.py`** — nuevo handler `GET /api/console/me`:
  - Lee `Authorization` header via `request.headers`.
  - Usa `extract_bearer_token()` + `verify_console_access_token()`.
  - Resuelve public keys desde env vars (con fallback dev key).
  - Devuelve `{user_id, subject, token_type}`.
  - Errores: 401 con detail descriptivo.
- **`ls_iMotorSoft_Srv01.py`** — import + registro de `console_me`.

### Tests

- **`tests/test_console_auth.py`** — 15 tests:
  - `TestExtractBearerToken` (5): header ausente, vacío, Basic, Bearer vacío, token válido.
  - `TestVerifyConsoleAccessToken` (9): token válido, `user_id` correcto,
    typ incorrecto, issuer incorrecto, sub sin `user:`, `user_id` ausente,
    kid desconocido, expirado, malformado.
  - `TestEndToEndP4A` (1): token emitido por P4A se verifica con P4B.
- **`tests/test_console_me_route.py`** — 9 tests via `TestClient`:
  - Sin header → 401; Bearer vacío → 401; Basic → 401; token inválido → 401.
  - Token válido → 200 con `user_id`, `subject`, `token_type`.
  - Respuesta no contiene `access_token`, keys ni secrets.
  - Token expirado → 401; typ incorrecto → 401.

### Protocolo

```
GET /api/console/me
Authorization: Bearer v4.public.<token>
→ 200 { "user_id": "...", "subject": "user:...", "token_type": "paseto_v4_public" }
→ 401 { "detail": "<reason>" }
```

### Decisión técnica

- El verificador vive en `modules/console/auth.py` (Console Console-specific).
- `verify_console_access_token` es wrapper sobre `verify_paseto_v4_public`
  (foundation genérica). Agrega validación de `sub=user:` y `user_id`.
- `extract_bearer_token` es independiente del tipo de token; podría reutilizarse.
- Dev keys: `get_dev_public_keys_by_id()` expone el mismo singleton que usa
  `issue_console_access_token()`, garantizando que tokens de bootstrap se
  verifiquen en dev sin configurar env vars.
- Producción: configurar `TEAM360_PASETO_PUBLIC_KEY_B64` + `TEAM360_PASETO_KEY_ID`.
- Errores 401, no 403, porque el cliente no está autenticado (no autorizado
  vs. no autenticado).

### Validación

| Validación | Resultado |
| ---------- | --------- |
| `git diff --check` | PASS |
| `tests/test_paseto_tokens.py` | 12/12 PASS |
| `tests/test_console_auth.py` | 15/15 PASS |
| `tests/test_console_bootstrap_service.py` | 12/12 PASS |
| `tests/test_console_me_route.py` | 9/9 PASS |
| `tests/test_embed_clients_contract.py` | 6/6 PASS (sin regresión) |
| `tests/test_diagnosis_public_router.py` | 77/77 PASS (sin regresión) |
| Secret/no-leak search | PASS |
| JWT search | PASS — solo referencias documentales |
| Protección `embed_clients/` | Sin diff |
| Protección `routes/diagnosis.py` | Sin diff |
| Protección `/t360`, `PublicVeraEntry`, `global.js` | Sin diff |
| Protección `astro/public/embed`, `cross-origin-host` | Sin diff |

### Documentación

- `docs/paseto_console_auth_verifier_v1.md` — documento específico P4B.

### No implementado en esta fase

- DB table para jti revocation.
- Refresh token.
- Scope/permisos en el endpoint.
- Aplicación verificador a endpoints Console reales (pendiente).
- Embed/HMAC dual-mode (Fase 2 del plan).

## Historial

- historial tecnico completo hasta esta reorganizacion: `status_historico_hasta_2026-06-28.md`;
- arquitectura viva e invariantes: `lat.md/lat.md`;
- orquestacion transversal: `lat.md/team360-global-orchestration.md`;
- Git conserva la evolucion exacta de cada cambio confirmado.
