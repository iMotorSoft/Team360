# Telchi DEV real provisioning V1

Aprovisionamiento aplicado a PostgreSQL 18 DEV; autenticación, migración telefónica y WhatsApp aún no operativos. Evidencia nueva de esta ejecución, sin adoptar cambios preexistentes.

## 1. Estado inicial

Rama `feature/console-backend-core`, HEAD `09d2ec715a31bb88574d734eacb9f437f008624e`. Máquina/base DEV aceptadas por autorización explícita del propietario, sin exigir una nueva acreditación DEV/PROD.

El precheck read-only confirmó `localhost:5432/team360`, PostgreSQL 18.4, system identifier `7630993354699489317`. No existían las tres identidades por email normalizado, organización/workspace Telchi, rol RBAC `platform_admin` ni tabla 027. Se preservaron las cuatro identidades anteriores y el workspace público.

## 2. Backup

Backup completo previo al primer write, fuera de Git, owner-only (0600), sin sobrescribir copias anteriores. Se respaldó exclusivamente `team360`.

- Ruta: `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/private/telchi/backups/real-provisioning-20261011T230540Z/team360.dump`.
- Tamaño: 3.140.648 bytes; formato custom PG18.
- SHA256: `99f1f341ce598a101e7e4a32dae83e7c15b2b630cd0f8ad28dff1485a44eb88f`.
- `docker exec imotorsoft-postgres pg_dump -U administrator -d team360 -Fc`: exit 0.
- `pg_restore --list` y `pg_restore --file=/dev/null`, mediante stdin: exit 0; TOC privada `team360.toc`.
- Archivo íntegro/legible y SQL extraíble; **no se hizo restore en otra base**, ni se certifica un ensayo de restauración completa.

Antes del commit se ensayaron las operaciones y su segunda ejecución en una transacción `SERIALIZABLE` con rollback forzado: PASS, sin persistir el ensayo. Las inserciones propias tienen snapshots en eventos para reversión revisada. Después del commit, no restaurar ciegamente toda la base ni borrar usuarios: revocar grants propios y conservar auditoría; el rollback protegido del seed debe rechazar dependencias supervivientes. No existe rollback postcommit automático del nuevo enrollment.

## 3. Migraciones

No se aplicó ninguna migración. La 027 quedó detenida únicamente por su condición específica de comparación con la versión validada, no por dudas sobre DEV.

SHA256 actual de `027_team360_messaging_phone_bindings.sql`: `9ff78e59b5276e0158a774aaef70162770bc907fbe71cf81159a73ec036f1694`. Las referencias anteriores documentan pruebas PG18 pero no conservan un hash histórico comparable. No afirmar que un hash calculado hoy demuestra igualdad con aquel archivo. La tabla y la función del trigger continúan ausentes. No se alteró el SQL ni se creó un esquema alternativo.

Las tablas referenciadas por el procedimiento de provisioning existen. La validación completa de constraints, índices y trigger 027 queda pendiente de su aplicación autorizada con checksum cotejado. La migración 026 no se reaplicó.

## 4. Organización y workspace

Aplicación real confirmada mediante consultas read-only posteriores al commit; no se utilizó Diagnosis como workspace Telchi.

- Organización `telchi`: `44b9b7ea-1c19-4a9f-a3d5-1f20622d2f99`, tipo client, active.
- Workspace `telchi_dev`: `3fb026a1-a4ba-44b3-b65b-fab452df7fc9`, testing, ligado a esa organización.
- Workspace administrativo separado `team360_admin_dev`: `d848e051-3dfc-408b-ad5a-94f2ba85ee23`, testing, ligado a la organización preexistente `team360_platform`.
- Módulo Telchi autorizado en los límites administrativos existentes, **no instalado/habilitado en runtime**. El contrato de bootstrap conserva `runtime_module_enabled=false`; no se inventó un catálogo de módulos.

## 5. Administradores y usuario

Se crearon exclusivamente las tres cuentas autorizadas, sin credenciales, tokens, traslados ni duplicados. `core_users.status=active` no equivale a login habilitado.

| Cuenta | UUID | Ámbito real |
| --- | --- | --- |
| `admin@team360.com` | `67a1b108-7c65-4c80-bbca-ffc42891949c` | Workspace administrativo Team360, rol RBAC global `platform_admin` |
| `admin@telchiai.com` | `73d09264-8be2-4402-8023-0142a5f26730` | Miembro Telchi con `organization_admin`, delegación existente |
| `devfull@telchiai.com` | `5015a69d-eb86-4ac9-b97f-c31dc06e2b59` | Miembro Telchi, lector comercial documental |

La vía local explícitamente auditada no fabricó un principal PASETO ni usó el bootstrap HTTP como login. El actor operacional es el propietario local autenticado al host/conexión PG, registrado como `local_owner_bootstrap_not_console_login`. Los eventos del seed atribuyen los grants al administrador designado, **no prueban una sesión humana de ese administrador**.

## 6. Roles y permisos

Verificación real mediante `PermissionConsoleRepository` y guards administrativos existentes. No se concedieron permisos ficticios para capacidades futuras.

- Global: `audit.view`, `role.manage`, `user.manage`, con rol RBAC global `platform_admin`; `AdminRepository.global_actor` acepta la identidad.
- Admin Telchi: membresía y rol organizacional activos; `AdminRepository.delegated_actor` acepta su ámbito. Permisos Console efectivos vacíos: su autoridad delegada usa el contrato organizacional existente, no grants globales.
- Piloto: exactamente `telchi.sales.source_quantity.read.v1`, rol local `telchi_source_quantity_reader_v1`.
- Capability: `telchi.sales_top_items.source_quantity.20260101_20260915.v1`; cantidades documentales, ventana fija y Foundation. Sin SAP, facturación neta, otros módulos/tenants o capacidades nuevas. No es FULL_ACCESS genérico.
- Límites delegados: módulos `[telchi]`, rol y permiso comercial exactos; credential enrollment y runtime module enablement permanecen false.
- Se rechazó realmente al piloto como administrador delegado y al admin Telchi en el workspace Team360. Permisos comerciales del piloto en workspace global: vacíos. Identidad global consultada como usuario del workspace Telchi: sin permisos comerciales.

Los comandos existentes todavía no crean/vinculan identidades nuevas ni configuran módulos runtime. No declarar que todas las facultades futuras de administración ya operan; solo provisioning/grants y los límites implementados quedaron comprobados.

## 7. Activación de contraseñas

**No activadas y no se preparó un comando ficticio de cambio de password.** Este pendiente requiere código Console/Auth, además de entrada humana; no alcanza con que el propietario escriba tres contraseñas.

La búsqueda focalizada confirmó que Console/Auth verifica PASETO, pero no hay login por contraseña, servicio de hashing/verificación, credential store ni política/rate limiting de un login por password demostrados. `core_users` no contiene password hash. No utilizar metadata JSON, un hash improvisado o un token emitido por identidad elegida para ocultar ese faltante.

No se recibieron contraseñas por chat/argv/env, no se generaron passwords y no se modificaron claves existentes. La política solicitada de 12 caracteres, sin composición, diferencias entre cuentas y `getpass` queda como contrato para el procedimiento DEV mínimo de Console/Auth. No hay comando exacto seguro de `set-password` que pueda ejecutarse hoy: inventarlo sería presentar una operación inexistente.

Login correcto/incorrecto, hashing, mínimo 12 y protección de intentos **no validados operacionalmente**. Las regresiones Console comprueban el verificador PASETO existente, no passwords.

## 8. Binding telefónico

No se creó ningún binding ni se declaró posesión del teléfono del piloto. El número completo no aparece en este informe ni en la nueva evidencia.

Contrato existente: E.164 sin `+`, verificación individual y consentimiento, referencia administrativa opaca, binding DEV Evolution y permisos reconsultados por usuario. Requiere primero 027 y evidencia real del control de la línea. No hay desafío OTP automatizado implementado; una referencia inventada o un booleano no son prueba de posesión.

Acción humana posterior: enviar desde la línea del piloto al receptor DEV confirmado y conservar un comprobante independiente de origen/posesión y consentimiento. Hasta revisar ese comprobante, no ejecutar `bind-phone` con `consent_verified=true`. No exponer OTPs, comprobantes sensibles ni teléfono completo en Git/chat.

## 9. Canal WhatsApp DEV

Inspección autenticada y exclusivamente GET de Evolution local, sin reinstalación, recreación, envío, cambio de webhook ni manipulación de sesiones.

`127.0.0.1:18180` respondió y el contenedor existente está running. La instancia realmente registrada se llama **`team360-meta-dev`**; su estado es **`open`**. `open` no es el nombre de la instancia. No se creó una instancia llamada open ni se asumió un receptor desconocido.

El proveedor Evolution de Team360 existe con status testing. Telchi tiene cero canales. No se habilitó `horizontal_v1` sin confirmar receiver/composición/binding, ni se habilitó fallback legacy o PROD. No se tocó Meta, Cloudflare, Flow, Diagnosis ni Srv01.

## 10. Tests

Tests focalizados baratos y ensayo sobre transacción propia; no benchmarks, browsers ni suite destructiva contra `team360`.

```bash
cd SrvRestAstroLS_v1/backend
uv run --no-sync pytest modules/telchi/provisioning/tests/test_live_bootstrap.py modules/telchi/provisioning/tests/test_admin.py modules/telchi/provisioning/tests/test_provisioning_pg18.py tests/test_console_auth.py tests/test_console_bootstrap_service.py tests/test_messaging_phone_binding_isolated.py tests/test_messaging_horizontal_runtime.py tests/test_srv05_horizontal_composition.py -q
```

Resultado final: **101 passed, 3 skipped**, warning preexistente de Diagnosis in-memory en composición. Los skips corresponden a integración que necesita DSN descartable; **jamás se apuntó `TELCHI_PROVISIONING_TEST_DSN` a team360**: esas fixtures borran public. Evidencia: [salida final](real-focused-tests-final.txt).

Primer intento: 45 PASS, 1 FAIL, 1 skip; defecto del test nuevo por usar un plugin asyncio no instalado. Corregido usando `asyncio.run`, sin instalar dependencias ni modificar runtime. [Salida preservada](real-focused-tests.txt). Las pruebas antiguas PG18 descartables siguen siendo evidencia anterior, no se contabilizan como ejecutadas ahora.

Unknown/revoked/wrong-environment phone y restricciones de manifests/CLI: contratos con fixtures; no presentarlos como bindings reales verificados. Aprovisionamiento, permisos, guards de delegación, commit y segunda ejecución sí se comprobaron sobre PG18 real.

## 11. Auditoría e idempotencia

Primera ejecución confirmó cuatro eventos administrativos; segunda ejecución no creó filas ni eventos. Snapshots de objetos nuevos preservados en PG.

- Seed scaffold: `6b70b861-1f84-4c80-b948-65b0601cbc66`, dos filas.
- Seed grants: `d4142416-643a-4e42-81f7-b59d10dba7c9`, ocho filas.
- Enrollment/global RBAC local: `c8ba6560-809d-4a44-a329-6ac939da77d0`, nueve filas.
- Delegación: `8515c1a9-e645-4f86-90cc-c1c36470e1ed`.
- [Aplicación](real-applied.json), [idempotencia](real-idempotence.json), [postcheck real](real-postcheck.json).

La nueva vía local usa manifest privado owner-only, backup con hash comprobado, source hashes, destino pinneado, loopback `team360:5432`, autorización explícita y transacción serializable. Solo permite las tres identidades fijas. No modifica el CLI autenticado anterior ni permite una API pública.

## 12. Pendientes humanos y técnicos

No atribuir todos los pendientes a acciones humanas: existen piezas de autenticación faltantes y condiciones de migration/runtime concretas.

1. Implementar el mínimo de password enrollment/login compatible con Console/Auth y su credential store, con hashing estándar revisado y protección de intentos; no existe un mecanismo real reutilizable de passwords hoy.
2. Después, el propietario ingresa las tres contraseñas ocultas en terminal; validar login/errores/tenant sin imprimir tokens.
3. Cotejar el checksum 027 con el artefacto validado, o aprobar explícitamente el checksum actual revisado como baseline de aplicación. Solo entonces aplicar 027 con backup y validar constraints/trigger/índices.
4. Confirmar receptor de la instancia existente `team360-meta-dev`; no confundir nombre con state open.
5. Completar prueba independiente de posesión/consentimiento del piloto, registrar binding verificado mediante el procedimiento existente y comprobar resolución Messaging.
6. Configurar canal Telchi `horizontal_v1`, DEV, tenant/workspace/handler correctos, con política runtime explícita. Luego primera prueba real WhatsApp; sin PROD ni modificaciones de arquitectura horizontal.

## 13. Archivos propios

No se editaron archivos preexistentes. Los archivos siguientes son nuevos y pertenecen exclusivamente a esta ejecución.

- `SrvRestAstroLS_v1/backend/modules/telchi/provisioning/live_repository.py`.
- `SrvRestAstroLS_v1/backend/modules/telchi/provisioning/live_cli.py`.
- `SrvRestAstroLS_v1/backend/modules/telchi/provisioning/tests/test_live_bootstrap.py`.
- Este informe y evidencia `real-applied.json`, `real-idempotence.json`, `real-postcheck.json`, `real-focused-tests.txt`, `real-focused-tests-final.txt`, `real-validation.txt` en este directorio.
- Manifest/backup/TOC privados fuera de Git, con credenciales ausentes.

No commits, push, deploy, migraciones nuevas, lockfiles, cambios Auth compartidos, Foundation, Luna, State Engine, guards, capabilities o infraestructura externa. Impacto transversal real: nuevas filas IAM/RBAC y organización/workspaces en la base DEV autorizada; no se mutaron filas preexistentes.

## 14. Problemas y recursos

No hubo bloqueo genérico DEV/PROD. Los bloqueos restantes son específicos y no impidieron aplicar las operaciones seguras de provisioning.

No hay password auth implementado; checksum histórico 027 ausente; habilitación runtime/módulo persistida no demostrada; instancia confundida con state; receptor y posesión no confirmados. El catálogo no contiene permisos futuros `platform.manage`, `organizations.manage`, etc.; se conservaron los permisos administrativos efectivamente existentes, sin inventar entradas.

Host: 8 cores, inicialmente load 1.23/1.45/1.40, ~5.8 GiB disponibles; swap histórica ~4.1 GiB sin crecimiento en muestras vmstat. Al cierre ~5.7 GiB disponibles, load 3.60/3.04/2.10. Se mantuvieron operaciones baratas/secuenciales, una conexión/worker, sin nuevos contenedores ni servicios.

```text
HOST_PREFLIGHT=BUSY_BUT_SAFE
RESOURCE_GUARD=PASS
CONCURRENCY_USED=1 sequential test worker / 1 own database connection
UNRELATED_PROCESSES_TERMINATED=0
ENVIRONMENTAL_ABORTS=0
OWN_PROCESSES_LEFT_RUNNING=0
```

## 15. Próxima acción y estados

Próximo paso inmediato: cerrar la pieza mínima de credenciales Console/Auth y cotejar/aprobar el hash 027 indicado. No pedir passwords por chat ni ejecutar WhatsApp como si el piloto ya tuviera un binding verificable.

Comando local realmente aplicado, desde backend, solo para revalidar el provisioning existente; **no activa contraseñas ni teléfonos**:

```bash
uv run --no-sync python -m modules.telchi.provisioning.live_cli --manifest /media/issajar/DEVELOP/Projects/iMotorSoft/ai/private/telchi/backups/real-provisioning-20261011T230540Z/local-bootstrap-manifest.json --apply --local-owner-bootstrap
```

PASS de organización/workspace/permiso significa commit y verificación real. PARTIAL de cuentas significa identidad/RBAC presentes, pero login y todas las facultades administrativas solicitadas no están operativos.

```text
TEAM360_DEV_REAL_PROVISIONING=PARTIAL
TEAM360_GLOBAL_ADMIN=PARTIAL
TELCHI_DEV_ORGANIZATION=PASS
TELCHI_DEV_WORKSPACE=PASS
TELCHI_DEV_ADMIN=PARTIAL
TELCHI_DEV_USER_FULL=PARTIAL
TELCHI_DEV_PASSWORD_ACTIVATION=BLOCKED
TELCHI_DEV_BUSINESS_PERMISSION=PASS
TELCHI_DEV_MIGRATION_027=BLOCKED
TELCHI_DEV_PHONE_BINDING=BLOCKED
TELCHI_DEV_HORIZONTAL_CHANNEL=BLOCKED
TELCHI_WHATSAPP_DEV_READY=BLOCKED
```

Gates LAT y revisión whitespace/diff propios: consultar [validación](real-validation.txt). Estos gates no convierten los estados operacionales pendientes en PASS.
