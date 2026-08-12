-- Team360 migration 013 — Level 1 operational replies and first response.
-- Additive V1 only: no SLA, timers, upper levels, escalation or resolution.
-- Depends on migrations 011 and 012.

alter table flow_request_routings
    add column if not exists outbound_observed_rfc_message_id text;

create unique index if not exists uq_flow_routing_observed_rfc_message
    on flow_request_routings (outbound_observed_rfc_message_id)
    where outbound_observed_rfc_message_id is not null;

create table if not exists flow_request_work_states (
    request_id             uuid        primary key references flow_requests(id),
    routing_id             uuid        not null unique references flow_request_routings(id),
    operational_status     text        not null default 'ASSIGNED',
    first_response_at_utc  timestamptz,
    first_responder        text,
    created_at_utc         timestamptz not null default now(),
    updated_at_utc         timestamptz not null default now(),
    constraint chk_flow_work_status check (
        operational_status in ('ASSIGNED', 'IN_PROGRESS')
    ),
    constraint chk_flow_first_response check (
        operational_status <> 'IN_PROGRESS'
        or (first_response_at_utc is not null and first_responder is not null)
    )
);

create table if not exists flow_request_operational_events (
    id                           uuid        primary key default gen_random_uuid(),
    request_id                   uuid        not null references flow_requests(id),
    routing_id                   uuid        not null references flow_request_routings(id),
    source_message_id            uuid        not null unique references flow_messages(id),
    provider                     text        not null,
    inbound_external_message_id  text        not null,
    responder_address            text        not null,
    response_received_at_utc     timestamptz not null,
    correlation_method           text        not null,
    interpretation_action        text        not null,
    interpretation_jsonb         jsonb       not null default '{}'::jsonb,
    ai_provider                  text        not null,
    ai_model                     text        not null,
    usage_jsonb                  jsonb       not null default '{}'::jsonb,
    latency_ms                   integer,
    created_at_utc               timestamptz not null default now(),
    constraint uq_flow_operational_external_message
        unique (provider, inbound_external_message_id),
    constraint chk_flow_operational_action check (
        interpretation_action in (
            'ACK_OR_PROGRESS', 'AMBIGUOUS', 'UNRELATED',
            'UNSUPPORTED_OPERATIONAL_ACTION'
        )
    ),
    constraint chk_flow_operational_interpretation check (
        jsonb_typeof(interpretation_jsonb) = 'object'
    ),
    constraint chk_flow_operational_usage check (
        jsonb_typeof(usage_jsonb) = 'object'
    ),
    constraint chk_flow_operational_latency check (
        latency_ms is null or latency_ms >= 0
    )
);

create index if not exists idx_flow_operational_events_request
    on flow_request_operational_events (request_id, response_received_at_utc);

insert into flow_request_work_states (request_id, routing_id)
select request_id, id
from flow_request_routings
where status = 'ASSIGNED'
on conflict (request_id) do nothing;

comment on table flow_request_work_states is
    'Operational state separate from routing delivery state; first response is immutable.';
comment on table flow_request_operational_events is
    'Audited, idempotent interpretations of correlated internal operational replies.';

-- Reversal, only when explicitly approved and no operational evidence is needed:
-- drop table flow_request_operational_events, flow_request_work_states;
-- drop index uq_flow_routing_observed_rfc_message;
-- alter table flow_request_routings drop column outbound_observed_rfc_message_id;
