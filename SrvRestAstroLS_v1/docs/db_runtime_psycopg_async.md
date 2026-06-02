# DB Runtime — psycopg 3 async

Fecha: 2026-06-02

Estado: modulo base creado. Sin integracion runtime. Sin DB touch.

## Objetivo

Proveer la capa de acceso runtime a PostgreSQL para Team360 usando `psycopg 3 async` directo, siguiendo la politica documentada en `lat.md/postgres-driver-policy.md`.

Este modulo no es un ORM, no reemplaza migraciones, no toca DB y no implementa logica de negocio.

## Estructura

```
backend/modules/db/
    __init__.py      — export publico
    settings.py      — DatabaseSettings, DSN resolution, sanitize_dsn
    pool.py          — AsyncConnectionPool lifecycle
    transaction.py   — fetch_one, fetch_all, execute, transaction context manager
    errors.py        — DatabaseError, DatabaseConfigurationError, DatabasePoolNotInitializedError, DatabaseExecutionError
```

## Patron de uso

```python
from modules.db import get_database_settings, create_pool, open_pool, close_pool

settings = get_database_settings()
pool = create_pool(settings)
await open_pool(pool)
# ... use pool ...
await close_pool(pool)
```

### Transaction helper

```python
from modules.db import transaction, fetch_one

async with transaction(pool) as conn:
    row = await fetch_one(conn, "SELECT * FROM core_workspaces WHERE id = %(id)s", {"id": workspace_id})
```

## Settings

`get_database_settings()` resuelve el DSN en este orden:

1. `TEAM360_DB_URL`
2. `TEAM360_DB_URL_PSQL`
3. `DB_PG_V360_URL` (reemplazando database name por `team360`)

`DatabaseSettings` es un `dataclass(frozen=True)` que no expone la password en `repr()`.

`sanitize_dsn(dsn)` remueve la password de un DSN para logging seguro.

## Pool lifecycle

- `create_pool(settings)` — crea `AsyncConnectionPool` con `open=False`. No abre conexiones.
- `set_pool(pool)` / `get_pool()` — singleton global. `get_pool()` falla con `DatabasePoolNotInitializedError` si no fue inicializado.
- `open_pool(pool)` — abre conexiones de background.
- `close_pool(pool)` — cierra todas las conexiones.
- `reset_pool_for_tests()` — limpia la referencia global (solo tests).

## Transaction helper

`transaction(pool)` es un context manager async que obtiene una conexion del pool, abre transaccion explicita, commitea al salir y hace rollback ante excepcion.

`fetch_one`, `fetch_all`, `execute` envuelven `psycopg` con manejo de errores tipado (`DatabaseExecutionError`).

## Repositories futuros

Los repositories de negocio (WorkspaceConsoleRepository, PermissionConsoleRepository, etc.) recibiran `AsyncConnection` como primer parametro, nunca manejaran pool ni conexiones, y devolveran TypedDicts/dataclasses segun la politica Pydantic Boundary.

## Integracion con Litestar (futuro)

En el lifecycle de Litestar:

1. **Startup:** `get_database_settings()` → `create_pool()` → `open_pool()` → `set_pool()`
2. **Durante request:** obtener conexion via `pool.connection()` o `transaction(pool)` en handlers/dependencies.
3. **Shutdown:** `close_pool(get_pool())` → `reset_pool_for_tests()`

No se implementa todavia porque Litestar no esta integrado al runtime activo.

## Lo que queda fuera

- ORM (SQLAlchemy, SQLModel)
- asyncpg
- Pydantic en core
- Conexion a DB (este modulo no se conecta automaticamente)
- Migraciones y auditorias de schema
- Logica de negocio
- Repositories de dominio
