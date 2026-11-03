-- Prepared only: operational application requires a separate authorization.
-- Identity only; business permissions remain in existing Console RBAC.
-- tenant_id is the trusted channel's external scope, not a new core tenant.
BEGIN;
CREATE TABLE messaging_phone_bindings (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    environment text NOT NULL CHECK (environment IN ('dev','pro')),
    provider text NOT NULL REFERENCES communication_providers(code),
    sender_identity text NOT NULL CHECK (sender_identity ~ '^[1-9][0-9]{6,14}$'),
    tenant_id text NOT NULL CHECK (length(trim(tenant_id)) > 0),
    workspace_id uuid NOT NULL REFERENCES core_workspaces(id),
    user_id uuid NOT NULL REFERENCES core_users(id),
    verification_status text NOT NULL DEFAULT 'pending'
        CHECK (verification_status IN ('pending','verified','revoked')),
    verified_at_utc timestamptz,
    verification_ref text,
    revoked_at_utc timestamptz,
    actor_user_id uuid NOT NULL REFERENCES core_users(id),
    created_at_utc timestamptz NOT NULL DEFAULT now(),
    updated_at_utc timestamptz NOT NULL DEFAULT now(),
    UNIQUE (environment,provider,sender_identity,tenant_id,workspace_id),
    CHECK (verification_status <> 'verified' OR
        (verified_at_utc IS NOT NULL AND revoked_at_utc IS NULL AND
         verification_ref IS NOT NULL AND length(trim(verification_ref)) > 0)),
    CHECK ((verification_status = 'revoked') = (revoked_at_utc IS NOT NULL))
);
-- One stable row per scope, including tombstones: revoked is never anonymous.
-- Proof references must be opaque administrative references, not PII or secrets.
CREATE FUNCTION messaging_phone_binding_audit() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'Revoke telephone bindings instead of deleting them';
    END IF;
    IF NEW.verification_status <> 'revoked' AND NOT EXISTS (
        SELECT 1 FROM core_users WHERE id=NEW.user_id
        AND workspace_id=NEW.workspace_id AND status IN ('active','testing')) THEN
        RAISE EXCEPTION 'Telephone binding user/workspace invalid';
    END IF;
    IF TG_OP = 'UPDATE' THEN
        IF ROW(NEW.id,NEW.environment,NEW.provider,NEW.sender_identity,NEW.tenant_id,
               NEW.workspace_id,NEW.user_id,NEW.created_at_utc)
           IS DISTINCT FROM
           ROW(OLD.id,OLD.environment,OLD.provider,OLD.sender_identity,OLD.tenant_id,
               OLD.workspace_id,OLD.user_id,OLD.created_at_utc) THEN
            RAISE EXCEPTION 'Telephone binding scope is immutable';
        END IF;
    END IF;
    NEW.updated_at_utc := clock_timestamp();
    INSERT INTO core_events(workspace_id,actor_user_id,event_name,entity_type,entity_id,payload_jsonb)
    VALUES (NEW.workspace_id,NEW.actor_user_id,'messaging.phone_binding.' || lower(TG_OP),
            'messaging_phone_binding',NEW.id,
            jsonb_build_object('environment',NEW.environment,'provider',NEW.provider,
                'verification_status',NEW.verification_status));
    RETURN NEW;
END $$;
CREATE TRIGGER messaging_phone_binding_audit
BEFORE INSERT OR UPDATE OR DELETE ON messaging_phone_bindings
FOR EACH ROW EXECUTE FUNCTION messaging_phone_binding_audit();
REVOKE ALL ON messaging_phone_bindings FROM PUBLIC;
COMMIT;
-- Rollback (isolated tests / separately authorized administration only):
-- BEGIN;
-- DROP TABLE messaging_phone_bindings;
-- DROP FUNCTION messaging_phone_binding_audit();
-- COMMIT;
