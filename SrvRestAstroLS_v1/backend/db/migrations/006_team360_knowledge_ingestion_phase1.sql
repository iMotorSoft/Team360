-- Team360 migration 006 — Knowledge Ingestion Phase 1.
--
-- Adds minimal infrastructure for multi-scope / multi-nivel knowledge ingestion:
--   1. knowledge_ingestion_runs table (track each ingestion run)
--   2. node_path column on knowledge_documents (hierarchical node reference)
--   3. node_path + permission_tags columns on knowledge_chunks (scope filtering)
--   4. knowledge_ingestion_worker seed in worker_definitions
--   5. Indices for the new columns
--
-- This migration does NOT:
--   - Create KnowledgeMap / KnowledgeNode tables (Phase 2+)
--   - Add organization_code / permission_tags to knowledge_chunk_embeddings
--     (deferred to Phase 2 — metadata_jsonb available as interim storage)
--   - Alter knowledge_embedding_models or knowledge_chunk_embeddings schema
--   - Touches automation_diagnosis tables or runtime
--   - Introduces any "vera" technical identifiers
--
-- Depends on migrations 001, 002, 003, 004, 005.

-- ---------------------------------------------------------------------------
-- 1. Knowledge ingestion runs
-- ---------------------------------------------------------------------------

create table if not exists knowledge_ingestion_runs (
    id uuid primary key default gen_random_uuid(),
    knowledge_scope_id uuid not null references knowledge_scopes(id) on delete cascade,
    workspace_id uuid references core_workspaces(id) on delete set null,
    document_source text not null,
    metadata_snapshot jsonb not null default '{}'::jsonb,
    status text not null default 'pending',
    phases_jsonb jsonb not null default '{}'::jsonb,
    chunk_count integer not null default 0,
    token_count integer not null default 0,
    error_code text,
    error_detail text,
    started_at_utc timestamptz,
    completed_at_utc timestamptz,
    created_at_utc timestamptz not null default now(),
    constraint chk_knowledge_ingestion_runs_status
        check (status in (
            'pending', 'validating', 'converting', 'chunking',
            'embedding', 'indexing', 'completed', 'failed'
        )),
    constraint chk_knowledge_ingestion_runs_counts
        check (chunk_count >= 0 and token_count >= 0)
);

create index if not exists idx_kir_knowledge_scope
    on knowledge_ingestion_runs (knowledge_scope_id);

create index if not exists idx_kir_workspace
    on knowledge_ingestion_runs (workspace_id);

create index if not exists idx_kir_status
    on knowledge_ingestion_runs (status);

create index if not exists idx_kir_created_at
    on knowledge_ingestion_runs (created_at_utc desc);

-- Add 'running' to status CHECK and add updated_at_utc column
-- (additive — does not rewrite the table)

do $$
begin
    alter table knowledge_ingestion_runs drop constraint if exists chk_knowledge_ingestion_runs_status;
    alter table knowledge_ingestion_runs add constraint chk_knowledge_ingestion_runs_status
        check (status in (
            'pending', 'running', 'validating', 'converting', 'chunking',
            'embedding', 'indexing', 'completed', 'failed'
        ));
end $$;

do $$
begin
    if not exists (
        select 1 from information_schema.columns
        where table_schema = 'public'
          and table_name = 'knowledge_ingestion_runs'
          and column_name = 'updated_at_utc'
    ) then
        alter table knowledge_ingestion_runs add column updated_at_utc timestamptz;
    end if;
end $$;

-- ---------------------------------------------------------------------------
-- 2. node_path on knowledge_documents
-- ---------------------------------------------------------------------------

do $$
begin
    if not exists (
        select 1 from information_schema.columns
        where table_schema = 'public'
          and table_name = 'knowledge_documents'
          and column_name = 'node_path'
    ) then
        alter table knowledge_documents add column node_path text;
    end if;
end $$;

create index if not exists idx_kd_node_path
    on knowledge_documents (node_path);

-- ---------------------------------------------------------------------------
-- 3. node_path + permission_tags on knowledge_chunks
-- ---------------------------------------------------------------------------

do $$
begin
    if not exists (
        select 1 from information_schema.columns
        where table_schema = 'public'
          and table_name = 'knowledge_chunks'
          and column_name = 'node_path'
    ) then
        alter table knowledge_chunks add column node_path text;
    end if;

    if not exists (
        select 1 from information_schema.columns
        where table_schema = 'public'
          and table_name = 'knowledge_chunks'
          and column_name = 'permission_tags'
    ) then
        alter table knowledge_chunks add column permission_tags text[] not null default '{}';
    end if;
end $$;

create index if not exists idx_kc_node_path
    on knowledge_chunks (node_path);

create index if not exists idx_kc_permission_tags
    on knowledge_chunks using gin (permission_tags);

-- ---------------------------------------------------------------------------
-- 4. Worker definition seed: knowledge_ingestion_worker
-- ---------------------------------------------------------------------------

insert into worker_definitions (
    worker_code,
    display_name,
    description,
    worker_kind,
    default_mode,
    capabilities_jsonb,
    status,
    updated_at_utc
) values (
    'knowledge_ingestion_worker',
    'Knowledge Ingestion Worker',
    'Worker generico que ingiere documentos, los chunkea semanticamente, genera embeddings y registra corridas de ingesta. Valida metadata, convierte a Markdown, preserva jerarquia de nodos y filtros de acceso.',
    'api',
    'assisted',
    '{
       "ingestion_formats": ["markdown", "pdf", "text"],
       "chunk_strategies": ["semantic", "heading", "fixed_size"],
       "embedding_providers": ["openai"],
       "index_targets": ["pgvector"],
       "max_document_size_mb": 10,
       "supported_locales": ["es", "en", "he"]
    }'::jsonb,
    'active',
    now()
)
on conflict (worker_code) do update set
    display_name = excluded.display_name,
    description = excluded.description,
    worker_kind = excluded.worker_kind,
    default_mode = excluded.default_mode,
    capabilities_jsonb = excluded.capabilities_jsonb,
    status = excluded.status,
    updated_at_utc = now();
