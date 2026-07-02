# Diagnosticador embebible — external host demo v1

## Proposito

Documentar la ruta controlada que simula un host externo para montar el
Diagnosticador embebible sin exponer `hmac_secret`, tenant ni scope en el
HTML de la pagina anfitriona.

## Ruta

```text
/t360-external-host-demo
```

## Decision tecnica

Fase 9A adopta Opcion A:

- ruta Astro nueva dentro del repo actual;
- sin `mount()` JavaScript publico;
- sin package npm;
- sin Web Component;
- reutilizando `EmbedDiagnosticadorWrapper.svelte`.

## Arquitectura

```text
/t360-external-host-demo
  -> EmbedDiagnosticadorWrapper
  -> requestEmbedTurnAuth()
  -> POST /api/diagnosis/embed/auth
  -> sendPublicTurn(embedAuth)
  -> POST /api/diagnosis/turn
  -> embed_clients (PostgreSQL)
```

## Configuracion permitida

- `clientId`
- `apiBaseUrl`
- `assistantName`
- `compact`
- `initialMessage`
- `sessionStorageKey`

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

## Session key

Host externo controlado:

```text
team360.embed.external.demo.session.v1
```

Debe permanecer separada de:

```text
team360.embed.demo.session.v1
team360.vera.session.v1
```

## Seguridad

- el navegador solo recibe `client_id`, `timestamp` y `signature`;
- la firma viaja en `X-T360-Signature`;
- el body del turn embed no envia tenant ni scope cuando existe `embedAuth`;
- la pagina `t360-external-host-demo` no embebe secretos ni codigos
  tenant/scope en su HTML generado;
- los bundles compartidos de `DiagnosticadorCore` siguen arrastrando contexto
  publico historico de Vera, fuera del alcance de esta fase.

## Validacion

Playwright CLI:

- `e2e/diagnosticador-external-host-demo.spec.ts`: PASS
- `e2e/diagnosticador-embed-demo.spec.ts`: PASS
- `e2e/public-vera-new-conversation.spec.ts`: PASS en aislado tras 9A-Fix
- suite focalizada Vera/lab/embed/external:
  `16 passed, 2 skipped`

Cobertura del nuevo E2E:

- carga del host externo;
- wrapper visible;
- request `POST /api/diagnosis/embed/auth`;
- request `POST /api/diagnosis/turn`;
- `client_id`, `timestamp` y `X-T360-Signature`;
- ausencia de tenant/scope en el body embed;
- session key externa separada.

## MCP / runtime

- endpoint esperado: `http://localhost:8931/mcp`;
- en esta sesion no hubo herramientas navegables MCP expuestas;
- la aceptacion se valido con Playwright CLI contra:
  - backend real via `backend-dev.sh`;
  - fallback estatico local sobre `astro/dist` con proxy `/api` porque
    `astro-dev.sh` sigue bloqueado por la guarda intencional asociada al diff
    preexistente `IS_REST_PRO=true` en `global.js`.

## Relacion con 9B

- 9B agrega `/t360-mount-demo` como adapter interno experimental;
- `/t360-external-host-demo` se mantiene sin cambios de producto y sigue siendo
  la referencia de host externo controlado montado directo desde Astro;
- ambas rutas reutilizan `EmbedDiagnosticadorWrapper.svelte`, pero la ruta 9B
  pasa primero por `mount.ts`.

## Relacion con 9C

- 9C agrega `/t360-script-demo` y `window.Team360Diagnosticador.mount(...)`;
- `/t360-external-host-demo` sigue siendo la referencia del host controlado
  montado directo desde Astro, sin script global;
- las tres rutas (`external`, `mount`, `script`) comparten el mismo wrapper y
  el mismo contrato embed auth -> turn.

## Relacion con 9D

- 9D agrega `/t360-asset-demo` y el asset estable
  `/embed/team360-diagnosticador.js`;
- `/t360-external-host-demo` sigue siendo la referencia del host directo sin
  adapter ni asset browser;
- las cuatro variantes (`external`, `mount`, `script`, `asset`) validan el
  mismo contrato embed auth -> turn.

## Actualizacion 9A-Fix

- el bloqueo previo de 9A no era del adapter externo;
- la causa raiz estaba en `public-vera-new-conversation.spec.ts`, que dependia
  del backend real y de waits fijos;
- el spec se estabilizo con limpieza explicita de `team360.vera.session.v1`,
  route mocking de `/api/diagnosis/turn` y waits sobre estado interactivo real;
- `/t360-external-host-demo` siguio pasando sin cambios de producto.

## Limitaciones

- esta ruta no usa `mount()`; monta el wrapper directo desde Astro;
- no hay Web Component;
- no hay package/npm;
- no hay encapsulacion CSS completa para hosts terceros;
- no hay eventos `t360:*` publicos estables;
- `astro-dev.sh` sigue fuera del gate local mientras `global.js` mantenga el
  diff preexistente `IS_REST_PRO=true`.

## Proxima fase sugerida

Fases 9B, 9C, 9D y 9E ya quedan cubiertas por `/t360-mount-demo`,
`/t360-script-demo`, `/t360-asset-demo` y `/t360-loader-demo`.
La siguiente evolucion chica recomendada es Fase 9F: empaquetado externo
controlado del loader/asset con metadata de compatibilidad y versionado mas
consistente entre manifest, loader y global.
