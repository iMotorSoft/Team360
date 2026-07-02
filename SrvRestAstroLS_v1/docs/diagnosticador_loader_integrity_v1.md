# Diagnosticador embebible — loader integrity opcional v1

## Proposito

Documentar la metadata de integridad opcional del distribuble publico
`manifest + loader + asset` sin cambiar la API browser actual.

Regla central:

> La integridad de 9F agrega confianza de distribucion. No cambia
> `window.Team360DiagnosticadorLoader.load()` ni
> `window.Team360Diagnosticador.mount(...)`.

## URLs publicas

```text
/embed/team360-diagnosticador.manifest.json
/embed/team360-diagnosticador-loader.js
/embed/team360-diagnosticador.js
```

## Formato elegido

Se eligio Opcion C:

- `SHA-256` en hex para verificacion reproducible simple;
- `SRI` `sha256-...` en base64 para snippets externos con `integrity`.

Campos del manifest:

```json
{
  "entry": "/embed/team360-diagnosticador.js",
  "entrySha256": "<hex>",
  "entryIntegrity": "sha256-<base64>",
  "loader": "/embed/team360-diagnosticador-loader.js",
  "loaderSha256": "<hex>",
  "loaderIntegrity": "sha256-<base64>"
}
```

## Fuente de verdad del hash

- `loader`: `astro/public/embed/team360-diagnosticador-loader.js`
- `entry`: `astro/dist/embed/team360-diagnosticador.js`

Motivo:

- el loader es un asset estatico en `public/` y hoy coincide 1:1 con `dist/`;
- el entry estable es un chunk emitido por Vite durante `build`, por lo que el
  hash operativo debe salir del archivo real en `dist/embed/`.

## Helper de recalculo

Archivo:

```text
astro/scripts/update-embed-integrity.mjs
```

Uso:

```bash
cd SrvRestAstroLS_v1/astro
corepack pnpm build
node scripts/update-embed-integrity.mjs
```

Comportamiento:

- exige que `dist/embed/team360-diagnosticador.js` exista;
- exige que `dist/embed/team360-diagnosticador-loader.js` coincida con
  `public/embed/team360-diagnosticador-loader.js`;
- recalcula `entrySha256`, `entryIntegrity`, `loaderSha256`,
  `loaderIntegrity`;
- actualiza en formato deterministico:
  - `public/embed/team360-diagnosticador.manifest.json`;
  - `dist/embed/team360-diagnosticador.manifest.json`.

## Consumo externo

Snippet simple:

```html
<script
  type="module"
  src="https://team360.live/embed/team360-diagnosticador-loader.js"
></script>
```

Snippet con integrity:

```html
<script
  type="module"
  src="https://team360.live/embed/team360-diagnosticador-loader.js"
  integrity="sha256-..."
  crossorigin="anonymous"
></script>
```

Notas:

- el valor real de `integrity` sale de `loaderIntegrity` en el manifest;
- para local usar `http://127.0.0.1:3050`;
- `clientId` es publico;
- `hmac_secret` nunca se entrega;
- tenant, scope y `allowed_origins` quedan server-side.

## Runtime

En 9F no se fuerza enforcement runtime del `entryIntegrity`.

Motivo:

- el loader actual hace `import(assetUrl)`;
- aplicar SRI al asset dinamico agregaria complejidad cross-origin y no es
  necesario para esta fase;
- el manifest ya publica metadata suficiente para verificacion reproducible.

## Validacion

Spec principal:

```text
e2e/diagnosticador-loader-manifest.spec.ts
```

Cobertura:

- manifest `200`;
- presencia de `entry`, `loader`, `version`, `format`;
- presencia de `entrySha256`, `entryIntegrity`, `loaderSha256`,
  `loaderIntegrity`;
- coincidencia real de digest contra `loader` y `asset` servidos;
- ausencia de `hmac_secret`, tenant, scope y `allowed_origins`;
- `load()` sigue funcionando e idempotente.

## Limitaciones

- sin package/npm;
- sin Web Component;
- sin enforcement runtime del asset dinamico;
- sin politica de rotacion de integrity por publicacion automatizada.
