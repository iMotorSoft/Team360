-- Team360 migration 017 — catalog-driven escalation from N2 to N3.
-- Additive V1 only: no N3 operational reply, N3 SLA, N4 or scheduler.
-- Depends on migrations 015 and 016.

insert into flow_sector_levels (
    sector_id, level, channel, destination, active, first_response_sla_seconds
) values (
    'alumbrado', 3, 'email', 'alumbrado.n3@alquimiablue.com', true, null
)
on conflict (sector_id, level) do update set
    channel = excluded.channel,
    destination = excluded.destination,
    active = excluded.active,
    first_response_sla_seconds = excluded.first_response_sla_seconds,
    updated_at_utc = now();

-- The next active catalog level may skip inactive levels. Preserve increasing
-- direction without hardcoding adjacency such as N1->N2 or N2->N3.
alter table flow_request_escalations
    drop constraint if exists chk_flow_escalation_levels;

alter table flow_request_escalations
    add constraint chk_flow_escalation_levels check (
        from_level > 0 and to_level > from_level
    );

-- Reversal, only when explicitly approved and no N3 evidence must be retained:
-- delete from flow_sector_levels where sector_id='alumbrado' and level=3;
-- restoring adjacency requires first proving no persisted escalation skips levels.
