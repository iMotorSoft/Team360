# Diagnosticador embebible — loader integrity opcional v1

## Proposito

Documentar la metadata de integridad opcional del distribuble publico
`manifest + loader + asset` sin cambiar la API browser actual.

Regla central:

> La integridad de 9F agrega metadata de distribucion.
> 9G agrega enforcement runtime opt-in del entry sin romper `load()`.

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
  src="https://team360.live/embed/team360-diagnosticador-loader.js"
></script>
```

Snippet con integrity:

```html
<script
  src="https://team360.live/embed/team360-diagnosticador-loader.js"
  integrity="sha256-..."
  crossorigin="anonymous"
></script>
```

Notas:

- el valor real de `integrity` sale de `loaderIntegrity` en el manifest;
- el host recomendado puede combinar `loaderIntegrity` en el `<script>` con
  `load({ verifyEntryIntegrity: true })` para el entry;
- el manifest default se resuelve desde el `src` real del loader cuando el
  host no pasa `manifestUrl`;
- para local usar `http://127.0.0.1:3050`;
- `clientId` es publico;
- `hmac_secret` nunca se entrega;
- tenant, scope y `allowed_origins` quedan server-side.

## Runtime

Default compatible:

- `load()` sin opciones no exige `entryIntegrity`;
- el host sigue pudiendo usar solo `loaderIntegrity` en el `<script>` externo.

Opt-in 9G:

- `load({ verifyEntryIntegrity: true })` exige `entryIntegrity`;
- el loader aplica `integrity` al script dinamico del entry;
- el loader aplica `crossorigin="anonymous"` cuando usa integrity;
- si `entryIntegrity` falta, rechaza;
- si el browser bloquea el entry por mismatch, rechaza con error controlado.

Detalle operativo:

- `diagnosticador_loader_integrity_enforcement_v1.md`.

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
- `load()` default sigue funcionando e idempotente;
- `verifyEntryIntegrity` correcto aplica `integrity` y `crossorigin`;
- falta de `entryIntegrity` rechaza;
- `entryIntegrity` invalido rechaza;
- fixture externo con `loaderIntegrity + verifyEntryIntegrity` pasa E2E;
- `loaderIntegrity` invalido bloquea antes de `auth/turn`.

## Limitaciones

- sin package/npm;
- sin Web Component;
- enforcement runtime del entry solo opt-in;
- sin politica de rotacion de integrity por publicacion automatizada.
