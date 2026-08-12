-- Team360 migration 015 — Alumbrado Level 1 to Level 2 escalation.
-- Additive V1 only: no N2 SLA evaluation, N3, scheduler or resolution.
-- Depends on migrations 011 through 014.

-- Work state belongs to a concrete routing. This preserves independent N1/N2
-- operational histories for the same request.
do $$
declare
    current_pk text;
begin
    select conname into current_pk
    from pg_constraint
    where conrelid = 'flow_request_work_states'::regclass
      and contype = 'p';

    if current_pk is not null and current_pk <> 'flow_request_work_states_routing_pkey' then
        execute format('alter table flow_request_work_states drop constraint %I', current_pk);
    end if;

    if exists (
        select 1 from pg_constraint
        where conrelid = 'flow_request_work_states'::regclass
          and conname = 'flow_request_work_states_routing_id_key'
    ) then
        alter table flow_request_work_states
            drop constraint flow_request_work_states_routing_id_key;
    end if;

    if not exists (
        select 1 from pg_constraint
        where conrelid = 'flow_request_work_states'::regclass
          and contype = 'p'
    ) then
        alter table flow_request_work_states
            add constraint flow_request_work_states_routing_pkey primary key (routing_id);
    end if;
end $$;

create index if not exists idx_flow_work_states_request
    on flow_request_work_states (request_id, created_at_utc);

insert into flow_sector_levels (
    sector_id, level, channel, destination, active, first_response_sla_seconds
) values (
    'alumbrado', 2, 'email', 'alumbrado.n2@alquimiablue.com', true, null
)
on conflict (sector_id, level) do update set
    channel = excluded.channel,
    destination = excluded.destination,
    active = excluded.active,
    first_response_sla_seconds = excluded.first_response_sla_seconds,
    updated_at_utc = now();

create table if not exists flow_request_escalations (
    id                    uuid        primary key default gen_random_uuid(),
    request_id            uuid        not null references flow_requests(id),
    sector_id             text        not null references flow_sectors(sector_id),
    from_routing_id       uuid        not null references flow_request_routings(id),
    from_level            smallint    not null,
    trigger_type          text        not null,
    trigger_sla_id        uuid        not null references flow_request_slas(id),
    to_level              smallint    not null,
    to_routing_id         uuid        unique references flow_request_routings(id),
    status                text        not null default 'PENDING',
    last_error_code       text,
    last_error_detail     text,
    created_at_utc        timestamptz not null default now(),
    completed_at_utc      timestamptz,
    updated_at_utc        timestamptz not null default now(),
    constraint chk_flow_escalation_levels check (
        from_level > 0 and to_level = from_level + 1
    ),
    constraint chk_flow_escalation_trigger check (
        trigger_type = 'FIRST_RESPONSE_SLA_BREACHED'
    ),
    constraint chk_flow_escalation_status check (
        status in ('PENDING', 'COMPLETED', 'FAILED')
    ),
    constraint chk_flow_escalation_completion check (
        (status = 'COMPLETED' and to_routing_id is not null and completed_at_utc is not null)
        or (status <> 'COMPLETED' and completed_at_utc is null)
    ),
    constraint uq_flow_escalation_trigger unique (trigger_sla_id, trigger_type)
);

create index if not exists idx_flow_escalations_request
    on flow_request_escalations (request_id, created_at_utc);
create index if not exists idx_flow_escalations_pending
    on flow_request_escalations (status, created_at_utc)
    where status in ('PENDING', 'FAILED');

comment on table flow_request_escalations is
    'Idempotent audit linking a breached routing SLA to the next routing level.';
comment on column flow_request_work_states.routing_id is
    'Primary operational identity; one independent work state per routing level.';

-- Reversal, only when explicitly approved and no N2 evidence must be retained:
-- drop table flow_request_escalations;
-- delete from flow_sector_levels where sector_id='alumbrado' and level=2;
-- restoring request-scoped work-state identity requires first removing all but
-- one work state per request, so it is intentionally not an automatic rollback.
