# Team360 - PostgreSQL local de desarrollo

## 1. Decision tecnica

### Observado

- `backend/db/README.md` indica que el runtime principal todavia no depende de DB propia.
- `backend/db/team360_pgvector_catalog.sql` existe, pero esta marcado como futuro opcional y no integrado al runtime actual.
- `backend/globalVar.py` ya reconoce `TEAM360_DB_URL`, `TEAM360_DB_NAME` y helpers para DSN compatible con `psql`, pero bajo nombres `FUTURE_OPTIONAL_*`.
- `backend/pyproject.toml` ya incluye `psycopg[binary]` y `psycopg-pool`, por lo que no hace falta agregar dependencias para una primera validacion local.

### Propuesto

Usar PostgreSQL local en Docker para desarrollo, con una base separada `team360_dev` y credenciales de desarrollo no reales. La primera migration queda en:

```text
backend/db/migrations/001_team360_core_schema.sql
```

La migration inicial crea tablas conceptuales para workspaces, canales WhatsApp, credenciales por provider, webhooks, conversaciones, eventos, providers LLM, politicas LLM, tareas scheduladas y local runners.

## 2. Docker recomendado

Comando recomendado:

```bash
docker run --name team360-postgres-dev \
  -e POSTGRES_DB=team360_dev \
  -e POSTGRES_USER=team360_dev \
  -e POSTGRES_PASSWORD=team360_dev_password \
  -p 54329:5432 \
  -v team360_pgdata:/var/lib/postgresql/data \
  -d postgres:16
```

Notas:

- El puerto local sugerido es `54329` para evitar conflicto con PostgreSQL local en `5432`.
- Usuario/password son solo de desarrollo local.
- No usar estas credenciales en staging ni produccion.

## 3. Variables de entorno sugeridas

Para Python/psycopg:

```bash
export TEAM360_DB_NAME="team360_dev"
export TEAM360_DB_URL="postgresql+psycopg://team360_dev:team360_dev_password@localhost:54329/team360_dev"
```

Para `psql`:

```bash
export TEAM360_DB_URL_PSQL="postgresql://team360_dev:team360_dev_password@localhost:54329/team360_dev"
```

Decision:

- `TEAM360_DB_URL` queda como DSN principal del backend.
- `TEAM360_DB_URL_PSQL` es solo comodidad para CLI.
- Las credenciales reales de providers, WhatsApp, LLM o bancos no deben ir en estas variables.

## 4. Como crear DB

Si se usa el comando `docker run` anterior, la DB `team360_dev` se crea automaticamente al iniciar el contenedor por primera vez.

Validar contenedor:

```bash
docker ps --filter "name=team360-postgres-dev"
```

Validar DB:

```bash
docker exec -it team360-postgres-dev psql -U team360_dev -d team360_dev -c "select current_database(), current_user;"
```

## 5. Como probar conexion

Con `psql`:

```bash
psql "$TEAM360_DB_URL_PSQL" -c "select 1 as ok;"
```

Con Python desde `backend/`:

```bash
cd backend
uv run python -c "import os, psycopg; dsn=os.environ['TEAM360_DB_URL'].replace('postgresql+psycopg://','postgresql://'); conn=psycopg.connect(dsn); print(conn.execute('select 1').fetchone()[0]); conn.close()"
```

Resultado esperado:

```text
1
```

## 6. Como aplicar migrations

Desde la raiz `SrvRestAstroLS_v1`:

```bash
psql "$TEAM360_DB_URL_PSQL" -v ON_ERROR_STOP=1 -f backend/db/migrations/001_team360_core_schema.sql
```

Validar tablas:

```bash
psql "$TEAM360_DB_URL_PSQL" -c "\\dt"
```

Validar tablas principales:

```bash
psql "$TEAM360_DB_URL_PSQL" -c "select table_name from information_schema.tables where table_schema='public' and table_name like 'core_%' order by table_name;"
```

## 7. Como resetear DB de desarrollo

Opcion A: reset completo de contenedor y volumen local.

```bash
docker rm -f team360-postgres-dev
docker volume rm team360_pgdata
```

Luego volver a ejecutar el `docker run` recomendado y reaplicar migrations.

Opcion B: reset de schema `public` dentro de la DB local.

```bash
psql "$TEAM360_DB_URL_PSQL" -v ON_ERROR_STOP=1 -c "drop schema public cascade; create schema public;"
psql "$TEAM360_DB_URL_PSQL" -v ON_ERROR_STOP=1 -f backend/db/migrations/001_team360_core_schema.sql
```

Usar estas opciones solo en desarrollo. No ejecutar resets contra staging ni produccion.

## 8. Convenciones iniciales

- Todos los timestamps de negocio usan `timestamptz`.
- Los nombres de timestamp terminan en `_utc` cuando representan instantes persistidos.
- Los estados usan `text` con `check constraints` en esta primera fase para mantener flexibilidad.
- Las credenciales se representan con `secret_ref` o metadata publica; no se guardan secretos planos.
- Las tablas multi-tenant incluyen `workspace_id` cuando corresponde.
- Las tablas de eventos incluyen `correlation_id` para unir AG-UI/SSE, task runs, webhooks, LLM y logs.

## 9. Proxima fase

- Definir un runner de migrations formal: Alembic, yoyo, sql directo controlado o herramienta propia simple.
- Crear repositorios Python despues de estabilizar el schema.
- Agregar seed de development sin secretos reales.
- Integrar `TEAM360_DB_URL` como configuracion runtime no opcional cuando el backend Litestar productivo exista.
