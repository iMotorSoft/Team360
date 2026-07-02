# Diagnosticador embebible — browser asset experimental v1

## Proposito

Documentar el asset JS browser real servido por Astro para hosts externos
controlados, sin crear package npm, CDN externo ni Web Component.

Regla central:

> El asset JS real debe servir el browser global existente, no crear una
> segunda implementacion.

## URL publica

```text
/embed/team360-diagnosticador.js
```

La URL publica es estable.

Internamente el build puede generar chunks auxiliares hasheados bajo:

```text
/_astro/*
```

## Ruta demo

```text
/t360-asset-demo
```

Rutas relacionadas:

```text
/t360-script-demo
/t360-mount-demo
/t360-external-host-demo
```

## Componentes

- asset estable emitido por build:
  `dist/embed/team360-diagnosticador.js`
- registro global reutilizado:
  `astro/src/lib/t360/embed/browser-global.ts`
- adapter base:
  `astro/src/lib/t360/embed/mount.ts`
- demo host:
  `astro/src/pages/t360-asset-demo.astro`
- wrapper reutilizado:
  `astro/src/lib/t360/diagnosticador/EmbedDiagnosticadorWrapper.svelte`

## Decision tecnica

Se descarto el intento con endpoint `src/pages/embed/team360-diagnosticador.js.ts`
porque `?url` sobre `browser-global.ts` generaba un `data:` import y no un
bundle browser real reutilizable.

La solucion final usa una salida minima de Rollup/Vite desde `astro.config.mjs`
para emitir un chunk estable:

```text
embed/team360-diagnosticador.js
```

El asset estable importa chunks compartidos generados por Astro/Vite cuando el
grafo del Diagnosticador lo requiere.

## Como se carga

```html
<script type="module" src="/embed/team360-diagnosticador.js"></script>
```

Luego el host puede llamar:

```js
window.Team360Diagnosticador.mount("#contenedor", {
  clientId: "local_embed_demo",
  apiBaseUrl: "http://127.0.0.1:7050/api",
  sessionStorageKey: "team360.embed.asset.demo.session.v1",
});
```

## API global

```ts
window.Team360Diagnosticador.mount(container, config)
```

Forma actual:

```ts
window.Team360Diagnosticador = {
  mount,
  version: "experimental-9c",
};
```

## Configuracion permitida

- `clientId` — requerido
- `apiBaseUrl` — requerido
- `assistantName` — opcional
- `compact` — opcional
- `initialMessage` — opcional
- `sessionStorageKey` — opcional

## Configuracion prohibida

- `hmac_secret`
- `organization_code`
- `workspace_code`
- `assistant_instance_code`
- `package_code`
- `knowledge_scope_code`
- `allowed_origins`
- `service_code`
- `template_code`

No se duplican validaciones en 9D: las sigue validando `mount.ts`.

## Arquitectura

```text
<script type="module" src="/embed/team360-diagnosticador.js">
  -> browser-global.ts
  -> window.Team360Diagnosticador.mount()
  -> mountTeam360Diagnosticador()
  -> EmbedDiagnosticadorWrapper
  -> requestEmbedTurnAuth()
  -> POST /api/diagnosis/embed/auth
  -> sendPublicTurn(embedAuth)
  -> POST /api/diagnosis/turn
  -> embed_clients (PostgreSQL)
```

## Session key

```text
team360.embed.asset.demo.session.v1
```

Debe permanecer separada de:

```text
team360.embed.script.demo.session.v1
team360.embed.mount.demo.session.v1
team360.embed.external.demo.session.v1
team360.embed.demo.session.v1
team360.vera.session.v1
```

## Seguridad

- el asset estable no contiene `clientId` ni `apiBaseUrl`;
- no expone `hmac_secret`;
- no expone tenant, scope ni `allowed_origins`;
- el host sigue usando `POST /api/diagnosis/embed/auth` y
  `POST /api/diagnosis/turn`;
- el turn embed mantiene `client_id`, `timestamp` y `X-T360-Signature`;
- `dist/embed/team360-diagnosticador.js` no contiene tenant/scope;
- chunks compartidos de `/_astro/*` siguen arrastrando contexto tecnico
  historico de Vera fuera del alcance de 9D.

## Validacion

Backend:

- `uv run pytest tests/test_diagnosis_public_router.py tests/test_embed_clients_contract.py`:
  `83 passed`
- `uv run pytest tests/ -x --ignore=tests/test_db_module.py`:
  `1089 passed, 9 skipped`

Frontend:

- `pnpm check`: `0 errors, 0 warnings, 5 hints`
- `pnpm build`: `145 page(s)`

Playwright CLI local (`PLAYWRIGHT_BASE_URL=http://127.0.0.1:3050`):

- `e2e/diagnosticador-asset-demo.spec.ts`:
  `1 passed`
- `asset + script + mount + external + embed`:
  `6 passed`
- suite focalizada Vera/lab/embed/external/mount/script/asset:
  `20 passed, 2 skipped`

Cobertura del E2E 9D:

- carga de `/t360-asset-demo`;
- `GET /embed/team360-diagnosticador.js` con `200`;
- existencia de `window.Team360Diagnosticador`;
- `mount` como funcion;
- montaje real del embed;
- request `POST /api/diagnosis/embed/auth`;
- request `POST /api/diagnosis/turn`;
- `client_id`, `timestamp` y `X-T360-Signature`;
- ausencia de tenant/scope en body embed;
- session key del asset aislada;
- Vera/script/mount/external/embed sin colision.

## MCP / runtime

- endpoint intentado: `http://localhost:8931/mcp`;
- reachability HTTP observada en esta sesion: `400 Bad Request`;
- no hubo herramientas MCP navegables expuestas en esta sesion;
- el gate efectivo se cerro con Playwright CLI sobre:
  - backend real via `backend-dev.sh`;
  - fallback estatico local sobre `astro/dist` con proxy `/api` a
    `127.0.0.1:7050`.

## Limitaciones v1

- sin package/npm;
- sin CDN externo real;
- sin Web Component;
- sin Shadow DOM;
- sin eventos `t360:*` publicos;
- el asset estable sigue dependiendo de chunks compartidos `/_astro/*`;
- `astro-dev.sh` sigue fuera del gate local mientras `global.js` mantenga el
  diff preexistente `IS_REST_PRO=true`.

## Relacion con 9E

- 9E agrega un manifest estable:
  `/embed/team360-diagnosticador.manifest.json`;
- 9E agrega un loader estable:
  `/embed/team360-diagnosticador-loader.js`;
- el asset sigue siendo la fuente browser real cargada por ese loader;
- `/t360-loader-demo` valida el mismo asset sin exponer rutas internas de
  chunks al host controlado.

## Proxima fase sugerida

Fase 9E ya queda cubierta por `docs/diagnosticador_loader_manifest_v1.md` y
`/t360-loader-demo`.
La siguiente evolucion chica recomendada es Fase 9F: empaquetado externo
controlado del loader/asset con metadata de compatibilidad y versionado mas
consistente entre manifest, loader y global.
