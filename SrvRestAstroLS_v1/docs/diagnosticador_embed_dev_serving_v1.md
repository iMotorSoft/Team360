# Diagnosticador embebible — serving local DEV v1

Este documento registra el Gate 3B que alinea el runtime oficial de desarrollo con el artefacto embebible generado, sin modificar la cadena productiva.

## Causa raíz

El plugin `team360-diagnosticador-browser-asset` se ejecuta sólo durante `astro build`. El build emite `dist/embed/team360-diagnosticador.js` y sus dependencias hasheadas bajo `dist/_astro`, mientras `astro dev` sirve `public` y el grafo fuente de Vite, pero no `dist`.

El manifest y loader respondían porque son fuentes versionadas en `public/embed`. El entry devolvía 404 porque existe únicamente como salida de build. Producción no presenta esa diferencia: el procedimiento oficial publica el contenido completo de `dist/`, incluyendo `/embed` y `/_astro`.

## Solución DEV

`astro-dev.sh` ejecuta un build local antes de iniciar Astro y usa `astro.config.dev.mjs`. Ese config ignora los artefactos de reporte Playwright para evitar recargas ajenas a la aplicación y agrega un middleware exclusivo de `serve` que expone solamente:

- `/embed/team360-diagnosticador.js` desde el build local;
- el cierre de imports locales requerido por ese entry bajo `/_astro`;
- un manifest DEV generado en memoria con `entrySha256` y `entryIntegrity` del entry local.

El middleware usa una allowlist calculada desde el grafo de imports, rechaza dependencias fuera de `/_astro`, valida que loader público y loader de `dist` sean idénticos y verifica la metadata protegida del loader antes de iniciar. Para esas respuestas replica el CORS local restringido de Vite: refleja únicamente origins `localhost` o `127.0.0.1`, agrega `Vary: Origin` y no introduce wildcard.

## Protección productiva

La solución no modifica `astro.config.mjs`, loader, manifest en disco, entry fuente, SRI productivo, CORS, CSP, allowed origins, URLs públicas ni procedimiento de publicación. `astro.config.dev.mjs` se usa únicamente cuando el launcher local lo selecciona de manera explícita.

El manifest DEV conserva todos los campos productivos y sustituye en memoria sólo los dos digests del entry construido localmente. Esto permite verificar SRI contra los bytes realmente servidos sin reescribir el manifest versionado.

Los E2E que montan mediante el browser global se sincronizan con `VeraEmbedWrapper`, adoptado previamente por `mount.ts`: validan `vera-embed-wrapper` en lugar del selector histórico del wrapper demo interno, sin cambiar el comportamiento esperado.

## Operación

El flujo reproducible es:

```bash
cd SrvRestAstroLS_v1
./backend-dev.sh
./astro-dev.sh
```

El launcher falla de manera visible si el build, el entry, una dependencia, el loader o su metadata protegida no son válidos. Repetir el comando vuelve a construir el mismo estado local y no escribe sobre producción.

## Gate

La validación requerida comprende serving HTTP, MIME, hashes, SRI positivo y negativo, cross-origin permitido y denegado, mount, interacción real, destrucción, `/t360`, shell, componentes de Etapa 3, `pnpm check`, `pnpm build`, gates LAT y `git diff --check`.
