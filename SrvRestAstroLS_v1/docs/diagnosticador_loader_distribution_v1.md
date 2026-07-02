# Diagnosticador embebible — loader distribution externo v1

## Proposito

Consolidar el contrato publico minimo del embed para hosts externos controlados
sin crear todavia npm package, CDN final ni Web Component.

Regla central:

> El distribuble estable de esta fase es `manifest + loader + asset`, no un SDK
> nuevo.

Fase 9F agrega metadata de integridad opcional al manifest para verificar
`loader + asset` sin cambiar la API publica del embed.

## URLs publicas estables

```text
/embed/team360-diagnosticador.manifest.json
/embed/team360-diagnosticador-loader.js
/embed/team360-diagnosticador.js
```

## Contrato publico minimo

API global:

```text
window.Team360DiagnosticadorLoader.load()
window.Team360Diagnosticador.mount(container, config)
```

Config permitida:

- `clientId`
- `apiBaseUrl`
- `assistantName`
- `compact`
- `initialMessage`
- `sessionStorageKey`

Config prohibida:

- `hmac_secret`
- `organization_code`
- `workspace_code`
- `assistant_instance_code`
- `package_code`
- `knowledge_scope_code`
- `allowed_origins`
- `service_code`
- `template_code`

## Manifest

Campos minimos actuales:

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
  "global": "Team360Diagnosticador"
}
```

Notas:

- `asset` se conserva por compatibilidad hacia atras.
- `entry` explicita el contrato de distribucion nuevo.
- `entrySha256` y `loaderSha256` permiten verificacion reproducible fuera del
  runtime.
- `entryIntegrity` y `loaderIntegrity` usan formato SRI compatible con
  `integrity="sha256-..."`.
- `version = 0.9.0-experimental` sigue siendo experimental y no implica SDK
  estable.

## Loader

Semantica actual:

- resuelve `assetUrl` explicito si el host lo pasa;
- si no, consulta el manifest estable;
- acepta `manifest.asset` o `manifest.entry`;
- si `window.Team360Diagnosticador.mount` ya existe, no recarga;
- devuelve `Promise`;
- falla con error claro si el manifest responde no-`200`;
- no hace mount automatico.

## Snippet externo copiable

Opcion simple:

```html
<div id="team360-diagnosticador"></div>
<script type="module" src="/embed/team360-diagnosticador-loader.js"></script>
<script type="module">
  await window.Team360DiagnosticadorLoader.load();
  window.Team360Diagnosticador.mount("#team360-diagnosticador", {
    clientId: "local_embed_demo",
    apiBaseUrl: "http://127.0.0.1:7050/api",
    assistantName: "Vera",
    sessionStorageKey: "team360.embed.client.session.v1"
  });
</script>
```

Opcion con integrity para el loader:

```html
<div id="team360-diagnosticador"></div>
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
  window.Team360Diagnosticador.mount("#team360-diagnosticador", {
    clientId: "local_embed_demo",
    apiBaseUrl: "http://127.0.0.1:7050/api",
    assistantName: "Vera",
    sessionStorageKey: "team360.embed.client.session.v1"
  });
</script>
```

Notas del snippet:

- el valor real de `integrity` debe salir de `loaderIntegrity` en el manifest;
- para entorno local usar `http://127.0.0.1:3050`;
- `clientId` es publico y no reemplaza la validacion server-side;
- `hmac_secret` nunca se entrega al host;
- tenant, scope y `allowed_origins` se administran server-side;
- el loader no fuerza todavia verificacion runtime del `entryIntegrity`; esa
  metadata queda disponible para verificacion offline o consumo directo del
  asset estable.

## Compatibilidad

Se preserva compatibilidad con:

- `/t360-loader-demo`
- `/embed-fixtures/t360-external-loader.html`
- `http://127.0.0.1:3060/t360-cross-origin-loader.html`
- demos previas `asset`, `script`, `mount`, `external`, `embed`

## Validacion

Specs relevantes:

- `e2e/diagnosticador-loader-manifest.spec.ts`
- `e2e/diagnosticador-loader-demo.spec.ts`
- `e2e/diagnosticador-browser-loader-fixture.spec.ts`
- `e2e/diagnosticador-cross-origin-loader-fixture.spec.ts`

Gate efectivo:

- Playwright CLI con backend `7050`;
- fallback estatico `astro/dist` en `3050` con proxy `/api`.

## Limitaciones

- sin npm package publicado;
- sin Web Component final;
- sin Shadow DOM;
- sin eventos publicos estables;
- sin enforcement runtime automatico de SRI sobre el asset cargado por el
  loader;
- sin CSS encapsulado final.

## Recalculo

Helper interno:

```bash
cd SrvRestAstroLS_v1/astro
corepack pnpm build
node scripts/update-embed-integrity.mjs
```

El helper recalcula `SHA-256` para:

- `public/embed/team360-diagnosticador-loader.js`;
- `dist/embed/team360-diagnosticador.js`;

y sincroniza el manifest de `public/embed` y `dist/embed`.
