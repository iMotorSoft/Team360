# Team360 Frontend — URL Source of Truth

## Propósito

Garantizar que todos los endpoints REST, URLs de site y conexiones SSE del frontend se resuelvan desde una única fuente de verdad, sin valores hardcodeados fuera de `global.js`.

## Reglas

### 1. `global.js` es la única fuente de verdad

El archivo `src/components/global.js` centraliza todas las URLs base del frontend:

- `URL_REST` — toggle dev/pro para el backend REST
- `getRestBaseUrl()` — helper que retorna `URL_REST` sin trailing slash
- `API_BASE_URL` — derivado de `getRestBaseUrl() + "/api"`
- `AGUI_BASE_URL` — derivado de `getRestBaseUrl() + "/api/agui"`
- `URL_SSE` — derivado de `getRestBaseUrl() + "/api/agui/stream"`
- `CONSOLE_SITE_URL` — URL del site de Console
- `PUBLIC_SITE_URL` — URL del site público

### 2. No hardcodear URLs fuera de `global.js`

Ningún archivo en `src/lib/`, `src/components/` ni `src/pages/` debe contener:

- URLs absolutas hardcodeadas (`http://localhost:...`, `https://console.team360.live/...`)
- Prefixes de API hardcodeados (`/api/...`, `/api/agui/...`)
- URLs de site hardcodeadas para console o site público

Toda URL debe construirse importando `URL_REST`, `getRestBaseUrl()`, `API_BASE_URL`, `CONSOLE_SITE_URL` o `PUBLIC_SITE_URL` desde `global.js`.

### 3. Toggle dev/pro con `IS_REST_PRO`

El toggle `IS_REST_PRO` en `global.js` controla si el frontend apunta al backend de desarrollo o producción. No debe replicarse este toggle en otros archivos.

Para desarrollo local, Browser MCP, Playwright real de `/t360` y validaciones
contra backend en `7050`, `IS_REST_PRO` debe estar en `false` y
`URL_REST_DEV` debe apuntar a:

```text
http://localhost:7050
```

Con `IS_REST_PRO=false`, los clientes frontend resuelven:

```text
http://localhost:7050/api
```

Si `IS_REST_PRO=true` y `URL_REST_PRO=""`, el frontend usa rutas relativas
como `/api`. Ese modo solo es valido cuando existe un reverse proxy/proxy
explicito que resuelve `/api` hacia el backend esperado. En local no debe usarse
para validar `/t360` salvo que el prompt pida y documente explicitamente el
proxy o `socat` correspondiente.

Regla operativa: no corregir conectividad de `/t360` modificando
`astro.config.mjs`, API clients, componentes Svelte o URLs hardcodeadas. El
punto de control para dev/pro es `global.js`.

### 4. Los API clients en `src/lib/` deben importar desde `global.js`

Todos los módulos en `src/lib/api/` deben importar `API_BASE_URL` o `URL_REST` desde `global.js`. Ningún API client debe definir su propio prefix.

### 5. `global.d.ts` debe mantenerse sincronizado

Cada vez que se agreguen, modifiquen o eliminen exports en `global.js`, el archivo `global.d.ts` debe actualizarse para reflejar los tipos correctos.

## Referencias

- [[team360-frontend-base]] — Stack frontend Team360
- [[team360-frontend-ui-policy]] — Política UI frontend
