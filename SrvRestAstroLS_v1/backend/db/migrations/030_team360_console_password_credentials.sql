-- Additive Console DEV enrollment/login storage. Apply only to verified DEV.
-- Credentials never live in core_users.metadata_jsonb or audit payloads.
CREATE TABLE console_password_credentials (
    user_id uuid PRIMARY KEY REFERENCES core_users(id) ON DELETE RESTRICT,
    password_hash text NOT NULL CHECK (password_hash LIKE 'scrypt$131072$8$1$%'),
    credential_version integer NOT NULL DEFAULT 1 CHECK (credential_version > 0),
    disabled boolean NOT NULL DEFAULT false,
    updated_at_utc timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE console_login_attempts (
    account_key text PRIMARY KEY CHECK (length(account_key) = 64),
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    window_started_at_utc timestamptz NOT NULL DEFAULT now()
);
-- Role/grants are deliberately provisioned separately by explicit DEV tooling.
REVOKE ALL ON console_password_credentials, console_login_attempts FROM PUBLIC;
