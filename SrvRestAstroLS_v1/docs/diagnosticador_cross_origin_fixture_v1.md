# Diagnosticador embebible — cross-origin loader fixture v1

## Proposito

Documentar un host externo controlado en puerto separado para validar el loader
publico del Diagnosticador con `Origin` real distinto del host Astro local.

Regla central:

> El fixture corre fuera de `127.0.0.1:3050`, carga `manifest + loader + asset`
> desde `3050` y llama la API Team360 en `7050`.

## Hosts locales

Permitido:

```text
http://127.0.0.1:3060/t360-cross-origin-loader.html
```

Rechazado:

```text
http://127.0.0.1:3061/t360-cross-origin-loader.html
```

## Fixture HTML

Archivo:

```text
astro/e2e/fixtures/cross-origin-host/t360-cross-origin-loader.html
```

El host usa:

```html
<script type="module" src="http://127.0.0.1:3050/embed/team360-diagnosticador-loader.js"></script>
<script type="module">
  await window.Team360DiagnosticadorLoader.load({
    manifestUrl: "http://127.0.0.1:3050/embed/team360-diagnosticador.manifest.json"
  });
  window.Team360Diagnosticador.mount("#team360-diagnosticador-root", {
    clientId: "local_embed_demo",
    apiBaseUrl: "http://127.0.0.1:7050/api",
    assistantName: "Vera",
    sessionStorageKey: "team360.embed.cross_origin.fixture.session.v1"
  });
</script>
```

No expone:

- `hmac_secret`
- tenant
- scope
- `allowed_origins`

## Session key

```text
team360.embed.cross_origin.fixture.session.v1
```

Debe permanecer separada de:

```text
team360.vera.session.v1
team360.embed.loader.fixture.session.v1
team360.embed.mount.demo.session.v1
team360.embed.external.demo.session.v1
```

## CORS / Origin

Capas validadas:

1. `3050` sirve `loader`, `manifest` y `asset` con CORS para hosts locales
   controlados `3060/3061`.
2. `7050` responde preflight `OPTIONS` para `3060/3061`.
3. `embed_clients.allowed_origins` sigue siendo la autorizacion fina por
   `client_id`.

Decision local 9D:

- CORS backend local permite `3050`, `3060` y `3061` para que el browser pueda
  recibir respuestas;
- `local_embed_demo.allowed_origins` se ajusta solo en la DB local para incluir
  `http://127.0.0.1:3060`;
- `3061` queda fuera de `allowed_origins` y se rechaza con `403`.

## Validacion

Spec nuevo:

```text
e2e/diagnosticador-cross-origin-loader-fixture.spec.ts
```

Cobertura:

- host permitido `3060`;
- host rechazado `3061`;
- loader remoto desde `3050`;
- globales browser `window.Team360DiagnosticadorLoader` y
  `window.Team360Diagnosticador`;
- `POST /api/diagnosis/embed/auth`;
- `POST /api/diagnosis/turn`;
- `Origin` real;
- `X-T360-Signature`;
- body sin tenant/scope;
- session key aislada;
- `destroy()` operativo.

Smokes complementarios:

- `OPTIONS /api/diagnosis/embed/auth`;
- `OPTIONS /api/diagnosis/turn`;
- `POST /api/diagnosis/embed/auth` con `Origin: 3060` antes del update local:
  `403`;
- `POST /api/diagnosis/embed/auth` con `Origin: 3060` despues del update local:
  `200`;
- `POST /api/diagnosis/embed/auth` con `Origin: 3061`: `403`.

## Limitaciones

- fixture controlado solo para dev local;
- sin npm/package;
- sin Web Component;
- sin Shadow DOM;
- sin CSS encapsulado final;
- sin eventos publicos estables;
- `astro-dev.sh` sigue fuera del gate local mientras `global.js` conserve el
  diff preexistente `IS_REST_PRO=true`.

## Proxima fase sugerida

Fase chica siguiente: empaquetado externo controlado del embed con contrato
minimo de distribucion, sin romper el loader/manifest ya validados.
