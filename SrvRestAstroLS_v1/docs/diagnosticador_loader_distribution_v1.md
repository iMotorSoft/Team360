# Diagnosticador embebible — loader distribution externo v1

## Proposito

Consolidar el contrato publico minimo del embed para hosts externos controlados
sin crear todavia npm package, CDN final ni Web Component.

Regla central:

> El distribuble estable de esta fase es `manifest + loader + asset`, no un SDK
> nuevo.

Fase 9F agrega metadata de integridad opcional al manifest para verificar
`loader + asset`.

Fase 9G agrega enforcement opt-in de `entryIntegrity` dentro del loader sin
romper la API publica del embed.

Fase 9H agrega un fixture externo recomendado con `loaderIntegrity` en el host
y `verifyEntryIntegrity: true` para el entry.

Fase 9I agrega sincronizacion automatizada del `loaderIntegrity` de referencia
en el fixture externo literal y un test anti-drift contra el manifest.

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
- acepta `verifyEntryIntegrity: true` como modo opt-in;
- si `window.Team360Diagnosticador.mount` ya existe, no recarga;
- devuelve `Promise`;
- falla con error claro si el manifest responde no-`200`;
- no hace mount automatico.

Comportamiento opt-in:

- `load()` sin opciones conserva el camino compatible actual;
- el manifest default ahora se resuelve relativo al `src` real del loader,
  tambien cuando el host vive en otro origin;
- `load({ verifyEntryIntegrity: true })` exige `entryIntegrity` en el manifest;
- en modo opt-in el loader crea un `script type="module"` dinamico para el
  entry;
- aplica `integrity=manifest.entryIntegrity`;
- aplica `crossorigin="anonymous"`;
- si `entryIntegrity` falta, rechaza antes de cargar el entry;
- si el browser bloquea el entry por SRI, rechaza con error controlado.

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
  src="https://team360.live/embed/team360-diagnosticador-loader.js"
  integrity="sha256-..."
  crossorigin="anonymous"
></script>
<script>
  window.Team360DiagnosticadorLoader.load({
    verifyEntryIntegrity: true
  }).then(() => {
    window.Team360Diagnosticador.mount("#team360-diagnosticador", {
      clientId: "CLIENT_ID_PUBLICO",
      apiBaseUrl: "https://team360.live/api",
      assistantName: "Vera",
      sessionStorageKey: "team360.embed.client.session.v1"
    });
  });
</script>
```

Notas del snippet:

- el valor real de `integrity` debe salir de `loaderIntegrity` en el manifest;
- el loader obtiene `entryIntegrity` desde el manifest y lo aplica al script
  dinamico del entry cuando `verifyEntryIntegrity=true`;
- el manifest default se deriva del `src` real del loader; `manifestUrl`
  queda como override opcional si el host necesita otra ruta;
- para entorno local usar `http://127.0.0.1:3050`;
- `clientId` es publico y no reemplaza la validacion server-side;
- `hmac_secret` nunca se entrega al host;
- tenant, scope y `allowed_origins` se administran server-side;
- el host puede activar enforcement runtime del entry con:
  `load({ verifyEntryIntegrity: true })`;
- el detalle operativo de ese modo queda en
  `diagnosticador_loader_integrity_enforcement_v1.md`;
- el snippet recomendado completo queda en
  `diagnosticador_external_integrity_snippet_v1.md`.

## Compatibilidad

Se preserva compatibilidad con:

- `/t360-loader-demo`
- `/embed-fixtures/t360-external-loader.html`
- `http://127.0.0.1:3060/t360-cross-origin-loader.html`
- `http://127.0.0.1:3060/t360-cross-origin-integrity-loader.html`
- demos previas `asset`, `script`, `mount`, `external`, `embed`

## Validacion

Specs relevantes:

- `e2e/diagnosticador-loader-manifest.spec.ts`
- `e2e/diagnosticador-loader-demo.spec.ts`
- `e2e/diagnosticador-browser-loader-fixture.spec.ts`
- `e2e/diagnosticador-cross-origin-loader-fixture.spec.ts`
- `e2e/diagnosticador-cross-origin-integrity-loader-fixture.spec.ts`

Gate efectivo:

- Playwright CLI con backend `7050`;
- fallback estatico `astro/dist` en `3050` con proxy `/api`.

Sync de referencia:

- fuente de verdad: `public/embed/team360-diagnosticador.manifest.json`;
- helper de hashes: `scripts/update-embed-integrity.mjs`;
- helper de snippets/fixtures:
  `scripts/sync-embed-integrity-snippets.mjs`;
- fixture literal sincronizado:
  `e2e/fixtures/cross-origin-host/t360-cross-origin-integrity-loader.html`.

## Limitaciones

- sin npm package publicado;
- sin Web Component final;
- sin Shadow DOM;
- sin eventos publicos estables;
- enforcement runtime del entry solo opt-in;
- sin CSS encapsulado final.

## Recalculo

Helper interno:

```bash
cd SrvRestAstroLS_v1/astro
corepack pnpm build
node scripts/update-embed-integrity.mjs
node scripts/sync-embed-integrity-snippets.mjs
```

El helper recalcula `SHA-256` para:

- `public/embed/team360-diagnosticador-loader.js`;
- `dist/embed/team360-diagnosticador.js`;

y sincroniza el manifest de `public/embed` y `dist/embed`.
