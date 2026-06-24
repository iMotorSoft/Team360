# Politica de despliegue frontend Astro por rsync - Team360

## Objetivo

Definir el procedimiento unico para:

```text
build productivo de Astro
-> validacion local
-> backup remoto
-> dry-run
-> rsync real
-> verificacion de assets servidos
-> smoke productivo
```

Esta politica aplica al frontend publico de Team360 servido desde:

```text
https://team360.live
```

## Directorios locales

Proyecto:

```text
/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/SrvRestAstroLS_v1
```

Frontend:

```text
/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/SrvRestAstroLS_v1/astro
```

Directorio generado:

```text
SrvRestAstroLS_v1/astro/dist/
```

## Destino remoto oficial

Destino productivo:

```text
administrator@imotorsoft.com:/home/administrator/project/iMotorSoft/ai/Team360/SrvRestAstroLS_v1/astro/dist/
```

La barra final debe conservarse:

```text
.../astro/dist/
```

Origen:

```text
dist/
```

Destino:

```text
.../astro/dist/
```

Esto copia el contenido de `dist/` dentro del `dist/` remoto.

No debe generarse accidentalmente:

```text
astro/dist/dist/
```

## Comando oficial

Dry-run:

```bash
rsync -avzn --delete \
  --itemize-changes \
  dist/ \
  administrator@imotorsoft.com:/home/administrator/project/iMotorSoft/ai/Team360/SrvRestAstroLS_v1/astro/dist/
```

Rsync real:

```bash
rsync -avz --delete \
  --itemize-changes \
  dist/ \
  administrator@imotorsoft.com:/home/administrator/project/iMotorSoft/ai/Team360/SrvRestAstroLS_v1/astro/dist/
```

La unica diferencia permitida entre ambos comandos es:

```text
-avzn
```

por:

```text
-avz
```

No cambiar origen, destino ni `--delete` entre dry-run y ejecucion real.

## Configuracion productiva obligatoria

Antes del build, verificar:

```text
SrvRestAstroLS_v1/astro/src/components/global.js
```

Debe contener:

```javascript
const IS_REST_PRO = true;
```

Comprobar desde `SrvRestAstroLS_v1/astro`:

```bash
grep -n "IS_REST_PRO" src/components/global.js
```

Regla:

```text
IS_REST_PRO=false -> desarrollo local y Playwright local
IS_REST_PRO=true  -> build productivo
```

Nunca desplegar un `dist/` generado con:

```javascript
const IS_REST_PRO = false;
```

## Estado Git antes del build

Ejecutar desde `SrvRestAstroLS_v1`:

```bash
cd /media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/SrvRestAstroLS_v1

git branch --show-current
git rev-parse --short HEAD
git status --short
git log -10 --oneline
```

Registrar:

```text
rama
HEAD
worktree
cambios locales
commits no pusheados
```

Rama esperada actualmente:

```text
feature/console-backend-core
```

No cambiar de rama automaticamente.

No hacer merge, rebase, pull ni push durante el despliegue salvo instruccion
explicita.

## Build productivo limpio

Desde:

```bash
cd /media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/SrvRestAstroLS_v1/astro
```

Ejecutar:

```bash
corepack pnpm check
```

Debe finalizar con:

```text
0 errores
```

Luego eliminar el build anterior:

```bash
rm -rf dist
```

Generar uno nuevo:

```bash
corepack pnpm build
```

Validar:

```bash
test -f dist/index.html
find dist -type f | wc -l
du -sh dist
```

No sincronizar un `dist/` viejo o generado antes de los ultimos cambios.

## Verificar que el fix este en el source

Antes del build, buscar los cambios que se esperan desplegar.

Ejemplo para interaction blocks:

```bash
rg -n \
  "consumed|answered|data-interaction-state" \
  src/components/diagnosis/PublicVeraEntry.svelte \
  src/lib/t360/interaction/T360InteractionRenderer.svelte
```

No hacer el despliegue si el source no contiene el cambio esperado.

## Verificar que el fix este en el build

Despues del build:

```bash
rg -n \
  "data-interaction-state|requires-response|answered" \
  dist \
  | head -30
```

Los nombres internos pueden quedar minificados, pero deben aparecer evidencias
publicas o atributos estables del fix.

No declarar valido un build solo porque `pnpm build` termino correctamente.
Debe comprobarse que contiene la funcionalidad que se intenta desplegar.

## Validar SSH y destino

Ejecutar:

```bash
ssh administrator@imotorsoft.com '
  echo SSH_OK
  hostname

  TARGET=/home/administrator/project/iMotorSoft/ai/Team360/SrvRestAstroLS_v1/astro/dist

  test -d "$TARGET"
  ls -ld "$TARGET"
'
```

Si el destino no existe o no coincide con la ruta servida por Nginx:

```text
DETENER
```

No crear otra ruta sin confirmar la configuracion productiva.

## Confirmar la ruta servida por Nginx

Cuando exista alguna duda:

```bash
ssh administrator@imotorsoft.com '
  nginx -T 2>/dev/null \
    | grep -n -E "server_name|root |alias "
'
```

Confirmar que:

```text
server_name team360.live
```

sirve:

```text
/home/administrator/project/iMotorSoft/ai/Team360/SrvRestAstroLS_v1/astro/dist/
```

No modificar Nginx durante un despliegue normal de archivos estaticos.

## Backup remoto obligatorio

Antes del rsync real:

```bash
ssh administrator@imotorsoft.com '
  set -e

  BASE=/home/administrator/project/iMotorSoft/ai/Team360/SrvRestAstroLS_v1/astro
  BACKUP_DIR="$BASE/backups"
  TS=$(date +%Y%m%d_%H%M%S)

  mkdir -p "$BACKUP_DIR"

  tar -czf "$BACKUP_DIR/dist_before_${TS}.tar.gz" \
    -C "$BASE" dist

  echo "BACKUP=$BACKUP_DIR/dist_before_${TS}.tar.gz"
  ls -lh "$BACKUP_DIR/dist_before_${TS}.tar.gz"
'
```

Registrar la ruta exacta del backup.

No borrar backups anteriores durante el deploy.

## Dry-run obligatorio

Desde el directorio `SrvRestAstroLS_v1/astro`:

```bash
rsync -avzn --delete \
  --itemize-changes \
  dist/ \
  administrator@imotorsoft.com:/home/administrator/project/iMotorSoft/ai/Team360/SrvRestAstroLS_v1/astro/dist/ \
  | tee /tmp/team360-frontend-rsync-dry-run.txt
```

No ejecutar el rsync real antes de revisar esta salida.

## Como interpretar el dry-run

Clasificar:

```text
archivos nuevos
archivos modificados
assets eliminados
HTML actualizado
CSS actualizado
JavaScript actualizado
```

Lineas importantes:

```text
*deleting
```

En builds Astro es normal eliminar assets viejos con hash, por ejemplo:

```text
_astro/PublicVeraEntry.OLDHASH.js
_astro/T360InteractionRenderer.OLDHASH.js
```

No es normal eliminar archivos fuera del arbol de build.

Bloquear si aparecen rutas inesperadas o que no pertenecen a `dist/`.

## Uso de `--delete`

La opcion:

```text
--delete
```

elimina del destino los archivos que ya no existen en el `dist/` local.

Es necesaria para evitar:

```text
assets viejos
bundles obsoletos
HTML apuntando a combinaciones inconsistentes
acumulacion de hashes anteriores
```

Solo es segura porque el destino debe contener exclusivamente el build
estatico.

No usar este comando sobre una carpeta que incluya:

```text
uploads
logs
configuracion manual
backups
datos persistentes
```

## Rsync real

Solo si:

```text
IS_REST_PRO=true
pnpm check PASS
build PASS
fix presente en source
fix presente en dist
SSH PASS
destino correcto
backup creado
dry-run revisado
```

Ejecutar:

```bash
rsync -avz --delete \
  --itemize-changes \
  dist/ \
  administrator@imotorsoft.com:/home/administrator/project/iMotorSoft/ai/Team360/SrvRestAstroLS_v1/astro/dist/ \
  | tee /tmp/team360-frontend-rsync-real.txt
```

No modificar otros directorios remotos.

## No reiniciar servicios

Para un despliegue normal de archivos estaticos Astro:

```text
no reiniciar backend
no tocar tmux
no reiniciar PostgreSQL
no reiniciar Milvus
no reiniciar LiteLLM
no reiniciar Nginx
```

Nginx sirve los archivos nuevos directamente.

Solo se requiere reload si se modifica su configuracion, lo cual no forma parte
de este procedimiento.

## Verificacion remota

Despues del rsync:

```bash
ssh administrator@imotorsoft.com '
  TARGET=/home/administrator/project/iMotorSoft/ai/Team360/SrvRestAstroLS_v1/astro/dist

  test -f "$TARGET/index.html"
  echo REMOTE_INDEX_OK

  find "$TARGET" -type f | wc -l
  du -sh "$TARGET"
  stat "$TARGET/index.html"
'
```

Confirmar:

```text
index.html actualizado
cantidad de archivos razonable
tamano razonable
```

## Comparar assets local y produccion

Local:

```bash
grep -oE '/_astro/[^"]+\.(js|css)' \
  dist/index.html \
  | sort -u \
  > /tmp/team360-assets-local.txt
```

Produccion:

```bash
curl -sS https://team360.live/ \
  | grep -oE '/_astro/[^"]+\.(js|css)' \
  | sort -u \
  > /tmp/team360-assets-prod.txt
```

Comparar:

```bash
diff -u \
  /tmp/team360-assets-local.txt \
  /tmp/team360-assets-prod.txt
```

Esperado:

```text
sin diferencias
```

La condicion de aprobacion es:

```text
dist local
=
dist remoto
=
assets servidos por team360.live
```

## Verificar metadata

Ejecutar:

```bash
curl -sS -D /tmp/team360-prod-headers.txt \
  -o /tmp/team360-prod-index.html \
  https://team360.live/
```

Validar:

```bash
head -20 /tmp/team360-prod-headers.txt

grep -Ei \
  '<title>|canonical|og:title|og:image|twitter:' \
  /tmp/team360-prod-index.html \
  | head -30
```

Esperado:

```text
HTTP 200
title correcto
canonical correcto
Open Graph completo
Twitter metadata completa
```

## Playwright productivo obligatorio

Despues del despliegue, ejecutar primero el caso especifico:

```bash
PLAYWRIGHT_SKIP_WEBSERVER=1 \
PLAYWRIGHT_BASE_URL=https://team360.live \
corepack pnpm exec playwright test \
  e2e/public-vera-phone-problems-interaction-priority.spec.ts \
  --project=chromium \
  --workers=1 \
  --reporter=line
```

No usar localhost.

No levantar Astro local.

No usar multiples workers contra produccion.

## Que validar en la UX

Para interaction blocks:

```text
requires-response
-> seleccion
-> submit
-> answered
```

Validar:

```text
botones activos
seleccion visible
contador actualizado
submit habilitado
request unico
estado answered
nuevo bloque activo
sin herencia de disabled
sin bloques simultaneos
```

Para movil, usar ademas:

```text
hasTouch=true
isMobile=true
tap()
```

## Smoke manual

Abrir:

```text
https://team360.live/
```

Preferentemente en ventana privada.

Ejecutar un caso conocido:

```text
recibimos muchas llamadas de telefono
problemas
```

Seleccionar:

```text
Planilla / Excel
```

Verificar:

```text
el toque responde
la seleccion queda visible
el bloque queda answered
el siguiente bloque queda activo
```

No declarar aprobado unicamente por rsync o build.

## Cache

Los assets Astro suelen tener nombres hasheados, por lo que un build nuevo
deberia generar archivos distintos.

Si produccion parece vieja:

```text
comparar assets local/prod
usar ventana privada
hacer recarga forzada
verificar HTML servido
confirmar root de Nginx
```

No repetir rsync a ciegas.

## Rollback

Usar unicamente si el frontend productivo queda roto.

Ejemplo:

```bash
ssh administrator@imotorsoft.com '
  set -e

  BASE=/home/administrator/project/iMotorSoft/ai/Team360/SrvRestAstroLS_v1/astro
  BACKUP=/ruta/exacta/dist_before_TIMESTAMP.tar.gz

  mv "$BASE/dist" "$BASE/dist_failed_$(date +%Y%m%d_%H%M%S)"
  tar -xzf "$BACKUP" -C "$BASE"

  echo ROLLBACK_OK
'
```

Despues validar:

```bash
curl -I https://team360.live/
```

No ejecutar rollback si el sitio esta sano.

## Limpieza local

Eliminar temporales:

```bash
rm -f /tmp/team360-frontend-rsync-dry-run.txt
rm -f /tmp/team360-frontend-rsync-real.txt
rm -f /tmp/team360-assets-local.txt
rm -f /tmp/team360-assets-prod.txt
rm -f /tmp/team360-prod-headers.txt
rm -f /tmp/team360-prod-index.html
```

No eliminar el backup remoto.

## Evidencia minima de despliegue aprobado

Registrar:

```text
rama
HEAD
IS_REST_PRO
pnpm check
build
cantidad de paginas
cantidad de archivos
tamano de dist
ruta remota
backup
dry-run
rsync real
assets local vs produccion
HTTP 200
metadata
Playwright productivo
errores 5xx
errores de consola
requests duplicados
```

Ejemplo:

```text
Rama: feature/console-backend-core
HEAD: 1195328
IS_REST_PRO: true
Build: 139 paginas
dist: 158 archivos / 7.6 MB
Assets local vs produccion: match
Playwright: 5/5 PASS
5xx: 0
Console critical errors: 0
```

## Condiciones de cierre

Aprobar unicamente si:

```text
IS_REST_PRO=true
check PASS
build PASS
backup PASS
dry-run revisado
rsync PASS
index remoto actualizado
assets local = produccion
metadata intacta
E2E especifico PASS
UX manual o tactil PASS
0 errores 5xx
0 requests duplicados
```

## Regla final

El rsync exitoso no demuestra que el frontend correcto este publicado.

La aprobacion requiere:

```text
source correcto
-> build correcto
-> dist correcto
-> rsync correcto
-> Nginx sirve ese dist
-> navegador ejecuta ese build
-> E2E productivo pasa
```

Resumen:

```text
Primero validar.
Despues hacer dry-run.
Despues sincronizar.
Finalmente demostrar que build esta sirviendo produccion.
```

## Referencias

- [[browser-mcp-validation-policy]]
- [[team360-frontend-url-source-of-truth]]
- [[team360-runtime-operational-policy]]
