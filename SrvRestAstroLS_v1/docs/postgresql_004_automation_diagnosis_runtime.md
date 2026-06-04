# PostgreSQL 004 - Automation Diagnosis Runtime

Estado: **APLICADA sobre team360 el 2026-06-04**

## Objetivo

Persistir en PostgreSQL el runtime inicial del asistente de venta y diagnostico, empezando por `team360_sales_diagnosis` como primera instalacion cliente real del paquete `pkg_sales_diagnosis`.

La migracion no implementa ArangoDB, Milvus, LiteLLM real, endpoints Litestar ni frontend. Deja PostgreSQL como verdad operacional para sesiones, respuestas, leads, eventos y auditoria.

## Archivo

```text
backend/db/migrations/004_team360_automation_diagnosis_runtime.sql
```

## Cambios de schema

### assistant_instances

Se agrega columna estable:

```text
assistant_code text
```

Indice:

```text
uq_assistant_instances_workspace_code
  unique (workspace_id, assistant_code)
  where assistant_code is not null
```

Motivo: resolver `assistant_instance` por codigo estable de producto/configuracion, sin depender de UUID hardcodeado.

### automation_diagnosis_sessions

Tabla de sesiones de diagnostico/venta.

Guarda:

- `public_session_id` generado por el modulo actual;
- FKs a workspace, assistant instance, automation package y knowledge scope;
- codigos estables usados por runtime;
- `organization_code`, `workspace_slug`, `site_channel`, `lead_owner`, `locale`, `market`;
- `visitor_jsonb`, package workers, cost attribution, metadata, resultado y contacto;
- `correlation_id` para eventos/auditoria.

### automation_diagnosis_answers

Tabla de respuestas por step del flujo guiado.

Unique:

```text
(session_id, step_id)
```

### automation_diagnosis_leads

Tabla de lead/ficha comercial derivada del diagnostico.

Guarda clasificacion, modo de automatizacion, paquete recomendado, score, siguiente paso, ficha interna y contacto.

### knowledge_scope_bindings

Se agrega indice unico para idempotencia de bindings por scope/entidad:

```text
uq_ksb_binding_scope_entity
  unique (knowledge_scope_id, binding_type, bound_entity_id)
  where bound_entity_id is not null
```

Esto evita duplicar bindings no-default al reinstalar o re-sincronizar un paquete.

## Seeds

La migracion agrega worker definitions para el paquete de venta/diagnostico:

```text
guided_intake_worker
lead_qualification_worker
knowledge_retrieval_worker
diagnosis_scoring_worker
package_recommendation_worker
proposal_outline_worker
crm_handoff_worker
calendar_handoff_worker
agui_render_worker
```

No guarda credenciales ni secretos.

## Repository

Se agrego:

```text
backend/modules/automation_diagnosis/postgres_repository.py
```

Responsabilidades:

- `upsert_package_installation()` instala/actualiza workspace, knowledge scope, assistant instance, automation package, package workers, configs y bindings;
- `persist_session_snapshot()` persiste sesion, respuestas, lead y eventos en `core_events`;
- todo SQL vive en repository y usa `psycopg 3 async` con parametros nombrados.

## Aplicacion real

Fecha: 2026-06-04.

Resultado:

```text
migration_004_applied=ok
```

Smoke real sobre `team360`:

```text
workspace_id: 90ff667c-b96b-4dce-aa9c-694b3b6d63e7
assistant_instance_id: d53d788b-3ded-4f4d-81dc-011971667f68
automation_package_id: cd0c8a70-8533-41b2-bb12-c9099d0b64c9
knowledge_scope_id: 8b071443-5bd6-4fe4-bbc3-fc2dca179a5b
package_workers: 9
sessions: 1
answers: 10
leads: 1
events: 16
```

## Validacion

```text
python3 -m py_compile ... OK
uv run pytest tests/test_automation_diagnosis.py tests/test_automation_diagnosis_postgres_repository.py -> 13 passed
uv run pytest -> 45 passed
uv run python -m scripts.audit_team360_schema -> 102 checks, 0 failed
```

## Limites

- No hay endpoint Litestar productivo nuevo.
- No hay ArangoDB/Milvus real todavia.
- No hay LiteLLM real en el smoke; se uso `MockAIInterpreter`.
- El repository queda listo para ser llamado desde una capa async/transactional.
