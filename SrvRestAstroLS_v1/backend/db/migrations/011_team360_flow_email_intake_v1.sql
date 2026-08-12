-- Team360 migration 011 — Flow email AI intake with human confirmation.
-- Additive V1 persistence only; no routing, sector, SLA or escalation fields.
-- Depends on migrations 001 through 010.

create table if not exists flow_conversations (
    id                  uuid        primary key default gen_random_uuid(),
    provider            text        not null,
    channel             text        not null,
    external_thread_id  text        not null,
    citizen_address     text        not null,
    subject             text        not null default '',
    state               text        not null default 'RECEIVED',
    candidate_revision  integer     not null default 0,
    created_at_utc      timestamptz not null default now(),
    updated_at_utc      timestamptz not null default now(),
    constraint chk_flow_conversation_state check (
        state in (
            'RECEIVED', 'INTERPRETED', 'PENDING_CONFIRMATION',
            'PENDING_CLARIFICATION', 'CORRECTED', 'CONFIRMED'
        )
    ),
    constraint chk_flow_conversation_revision check (candidate_revision >= 0),
    constraint uq_flow_conversation_external_thread unique (provider, external_thread_id)
);

create table if not exists flow_messages (
    id                  uuid        primary key default gen_random_uuid(),
    conversation_id     uuid        not null references flow_conversations(id),
    provider            text        not null,
    external_message_id text        not null,
    direction           text        not null,
    sender_address      text        not null,
    recipients_jsonb    jsonb       not null default '[]'::jsonb,
    subject             text        not null default '',
    text_body           text        not null default '',
    occurred_at_utc     timestamptz not null,
    processed_at_utc    timestamptz,
    metadata_jsonb      jsonb       not null default '{}'::jsonb,
    created_at_utc      timestamptz not null default now(),
    constraint chk_flow_message_direction check (direction in ('inbound', 'outbound')),
    constraint chk_flow_message_recipients check (jsonb_typeof(recipients_jsonb) = 'array'),
    constraint chk_flow_message_metadata check (jsonb_typeof(metadata_jsonb) = 'object'),
    constraint uq_flow_message_external unique (provider, external_message_id)
);

create table if not exists flow_interpretations (
    id                  uuid        primary key default gen_random_uuid(),
    conversation_id     uuid        not null references flow_conversations(id),
    source_message_id   uuid        not null references flow_messages(id),
    phase               text        not null,
    outcome             text        not null,
    payload_jsonb       jsonb       not null,
    ai_provider         text        not null,
    ai_model            text        not null,
    usage_jsonb         jsonb       not null default '{}'::jsonb,
    latency_ms          integer,
    created_at_utc      timestamptz not null default now(),
    constraint chk_flow_interpretation_phase check (phase in ('initial', 'reply')),
    constraint chk_flow_interpretation_payload check (jsonb_typeof(payload_jsonb) = 'object'),
    constraint chk_flow_interpretation_usage check (jsonb_typeof(usage_jsonb) = 'object'),
    constraint chk_flow_interpretation_latency check (latency_ms is null or latency_ms >= 0),
    constraint uq_flow_interpretation_source unique (source_message_id)
);

create table if not exists flow_request_candidates (
    id                  uuid        primary key default gen_random_uuid(),
    conversation_id     uuid        not null references flow_conversations(id),
    revision            integer     not null,
    ordinal             integer     not null,
    description         text        not null,
    tentative_category  text,
    location_text       text,
    missing_data_jsonb  jsonb       not null default '[]'::jsonb,
    context_notes       text,
    confidence          numeric(5,4),
    status              text        not null default 'ACTIVE',
    created_at_utc      timestamptz not null default now(),
    updated_at_utc      timestamptz not null default now(),
    constraint chk_flow_candidate_description check (length(description) > 0),
    constraint chk_flow_candidate_revision check (revision > 0),
    constraint chk_flow_candidate_ordinal check (ordinal > 0),
    constraint chk_flow_candidate_missing_data check (jsonb_typeof(missing_data_jsonb) = 'array'),
    constraint chk_flow_candidate_confidence check (confidence is null or confidence between 0 and 1),
    constraint chk_flow_candidate_status check (status in ('ACTIVE', 'SUPERSEDED', 'CONFIRMED')),
    constraint uq_flow_candidate_revision_ordinal unique (conversation_id, revision, ordinal)
);

create table if not exists flow_requests (
    id                  uuid        primary key default gen_random_uuid(),
    conversation_id     uuid        not null references flow_conversations(id),
    source_candidate_id uuid        not null references flow_request_candidates(id),
    description         text        not null,
    tentative_category  text,
    location_text       text,
    missing_data_jsonb  jsonb       not null default '[]'::jsonb,
    context_notes       text,
    confidence          numeric(5,4),
    status              text        not null default 'CONFIRMED',
    confirmed_at_utc    timestamptz not null,
    created_at_utc      timestamptz not null default now(),
    constraint chk_flow_request_status check (status = 'CONFIRMED'),
    constraint chk_flow_request_missing_data check (jsonb_typeof(missing_data_jsonb) = 'array'),
    constraint uq_flow_request_source_candidate unique (source_candidate_id)
);

create index if not exists idx_flow_conversations_state
    on flow_conversations (state, updated_at_utc);
create index if not exists idx_flow_messages_conversation
    on flow_messages (conversation_id, occurred_at_utc);
create index if not exists idx_flow_candidates_active
    on flow_request_candidates (conversation_id, ordinal) where status = 'ACTIVE';
create index if not exists idx_flow_requests_conversation
    on flow_requests (conversation_id, confirmed_at_utc);

comment on table flow_conversations is
    'External citizen conversations and persistent Flow intake state.';
comment on table flow_messages is
    'Normalized inbound/outbound messages with provider idempotency keys.';
comment on table flow_interpretations is
    'Schema-validated AI interpretation audit records.';
comment on table flow_request_candidates is
    'Revisioned requests awaiting explicit citizen confirmation.';
comment on table flow_requests is
    'Independent Flow requests created only after human confirmation.';

-- Reversal, when explicitly approved and only if no V1 data must be retained:
-- drop table flow_requests, flow_request_candidates, flow_interpretations,
--            flow_messages, flow_conversations;
