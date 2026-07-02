# Status actual - lat.md

Objetivo: `arquitectura-viva`

Ultima actualizacion: 2026-07-01 (Fase 9E — manifest/loader externo minimo)

## Estado general

`lat.md/` contiene definiciones de alto nivel, reglas de negocio, decisiones de arquitectura e invariantes para Team360.

Esta capa sigue el patron usado en JudaismoenVivo: indice raiz `lat.md/lat.md`, documentos por concepto y referencias `[[...]]` que pueden anclarse desde codigo con comentarios `@lat`. Las reglas de uso quedaron declaradas en `AGENTS.md` y en `.agents/skills/team360-project/SKILL.md`.

## Acciones realizadas

### 2026-07-01 — Fase 9E — manifest/loader externo minimo con versionado explicito

Se agrego un manifest publico minimo y un loader publico minimo para hosts
controlados, sin npm/package, CDN real ni Web Component.

- Manifest estable:
  `/embed/team360-diagnosticador.manifest.json`.
- Loader estable:
  `/embed/team360-diagnosticador-loader.js`.
- Asset estable conservado:
  `/embed/team360-diagnosticador.js`.
- El loader reusa el asset estable con `import(assetUrl)` y no duplica
  `mount.ts` ni `browser-global.ts`.
- Nuevo host controlado:
  `/t360-loader-demo`.
- Session key nueva:
  `team360.embed.loader.demo.session.v1`.
- Nuevo E2E:
  `e2e/diagnosticador-loader-demo.spec.ts`.
- Versionado explicito nuevo:
  - manifest `0.9.0-experimental`;
  - loader `experimental-9e`;
  - global del asset conserva `experimental-9c`.
- Validacion:
  - backend focal `83/83 PASS`;
  - backend full `1089 PASS, 9 skipped`;
  - `pnpm check` PASS;
  - `pnpm build` PASS, `146 page(s)`;
  - `diagnosticador-loader-demo.spec.ts`: `1 passed`;
  - regresion corta loader/asset/script/mount/external/embed:
    `7 passed`.
- Manifest/loader/asset estables no contienen tenant/scope ni
  `hmac_secret`.
- `/t360`, `PublicVeraEntry.svelte` y `global.js` no se tocaron.
- MCP `http://localhost:8931/mcp` siguio reachable por HTTP (`400 Bad Request`)
  pero sin herramientas navegables expuestas; cierre efectivo con Playwright
  CLI sobre backend `7050` + fallback estatico `astro/dist` con proxy `/api`.

### 2026-07-01 — Fase 9D — asset JS browser real servido por Astro

Se agrego un asset browser estable servido por Astro para hosts controlados,
sin package npm, CDN externo ni Web Component.

- URL publica estable:
  `/embed/team360-diagnosticador.js`.
- La salida se emite desde el build Astro/Vite con un chunk fijo definido en
  `astro.config.mjs`.
- Reutiliza `browser-global.ts` como registro global y `mount.ts` como fuente
  de verdad; no duplica validaciones ni logica conversacional.
- Nuevo host controlado:
  `/t360-asset-demo`.
- Session key nueva:
  `team360.embed.asset.demo.session.v1`.
- Nuevo E2E:
  `e2e/diagnosticador-asset-demo.spec.ts`.
- Validacion:
  - backend focal `83/83 PASS`;
  - backend full `1089 PASS, 9 skipped`;
  - `pnpm check` PASS;
  - `pnpm build` PASS, `145 page(s)`;
  - `diagnosticador-asset-demo.spec.ts`: `1 passed`;
  - regresion corta asset/script/mount/external/embed:
    `6 passed`;
  - suite focalizada Vera/lab/embed/external/mount/script/asset:
    `20 passed, 2 skipped`.
- El asset estable `dist/embed/team360-diagnosticador.js` no contiene
  tenant/scope; los chunks compartidos `/_astro/*` siguen arrastrando strings
  tecnicos historicos de Vera, fuera del alcance de esta fase.
- `/t360`, `PublicVeraEntry.svelte` y `global.js` no se tocaron.
- MCP `http://localhost:8931/mcp` siguio reachable por HTTP (`400 Bad Request`)
  pero sin herramientas navegables expuestas; cierre efectivo con Playwright
  CLI sobre backend `7050` + fallback estatico `astro/dist` con proxy `/api`.

### 2026-07-01 — Fase 9C — script browser global controlado sobre mount

Se agrego una capa browser global experimental que expone
`window.Team360Diagnosticador.mount(...)` sobre el adapter de Fase 9B, sin
crear package npm, asset externo final ni Web Component.

- Nuevo registro global:
  `astro/src/lib/t360/embed/browser-global.ts`.
- Reusa `mountTeam360Diagnosticador()`; no duplica validaciones ni logica
  conversacional.
- Nueva ruta host controlada:
  `/t360-script-demo`.
- Session key nueva:
  `team360.embed.script.demo.session.v1`.
- El global actual expone:
  - `mount`;
  - `version="experimental-9c"`;
  - handle con `destroy()`.
- Si el script se carga dos veces, conserva el global existente y no lo
  sobreescribe.
- El contrato embed sigue pasando por `POST /api/diagnosis/embed/auth` y
  `POST /api/diagnosis/turn` con `client_id`, `timestamp` y
  `X-T360-Signature`.
- Nuevo E2E:
  `e2e/diagnosticador-script-demo.spec.ts`.
- Validacion:
  - backend focal `83/83 PASS`;
  - backend full `1089 PASS, 9 skipped`;
  - `pnpm check` PASS;
  - `pnpm build` PASS, `144 page(s)`;
  - `diagnosticador-script-demo.spec.ts`: `2 passed`;
  - regresion corta script/mount/external/embed:
    `5 passed`;
  - suite focalizada Vera/lab/embed/external/mount/script:
    `19 passed, 2 skipped`.
- `/t360`, `PublicVeraEntry.svelte` y `global.js` no se tocaron.
- MCP `http://localhost:8931/mcp` siguio reachable por HTTP (`400 Bad Request`)
  pero sin herramientas navegables expuestas; cierre efectivo con Playwright
  CLI sobre backend `7050` + fallback estatico `astro/dist` con proxy `/api`.

### 2026-07-01 — Fase 9B — `mount()` JavaScript experimental controlado

Se agrego una capa de montaje TypeScript interna para hosts controlados, sin
crear SDK publico, package npm ni Web Component.

- Nuevo adapter:
  `astro/src/lib/t360/embed/mount.ts`.
- Usa `mount()` y `unmount()` de Svelte 5 local.
- Reutiliza `EmbedDiagnosticadorWrapper.svelte`; no duplica logica
  conversacional ni contrato backend.
- Nuevo host controlado:
  `/t360-mount-demo`.
- Nueva session key aislada:
  `team360.embed.mount.demo.session.v1`.
- El adapter valida:
  - selector/HTMLElement;
  - `clientId`;
  - `apiBaseUrl`;
  - rechazo de claves prohibidas (`hmac_secret`, tenant/scope, etc.).
- Se exporta `mountTeam360Diagnosticador()` y namespace interno
  `Team360Diagnosticador.mount(...)`, sin `window`.
- `/t360`, `PublicVeraEntry.svelte` y `global.js` no se tocaron.
- Validacion:
  - backend focal `83/83 PASS`;
  - backend full `1089 PASS, 9 skipped`;
  - `pnpm check` PASS;
  - `pnpm build` PASS, `143 page(s)`;
  - `diagnosticador-mount-demo.spec.ts` PASS;
  - regresion corta embed/external/mount `3 passed`;
  - suite focalizada Vera/lab/embed/external/mount:
    `17 passed, 2 skipped`.
- Preflight DB real confirmado:
  `embed_clients` presente, seed `local_embed_demo` activo, secret presente.
- MCP `http://localhost:8931/mcp` respondio `400 Bad Request` por HTTP, pero
  no expuso herramientas navegables en esta sesion; cierre efectivo con
  Playwright CLI sobre backend `7050` + fallback estatico `astro/dist` con
  proxy `/api`.

### 2026-06-30 — Fase 9A-Fix — runtime/gate E2E del adapter externo

Se cerro el bloqueo operativo de 9A sin tocar `/t360`, `PublicVeraEntry` ni
`global.js`.

- El fallo real estaba en `e2e/public-vera-new-conversation.spec.ts`, no en el
  adapter externo.
- El spec usaba waits fijos, dependia del backend real y no limpiaba
  `team360.vera.session.v1`, por eso quedaba expuesto a timing de hidratacion y
  loading state (`Analizando...`).
- Se endurecio el spec con el mismo patron de los tests estables de Vera:
  limpieza explicita de sesion, route mocking de `/api/diagnosis/turn` y
  esperas sobre estado habilitado/visible.
- `astro-dev.sh` sigue bloqueado por la guarda intencional contra
  `IS_REST_PRO=true` en `global.js`; no se toco ese diff preexistente.
- El gate real se valido con backend `7050` + fallback estatico sobre
  `astro/dist` + proxy `/api`.
- Resultado final:
  - `diagnosticador-external-host-demo`: PASS;
  - `diagnosticador-embed-demo`: PASS;
  - `public-vera-new-conversation`: PASS en aislado;
  - suite focalizada Vera/lab/embed/external: `16 passed, 2 skipped`.
- MCP oficial `http://localhost:8931/mcp` siguio sin herramientas navegables
  expuestas en esta sesion; cierre efectivo con Playwright CLI.

### 2026-06-30 — Fase 9A — Adapter externo controlado del embed

Se agrego una ruta host externa controlada para montar el Diagnosticador fuera
de `/t360` sin crear SDK, package ni Web Component.

- Nueva ruta Astro:
  `/t360-external-host-demo`.
- Reutiliza `EmbedDiagnosticadorWrapper.svelte`.
- El wrapper ahora acepta `sessionStorageKey` opcional para aislar hosts
  controlados.
- Session key nueva:
  `team360.embed.external.demo.session.v1`.
- Nuevo E2E:
  `e2e/diagnosticador-external-host-demo.spec.ts`.
- `POST /api/diagnosis/embed/auth` y `POST /api/diagnosis/turn` se validaron
  otra vez con `client_id`, `timestamp` y `X-T360-Signature`.
- No se toco `/t360`, `PublicVeraEntry.svelte` ni `global.js`.
- El host HTML nuevo no incrusta tenant/scope ni secretos.
- El bundle compartido del Core mantiene strings tecnicos historicos de Vera,
  fuera del alcance de esta fase.
- MCP oficial `http://localhost:8931/mcp` siguio sin herramientas navegables
  en esta sesion; cierre con Playwright CLI.

### 2026-06-30 — Fase 8C — Endurecimiento operativo embed auth

Se endurecio `POST /api/diagnosis/embed/auth` antes de ampliar el contrato
publico del embed.

- Se eligio interfaz minima + rate limiter in-memory por proceso.
- Nueva clave de rate limit:
  `client_id + origin + remote_ip`.
- Defaults v1:
  - `TEAM360_EMBED_AUTH_RATE_LIMIT_WINDOW_SECONDS=60`
  - `TEAM360_EMBED_AUTH_RATE_LIMIT_MAX_REQUESTS=20`
  - `TEAM360_EMBED_AUTH_RATE_LIMIT_MAX_KEYS=10000`
- Exceso de limite:
  - `429 Too Many Requests`
  - detail generico `Too many embed authentication requests.`
  - `Retry-After`
  - sin firma y sin sesion.
- Auditoria segura nueva por intento:
  - `embed_auth_allowed`
  - `embed_auth_rejected`
  - `embed_auth_rate_limited`
- Los eventos solo registran hashes de `client_id`, `origin`, `remote_ip`,
  `user_agent`, mas `status_code`, `reason_code` y `request_id` cuando existe.
- No se persisten ni loguean `hmac_secret`, mensaje completo, tenant, scope ni
  `allowed_origins`.
- Validacion backend:
  - focalizada `83/83 PASS`;
  - suite completa `1089 PASS, 9 skipped`.
- MCP oficial `http://localhost:8931/mcp` no expuso herramientas navegables en
  esta sesion; el launcher oficial de Astro siguio bloqueado por el diff
  preexistente `IS_REST_PRO=true` en `global.js`, que no corresponde tocar en
  esta fase.

### 2026-06-30 — Fase 8B — Contrato publico controlado v1

Se formalizo el contrato publico controlado del embed sobre la opcion B
(firma delegada por turno), sin introducir JWT ni token store.

- Se mantiene `POST /api/diagnosis/embed/auth` como endpoint publico
  controlado v1.
- El timestamp lo genera siempre backend y la firma sigue el canonical string
  `client_id.timestamp.session_id.message`.
- El backend mantiene `embed_clients` como fuente exclusiva del contexto
  cuando existe `client_id`.
- Nuevo test backend de seguridad: una firma emitida para un mensaje no
  autoriza otro mensaje distinto.
- Playwright demo ahora valida request y response de auth sin leak de tenant,
  scope, secret ni `allowed_origins`.
- El gate Vera/lab/embed se estabilizo sin tocar `/t360`:
  - `diagnosticador-embed-demo`: PASS;
  - `diagnosticador-embed-lab`: route mocking para aislar el diff preexistente
    de `global.js` y validar transporte/session keys;
  - `public-vera` y `public-vera-new-conversation`: PASS sobre el entorno local
    correcto, con ajuste de expectativas frágiles.
- MCP oficial `http://localhost:8931/mcp` siguio reachable por HTTP, pero el
  cierre efectivo permanecio en Playwright CLI por falta de herramientas MCP
  navegables expuestas en esta sesion.

### 2026-06-30 — Fase 8A — Wrapper embed interno/demo seguro

Se implemento el primer wrapper embebible interno/demo sobre el contrato
`embed_clients`, sin exponer `hmac_secret` al navegador.

- Nuevo endpoint backend `POST /api/diagnosis/embed/auth`:
  valida `client_id`, `is_active`, `Origin`/`Referer`; genera `timestamp`
  server-side y devuelve solo `client_id`, `timestamp`, `signature`.
- `routes/diagnosis.py` reutiliza `PostgresEmbedClientRepository`,
  validacion de origins y helpers HMAC ya existentes; el endpoint de firma no
  crea sesion ni contacta LLM.
- `publicDiagnosis.ts` ahora soporta `embedAuth`:
  si existe, envia `client_id` y `timestamp` en body + `X-T360-Signature`
  en headers, sin mezclar `publicDiagnosisContext`.
- `DiagnosticadorCore.svelte` agrega `turnAuthProvider` opcional. Vera y el lab
  viejo no lo usan; el wrapper demo si.
- Nuevo wrapper `EmbedDiagnosticadorWrapper.svelte` y pagina
  `/t360-embed-demo` con `client_id=local_embed_demo`, `apiBaseUrl`
  explicito y key aislada `team360.embed.demo.session.v1`.
- Props publicas v1 del wrapper:
  `apiBaseUrl`, `clientId`, `assistantName`, `compact`, `initialMessage`.
- Props prohibidas por contrato: `hmac_secret`, tenant/scopes,
  `allowed_origins`, `service_code`, `template_code`.
- Validacion backend:
  - `73/73 PASS` en tests focalizados (`embed auth` + router publico);
  - `1079 PASS, 9 skipped` en la suite backend completa.
- Validacion frontend:
  - `pnpm check` 0 errors, 0 warnings, 5 hints;
  - `pnpm build` 141 pages;
  - `git diff --check` PASS.
- Smoke real backend:
  - `POST /api/diagnosis/embed/auth` con `local_embed_demo`: `200 OK`;
  - auth → turn real: `201 Created`;
  - body malicioso ignorado y contexto persistido desde DB;
  - unknown client / invalid origin: `403`.
- Playwright:
  - MCP endpoint `http://localhost:8931/mcp` respondio a nivel HTTP, pero no
    hubo herramientas MCP navegables expuestas en esta sesion;
  - Playwright CLI quedo como evidencia de cierre;
  - `e2e/diagnosticador-embed-demo.spec.ts`: PASS real;
  - `public-vera-new-conversation` y `diagnosticador-embed-lab` fallaron bajo
    el server local proxyeado por supuestos de entorno (`URL exacta` y
    reset UI), no por el wrapper nuevo.
- No se tocaron `/t360`, `PublicVeraEntry.svelte`, `global.js`, `runtime.py`
  ni `policies.py`.

### 2026-06-30 — Fase 7C — Aplicacion controlada de DB real para embed_clients

Se cerro la validacion extremo a extremo de `embed_clients` sobre PostgreSQL
local/controlado, sin tocar `/t360` ni reiniciar servicios permanentes.

- Migracion `008_create_embed_clients.sql` aplicada manualmente sobre DB local
  `team360` usando `psycopg`.
- Backup logico minimo previo registrado en
  `backups/phase7c_pre_migration_20260630T122347Z.json`.
- Tabla `embed_clients` verificada post-migracion: columnas, indices y
  constraints compatibles con el contrato v1.
- Seed local de prueba insertado con UPSERT:
  `client_id=local_embed_demo`, origins `http://127.0.0.1:3050` y
  `http://localhost:3050`, secret no real.
- Backend real levantado solo con `backend-dev.sh`; `/health` OK.
- Smokes reales contra `http://127.0.0.1:7050/api/diagnosis/turn`:
  - sin `client_id`: 201;
  - `client_id` valido + HMAC + origin: 201;
  - body malicioso con contexto manipulado: 201 pero contexto efectivo
    persistido desde DB;
  - `client_id` desconocido: 403;
  - firma invalida: 403;
  - origin invalido: 403;
  - timestamp vencido/futuro: 403.
- Requests 403 no crearon estado conversacional en PostgreSQL.
- Validacion post-migracion:
  `uv run pytest tests/test_diagnosis_public_router.py tests/test_embed_clients_contract.py`
  66/66 PASS;
  `uv run pytest tests/ -x --ignore=tests/test_db_module.py`
  1072 PASS, 9 skipped;
  `pnpm check` 0 errors, 0 warnings, 5 hints;
  `pnpm build` 140 pages;
  `git diff --check` PASS.
- Playwright/MCP no ejecutados en esta fase: Astro runtime local no estaba
  disponible y `global.js` conserva un diff preexistente ajeno a Fase 7C que
  no debe tocarse para forzar `astro-dev.sh`.

### 2026-06-30 — Fase 7B — Produccion multi-cliente para embed

Se preparo el contrato backend seguro para clientes embebibles multi-tenant sin
romper Vera ni `/t360`.

- Nueva migracion `008_create_embed_clients.sql`: tabla persistente para
  `client_id`, `hmac_secret`, contexto fijo y `allowed_origins`.
- Seed de ejemplo separado `008_create_embed_clients_seed_example.sql`; no se
  aplica automaticamente y no contiene secretos reales.
- Nuevo modulo `backend/modules/embed_clients/` con validacion HMAC-SHA256,
  canonical string `client_id.timestamp.session_id.message`, origin exacto y
  timestamp window configurable.
- `routes/diagnosis.py` ahora resuelve requests con `client_id` solo desde
  PostgreSQL y descarta cualquier contexto enviado por frontend.
- Vera sin `client_id` mantiene defaults + allowlist minima de Fase 7A.
- Secret storage v1: `hmac_secret` en plaintext en PostgreSQL, con deuda
  explicitada de vault/cifrado/rotacion futura.
- Documentacion canonica nueva:
  `SrvRestAstroLS_v1/docs/diagnosticador_embed_auth_v1.md`.
- Validacion focalizada: 66/66 PASS en tests backend de router + contrato;
  `pnpm check` sin errores; `pnpm build` 140 pages; `git diff --check` PASS.
- Migracion no aplicada sobre PostgreSQL real en esta fase.

### 2026-06-28 — publicDiagnosisContext configurable en DiagnosticadorCore (Fase 5)

El Core acepta un contexto publico configurable sin alterar el payload historico de Vera.

- Se definio `PublicDiagnosisContext` interface en `config/types.ts`.
- Se exporto `DEFAULT_PUBLIC_DIAGNOSIS_CONTEXT` en `config/defaults.ts`
  como re-export de la constante canonica `PUBLIC_DIAGNOSIS_CONTEXT`.
- `sendPublicTurn` acepta `options.publicDiagnosisContext`; cuando se
  provee, mergea los campos al body HTTP (`{ ...ctx, ...request }`).
  Vera (sin contexto) mantiene payload identico.
- `DiagnosticadorCore` agrega prop `publicDiagnosisContext` con default
  compatible; lo pasa a `sendPublicTurn`.
- `DiagnosticadorEmbedLab` pasa `publicDiagnosisContext` explicitamente.
- Test E2E actualizado: intercepta request y verifica que el body incluya
  `assistant_instance_code`, `package_code`, `knowledge_scope_code`.
- Frozen files intactos: `t360.astro`, `PublicVeraEntry.svelte`, `global.js`.
- Validacion: `pnpm check` 0 errors, `pnpm build` 140 pages, Playwright
  14/14 pass (lab + Vera + new-conversation). Sin regresiones.
- Estado: FASE 5 — PUBLIC_DIAGNOSIS_CONTEXT CONFIGURABLE — IMPLEMENTADA Y VALIDADA.
- Detalle completo en `SrvRestAstroLS_v1/docs/status_actual.md`.

### 2026-06-29 — Fase 7A — Allowlist minima backend para PublicDiagnosisContext

El backend ahora rechaza contextos publicos arbitrarios validando contra una allowlist de
tuplas completas de 5 campos (assistant_instance_code, organization_code, workspace_code,
package_code, knowledge_scope_code).

- `ALLOWED_PUBLIC_DIAGNOSIS_CONTEXTS` en `backend/routes/diagnosis.py`: frozenset con el
  unico contexto permitido (default actual de Vera).
- `_validate_public_turn_context_allowed()`: compara tupla completa de 5 campos; HTTP 403
  si no coincide.
- Validacion integrada en `public_turn()` inmediatamente despues de resoler contexto.
- Request sin contexto → pasa allowlist (resuelve a default). Request parcial → idem.
- Request invalido → 403 con mensaje generico, sin leak de allowlist.
- 7 tests nuevos en `test_diagnosis_public_router.py` (49/49 PASS).
- Frozen files intactos: `t360.astro`, `PublicVeraEntry.svelte`, `global.js`.
- Validacion: backend 1055 PASS, `pnpm check` 0 errors, `pnpm build` 140 pages,
  smoke sin contexto 201, smoke permitido 201, smoke invalido 403.
- Estado: FASE 7A — ALLOWLIST MINIMA BACKEND — IMPLEMENTADA Y VALIDADA.
- Detalle completo en `SrvRestAstroLS_v1/docs/status_actual.md`.

### 2026-06-28 — apiBaseUrl configurable en DiagnosticadorCore (Fase 4)

El Core permite definir la URL base de la API manteniendo `global.js` como default compatible.

- `sendPublicTurn` en `publicDiagnosis.ts` acepta ahora `options.apiBaseUrl`
  opcional; default es `API_BASE_URL` de `global.js` (compatible hacia atras).
- `DiagnosticadorCore.svelte` agrega prop `apiBaseUrl` (default: `API_BASE_URL`);
  la pasa a `sendPublicTurn` como options.
- `DiagnosticadorEmbedLab.svelte` pasa `apiBaseUrl={API_BASE_URL}` explicitamente,
  validando override sin tocar `global.js`.
- Test E2E actualizado: intercepta request del lab y verifica URL target
  `http://localhost:7050/api/diagnosis/turn`.
- Frozen files intactos: `t360.astro`, `PublicVeraEntry.svelte`, `global.js`.
- Validacion: `pnpm check` 0 errors, `pnpm build` 140 pages, Playwright
  14/14 pass (lab + Vera + new-conversation). Sin regresiones.
- Estado: FASE 4 — API_BASE_URL CONFIGURABLE — IMPLEMENTADA Y VALIDADA.
- Detalle completo en `SrvRestAstroLS_v1/docs/status_actual.md`.

### 2026-06-28 - Lab embebible DiagnosticadorCore fuera de /t360

El laboratorio valida que el DiagnosticadorCore pueda montarse fuera de Vera con sesion aislada.

- Se creo `DiagnosticadorEmbedLab.svelte` en `src/lib/t360/diagnosticador/`
  como adapter de laboratorio que monta `DiagnosticadorCore` con configuracion
  propia (session key aislada `team360.diagnosticador.lab.session.v1`,
  sin mailto, sin copy comercial).
- Se creo pagina `/t360-diagnosticador-lab` en `src/pages/` usando `BaseLayout`.
- Se creo test E2E `diagnosticador-embed-lab.spec.ts` que valida: carga del lab,
  envio de mensaje real contra backend, key de sessionStorage aislada, no
  colision con key de Vera, Vera preservada en su pestana original.
- `t360.astro` no fue modificado. `PublicVeraEntry` no fue modificado.
- No se creo workspace, package, Web Component ni iframe.
- Validacion: `pnpm check` 0 errors, `pnpm build` 140 pages, Playwright
  13/13 + 1/1 lab pass. Sin regresiones en `/t360`.
- Estado: LAB EMBEBIBLE IMPLEMENTADO Y VALIDADO.
- Detalle completo en `SrvRestAstroLS_v1/docs/status_actual.md`.

### 2026-06-26 - Politica Playwright MCP Server

- Se documento `playwright-mcp-server-policy.md` como herramienta oficial de
  exploracion visual y reproduccion interactiva asistida.
- Endpoint local documentado: `http://localhost:8931/mcp`.
- Playwright CLI continua siendo el gate E2E oficial para cierre reproducible.
- Se enlazo la politica desde `lat.md/lat.md`, `AGENTS.md` y
  `.agents/skills/team360-project/SKILL.md`.
- No se modifico codigo productivo, backend, frontend, tests ni configuracion
  productiva.

### 2026-06-25 - Contexto componentes Diagnosticador embeddable

- Se agrego `diagnosticador-embeddable-component-architecture.md` como fuente
  canonica para el atajo `contexto componentes`.
- El documento consolida la decision de mantener inicialmente el Core dentro de
  `SrvRestAstroLS_v1/astro/src/lib/t360`, sin crear `/packages`, workspace raiz
  ni paquetes npm prematuros.
- Se documento la extraccion progresiva de `DiagnosticadorCore.svelte`, el rol
  de `PublicVeraEntry.svelte` como adapter de Home, la separacion de
  `ConsoleDiagnosis.svelte`, estado conversacional, eventos publicos `t360:*`,
  estilos encapsulados y reglas para futuros productos, variantes, interaction
  blocks, adapters y paquetes.
- Se enlazo el nuevo documento desde `lat.md/lat.md`, `AGENTS.md`,
  `.agents/skills/team360-project/SKILL.md` y el antecedente UX embeddable.
- No se modifico codigo productivo, componentes, configs, dependencias,
  servicios, DB, Milvus, LiteLLM ni workspaces.

### 2026-06-25 - Playwright como navegador sobre runtime real

- Se reforzo `browser-mcp-validation-policy.md` para que todo test local de
  paginas, componentes hidratados o E2E real lea esta politica antes de
  ejecutarse.
- Se fijo como regla obligatoria que `backend-dev.sh` y `astro-dev.sh` son los
  responsables de levantar/bajar el runtime local real.
- Se dejo explicito que Playwright debe automatizar Chromium contra ese runtime
  con `PLAYWRIGHT_SKIP_WEBSERVER=1`, sin levantar su `webServer` automatico ni
  usar proxy/puertos paralelos salvo justificacion explicita.
- Se actualizaron `AGENTS.md` y `.agents/skills/team360-project/SKILL.md` para
  que esta regla se lea al iniciar sesiones y antes de validaciones de paginas
  o end-to-end.
- No se modifico codigo productivo, backend, frontend runtime, DB, Milvus,
  LiteLLM ni configuracion de servicios.

### 2026-06-24 - Mapa de conocimiento Mermaid

- Se agrego `team360-knowledge-map.md` como arbol de conocimiento navegable
  para `lat.md/` usando Mermaid `mindmap`.
- El mapa organiza las referencias canonicas por orquestacion global, modelo de
  producto, runtime, knowledge e IA, workers, persistencia, Console/frontend,
  seguridad, validacion, deploy y documentacion viva.
- Se enlazo el nuevo documento desde `lat.md/lat.md`.
- No se instalaron dependencias, no se genero render derivado y no se modifico
  codigo productivo, frontend, backend, DB, Milvus, LiteLLM ni servicios.

### 2026-06-24 - Politica root cause para bugs manuales

- Se agrego `team360-root-cause-debugging-policy.md` como invariante operativo
  para investigar bugs no triviales de Team360.
- La politica adapta el concepto util de gstack `/investigate`: no corregir sin
  causa raiz verificable, reproducir el sintoma, formular una hipotesis
  explicita, confirmar evidencia, aplicar fix minimo y convertir el caso en
  regresion backend/Playwright cuando corresponda.
- Se documento su uso obligatorio para bugs que aparecen en prueba manual
  aunque los tests pasen, diferencias local/produccion, interaction blocks,
  touch mobile, requests duplicados, persistencia, fallback de modelo y deploys.
- Se fijo la regla de tres hipotesis: si tres hipotesis verificadas fallan, se
  detiene el parcheo y se reporta posible problema de arquitectura, contrato,
  estado persistido o entorno.
- Se enlazo desde `lat.md/lat.md`, `AGENTS.md` y
  `.agents/skills/team360-project/SKILL.md`.
- No se instalo gstack, no se adopto su skill completo y no se modifico codigo
  productivo, frontend, backend, DB, Milvus, LiteLLM ni servicios.

### 2026-06-24 - Politica Mermaid para diagramas

- Se agrego `team360-mermaid-diagram-policy.md` como invariante documental para
  diagramas tecnicos de Team360.
- Se definio Mermaid como fuente canonica versionable en Git, embebida en
  Markdown o en archivos `.mmd` cuando el diagrama sea largo o reutilizable.
- Se establecio que SVG, PNG, PDF y Excalidraw son artefactos derivados
  opcionales, no fuente de verdad tecnica.
- Se dejo explicito que Team360 no requiere instalacion global de Mermaid y que
  cualquier render automatico futuro debe versionarse localmente en el proyecto.
- Se tomo de gstack `/diagram` solo el concepto de fuente textual revisable y
  renders derivados, sin adoptar su skill completo, telemetry, estado global,
  hooks, routing, browse daemon ni commits automaticos.
- Se actualizaron `lat.md/lat.md`, `AGENTS.md` y
  `.agents/skills/team360-project/SKILL.md`.

### 2026-06-24 - Politica rsync para deploy backend

- Se agrego `team360-backend-rsync-deploy-policy.md` como invariante operativo
  para publicar el backend de Team360 por `rsync`.
- La politica fija el flujo canonico: validar rama/HEAD, distinguir HEAD vs
  worktree, comparar con origin, ejecutar tests backend, validar SSH/destino,
  preservar `.env*` y `.venv`, crear backup remoto, revisar dry-run con
  `--delete`, ejecutar rsync real y verificar archivos remotos.
- Se establecio que el procedimiento no reinicia automaticamente el backend ni
  toca `tmux`, `systemctl`, Nginx, frontend, PostgreSQL, Milvus ni LiteLLM; el
  reinicio productivo queda como paso manual posterior en `tmux`.
- Se documento que la aprobacion requiere health remoto/interno, smoke con
  modelo real y `fallback_used=false`, smoke conversacional, 0 errores 5xx,
  0 requests duplicados y Playwright productivo.
- Se actualizaron `lat.md/lat.md`, `AGENTS.md`,
  `.agents/skills/team360-project/SKILL.md` y
  `team360-runtime-operational-policy.md` para enlazar la politica.
- No se ejecuto deploy ni se modifico produccion, backend runtime, frontend,
  DB, Milvus, LiteLLM, Nginx ni tmux.

### 2026-06-24 - Politica rsync para deploy frontend Astro

- Se agrego `team360-frontend-rsync-deploy-policy.md` como invariante
  operativo para publicar el frontend Astro de `team360.live` por `rsync`.
- La politica fija el flujo canonico: build productivo, validacion local,
  backup remoto, dry-run, rsync real, verificacion de assets servidos y smoke
  productivo.
- Se documento el destino remoto oficial, la obligacion de conservar la barra
  final en `.../astro/dist/`, el uso obligatorio de `--delete`, la revision del
  dry-run y la condicion `dist local = dist remoto = assets servidos por
  team360.live`.
- Se establecio que un rsync exitoso no prueba el despliegue: el cierre requiere
  `IS_REST_PRO=true`, `pnpm check`, build limpio, fix presente en source y
  `dist`, backup, metadata intacta, Playwright productivo, smoke UX y 0 errores
  criticos.
- Se actualizaron `lat.md/lat.md`, `AGENTS.md`,
  `.agents/skills/team360-project/SKILL.md` y la nota historica
  `SrvRestAstroLS_v1/docs/team360_live_frontend_deploy_20260618.md`.
- No se ejecuto deploy ni se modifico produccion, backend, DB, Milvus, LiteLLM
  ni Nginx.

### 2026-06-24 - Politica de validacion de navegador

- Se amplio `browser-mcp-validation-policy.md` para convertirlo en la politica
  unica de validacion de navegador de Team360.
- Se fijo Playwright + Chromium como gate E2E oficial para regresiones, flujos
  completos, interaction blocks, validaciones productivas y cierres de fase.
- Se reclasifico Browser MCP / `opencode-browser` como herramienta exploratoria
  y de diagnostico visual: ayuda a descubrir, reproducir e inspeccionar, pero
  no reemplaza Playwright como evidencia de PASS reproducible.
- Se documentaron launchers oficiales (`backend-dev.sh`, `astro-dev.sh`),
  configuracion local con `IS_REST_PRO=false`, variables estandar de
  Playwright, reglas para produccion, build productivo, pruebas moviles tactiles
  y evidencia minima ante PASS/fallo.
- Se actualizo el indice `lat.md/lat.md`, la guia
  `deepseek-v4-flash-opencode-browser.md`, `AGENTS.md` y el skill propio
  `.agents/skills/team360-project/SKILL.md` para que los agentes carguen la
  nueva jerarquia: Playwright demuestra, Browser MCP explora.
- No se modifico codigo productivo, frontend, backend, DB, Milvus, LiteLLM ni
  configuracion de servicios.

### 2026-06-22 - Refuerzo de `global.js` como control de conectividad

- Se reforzo `team360-frontend-url-source-of-truth.md` para aclarar que
  `global.js` es el unico punto de control de conectividad frontend/backend.
- Para desarrollo local, Browser MCP, Playwright real de `/t360` y validacion
  contra backend `7050`, `IS_REST_PRO` debe estar en `false` y `URL_REST_DEV`
  debe apuntar a `http://localhost:7050`.
- Se dejo explicitado que `IS_REST_PRO=true` con `URL_REST_PRO=""` usa rutas
  relativas `/api` y solo es valido si existe proxy/reverse proxy documentado.
- Se agrego la regla de no corregir conectividad de `/t360` tocando
  `astro.config.mjs`, API clients, componentes Svelte ni URLs hardcodeadas salvo
  instruccion explicita.

### 2026-06-22 - Politica general de Browser MCP

- Se agrego `browser-mcp-validation-policy.md` como regla operativa estable
  para validaciones Browser MCP / `opencode-browser` sobre Team360.
- Se fijo como precondicion que backend Litestar responda en `127.0.0.1:7050`
  y Astro en `127.0.0.1:3050` antes de iniciar la fase browser.
- Se autorizo bajar y volver a levantar solo los procesos locales de backend y
  Astro cuando sea necesario para validar contra el estado correcto; no aplica a
  PostgreSQL, Milvus ni LiteLLM salvo pedido explicito.
- Se documento que cualquier falla de Browser MCP obliga a detener la prueba,
  reportar el paso/error/estado de servidores y no reemplazar la validacion con
  terminal, `curl`, Playwright, HTML o lectura de codigo sin autorizacion.
- Se agrego la referencia `[[browser-mcp-validation-policy]]` al indice
  `lat.md/lat.md`.

### 2026-06-20 - Comando canonico de arranque productivo backend Vera

- Se actualizo `team360-runtime-operational-policy.md` con la linea canonica
  actual para levantar el backend productivo remoto de Vera:
  `uv run uvicorn ls_iMotorSoft_Srv01:app --host 127.0.0.1 --port 7050`.
- Se documento que `TEAM360_BACKEND_DEBUG` no debe definirse en produccion y
  que Litestar debe quedar con `debug=False` por defecto.
- Se aclaro la diferencia entre variables efectivas y marcadores operativos:
  `AUTOMATION_DIAGNOSIS_REPOSITORY=postgres` es el switch real de estado
  persistido; `TEAM360_EMBEDDING_VERSION` es la variable efectiva para version
  de embeddings Milvus; `TEAM360_PUBLIC_*` documenta contexto publico esperado.
- Se dejo explicitado que `/api/env` y `/api/config` son rutas de scanner
  externas y deben responder `404 Not Found` controlado, sin crear endpoints
  sensibles ni tracebacks por debug.

### 2026-06-18 - Politica Responses API para GPT-5.4 Nano

- Se aclaro en `team360-runtime-operational-policy.md` que la ruta publica
  validada de Vera sigue usando Chat Completions sin `reasoning_effort`.
- Se documento la excepcion para labs, compatibilidad o evaluaciones controladas
  con Responses API: cuando el upstream efectivo es `openai/gpt-5.4-nano`, el
  valor operativo de `reasoning.effort` debe ser `low`.
- Se dejo explicitado que `minimal` no debe usarse para ese upstream y que esta
  excepcion no cambia la configuracion principal de `/t360`.

### 2026-06-18 - Guia DeepSeek V4 Flash + opencode-browser para agentes

- Se agrego `deepseek-v4-flash-opencode-browser.md` como invariante operativo
  transversal para agentes.
- Se clasifico el uso validado de DeepSeek V4 Flash con OpenCode +
  `opencode-browser`: browser QA dirigido, smoke tests, validacion
  frontend/backend acotada, prompts atomicos, snapshots y punto de detencion.
- Se documento que `browsermcp_*` debe usarse como herramienta obligatoria
  durante la fase browser y que terminal, `curl`, HTML directo o Playwright no
  reemplazan la validacion real de UI.
- Se agregaron plantillas de prompt para navegacion minima, inspeccion de UI,
  interaccion basica, envio de mensaje, validacion frontend/backend y smoke
  repetible sobre `http://127.0.0.1:3050/t360`.
- Se enlazo el documento desde `lat.md/lat.md` y desde
  `model-selection-routing.md`.
- Se actualizaron `AGENTS.md` y `.agents/skills/team360-project/SKILL.md` para
  que la guia quede visible en el protocolo de agentes.
- No se modifico codigo productivo, runtime, frontend, backend, DB, Milvus ni
  LiteLLM.

### 2026-06-17 - Politica operativa runtime publico Vera

- Se agrego `team360-runtime-operational-policy.md` como invariante estable para
  la experiencia publica `/t360` y el endpoint `POST /api/diagnosis/turn`.
- Se documento el flujo validado: Astro/Svelte -> Litestar -> PostgreSQL 18 ->
  Milvus 2.6 -> LiteLLM -> `openai_gpt-5-nano` -> `openai/gpt-5.4-nano`.
- Se fijaron puertos operativos, variables de entorno conceptuales, coleccion
  Milvus `team360_sales_diagnosis_knowledge_v1`, modo LiteLLM
  `chat`, endpoint base `http://localhost:4000/v1` y regla de no usar OpenAI
  directo como ruta principal.
- Se documento que `global.js` es fuente efectiva de `/t360` y que el proxy
  Astro hacia `8000` es una inconsistencia conocida pendiente de unificacion.
- Se reforzaron las reglas de secretos: no imprimir DSN con password, master
  keys ni claves upstream; usar `postgresql://administrator:***@localhost:5432/team360`
  como representacion sanitizada.
- Se actualizo `lat.md/lat.md` con la referencia
  `[[team360-runtime-operational-policy]]`.

### 2026-06-16 - Frontend URL source of truth invariant

- Se agrego `team360-frontend-url-source-of-truth.md` como invariante de arquitectura frontend.
- Se fijaron 5 reglas:
  1. `global.js` es la unica fuente de verdad para endpoints REST, URLs de site y SSE.
  2. No hardcodear URLs fuera de `global.js`.
  3. Toggle dev/pro exclusivo via `IS_REST_PRO` en `global.js`.
  4. API clients en `src/lib/` deben importar desde `global.js`.
  5. `global.d.ts` debe sincronizarse con `global.js`.
- Se auditaron `src/lib/` y `src/components/` (33 archivos limpios, 3 corregidos):
  - `src/lib/api/diagnosis.ts`: migrado a `API_BASE_URL` desde global.js.
  - `MarketingFooter.astro` y `MarketingHeader.astro`: migrados a `CONSOLE_SITE_URL` desde global.js.
- Validacion: `pnpm check` = 0 errors, 0 warnings, 0 hints.
- Se actualizo `lat.md/lat.md` con referencia `[[team360-frontend-url-source-of-truth]]`.

### 2026-06-14 - Modelo T360 Pack, Task, Flow, Integrate y Diagnostico

- Se agrego `team360-pack-task-diagnosis-model.md` como invariante conceptual y comercial transversal.
- Se definieron T360 Pack, T360 Task, T360 Pack Flow, T360 Pack Integrate y modos de ejecucion Scheduled, On-Demand y Event-Driven.
- Se fijo que el Diagnostico Team360 debe diagnosticar la operacion real del cliente y traducirla en una arquitectura posible de solucion, aunque todavia no exista el Pack o Task exacta.
- Se documento la clasificacion de resultado: disponible hoy, configurable/armable, requiere desarrollo y no conviene vender todavia.
- Se reforzo la regla: automatizable no significa vendible hoy.
- Se actualizo `lat.md/lat.md` con la referencia `[[team360-pack-task-diagnosis-model]]`.
- Se actualizo `team360-global-orchestration.md` para enlazar el modelo desde decisiones globales de producto.
- No se implemento codigo, no se tocaron migraciones, runtime, frontend ni `knowledge/`.

### 2026-06-12 - Metodologia obligatoria de preflight de servicios

- Se agrego `service-preflight-methodology.md` como invariante estable para
  desarrollo, tests, smokes, benchmarks y pruebas con servicios reales.
- Se fijo la regla central: no aceptar benchmarks ni conclusiones de calidad si
  el preflight falla.
- El checklist obligatorio cubre PostgreSQL, Milvus, collection correcta,
  LiteLLM, `.bashrc`/env vars, `globalVar.py`, alias registrado en LiteLLM y
  llamada real minima al modelo para validar auth/credito/provider/endpoint.
- Se actualizo `lat.md/lat.md` con la referencia
  `[[service-preflight-methodology]]`.
- No se implemento codigo runtime ni migraciones.

### 2026-06-10 - Ajuste de ownership por rama

- Se refinó `team360-global-orchestration.md` para evitar ambigüedad entre producto funcional vivo, labs de knowledge/RAG, documentación editorial y handoff visual.
- `feature/console-backend-core` queda descrita como desarrollo funcional principal/producto funcional vivo; los labs solo aplican allí cuando validan backend runtime, assistant productivo, UX conectada o experiencia final de consola.
- `feature/knowledge-ingestion-service` queda descrita como knowledge ingestion / RAG / labs de knowledge, incluyendo pruebas RAG/asistente como efecto del knowledge package y decision notes técnicas de esa línea.
- Se actualizó el mapa rápido de ramas en `.agents/skills/team360-project/SKILL.md` y la convención operativa en `AGENTS.md`.
- No se modificó código productivo, frontend, backend runtime ni labs.

### 2026-06-10 - Orquestación global entre ramas y frentes

- Se creo `team360-global-orchestration.md` como documento transversal de arquitectura viva.
- Se documento el mapa actual de ramas (`main`, `feature/console-backend-core`, `ux/team360-console-design-handoff`, `feature/knowledge-ingestion-service`, `docs/knowledge-documents-foundation`) y sus responsabilidades.
- Se fijo la regla operativa: trabajar separado, decidir globalmente.
- Se agregaron reglas para coordinar UX real vs handoff visual, knowledge ingestion vs documentacion editorial, ownership de `lab/` por hipotesis validada y cierre de trabajo por rama.
- Se registraron decisiones globales de producto: `pkg_sales_diagnosis` evolutivo, Team360.live como primer contexto de validacion, Vera como marca visible, diagnosis mas amplio que ventas y capacidades futuras no vendibles como listas.
- Se actualizo `lat.md/lat.md` con la referencia `[[team360-global-orchestration]]`.
- No se modifico codigo productivo, migraciones, runtime, frontend ni documentos knowledge editoriales.

### 2026-06-07 - Diseno tecnico Knowledge Ingestion multi-scope / multi-nivel

- Se creo `SrvRestAstroLS_v1/docs/knowledge_ingestion_multiscope_design_20260607.md` como documento de diseno tecnico.
- El diseno referencia y extiende los invariantes existentes en `[[knowledge-scope-contract]]` y `[[ai-diagnosis-rag-runtime]]`.
- Se propusieron nuevas entidades conceptuales (KnowledgeMap, KnowledgeNode, KnowledgeAccessPolicy, KnowledgeRetrievalPolicy) que complementan el contrato canonico sin reemplazarlo.
- Se documentaron 8 niveles de scope y cascada de retrieval por capas.
- El documento es de diseno solamente; no crea nuevos invariantes en `lat.md/` ni modifica contratos existentes.
- No se implemento codigo, no se tocaron DBs ni migraciones.

### 2026-06-07 - Fase 1 Knowledge Ingestion Platform Service

- Se implemento la Fase 1 minima del servicio de ingesta, basada en el diseno tecnico.
- Migracion 006: `knowledge_ingestion_runs`, `node_path` en `knowledge_documents`, `node_path` + `permission_tags` en `knowledge_chunks`, seed de `knowledge_ingestion_worker`.
- Modulo backend `modules/knowledge_ingestion/` con schemas, repository y worker skeleton.
- 20 tests de validacion de metadata de ingesta.
- No se agregaron columnas a `knowledge_chunk_embeddings` (difiere a Fase 2).
- No se tocaron invariantes de arquitectura ni contratos existentes en `lat.md/`.

### 2026-06-07 - Fase 1.1 Hardening de Knowledge Ingestion Platform Service

- Revision sistematica de migracion 006, schemas, repository, worker y tests.
- Migration 006: se agrego `updated_at_utc`, status `running` al CHECK, manejo de `started_at_utc`.
- Schemas: validacion de node_path, area_key, topic_key, access_tags depth, source_type. Se removieron constantes no usadas (RETRIEVAL_MODES, NODE_TYPES).
- Repository: error handling explicito, started_at_utc en transicion a running, updated_at_utc en todos los updates.
- Worker: pending→running en lugar de pending→validating. Metodo `advance_phase()` stub con validacion de orden.
- Tests: 8 nuevos. Total: 30 tests. 110/110 suite completa.

### 2026-06-07 - Politica de seleccion de modelos y ruteo (gpt-5-nano, DeepSeek, Gemini)

- Se agrego `model-selection-routing.md` como invariante de arquitectura viva.
- Se documento la jerarquia de tiers (nano/mini/medium/large) con costos y distribucion objetivo 95/4/1.
- Se fijo `gpt-5-nano` como modelo economico para OpenAI directo (USD 0.05/0.40) y `google/gemini-2.5-flash-lite` como alternativa para OpenRouter.
- Se fijo DeepSeek V4 Flash como orquestador textual, no como lector de capturas.
- Se documentaron reglas de ruteo por tipo de automatizacion: SAP B1 (UI Automation > OCR > vision > humano), browser automation (Playwright > datos estructurados > modelo barato), diagnosis assistant (LiteLLM aliases).
- Se documento que los modelos deben configurarse mediante aliases LiteLLM, no hardcodearse como slugs.
- Se actualizo `lat.md/lat.md` con referencia `[[model-selection-routing]]`.
- Fuentes: `docs/analisis-tecnico/analisis_tecnico_browser_automation_modelos_ai_2026-05-08.md`, `docs/analisis-tecnico/sap_b1_modelos_vision_costos_automatizacion.md`, `docs/analisis-tecnico/team360_ai_diagnostico_stack_arango_milvus_litellm.md` y `lat.md/ai-diagnosis-rag-runtime.md`.
- No se implemento codigo, no se tocaron DBs, migraciones ni runtime.

### 2026-06-07 - Contrato publico /api/diagnosis/* wrapper backend

- Se creo `SrvRestAstroLS_v1/backend/routes/diagnosis.py` como wrapper sobre `automation_diagnosis`, compartiendo la misma instancia de servicio.
- Endpoints: `POST /api/diagnosis/start`, `POST /api/diagnosis/message`, `GET /api/diagnosis/session/{id}`.
- Stubs 501 para `submit-checklist` y `lead` (no implementados).
- No se creo motor paralelo, no se cambio scoring, service.py ni guided_flow.
- `team360_sales_diagnosis`, `pkg_sales_diagnosis`, `ks_team360_sales_diagnosis` y `svc_sales_diagnosis` se mantienen como identificadores estables.

### 2026-06-07 - Entrada publica de Vera en Home Team360

- La Home publica incorpora una primera entrada de texto libre para `Vera` como marca visible del asistente Team360.
- La implementacion reutiliza el backend existente `automation_diagnosis` mediante un adapter frontend minimo; no crea motor paralelo ni contrato definitivo `/api/diagnosis/*`.
- Se mantiene la frontera tecnica/comercial: `team360_sales_diagnosis`, `pkg_sales_diagnosis`, `ks_team360_sales_diagnosis` y `svc_sales_diagnosis` siguen siendo identificadores estables.
- El flujo publico todavia no implementa conversacion completa, captura de lead, resultado final ni L2/RAG ArangoDB/Milvus.
- El mailto queda como fallback controlado si el backend no esta disponible.

### 2026-06-07 - Representacion Console de Team360.live y Vera

- Se valido y ajusto la Console mock para representar Team360.live como cliente real y el servicio `Asistente Inteligente Vera` como servicio comercial visible.
- La navegacion mock habilita `diagnosis` para el admin cliente de Team360.live, manteniendo el flujo actual de `automation_diagnosis`.
- Los codigos tecnicos estables se mantienen como `team360_sales_diagnosis`, `pkg_sales_diagnosis`, `ks_team360_sales_diagnosis` y `svc_sales_diagnosis`; `Vera` queda como marca visible.
- El detalle de servicio deja explicito que la home publica y L2/RAG ArangoDB/Milvus no estan activos todavia.
- No se modificaron invariantes de arquitectura, motor conversacional, migraciones ni contrato `/api/diagnosis/*`.

### 2026-06-07 - Materializacion inicial de configuracion productiva Team360.live / Vera

- Se avanzo desde documentacion hacia configuracion inicial mediante seed SQL y mocks, manteniendo los invariantes de arquitectura viva.
- La configuracion productiva inicial conserva `team360_sales_diagnosis`, `pkg_sales_diagnosis` y `ks_team360_sales_diagnosis` como identificadores tecnicos estables.
- `Vera` se materializa solo como nombre comercial visible en metadata/display fields, Console label y package/service visible.
- Se mantiene `automation_diagnosis` como motor base; no se creo motor paralelo ni contrato `/api/diagnosis/*`.
- No se implemento home publica, L2/RAG ArangoDB/Milvus ni nuevas tablas de organizaciones/servicios.

### 2026-06-07 - Vera como marca comercial, no identificador tecnico

- Se actualizo `customer-packaged-assistant-instance.md` con el invariante de naming comercial/tecnico.
- Se fijo que `Vera` es nombre visible configurable y no debe usarse como identificador core de assistant instance, paquete, knowledge scope, workers, rutas, tests, migrations ni integraciones.
- Se mantienen como identificadores tecnicos estables `team360_sales_diagnosis`, `pkg_sales_diagnosis` y `ks_team360_sales_diagnosis`.
- Se agrego una nota en `automation-diagnosis.md` para aclarar que los commercial entry points son assistant instance codes tecnicos.
- La regla busca evitar migraciones, rewrites de tests, cambios de integracion o reescritura de sesiones/leads historicos ante un rebranding.
- No se implemento runtime, no se tocaron DBs, migraciones, frontend ni seeds.

### 2026-06-04 - Contrato canonico KnowledgeScope / Document / Chunk / VectorEmbedding

- Se agrego `knowledge-scope-contract.md`.
- Se formalizo el mapeo del patron probado de JudaismoEnVivo `Catalog -> MD -> Chunk -> Milvus vector` hacia Team360 `KnowledgeScope -> KnowledgeDocument -> KnowledgeChunk -> VectorEmbedding`.
- Se fijo que `knowledge_scope_id` es el equivalente de `catalog_key`, pero siempre con filtros multi-tenant obligatorios por organizacion, workspace, assistant instance, status y version.
- Se documento ArangoDB como fuente textual/grafo y Milvus como indice vectorial derivado, no fuente de verdad comercial.
- Se recomendo persistir `chunk_text` en Team360 para mejorar precision, auditoria, fuentes y control de contexto.
- Se documento fallback Arango-only y se aclaro que Milvus 2.6 es objetivo de validacion paralela, no migracion automatica.
- Se reforzo que pgvector queda como laboratorio/fallback y que no se debe migrar ArangoDB a PostgreSQL/JSONB/pgvector ahora.
- Se actualizaron `lat.md/lat.md`, `knowledge-rag-graphrag.md`, `ai-diagnosis-rag-runtime.md` y `customer-packaged-assistant-instance.md`.
- No se implemento runtime, drivers ArangoDB/Milvus, migraciones ni cambios de API.

### 2026-06-04 - Persistencia PostgreSQL 004 para automation diagnosis runtime

- Se actualizo `postgres-ai-persistence.md` para reflejar que `004_team360_automation_diagnosis_runtime.sql` fue aplicada sobre `team360`.
- Se aclaro que la migracion 004 persiste sesiones, respuestas, leads y soporte de package installation para el asistente de venta/diagnostico.
- LangGraph PostgresSaver queda reservado para una migracion futura separada, ahora referida como `005_team360_langgraph_checkpointing.sql`.
- PostgreSQL sigue siendo verdad operacional; ArangoDB/Milvus siguen como runtime RAG/knowledge inicial, no como fuente de verdad comercial.

### 2026-06-04 - Team360 como primera instalacion cliente del paquete venta/diagnostico

- Se agrego `customer-packaged-assistant-instance.md`.
- Se fijo que `team360_sales_diagnosis` no es demo interna ni caso hardcodeado: es la primera instalacion cliente del paquete de venta y diagnostico para el workspace publico de Team360.
- Se documento la forma canonica: organizacion/workspace, `automation_package`, `assistant_instance`, `package_workers`, `knowledge_scope`, lead owner, costos, eventos y auditoria.
- Se documento la frontera ArangoDB/Milvus: colecciones compartidas por dominio con filtros obligatorios por organizacion, workspace, assistant instance y knowledge scope; no una coleccion fisica por cliente como default.
- Se reservaron colecciones/base fisicamente aisladas para enterprise, compliance, volumen alto o contrato dedicado.
- Se actualizo `lat.md/lat.md`, `automation-diagnosis.md` y `ai-diagnosis-rag-runtime.md`.
- No se implemento codigo, no se tocaron DBs ni migraciones.

### 2026-06-04 - Runtime RAG inicial para diagnostico: ArangoDB + Milvus + LiteLLM

- Se agrego `ai-diagnosis-rag-runtime.md`.
- Se documento como decision estable que el primer servicio de asistente inteligente de venta y diagnostico de automatizacion debe acelerar salida reutilizando el patron probado en JudaismoenVivo: ArangoDB + Milvus + LiteLLM.
- Se documento el alcance comercial inicial: asistente `team360_sales_diagnosis` para venta directa Team360 y asistente `mamamia360_sales_diagnosis` para Mamá Mía 360 como distribuidor regional en Israel, con soporte español, ingles y hebreo.
- Se fijo que ambos asistentes comparten motor tecnico y difieren por configuracion de organizacion, workspace, canal, marca, mercado, locale, paquetes, knowledge scope, lead owner y atribucion de costos.
- Se fijo que PostgreSQL 18 sigue siendo la fuente de verdad transaccional para organizaciones, workspaces, permisos, paquetes, workers, diagnosticos, eventos, auditoria, costos y billing.
- Se aclaro que `003_team360_pgvector_knowledge_embeddings.sql` deja pgvector disponible, pero no como RAG principal de la primera salida.
- Se actualizo `console-multi-organization.md` y `automation-diagnosis.md` con la frontera de canal directo / partner.
- Se actualizo `knowledge-rag-graphrag.md` con la frontera del runtime inicial.
- Se actualizo `postgres-ai-persistence.md` para alinear pgvector como capacidad instalada/futura y no como runtime RAG primario inicial.
- Se actualizo `lat.md/lat.md` con la nueva referencia `[[ai-diagnosis-rag-runtime]]`.
- No se implemento codigo, no se tocaron DBs ni migraciones.

### 2026-06-02 - Pydantic Boundary: Pydantic no es obligatorio en repositorios ni dominio

- Se agrego la seccion `Pydantic Boundary` en `lat.md/postgres-driver-policy.md` que define:
  - Pydantic solo en bordes HTTP/API (validacion, serializacion, OpenAPI, proteccion de campos).
  - Repositorios devuelven `dict`, `dataclass`, `TypedDict` o DTO explicitos; nunca Pydantic como capa de dominio.
  - Pydantic no es fuente de verdad del dominio ni debe duplicar schema SQL.
  - ConsoleBootstrap: primero JSON/TypedDict; Pydantic se evalua cuando exista endpoint real.
  - Contratos internos simples usan `dataclass` o `TypedDict`.
- Se actualizo el resumen de Decision (linea `Repos:`) y Summary table.
- Se reemplazo el ejemplo de repositorio de Pydantic a `dataclass`.
- Se agrego la regla en `.agents/skills/team360-project/SKILL.md`: no asumir Pydantic en repositorios ni core de dominio.
- No se toco DB, migraciones, codigo runtime, v360, litellm ni temp1.txt.

### 2026-05-31 - Politica estable frontend pnpm y wrappers UI

- Se agrego referencia `[[team360-frontend-ui-policy]]` en `lat.md/lat.md`.
- Se fijo pnpm como package manager frontend obligatorio.
- Se fijo Tailwind CSS 4 + DaisyUI 5 CSS-first como stack UI inicial obligatorio.
- Se fijo que las pantallas de negocio consumen wrappers Team360 y no clases DaisyUI dispersas.
- La especificacion completa queda en `docs/frontend/` y ADR-005.

### 2026-05-31 - Correccion frontend base DaisyUI 5 + Tailwind 4

- Se corrigio la referencia estable `[[team360-frontend-base]]`.
- DaisyUI 5 queda confirmado como compatible con Tailwind 4 mediante integracion CSS-first.
- Se mantiene como invariante no reutilizar configuracion legacy ni tema `vertice360`.
- La documentacion completa y fuentes oficiales quedan en `docs/frontend/`.

### 2026-05-31 - App Shell reutilizable de Team360 Console

- Se amplio `console-multi-organization.md` con el invariante de App Shell.
- Se fijo un unico shell reutilizable y layouts compartidos, sin consolas separadas por rol.
- Se agrego la regla de no renderizar datos privados antes de validar sesion y contexto, y descartar estado obsoleto al cambiar workspace.
- Se enlazaron la guia UX de layouts y `ADR-003`.

### 2026-05-31 - Navegacion contextual de Team360 Console

- Se amplio `console-multi-organization.md` con el invariante de navegacion contextual.
- Se fijo un unico App Shell adaptable con navegacion derivada desde tipo de organizacion, permisos efectivos, workspace activo, servicios, modulos y scope permitido.
- Se enlazaron la guia UX `docs/ux/team360-console-navigation-model.md` y `ADR-002`.
- No se duplico la especificacion UX completa dentro de `lat.md/`.

### 2026-05-31 - Team360 Console multi-organizacion

- Se agrego `console-multi-organization.md` como regla estable de arquitectura viva.
- Se separaron `team360.live` como sitio comercial publico y `console.team360.live` como Team360 Console privada.
- Se definieron jerarquia de organizaciones, diferencia entre `organization` y `workspace`, alcance delegado de partners e invariante de autorizacion.
- Se registro a `Mamá Mía 360` como primera instancia configurable de `partner` para Israel, sin hardcodear reglas de producto.
- Se actualizo `lat.md/lat.md` con referencia `[[console-multi-organization]]`.

### 2026-05-29 - Driver policy psycopg 3 async

- Se agrego `postgres-driver-policy.md` como decision estable de arquitectura viva.
- Documenta que `psycopg 3 async` es el driver runtime estandar de Team360.
- Prohibe SQLAlchemy/SQLModel/asyncpg como base del core; permite excepciones solo si hay metrica concreta.
- Define patron de repositories, unit-of-work, pool, y estructura de modulos `backend/modules/db/`.
- Relacion con pgvector, LangGraph PostgresSaver y schema migrations explicitas.
- Se actualizo `lat.md/lat.md` con referencia `[[postgres-driver-policy]]`.

### 2026-05-29 - Materializacion de pgvector en fase 003

- Se actualizo `postgres-ai-persistence.md` para reflejar que la fase `003_team360_pgvector_knowledge_embeddings.sql` ya materializa pgvector sobre `team360`.
- Se mantuvo la separacion arquitectonica: embeddings en tabla propia, Team360 core como fuente de verdad y LangGraph PostgresSaver reservado para fase 004.
- No se convirtio `lat.md/` en bitacora operativa; el detalle de aplicacion y auditoria queda en `SrvRestAstroLS_v1/docs/status_actual.md`.

### 2026-05-29 - Decision Postgres AI persistence

- Se agrego `postgres-ai-persistence.md` como decision estable de arquitectura viva.
- Se documento PostgreSQL 18 como nucleo transaccional unico de Team360.
- Se separo explicitamente el modelo core Team360 de futuras capas pgvector y LangGraph PostgresSaver.
- Se fijo que LangGraph checkpoints no reemplazan `task_runs` ni `core_events`.
- Se documento la precaucion de no depender de `pg_checkpointer` sin verificar disponibilidad real.
- Se actualizo `lat.md/lat.md` con la referencia `[[postgres-ai-persistence]]`.

### 2026-05-28 - Reglas operativas de lat.md para agentes

- Se agrego en `AGENTS.md` la regla obligatoria para leer `lat.md/lat.md` ante cambios de arquitectura, dominio, IA, workers, knowledge, seguridad, paquetes o reglas transversales.
- Se agrego en `.agents/skills/team360-project/SKILL.md` el procedimiento de uso de `lat.md/`: documentos `kebab-case.md`, referencias `[[...]]`, anchors `@lat`, limites de uso y actualizacion de status local.
- Se explicito que `lat.md/` no reemplaza la bitacora tecnica `SrvRestAstroLS_v1/docs/status_actual.md`.

### 2026-05-28 - Base lat.md general de Team360

- Se creo `lat.md/lat.md` como indice raiz.
- Se agregaron documentos para:
  - plataforma Team360;
  - multi-paquete / multi-worker;
  - knowledge RAG / GraphRAG;
  - LiteLLM;
  - seguridad HITL / MFA;
  - automation diagnosis.

## Validacion

- No se movio documentacion tecnica viva desde `SrvRestAstroLS_v1/docs/`.
- `lat.md/` queda como capa de invariantes y conceptos estables anclables desde codigo.

### 2026-05-31 - Base frontend Team360 desde Vertice360

- Se agrego referencia `[[team360-frontend-base]]` en `lat.md/lat.md`.
- La documentacion completa de la base frontend queda en `docs/frontend/` y `docs/adr/ADR-004/`.
- No se implemento codigo, rutas, componentes ni migraciones.

### 2026-06-25 — Fase 1 extraccion mecanica de DiagnosticadorCore (cierre)

- Se implemento la Fase 1 descrita en `diagnosticador-embeddable-component-architecture.md`:
  extraccion mecanica del nucleo conversacional desde `PublicVeraEntry.svelte` hacia
  `DiagnosticadorCore.svelte` en `src/lib/t360/diagnosticador/`.
- `PublicVeraEntry.svelte` quedo como adapter publico con `section#vera`, layout
  comercial, ejemplos y mailto. El Core contiene el chat operativo, estado,
  persistencia, eventos y render conversacional.
- La implementacion respeta las restricciones documentadas: no se creo workspace,
  /packages, Web Component, iframe ni npm. No se movieron interaction blocks ni
  `ConsoleDiagnosis`. No se modifico backend, endpoints, `global.js` ni
  `publicVeraSession.ts`.
- Validacion estatica: `pnpm check` 0 errores, `pnpm build` OK (139 pages),
  `git diff --check` OK.
- Runtime real validado: backend `127.0.0.1:7050` (LiteLLM, Milvus, PostgreSQL),
  modelo `openai_gpt-5-nano`, `fallback_used=false`. BrowserMCP validado sin
  errores de consola.
- Playwright: 35 tests observados, 33-34 passed segun corrida, 2 skipped. Unico
  test flaky: `public-vera-mobile-sequential-blocks` (~80% pass en 5 corridas).
  Sin regresion atribuible a la extraccion.
- Estado de cierre: FASE 1 CERRADA — RUNTIME Y BROWSERMCP VALIDADOS,
  CON E2E MOVIL FLAKY DOCUMENTADO.
- Detalle completo en `SrvRestAstroLS_v1/docs/status_actual.md`.

### 2026-06-25 — Fase 2 Configuracion y sesion extraibles

- Se implemento configuracion minima tipada en `config/types.ts` y
  `config/defaults.ts` dentro de `diagnosticador/`.
- Se extrajo `state/session.ts` como modulo de sesion configurable (key por
  parametro, SSR-safe, compatible con el formato historico).
- `publicVeraSession.ts` paso a ser wrapper delgado sobre `state/session.ts`;
  su API publica no cambio.
- `DiagnosticadorCore.svelte` recibe `sessionStorageKey` y `assistantInstanceId`
  como props configurables. El Core ya no conoce key fija.
- `PublicVeraEntry.svelte` explicita la identidad de Vera:
  `assistantInstanceId="team360_sales_diagnosis"` y
  `sessionStorageKey="team360.vera.session.v1"` via constante.
- Validacion estatica: `pnpm check` 0 errores, `pnpm build` 139 pages.
- Playwright: 28 tests, todos pasan. Sin regresiones.
- Sin commit, sin cambios en backend, endpoints, tests ni config global.
- Estado de cierre: FASE 2 IMPLEMENTADA Y VALIDADA.
- Detalle completo en `SrvRestAstroLS_v1/docs/status_actual.md`.

## Pendientes recomendados

- Agregar nuevos documentos lat.md solo para conceptos estables de plataforma.
- Evitar duplicar bitacoras tecnicas: el estado de implementacion sigue en `SrvRestAstroLS_v1/docs/status_actual.md`.
