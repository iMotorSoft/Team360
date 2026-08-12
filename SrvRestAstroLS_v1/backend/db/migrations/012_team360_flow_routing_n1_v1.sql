-- Team360 migration 012 — deterministic Flow routing to sector Level 1.
-- Additive V1 only: no SLA, timers, upper levels, escalation or delegation.
-- Depends on migration 011.

create table if not exists flow_sectors (
    sector_id       text        primary key,
    display_name    text        not null,
    active          boolean     not null default true,
    created_at_utc  timestamptz not null default now(),
    updated_at_utc  timestamptz not null default now(),
    constraint chk_flow_sector_id check (sector_id ~ '^[a-z][a-z0-9_]*$'),
    constraint chk_flow_sector_display_name check (length(trim(display_name)) > 0)
);

create table if not exists flow_sector_levels (
    id              uuid        primary key default gen_random_uuid(),
    sector_id       text        not null references flow_sectors(sector_id),
    level           smallint    not null,
    channel         text        not null,
    destination     text        not null,
    active          boolean     not null default true,
    created_at_utc  timestamptz not null default now(),
    updated_at_utc  timestamptz not null default now(),
    constraint chk_flow_sector_level check (level > 0),
    constraint chk_flow_sector_level_channel check (length(trim(channel)) > 0),
    constraint chk_flow_sector_level_destination check (length(trim(destination)) > 0),
    constraint uq_flow_sector_level unique (sector_id, level)
);

create table if not exists flow_request_routings (
    id                           uuid        primary key default gen_random_uuid(),
    request_id                   uuid        not null references flow_requests(id),
    routing_key                  text        not null default 'initial_n1',
    sector_id                    text        references flow_sectors(sector_id),
    sector_level_id              uuid        references flow_sector_levels(id),
    level                        smallint    not null default 1,
    channel                      text,
    destination                  text,
    status                       text        not null,
    outbound_rfc_message_id      text,
    outbound_external_message_id text,
    attempt_count                integer     not null default 0,
    delivery_uncertain           boolean     not null default false,
    last_error_code              text,
    last_error_detail            text,
    routed_at_utc                timestamptz not null default now(),
    assigned_at_utc              timestamptz,
    updated_at_utc               timestamptz not null default now(),
    constraint chk_flow_routing_key check (length(trim(routing_key)) > 0),
    constraint chk_flow_routing_level check (level > 0),
    constraint chk_flow_routing_status check (
        status in (
            'ROUTING_PENDING', 'ASSIGNED',
            'ROUTING_UNRESOLVED', 'ROUTING_FAILED'
        )
    ),
    constraint chk_flow_routing_attempt_count check (attempt_count >= 0),
    constraint chk_flow_routing_assigned_evidence check (
        status <> 'ASSIGNED'
        or (
            sector_id is not null
            and sector_level_id is not null
            and channel is not null
            and destination is not null
            and outbound_rfc_message_id is not null
            and outbound_external_message_id is not null
            and assigned_at_utc is not null
        )
    ),
    constraint uq_flow_request_routing unique (request_id, routing_key)
);

create unique index if not exists uq_flow_routing_external_message
    on flow_request_routings (outbound_external_message_id)
    where outbound_external_message_id is not null;

create unique index if not exists uq_flow_routing_rfc_message
    on flow_request_routings (outbound_rfc_message_id)
    where outbound_rfc_message_id is not null;

create index if not exists idx_flow_routing_status
    on flow_request_routings (status, updated_at_utc);

insert into flow_sectors (sector_id, display_name, active)
values ('alumbrado', 'Alumbrado Público', true)
on conflict (sector_id) do nothing;

insert into flow_sector_levels (sector_id, level, channel, destination, active)
values ('alumbrado', 1, 'email', 'alumbrado.n1@alquimiablue.com', true)
on conflict (sector_id, level) do nothing;

comment on table flow_sectors is
    'Stable Flow sector catalog; destination addresses are not sector identities.';
comment on table flow_sector_levels is
    'Per-sector delivery configuration by operational level.';
comment on table flow_request_routings is
    'Idempotent routing assignment and external delivery evidence per Flow request.';

-- Reversal, only when explicitly approved and no routing data must be retained:
-- drop table flow_request_routings, flow_sector_levels, flow_sectors;
