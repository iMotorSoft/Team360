# Diagnosticador embebible — browser loader fixture externo v1

## Proposito

Documentar un host HTML estatico controlado que consume el loader publico del
Diagnosticador como lo haria un tercero real: `div` + `script` + config minima.

Regla central:

> El fixture no usa Astro ni Svelte para montar el embed. Solo HTML estatico,
> el loader publico y `window.Team360Diagnosticador.mount(...)`.

## URL local

```text
/embed-fixtures/t360-external-loader.html
```

## Rutas publicas usadas

```text
/embed/team360-diagnosticador.manifest.json
/embed/team360-diagnosticador-loader.js
/embed/team360-diagnosticador.js
```

## Decision tecnica

Se elige Opcion A same-origin para esta fase:

- fixture estatico en `astro/public/embed-fixtures/`;
- sin puerto extra ni cambio DB;
- sin npm/package;
- sin Web Component;
- sin tocar `/t360`, `PublicVeraEntry.svelte` ni `global.js`.

## HTML del host

El fixture monta el Diagnosticador con:

```html
<div id="team360-diagnosticador-root"></div>
<script type="module" src="/embed/team360-diagnosticador-loader.js"></script>
<script type="module">
  await window.Team360DiagnosticadorLoader.load();
  const handle = window.Team360Diagnosticador.mount("#team360-diagnosticador-root", {
    clientId: "local_embed_demo",
    apiBaseUrl: "http://127.0.0.1:7050/api",
    assistantName: "Diagnosticador Team360",
    sessionStorageKey: "team360.embed.loader.fixture.session.v1"
  });
</script>
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

La validacion sigue viviendo en `astro/src/lib/t360/embed/mount.ts`.

## API browser

El fixture usa dos capas publicas ya existentes:

- `window.Team360DiagnosticadorLoader.load(...)`
- `window.Team360Diagnosticador.mount(container, config)`

Si `mount()` responde con handle, el fixture tambien valida:

- `destroy()`

## Session key

```text
team360.embed.loader.fixture.session.v1
```

Debe permanecer separada de:

```text
team360.vera.session.v1
team360.embed.mount.demo.session.v1
team360.embed.external.demo.session.v1
team360.embed.loader.demo.session.v1
```

## Seguridad

- no expone `hmac_secret`;
- no expone tenant/scope;
- no expone `allowed_origins`;
- el host solo conoce `clientId`, `apiBaseUrl` y props visuales seguras;
- la firma sigue siendo server-side via `POST /api/diagnosis/embed/auth`;
- el turn embed sigue enviando `client_id`, `timestamp` y
  `X-T360-Signature`.

## Validacion

Spec nuevo:

```text
e2e/diagnosticador-browser-loader-fixture.spec.ts
```

Cobertura:

- carga del fixture HTML estatico;
- existencia del loader publico y del global browser;
- mount exitoso;
- `POST /api/diagnosis/embed/auth`;
- `POST /api/diagnosis/turn`;
- `client_id`, `timestamp` y `X-T360-Signature`;
- body sin tenant/scope;
- session key aislada;
- `destroy()` operativo;
- config invalida sin requests adicionales.

## MCP / CLI

- endpoint MCP esperado: `http://localhost:8931/mcp`;
- reachability HTTP observada: `400 Bad Request`;
- si no hay herramientas navegables expuestas, el gate real sigue siendo
  Playwright CLI.

## Limitaciones

- same-origin, no cross-origin real;
- sin npm/package;
- sin Web Component;
- sin Shadow DOM;
- sin eventos publicos estables;
- sin encapsulacion CSS final para terceros;
- `astro-dev.sh` sigue bloqueado por el diff preexistente `IS_REST_PRO=true`,
  por lo que el gate local usa `backend-dev.sh` + `astro/dist` con proxy
  `/api`.

## Proxima fase sugerida

Fase chica siguiente: fixture cross-origin real controlado en puerto separado,
con `allowed_origins` explicitamente preparados para validar CORS/origin sin
mezclarlo con esta fase same-origin.

## Relacion con 9D

- 9D agrega un fixture cross-origin real en `3060/3061`;
- el fixture same-origin de este documento se conserva como baseline sin tocar
  DB;
- la validacion cross-origin y el ajuste local de `allowed_origins` quedaron
  documentados en `diagnosticador_cross_origin_fixture_v1.md`.
