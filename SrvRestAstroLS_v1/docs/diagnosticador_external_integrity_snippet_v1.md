# Diagnosticador embebible - external integrity snippet v1

## Proposito

Documentar el snippet externo recomendado para terceros que quieran proteger
el loader con `loaderIntegrity` y el entry con
`load({ verifyEntryIntegrity: true })`.

## Snippet recomendado

Produccion esperada:

```html
<div id="team360-diagnosticador-root"></div>

<script
  src="https://team360.live/embed/team360-diagnosticador-loader.js"
  integrity="sha256-..."
  crossorigin="anonymous"
></script>

<script>
  window.Team360DiagnosticadorLoader.load({
    verifyEntryIntegrity: true
  }).then(() => {
    window.Team360Diagnosticador.mount("#team360-diagnosticador-root", {
      clientId: "CLIENT_ID_PUBLICO",
      apiBaseUrl: "https://team360.live/api",
      assistantName: "Vera",
      sessionStorageKey: "team360.embed.client.session.v1"
    });
  });
</script>
```

Local de validacion:

- loader: `http://127.0.0.1:3050/embed/team360-diagnosticador-loader.js`
- manifest: `http://127.0.0.1:3050/embed/team360-diagnosticador.manifest.json`
- api: `http://127.0.0.1:7050/api`
- fixture E2E: `http://127.0.0.1:3060/t360-cross-origin-integrity-loader.html`

## Fuente de cada integrity

- `loaderIntegrity` sale de `manifest.loaderIntegrity`.
- `entryIntegrity` sale de `manifest.entryIntegrity`.
- el host copia solo `loaderIntegrity` en el `<script>` remoto.
- el loader lee `entryIntegrity` internamente cuando
  `verifyEntryIntegrity=true`.

## Comportamiento esperado

- el host externo protege el loader con `integrity` y
  `crossorigin="anonymous"`;
- el loader resuelve el manifest default relativo a su propio `src`, aunque la
  pagina host viva en otro origin;
- el loader aplica `integrity` y `crossorigin="anonymous"` al script dinamico
  del entry;
- si `loaderIntegrity` no coincide, el browser bloquea el loader antes de
  `auth/turn`;
- si `entryIntegrity` falta o no coincide, `load()` rechaza y el embed no debe
  montarse.

## Lo que copia el integrador

- `clientId` publico;
- `apiBaseUrl`;
- `assistantName` opcional;
- `sessionStorageKey` propia;
- `loaderIntegrity` vigente desde el manifest.

## Lo que administra Team360 server-side

- `hmac_secret`;
- `allowed_origins`;
- resolucion tenant/scope;
- firma `X-T360-Signature`;
- autorizacion de `client_id`.

## Seguridad

- no se entrega `hmac_secret`;
- no se exponen tenant/scope;
- no se publica `allowed_origins`;
- un mismatch de integrity bloquea el mount.

## Validacion

- `e2e/diagnosticador-cross-origin-integrity-loader-fixture.spec.ts`:
  - flujo exitoso completo `loaderIntegrity + verifyEntryIntegrity + mount + auth + turn`;
  - `loaderIntegrity` invalido bloquea antes de requests;
  - `entryIntegrity` invalido rechaza antes de mount.
- `e2e/diagnosticador-loader-manifest.spec.ts` valida los digests del manifest.

## Limitaciones

- sin package/npm;
- sin Web Component;
- sin CSS encapsulado final;
- sin eventos publicos estables;
- `https://team360.live/...` es el formato objetivo del snippet, no una promesa
  de publicacion automatica en esta fase.
