-- Team360 migration 014 — configurable Level 1 first-response SLA.
-- Additive V1 only: no upper levels, escalation, supervisor delivery or scheduler.
-- Depends on migrations 012 and 013.

alter table flow_sector_levels
    add column if not exists first_response_sla_seconds integer;

do $$
begin
    if not exists (
        select 1 from pg_constraint
        where conname = 'chk_flow_level_first_response_sla_seconds'
    ) then
        alter table flow_sector_levels add constraint
            chk_flow_level_first_response_sla_seconds check (
                first_response_sla_seconds is null
                or first_response_sla_seconds > 0
            );
    end if;
end $$;

update flow_sector_levels
set first_response_sla_seconds = 30,
    updated_at_utc = now()
where sector_id = 'alumbrado' and level = 1;

create table if not exists flow_request_slas (
    id                    uuid        primary key default gen_random_uuid(),
    routing_id            uuid        not null unique references flow_request_routings(id),
    request_id            uuid        not null references flow_requests(id),
    sla_type              text        not null default 'FIRST_RESPONSE',
    duration_seconds      integer     not null,
    started_at_utc        timestamptz not null,
    due_at_utc            timestamptz not null,
    status                text        not null default 'PENDING',
    met_at_utc            timestamptz,
    breached_at_utc       timestamptz,
    evaluated_at_utc      timestamptz not null,
    created_at_utc        timestamptz not null default now(),
    updated_at_utc        timestamptz not null default now(),
    constraint chk_flow_sla_type check (sla_type = 'FIRST_RESPONSE'),
    constraint chk_flow_sla_duration check (duration_seconds > 0),
    constraint chk_flow_sla_due check (
        due_at_utc = started_at_utc + make_interval(secs => duration_seconds)
    ),
    constraint chk_flow_sla_status check (status in ('PENDING', 'MET', 'BREACHED')),
    constraint chk_flow_sla_result check (
        (status = 'PENDING' and met_at_utc is null and breached_at_utc is null)
        or (status = 'MET' and met_at_utc is not null and breached_at_utc is null)
        or (status = 'BREACHED' and met_at_utc is null and breached_at_utc is not null)
    )
);

create table if not exists flow_request_sla_events (
    id              uuid        primary key default gen_random_uuid(),
    sla_id          uuid        not null references flow_request_slas(id),
    event_type      text        not null,
    occurred_at_utc timestamptz not null,
    from_status     text,
    to_status       text        not null,
    created_at_utc  timestamptz not null default now(),
    constraint chk_flow_sla_event_type check (
        event_type in ('SLA_STARTED', 'SLA_MET', 'SLA_BREACHED', 'SLA_RECONCILED')
    ),
    constraint uq_flow_sla_event unique (sla_id, event_type)
);

create index if not exists idx_flow_request_slas_pending_due
    on flow_request_slas (due_at_utc) where status = 'PENDING';
create index if not exists idx_flow_request_slas_request
    on flow_request_slas (request_id, sla_type);

comment on table flow_request_slas is
    'Immutable first-response SLA snapshot and result for one concrete routing.';
comment on table flow_request_sla_events is
    'Idempotent first-response SLA lifecycle and reconciliation audit.';

-- Existing assigned routings are intentionally not backfilled: no historical SLA
-- configuration existed when they were assigned, so fabricating a snapshot is unsafe.

-- Reversal, only when explicitly approved and no SLA evidence is needed:
-- drop table flow_request_sla_events, flow_request_slas;
-- alter table flow_sector_levels drop constraint chk_flow_level_first_response_sla_seconds;
-- alter table flow_sector_levels drop column first_response_sla_seconds;
