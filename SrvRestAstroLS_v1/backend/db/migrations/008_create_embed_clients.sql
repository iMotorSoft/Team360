-- Team360 migration 008 — embed_clients table for multi-client embed support.
-- Associates each client_id with a context (assistant_instance, organization,
-- workspace, package, knowledge_scope), an HMAC secret for request signing,
-- and a list of allowed origins for Origin validation.
--
-- Architecture invariant: PostgreSQL is the source of truth for client
-- authorisation. No embed client configuration is stored in code.
--
-- Depends on migrations 001 through 007.
-- This migration does NOT insert any real secrets.
-- Seeds for local/integration testing are in a separate file.

-- ---------------------------------------------------------------------------
-- 1. embed_clients
-- ---------------------------------------------------------------------------

create table if not exists embed_clients (
    id                      bigserial       primary key,
    client_id               text            not null,
    hmac_secret             text            not null,
    assistant_instance_code text            not null,
    organization_code       text            not null,
    workspace_code          text            not null,
    package_code            text            not null,
    knowledge_scope_code    text            not null,
    allowed_origins         jsonb           not null default '[]'::jsonb,
    is_active               boolean         not null default true,
    label                   text,
    metadata_jsonb          jsonb           not null default '{}'::jsonb,
    created_at_utc          timestamptz     not null default now(),
    updated_at_utc          timestamptz     not null default now(),
    constraint chk_ec_client_id_not_empty
        check (length(client_id) > 0),
    constraint chk_ec_hmac_secret_not_empty
        check (length(hmac_secret) > 0),
    constraint chk_ec_allowed_origins_is_array
        check (jsonb_typeof(allowed_origins) = 'array'::text),
    constraint chk_ec_metadata_jsonb_is_object
        check (jsonb_typeof(metadata_jsonb) = 'object'::text)
);

comment on table embed_clients is
    'Authorised embed clients for public diagnosis. '
    'Each client has a fixed context and allowed origins for Origin validation. '
    'HMAC secret is stored in plaintext for signature verification (v1). '
    'Future: migrate to vault / encrypted storage / rotation.';

comment on column embed_clients.client_id is
    'Public identifier for the embed client. Sent in request body.';

comment on column embed_clients.hmac_secret is
    'Shared secret used to verify HMAC-SHA256 signatures. '
    'Debt: stored in plaintext, needs vault/rotation in future phase.';

comment on column embed_clients.allowed_origins is
    'JSON array of allowed Origin header values, e.g. '
    '["https://cliente.com", "https://app.cliente.com"].';

comment on column embed_clients.metadata_jsonb is
    'Operational metadata for the embed client. Must not contain secrets.';

-- ---------------------------------------------------------------------------
-- 2. Unique constraint and indexes
-- ---------------------------------------------------------------------------

create unique index if not exists idx_ec_client_id
    on embed_clients (client_id);

create index if not exists idx_ec_is_active
    on embed_clients (is_active)
    where is_active = true;
