# Migracion 002 — RBAC, Paquetes, Workers y Knowledge

Fecha: 2026-05-29
Estado: **APLICADA sobre team360 el 2026-05-29**
Proximo paso: auditar cambios futuros y disenar 003 pgvector/embeddings.

## Objetivo

Disenar y preparar el schema PostgreSQL que soporta:

1. RBAC minimo (areas, roles, permisos, perfiles).
2. Planes, features y limites por paquete.
3. Assistant instances.
4. Automation packages.
5. Workers (definiciones, package_workers, configs).
6. Credenciales genericas (por referencia, sin secretos planos).
7. Knowledge scopes, scope bindings, documentos y chunks.
8. Extension de `task_runs` para vinculacion con packages/workers/areas.
9. Convencion de eventos en `core_events` para package/worker/knowledge.

## DB objetivo

`team360` — misma DB de la migracion 001.

## Principios de diseno

- `CREATE TABLE IF NOT EXISTS` — idempotente, permite re-ejecucion.
- `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` para extender `task_runs` sin romperla.
- `gen_random_uuid()` consistente con 001 (no uuidv7).
- `timestamptz` con sufijo `_utc`.
- `jsonb` para config flexible, evitar EAV.
- Foreign keys a `core_workspaces`, `core_users` y tablas de 001.
- Indices unicos parciales para `UNIQUE(workspace_id, code)` cuando `workspace_id` es nullable.
- Check constraints para estados y valores controlados.
- **No usar `bypassed`** en approval_status (contradice reglas de seguridad/HITL).
- Seeds idempotentes con `ON CONFLICT` solo para catalogos no sensibles.
- No cargar datos reales de clientes.

## 1. RBAC minimo

### core_workspace_areas

Almacena areas o sectores dentro de un workspace. Ej: `ventas`, `administracion`, `produccion`, `soporte`.

```
id              uuid PK
workspace_id    FK -> core_workspaces(id) NOT NULL
area_code       text (unique por workspace)
display_name    text
description     text nullable
status          text check
created_at_utc  timestamptz
updated_at_utc  timestamptz
```

Unique: `(workspace_id, area_code)` — areas siempre estan dentro de un workspace.

### core_permissions

Catalogo global de permisos del sistema.

```
id              uuid PK
permission_code text UNIQUE
display_name    text
description     text nullable
category        text nullable (agrupacion logica)
created_at_utc  timestamptz
```

Permisos iniciales:
`dashboard.view`, `task.view`, `task.assign`, `task.execute`, `task.approve`, `task.reject`, `task.comment`, `package.view`, `package.configure`, `package.pause`, `worker.view`, `worker.configure`, `worker.execute`, `knowledge.view`, `knowledge.upload`, `credential.view_ref`, `credential.manage_ref`, `audit.view`, `user.manage`, `role.manage`

### core_roles

Roles del sistema. Pueden ser globales Team360 (`workspace_id IS NULL`) o por workspace.

```
id              uuid PK
workspace_id    FK -> core_workspaces(id) nullable (null = rol global Team360)
role_code       text
display_name    text
description     text nullable
is_system_role  boolean default false
status          text check
created_at_utc  timestamptz
updated_at_utc  timestamptz
```

Unicos parciales:
- `UNIQUE(role_code) WHERE workspace_id IS NULL` — roles globales.
- `UNIQUE(workspace_id, role_code) WHERE workspace_id IS NOT NULL` — roles por workspace.

### core_role_permissions

Asignacion de permisos a roles.

```
id              uuid PK
role_id         FK -> core_roles(id) ON DELETE CASCADE
permission_id   FK -> core_permissions(id) ON DELETE CASCADE
created_at_utc  timestamptz
UNIQUE (role_id, permission_id)
```

### core_permission_profiles

Perfiles reutilizables de permisos. Ej: `operador_basico`, `supervisor`, `admin_workspace`.

Pueden ser globales (`workspace_id IS NULL`) o por workspace.

```
id              uuid PK
workspace_id    FK -> core_workspaces(id) nullable (null = global)
profile_code    text
display_name    text
description     text nullable
status          text check
created_at_utc  timestamptz
updated_at_utc  timestamptz
```

Unicos parciales:
- `UNIQUE(profile_code) WHERE workspace_id IS NULL`
- `UNIQUE(workspace_id, profile_code) WHERE workspace_id IS NOT NULL`

### core_profile_permissions

Asignacion de permisos a perfiles.

```
id              uuid PK
profile_id      FK -> core_permission_profiles(id) ON DELETE CASCADE
permission_id   FK -> core_permissions(id) ON DELETE CASCADE
created_at_utc  timestamptz
UNIQUE (profile_id, permission_id)
```

### core_user_roles

Asignacion de roles a usuarios.

```
id              uuid PK
user_id         FK -> core_users(id) ON DELETE CASCADE
role_id         FK -> core_roles(id) ON DELETE CASCADE
created_at_utc  timestamptz
UNIQUE (user_id, role_id)
```

### core_user_profiles

Asignacion de perfiles a usuarios, con area opcional.

```
id              uuid PK
user_id         FK -> core_users(id) ON DELETE CASCADE
profile_id      FK -> core_permission_profiles(id) ON DELETE CASCADE
area_id         FK -> core_workspace_areas(id) ON DELETE SET NULL nullable
created_at_utc  timestamptz
```

Unicos parciales:
- `UNIQUE(user_id, profile_id, area_id) WHERE area_id IS NOT NULL`
- `UNIQUE(user_id, profile_id) WHERE area_id IS NULL`

Permite asignar el mismo perfil en areas distintas.

## 2. Planes, features y limites

### package_plans

Catalogos de planes disponibles globalmente.

```
id              uuid PK
plan_code       text UNIQUE
display_name    text
description     text nullable
sort_order      integer default 0
status          text check
created_at_utc  timestamptz
updated_at_utc  timestamptz
```

Planes: `starter`, `operational`, `premium_erp`, `enterprise_custom`

### package_features

Catalogo global de features.

```
id              uuid PK
feature_code    text UNIQUE
display_name    text
description     text nullable
category        text nullable
status          text check
created_at_utc  timestamptz
```

Features iniciales:
`diagnosis.basic`, `dashboard.basic`, `dashboard.by_area`, `rag.simple`, `graphrag.enabled`, `approval.basic`, `approval.multi_level`, `events.basic`, `audit.advanced`, `workers.internal`, `workers.external`, `package_worker.config`, `erp.read_only`, `erp.assisted`, `erp.write_approval`, `marketplace.ops`, `crm.integration`

### package_plan_features

Features incluidas en cada plan, con limites opcionales.

```
id              uuid PK
plan_id         FK -> package_plans(id) ON DELETE CASCADE
feature_id      FK -> package_features(id) ON DELETE CASCADE
max_value       integer nullable (limite numerico, null = sin limite)
metadata_jsonb  jsonb default '{}'
created_at_utc  timestamptz
UNIQUE (plan_id, feature_id)
```

### workspace_plan_subscriptions

Suscripcion de un workspace a un plan. Soporta historial de suscripciones.

```
id                  uuid PK
workspace_id        FK -> core_workspaces(id) ON DELETE CASCADE
plan_id             FK -> package_plans(id) ON DELETE RESTRICT
status              text check
started_at_utc      timestamptz
ended_at_utc        timestamptz nullable (fecha de terminacion, natural o por cancelacion)
expires_at_utc      timestamptz nullable
metadata_jsonb      jsonb default '{}'
created_at_utc      timestamptz
updated_at_utc      timestamptz
```

Unico parcial: `UNIQUE(workspace_id) WHERE status = 'active'` — solo una suscripcion activa por workspace. El historial se mantiene con registros previos en estado `expired` o `cancelled`.

## 3. Assistant instances

### assistant_instances

Instancias concretas de asistentes por workspace.

```
id                      uuid PK
workspace_id            FK -> core_workspaces(id) ON DELETE CASCADE
assistant_type          text
name                    text
status                  text check
embed_config_jsonb      jsonb default '{}'
public_config_jsonb     jsonb default '{}'
default_knowledge_scope_id  uuid nullable (SIN FK — ver nota)
settings_jsonb          jsonb default '{}'
created_at_utc          timestamptz
updated_at_utc          timestamptz
```

Nota: `default_knowledge_scope_id` no tiene FK a `knowledge_scopes` para evitar dependencia circular (un assistant puede tener un scope, y un scope puede bindearse a un assistant). La resolucion del scope por defecto se hace via `knowledge_scope_bindings` con `is_default = true` y `binding_type = 'assistant_instance'`.

## 4. Automation packages

### automation_packages

Paquetes de automatizacion contratados por workspace.

```
id                      uuid PK
workspace_id            FK -> core_workspaces(id) ON DELETE CASCADE
assistant_instance_id   FK -> assistant_instances(id) ON DELETE SET NULL nullable
package_code            text (unique por workspace)
package_name            text
plan_code               text FK -> package_plans(plan_code)
status                  text check
enabled_features_jsonb  jsonb default '[]'
limits_jsonb            jsonb default '{}'
settings_jsonb          jsonb default '{}'
created_at_utc          timestamptz
updated_at_utc          timestamptz
```

Unique: `(workspace_id, package_code)` — no global.

## 5. Workers

### worker_definitions

Capacidad generica de un worker. No pertenece a un workspace.

```
id                  uuid PK
worker_code         text UNIQUE
display_name        text
description         text nullable
worker_kind         text
default_mode        text
capabilities_jsonb  jsonb default '{}'
status              text check
created_at_utc      timestamptz
updated_at_utc      timestamptz
```

Worker kinds iniciales: `browser`, `api`, `desktop`, `interpreter`, `classifier`, `approval`, `notification`.

### package_workers

Uso concreto de un worker dentro de un paquete de un workspace.

```
id                      uuid PK
workspace_id            FK -> core_workspaces(id) ON DELETE CASCADE
automation_package_id   FK -> automation_packages(id) ON DELETE CASCADE
worker_definition_id    FK -> worker_definitions(id) ON DELETE RESTRICT
package_worker_code     text (alias unico dentro del paquete)
status                  text check
mode                    text check
knowledge_scope_id      FK -> knowledge_scopes(id) ON DELETE SET NULL nullable (via ALTER)
created_at_utc          timestamptz
updated_at_utc          timestamptz
```

Unique: `(automation_package_id, package_worker_code)`.
Modes: `read_only`, `assisted`, `approval_required`, `execution`, `blocked`.

Nota: `knowledge_scope_id` FK se agrega via ALTER TABLE al final para evitar dependencia circular durante CREATE.

### package_worker_configs

Configuracion especifica de un package_worker.

```
id                      uuid PK
package_worker_id       FK -> package_workers(id) ON DELETE CASCADE (UNIQUE)
config_jsonb            jsonb default '{}'
allowed_actions_jsonb   jsonb default '[]'
blocked_actions_jsonb   jsonb default '[]'
limits_jsonb            jsonb default '{}'
requires_human_approval boolean default false
created_at_utc          timestamptz
updated_at_utc          timestamptz
```

## 6. Credenciales genericas

### credential_references

Referencias a credenciales externas. **Nunca almacena tokens/keys reales.**

Solo `secret_ref` (referencia a un vault externo o variable de entorno).
`metadata_jsonb` NO debe contener `password`, `passwd`, `token`, `api_key`, `apikey`, `secret`, `private_key` ni `credential`.

```
id                      uuid PK
workspace_id            FK -> core_workspaces(id) ON DELETE CASCADE
automation_package_id   FK -> automation_packages(id) ON DELETE CASCADE nullable
package_worker_id       FK -> package_workers(id) ON DELETE CASCADE nullable
credential_type         text
provider_code           text nullable
secret_ref              text
status                  text check
metadata_jsonb          jsonb default '{}' (NO almacenar secretos aqui)
created_at_utc          timestamptz
updated_at_utc          timestamptz
```

## 7. Knowledge scopes

### knowledge_scopes

Alcance de conocimiento. Ya NO tiene `binding_type`/`binding_id` — eso se mueve a `knowledge_scope_bindings`.

```
id                      uuid PK
workspace_id            FK -> core_workspaces(id) ON DELETE CASCADE nullable
scope_code              text
name                    text
retrieval_mode          text default 'none'
graph_enabled           boolean default false
settings_jsonb          jsonb default '{}'
status                  text check
created_at_utc          timestamptz
updated_at_utc          timestamptz
```

retrieval_mode: `none`, `rag`, `graphrag`, `hybrid`

Unicos parciales:
- `UNIQUE(scope_code) WHERE workspace_id IS NULL`
- `UNIQUE(workspace_id, scope_code) WHERE workspace_id IS NOT NULL`

### knowledge_scope_bindings (NUEVA)

Vincula knowledge_scopes a entidades del sistema. Reemplaza `binding_type`/`binding_id` en knowledge_scopes.

#### Convencion fuerte (v3)

La tabla impone por DB una convencion estricta de nulabilidad segun `binding_type`:

| binding_type | workspace_id | bound_entity_id | bound_entity_id = workspace_id |
|---|---|---|---|
| `internal` | NULL | NULL | N/A |
| `workspace` | NOT NULL | NOT NULL | SI (CHECK obliga) |
| `assistant_instance` | NOT NULL | NOT NULL | NO (es otro ID) |
| `automation_package` | NOT NULL | NOT NULL | NO |
| `package_worker` | NOT NULL | NOT NULL | NO |

**Razon de `bound_entity_id = workspace_id` para `workspace`:** El scope "default del workspace" es un concepto global del workspace. No apunta a otra entidad — el workspace ES la entidad destino. Usar `workspace_id` como `bound_entity_id` evita tablas polimorficas, permite FKs simples desde aplicacion, y el CHECK constraint garantiza consistencia.

#### Schema

```
id                  uuid PK
knowledge_scope_id  FK -> knowledge_scopes(id) ON DELETE CASCADE
workspace_id        FK -> core_workspaces(id) ON DELETE CASCADE (nullable solo para internal)
binding_type        text
bound_entity_id     uuid (nullable solo para internal)
is_default          boolean default false
metadata_jsonb      jsonb default '{}'
created_at_utc      timestamptz
```

#### CHECK constraint (chk_ksb_convention)

```sql
CHECK (
    (binding_type = 'internal' AND workspace_id IS NULL AND bound_entity_id IS NULL)
    OR
    (binding_type = 'workspace'
        AND workspace_id IS NOT NULL
        AND bound_entity_id IS NOT NULL
        AND bound_entity_id = workspace_id)
    OR
    (binding_type IN ('assistant_instance', 'automation_package', 'package_worker')
        AND workspace_id IS NOT NULL
        AND bound_entity_id IS NOT NULL)
)
```

Este CHECK reemplaza y subsume al anterior `chk_knowledge_scope_bindings_type` (que solo validaba el enum).

#### Defaults por tipo

Cada tipo de binding tiene a lo sumo una fila con `is_default = true`, garantizado por indices unicos parciales:

| Indice | Columnas | WHERE |
|--------|----------|-------|
| `uq_ksb_default_internal` | `(binding_type)` | `binding_type = 'internal' AND is_default = true` |
| `uq_ksb_default_workspace` | `(workspace_id)` | `binding_type = 'workspace' AND is_default = true` |
| `uq_ksb_default_per_entity` | `(binding_type, bound_entity_id)` | `binding_type IN ('assistant_instance','automation_package','package_worker') AND is_default = true` |

#### Validado por DB

- Nulabilidad y consistencia de workspace_id / bound_entity_id segun binding_type (CHECK)
- `bound_entity_id = workspace_id` cuando binding_type = 'workspace' (CHECK)
- Un solo default por internal, por workspace, y por entidad (indices unicos parciales)
- binding_type solo puede ser uno de los 5 valores permitidos (subsumido en CHECK)

#### Validado por aplicacion

- `bound_entity_id` existe como FK real en su tabla destino (el CHECK no lo verifica)
- workspace_id del binding matchea workspace_id de la entidad destino (multi-tenant)
- Las entidades destino existen (el binding no tiene FKs a las tablas destino)
- Transiciones de default (cambiar default de una entidad a otra)
- No crear `is_default = true` si ya existe otro default del mismo tipo

#### Indices adicionales (no unicos)

- `idx_ksb_knowledge_scope` por `(knowledge_scope_id)`
- `idx_ksb_workspace` por `(workspace_id)`
- `idx_ksb_binding` por `(binding_type, bound_entity_id)`

### knowledge_documents

Documentos cargados dentro de un scope de conocimiento.

```
id                  uuid PK
knowledge_scope_id  FK -> knowledge_scopes(id) ON DELETE CASCADE
source_type         text
source_uri          text nullable
title               text
content_hash        text not null
metadata_jsonb      jsonb default '{}'
status              text check
created_at_utc      timestamptz
updated_at_utc      timestamptz
```

### knowledge_chunks

Fragmentos de documentos para retrieval.

```
id                      uuid PK
knowledge_document_id   FK -> knowledge_documents(id) ON DELETE CASCADE
chunk_index             integer
title                   text nullable
content                 text
metadata_jsonb          jsonb default '{}'
token_count             integer nullable
embedding_status        text default 'pending'
created_at_utc          timestamptz
updated_at_utc          timestamptz
```

embedding_status: `pending`, `processing`, `completed`, `failed`

## 8. Extension de task_runs

Se agregan columnas a `task_runs` para vincular ejecuciones con packages, workers, areas y permisos:

```sql
ALTER TABLE task_runs
    ADD COLUMN IF NOT EXISTS automation_package_id uuid,
    ADD COLUMN IF NOT EXISTS package_worker_id uuid,
    ADD COLUMN IF NOT EXISTS area_id uuid,
    ADD COLUMN IF NOT EXISTS assigned_user_id uuid,
    ADD COLUMN IF NOT EXISTS required_permission text,
    ADD COLUMN IF NOT EXISTS approval_status text,
    ADD CONSTRAINT chk_task_runs_approval_status
        CHECK (approval_status IS NULL OR approval_status IN (
            'not_required', 'pending', 'approved', 'rejected', 'expired', 'cancelled'
        ));
```

Todas son nullable para no romper registros existentes.
**Valor `bypassed` eliminado** — contradecia reglas de seguridad/HITL.

FKs se agregan con ALTER TABLE por separado.

## 9. Eventos de auditoria

Usar `core_events` para todos los eventos de dominio package/worker/knowledge.

Convencion de payload:

```jsonc
// package event
{
  "entity_type": "automation_package",
  "event_name": "package.created" | "package.status_changed" | "package.feature_updated",
  "payload_jsonb": {
    "package_id": "uuid",
    "previous_status": "active",
    "new_status": "paused",
    "triggered_by": "user_id"
  }
}

// worker event
{
  "entity_type": "package_worker",
  "event_name": "worker.execution_started" | "worker.execution_completed" | "worker.execution_failed",
  "payload_jsonb": {
    "package_worker_id": "uuid",
    "mode": "execution",
    "result": "completed",
    "correlation_id": "uuid"
  }
}

// knowledge event
{
  "entity_type": "knowledge_scope" | "knowledge_document" | "knowledge_chunk",
  "event_name": "knowledge.document_uploaded" | "knowledge.document_removed" | "knowledge.scope_created",
  "payload_jsonb": {
    "knowledge_scope_id": "uuid",
    "document_id": "uuid",
    "source_type": "markdown"
  }
}

// RBAC event
{
  "entity_type": "core_role" | "core_permission_profile" | "core_user_roles",
  "event_name": "rbac.role_created" | "rbac.permission_granted",
  "payload_jsonb": {
    "role_id": "uuid",
    "user_id": "uuid",
    "permission_id": "uuid"
  }
}
```

No se crea tabla de eventos paralela.

## 10. Seeds

Catalogos con datos semilla idempotentes:

- **core_permissions**: 20 permisos iniciales.
- **package_plans**: 4 planes (starter, operational, premium_erp, enterprise_custom).
- **package_features**: 17 features iniciales.
- **package_plan_features**: asignacion de features a cada plan.
- **worker_definitions**: 8 workers base del sistema (alineados con lat.md):
  - `diagnosis_ai_interpreter`, `workflow_classifier`, `approval_worker`,
    `sap_b1_desktop_worker`, `meli_browser_worker`, `document_ocr_worker`,
    `rag_retriever_worker`, `notification_worker`

Usar `ON CONFLICT` para idempotencia.

## Indices propuestos

Se crean indices para las consultas mas frecuentes:
- Por workspace_id en tablas multi-tenant.
- Por tipo de binding en knowledge_scope_bindings.
- Por estado en tablas con filtro de status.
- Indices parciales para columnas con alta densidad de NULL.
- Indices unicos parciales para restricciones UNIQUE con workspace_id nullable.

## Tablas propuestas (resumen)

1. `core_workspace_areas`
2. `core_permissions`
3. `core_roles`
4. `core_role_permissions`
5. `core_permission_profiles`
6. `core_profile_permissions`
7. `core_user_roles`
8. `core_user_profiles`
9. `package_plans`
10. `package_features`
11. `package_plan_features`
12. `workspace_plan_subscriptions`
13. `assistant_instances`
14. `automation_packages`
15. `worker_definitions`
16. `package_workers`
17. `package_worker_configs`
18. `credential_references`
19. `knowledge_scopes`
20. `knowledge_scope_bindings` (NUEVA)
21. `knowledge_documents`
22. `knowledge_chunks`

Total: **22 tablas nuevas** (+1 respecto a v1: knowledge_scope_bindings).

## ALTER TABLE propuestos

- `task_runs`: +6 columnas (automation_package_id, package_worker_id, area_id, assigned_user_id, required_permission, approval_status) + check constraint + 4 FKs.
- `package_workers`: FK a `knowledge_scopes` agregada al final via ALTER.

## Indices unicos parciales (cambios clave respecto a v1)

| Tabla | Unico parcial | Condicion |
|-------|--------------|-----------|
| core_roles | `(role_code)` | `workspace_id IS NULL` |
| core_roles | `(workspace_id, role_code)` | `workspace_id IS NOT NULL` |
| core_permission_profiles | `(profile_code)` | `workspace_id IS NULL` |
| core_permission_profiles | `(workspace_id, profile_code)` | `workspace_id IS NOT NULL` |
| core_user_profiles | `(user_id, profile_id, area_id)` | `area_id IS NOT NULL` |
| core_user_profiles | `(user_id, profile_id)` | `area_id IS NULL` |
| workspace_plan_subscriptions | `(workspace_id)` | `status = 'active'` |
| knowledge_scopes | `(scope_code)` | `workspace_id IS NULL` |
| knowledge_scopes | `(workspace_id, scope_code)` | `workspace_id IS NOT NULL` |
| knowledge_scope_bindings | `(binding_type)` | `binding_type = 'internal' AND is_default = true` |
| knowledge_scope_bindings | `(workspace_id)` | `binding_type = 'workspace' AND is_default = true` |
| knowledge_scope_bindings | `(binding_type, bound_entity_id)` | `binding_type IN ('assistant_instance','automation_package','package_worker') AND is_default = true` |

## Multi-tenant consistency

Riesgo conocido: Las FKs simples no evitan que, por ejemplo, un `package_worker` de workspace A se vincule a un `automation_package` de workspace B.

En 002 no se implementan FKs compuestas con `workspace_id`. Mitigaciones:
- Indices por `workspace_id` en todas las tablas multi-tenant para facilitar auditoria.
- `audit_team360_schema.py` incluye validacion de consistencia multi-tenant.
- La capa de aplicacion (backend Litestar) debe validar consistencia de workspace_id antes de insertar.

## Seguridad en credential_references

- `secret_ref`: unico campo que referencia secretos. No almacenar valores planos.
- `metadata_jsonb`: solo metadatos no sensibles (fecha de rotacion, descripcion, etc.).
- `audit_team360_schema.py` detecta claves sospechosas en `metadata_jsonb` (password, passwd, token, api_key, apikey, secret, private_key, credential).

## Cambios en v3 respecto a v2

1. **knowledge_scope_bindings**: CHECK constraint reemplazado por `chk_ksb_convention` mas fuerte que valida nulabilidad segun tipo, y para `workspace` exige `bound_entity_id = workspace_id`.
2. **Indices unicos parciales**: `uq_ksb_default_internal` cambiado a `WHERE binding_type = 'internal' AND is_default = true`; agregado `uq_ksb_default_workspace` con `UNIQUE(workspace_id)` para workspace; `uq_ksb_default_per_entity` cambiado a `WHERE binding_type IN ('assistant_instance','automation_package','package_worker') AND is_default = true` (mas preciso, evita ambiguedad con NULL).
3. **DO blocks**: filtros `conrelid` agregados en consultas a `pg_constraint` y `table_schema = 'public'` en consultas a `information_schema.columns` para evitar falsos positivos.
4. **audit_team360_schema.py**: nueva seccion 7 para validar `knowledge_scope_bindings`; validacion semantica de predicates de indices parciales via `pg_index`, `pg_get_indexdef()` y `pg_get_expr()`; nuevas claves sospechosas (`passwd`, `apikey`); mensaje final cambiado a "Audit completed for current database state."
5. **Bloqueante resuelto**: ya no es posible insertar defaults ambiguos con `bound_entity_id IS NULL` para tipos no-internal.

## Cambios respecto a v1 del borrador

1. **core_roles**: workspace_id nullable con is_system_role + indices unicos parciales.
2. **core_permission_profiles**: indices unicos parciales para workspace_id nullable.
3. **core_user_profiles**: area_id nullable con indices unicos parciales para permitir mismo perfil en areas distintas.
4. **automation_packages**: package_code scoped a workspace (no global) + FK a package_plans(plan_code).
5. **knowledge_scope_bindings**: nueva tabla, binding movido desde knowledge_scopes.
6. **knowledge_scopes**: eliminados binding_type/binding_id.
7. **assistant_instances**: default_knowledge_scope_id sin FK (evita circular).
8. **package_workers**: agregado package_worker_code + UNIQUE(automation_package_id, package_worker_code).
9. **workspace_plan_subscriptions**: UNIQUE parcial para active only + ended_at_utc en vez de cancelled_at_utc.
10. **approval_status**: eliminado `bypassed`, valores seguros: not_required, pending, approved, rejected, expired, cancelled.
11. **worker_definitions seeds**: nombres alineados con lat.md.
12. **credential_references**: documentacion de seguridad + audit de metadata_jsonb.

## Riesgos

1. **Multi-tenant consistency**: FKs simples no validan workspace_id. Mitigado con indices y validacion en aplicacion.
2. **FK no circular**: `assistant_instances.default_knowledge_scope_id` no tiene FK a `knowledge_scopes`. La integridad se valida en aplicacion.
3. **task_runs ya tiene datos**: columnas nuevas son todas nullable, no rompe filas existentes.
4. **Seeds con datos no sensibles**: solo catalogos de sistema, no datos de clientes.
5. **Compatibilidad con 001**: se usan los mismos patrones (gen_random_uuid, timestamptz, jsonb).
6. **v360 no se toca**: ninguna FK o referencia apunta a tablas de v360.

## Confirmacion

**002 (v3) NO fue aplicada sobre team360.** Este documento y los archivos SQL asociados son borradores revisables que requieren validacion con GPT-5.5 antes de ejecutar.
