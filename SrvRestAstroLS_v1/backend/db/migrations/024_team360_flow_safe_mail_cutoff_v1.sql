-- Team360 migration 024 — Flow safe configurable mail cutoff V1.
-- Additive only. Depends on migration 023.

alter table flow_operational_settings
    add column if not exists mail_cutoff_epoch bigint not null
    default 1787239323;

-- Normalize only the unsafe development fallback introduced before this
-- migration existed. Operator-defined cutoffs are preserved.
update flow_operational_settings
set mail_cutoff_epoch = 1787239323,
    updated_at_utc = now()
where mail_cutoff_epoch = 1767225600;

alter table flow_operational_settings
    alter column mail_cutoff_epoch set default 1787239323,
    alter column mail_cutoff_epoch set not null;

do $$
begin
    if not exists (
        select 1
        from pg_constraint
        where conname = 'chk_flow_ops_mail_cutoff_epoch'
          and conrelid = 'flow_operational_settings'::regclass
    ) then
        alter table flow_operational_settings
            add constraint chk_flow_ops_mail_cutoff_epoch check (
                mail_cutoff_epoch between 1577836800 and 1893456000
            );
    end if;
end
$$;

comment on column flow_operational_settings.mail_cutoff_epoch is
    'Unix epoch UTC used by the Flow Gmail query as after:<epoch>.';

-- Reversal (only when explicitly approved):
-- alter table flow_operational_settings drop column mail_cutoff_epoch;
