# Diagnosticador embebible — wrapper interno/demo v1

## Proposito

Documentar el wrapper embebible interno/demo usado para validar el contrato
publico controlado v1 sin exponer `hmac_secret` al navegador.

## Ruta demo

```text
/t360-embed-demo
```

Ruta host externo controlado relacionada:

```text
/t360-external-host-demo
```

## Componentes

- page:
  `astro/src/pages/t360-embed-demo.astro`
- wrapper:
  `astro/src/lib/t360/diagnosticador/EmbedDiagnosticadorWrapper.svelte`
- core reutilizado:
  `astro/src/lib/t360/diagnosticador/DiagnosticadorCore.svelte`

## Arquitectura

```text
/t360-embed-demo
  -> EmbedDiagnosticadorWrapper
  -> turnAuthProvider
  -> POST /api/diagnosis/embed/auth
  -> sendPublicTurn(embedAuth)
  -> POST /api/diagnosis/turn
  -> embed_clients (PostgreSQL)
  -> AssistantConversationRuntime
```

## Props publicas permitidas

- `apiBaseUrl` — requerido
- `clientId` — requerido
- `assistantName` — opcional
- `compact` — opcional
- `initialMessage` — opcional
- `sessionStorageKey` — opcional, para aislar hosts controlados

## Props prohibidas

No deben exponerse en el wrapper:

- `hmac_secret`
- `organization_code`
- `workspace_code`
- `assistant_instance_code`
- `package_code`
- `knowledge_scope_code`
- `service_code`
- `template_code`
- `allowed_origins`

## Contrato de auth

El wrapper no firma en frontend.

Pide una firma server-side a:

```text
POST /api/diagnosis/embed/auth
```

Y recibe:

```json
{
  "client_id": "local_embed_demo",
  "timestamp": 1780000000,
  "signature": "sha256=..."
}
```

Luego llama:

```text
POST /api/diagnosis/turn
```

con:

- body:
  - `client_id`
  - `timestamp`
  - `session_id`
  - `message`
  - `locale`
  - `interaction_response` cuando aplique
- header:
  - `X-T360-Signature`

Cuando `embedAuth` existe, el frontend no envia tenant/scopes.

Decision 8B:

- se conserva `/api/diagnosis/embed/auth` como contrato publico controlado v1;
- no se agrega token efimero en esta fase;
- el wrapper sigue siendo interno/demo, pero ya usa el mismo contrato que la
  integracion publica controlada.

Decision 8C:

- el wrapper no cambia visualmente;
- cuando `embed/auth` responde `429`, el frontend sigue mostrando error
  generico sin exponer detalles de rate limit;
- no se agregan props nuevas ni se expone telemetria sensible al navegador.

## Session key

```text
team360.embed.demo.session.v1
```

Debe permanecer separada de:

```text
team360.vera.session.v1
team360.embed.external.demo.session.v1
```

## Seguridad

- `hmac_secret` nunca viaja al navegador;
- no se usa `PUBLIC_*` para el secreto;
- no se guarda en `sessionStorage` ni `localStorage`;
- no aparece en HTML generado ni en `dist`;
- el navegador solo conoce `client_id`, `timestamp`, `signature`.

## Validacion

- backend:
  - endpoint de firma probado por `pytest`
  - auth -> turn real validado contra backend `7050`
- frontend:
  - `pnpm check`
  - `pnpm build`
  - Playwright CLI:
    `e2e/diagnosticador-embed-demo.spec.ts`
- contrato operativo 8C:
  - `429` generico cuando se excede el rate limit;
  - sin `signature` en la respuesta limitada;
  - sin cambios en `/t360` ni en `PublicVeraEntry.svelte`.

## MCP / Playwright

Endpoint MCP esperado:

```text
http://localhost:8931/mcp
```

En Fase 8A/8B el endpoint quedo reachable a nivel HTTP, pero el cierre
efectivo se hizo con Playwright CLI porque no hubo herramientas MCP navegables
expuestas en esta sesion.

## Limitaciones v1

- wrapper interno/demo, no publico;
- `clientId` fijo de demo (`local_embed_demo`);
- sin script global distribuible final; 9C agrega solo un registro browser
  experimental controlado dentro del bundle Astro;
- sin token efimero;
- sin SDK;
- sin Web Component;
- sin iframe;
- sin alta dinamica de clientes;
- sin rotacion/vault del secret;
- sin contrato externo definitivo.

## Gate E2E 8B

- `e2e/diagnosticador-embed-demo.spec.ts`: valida auth response publica,
  header `X-T360-Signature`, body embed sin tenant/scope y session key aislada;
- `e2e/diagnosticador-embed-lab.spec.ts`: valida aislamiento de tabs y payload
  del lab via route mocking para no depender del diff preexistente de
  `global.js`;
- `e2e/public-vera.spec.ts` y
  `e2e/public-vera-new-conversation.spec.ts`: quedan estabilizados sobre el
  entorno local correcto sin tocar `/t360`; en 9A-Fix el spec de "new
  conversation" se endurecio con limpieza explicita de sessionStorage y route
  mocking para eliminar timing fragil del backend real.

## Relacion con 9C

- 9C agrega `window.Team360Diagnosticador.mount(...)` como capa fina sobre
  `mount.ts`;
- el wrapper no cambia contrato ni props publicas;
- `/t360-script-demo` prueba el mismo wrapper desde un script global
  experimental, todavia sin asset JS externo estable.

## Relacion con 9D

- 9D agrega `/embed/team360-diagnosticador.js` como asset estable servido por
  Astro;
- el wrapper no cambia contrato ni props publicas;
- `/t360-asset-demo` valida el mismo wrapper cargado desde un `script src`
  real, sin npm ni Web Component.

## Proxima fase sugerida

Fases 9A, 9B, 9C, 9D y 9E ya quedan cubiertas por
`/t360-external-host-demo`, `/t360-mount-demo`, `/t360-script-demo`,
`/t360-asset-demo` y `/t360-loader-demo`.
La siguiente evolucion chica recomendada es Fase 9F: empaquetado externo
controlado del loader/asset con metadata de compatibilidad y versionado mas
consistente entre manifest, loader y global.
