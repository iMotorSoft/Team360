# Diagnosticador embebible - entryIntegrity enforcement opt-in v1

## Proposito

Documentar el enforcement runtime opt-in de `entryIntegrity` en el loader
publico del Diagnosticador sin romper el camino compatible actual.

Regla central:

> La verificacion runtime del asset principal es opt-in.
> `load()` sin opciones sigue siendo compatible.

## API publica

Compatibilidad preservada:

```text
window.Team360DiagnosticadorLoader.load()
window.Team360Diagnosticador.mount(container, config)
```

Opt-in nuevo:

```js
await window.Team360DiagnosticadorLoader.load({
  verifyEntryIntegrity: true
});
```

La opcion puede combinarse con `manifestUrl` cuando el host necesita apuntar a
un manifest explicito:

```js
await window.Team360DiagnosticadorLoader.load({
  manifestUrl: "https://team360.live/embed/team360-diagnosticador.manifest.json",
  verifyEntryIntegrity: true
});
```

## Manifest usado

Campos leidos por el loader cuando `verifyEntryIntegrity=true`:

```json
{
  "entry": "/embed/team360-diagnosticador.js",
  "entryIntegrity": "sha256-<base64>"
}
```

Notas:

- `entry` se resuelve contra la URL real del manifest;
- `asset` sigue aceptado por compatibilidad;
- si el host ya paso `assetUrl`, el loader exige que coincida con el `entry`
  resuelto desde el manifest antes de aplicar integrity.

## Comportamiento

### Default compatible

```js
await window.Team360DiagnosticadorLoader.load();
```

Hace:

- fetch del manifest;
- resolucion de `entry`;
- carga del asset principal;
- sin `integrity`;
- sin `crossorigin`;
- idempotencia preservada.

### Opt-in seguro

```js
await window.Team360DiagnosticadorLoader.load({
  verifyEntryIntegrity: true
});
```

Hace:

- fetch del manifest;
- lectura de `entryIntegrity`;
- creacion de `script type="module"` dinamico para el entry;
- `script.integrity = manifest.entryIntegrity`;
- `script.crossOrigin = "anonymous"`;
- rechazo controlado si `entryIntegrity` falta;
- rechazo controlado si el browser bloquea la carga por mismatch.

## Errores controlados

Falta `entryIntegrity`:

```text
Team360DiagnosticadorLoader: entry integrity is required when verifyEntryIntegrity=true.
```

Integrity invalido o carga bloqueada:

```text
Team360DiagnosticadorLoader: entry script failed to load or failed integrity verification.
```

Los errores no exponen secretos, tenant, scope ni `allowed_origins`.

## Idempotencia

Si `window.Team360Diagnosticador.mount` ya existe:

- `load()` resuelve con el global existente;
- no duplica scripts;
- no revalida una carga ya realizada.

Limitacion:

> El enforcement protege cargas nuevas del entry.
> No puede revalidar un asset ya cargado antes de llamar `load({ verifyEntryIntegrity: true })`.

## Validacion

Spec principal:

```text
e2e/diagnosticador-loader-manifest.spec.ts
```

Cobertura agregada:

- `load()` default sin integrity;
- `load({ verifyEntryIntegrity: true })` con `integrity` correcto;
- manifest sin `entryIntegrity` -> rechazo controlado;
- manifest con `entryIntegrity` invalido -> rechazo controlado;
- idempotencia preservada en ambos caminos.

Gate E2E relacionado:

- `e2e/diagnosticador-cross-origin-loader-fixture.spec.ts`
- `e2e/diagnosticador-browser-loader-fixture.spec.ts`
- `e2e/diagnosticador-mount-demo.spec.ts`
- `e2e/diagnosticador-external-host-demo.spec.ts`
- `e2e/diagnosticador-embed-demo.spec.ts`

## MCP / CLI

- MCP intentado en `http://localhost:8931/mcp`;
- si no expone herramientas navegables, el gate real sigue siendo Playwright
  CLI;
- el enforcement se valido con Playwright CLI sobre runtime local real
  `3050/7050`.

## Alcance fuera de esta fase

- sin package/npm;
- sin Web Component;
- sin Shadow DOM;
- sin enforcement del `loaderIntegrity` desde el mismo loader;
- sin rotacion automatizada por publicacion;
- sin CSS encapsulado final;
- sin eventos publicos definitivos.
