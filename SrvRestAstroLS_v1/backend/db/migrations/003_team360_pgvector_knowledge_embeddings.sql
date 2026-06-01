-- Team360 migration 003: pgvector knowledge embeddings.
-- Prepares persistence for embeddings over knowledge_chunks.
-- Does not generate embeddings, call LLM providers or create GraphRAG/LangGraph tables.

create extension if not exists vector;

-- ---------------------------------------------------------------------------
-- 1. Embedding model catalog
-- ---------------------------------------------------------------------------

create table if not exists knowledge_embedding_models (
    embedding_model_id uuid primary key default gen_random_uuid(),
    provider_code text not null,
    model_code text not null,
    model_alias text not null,
    dimension integer not null,
    distance_metric text not null default 'cosine',
    status text not null default 'active',
    metadata_jsonb jsonb not null default '{}'::jsonb,
    created_at_utc timestamptz not null default now(),
    updated_at_utc timestamptz not null default now(),
    constraint chk_kem_dimension
        check (dimension > 0),
    constraint chk_kem_distance_metric
        check (distance_metric in ('cosine', 'l2', 'ip')),
    constraint chk_kem_status
        check (status in ('active', 'inactive', 'deprecated')),
    constraint uq_kem_provider_model_dimension
        unique (provider_code, model_code, dimension),
    constraint uq_kem_model_alias
        unique (model_alias)
);

insert into knowledge_embedding_models (
    provider_code,
    model_code,
    model_alias,
    dimension,
    distance_metric,
    status,
    metadata_jsonb
)
values (
    'openai',
    'text-embedding-3-small',
    'default_1536',
    1536,
    'cosine',
    'active',
    '{"purpose": "default Team360 knowledge embedding model catalog entry"}'::jsonb
)
on conflict (model_alias) do nothing;

-- ---------------------------------------------------------------------------
-- 2. Chunk embeddings
-- ---------------------------------------------------------------------------

create table if not exists knowledge_chunk_embeddings (
    chunk_embedding_id uuid primary key default gen_random_uuid(),
    knowledge_chunk_id uuid not null references knowledge_chunks(id) on delete cascade,
    knowledge_scope_id uuid not null references knowledge_scopes(id) on delete cascade,
    embedding_model_id uuid not null references knowledge_embedding_models(embedding_model_id) on delete restrict,
    embedding vector(1536),
    embedding_status text not null default 'pending',
    content_hash text,
    metadata_jsonb jsonb not null default '{}'::jsonb,
    embedded_at_utc timestamptz,
    created_at_utc timestamptz not null default now(),
    updated_at_utc timestamptz not null default now(),
    constraint chk_kce_embedding_status
        check (embedding_status in ('pending', 'ready', 'failed', 'stale')),
    constraint chk_kce_ready_requires_embedding
        check (
            (embedding_status = 'ready' and embedding is not null)
            or
            (embedding_status <> 'ready')
        ),
    constraint uq_kce_chunk_model
        unique (knowledge_chunk_id, embedding_model_id)
);

create index if not exists idx_kce_knowledge_scope
    on knowledge_chunk_embeddings (knowledge_scope_id);

create index if not exists idx_kce_knowledge_chunk
    on knowledge_chunk_embeddings (knowledge_chunk_id);

create index if not exists idx_kce_embedding_model
    on knowledge_chunk_embeddings (embedding_model_id);

create index if not exists idx_kce_embedding_status
    on knowledge_chunk_embeddings (embedding_status);

create index if not exists idx_kce_ready_scope_model
    on knowledge_chunk_embeddings (knowledge_scope_id, embedding_model_id)
    where embedding_status = 'ready';

create index if not exists idx_kce_embedding_hnsw_cosine
    on knowledge_chunk_embeddings
    using hnsw (embedding vector_cosine_ops)
    where embedding_status = 'ready';

-- ---------------------------------------------------------------------------
-- 3. Retrieval view
-- ---------------------------------------------------------------------------

create or replace view knowledge_ready_chunks as
select
    kce.knowledge_scope_id,
    kd.id as knowledge_document_id,
    kc.id as knowledge_chunk_id,
    kc.chunk_index,
    kc.title,
    kc.content,
    kce.embedding_model_id,
    kem.model_alias,
    kce.embedding_status,
    kce.embedded_at_utc
from knowledge_chunk_embeddings kce
join knowledge_chunks kc
    on kc.id = kce.knowledge_chunk_id
join knowledge_documents kd
    on kd.id = kc.knowledge_document_id
join knowledge_embedding_models kem
    on kem.embedding_model_id = kce.embedding_model_id
where kce.embedding_status = 'ready'
  and kce.embedding is not null
  and kd.knowledge_scope_id = kce.knowledge_scope_id;
