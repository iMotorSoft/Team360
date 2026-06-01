# Postgres AI Persistence

Team360 uses PostgreSQL 18 as the single transactional persistence core for platform state, operational truth and future AI persistence layers.

This decision does not apply migrations by itself. It defines the target architecture for the DB roadmap after migration 002.

## Core Decision

PostgreSQL is the source of truth for Team360.

It stores:

- operational data;
- workspaces;
- users;
- roles and permission assignments;
- automation packages;
- package workers;
- task runs;
- events;
- audit trails;
- knowledge scopes;
- knowledge documents and chunks;
- embeddings through pgvector;
- future LangGraph checkpoints through PostgresSaver.

Rule:

```text
Postgres records truth.
Team360 owns the domain model.
AI and workflow engines are subordinate runtime layers.
```

This extends [[team360-platform]] and does not change the rule that Team360 must not copy `v360`; it can only reuse patterns.

## Separation Of Concerns

The Team360 core model lives in Team360-owned tables, currently in `public`:

- `core_workspaces`;
- `core_users`;
- `core_events`;
- `task_runs`;
- `automation_packages`;
- `package_workers`;
- `knowledge_scopes`;
- `knowledge_documents`;
- `knowledge_chunks`.

These tables are the operational and audit model. They must remain understandable without depending on LangGraph internals, vector index internals or provider-specific AI state.

## pgvector Phase

pgvector is introduced by the dedicated embeddings migration when embeddings are needed by the production model.

Implemented phase:

```text
003_team360_pgvector_knowledge_embeddings.sql
```

Expected scope:

- install/validate `vector` extension;
- add dedicated embedding rows for knowledge chunks;
- preserve `knowledge_scopes`, `knowledge_documents` and `knowledge_chunks` as the domain model;
- keep retrieval mode per `knowledge_scope`, as defined in [[knowledge-rag-graphrag]].

Migration 003 materializes embeddings in `public.knowledge_chunk_embeddings`. It prepares persistence and retrieval indexes only; it does not generate embeddings or implement GraphRAG.

## LangGraph Phase

LangGraph PostgresSaver must be introduced only in a later migration, separated from the Team360 core model.

Suggested phase:

```text
004_team360_langgraph_checkpointing.sql
```

Recommended schema:

```text
langgraph
```

LangGraph checkpoint tables are internal workflow state. They must not replace Team360 operational tables.

## Runtime Truth Boundaries

LangGraph PostgresSaver does not replace `task_runs` or `core_events`.

```text
task_runs = Team360 operational truth visible to product and support
core_events = audit trail and traceability
LangGraph checkpoints = internal resumable state for workflows/agents
```

Team360 should link to LangGraph by reference, not by mixing models.

Future options:

```text
task_runs.langgraph_thread_id nullable
task_runs.langgraph_checkpoint_ns nullable
```

or a dedicated table:

```text
task_run_langgraph_refs
```

The final shape belongs to migration 004.

## Schema Model

Recommended schema split:

```text
public      -> Team360 core tables and migrations 001/002/003
langgraph   -> LangGraph PostgresSaver checkpoint tables
public or future embeddings schema -> pgvector-backed embedding storage
```

Team360 core tables must stay queryable and auditable without joining against `langgraph` internals.

## pg_checkpointer Precaution

Do not assume `pg_checkpointer` exists as a standard PostgreSQL extension.

Before any design depends on it, verify availability in the target PostgreSQL 18 environment:

```sql
SELECT name, default_version, installed_version
FROM pg_available_extensions
WHERE name ILIKE '%checkpoint%';

SELECT *
FROM pg_available_extensions
WHERE name = 'pg_checkpointer';
```

Do not depend on `pg_checkpointer` until availability and usefulness are confirmed.

Safe decision:

- PostgreSQL 18 as the transactional core;
- pgvector for embeddings through migration 003;
- LangGraph PostgresSaver for checkpoints in a future migration;
- `pg_checkpointer` only if verified and justified.

## Migration Order

Current known sequence:

```text
001_team360_core_schema.sql                      -> applied to team360
002_team360_rbac_packages_workers_knowledge.sql  -> applied to team360
003_team360_pgvector_knowledge_embeddings.sql    -> applied to team360
004_team360_langgraph_checkpointing.sql          -> future
```

Migration 002 did not include pgvector or LangGraph. Migration 003 covers pgvector embeddings only. Migration 004 remains the boundary for LangGraph checkpointing.
