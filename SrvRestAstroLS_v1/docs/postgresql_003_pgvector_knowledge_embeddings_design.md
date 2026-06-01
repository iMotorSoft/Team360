# Migracion 003 - pgvector Knowledge Embeddings

Fecha: 2026-05-29
Estado: **APLICADA sobre team360 el 2026-05-29**

## Objetivo

Preparar persistencia PostgreSQL para embeddings de `knowledge_chunks` usando pgvector.

La migracion no genera embeddings, no llama a proveedores LLM, no crea GraphRAG completo y no incorpora LangGraph. Solo deja el soporte transaccional e indexable para que una fase posterior cargue y consulte embeddings.

## Alcance

La 003 agrega:

- extension `vector`;
- catalogo `knowledge_embedding_models`;
- tabla `knowledge_chunk_embeddings`;
- indices B-tree para filtros operativos;
- indice HNSW cosine para retrieval vectorial;
- vista `knowledge_ready_chunks` sin exponer la columna vector.

Quedan fuera:

- generacion automatica de embeddings;
- workers externos;
- colas;
- GraphRAG completo;
- `knowledge_entities`, `knowledge_relations` o `knowledge_graphs`;
- LangGraph PostgresSaver;
- secretos, API keys o credenciales de proveedor.

## Por Que Tabla Separada

Los embeddings viven en `knowledge_chunk_embeddings`, no directamente en `knowledge_chunks`.

Motivos:

- permite multiples embeddings por chunk en el futuro;
- soporta re-embedding por modelo;
- evita atar `knowledge_chunks` a una unica dimension;
- separa estado de contenido y estado de embedding;
- permite mantener `knowledge_chunks` como dominio estable de conocimiento.

`knowledge_chunks` sigue siendo la fuente del texto chunked. `knowledge_chunk_embeddings` guarda representaciones vectoriales derivadas.

## Modelo Inicial

Modelo semilla:

```text
provider_code: openai
model_code: text-embedding-3-small
model_alias: default_1536
dimension: 1536
distance_metric: cosine
status: active
```

Este seed es solo catalogo tecnico. No implica llamadas a OpenAI ni guarda API keys.

La tabla de embeddings usa:

```sql
embedding vector(1536)
```

Si en el futuro se requiere otra dimension, debe disenarse una migracion explicita en lugar de mezclar dimensiones de forma ambigua.

## Estado De Embedding

`knowledge_chunk_embeddings.embedding_status` acepta:

```text
pending | ready | failed | stale
```

Regla:

```text
ready requiere embedding no NULL.
pending, failed y stale pueden no tener embedding.
```

La unicidad `(knowledge_chunk_id, embedding_model_id)` evita duplicados para el mismo chunk/modelo. Para re-embedding se actualiza la fila existente o se agrega una migracion futura para historico de versiones si aparece esa necesidad.

## Retrieval

La vista `knowledge_ready_chunks` expone chunks listos para retrieval:

- `knowledge_scope_id`;
- `knowledge_document_id`;
- `knowledge_chunk_id`;
- `chunk_index`;
- `title`;
- `content`;
- `embedding_model_id`;
- `model_alias`;
- `embedding_status`;
- `embedded_at_utc`.

La vista no incluye la columna `embedding`; las consultas vectoriales deben ir contra `knowledge_chunk_embeddings` cuando necesiten calcular distancia.

## Indices

Indices operativos:

- `idx_kce_knowledge_scope`;
- `idx_kce_knowledge_chunk`;
- `idx_kce_embedding_model`;
- `idx_kce_embedding_status`;
- `idx_kce_ready_scope_model`.

Indice vectorial:

```sql
idx_kce_embedding_hnsw_cosine
```

Usa HNSW con `vector_cosine_ops` y predicate `embedding_status = 'ready'`.

## Aplicacion

Comando recomendado si `psql` esta disponible:

```bash
cd /media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/SrvRestAstroLS_v1
psql "$TEAM360_DB_URL_PSQL" -v ON_ERROR_STOP=1 -1 -f backend/db/migrations/003_team360_pgvector_knowledge_embeddings.sql
```

En el entorno local actual se puede usar `psycopg` desde `uv` si `psql` no esta disponible, con DSN sanitizado y transaccion explicita.

## Resultado Observado

Aplicacion 2026-05-29 sobre DB viva `team360`:

- extension `vector` instalada: `0.8.2`;
- tablas base esperadas 001+002+003: 48/48;
- view `knowledge_ready_chunks`: OK;
- checks de auditoria: 88 pasados, 0 fallidos;
- seed `knowledge_embedding_models.default_1536`: OK;
- indice `idx_kce_embedding_hnsw_cosine`: OK HNSW cosine;
- no hay embeddings `ready` con vector NULL;
- no hay embeddings reales cargados todavia.

## Auditoria

Comando:

```bash
cd /media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/SrvRestAstroLS_v1
uv run --project backend python -m backend.scripts.audit_team360_schema
```

El auditor valida:

- extension `vector` instalada;
- tablas `knowledge_embedding_models` y `knowledge_chunk_embeddings`;
- vista `knowledge_ready_chunks`;
- columnas clave;
- constraints;
- seed `default_1536`;
- indices B-tree y HNSW;
- ausencia de embeddings `ready` con vector NULL;
- ausencia de status invalidos;
- ausencia de duplicados chunk/modelo;
- consistencia basica entre `knowledge_scope_id` del embedding y el documento del chunk.

El auditor no imprime vectores completos.

## Relacion Con 004 LangGraph

La 003 no crea tablas LangGraph. La fase 004 debe mantenerse separada, idealmente en schema `langgraph`.

LangGraph PostgresSaver no reemplaza:

- `task_runs`;
- `core_events`;
- `knowledge_chunk_embeddings`.

Los checkpoints son estado interno/reanudable de workflows o agentes. La verdad operativa visible para Team360 sigue en tablas core.

## Relacion Con GraphRAG Futuro

La 003 habilita RAG vectorial simple. GraphRAG sigue fuera de alcance.

Una fase futura puede agregar:

- entidades;
- relaciones;
- grafos;
- indices auxiliares;
- jobs de extraccion.

Esa fase debe apoyarse en `knowledge_scopes`, `knowledge_documents`, `knowledge_chunks` y los embeddings ya persistidos, sin mezclar checkpoints LangGraph con el modelo core.
