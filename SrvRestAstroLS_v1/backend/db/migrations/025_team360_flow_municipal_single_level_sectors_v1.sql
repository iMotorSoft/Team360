-- Team360 migration 025 — municipal single-level sectors.
-- Adds Baches and Residuos without changing Alumbrado or creating upper levels.
-- Depends on migrations 011 through 024.

insert into flow_sectors (
    sector_id, display_name, active, closure_approval_level
) values
    ('baches', 'Baches', true, null),
    ('residuos', 'Residuos', true, null)
on conflict (sector_id) do update set
    display_name = excluded.display_name,
    active = excluded.active,
    closure_approval_level = excluded.closure_approval_level,
    updated_at_utc = now();

insert into flow_sector_levels (
    sector_id, level, channel, destination, active, first_response_sla_seconds
) values
    ('baches', 1, 'email', 'baches.n1@alquimiablue.com', true, 30),
    ('residuos', 1, 'email', 'residuos.n1@alquimiablue.com', true, 30)
on conflict (sector_id, level) do update set
    channel = excluded.channel,
    destination = excluded.destination,
    active = excluded.active,
    first_response_sla_seconds = excluded.first_response_sla_seconds,
    updated_at_utc = now();

comment on table flow_sectors is
    'Stable Flow sector catalog; destination addresses are not sector identities.';
