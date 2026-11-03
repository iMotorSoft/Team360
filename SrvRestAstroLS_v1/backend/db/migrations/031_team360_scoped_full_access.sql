-- DEV opt-in only. No assignments, authentication changes or ordinary grant changes.
-- An explicit enabled registry entry is required; no prefix/wildcard authorization.
CREATE TABLE IF NOT EXISTS core_workspace_capabilities (
    workspace_id uuid NOT NULL REFERENCES core_workspaces(id),
    module text NOT NULL CHECK (module ~ '^[a-z][a-z0-9_]*$'),
    capability_code text NOT NULL,
    permission_id uuid NOT NULL REFERENCES core_permissions(id),
    enabled boolean NOT NULL DEFAULT false,
    PRIMARY KEY (workspace_id, module, capability_code)
);
CREATE TABLE IF NOT EXISTS core_module_full_access_grants (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES core_organizations(id),
    workspace_id uuid NOT NULL REFERENCES core_workspaces(id),
    module text NOT NULL CHECK (module ~ '^[a-z][a-z0-9_]*$'),
    user_id uuid NOT NULL REFERENCES core_users(id),
    granted_by uuid NOT NULL REFERENCES core_users(id),
    granted_at_utc timestamptz NOT NULL DEFAULT now(),
    revoked_at_utc timestamptz,
    revoked_by uuid REFERENCES core_users(id),
    CHECK ((revoked_at_utc IS NULL) = (revoked_by IS NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_core_module_full_access_active
    ON core_module_full_access_grants(workspace_id,module,user_id)
    WHERE revoked_at_utc IS NULL;
-- Revocation retains the grant row. Administrative operations also append core_events.
