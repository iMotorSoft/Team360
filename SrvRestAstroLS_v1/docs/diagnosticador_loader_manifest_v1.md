# Diagnosticador embebible — manifest y loader experimental v1

## Proposito

Documentar el contrato externo minimo para hosts controlados que no quieran
conocer el detalle de `/_astro/*`, pero todavia sin npm/package, CDN real ni
Web Component.

Regla central:

> El manifest y el loader describen y cargan el asset estable existente.
> No crean una segunda implementacion del embed.

## URLs publicas

```text
/embed/team360-diagnosticador.manifest.json
/embed/team360-diagnosticador-loader.js
/embed/team360-diagnosticador.js
```

Ruta demo:

```text
/t360-loader-demo
```

Fixture externo relacionado:

```text
/embed-fixtures/t360-external-loader.html
```

## Versionado explicito

Manifest:

```json
{
  "name": "team360-diagnosticador",
  "version": "0.9.0-experimental",
  "channel": "experimental"
}
```

Loader:

```text
window.Team360DiagnosticadorLoader.version = "experimental-9e"
```

Global del asset:

```text
window.Team360Diagnosticador.version = "experimental-9c"
```

El versionado explicito nuevo de 9E vive en el manifest y en el loader. El
asset global conserva su version interna previa porque no cambia la fuente de
verdad del embed.

## Manifest

URL:

```text
/embed/team360-diagnosticador.manifest.json
```

Contenido actual:

```json
{
  "name": "team360-diagnosticador",
  "version": "0.9.0-experimental",
  "channel": "experimental",
  "asset": "/embed/team360-diagnosticador.js",
  "entry": "/embed/team360-diagnosticador.js",
  "entrySha256": "<hex>",
  "entryIntegrity": "sha256-<base64>",
  "loader": "/embed/team360-diagnosticador-loader.js",
  "loaderSha256": "<hex>",
  "loaderIntegrity": "sha256-<base64>",
  "format": "browser-global",
  "global": "Team360Diagnosticador",
  "api": {
    "mount": "window.Team360Diagnosticador.mount",
    "auth": "POST /api/diagnosis/embed/auth",
    "turn": "POST /api/diagnosis/turn"
  },
  "requires": {
    "moduleScript": true,
    "api": "diagnosis-embed-auth-v1"
  }
}
```

Notas:

- `asset` se conserva por compatibilidad con los fixtures previos;
- `entry` formaliza la ruta de distribucion publica estable;
- `entrySha256` y `loaderSha256` publican checksum reproducible;
- `entryIntegrity` y `loaderIntegrity` publican SRI listo para snippets
  externos;
- `format = browser-global` explicita que el host espera globals, no package ni
  import map.

No expone:

- `hmac_secret`
- tenant
- scope
- `allowed_origins`
- lista de `client_id`
- metadata interna de `embed_clients`

## Loader

URL:

```text
/embed/team360-diagnosticador-loader.js
```

API:

```ts
window.Team360DiagnosticadorLoader.load(options?)
```

Forma actual:

```ts
window.Team360DiagnosticadorLoader = {
  version: "experimental-9e",
  load: async (options?: {
    assetUrl?: string;
    manifestUrl?: string;
  }) => Promise<window.Team360Diagnosticador>,
  defaults: {
    assetUrl: "/embed/team360-diagnosticador.js",
    manifestUrl: "/embed/team360-diagnosticador.manifest.json"
  }
}
```

Comportamiento:

- si `window.Team360Diagnosticador.mount` ya existe, `load()` resuelve sin
  recargar nada;
- si no existe, resuelve el asset desde `assetUrl` o desde el manifest;
- acepta `manifest.asset` o `manifest.entry`;
- carga el asset con `import(assetUrl)`;
- no hace mount automatico;
- no contiene `clientId`;
- no contiene `apiBaseUrl`;
- no conoce tenant/scope;
- no contiene secretos;
- no duplica `mount.ts`.

## Consumo desde host externo controlado

Camino directo:

```html
<script type="module" src="/embed/team360-diagnosticador.js"></script>
<script type="module">
  window.Team360Diagnosticador.mount("#target", {
    clientId: "local_embed_demo",
    apiBaseUrl: "http://127.0.0.1:7050/api",
    sessionStorageKey: "team360.embed.loader.demo.session.v1"
  });
</script>
```

Camino loader:

```html
<script type="module" src="/embed/team360-diagnosticador-loader.js"></script>
<script type="module">
  await window.Team360DiagnosticadorLoader.load();
  window.Team360Diagnosticador.mount("#target", {
    clientId: "local_embed_demo",
    apiBaseUrl: "http://127.0.0.1:7050/api",
    sessionStorageKey: "team360.embed.loader.demo.session.v1"
  });
</script>
```

Camino loader con integrity:

```html
<script
  type="module"
  src="https://team360.live/embed/team360-diagnosticador-loader.js"
  integrity="sha256-..."
  crossorigin="anonymous"
></script>
<script type="module">
  await window.Team360DiagnosticadorLoader.load({
    manifestUrl: "https://team360.live/embed/team360-diagnosticador.manifest.json"
  });
  window.Team360Diagnosticador.mount("#target", {
    clientId: "local_embed_demo",
    apiBaseUrl: "http://127.0.0.1:7050/api",
    sessionStorageKey: "team360.embed.loader.demo.session.v1"
  });
</script>
```

Notas del consumo:

- el valor real de `integrity` debe leerse desde `loaderIntegrity`;
- `entryIntegrity` queda disponible para verificacion offline o para consumo
  directo del asset estable;
- el loader actual no aplica enforcement runtime del asset dinamico.

Fixture 9C-ext:

- sirve ese mismo flujo desde HTML estatico en `public/embed-fixtures/`;
- no usa Astro ni Svelte para el host;
- valida el consumo mas cercano a un tercero real same-origin sin bundler.

Fixture 9D:

- sirve el mismo flujo desde `http://127.0.0.1:3060`;
- mantiene `loader + manifest + asset` en `3050`;
- valida CORS del asset host y validacion exacta de `Origin` en `7050`.

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

La validacion sigue viviendo en `mount.ts`.

## Seguridad

- manifest/loader/asset estables no contienen tenant/scope;
- manifest/loader/asset estables no contienen `hmac_secret`;
- el contrato embed sigue pasando por:
  - `POST /api/diagnosis/embed/auth`
  - `POST /api/diagnosis/turn`
- el navegador sigue enviando:
  - `client_id`
  - `timestamp`
  - `X-T360-Signature`

## Session key

```text
team360.embed.loader.demo.session.v1
```

Debe permanecer separada de:

```text
team360.embed.asset.demo.session.v1
team360.embed.script.demo.session.v1
team360.embed.mount.demo.session.v1
team360.embed.external.demo.session.v1
team360.embed.demo.session.v1
team360.vera.session.v1
```

## Validacion

Backend:

- `uv run pytest tests/test_diagnosis_public_router.py tests/test_embed_clients_contract.py`
- `uv run pytest tests/ -x --ignore=tests/test_db_module.py`

Frontend:

- `pnpm check`
- `pnpm build`

Playwright CLI:

- `e2e/diagnosticador-loader-manifest.spec.ts`
- `e2e/diagnosticador-loader-demo.spec.ts`
- `e2e/diagnosticador-browser-loader-fixture.spec.ts`
- regresion corta con asset/script/mount/external/embed
- suite focalizada Vera/lab/embed/external/mount/script/asset/loader/fixture

Ver tambien:

- `docs/diagnosticador_loader_distribution_v1.md`
- `docs/diagnosticador_loader_integrity_v1.md`

## Limitaciones v1

- sin npm/package;
- sin CDN externo real;
- sin Web Component;
- sin Shadow DOM;
- sin eventos publicos `t360:*`;
- el loader sigue dependiendo del asset estable `team360-diagnosticador.js`;
- el asset estable sigue dependiendo de chunks compartidos `/_astro/*`.

## Recalculo

```bash
cd SrvRestAstroLS_v1/astro
corepack pnpm build
node scripts/update-embed-integrity.mjs
```

## Proxima fase sugerida

Fase chica siguiente: consumo directo del asset estable con enforcement opt-in
del `entryIntegrity`, sin romper el loader actual ni los fixtures existentes.
