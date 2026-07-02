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
  "loader": "/embed/team360-diagnosticador-loader.js",
  "global": "Team360Diagnosticador",
  "api": {
    "mount": "window.Team360Diagnosticador.mount"
  },
  "requires": {
    "moduleScript": true
  }
}
```

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

- `e2e/diagnosticador-loader-demo.spec.ts`
- regresion corta con asset/script/mount/external/embed
- suite focalizada Vera/lab/embed/external/mount/script/asset/loader

## Limitaciones v1

- sin npm/package;
- sin CDN externo real;
- sin Web Component;
- sin Shadow DOM;
- sin eventos publicos `t360:*`;
- el loader sigue dependiendo del asset estable `team360-diagnosticador.js`;
- el asset estable sigue dependiendo de chunks compartidos `/_astro/*`.

## Proxima fase sugerida

Fase 9F: empaquetado externo controlado del loader/asset con metadata de
compatibilidad y versionado mas consistente entre manifest, loader y global.
