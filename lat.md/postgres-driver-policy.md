# PostgreSQL Driver Policy

Team360 uses `psycopg 3 async` as the standard runtime access layer for PostgreSQL.

This decision is stable across all core modules, repositories and runtime paths. It does not depend on a specific ORM, query builder or alternative driver.

## Decision

```
Schema:    explicit SQL migrations (001/002/003)
Runtime:   psycopg 3 async direct
Pool:      psycopg_pool.AsyncConnectionPool
Queries:   explicit parameterised SQL
Repos:     disciplined repository layer returning Pydantic models or typed dicts
ORM:       not the source of truth; not the core access layer
```

## Scope

This policy applies to:

- all runtime DB access from backend Python code;
- all repository implementations under `backend/modules/*/repository.py` or equivalent;
- all service-layer transaction boundaries;
- all future agent/workflow persistence (outside LangGraph PostgresSaver internal schema);
- all pgvector query paths (retrieval, similarity search).

This policy does NOT apply to:

- LangGraph PostgresSaver internal tables (`langgraph` schema) — those use LangGraph's own `AsyncPostgresSaver` which wraps `psycopg` internally;
- migration execution scripts — those can use `psycopg` synchronously or direct `psql`;
- administrative scripts outside the runtime path.

## Why Not SQLAlchemy / SQLModel

Team360 uses PostgreSQL features that ORMs abstract poorly or require workarounds for:

- partial unique indexes with composite WHERE predicates;
- jsonb with check constraints for structural validation;
- HNSW vector indexes with cosine operators;
- CHECK constraints that express domain invariants (e.g. `chk_ksb_convention`);
- explicit transaction control for multi-step agent workflows;
- direct `pg_get_expr`, `pg_get_constraintdef` and audit queries;
- future LangGraph PostgresSaver coexistence in a separate schema.

SQLAlchemy/SQLModel add a mental indirection layer that fights these features. The cost (translation bugs, opaque generated SQL, migration drift) exceeds the benefit for a project of this profile.

SQLAlchemy/SQLModel may be evaluated ONLY for:

- administrative CRUD UIs with no complex constraints;
- internal tools outside the runtime path;
- read-only reporting dashboards.

Even in those cases, the source of truth remains the explicit SQL migration and the `psycopg` repository layer. An ORM must never be the authoritative schema definition.

## Why Not asyncpg

`asyncpg` is a high-performance async PostgreSQL driver with its own type system and connection pool.

Team360 uses `psycopg 3 async` as the default and primary driver because:

- it is the official, actively maintained PostgreSQL adapter for Python;
- its async API (`AsyncConnection`, `AsyncCursor`) is mature and matches `psycopg_pool`;
- it uses `dict_row` for native dict returns, removing the need for a secondary row factory;
- it has first-class support for `jsonb`, `uuid`, `timestamptz`, `array`, and custom types;
- it is the dependency already declared in `pyproject.toml` (`psycopg[binary]>=3.2.0`);
- the LangGraph PostgresSaver (`langgraph-checkpoint-postgres`) uses `psycopg` as its underlying driver;
- `asyncpg` would add a second async driver with a different type system, different pool API and different connection lifecycle, increasing cognitive load and maintenance surface.

`asyncpg` may be evaluated ONLY for:

- specialised high-throughput worker paths where profiling demonstrates a concrete bottleneck proven to be driver-related (not query, index or I/O bound);
- dedicated worker processes isolated from the main runtime.

Until such a metric exists, the default is `psycopg 3 async`.

## Relationship with pgvector

pgvector queries (cosine similarity, HNSW index scans) are executed through the same `psycopg 3 async` layer:

```python
await conn.execute(
    """
    SELECT kce.chunk_id, kce.embedding <=> $1::vector AS distance
    FROM knowledge_chunk_embeddings kce
    WHERE kce.embedding_status = 'ready'
      AND kce.model_id = $2
    ORDER BY distance
    LIMIT $3
    """,
    (query_embedding, model_id, top_k)
)
```

The `vector` type is passed and received as native PostgreSQL text representation; `psycopg` handles it transparently via its generic type adapter. No special ORM mapping is needed.

## Relationship with LangGraph PostgresSaver

LangGraph PostgresSaver ships with its own connection management based on `psycopg`. It uses an internal `AsyncPostgresSaver` that manages checkpoints in the `langgraph` schema.

The policy is:

- LangGraph stores its internal state (checkpoints, writes, blobs) in `langgraph.*` tables, managed by `AsyncPostgresSaver`.
- Team360 repository layer does NOT query `langgraph.*` tables directly.
- Team360 links to LangGraph runs by reference columns on `task_runs` (e.g. `task_runs.langgraph_thread_id`), managed by the Team360 repository layer via `psycopg 3 async`.
- The `langgraph` schema uses the same PostgreSQL cluster but is logically separated.

This means two `psycopg` connection pools coexist in the same process:

```
Team360 pool  -> public.* tables (psycopg_pool.AsyncConnectionPool)
LangGraph     -> langgraph.* tables (internal pool managed by AsyncPostgresSaver)
```

Both use the same driver. No second driver is introduced.

## Recommended Module Structure

```
backend/modules/db/
    __init__.py
    settings.py         — DB URL resolution, connection parameters
    pool.py             — AsyncConnectionPool singleton, acquire/release helpers
    transaction.py      — unit-of-work helper for explicit transaction boundaries
    errors.py           — domain-level DB exceptions (not found, constraint violation, etc.)

backend/modules/knowledge/
    repository.py       — psycopg async queries for knowledge_scopes, documents, chunks, embeddings
    ingestion.py        — ingestion pipeline (chunk + embed + insert)
    retrieval.py        — similarity search and RAG retrieval
    embeddings.py       — embedding generation (OpenAI, LiteLLM, local)
```

## Repository Pattern Rules

1. Every repository is a class or set of functions that receive an `AsyncConnection` as first parameter.
2. Repositories never manage connections or transactions — they receive them from the caller.
3. Repositories return Pydantic models or typed dicts, never raw cursor rows.
4. Repository methods are named by operation: `get_by_id`, `find_by_workspace`, `insert`, `update_status`, `delete`.
5. SQL lives inside repository methods, not in endpoints or service methods.
6. Parameterised queries use `$1`, `$2`, ... (PostgreSQL native positional) or `%(name)s` (psycopg named).

## Example: Pool

```python
from psycopg_pool import AsyncConnectionPool
from backend.modules.db.settings import get_db_url

pool: AsyncConnectionPool | None = None

async def init_pool() -> AsyncConnectionPool:
    global pool
    if pool is None:
        pool = AsyncConnectionPool(
            conninfo=get_db_url(),
            min_size=2,
            max_size=10,
            open=True,
            configure=lambda conn: conn,
        )
    return pool

async def get_connection():
    p = await init_pool()
    return p.connection()
```

## Example: Repository

```python
from psycopg import AsyncConnection
from psycopg.rows import dict_row
from pydantic import BaseModel

class Workspace(BaseModel):
    id: str
    slug: str
    display_name: str
    status: str

async def get_workspace_by_slug(
    conn: AsyncConnection, slug: str
) -> Workspace | None:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT id, slug, display_name, status "
            "FROM core_workspaces WHERE slug = $1",
            (slug,),
        )
        row = await cur.fetchone()
        if row is None:
            return None
        return Workspace(**row)
```

## Example: Unit of Work

```python
@contextlib.asynccontextmanager
async def transaction(conn: AsyncConnection):
    async with conn.transaction():
        yield
```

Service layer:

```python
async def activate_workspace(workspace_id: str) -> None:
    conn = await get_connection()
    async with transaction(conn):
        repo = WorkspaceRepository()
        await repo.update_status(conn, workspace_id, "active")
        event_repo = EventRepository()
        await event_repo.record(
            conn, workspace_id, "workspace.activated"
        )
```

## What Is Discouraged

- Writing raw SQL strings inside endpoint handlers or route functions.
- Using `connection.execute()` with string interpolation or f-strings for parameter values.
- Importing `psycopg` or `psycopg_pool` outside the `db/` module or repository layer.
- Adding SQLAlchemy, SQLModel or asyncpg as project dependencies without an explicit architectural review.
- Creating ORM models that duplicate or replace the authoritative schema defined in SQL migrations.
- Mixing LangGraph `AsyncPostgresSaver` connection pool with the Team360 repository pool.

## What Is Prohibited

- Storing database credentials, connection strings or secrets in source code.
- Using ORM-managed migrations (Alembic, SQLAlchemy Migrate) as the primary migration tool. All schema changes must be explicit `.sql` files in `backend/db/migrations/`.
- Bypassing the repository layer to write SQL directly in endpoints, except in well-justified, reviewed exceptions.

## Summary

| Aspect | Decision |
|--------|----------|
| Runtime driver | `psycopg 3 async` |
| Connection pool | `psycopg_pool.AsyncConnectionPool` |
| Row factory | `dict_row` |
| Query style | Explicit parameterised SQL |
| Repository pattern | Class with `AsyncConnection` as parameter |
| Return type | Pydantic models or typed dicts |
| ORM (SQLAlchemy/SQLModel) | Not for core; only administrative tools if justified |
| asyncpg | Not for core; only high-throughput workers if metrics justify |
| pgvector | Same `psycopg` layer, no special adapter needed |
| LangGraph PostgresSaver | Separate `langgraph` schema, same cluster, same driver |
| Schema truth | SQL migrations only |
