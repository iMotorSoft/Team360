# Telchi DEV tenant provisioning V1

Procedimiento preparado y probado; no aplicado a la base operacional. El siguiente paso requiere autorizaciones específicas, no otro diagnóstico general de identidad.

## A. Estado inicial y destino

La rama es `feature/console-backend-core`, HEAD `09d2ec715a31bb88574d734eacb9f437f008624e`. Todos los cambios preexistentes fueron preservados; no hubo commit, deploy ni edición GLOBAL/SHARED.

- Evidencia nueva: [inspección inicial](tenant-target-inspection.json) e [inventario focalizado](tenant-target-inspection-r2.json). No existía `pg18_identity_reuse.md`.
- Configuración base y override `.env.backend-dev.local`: `localhost:5432/team360`, PostgreSQL **18.4**, `public`, rol `administrator`, superusuario. Consultas con `default_transaction_read_only=on`, timeout 5 s.
- Organizaciones: `team360_platform`, `team360_live`. Único workspace: `team360_public_site`. Ninguna organización/workspace Telchi ni permiso equivalente comercial encontrado.
- Cuatro usuarios activos: dos en workspace público y dos sin workspace. Ninguno autorizado por este pedido como persona Telchi; no se publicó PII ni se asumió que un administrador Team360 representa al cliente.
- Membresías administrativas existentes: `organization_admin`, `organization_owner`, `technical_admin`, `content_admin`, en organizaciones Team360. Estas convenciones se reutilizan sin otorgar privilegios globales.
- En los roles login inspeccionados, solo `administrator` tiene INSERT en `core_workspaces` y UPDATE en `core_users`. El inventario completo de esas dos facultades está en JSON; no representa un análisis universal de ACL.
- La observación de `pg_stat_activity` mostró únicamente la consulta actual en `team360`. **No prueba ausencia de consumidores productivos**: servicios desconectados, cron y clientes remotos pueden volver a conectarse.
- Contenedor compartido `imotorsoft-postgres`, PG18, publica 5432 también fuera de loopback. La documentación histórica `postgresql_live_team360_setup.md` registra que `team360_dev` fue eliminada y se eligió `team360` como base viva. `TEAM360_ENV=development` no cambia ese alcance.
- El launcher baseline sigue usando Srv01 y la composición Telchi Srv05 recibe el pool existente. No se levantó Srv05 ni se certificó un proceso DEV vivo utilizando otra base.
- `messaging_phone_bindings` no existe en el destino inspeccionado. **Cero DDL/DML operacional ejecutado.**

## B. Modelo reutilizado y límites reales

El seed utiliza únicamente entidades existentes y SQL parametrizado con psycopg async. Las transacciones pertenecen al caller; no agrega tablas, pools ni un motor de identidad.

- Organización: `core_organizations.organization_code` UNIQUE, `primary_type=client`, status active; workspace mediante FK `core_workspaces.organization_id`.
- Miembros: UNIQUE `(organization_id,user_id)`; roles de miembro UNIQUE `(organization_member_id,role_code)`. `organization_admin` es una convención real observada.
- `core_organization_roles` expresa roles organizacionales como `client`; **no tiene FK desde el código de rol del miembro**. El seed no confunde ese registro con un permiso RBAC.
- RBAC: `core_permissions` → `core_role_permissions` → rol local `core_roles` → `core_user_roles`. No usa perfiles globales, FULL_ACCESS ni permisos de Knowledge/Flow.
- `PermissionConsoleRepository` exige usuario active/testing con **workspace directo igual** al solicitado. Una membresía organizacional no habilita automáticamente un segundo workspace. El seed rechaza usuarios de otro workspace y usuarios inactivos; no los mueve ni duplica.
- Console `service.py` aún usa `_provisional_organization_context`; su comentario indica que el consumo de tablas organizacionales está diferido. Registrar un administrador organizacional **no acredita una API de gestión de organización operativa**. No se modificó Console para ocultar esta limitación.
- Auditoría: `core_events`, correlación de corrida, snapshots de filas nuevas y referencias opacas a aprobaciones; actor admin en fase grants. Eventos sin FK al scaffold permiten conservar auditoría al revertirlo.
- El esquema organizacional no tiene migración fuente localizada en `001`–`027`. Para probar se exportó exclusivamente su DDL real con `pg_dump --schema-only --no-owner --no-privileges`, sin filas. El fixture **no es una nueva migración operacional**.

## C. Definición del aprovisionamiento

Dos fases evitan crear usuarios ficticios: primero scaffold; luego grants sobre UUIDs humanos ya registrados y activos en el workspace Telchi.

| Entidad | Definición preparada | Aplicación operacional |
| --- | --- | --- |
| Organización | código `telchi`, nombre Telchi, tipo client; UUID fijado por manifest | No aplicada |
| Workspace | slug `telchi_dev`, nombre Telchi DEV, testing, FK organización; UUID fijado | No aplicado |
| Administrador | miembro Telchi active, rol de miembro `organization_admin`; rol organizacional `client` | Persona pendiente de aprobación |
| Piloto | miembro Telchi active; puede ser el mismo admin | Persona pendiente de aprobación |
| Permiso | `telchi.sales.source_quantity.read.v1` | Nombre y alcance pendientes de aprobación del dueño comercial |
| Rol comercial | `telchi_source_quantity_reader_v1`, local al workspace; solo permiso anterior | No asignado |
| Canal opcional | `telchi_whatsapp_dev`, provider Evolution existente, testing, horizontal_v1, dev, tenant telchi | Instance/receiver aprobados pendientes |
| Módulo | política explícita `BusinessPolicy` del handler existente | Deshabilitado por defecto |

La habilitación real se realiza mediante `create_telchi_app(policy=..., pool=...)`, puerto de inyección existente de Srv05. `runtime_policy()` produce ese contrato, pero nunca activa nada por éxito del seed. No hay un catálogo persistido de módulos por workspace demostrado aquí.

No se crean `assistant_instances` ni `automation_packages`: Telchi no es una instalación ficticia de Diagnosis ni una automatización. El registro estático de Srv05, registro del handler, habilitación de política y canal son operaciones distintas.

## D. Seed, aplicación y rollback

Los archivos nuevos están exclusivamente en `SrvRestAstroLS_v1/backend/modules/telchi/provisioning/`; los cambios de datos se detienen antes de conectar si faltan aprobaciones.

- `repository.py`: scaffold/grants/canal opcional; detección de equivalencias Telchi con otro código o workspace; diferencias de UUID, estado o atributos provocan conflicto. No contiene `ON CONFLICT DO UPDATE`.
- `cli.py`: plan sin conexión por defecto, `--apply` explícito y DSN privado sin fallback global. Exige referencias a acreditación DEV, impacto productivo, identidades humanas, permiso, respaldo, aplicación y membresía administrativa.
- `inspect_target.py`: inspección read-only focalizada sin PII/secrets; preserva evidencia existente.
- `phone_binding.py`: procedimiento posterior a 027, consentido/verificado; no inscribe teléfonos automáticamente.
- `tests/test_provisioning_pg18.py` y `tests/organization_schema_pg18.sql`: integración contra PostgreSQL 18 descartable y DDL organizacional real.

### Manifest privado

Crear el manifest en PRIVATE_ROOT después de las decisiones humanas. Los placeholders siguientes se sustituyen; no son usuarios ni destinos aprobados.

```json
{
  "seed": {
    "workspace_id": "UUID-DEL-WORKSPACE-APROBADO",
    "organization_id": "UUID-DE-LA-ORGANIZACION-APROBADA",
    "stage": "scaffold",
    "admin_id": null,
    "pilot_id": null,
    "provider_instance": null,
    "receiver_context": null
  },
  "target": {
    "database": "BASE-DEV-ACREDITADA",
    "system_identifier": "IDENTIFICADOR-PG-OBSERVADO",
    "server_address": "IP-OBSERVADA-POR-PG",
    "server_port": 5432
  },
  "approvals": {
    "dev_isolation": "REFERENCIA-A-EVIDENCIA",
    "no_production_impact": "REFERENCIA-A-INVENTARIO-DE-CONSUMIDORES",
    "human_identities": "REFERENCIA-A-PERSONAS-Y-ALTA-APROBADAS",
    "business_permission": "REFERENCIA-A-APROBACION-CAPABILITY-Y-SCOPE",
    "backup_restore": "REFERENCIA-A-BACKUP-Y-RESTAURACION-PROBADA",
    "explicit_application": "REFERENCIA-A-VENTANA-Y-OPERADOR-AUTORIZADO",
    "organization_admin_membership": "REFERENCIA-A-ADMIN-DEL-CLIENTE"
  }
}
```

El pin se obtiene read-only en el destino autorizado con `current_database()`, `(pg_control_system()).system_identifier::text`, `inet_server_addr()::text`, `inet_server_port()`. El CLI compara exactamente esos cuatro campos antes del seed; no toma el nombre de base como prueba DEV.

Desde backend, con DSN cargado fuera de Git y sin imprimirlo:

```bash
uv run --no-sync python -m modules.telchi.provisioning.cli --manifest "$TELCHI_PRIVATE_MANIFEST"
# Solo después de acreditación y autorización explícita:
uv run --no-sync python -m modules.telchi.provisioning.cli --manifest "$TELCHI_PRIVATE_MANIFEST" --apply
```

Después del scaffold, el operador registra o vincula **las personas reales aprobadas mediante la administración de identidad vigente**, con `core_users.workspace_id` igual al UUID elegido. El seed no crea cuentas ni emite tokens. Si la persona existente está en otro workspace, se debe aprobar una vinculación compatible antes de grants; no se duplica por email.

No se encontró un endpoint Console de invitación/alta organizacional que garantice esa vinculación: Auth verifica tokens, no inscribe personas. Esta operación requiere el administrador de identidad existente; el seed no afirma haber completado login humano.

Cambiar el mismo manifest a `stage=grants` con `admin_id` y `pilot_id` aprobados, y ejecutar el mismo CLI. Para canal, agregar la instance DEV y receiver exactos; se exige provider Evolution ya existente, sin crear/modificar configuración Evolution.

Cada corrida guarda solo filas insertadas. Reejecutar sin cambios produce `created=[]` y ninguna nueva entidad/auditoría de creación. Para reversión autorizada:

```bash
uv run --no-sync python -m modules.telchi.provisioning.cli --manifest "$TELCHI_PRIVATE_MANIFEST" --apply --rollback-run "$TELCHI_CREATED_RUN_ID"
```

Rollback elimina en orden inverso solo snapshots intactos de esa corrida, dentro de una transacción. Cualquier edición posterior o dependencia superviviente, incluso FK CASCADE/SET NULL, provoca aborto. Las identidades preexistentes y los eventos no se eliminan. Un workspace con humanos/bindings no se borra: primero revocar grants propios; conservar scaffold y tombstones cuando corresponde.

Las referencias a aprobaciones no verifican criptográficamente una autorización humana: son un gate del operador y trazabilidad, no una nueva autoridad IAM. El caller directo del repository debe respetar las mismas condiciones y límites.

## E. Permiso y teléfono

El permiso candidato es horizontal y acotado a la única capability documental disponible, no a todos los datos de ventas.

- Capability exacta: `telchi.sales_top_items.source_quantity.20260101_20260915.v1`.
- Autoriza cantidades de documentos fuente por producto, ventana fija enero–15 septiembre 2026, top 10, unidades originales. No autoriza facturación monetaria, net sales, otro período, filtros por sucursal/canal ni SAP/HANA.
- Scope: todo **este workspace Telchi**, solo esta capability. Si el humano requiere una subárea/sucursal, mantener bloqueado: el resolver actual aplana los perfiles de área y el handler exige scope whole-workspace acreditado.
- La referencia Foundation CURRENT `foundation_afd08d9eca6a725be53cdc3f9d5709c9` y snapshot de publicación `1408` son evidencia previa del contexto, no una nueva lectura/validación realizada aquí. No se modificó Foundation ni se confundió snapshot general DuckLake.
- El handler vuelve a consultar permisos efectivos en cada ejecución de datos; la revocación se comprobó contra DB. El binding no contiene permisos duplicados. Revocar una membresía organizacional sola no revoca RBAC automáticamente: retirar también el grant comercial y revocar el binding si se termina el acceso.

### Aplicación autorizada de 027

Utilizar exactamente la migración existente; nunca aplicar una tabla alternativa ni ejecutarla automáticamente desde el seed.

1. Confirmar el target pin/DEV, backup/restore y autorización DDL independiente. Dependencias: `core_workspaces`, `core_users`, `core_events`, `communication_providers(code)` y PL/pgSQL.
2. Comprobar `to_regclass('public.messaging_phone_bindings')`. Si existe, validar mediante `PhoneIdentityRepository.validate_schema()` y revisar columnas/constraints/trigger; **027 no es idempotente**, no repetir CREATE ni adoptar por el nombre.
3. Con servicio PostgreSQL privado y `PGPASSFILE` privado, sin credentials en argv ni logs, desde backend ejecutar lo siguiente.

```bash
psql -X -v ON_ERROR_STOP=1 -f db/migrations/027_team360_messaging_phone_bindings.sql
```

`PGSERVICE` debe apuntar exclusivamente al destino acreditado; comprobar el pin en esa misma conexión antes de DDL. Migración 026 es un requisito del transporte horizontal, no de 027: validar sus cuatro índices con `MessagingRepository.validate_transport_schema()` y aplicar 026 únicamente con autorización específica si falta.

En prueba aislada se comprobó 027 nuevamente. El rollback DDL `DROP TABLE messaging_phone_bindings; DROP FUNCTION messaging_phone_binding_audit();` pertenece al procedimiento existente, con transacción y autorización; **no usar en operación con bindings reales**. Para operación, la reversión normal es revocación con timestamp y auditoría, nunca DELETE.

### Vinculación consentida

Verificar externamente persona, control del teléfono y consentimiento; guardar solo referencia opaca del comprobante. Evolution histórico no es evidencia suficiente.

En una transacción del pool DEV acreditado, invocar `bind_verified_dev_phone()` con workspace, piloto, admin actor, sender normalizado E.164 sin `+`, referencia y `consent_verified=True`. Esto es un procedimiento administrativo posterior, no una operación que esta ejecución haya realizado.

El procedimiento verifica membresía Telchi, administrador organizacional, permiso efectivo, esquema 027 y unicidad del sender DEV. Repetición exacta devuelve el mismo binding; revocado, proof diferente, otro usuario o sender ambiguo se rechazan. El trigger audita sin teléfono ni secretos.

Runtime resuelve solo el tenant/workspace del canal confiable: un registro en otro scope no concede acceso a este. Unicidad DB impide dos registros en el mismo scope; el procedimiento de piloto es más restrictivo y rechaza sender existente en múltiples scopes DEV. DEV no autoriza PROD.

## F. Tests e integración

La validación real de datos se realizó exclusivamente en un contenedor PostgreSQL 18 descartable, no en `team360`. Srv05/handler se verificaron con contratos sin WhatsApp externo.

- Imagen local `postgres:18-alpine`, DB `telchi_provisioning_disposable`, puerto loopback efímero, límite 1 CPU/256 MiB. DDL organizacional exportado read-only del servidor 18.4; RBAC fuente 001/002; migración 027 existente.
- Comando: `TELCHI_PROVISIONING_TEST_DSN=<dsn-descartable> uv run --no-sync pytest modules/telchi/provisioning/tests/test_provisioning_pg18.py modules/telchi/assistant/tests tests/test_telchi_assistant_srv05.py -q`.
- Resultado final: **74 passed**, una advertencia de Diagnosis in-memory en test de composición, sin cambios a Diagnosis. [Salida final](tenant-tests-final-v3.txt).
- Cubierto: seed inicial; segunda ejecución; conflictos organización/workspace; admin existente; admin sin permiso comercial; piloto autorizado; revocación inmediata; aislamiento tenants; rollback completo de scaffold intacto y rollback grants conservando usuarios; rechazo de rollback con dependencias/ediciones; misma persona admin/piloto; canal horizontal; binding consentido/idempotente; proof distinto/ambiguo rechazado; separación DEV/PROD; FK/unicidad y auditoría.
- Primer intento de fixture falló por search_path vacío de pg_dump: se corrigió únicamente el montaje de test. Una expectativa posterior confundía duplicidad entre scopes con ambigüedad dentro del scope; se corrigió el test al contrato real, conservando rechazo administrativo estricto. Una revalidación final arrancó antes de que PG estuviera listo (ENVIRONMENTAL_ABORT, conexión cerrada); se repitió tras pg_isready y pasó. Salidas anteriores preservadas, no ocultadas como PASS.
- Compatibilidad PG/PermissionConsoleRepository y datos para Messaging: comprobada real en entorno descartable. Handler/Srv05: contratos de regresión. Web TelchiAI no fue modificado ni se declara sesión Web RBAC real.
- **No se envió ningún mensaje externo ni se verificó login humano/WhatsApp vivo.**

Host observado: 8 cores, load ~3, ~5.6 GiB disponibles, swap histórica ~4.1 GiB sin crecimiento en muestras vmstat, CPU mayormente libre. Presupuesto conservador: un pytest secuencial y un PG pequeño; sin browsers/LLM/SAP.

```text
HOST_PREFLIGHT=BUSY_BUT_SAFE
RESOURCE_GUARD=PASS
CONCURRENCY_USED=1 pytest worker + 1 capped PostgreSQL test container
UNRELATED_PROCESSES_TERMINATED=0
ENVIRONMENTAL_ABORTS=1 (startup del PG descartable antes de readiness)
OWN_PROCESSES_LEFT_RUNNING=0
```

Los tres contenedores propios (`d9e1dd1a7d2b…`, `32047b854b82…`, `8e58881279e3…`) fueron identificados, detenidos y eliminados con sus volúmenes; el último produjo la salida final. La última observación mostró load 3.58, ~5.3 GiB disponibles y swap 4.2 GiB; se mantuvo el presupuesto conservador. Evolution y servicios ajenos quedaron intactos.

## G. Operaciones y autorizaciones pendientes

Estos pendientes son condiciones concretas de aplicación; no habilitan una auditoría general ni reconstrucción de componentes validados.

1. Dueño operacional: acreditar si `team360` es exclusivamente DEV, con inventario de consumidores/cron/deploy y DSNs productivos sanitizados. Una sesión instantánea vacía no basta. Autorizar por escrito DDL/DML específicos.
2. Si no puede acreditarse: aprobar **una base lógica DEV en el PostgreSQL 18 existente**, con rol propietario/runtime no-superusuario y sin acceso al public operacional. Restaurar solo esquema revisado y datos mínimos autorizados, no clonar personas/proveedores productivos indiscriminadamente. No se creó esa base ni se propone otro servidor operacional.
3. Backup: herramientas PG18 `pg_dump` verificadas disponibles en el contenedor compartido. Preparar backup privado `pg_dump -Fc` del destino aprobado y probar restore aislado; seleccionar custodio/retención. No se ejecutó ni acreditó un backup operativo vigente.
4. Cliente: aprobar UUID/identidad real del administrador y piloto (pueden coincidir), alta/vinculación directa a workspace y alcance de `organization_admin`. No reutilizar global admin ni mover usuarios ajenos automáticamente.
5. Dueño comercial: aprobar nombre `telchi.sales.source_quantity.read.v1` y capability/scope whole-workspace descritos. Si se exige scope menor, esta entrega no lo habilita.
6. Operador Srv05: aprobar instance/receiver DEV y composición existente con `runtime_policy(seed_grants, module_enable_approved=True, whole_workspace_approved=True)`. No existe registro DB de instalación de módulo demostrado; no crear uno ficticio para el gate.
7. Aplicar 027 (y 026 solo si su preflight lo requiere) en la ventana DDL autorizada; vincular el teléfono consentido con el procedimiento preparado y recién entonces ejecutar WhatsApp externo.

**Límite importante al siguiente paso exclusivamente operacional:** la prueba WhatsApp puede usar el contrato existente, pero administración empresarial por Console y alta humana no quedan certificadas por el seed. Si se exige UI/API organizacional completa, requiere una ventana Console separada; no se declara resuelto aquí.

## H. Estados finales

PASS del seed significa prueba descartable; los estados de identidad/módulo/binding siguientes describen operación, no fixtures.

```text
TELCHI_DEV_TENANT_SCHEMA=PASS
TELCHI_DEV_PROVISIONING_SEED=PASS
TELCHI_DEV_SEED_IDEMPOTENCY=PASS

TELCHI_DEV_ORGANIZATION=BLOCKED
TELCHI_DEV_WORKSPACE=BLOCKED
TELCHI_DEV_ADMIN=BLOCKED
TELCHI_DEV_MODULE_ENABLED=BLOCKED
TELCHI_DEV_BUSINESS_PERMISSION=BLOCKED

TELCHI_DEV_PHONE_BINDING=BLOCKED
TELCHI_DEV_PG_ISOLATION=BLOCKED

TELCHI_DEV_IDENTITY_READY=BLOCKED
TELCHI_DEV_WHATSAPP_READY=BLOCKED

SCHEMA_VALIDATED=YES (DDL real organizacional + RBAC + 027 en PG18 descartable)
SEED_TESTED=YES
OPERATIONALLY_APPLIED=NO
LIVE_VERIFIED=NO
```

Validaciones documentales y revisión final: `lat check md`, `lat check index`, `lat check sections`, `lat check code-refs`, `lat check`, `git diff --check`. Evidencia `tenant-lat-*.txt`; sin cambios LAT/GLOBAL ni impacto sobre Flow, Mamamia, Diagnosis, Messaging, Luna, State Engine o Data Lake.
