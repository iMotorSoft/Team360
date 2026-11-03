# Cierre de la ventana GLOBAL Console/Auth DEV

Autorización explícita del propietario posterior al bloqueo. Pieza mínima implementada y preparada en DEV; no se declara login humano, seguridad multitenant integral ni readiness WhatsApp.

## Resultado y contratos

Se separan código probado, preparación real e intervención humana pendiente; el cierre anterior BLOCKED no se reescribe.

```text
TEAM360_CONSOLE_PASSWORD_CEREMONY_CODE=PASS
TEAM360_CONSOLE_PASSWORD_PG18_ISOLATED=PASS
TEAM360_CONSOLE_PASSWORD_DEV_PREPARED=PASS
TEAM360_CONSOLE_PASSWORD_HUMAN_LOGIN=BLOCKED
TEAM360_BS_EFFECTIVE_DB_IDENTIFIED=PARTIAL
TEAM360_BS_DEV_PROD_ISOLATION=PASS
TEAM360_BS_RUNTIME_DB_PRIVILEGES=PARTIAL
TEAM360_BS_MULTIUSER_REAL_AUTH=BLOCKED
TEAM360_BS_MULTITENANT_REAL_ISOLATION=BLOCKED
TEAM360_BS_CONSOLE_REAL_RBAC=BLOCKED
TEAM360_BS_PGVECTOR_REAL_CALIBRATION=BLOCKED
TEAM360_BS_STATE_ENGINE_REGRESSION=PASS
TEAM360_BS_CAPABILITY_REGRESSION=PARTIAL
TEAM360_BS_WHATSAPP_HANDOFF=BLOCKED
TEAM360_BUSINESS_SEMANTICS_SECURITY_UNBLOCK_V1=BLOCKED
TEAM360_BUSINESS_SEMANTICS_OPERATIONAL_CLOSURE_V1=BLOCKED
```

PARTIAL de privilegios: rol dedicado real no privilegiado creado y utilizado por la CLI nueva; el pool Srv05 global no cambió, sigue sin una observación runtime autenticada y RLS permanece ausente. No certificar tenants seguros sólo por cambiar de rol.

## Lo completado

La ceremonia pertenece al Console existente y consume/emite su PASETO, sin otro IAM ni actores impersonados.

- Migración aditiva 030: credenciales fuera de metadata_jsonb e intentos persistidos.
- scrypt N=131072/r=8/p=1; salt aleatorio; mínimo 12, sin composición; límites de entrada/KDF y comparación constante.
- Login por workspace/email + contraseña verificada; cinco fallos por 15 minutos, locks transaccionales y commit de contadores fallidos.
- Issuer/keys persistentes explícitos, sin fallback; token amr=pwd, workspace y credential_version. Session check reconsulta usuario/workspace/organización y reset/disabled.
- Enrollment/reset humano por getpass dos veces; no admite stdin no-TTY ni plaintext por argv/env/chat. No crea usuarios ni grants.
- Audit enrollment distingue operador OS de sujeto; audit login y mutaciones identifica al sujeto autenticado.
- Business Semantics CLI exige --auth-config para operaciones autenticadas, usa DSN del rol dedicado y verifica sesión/RBAC actual. Camino bootstrap/seed separado y explícito, sin simular login.
- Verificador Console compartido endurecido para exigir sub=user:user_id concordante. Consumidores existentes revalidados; ninguna ruta Srv01/Vera modificada.

No se agregó HTTP login o UI. El issuer privado no debe configurarse en el bootstrap experimental ni distribuirse a clientes. Otros consumidores PASETO no reciben revocación DB automática.

## Aplicación real DEV

Preparación realizada sólo después de validación PG18 descartable y backup, contra el cluster acreditado; ninguna contraseña humana fue elegida por el agente.

Cluster local: 7630993354699489317, team360. [dev_before.json](dev_before.json) acredita ausencia de schema/rol nuevo. [prepare.log](prepare.log) confirma preparación. [dev_after.json](dev_after.json) acredita rol sin SUPERUSER/BYPASSRLS/CREATEROLE/CREATEDB, credenciales=0, intentos=0 y los mismos siete core_users.

Se crearon dos tablas y un rol dedicado con grants sólo en team360. Runtime: SELECT IAM/credenciales, DML de contadores/semántica, INSERT auditoría; sin administración de credenciales, DDL, DELETE o privilegios en otras bases. Se permite consultar pg_control_system() para comparar el pin no secreto.

Config/keys/DSN de rol: issuer.json privado modo 0600, directorio 0700 señalado en [private_directory.txt](private_directory.txt). No se copiaron secretos a Git ni se alteró .env/backend-dev/globalVar/pool compartido.

Backup local completo previo, custom PG18, con SHA256 en [backup_sha256.txt](backup_sha256.txt). TOC y extracción SQL con pg_restore PASS; no restore completo. El backup permanece privado junto a issuer.json.

## Validaciones

Todos los datos/contraseñas/tokens de integración son sintéticos y permanecieron en contenedores propios descartables, nunca en las identidades DEV operacionales.

[final_tests.log](final_tests.log): **221 passed, 1 skipped**, warning preexistente Diagnosis in-memory. Paths: Console login/PG/auth/bootstrap/me/SQL-safety, frontera bootstrap, Flow access-mode, administración Telchi, evidencia semántica y dos guards State Engine. No se repitió la batería original de 215.

El skip corresponde a la integración Telchi admin que exige su propio DSN descartable, no al nuevo test PostgreSQL. Las pruebas nuevas PG cubren login/rol/grants, negativa DDL/enrollment runtime, usuarios separados y admin de tenant B rechazado por ID ajeno, auditoría, lockout persistido/reconexión, reset/usuario desactivado y CLI Business Semantics real.

El guard final añade rechazo de ownership público y membresías privilegiadas, con revalidación focalizada en [privilege_guard_tests.log](privilege_guard_tests.log). LAT/whitespace/syntax y revisión final: [validation.log](validation.log).

## Ownership, impacto y retorno

Rama feature/console-backend-core, HEAD 09d2ec715a31bb88574d734eacb9f437f008624e. Ventana GLOBAL delimitada a Console/Auth/DB y documentación de este frente.

Archivos propios: modules/console/{passwords,login_repository,login_admin_repository,login_service,login_cli}.py; migración 030; tests/test_console_password_{login,postgres}.py; runbook Console DEV y auth_window. Edits precisos: console/auth.py, business_semantics/cli.py, estados Console/GLOBAL e índice docs.

Diffs preexistentes preservados. Sin cambios Foundation, SAP/HANA, Messaging, Evolution, Flow runtime, Srv01, embed/Vera, frontend, capabilities, lockfiles, deploy, commits o reinicios compartidos. Impacto transversal: comprobación sub/user_id más estricta y schema/rol aditivos únicamente DEV.

Retorno no destructivo: no usar la nueva ceremonia y mantener el material privado custodiado; retirar LOGIN/grants del rol dedicado sólo en ventana autorizada revisando dependencias. No restaurar toda la base ni borrar identidades/auditoría. No hay configuración global cambiada que restaurar.

## Intervención humana mínima y continuación

Ahora existe un comando real de activación/login; ya no se pide al usuario suplir con passwords un mecanismo inexistente.

Seguir el [runbook](../../../../../SrvRestAstroLS_v1/docs/team360_console_dev_password_login_v1.md): operador autorizado activa en terminal dos cuentas Telchi distintas y la identidad tenant B designada, con sus passwords privadas. Admin Telchi puede ser uno de los dos sujetos.

Cada persona autentica su cuenta; entregar sólo el token por canal privado autorizado, nunca issuer.json ni passwords. Aún faltan estas sesiones reales, pool Srv05 observado y contratos multitenant/Console/calibración. Con ellos ejecutar sólo pendientes y continuar WhatsApp, sin ampliar Business Semantics.

## Recursos

Host BUSY_BUT_SAFE, ocho cores, 5.3–5.6 GiB disponibles en muestras, swap estable/decreciente durante operaciones; cargas secuenciales y KDF limitado.

```text
HOST_PREFLIGHT=BUSY_BUT_SAFE
RESOURCE_GUARD=PASS
CONCURRENCY_USED=1 pytest worker / 1 capped PG container at a time
UNRELATED_PROCESSES_TERMINATED=0
ENVIRONMENTAL_ABORTS=0
OWN_PROCESSES_LEFT_RUNNING=0
HUMAN_PASSWORDS_ACTIVATED=0
```

Contenedores propios: IDs en owned_test_container.txt, detenidos/eliminados con --rm; cleanup registrado. No se cerraron servicios ajenos ni se consultó producción otra vez. La preparación de infraestructura sí hizo DDL/GRANT DEV autorizados; no se mantiene el claim anterior DATABASE_WRITES=0 para esta ventana.
