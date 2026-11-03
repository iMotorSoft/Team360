-- Candidate additive migration, isolated rehearsal only; NOT authorized on active DBs.
-- 026 must already be recorded/applied. No UPDATE/backfill of message_events:
-- legacy sending + transport_status NULL remains uncertain and non-replayable.
-- Keep 026 immutable; rollback retains these tables and the V1 reconciler.
DO $$ BEGIN
    -- Catalog visibility must not depend on runtime SELECT grants. A dedicated
    -- additive DDL migrator does not need to read historical message contents.
    IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_attribute
        WHERE attrelid=pg_catalog.to_regclass('message_events')
          AND attname='transport_status' AND attnum>0 AND NOT attisdropped) THEN
        RAISE EXCEPTION 'transport evidence requires migration 026';
    END IF;
END $$;
CREATE TABLE ot_target (
    side text PRIMARY KEY CHECK (side IN ('team360','evolution')),
    target_id uuid NOT NULL UNIQUE,
    epoch uuid NOT NULL
);
CREATE TABLE ot_inventory (
    side text NOT NULL REFERENCES ot_target(side),
    binding_id uuid NOT NULL,
    scope jsonb NOT NULL,
    PRIMARY KEY (side,binding_id)
);
CREATE TABLE ot_revision (
    side text NOT NULL,
    binding_id uuid NOT NULL,
    revision integer NOT NULL CHECK (revision>0),
    scope jsonb NOT NULL,
    credential_hash text NOT NULL CHECK (credential_hash ~ '^[0-9a-f]{64}$'),
    state text NOT NULL CHECK (state IN ('prepared','active','revoked')),
    activation_id uuid,
    prepared_receipt jsonb NOT NULL,
    PRIMARY KEY (side,binding_id,revision),
    UNIQUE (side,credential_hash),
    FOREIGN KEY (side,binding_id) REFERENCES ot_inventory(side,binding_id)
);
CREATE UNIQUE INDEX ot_one_active ON ot_revision(side,binding_id) WHERE state='active';
CREATE TABLE ot_operation (
    side text NOT NULL REFERENCES ot_target(side),
    operation_id uuid NOT NULL,
    approver text NOT NULL,
    nonce uuid NOT NULL,
    envelope_hash text NOT NULL,
    envelope jsonb NOT NULL,
    receipt jsonb NOT NULL,
    applied_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (side,operation_id),
    UNIQUE (side,approver,nonce)
);
CREATE FUNCTION ot_audit_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'offline audit is append only'; END;
$$;
CREATE TRIGGER ot_audit_immutable BEFORE UPDATE OR DELETE ON ot_operation
FOR EACH ROW EXECUTE FUNCTION ot_audit_immutable();
CREATE TABLE ot_received_callback (
    event_id text PRIMARY KEY,
    envelope_hash text NOT NULL,
    payload jsonb NOT NULL,
    received_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
REVOKE ALL ON ot_target,ot_inventory,ot_revision,ot_operation,ot_received_callback FROM PUBLIC;
REVOKE ALL ON FUNCTION ot_audit_immutable() FROM PUBLIC;
-- Role names are deployment inputs, never created or auto-granted by this DDL.
-- Migrator: owns DDL; not a service login.
-- Catalog accreditor: INSERT/UPDATE ot_target,ot_inventory; independently controlled.
-- Offline provisioner: SELECT targets/inventory; SELECT/UPDATE inventory (row lock);
-- SELECT/INSERT/UPDATE revisions; SELECT/INSERT operations; no DELETE or TRUNCATE.
-- Sender runtime: SELECT targets/revisions; SELECT/UPDATE inventory (row lock).
-- Callback runtime: SELECT targets/revisions; SELECT/INSERT received_callback.
-- Both runtime paths additionally need existing scoped message_events privileges.
-- Auditor: SELECT only on evidence tables; no credentials or private key material.
-- Effective grants, ownership, absence of inherited privileges require a separate gate.
