-- Team360 migration 021 — sector configuration capabilities for Flow.
-- Additive permission-catalog seed only: no user grants (those are operational
-- fixtures), no RBAC redesign. Depends on migration 002 (RBAC tables) and 020.
--
-- The Flow sector configuration API (read + atomic write of
-- flow_sectors / flow_sector_levels) requires the capabilities
-- `flow.configuration.read` and `flow.configuration.write`, resolved through
-- the existing `list_effective_permissions` RBAC SQL. Fail closed: without the
-- explicit capability every request is denied before any data access or
-- mutation. `flow.executive.read` does NOT grant configuration access.

insert into core_permissions (permission_code, display_name, description, category)
values (
    'flow.configuration.read',
    'Flow Configuration Read',
    'Leer la configuración de routing de Team360 Flow.',
    'flow'
)
on conflict (permission_code) do nothing;

insert into core_permissions (permission_code, display_name, description, category)
values (
    'flow.configuration.write',
    'Flow Configuration Write',
    'Actualizar la configuración de routing de Team360 Flow.',
    'flow'
)
on conflict (permission_code) do nothing;

-- Reversal, only when explicitly approved and no grant depends on it:
-- delete from core_permissions
-- where permission_code in ('flow.configuration.read', 'flow.configuration.write');
