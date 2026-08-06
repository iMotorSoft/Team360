# Release — Team360 Console UX en producción

Fecha: 2026-08-06.
Rama: `feature/console-backend-core`.
Resultado: `TEAM360_CONSOLE_UX_PRODUCTION_DEPLOY_PASS`.

## Alcance

Publicación de la adaptación UX de Team360 Console (Stages 1-8 + gates de
protección) sobre el frontend estatico de `https://team360.live`, mediante el
procedimiento canonico `lat.md/team360-frontend-rsync-deploy-policy.md`.

No se desplegaron cambios de backend, esquema, secretos, CORS, allowed origins
ni configuracion productiva. No se publico en el servidor del cliente
(Mamamia360).

## Git

- Rama: `feature/console-backend-core`.
- HEAD local desplegado: `0ac79fc` (23 commits locales sin push).
- Remoto: `origin git@github.com:iMotorSoft/Team360.git`.
- Push: no realizado.
- Worktree inicial: limpio. Worktree final: limpio (documentacion del release
  pendiente de commit).

## Baseline local

| Check | Resultado |
| --- | --- |
| `pnpm check` (con `IS_REST_PRO=true`) | 0 errores, 0 warnings, 7 hints |
| `pnpm build` | 146 paginas |
| dist | 178 archivos / 8.0 MB |
| Home / `/#vera` (DEV) | PASS (gate 7/7 + matriz) |
| Console DEV | 27/27 PASS |
| Vera real (DEV) | PASS |
| Embed DEV | 28/28 PASS |
| LAT | 0 errores |
| `git diff --check` | PASS |

## Contrato productivo

- Servidor: `vps-0bfd28fb` (administrator@imotorsoft.com).
- Usuario SSH: `administrator`.
- Directorio remoto: `/home/administrator/project/iMotorSoft/ai/Team360/SrvRestAstroLS_v1/astro/dist/`.
- Nginx: `server_name team360.live` -> root `.../astro/dist`; `/api/` -> proxy a `localhost:7050`.
- Version anterior: build del 2026-08-04 23:36 UTC (UX hasta Stage 3 + embed).
- Proceso frontend: Nginx sirve estaticos; no requiere restart.
- Backend: no tocado (respuesta de `/api` verificada).

## Backup

- Ruta: `/home/administrator/project/iMotorSoft/ai/Team360/SrvRestAstroLS_v1/astro/backups/dist_before_ux_20260806_230348.tar.gz`.
- Contenido: `dist/` completo (333 entradas), 2.5 MB, verificado legible.
- Restauracion: descomprimir el tar sobre el directorio `dist` (procedimiento
  de rollback de la politica).

## Release / publicacion

- Build productivo con `IS_REST_PRO=true` (procedimiento documentado; luego se
  restauro `global.js` a `false` para dev local).
- Dry-run revisado: 111 archivos a actualizar, 2 nuevos, 2 eliminados; sin
  rutas inesperadas.
- Rsync real: `rsync -avz --delete --itemize-changes dist/ .../astro/dist/` -> exit 0.
- 111 paginas `w/` actualizadas (Stages 4-8), `index.html` actualizado,
  2 assets hasheados rotados (`AppShell.*.js`, `global.*.css`).

## Proteccion del embed

- Loader, manifest, entry y `vera-loader.js`: **byte-identicos a produccion**
  (SHA-256 coincidentes antes y despues del deploy). No fueron reemplazados.
- `entrySha256=9d276315...`, `loaderSha256=8ee2b72f...` intactos.
- SRI, CORS, allowed origins y URLs publicas: sin cambios.
- Assets `/_astro` servidos: local = produccion (diff PASS).

## Activacion

- Mecanismo: publicacion estatica por rsync; Nginx sirve los archivos nuevos
  directamente. Sin reload/restart de procesos (politica: no reiniciar Nginx,
  backend, tmux ni servicios permanentes).

## Smoke productivo

| Validacion | Resultado |
| --- | --- |
| `/` y `/#vera` | 200, metadata/canonical/OG intactos |
| `/login/`, `/select-workspace/` | 200 |
| Rutas Console (`/w/...`) | 200 (301 de trailing slash -> 200 al seguir) |
| Console shell / stages (suites DEV) | 19/20 + shell 6/7 (2 diferencias de entorno, ver pendientes) |
| `public-home-vera-protection` | 7/7 PASS |
| Vera real (`phone-problems`) | 5/5 PASS |
| Mamamia360 embed | 6/6 PASS (auth->turn real, clientId mamamia360) |
| Matriz responsive 390/768/1280 (home, dashboard, clients, services, results, service detail, login, vera) | 24/24 PASS |
| Flujo ConsoleDiagnosis | session/start 201 + question-card (verificado) |
| 5xx / errores de red | 0 |

## Pendientes (notas de suites productivas)

- `console-shell.spec.ts:29` asume URL `/services` sin trailing slash; en
  produccion Astro/Nginx sirve `/services/` (301). Suite DEV; no se modifico.
- `console-shared-components-stage3.spec.ts:34` (formulario) clickea
  `btn-start-diagnosis` inmediatamente tras goto; contra produccion puede
  anticiparse a la hidratacion del island. El flujo funciona (verificado con
  espera). Suite DEV; no se modifico.
- No son regresiones de produccion; quedan como notas para una futura suite
  productiva dedicada.

## Rollback

- Disponible: `dist_before_ux_20260806_230348.tar.gz`.
- Metodo: mover `dist` a `dist_failed_<ts>` y extraer el backup (politica
  canonica). No fue necesario ejecutarlo.

## Servicios protegidos

```
PostgreSQL: no iniciado, detenido ni reiniciado.
Milvus: no iniciado, detenido ni reiniciado.
LiteLLM: no iniciado, detenido ni reiniciado.
```

## Cliente

```
Configuracion de Mamamia360 no modificada.
Allowed origin del cliente no modificado.
Snippet del cliente no modificado.
No se realizo deploy sobre el servidor del cliente.
```

## Comandos clave

```bash
# Build productivo
sed -i 's/const IS_REST_PRO = false;/const IS_REST_PRO = true;/' astro/src/components/global.js
cd astro && rm -rf dist && corepack pnpm build
# Backup remoto
ssh administrator@imotorsoft.com 'tar -czf .../backups/dist_before_ux_20260806_230348.tar.gz -C .../astro dist'
# Dry-run y real
rsync -avzn --delete --itemize-changes dist/ administrator@imotorsoft.com:.../astro/dist/
rsync -avz  --delete --itemize-changes dist/ administrator@imotorsoft.com:.../astro/dist/
# Restauracion de global.js a dev
sed -i 's/const IS_REST_PRO = true;/const IS_REST_PRO = false;/' astro/src/components/global.js
```
