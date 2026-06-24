# Politica de despliegue backend por rsync - Team360

## Objetivo

Definir el procedimiento unico para:

```text
validar rama y HEAD
-> verificar backend local
-> backup remoto
-> dry-run
-> revisar eliminaciones
-> rsync real
-> verificar archivos remotos
-> reinicio manual posterior en tmux
-> smoke productivo
```

Esta politica aplica al backend de Team360 publicado detras de:

```text
https://team360.live
```

## Directorio local

Proyecto:

```text
/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/SrvRestAstroLS_v1
```

Backend local:

```text
/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/SrvRestAstroLS_v1/backend
```

Para ejecutar el comando desde el directorio padre:

```text
/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360
```

Origen:

```text
SrvRestAstroLS_v1/backend/
```

## Destino remoto oficial

Destino productivo:

```text
administrator@imotorsoft.com:/home/administrator/project/iMotorSoft/ai/Team360/SrvRestAstroLS_v1/backend/
```

Mantener la barra final:

```text
.../backend/
```

Esto copia el contenido del backend local dentro del backend remoto.

No generar accidentalmente:

```text
backend/backend/
```

## Comandos oficiales

Dry-run:

```bash
rsync -avzn --delete \
  --itemize-changes \
  --exclude '.env*' \
  --exclude '.venv/' \
  --exclude '__pycache__/' \
  --exclude '.pytest_cache/' \
  --exclude '.mypy_cache/' \
  --exclude '*.pyc' \
  SrvRestAstroLS_v1/backend/ \
  administrator@imotorsoft.com:/home/administrator/project/iMotorSoft/ai/Team360/SrvRestAstroLS_v1/backend/
```

Rsync real:

```bash
rsync -avz --delete \
  --itemize-changes \
  --exclude '.env*' \
  --exclude '.venv/' \
  --exclude '__pycache__/' \
  --exclude '.pytest_cache/' \
  --exclude '.mypy_cache/' \
  --exclude '*.pyc' \
  SrvRestAstroLS_v1/backend/ \
  administrator@imotorsoft.com:/home/administrator/project/iMotorSoft/ai/Team360/SrvRestAstroLS_v1/backend/
```

La unica diferencia permitida entre ambos comandos es:

```text
-avzn
```

por:

```text
-avz
```

No modificar entre dry-run y ejecucion real:

- origen;
- destino;
- exclusiones;
- `--delete`;
- usuario remoto.

## Rama esperada

Antes de sincronizar:

```bash
cd /media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360

git -C SrvRestAstroLS_v1 branch --show-current
git -C SrvRestAstroLS_v1 rev-parse --short HEAD
git -C SrvRestAstroLS_v1 status --short
git -C SrvRestAstroLS_v1 log -12 --oneline
```

Rama esperada:

```text
feature/console-backend-core
```

Si no coincide:

```text
DETENER
```

No cambiar automaticamente de rama.

No hacer:

- checkout;
- merge;
- rebase;
- pull;
- push.

## Validar que se desplegara

Registrar:

```bash
git -C SrvRestAstroLS_v1 status --short
git -C SrvRestAstroLS_v1 diff --stat
git -C SrvRestAstroLS_v1 diff --name-only
git -C SrvRestAstroLS_v1 ls-files --others --exclude-standard
```

Diferenciar claramente:

```text
cambios incluidos en HEAD
```

de:

```text
cambios locales sin commit
```

El `rsync` copia el contenido real del worktree, no solamente el ultimo commit.

Por eso, si existen archivos backend sin commit, deben declararse antes del
despliegue.

No desplegar accidentalmente archivos temporales o experimentales.

## Comparar con origin

Ejecutar:

```bash
git -C SrvRestAstroLS_v1 fetch --dry-run

git -C SrvRestAstroLS_v1 rev-parse --short HEAD

git -C SrvRestAstroLS_v1 \
  rev-parse --short origin/feature/console-backend-core \
  2>/dev/null || true

git -C SrvRestAstroLS_v1 \
  log --oneline origin/feature/console-backend-core..HEAD \
  2>/dev/null || true
```

Registrar:

```text
HEAD local
HEAD remoto
commits locales no pusheados
```

No bloquear el `rsync` por falta de push, pero dejar constancia.

## Validacion local previa

Si los cambios afectan el runtime de Vera, ejecutar tests backend relevantes
antes del despliegue.

Ejemplo:

```bash
cd /media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/SrvRestAstroLS_v1/backend

uv run pytest tests/test_canonical_patterns_phase2.py
```

Cuando corresponda:

```bash
uv run pytest
```

Registrar exactamente:

```text
passed
failed
skipped
xfailed
```

No escribir:

```text
0 fallos
```

si hubo fallos excluidos, preexistentes o en otra ejecucion.

## Verificar conectividad SSH

Ejecutar:

```bash
ssh administrator@imotorsoft.com '
  echo SSH_OK
  hostname
'
```

Si falla:

```text
DETENER
```

No modificar claves ni configuracion SSH dentro del procedimiento de deploy.

## Validar destino remoto

Ejecutar:

```bash
ssh administrator@imotorsoft.com '
  TARGET=/home/administrator/project/iMotorSoft/ai/Team360/SrvRestAstroLS_v1/backend

  echo "TARGET=$TARGET"
  test -d "$TARGET"
  ls -ld "$TARGET"
'
```

No crear una ruta paralela.

No continuar si el destino no existe o no parece ser el backend productivo.

## Verificar sensibles remotos

Comprobar solamente existencia y rutas:

```bash
ssh administrator@imotorsoft.com '
  TARGET=/home/administrator/project/iMotorSoft/ai/Team360/SrvRestAstroLS_v1/backend

  find "$TARGET" -maxdepth 2 \
    \( -name ".env*" -o -name ".venv" \) \
    -printf "%p\n"
'
```

No mostrar valores de variables.

No leer el contenido de `.env`.

No borrar ni copiar `.env` o `.venv`.

## Exclusiones obligatorias

Mantener:

```text
--exclude '.env*'
--exclude '.venv/'
--exclude '__pycache__/'
--exclude '.pytest_cache/'
--exclude '.mypy_cache/'
--exclude '*.pyc'
```

Estas exclusiones protegen:

- configuracion productiva;
- entorno virtual remoto;
- caches;
- bytecode;
- archivos que no deben reemplazarse desde local.

No quitar exclusiones sin una razon documentada.

## Backup remoto obligatorio

Antes del rsync real:

```bash
ssh administrator@imotorsoft.com '
  set -e

  BASE=/home/administrator/project/iMotorSoft/ai/Team360/SrvRestAstroLS_v1
  TARGET="$BASE/backend"
  BACKUP_DIR="$BASE/backups"
  TS=$(date +%Y%m%d_%H%M%S)

  mkdir -p "$BACKUP_DIR"

  tar \
    --exclude=".venv" \
    --exclude="__pycache__" \
    --exclude=".pytest_cache" \
    --exclude=".mypy_cache" \
    --exclude="*.pyc" \
    -czf "$BACKUP_DIR/backend_before_${TS}.tar.gz" \
    -C "$BASE" backend

  echo "BACKUP=$BACKUP_DIR/backend_before_${TS}.tar.gz"
  ls -lh "$BACKUP_DIR/backend_before_${TS}.tar.gz"
'
```

Registrar:

```text
ruta exacta
tamano
timestamp
```

No borrar backups anteriores durante el despliegue.

## Dry-run obligatorio

Desde:

```bash
cd /media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360
```

Ejecutar:

```bash
rsync -avzn --delete \
  --itemize-changes \
  --exclude '.env*' \
  --exclude '.venv/' \
  --exclude '__pycache__/' \
  --exclude '.pytest_cache/' \
  --exclude '.mypy_cache/' \
  --exclude '*.pyc' \
  SrvRestAstroLS_v1/backend/ \
  administrator@imotorsoft.com:/home/administrator/project/iMotorSoft/ai/Team360/SrvRestAstroLS_v1/backend/ \
  | tee /tmp/team360-backend-rsync-dry-run.txt
```

No ejecutar el rsync real antes de revisar esta salida.

## Interpretar el dry-run

Clasificar:

```text
archivos nuevos
archivos modificados
archivos eliminados
directorios eliminados
```

Revisar especialmente:

```text
*deleting
```

Bloquear si intenta eliminar:

```text
.env
.env.*
.venv
logs operativos
uploads
datos
backups
configuracion productiva no versionada
scripts manuales remotos
```

Puede ser aceptable eliminar, despues de revisar:

```text
*.bak
archivos obsoletos versionados
temporales claramente descartables
```

No asumir que toda eliminacion es segura.

## Uso de `--delete`

La opcion:

```text
--delete
```

elimina del remoto los archivos que ya no existen en el backend local, excepto
los excluidos.

Su objetivo es evitar:

```text
modulos viejos
archivos renombrados duplicados
codigo obsoleto
backups accidentales dentro del arbol versionado
```

Solo es segura porque:

- el destino fue validado;
- existe backup;
- el dry-run fue revisado;
- `.env` y `.venv` estan excluidos.

## Rsync real

Solo si:

```text
rama correcta
HEAD registrado
tests relevantes PASS
SSH PASS
destino correcto
sensibles identificados
backup creado
dry-run revisado
sin eliminaciones peligrosas
```

Ejecutar:

```bash
rsync -avz --delete \
  --itemize-changes \
  --exclude '.env*' \
  --exclude '.venv/' \
  --exclude '__pycache__/' \
  --exclude '.pytest_cache/' \
  --exclude '.mypy_cache/' \
  --exclude '*.pyc' \
  SrvRestAstroLS_v1/backend/ \
  administrator@imotorsoft.com:/home/administrator/project/iMotorSoft/ai/Team360/SrvRestAstroLS_v1/backend/ \
  | tee /tmp/team360-backend-rsync-real.txt
```

No cambiar ningun parametro respecto del dry-run, salvo quitar `n`.

## Verificacion posterior al rsync

Confirmar que sensibles siguen presentes:

```bash
ssh administrator@imotorsoft.com '
  TARGET=/home/administrator/project/iMotorSoft/ai/Team360/SrvRestAstroLS_v1/backend

  echo "Sensitive paths:"
  find "$TARGET" -maxdepth 2 \
    \( -name ".env*" -o -name ".venv" \) \
    -printf "%p\n"
'
```

Verificar archivos principales:

```bash
ssh administrator@imotorsoft.com '
  TARGET=/home/administrator/project/iMotorSoft/ai/Team360/SrvRestAstroLS_v1/backend/modules/sales_diagnosis_runtime

  find "$TARGET" -maxdepth 1 -type f \
    -printf "%TY-%Tm-%Td %TH:%TM:%TS %f\n" \
    | sort
'
```

Registrar si se actualizaron, por ejemplo:

```text
runtime.py
policies.py
```

## Reinicio manual en tmux

El procedimiento de `rsync` no debe reiniciar el backend.

No ejecutar automaticamente:

```text
tmux
systemctl restart
supervisorctl restart
pm2 restart
pkill
killall
```

El usuario realizara manualmente el reinicio dentro de la ventana productiva de
`tmux`.

La salida del deploy debe terminar con:

```text
backend sincronizado
pendiente reinicio manual en tmux
```

## Variables de entorno del proceso

Despues del reinicio manual, confirmar que el proceso recibe las variables
necesarias.

No asumir que `.bashrc` siempre es cargado.

En el entorno que inicia el backend debe existir, sin mostrar valores:

```bash
if [[ -n "${LITELLM_MASTER_KEY:-}" ]]; then
  echo "LITELLM_MASTER_KEY=present"
else
  echo "LITELLM_MASTER_KEY=missing"
fi
```

Tambien verificar las variables productivas necesarias para:

```text
LiteLLM
PostgreSQL
Milvus
modelo/alias
persistencia
```

No imprimir secretos.

## Health posterior al reinicio

Despues de que el usuario reinicie manualmente:

```bash
curl -fsS https://team360.live/api/health
```

Y, opcionalmente, directamente desde la VM:

```bash
ssh administrator@imotorsoft.com '
  curl -fsS http://127.0.0.1:7050/api/health
'
```

Esperado:

```json
{
  "status": "ok",
  "service": "backend-team360"
}
```

No considerar suficiente que el proceso exista: debe responder health.

## Smoke del modelo real

Crear una sesion nueva:

```bash
export PROD_SMOKE_ID="prod_backend_$(date +%Y%m%d_%H%M%S)"
```

Ejecutar:

```bash
curl -sS \
  -X POST \
  -H 'Content-Type: application/json' \
  https://team360.live/api/diagnosis/turn \
  -d "{
    \"session_id\":\"${PROD_SMOKE_ID}\",
    \"message\":\"recibo muchas consultas por email y quiero ordenarlas\"
  }"
```

Validar:

```text
HTTP 200
respuesta coherente
modelo esperado
fallback_used = false
sin detail de error
```

Si aparece:

```text
fallback_used = true
```

el codigo puede estar desplegado, pero el backend funcional no esta aprobado.

## Smoke conversacional productivo

Ejecutar un caso corto conocido:

```text
recibimos muchas llamadas de telefono
problemas
```

Validar:

```text
pregunta correcta
single_choice visible
Planilla / Excel funciona
maximo un bloque accionable
sin 5xx
sin requests duplicados
```

Tambien comprobar brevemente:

```text
Necesito responder los WhatsApp que llegan a Kommo.
```

y:

```text
Necesito responder los WhatsApp que llegan a Salesforce.
```

Validar:

```text
WhatsApp = canal
Kommo = CRM
Salesforce = CRM
```

## Playwright contra produccion

Despues del reinicio manual y health:

```bash
cd /media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/SrvRestAstroLS_v1/astro

PLAYWRIGHT_SKIP_WEBSERVER=1 \
PLAYWRIGHT_BASE_URL=https://team360.live \
corepack pnpm exec playwright test \
  e2e/public-vera-phone-problems-interaction-priority.spec.ts \
  e2e/public-vera-email-orders-definitive.spec.ts \
  e2e/public-vera-kommo.spec.ts \
  e2e/public-vera-salesforce.spec.ts \
  e2e/public-vera-new-conversation.spec.ts \
  --project=chromium \
  --workers=1 \
  --reporter=line
```

No usar localhost.

No levantar servicios locales.

No ejecutar varios workers contra produccion.

## Que no debe tocar el deploy backend

No modificar:

```text
astro/dist
frontend
Nginx
PostgreSQL
Milvus
LiteLLM
backups
uploads
.env
.venv
```

No ejecutar:

```text
pnpm build
rsync astro
nginx reload
```

El despliegue backend debe afectar exclusivamente:

```text
SrvRestAstroLS_v1/backend/
```

## Rollback

Solo si el backend no inicia o falla gravemente despues del reinicio.

Usar el backup exacto creado:

```bash
ssh administrator@imotorsoft.com '
  set -e

  BASE=/home/administrator/project/iMotorSoft/ai/Team360/SrvRestAstroLS_v1
  BACKUP=/ruta/exacta/backend_before_TIMESTAMP.tar.gz

  mv "$BASE/backend" "$BASE/backend_failed_$(date +%Y%m%d_%H%M%S)"
  tar -xzf "$BACKUP" -C "$BASE"

  echo BACKEND_ROLLBACK_OK
'
```

Despues:

```text
reinicio manual del backend en tmux
health
smoke
```

No ejecutar rollback si:

- health esta bien;
- modelo real responde;
- el problema es solamente visual frontend.

## Limpieza local

Eliminar temporales:

```bash
rm -f /tmp/team360-backend-rsync-dry-run.txt
rm -f /tmp/team360-backend-rsync-real.txt
```

No borrar el backup remoto.

## Evidencia minima del deploy

Registrar:

```text
rama
HEAD
HEAD origin
commits no pusheados
worktree
tests backend
SSH
destino
sensibles
backup
dry-run
archivos nuevos
archivos modificados
archivos eliminados
rsync real
reinicio manual
health
modelo
fallback
smoke
Playwright productivo
```

## Condiciones de aprobacion

Aprobar unicamente si:

```text
rama correcta
tests relevantes PASS
backup PASS
dry-run revisado
rsync PASS
sensibles preservados
reinicio manual completado
health PASS
modelo real PASS
fallback_used=false
smoke conversacional PASS
0 errores 5xx
0 requests duplicados
```

## Informe final obligatorio

Entregar:

1. Rama.
2. HEAD local.
3. HEAD origin.
4. Commits no pusheados.
5. Worktree.
6. Tests backend.
7. SSH.
8. Destino remoto.
9. Sensibles encontrados.
10. Backup creado.
11. Ruta del backup.
12. Dry-run.
13. Archivos nuevos.
14. Archivos modificados.
15. Archivos eliminados.
16. Eliminaciones peligrosas.
17. Rsync real.
18. Sensibles preservados.
19. Backend reiniciado manualmente.
20. Tmux tocado por el proceso automatico: no.
21. Health remoto.
22. Health interno.
23. Modelo utilizado.
24. Fallback.
25. Smoke diagnostico.
26. Phone problems.
27. Kommo.
28. Salesforce.
29. Playwright productivo.
30. Errores 5xx.
31. Requests duplicados.
32. Backend aprobado: si/no.
33. Frontend tocado: no.
34. Nginx tocado: no.
35. Push realizado: si/no.
36. Recomendacion final.

## Regla final

El rsync exitoso no demuestra que el backend este operativo.

La cadena de aprobacion es:

```text
codigo correcto
-> tests correctos
-> dry-run seguro
-> backup
-> rsync
-> reinicio manual en tmux
-> health
-> modelo real sin fallback
-> smoke productivo
```

## Referencias

- [[team360-runtime-operational-policy]]
- [[browser-mcp-validation-policy]]
- [[service-preflight-methodology]]
