# Diagnosticador embebible — browser global adapter experimental v1

## Proposito

Documentar la capa browser global experimental que expone
`window.Team360Diagnosticador.mount(...)` sobre el adapter interno de Fase 9B,
sin crear package npm, Web Component ni SDK publico final.

Regla central:

> El script global debe ser una capa fina sobre `mount.ts`.

## Ruta demo

```text
/t360-script-demo
```

Rutas relacionadas:

```text
/t360-mount-demo
/t360-external-host-demo
```

## Componentes

- registro global:
  `astro/src/lib/t360/embed/browser-global.ts`
- adapter base:
  `astro/src/lib/t360/embed/mount.ts`
- page host demo:
  `astro/src/pages/t360-script-demo.astro`
- wrapper reutilizado:
  `astro/src/lib/t360/diagnosticador/EmbedDiagnosticadorWrapper.svelte`

## API global experimental

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

Retorno:

```ts
type Team360DiagnosticadorMountHandle = {
  destroy: () => void;
};
```

## Arquitectura

```text
/t360-script-demo
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

No se duplican validaciones en el global: las valida `mount.ts`.

## Doble carga / registro

- si `window.Team360Diagnosticador` no existe, `browser-global.ts` registra el
  objeto experimental;
- si ya existe, conserva el objeto existente y no lo sobreescribe;
- el script demo reusa ese mismo objeto y no crea una segunda fuente de
  verdad.

## Session key

```text
team360.embed.script.demo.session.v1
```

Debe permanecer separada de:

```text
team360.embed.mount.demo.session.v1
team360.embed.external.demo.session.v1
team360.embed.demo.session.v1
team360.vera.session.v1
```

## Seguridad

- el host solo conoce `clientId`, `apiBaseUrl` y props visuales seguras;
- `hmac_secret` nunca viaja al navegador;
- el global no expone tenant, scope ni `allowed_origins`;
- la firma sigue siendo server-side via `POST /api/diagnosis/embed/auth`;
- el turn embed mantiene `client_id`, `timestamp` y `X-T360-Signature`;
- `/t360`, `PublicVeraEntry.svelte` y `global.js` permanecen fuera del alcance
  de esta fase.

## Validacion

Backend:

- `uv run pytest tests/test_diagnosis_public_router.py tests/test_embed_clients_contract.py`:
  `83 passed`
- `uv run pytest tests/ -x --ignore=tests/test_db_module.py`:
  `1089 passed, 9 skipped`

Frontend:

- `pnpm check`: `0 errors, 0 warnings, 5 hints`
- `pnpm build`: `144 page(s)`

Playwright CLI local (`PLAYWRIGHT_BASE_URL=http://127.0.0.1:3050`):

- `e2e/diagnosticador-script-demo.spec.ts`:
  `2 passed`
- `diagnosticador-script-demo + mount-demo + external-host-demo + embed-demo`:
  `5 passed`
- suite focalizada Vera/lab/embed/external/mount/script:
  `19 passed, 2 skipped`

Cobertura del E2E 9C:

- existencia de `window.Team360Diagnosticador`;
- `mount` como funcion;
- `version` experimental;
- `destroy()` operativo;
- request `POST /api/diagnosis/embed/auth`;
- request `POST /api/diagnosis/turn`;
- `client_id`, `timestamp` y `X-T360-Signature`;
- ausencia de tenant/scope en body embed;
- rechazo de config prohibida sin requests;
- session key del script aislada;
- Vera/mount/external/embed sin colision.

## MCP / runtime

- endpoint intentado: `http://localhost:8931/mcp`;
- reachability HTTP observada en esta sesion: `400 Bad Request`;
- no hubo herramientas MCP navegables expuestas en esta sesion;
- el gate efectivo se cerro con Playwright CLI sobre:
  - backend real via `backend-dev.sh`;
  - fallback estatico local sobre `astro/dist` con proxy `/api` a
    `127.0.0.1:7050`.

## Limitaciones v1

- registro global solo dentro del bundle Astro actual;
- sin asset JS externo versionado; 9D agrega un asset estable servido por Astro
  en `/embed/team360-diagnosticador.js`;
- sin package/npm;
- sin SDK publico estable;
- sin Web Component;
- sin Shadow DOM;
- sin eventos `t360:*` publicos;
- sin encapsulacion CSS final para terceros;
- `astro-dev.sh` sigue fuera del gate local mientras `global.js` mantenga el
  diff preexistente `IS_REST_PRO=true`.

## Relacion con 9D

- 9D agrega el asset estable `/embed/team360-diagnosticador.js`;
- el asset sigue reutilizando este registro global;
- `/t360-script-demo` sigue siendo la referencia mas simple del browser global
  dentro de una pagina Astro;
- `/t360-asset-demo` valida la misma API cargada por `src=...`.

## Proxima fase sugerida

Fases 9D y 9E ya quedan cubiertas por `/t360-asset-demo`,
`/t360-loader-demo`, `docs/diagnosticador_browser_asset_v1.md` y
`docs/diagnosticador_loader_manifest_v1.md`.
La siguiente evolucion chica recomendada es Fase 9F: empaquetado externo
controlado del loader/asset con metadata de compatibilidad y versionado mas
consistente entre manifest, loader y global.
