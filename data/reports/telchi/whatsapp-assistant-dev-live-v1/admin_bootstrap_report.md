# Team360 / Telchi administrative bootstrap V1

Implementación mínima validada en PostgreSQL 18 descartable. Sin aprovisionamiento operacional, alta humana, instalación de módulo ni WhatsApp vivo. Estado general PARTIAL por límites reales de identidad, habilitación e infraestructura.

## 1. Estado inicial y alcance

Rama `feature/console-backend-core`, HEAD `09d2ec715a31bb88574d734eacb9f437f008624e`. El worktree inicial tenía numerosos cambios tracked/untracked; se preservaron íntegramente.

Scope: `SrvRestAstroLS_v1/backend/modules/telchi/provisioning/` y evidencia `data/reports/telchi/whatsapp-assistant-dev-live-v1/admin-*`. Contexto: TELCHI / USUARIOS_ROLES_Y_PERMISOS / DEVELOPMENT. Sin cambios GLOBAL/SHARED, commits, deploy ni interfaces.

Archivos nuevos: `admin_repository.py`, `admin_service.py`, `admin_cli.py`, `tests/test_admin.py`. Cambios focalizados al seed existente: `repository.py` permite atribuir auditoría al actor global; `cli.py` conserva plan offline y deshabilita ejecución/rollback sin autenticación. No se reconstruyó el seed.

## 2. Componentes reutilizados

La autorización y los permisos continúan en entidades existentes, sin otro motor IAM ni SQL que omita los controles administrativos nuevos.

- Console: `verify_console_access_token`, PASETO v4.public y `PermissionConsoleRepository`.
- Seed: `ProvisioningRepository`, `Seed`, permiso `telchi.sales.source_quantity.read.v1`, rol local `telchi_source_quantity_reader_v1`.
- Organización/workspace: tablas reales existentes y fixture DDL organizacional del seed anterior.
- Auditoría: `core_events`; 027 mantiene su trigger para teléfonos.
- Binding: `bind_verified_dev_phone`, `PhoneIdentityRepository`; Messaging conserva canales/conversaciones y permisos reconsultados por usuario.
- Handler/Srv05: contratos existentes; no configuración ni modificación de runtime.

La búsqueda focalizada en modules/routes/scripts/migrations no encontró servicio de alta humana, hash de password, reset/activación o invitación Team360. Console repositorios consultan identidad/RBAC; no proporcionan CRUD administrativo equivalente. Por eso los comandos pequeños agregan validaciones y SQL parametrizado en un repository local, no endpoints.

## 3. Arquitectura efectiva

El CLI es solo transporte. `AdminService` valida manifest/principal y `AdminRepository` impone alcance; el caller abre transacción serializable.

Bootstrap global exige usuario activo con workspace, rol RBAC persistido `platform_admin` activo y permiso efectivo `user.manage`. No basta `core_users.role`, un UUID en manifest, referencias a aprobación ni `default_admin`.

Dos fases reutilizan el seed: `scaffold` crea/reutiliza organización/workspace; `grants` exige administrador y piloto existentes, activos y ligados directamente al workspace. Pueden ser la misma persona. La fase grants conserva el comportamiento del seed: asigna el permiso comercial al piloto indicado.

El bootstrap grants registra límites fijos V1 y administrador en un evento auditado `telchi.admin.bootstrap`. El delegado debe tener membresía Telchi activa, `organization_admin` activo, usuario activo en `telchi_dev` y límites globales concordantes. No puede escribir esos límites desde manage-client.

Ese evento acredita **delegación administrativa**, no un catálogo alternativo de módulos ni una instalación. Solo se admite módulo `telchi`, rol comercial exacto y permiso exacto. `runtime_module_enabled=false`: habilitación real sigue siendo `BusinessPolicy` y composición existente de Srv05, pendiente de autorización. No se declara completado el requisito de registrar/habilitar operacionalmente módulos.

## 4. Comandos implementados

Los comandos se ejecutan desde backend, con archivos privados fuera del repositorio, permisos owner-only y un token Console previamente autenticado entregado por stdin.

```bash
uv run --no-sync python -m modules.telchi.provisioning.admin_cli bootstrap-client --manifest "$TELCHI_PRIVATE_MANIFEST" --dry-run
uv run --no-sync python -m modules.telchi.provisioning.admin_cli manage-client --manifest "$TELCHI_PRIVATE_MANIFEST" --dry-run
```

`--dry-run` es el default; `--apply` es explícito y mutuamente excluyente. Para usar stdin, el operador integra el canal seguro de entrega del token; **no escribir tokens en argv, chat, archivos versionados ni historial shell**. El CLI no emite tokens ni genera claves DEV.

Variables privadas: `TELCHI_PROVISIONING_DSN`, `TELCHI_ADMIN_TRUST_CONFIG`; configuración pública de verificación Console: `TEAM360_PASETO_ENABLED`, `TEAM360_PASETO_KEY_ID`, `TEAM360_PASETO_PUBLIC_KEY_B64`, issuer existente. No hay fallback a DSN global o claves efímeras.

Trust config separado del manifest contiene `environment=dev`, pin `target` (database/system_identifier/server_address/server_port) y referencias opacas `approvals.dev_isolation`, `explicit_application`, `backup_restore`, `authenticated_issuer`. Se exige archivo owner-only fuera de Git; el pin se compara con la conexión real.

Las referencias son evidencia administrativa externa, **no prueba criptográfica de aislamiento ni login**. La entrega no autoriza rellenarlas sin acreditar esos hechos. El issuer experimental `/api/console/bootstrap` acepta identidad elegida por caller y **no debe usarse como demostración de autenticación humana**.

El CLI verifica actor y alcance tanto en dry-run como apply. Dry-run usa `SERIALIZABLE READ ONLY`, no escrituras seguidas de rollback. Plan enumera operaciones sin teléfonos, proof refs, nombres o emails. Límite explícito: dry-run comprueba actor/catalog/identidad; conflictos de filas seed, grants y bindings se comprueban transaccionalmente al aplicar, no hay simulación completa de planes dependientes.

El CLI legacy del seed queda offline-only: `--apply` y `--rollback-run` se rechazan antes de leer manifest/conectar. El runbook anterior es evidencia histórica; sus comandos legacy de aplicación ya no están habilitados.

## 5. Esquema de manifests

Los ejemplos siguientes son placeholders de estructura, no personas, UUIDs válidos ni destino autorizado. Manifests reales y datos humanos pertenecen a PRIVATE_ROOT.

```json
{
  "version": 1,
  "environment": "dev",
  "actor_id": "UUID-DEL-ACTOR-GLOBAL-AUTENTICADO",
  "workspace_id": "UUID-WORKSPACE-TELCHI",
  "command": "bootstrap-client",
  "seed": {
    "workspace_id": "UUID-WORKSPACE-TELCHI",
    "organization_id": "UUID-ORGANIZACION-TELCHI",
    "stage": "scaffold"
  }
}
```

Luego `stage=grants`, `admin_id` y `pilot_id` aprobados. Los usuarios deben existir en ese workspace: el comando no mueve identidades de otros clientes, no duplica por email y no realiza altas. Scaffold no habilita delegación.

```json
{
  "version": 1,
  "environment": "dev",
  "actor_id": "UUID-ADMIN-TELCHI-AUTENTICADO",
  "workspace_id": "UUID-WORKSPACE-TELCHI",
  "command": "manage-client",
  "operations": [
    {
      "action": "grant",
      "user_id": "UUID-USUARIO-EXISTENTE",
      "role": "telchi_source_quantity_reader_v1",
      "permissions": ["telchi.sales.source_quantity.read.v1"],
      "modules": ["telchi"]
    }
  ]
}
```

Acciones disponibles: `inspect`; `grant`; `revoke-access`; `bind-phone` con user_id/sender_identity/verification_ref/consent_verified; `revoke-phone` con user_id/binding_id. Máximo 50 operaciones por transacción. Campos desconocidos, passwords, módulos/roles/permisos fuera de catálogo y environment distinto a dev se rechazan.

Teléfono: E.164 normalizado sin `+`, 7–15 dígitos, sin cero inicial. Cada línea requiere consentimiento y prueba de posesión externa independiente. `verification_ref` debe ser una referencia opaca no reutilizable como credencial, nunca un OTP/token. No versionar manifests reales.

## 6. Administración delegada

Solo se gestionan miembros/roles comerciales del workspace Telchi; ninguna operación modifica otros tenants, roles globales, módulos no habilitados o Srv05.

Grant incorpora la membresía organizacional de un usuario activo ya ligado al workspace y su rol comercial. Rechaza permisos efectivos fuera del catálogo y un rol comercial contaminado. No crea identidades ni otorga administración delegada a terceros.

Revoke-access retira el rol comercial, revoca líneas DEV Evolution del usuario y desactiva membresía/roles organizacionales locales. Conserva identidad y tombstones. Rechaza auto-revocación y perfiles/roles ajenos que exigirían reconciliación global, en vez de afirmar una revocación incompleta. Reactivar membresías o líneas revocadas requiere revisión global; no se reactivan silenciosamente.

Inspect devuelve UUIDs, permisos y UUID/usuario/estado de bindings, sin números ni comprobantes. Revoke-phone verifica propiedad exacta del binding y afecta solo esa línea. Auditoría atribuye cambios al actor y las reejecuciones sin cambios no agregan entidades/eventos administrativos innecesarios.

## 7. Multiusuario y multilínea

027 ya soporta varias líneas por usuario y unicidad del número por contexto. No se modificó la migración ni el resolver horizontal.

Prueba PG18: un usuario con dos bindings diferentes resuelve a la misma identidad y permiso; otro usuario con binding válido sin permiso comercial permanece sin permiso. Cambiar el grant se refleja inmediatamente en ambas líneas. Revocar una conserva la otra; revocar acceso cierra las restantes sin afectar otro usuario.

MessagingRepository real con 026 produce threads diferentes para dos números sobre el mismo canal. DEV no resuelve bindings como PROD; provider desconocido no concede identidad. Reasignar un número ya vinculado a otro usuario o reactivar un tombstone se rechaza.

La prueba usa solo identidades/números sintéticos en PostgreSQL descartable. No se creó ningún humano ficticio en operación.

## 8. Console/Auth y credenciales

Se reutiliza el verificador Console; no se introdujo autenticación propia ni se equiparó teléfono verificado con sesión PASETO web.

Bloqueo real: no existe un procedimiento de alta/activación/reset humano demostrado en este backend. `core_users` no contiene hash de contraseña y el bootstrap experimental no es login. Los comandos rechazan enrollment en lugar de inventar passwords o generar tokens impersonando personas.

Identidad existente compatible: requiere UUID activo y pertenencia directa al workspace Telchi. Identidad de otro workspace: requiere decisión/autorización de identidad en una ventana Console/Identity; este CLI no la traslada. Nueva identidad/credenciales: requiere identificar el mecanismo autenticado Team360 real o implementar la pieza faltante con ownership correspondiente, sin segundo sistema.

La verificación de posesión del teléfono sigue siendo un procedimiento externo del seed, validado mediante referencia/consentimiento por operador autorizado. No hay desafío OTP automatizado demostrado: una referencia y un booleano no acreditan por sí solos una posesión real. Binding vivo queda bloqueado hasta ese comprobante.

## 9. Validación PostgreSQL 18 y compatibilidad

Los tests de datos se ejecutaron únicamente en un contenedor PG18 descartable creado para esta tarea; el destino operacional solo se consultó read-only.

Imagen local reutilizada `postgres:18.1-alpine3.22`, contenedores propios `986553a8fca2…` y `03d19ed30d01…`, loopback puertos 32769/32770, base `telchi_provisioning_disposable`, 1 CPU/256 MiB, sin descarga/instalación de PostgreSQL. 001/002, DDL organizacional del seed anterior y 026/027 solo allí.

```bash
TELCHI_PROVISIONING_TEST_DSN=<DSN-descartable> uv run --no-sync pytest modules/telchi/provisioning/tests modules/telchi/assistant/tests tests/test_telchi_assistant_srv05.py tests/test_console_auth.py tests/test_console_bootstrap_service.py -q
```

Resultado final: **113 passed**, sin skips, una advertencia preexistente de Diagnosis in-memory en composición. [Salida final](admin-tests-final-v3.txt); [corrida anterior](admin-tests-final-v2.txt); [primer gate PG18](admin-tests-pg18.txt). La revisión final corrigió también el plan bootstrap grants para usar lecturas sin FOR UPDATE, y lo revalidó en una transacción READ ONLY real.

Cobertura ejecutada: seed inicial/repetido/existente/conflictos/rollback; actor global y delegado; admin de otro cliente y no-admin rechazados; manifest inválido y grants fuera del catálogo; transacción multioperación fallida sin cambio parcial; CLI con PASETO real sintético, archivos privados, dry-run READ ONLY, aplicación aislada, token inválido, pin incorrecto y trust PROD rechazados; revocación/idempotencia/auditoría; multiusuario/multilínea/conversaciones; Console/Auth/handler/Srv05 contratos.

Compatibilidad Messaging y PermissionConsoleRepository contra PG18: real. Handler/Srv05/Console bootstrap: regresiones con fixtures, no login humano ni servidor vivo. No llamadas a Luna/LLM, SAP, Evolution, Foundation ni WhatsApp externo.

## 10. Idempotencia y rollback

Los cambios se realizan en una transacción serializable con lock administrativo del seed; una operación fallida aborta toda la aplicación.

Se preservó el rollback protegido del seed: snapshots exactos, dependencias y modificaciones posteriores impiden borrar filas ajenas. Sus contratos existentes pasaron nuevamente. Un scaffold con usuarios/bindings/auditoría dependiente no se borra.

Los comandos delegados usan revocación y tombstones, no DELETE de teléfonos. No se agregó rollback genérico destructivo de memberships o cuentas. La reversión administrativa posterior al commit requiere revisión global; el rollback del seed debe invocarse en transacción autorizada tras `AdminRepository.global_actor`, con actor auditado en el procedimiento operacional. No hay comando legacy sin autorización disponible.

## 11. Aislamiento DEV y recursos

La configuración actual sigue apuntando al destino compartido `localhost:5432/team360`; no se acredita que sea exclusivamente DEV.

[Inspección actual sanitizada](admin-target-inspection.json): configuración base y override iguales; servidor 18.4; transaction_read_only=on; 0 organizaciones Telchi, 0 workspaces Telchi, 4 usuarios existentes, tabla 027 ausente. El contenedor compartido publica 5432 fuera de loopback. Una muestra de conexiones no demuestra ausencia de consumidores PROD.

No se crearon bases en infraestructura operacional ni se aplicaron DDL/DML. El PG descartable autorizado es solo validación, no una solución DEV instalada por comodidad.

Host inicial: 8 cores, load 1.08/1.46/1.32, ~5.5 GiB disponibles, swap histórica ~4.2 GiB sin crecimiento en muestras. Final: load 2.05/1.99/1.64, ~5.7 GiB disponibles, swap ~4.2 GiB, CPU mayormente libre. Un pytest secuencial y un PG limitado; sin browsers.

```text
HOST_PREFLIGHT=BUSY_BUT_SAFE
RESOURCE_GUARD=PASS
CONCURRENCY_USED=1 pytest worker + 1 capped PG test container
UNRELATED_PROCESSES_TERMINATED=0
ENVIRONMENTAL_ABORTS=0
OWN_PROCESSES_LEFT_RUNNING=0
```

Ambos contenedores propios detenidos y eliminados con volúmenes; filtro de etiqueta propio sin contenedores vivos. CLI hijos terminaron vía communicate; todos los tests finalizaron. Servicios ajenos intactos.

## 12. Datos humanos y condiciones para aplicar

No se necesitan passwords ni códigos por chat. La siguiente etapa necesita personas autorizadas y resolver primero los bloqueos de autenticación y destino.

- Administrador y piloto: nombre, email Team360, rol Telchi, uno o varios WhatsApp; pueden coincidir. Datos reales exclusivamente privados.
- UUIDs de identidades existentes, organización/workspace aprobados y actor global autenticado.
- Consentimiento y comprobante independiente de control de cada línea, custodiados privadamente.
- Scope comercial aprobado: solo cantidades documentales `telchi.sales_top_items.source_quantity.20260101_20260915.v1`, no facturación neta ni acceso total.
- Acreditación de destino DEV/consumidores, ventana DDL/DML, backup/restore, issuer humano seguro; después autorización específica para 027, composición/instance/receiver DEV y prueba WhatsApp.

No pedir credenciales al usuario para suplir el mecanismo ausente.

## 13. Operaciones no ejecutadas y bloqueos

No hay provisioning operacional ni readiness WhatsApp demostrado; los PASS aislados no sustituyen permisos humanos o infraestructura segura.

No ejecutado: crear Telchi operacionalmente, crear/mover/deshabilitar cuentas humanas reales, modificar permisos operacionales, aplicar 027, registrar teléfonos reales, habilitar módulos/canales productivos, enviar WhatsApp, deploy.

Bloqueos reales: aislamiento PG DEV no acreditado; alta/activación/login humano seguro no localizado; personas autorizadas pendientes; verificación real de posesión pendiente; habilitación persistida de módulos no demostrada; dry-run no simula todos los conflictos de filas; rollback delegado post-commit no automatizado.

Próximo paso no puede reducirse todavía a cargar nombre/email/teléfono: primero designar mecanismo de identidad autenticada y destino autorizado. Resolver esas piezas exige coordinación del ownership correspondiente, no cambios silenciosos a Auth o infraestructura desde Telchi.

## 14. Estados finales

PASS de multilínea describe contratos en PG18 aislado. PARTIAL describe código probado con capacidades o garantías faltantes; BLOCKED describe aplicación/readiness operacional.

```text
TEAM360_ADMIN_BOOTSTRAP_V1=PARTIAL
TELCHI_CLIENT_BOOTSTRAP=PARTIAL
TELCHI_DELEGATED_ADMINISTRATION=PARTIAL
TELCHI_MULTIUSER_MULTIPHONE=PASS
TELCHI_ADMIN_CLI=PARTIAL
TELCHI_DEV_PG_ISOLATION=BLOCKED
TELCHI_OPERATIONAL_PROVISIONING=BLOCKED
TELCHI_WHATSAPP_DEV_READY=BLOCKED

CODE_IMPLEMENTED=YES
LOCAL_TESTS=PASS
PG18_ISOLATED_TESTS=PASS
OPERATIONALLY_APPLIED=NO
LIVE_WHATSAPP_VERIFIED=NO
```

Validaciones `lat check md`, `index`, `sections`, `code-refs`, `lat check` y `git diff --check`: todas PASS, registradas en `admin-lat-*.txt` y `admin-diff-check.txt`. Se revisaron los archivos finales y se comprobó whitespace también en archivos nuevos untracked con `git diff --no-index --check`. Impacto transversal: ninguno en implementación compartida; únicamente se cierra la vía de ejecución legacy sin actor en provisioning local. Los consumidores operacionales permanecen sin modificar.
