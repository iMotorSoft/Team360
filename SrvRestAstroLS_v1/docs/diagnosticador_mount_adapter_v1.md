# Diagnosticador embebible — mount adapter experimental v1

## Proposito

Documentar el adapter TypeScript interno que monta el Diagnosticador Team360 en
un contenedor del DOM sin exponer `hmac_secret`, tenant ni scope al host.

Regla central:

> Esta fase crea una capa de montaje interno controlado, no un SDK publico
> final.

## Ruta demo

```text
/t360-mount-demo
```

Ruta relacionada:

```text
/t360-external-host-demo
```

## Componentes

- adapter:
  `astro/src/lib/t360/embed/mount.ts`
- componente demo cliente:
  `astro/src/lib/t360/embed/MountDiagnosticadorDemo.svelte`
- page:
  `astro/src/pages/t360-mount-demo.astro`
- wrapper reutilizado:
  `astro/src/lib/t360/diagnosticador/EmbedDiagnosticadorWrapper.svelte`

## API experimental

```ts
mountTeam360Diagnosticador(container, config)
```

Tipos v1:

```ts
type Team360DiagnosticadorMountConfig = {
  clientId: string;
  apiBaseUrl: string;
  assistantName?: string;
  compact?: boolean;
  initialMessage?: string;
  sessionStorageKey?: string;
};

type Team360DiagnosticadorMountHandle = {
  destroy: () => void;
};
```

Tambien se exporta namespace interno:

```ts
Team360Diagnosticador.mount(container, config)
```

No se expone en `window`.

## Arquitectura

```text
/t360-mount-demo
  -> MountDiagnosticadorDemo
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

## Validaciones del adapter

- `container` acepta selector string o `HTMLElement`;
- selector vacio: error;
- selector sin match: error;
- `clientId` vacio: error;
- `apiBaseUrl` vacio: error;
- clave prohibida presente: error;
- no se hacen requests si la configuracion es invalida;
- los errores no imprimen secretos ni valores completos de config.

## Session key

```text
team360.embed.mount.demo.session.v1
```

Debe permanecer separada de:

```text
team360.embed.demo.session.v1
team360.embed.external.demo.session.v1
team360.vera.session.v1
```

## Seguridad

- el host sigue usando `client_id`, `timestamp` y `X-T360-Signature`;
- el adapter no firma en frontend;
- el host no conoce tenant, scope ni `allowed_origins`;
- `hmac_secret` nunca viaja al navegador;
- la pagina demo no importa `PublicVeraEntry.svelte` ni toca `/t360`;
- los bundles compartidos del Core siguen arrastrando strings tecnicos
  historicos de Vera, preexistentes y fuera del alcance de 9B.

## Validacion

Backend:

- `uv run pytest tests/test_diagnosis_public_router.py tests/test_embed_clients_contract.py`:
  `83 passed`
- `uv run pytest tests/ -x --ignore=tests/test_db_module.py`:
  `1089 passed, 9 skipped`

Frontend:

- `pnpm check`: `0 errors, 0 warnings, 5 hints`
- `pnpm build`: `143 page(s)`

Playwright CLI local (`PLAYWRIGHT_BASE_URL=http://127.0.0.1:3050`):

- `e2e/diagnosticador-mount-demo.spec.ts`: PASS
- `e2e/diagnosticador-mount-demo.spec.ts + diagnosticador-external-host-demo.spec.ts + diagnosticador-embed-demo.spec.ts`:
  `3 passed`
- suite focalizada Vera/lab/embed/external/mount:
  `17 passed, 2 skipped`

Cobertura del nuevo E2E:

- carga de `/t360-mount-demo`;
- contenedor de montaje visible;
- wrapper montado via adapter;
- request `POST /api/diagnosis/embed/auth`;
- request `POST /api/diagnosis/turn`;
- `client_id`, `timestamp` y `X-T360-Signature`;
- ausencia de tenant/scope en body embed;
- session key del mount separada;
- Vera/external/embed demo sin colision.

## MCP / runtime

- endpoint intentado: `http://localhost:8931/mcp`;
- reachability HTTP observada en esta sesion: `400 Bad Request`;
- no hubo herramientas MCP navegables expuestas en esta sesion;
- el gate efectivo se cerro con Playwright CLI sobre:
  - backend real via `backend-dev.sh`;
  - fallback estatico local sobre `astro/dist` con proxy `/api` a
    `127.0.0.1:7050`.

## Limitaciones v1

- adapter interno; no global en `window`;
- sin package/npm;
- sin SDK publico estable;
- sin Web Component;
- sin script browser distribuible;
- sin encapsulacion CSS final para terceros;
- sin eventos `t360:*` publicos estables;
- `clientId` demo fijo en la pagina controlada;
- `astro-dev.sh` sigue fuera del gate local mientras `global.js` mantenga el
  diff preexistente `IS_REST_PRO=true`.

## Relacion con 9C

- 9C agrega `browser-global.ts` como registro controlado sobre este adapter;
- `window.Team360Diagnosticador.mount(...)` delega en
  `mountTeam360Diagnosticador(...)`;
- `/t360-mount-demo` sigue siendo la referencia interna mas simple del adapter;
- `/t360-script-demo` prueba el mismo contrato desde un global browser.

## Relacion con 9D

- 9D agrega el asset estable `/embed/team360-diagnosticador.js`;
- ese asset sigue entrando por `browser-global.ts` y termina en este adapter;
- `/t360-mount-demo` sigue siendo la referencia mas chica para validar el
  adapter sin depender del asset browser.

## Proxima fase sugerida

Fases 9C, 9D y 9E ya quedan cubiertas por `/t360-script-demo`,
`/t360-asset-demo`, `/t360-loader-demo` y sus documentos asociados.
La siguiente evolucion chica recomendada es Fase 9F: empaquetado externo
controlado del loader/asset con metadata de compatibilidad y versionado mas
consistente entre manifest, loader y global.
