-- Team360 migration 019 — supervisor-approved case resolution and audit record.
-- Additive V1 only: technical resolution proposal -> supervisor closure approval
-- -> RESOLVED -> immutable audit snapshot. No reopen, N4, scheduler or worker.
-- Depends on migrations 011 through 018.

-- ---------------------------------------------------------------------------
-- Request lifecycle status. CONFIRMED remains the pre-routing baseline and the
-- working state; RESOLUTION_PENDING_APPROVAL means a technician proposed
-- resolution and Flow awaits supervisor authorization; RESOLVED is terminal.
-- ---------------------------------------------------------------------------
alter table flow_requests drop constraint if exists chk_flow_request_status;
alter table flow_requests add constraint chk_flow_request_status check (
    status in (
        'CONFIRMED', 'ACTIVE', 'RESOLUTION_PENDING_APPROVAL', 'RESOLVED'
    )
);

alter table flow_requests
    add column if not exists resolved_at_utc timestamptz,
    add column if not exists authorized_by text;

-- The operational reply interpreter now emits RESOLUTION_PROPOSED, so the
-- 013 audit constraint must admit the new interpretation action.
alter table flow_request_operational_events
    drop constraint if exists chk_flow_operational_action;
alter table flow_request_operational_events
    add constraint chk_flow_operational_action check (
        interpretation_action in (
            'ACK_OR_PROGRESS', 'RESOLUTION_PROPOSED', 'AMBIGUOUS', 'UNRELATED',
            'UNSUPPORTED_OPERATIONAL_ACTION'
        )
    );

-- ---------------------------------------------------------------------------
-- Closure approval authority policy, resolved per sector. The supervisor level
-- is configuration, never inferred from the current routing level.
-- ---------------------------------------------------------------------------
alter table flow_sectors
    add column if not exists closure_approval_level smallint;

do $$
begin
    if not exists (
        select 1 from pg_constraint
        where conname = 'chk_flow_sector_closure_approval_level'
    ) then
        alter table flow_sectors add constraint
            chk_flow_sector_closure_approval_level check (
                closure_approval_level is null or closure_approval_level > 0
            );
    end if;
end $$;

update flow_sectors
set closure_approval_level = 2,
    updated_at_utc = now()
where sector_id = 'alumbrado';

-- ---------------------------------------------------------------------------
-- Technical resolution proposals. One proposal per correlated inbound message;
-- multiple proposals are allowed over a request's lifetime (reject -> retry).
-- ---------------------------------------------------------------------------
create table if not exists flow_request_resolutions (
    id                          uuid        primary key default gen_random_uuid(),
    request_id                  uuid        not null references flow_requests(id),
    routing_id                  uuid        not null references flow_request_routings(id),
    status                      text        not null default 'PROPOSED',
    proposed_by                 text        not null,
    proposed_at_utc             timestamptz not null,
    source_provider             text        not null,
    source_external_message_id  text        not null,
    resolution_text             text        not null default '',
    created_at_utc              timestamptz not null default now(),
    updated_at_utc              timestamptz not null default now(),
    constraint chk_flow_resolution_status check (
        status in ('PROPOSED', 'APPROVED', 'REJECTED')
    ),
    constraint uq_flow_resolution_source unique (source_provider, source_external_message_id)
);

create index if not exists idx_flow_resolutions_request
    on flow_request_resolutions (request_id, proposed_at_utc);

-- ---------------------------------------------------------------------------
-- Supervisor closure approvals. Exactly one approval per resolution; the
-- decision source message is unique so a single Gmail reply decides once.
-- ---------------------------------------------------------------------------
create table if not exists flow_closure_approvals (
    id                                    uuid        primary key default gen_random_uuid(),
    request_id                            uuid        not null references flow_requests(id),
    resolution_id                         uuid        not null unique references flow_request_resolutions(id),
    approver_level                        smallint    not null,
    approver_destination                  text        not null,
    approval_token                        text        not null unique,
    status                                text        not null default 'PENDING',
    outbound_rfc_message_id               text,
    outbound_external_message_id          text,
    outbound_observed_rfc_message_id      text,
    decision_source_external_message_id   text,
    decided_by                            text,
    decided_at_utc                        timestamptz,
    decision_reason                       text,
    created_at_utc                        timestamptz not null default now(),
    updated_at_utc                        timestamptz not null default now(),
    constraint chk_flow_approval_level check (approver_level > 0),
    constraint chk_flow_approval_token check (approval_token ~ '^[0-9a-f]{8,64}$'),
    constraint chk_flow_approval_status check (
        status in ('PENDING', 'APPROVED', 'REJECTED', 'DELIVERY_UNCERTAIN')
    ),
    constraint chk_flow_approval_decision check (
        (status in ('APPROVED', 'REJECTED')
         and decided_by is not null
         and decided_at_utc is not null
         and decision_source_external_message_id is not null)
        or (status in ('PENDING', 'DELIVERY_UNCERTAIN')
            and decided_at_utc is null
            and decided_by is null)
    )
);

create index if not exists idx_flow_approvals_request
    on flow_closure_approvals (request_id, created_at_utc);

create unique index if not exists uq_flow_approval_decision_source
    on flow_closure_approvals (decision_source_external_message_id)
    where decision_source_external_message_id is not null;

-- ---------------------------------------------------------------------------
-- Immutable, versioned case audit snapshot for Directorio/Auditoria.
-- ---------------------------------------------------------------------------
create table if not exists flow_case_audit_records (
    id                  uuid        primary key default gen_random_uuid(),
    request_id          uuid        not null references flow_requests(id),
    schema_version      integer     not null default 1,
    generated_at_utc    timestamptz not null default now(),
    resolved_at_utc     timestamptz not null,
    snapshot_jsonb      jsonb       not null,
    snapshot_sha256     text        not null,
    created_at_utc      timestamptz not null default now(),
    constraint chk_flow_audit_schema_version check (schema_version > 0),
    constraint chk_flow_audit_snapshot check (jsonb_typeof(snapshot_jsonb) = 'object'),
    constraint chk_flow_audit_sha check (snapshot_sha256 ~ '^[0-9a-f]{64}$'),
    constraint uq_flow_audit_request_version unique (request_id, schema_version)
);

create index if not exists idx_flow_audit_request
    on flow_case_audit_records (request_id, generated_at_utc);

-- ---------------------------------------------------------------------------
-- DB-level closure integrity: RESOLVED requires a referenced approval that is
-- APPROVED, belongs to the same request, and has an APPROVED resolution. The
-- trigger is the authoritative gate; Python atomically follows it.
-- ---------------------------------------------------------------------------
alter table flow_requests
    add column if not exists authorized_approval_id uuid
        references flow_closure_approvals(id);

do $$
begin
    if not exists (
        select 1 from pg_constraint
        where conname = 'chk_flow_request_resolution_evidence'
    ) then
        alter table flow_requests add constraint
            chk_flow_request_resolution_evidence check (
                status <> 'RESOLVED'
                or (
                    resolved_at_utc is not null
                    and authorized_by is not null
                    and authorized_approval_id is not null
                )
            );
    end if;
end $$;

create or replace function fn_flow_request_resolution_guard() returns trigger as $$
declare
    approval_status    text;
    approval_request   uuid;
    resolution_status  text;
begin
    if TG_OP = 'UPDATE' and OLD.status = 'RESOLVED' and NEW.status <> 'RESOLVED' then
        raise exception 'Flow request resolution is terminal and cannot be degraded';
    end if;

    if NEW.status = 'RESOLVED' then
        if NEW.authorized_approval_id is null then
            raise exception 'Flow RESOLVED request requires an authorized approval';
        end if;
        select a.status, a.request_id, r.status
          into approval_status, approval_request, resolution_status
          from flow_closure_approvals a
          join flow_request_resolutions r on r.id = a.resolution_id
         where a.id = NEW.authorized_approval_id;
        if approval_status is distinct from 'APPROVED'
           or approval_request is distinct from NEW.id
           or resolution_status is distinct from 'APPROVED' then
            raise exception
                'Flow RESOLVED requires an APPROVED closure approval for this request';
        end if;
    end if;
    return NEW;
end;
$$ language plpgsql;

drop trigger if exists trg_flow_request_resolution_guard on flow_requests;
create trigger trg_flow_request_resolution_guard
    before insert or update on flow_requests
    for each row execute function fn_flow_request_resolution_guard();

comment on table flow_request_resolutions is
    'Idempotent technical resolution proposals tied to a concrete routing.';
comment on table flow_closure_approvals is
    'Supervisor closure authorization with exactly-once decision evidence.';
comment on table flow_case_audit_records is
    'Immutable, hash-verified snapshot of the case truth at closure.';
comment on column flow_sectors.closure_approval_level is
    'Catalog level authorized to approve closure for this sector.';
comment on column flow_requests.authorized_approval_id is
    'APPROVED closure approval that authorized this RESOLVED state.';

-- Reversal, only when explicitly approved and no closure evidence is retained.
-- Order matters: the authorized_approval_id FK must be dropped before the
-- approvals table, and the guard trigger/check must be removed before clearing
-- any RESOLVED request evidence.
-- alter table flow_requests drop constraint if exists chk_flow_request_resolution_evidence;
-- alter table flow_requests disable trigger trg_flow_request_resolution_guard;
-- drop trigger if exists trg_flow_request_resolution_guard on flow_requests;
-- drop function if exists fn_flow_request_resolution_guard();
-- drop table if exists flow_case_audit_records;
-- alter table flow_requests drop column if exists authorized_approval_id;
-- drop table if exists flow_closure_approvals, flow_request_resolutions;
-- alter table flow_requests drop column if exists authorized_by,
--     drop column if exists resolved_at_utc;
-- alter table flow_sectors drop column if exists closure_approval_level;
-- restoring status = 'CONFIRMED' and the four-action operational constraint
-- requires first proving no RESOLVED request or RESOLUTION_PROPOSED event must
-- be retained, so it is intentionally not an automatic rollback.
