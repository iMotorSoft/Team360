-- FUTURE OPTIONAL / NOT INTEGRATED INTO CURRENT TEAM360 RUNTIME
-- Preserved for later catalog/retrieval experiments.
-- Not part of the active priorities today:
-- 1. real channels
-- 2. conversational flow
-- 3. inbox/questions reading
-- 4. normalization into the orchestrator
-- 5. operational telemetry
-- Only revisit after the current core path is stable.

create extension if not exists vector;

create table if not exists team360_catalog_source (
    id bigserial primary key,
    source_system text not null,
    source_entity_type text not null,
    source_entity_key text not null,
    source_workspace_id text,
    source_project_code text,
    source_channel text,
    target_channel text not null default 'mercadolibre',
    target_entity_type text not null,
    title text not null,
    subtitle text,
    body_text text not null,
    metadata_jsonb jsonb not null default '{}'::jsonb,
    content_hash text not null,
    synced_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (source_system, source_entity_type, source_entity_key, target_channel),
    constraint chk_team360_catalog_source_entity_type
        check (source_entity_type in ('project', 'unit', 'marketing_asset')),
    constraint chk_team360_catalog_target_entity_type
        check (target_entity_type in ('catalog', 'offer', 'campaign', 'faq'))
);

create index if not exists idx_team360_catalog_source_project_code
    on team360_catalog_source (source_project_code);

create index if not exists idx_team360_catalog_source_target_channel
    on team360_catalog_source (target_channel);

create index if not exists idx_team360_catalog_source_metadata
    on team360_catalog_source
    using gin (metadata_jsonb);


create table if not exists team360_catalog_chunk (
    id bigserial primary key,
    source_id bigint not null references team360_catalog_source(id) on delete cascade,
    chunk_index integer not null,
    chunk_kind text not null default 'semantic',
    chunk_text text not null,
    token_estimate integer,
    metadata_jsonb jsonb not null default '{}'::jsonb,
    content_hash text not null,
    embedding_model text,
    embedding vector(1536),
    search_tsv tsvector generated always as (
        to_tsvector('spanish', coalesce(chunk_text, ''))
    ) stored,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (source_id, chunk_index),
    constraint chk_team360_catalog_chunk_kind
        check (chunk_kind in ('semantic', 'summary', 'faq'))
);

create index if not exists idx_team360_catalog_chunk_source
    on team360_catalog_chunk (source_id, chunk_index);

create index if not exists idx_team360_catalog_chunk_search_tsv
    on team360_catalog_chunk
    using gin (search_tsv);

create index if not exists idx_team360_catalog_chunk_embedding_hnsw
    on team360_catalog_chunk
    using hnsw (embedding vector_cosine_ops)
    where embedding is not null;

create index if not exists idx_team360_catalog_chunk_metadata
    on team360_catalog_chunk
    using gin (metadata_jsonb);


create table if not exists team360_telemetry_sync_run (
    id bigserial primary key,
    run_id uuid not null unique,
    source_system text not null,
    source_database text,
    target_database text,
    target_channel text not null,
    status text not null,
    started_at timestamptz not null default now(),
    finished_at timestamptz,
    documents_seen integer not null default 0,
    documents_upserted integer not null default 0,
    chunks_upserted integer not null default 0,
    chunks_embedded integer not null default 0,
    embeddings_skipped integer not null default 0,
    error_text text,
    meta_jsonb jsonb not null default '{}'::jsonb,
    constraint chk_team360_telemetry_sync_run_status
        check (status in ('running', 'completed', 'failed'))
);

create index if not exists idx_team360_telemetry_sync_run_started_at
    on team360_telemetry_sync_run (started_at desc);


create table if not exists team360_telemetry_retrieval_event (
    id bigserial primary key,
    event_id uuid not null unique,
    conversation_id text,
    channel text not null default 'mercadolibre',
    query_text text not null,
    query_embedding_model text,
    retrieval_mode text not null,
    top_k integer not null default 8,
    started_at timestamptz not null default now(),
    finished_at timestamptz,
    meta_jsonb jsonb not null default '{}'::jsonb,
    constraint chk_team360_telemetry_retrieval_mode
        check (retrieval_mode in ('semantic', 'lexical', 'hybrid'))
);

create index if not exists idx_team360_telemetry_retrieval_event_conversation
    on team360_telemetry_retrieval_event (conversation_id, started_at desc);


create table if not exists team360_telemetry_retrieval_hit (
    id bigserial primary key,
    retrieval_event_id bigint not null references team360_telemetry_retrieval_event(id) on delete cascade,
    rank_position integer not null,
    catalog_chunk_id bigint references team360_catalog_chunk(id) on delete set null,
    source_id bigint references team360_catalog_source(id) on delete set null,
    score_cosine double precision,
    score_lexical real,
    score_final double precision,
    source_project_code text,
    source_entity_type text,
    meta_jsonb jsonb not null default '{}'::jsonb
);

create index if not exists idx_team360_telemetry_retrieval_hit_event
    on team360_telemetry_retrieval_hit (retrieval_event_id, rank_position);


create table if not exists team360_telemetry_ai_turn (
    id bigserial primary key,
    turn_id uuid not null unique,
    conversation_id text not null,
    channel text not null default 'mercadolibre',
    role text not null,
    model text,
    prompt_tokens integer,
    completion_tokens integer,
    latency_ms integer,
    input_text text,
    output_text text,
    retrieval_event_id bigint references team360_telemetry_retrieval_event(id) on delete set null,
    created_at timestamptz not null default now(),
    meta_jsonb jsonb not null default '{}'::jsonb,
    constraint chk_team360_telemetry_ai_turn_role
        check (role in ('system', 'user', 'assistant', 'tool'))
);

create index if not exists idx_team360_telemetry_ai_turn_conversation
    on team360_telemetry_ai_turn (conversation_id, created_at desc);


create or replace function team360_search_catalog_lexical(
    query_text text,
    match_count integer default 8,
    filter_project_code text default null,
    filter_channel text default null
)
returns table (
    chunk_id bigint,
    source_id bigint,
    source_entity_type text,
    source_entity_key text,
    source_project_code text,
    title text,
    chunk_text text,
    lexical_score real
)
language sql
stable
as $$
with query_input as (
    select plainto_tsquery('spanish', query_text) as q
)
select
    c.id,
    s.id,
    s.source_entity_type,
    s.source_entity_key,
    s.source_project_code,
    s.title,
    c.chunk_text,
    ts_rank_cd(c.search_tsv, query_input.q) as lexical_score
from team360_catalog_chunk c
join team360_catalog_source s on s.id = c.source_id
cross join query_input
where c.search_tsv @@ query_input.q
  and (filter_project_code is null or s.source_project_code = filter_project_code)
  and (filter_channel is null or s.target_channel = filter_channel)
order by lexical_score desc, c.id desc
limit greatest(match_count, 1);
$$;


create or replace function team360_search_catalog_semantic(
    query_embedding vector(1536),
    match_count integer default 8,
    filter_project_code text default null,
    filter_channel text default null
)
returns table (
    chunk_id bigint,
    source_id bigint,
    source_entity_type text,
    source_entity_key text,
    source_project_code text,
    title text,
    chunk_text text,
    cosine_distance double precision
)
language sql
stable
as $$
select
    c.id,
    s.id,
    s.source_entity_type,
    s.source_entity_key,
    s.source_project_code,
    s.title,
    c.chunk_text,
    (c.embedding <=> query_embedding) as cosine_distance
from team360_catalog_chunk c
join team360_catalog_source s on s.id = c.source_id
where c.embedding is not null
  and (filter_project_code is null or s.source_project_code = filter_project_code)
  and (filter_channel is null or s.target_channel = filter_channel)
order by c.embedding <=> query_embedding asc, c.id desc
limit greatest(match_count, 1);
$$;


create or replace function team360_begin_retrieval_event(
    p_conversation_id text,
    p_channel text,
    p_query_text text,
    p_retrieval_mode text,
    p_top_k integer default 8,
    p_query_embedding_model text default null,
    p_meta_jsonb jsonb default '{}'::jsonb
)
returns bigint
language sql
as $$
    insert into team360_telemetry_retrieval_event (
        event_id,
        conversation_id,
        channel,
        query_text,
        query_embedding_model,
        retrieval_mode,
        top_k,
        meta_jsonb
    )
    values (
        gen_random_uuid(),
        p_conversation_id,
        coalesce(nullif(trim(p_channel), ''), 'mercadolibre'),
        p_query_text,
        p_query_embedding_model,
        p_retrieval_mode,
        greatest(p_top_k, 1),
        coalesce(p_meta_jsonb, '{}'::jsonb)
    )
    returning id;
$$;


create or replace function team360_finish_retrieval_event(
    p_retrieval_event_id bigint,
    p_meta_jsonb jsonb default null
)
returns void
language sql
as $$
    update team360_telemetry_retrieval_event
    set
        finished_at = now(),
        meta_jsonb = case
            when p_meta_jsonb is null then meta_jsonb
            else meta_jsonb || p_meta_jsonb
        end
    where id = p_retrieval_event_id;
$$;


create or replace function team360_log_retrieval_hit(
    p_retrieval_event_id bigint,
    p_rank_position integer,
    p_catalog_chunk_id bigint,
    p_source_id bigint,
    p_score_cosine double precision default null,
    p_score_lexical real default null,
    p_score_final double precision default null,
    p_source_project_code text default null,
    p_source_entity_type text default null,
    p_meta_jsonb jsonb default '{}'::jsonb
)
returns bigint
language sql
as $$
    insert into team360_telemetry_retrieval_hit (
        retrieval_event_id,
        rank_position,
        catalog_chunk_id,
        source_id,
        score_cosine,
        score_lexical,
        score_final,
        source_project_code,
        source_entity_type,
        meta_jsonb
    )
    values (
        p_retrieval_event_id,
        greatest(p_rank_position, 1),
        p_catalog_chunk_id,
        p_source_id,
        p_score_cosine,
        p_score_lexical,
        p_score_final,
        p_source_project_code,
        p_source_entity_type,
        coalesce(p_meta_jsonb, '{}'::jsonb)
    )
    returning id;
$$;


create or replace function team360_log_ai_turn(
    p_conversation_id text,
    p_channel text,
    p_role text,
    p_model text default null,
    p_input_text text default null,
    p_output_text text default null,
    p_prompt_tokens integer default null,
    p_completion_tokens integer default null,
    p_latency_ms integer default null,
    p_retrieval_event_id bigint default null,
    p_meta_jsonb jsonb default '{}'::jsonb
)
returns bigint
language sql
as $$
    insert into team360_telemetry_ai_turn (
        turn_id,
        conversation_id,
        channel,
        role,
        model,
        prompt_tokens,
        completion_tokens,
        latency_ms,
        input_text,
        output_text,
        retrieval_event_id,
        meta_jsonb
    )
    values (
        gen_random_uuid(),
        p_conversation_id,
        coalesce(nullif(trim(p_channel), ''), 'mercadolibre'),
        p_role,
        p_model,
        p_prompt_tokens,
        p_completion_tokens,
        p_latency_ms,
        p_input_text,
        p_output_text,
        p_retrieval_event_id,
        coalesce(p_meta_jsonb, '{}'::jsonb)
    )
    returning id;
$$;
