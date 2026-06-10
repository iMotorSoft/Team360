-- Team360 migration 007 — sales diagnosis conversation state persistence.
-- Adds persistent storage for ConversationState used by the sales diagnosis
-- assistant runtime (Fase 1.8).
-- Architecture invariant: PostgreSQL 18 is source of truth for conversation state.
-- Depends on migrations 001, 002, 003, 004, 005 and 006.
-- No provider credentials or secrets are stored here.

-- ---------------------------------------------------------------------------
-- 1. Sales diagnosis conversation states
-- ---------------------------------------------------------------------------

create table if not exists sales_diagnosis_conversation_states (
    session_id              text        not null primary key,
    assistant_instance_code text        not null,
    package_code            text        not null,
    knowledge_scope_code    text        not null,
    state_jsonb             jsonb       not null,
    created_at_utc          timestamptz not null default now(),
    updated_at_utc          timestamptz not null default now(),
    constraint chk_sd_cs_jsonb_is_object
        check (jsonb_typeof(state_jsonb) = 'object'::text)
);

comment on table sales_diagnosis_conversation_states is
    'Conversation state for sales diagnosis assistant runtime. '
    'Architecture invariant: PostgreSQL 18 is source of truth.';

comment on column sales_diagnosis_conversation_states.state_jsonb is
    'JSONB payload containing slots, history_summary, turn_count, risk_flags, '
    'last_sources, pending_questions and other dynamic fields.';

-- ---------------------------------------------------------------------------
-- 2. Indexes
-- ---------------------------------------------------------------------------

create index if not exists idx_sd_cs_updated_at
    on sales_diagnosis_conversation_states (updated_at_utc desc);

create index if not exists idx_sd_cs_assistant_instance
    on sales_diagnosis_conversation_states (assistant_instance_code);

create index if not exists idx_sd_cs_package
    on sales_diagnosis_conversation_states (package_code);

create index if not exists idx_sd_cs_knowledge_scope
    on sales_diagnosis_conversation_states (knowledge_scope_code);
