# PostgreSQL Live Team360 Setup

Fecha: 2026-05-28

## Objetivo

Inicializar la base PostgreSQL viva de Team360 como proyecto propio, sin copiar el schema de `v360`.

La fuente de verdad para el siguiente diseno queda formada por:

- migraciones versionadas del repo;
- documentacion tecnica;
- DB viva PostgreSQL `team360`;
- patrones heredados de `v360` solo como referencia operativa.

## Decision de DB

DB elegida: `team360`.

Motivo:

- el usuario pidio usar explicitamente `team360`;
- `team360_dev` habia sido creada durante la preparacion inicial y fue eliminada;
- `v360` se mantiene intacta como referencia heredada;
- `litellm` se mantiene intacta como DB separada del proxy LiteLLM.

Estado del servidor:

- PostgreSQL local activo en puerto `5432`;
- bases post-operacion: `litellm`, `postgres`, `team360`, `v360`;
- no se usa ni queda creada `team360_dev`.

## Conexion Segura

No se documentan passwords, tokens ni DSN completos.

La conexion se resolvio desde la configuracion existente del entorno, usando `DB_PG_V360_URL` solo como DSN de referencia del servidor PostgreSQL local y cambiando el nombre de base a `team360` para aplicar la migracion.

Formato sanitizado:

```text
postgresql://***:***@<redacted>:5432/team360
```

Para uso futuro del backend, conviene configurar explicitamente:

```bash
export TEAM360_DB_NAME="team360"
export TEAM360_DB_URL="postgresql+psycopg://***:***@<host>:5432/team360"
export TEAM360_DB_URL_PSQL="postgresql://***:***@<host>:5432/team360"
```

## Operaciones Ejecutadas

No se ejecutaron cambios destructivos sobre `v360`, `litellm` ni `postgres`.

Operaciones realizadas:

```sql
-- sobre la conexion administrativa al servidor local
drop database team360_dev;
create database team360;
```

Luego se aplico:

```text
SrvRestAstroLS_v1/backend/db/migrations/001_team360_core_schema.sql
```

Comando equivalente sanitizado:

```bash
psql "postgresql://***:***@<host>:5432/team360" \
  -v ON_ERROR_STOP=1 \
  -f SrvRestAstroLS_v1/backend/db/migrations/001_team360_core_schema.sql
```

La ejecucion real se hizo con `psycopg` desde el entorno del backend para evitar exponer DSN.

## Resultado De Migracion 001

Resultado: aplicada correctamente sobre `team360`.

La migracion:

- instala `pgcrypto`;
- usa `gen_random_uuid()`;
- no usa `uuidv7()`;
- no instala `vector/pgvector`;
- no crea datos semilla.

Extensiones en `team360`:

- `pgcrypto 1.4`;
- `plpgsql 1.0`.

## Tablas Creadas

Core:

- `core_workspaces`
- `core_users`
- `core_events`

Comunicacion y WhatsApp:

- `communication_providers`
- `provider_credentials`
- `communication_channels`
- `whatsapp_numbers`
- `webhook_bindings`
- `channel_routing_rules`
- `whatsapp_number_migration_history`

Tasks y runners:

- `local_runners`
- `scheduled_tasks`
- `task_runs`
- `runner_heartbeats`

Conversaciones:

- `message_threads`
- `message_events`

LLM:

- `llm_providers`
- `llm_credentials`
- `llm_model_profiles`
- `llm_fallback_policy`
- `workspace_llm_settings`
- `automation_llm_policy`
- `llm_cost_estimates`
- `llm_usage_logs`

## Columnas Principales Por Tabla

- `core_workspaces`: `id`, `slug`, `display_name`, `timezone`, `status`, `metadata_jsonb`, timestamps.
- `core_users`: `id`, `workspace_id`, `email`, `display_name`, `role`, `status`, `metadata_jsonb`, timestamps.
- `core_events`: `workspace_id`, `actor_user_id`, `event_name`, `entity_type`, `entity_id`, `correlation_id`, `payload_jsonb`, timestamps.
- `communication_providers`: `code`, `display_name`, `provider_kind`, `status`, `capabilities_jsonb`, `metadata_jsonb`.
- `provider_credentials`: `workspace_id`, `provider_id`, `credential_scope`, `environment`, `secret_ref`, `public_config_jsonb`, `status`.
- `communication_channels`: `workspace_id`, `provider_id`, `channel_type`, `channel_alias`, `department`, `display_name`, `current_whatsapp_number_id`.
- `whatsapp_numbers`: `workspace_id`, `provider_id`, `channel_id`, `credential_id`, `phone_e164`, provider ids, statuses.
- `webhook_bindings`: `workspace_id`, `provider_id`, `channel_id`, `whatsapp_number_id`, `webhook_url`, secret refs, status.
- `channel_routing_rules`: `workspace_id`, `channel_id`, `rule_type`, `match_value`, `priority`, status, metadata.
- `local_runners`: `workspace_id`, `runner_name`, `runner_key_hash`, `install_fingerprint`, status, capabilities.
- `scheduled_tasks`: `workspace_id`, `task_key`, `display_name`, schedule fields, target channel, payload.
- `task_runs`: `workspace_id`, `scheduled_task_id`, `runner_id`, status, lease, attempts, correlation, input/result/error JSON.
- `runner_heartbeats`: `workspace_id`, `runner_id`, `status`, `observed_at_utc`, `metrics_jsonb`.
- `message_threads`: `workspace_id`, `channel_id`, `current_whatsapp_number_id`, `contact_identity`, status, metadata.
- `message_events`: `workspace_id`, thread/channel/provider/task refs, direction, event type, status, payload, correlation.
- `llm_providers`: `code`, `display_name`, `base_url`, `auth_type`, status, capabilities.
- `llm_credentials`: `workspace_id`, `provider_id`, `credential_scope`, `environment`, `secret_ref`, status.
- `llm_model_profiles`: `provider_id`, `model_id`, display/capabilities/cost/context/status fields.
- `llm_fallback_policy`: `workspace_id`, `name`, ordered profiles, error codes, retry/cooldown config.
- `workspace_llm_settings`: `workspace_id`, default model, fallback policy, key scope preference, budgets, safety policy.
- `automation_llm_policy`: `workspace_id`, `automation_key`, model/fallback refs, credential scope, token/temp/timeout config.
- `llm_cost_estimates`: `provider_id`, `model_id`, costs, currency, effective dates.
- `llm_usage_logs`: `workspace_id`, `automation_key`, task/workflow refs, provider/model refs, tokens, cost, latency, status, correlation.

## Indices Y Constraints

Audit post-001:

- tablas versionadas esperadas: 24;
- tablas creadas en DB viva: 24;
- indices versionados esperados: 51;
- indices versionados presentes: 51;
- primary keys: 24;
- foreign keys: 58;
- unique constraints: 9;
- check constraints detectadas: 237.

No faltan indices versionados.

Existen ademas indices/constraints creados automaticamente por primary keys y unique constraints.

## Conteo De Filas

Todas las tablas creadas por `001` quedaron con `0` filas.

No se cargaron seeds ni datos reales.

## Diferencias Repo Vs DB Viva

Comparacion contra `001_team360_core_schema.sql`:

- tablas en repo pero no en DB: ninguna;
- tablas en DB pero no en repo: ninguna;
- indices versionados faltantes: ninguno;
- extensiones versionadas faltantes: ninguna;
- `plpgsql` aparece como extension viva adicional normal de PostgreSQL.

Conclusion: `001` quedo aplicada completa sobre `team360`.

## Relacion Con v360

`v360` no fue modificada.

Se mantiene solo como referencia de patrones:

- `events` inspira `core_events`;
- `conversations/messages` inspira `message_threads/message_events`;
- `tickets` inspira futuros task dashboards;
- `visit_followup_config` inspira `package_worker_config`;
- `visit_followup_cycle` inspira `task_runs` o futuros worker jobs;
- `jsonb`, `correlation_id` y pgvector son patrones utiles.

No se copiaron tablas de dominio inmobiliario ni enums cerrados.

## Resultado De Migracion 002

Fecha de aplicacion: 2026-05-29.

Resultado: aplicada correctamente sobre `team360` despues de la migracion 001.

La migracion 002 agrego el modelo inicial para:

- RBAC: areas, permisos, roles, perfiles y asignaciones;
- planes, features y limites;
- subscriptions de workspace con historial;
- assistant instances;
- automation packages;
- worker definitions, package workers y configs;
- credential references sin secretos planos;
- knowledge scopes, bindings, documents y chunks;
- extension nullable de `task_runs` para packages/workers/areas/aprobacion.

Auditoria post-002:

```bash
cd SrvRestAstroLS_v1/backend
uv run python -m backend.scripts.audit_team360_schema
```

Resultado observado:

- checks pasados: 74;
- checks fallidos: 0;
- tablas esperadas 001+002: 46/46;
- FKs esperadas post-002: 5/5;
- seeds cargados: 20 permisos, 4 planes, 17 features, 49 asignaciones plan-feature y 8 worker definitions;
- sin datos reales de clientes;
- tablas operativas de 002 en 0 filas.

Siguiente fase recomendada: disenar `003_team360_pgvector_knowledge_embeddings.sql` segun `lat.md/postgres-ai-persistence.md`.

## Roadmap Posterior A 002

Despues de aplicar y auditar la migracion 002, las siguientes fases de persistencia AI deben mantenerse separadas del modelo core:

1. `003_team360_pgvector_knowledge_embeddings.sql`
   - incorporar pgvector/`vector` solo cuando se disene el almacenamiento de embeddings;
   - mantener `knowledge_scopes`, `knowledge_documents` y `knowledge_chunks` como modelo de dominio;
   - decidir si embeddings viven en `public` o en un schema dedicado futuro.

2. `004_team360_langgraph_checkpointing.sql`
   - incorporar LangGraph PostgresSaver en schema separado, sugerido `langgraph`;
   - vincular con Team360 por referencia (`task_runs.langgraph_thread_id`, `task_runs.langgraph_checkpoint_ns` o tabla futura `task_run_langgraph_refs`);
   - no reemplazar `task_runs` ni `core_events`.

Antes de usar `pg_checkpointer`, verificar disponibilidad real:

```sql
SELECT name, default_version, installed_version
FROM pg_available_extensions
WHERE name ILIKE '%checkpoint%';

SELECT *
FROM pg_available_extensions
WHERE name = 'pg_checkpointer';
```

No depender de `pg_checkpointer` hasta confirmar existencia y utilidad.

## Proximos Pasos Recomendados

No disenar ni aplicar `002` hasta usar esta DB viva como base del siguiente inventario.

Proxima fase recomendada:

- seed minimo sin secretos para `team360`;
- RBAC: areas, roles, perfiles y permisos;
- planes/features;
- `automation_packages`;
- `worker_definitions`;
- `package_workers`;
- `package_worker_configs`;
- `credential_references`;
- `knowledge_scopes`;
- `knowledge_documents`;
- `knowledge_chunks`;
- dashboards/task views;
- decidir si `uuidv7()` reemplaza `gen_random_uuid()` en migraciones nuevas, sin reescribir `001`.
