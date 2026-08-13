-- Team360 migration 018 — enable the existing first-response SLA for Alumbrado N3.
-- Configuration-only gate: no historical routing backfill, N4 or scheduler.
-- Depends on migrations 014, 016 and 017.

update flow_sector_levels
set first_response_sla_seconds = 30,
    updated_at_utc = now()
where sector_id = 'alumbrado'
  and level = 3;

-- Existing assigned N3 routings are intentionally not backfilled. Their
-- assignment happened while the catalog policy was NULL, so no valid policy
-- snapshot existed at assigned_at_utc.

-- Reversal, only when explicitly approved:
-- update flow_sector_levels set first_response_sla_seconds = null,
--     updated_at_utc = now() where sector_id = 'alumbrado' and level = 3;
