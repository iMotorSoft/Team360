-- Team360 migration 023 — Flow operational settings + scheduler state V1.
-- Additive only: no modifications to existing tables or data.
-- Depends on migrations 011-022.

-- Operational settings: single-row configuration for Flow scheduler and behavior.
create table if not exists flow_operational_settings (
    id                              integer     primary key default 1,
    automation_enabled              boolean     not null default false,
    scheduler_interval_seconds      integer     not null default 15,
    mail_intake_enabled             boolean     not null default true,
    mail_batch_limit                integer     not null default 500,
    mail_after_cutoff               boolean     not null default true,
    updated_at_utc                  timestamptz not null default now(),
    constraint chk_flow_ops_single_row check (id = 1),
    constraint chk_flow_ops_scheduler_interval check (scheduler_interval_seconds > 0),
    constraint chk_flow_ops_mail_batch_limit check (mail_batch_limit > 0)
);

comment on table flow_operational_settings is
    'Flow operational configuration: scheduler, mail intake, limits. Single-row.';

-- Seed defaults if empty.
insert into flow_operational_settings (id) values (1)
on conflict (id) do nothing;

-- Scheduler state: tracks the last cycle execution for UI display.
create table if not exists flow_scheduler_state (
    id                  integer     primary key default 1,
    last_started_at_utc timestamptz,
    last_finished_at_utc timestamptz,
    last_result         text,
    last_error_class    text,
    processed_count     integer     not null default 0,
    cycle_count         integer     not null default 0,
    updated_at_utc      timestamptz not null default now(),
    constraint chk_flow_sched_single_row check (id = 1),
    constraint chk_flow_sched_last_result check (
        last_result is null
        or last_result in ('PASS', 'DEGRADED', 'ERROR', 'SKIPPED')
    )
);

comment on table flow_scheduler_state is
    'Flow scheduler execution state: last cycle result and counters. Single-row.';

insert into flow_scheduler_state (id) values (1)
on conflict (id) do nothing;

-- Reversal (only when explicitly approved):
-- drop table flow_scheduler_state;
-- drop table flow_operational_settings;
