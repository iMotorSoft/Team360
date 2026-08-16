-- Team360 migration 020 — Directorio capability for Flow executive queries.
-- Additive permission-catalog seed only: no user grants (those are operational
-- fixtures), no RBAC redesign. Depends on migration 002 (RBAC tables).
--
-- The Flow executive query route requires the capability
-- `flow.executive.read`, resolved through the existing
-- `list_effective_permissions` RBAC SQL. Without the code existing in
-- core_permissions no grant could ever authorize access, so this seed is the
-- minimal persistent source of truth for the Directorio authorization gate.

insert into core_permissions (permission_code, display_name, description, category)
values (
    'flow.executive.read',
    'Flow Executive Read',
    'Consultar información ejecutiva read-only de Team360 Flow.',
    'flow'
)
on conflict (permission_code) do nothing;

-- Reversal, only when explicitly approved and no grant depends on it:
-- delete from core_permissions where permission_code = 'flow.executive.read';
