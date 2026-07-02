-- Example seed for embed_clients (integration testing / local dev).
-- NOT applied automatically. Run manually only after migration 008.
--
-- Usage:
--   psql -d team360 -f 008_create_embed_clients_seed_example.sql
--
-- WARNING: Replace the hmac_secret values with real secrets for production.
-- Never commit real secrets to the repository.

-- Client for Team360 public demo (same context as Vera default)
-- hmac_secret placeholder: "embed-secret-key-change-in-production"
insert into embed_clients (
    client_id,
    hmac_secret,
    assistant_instance_code,
    organization_code,
    workspace_code,
    package_code,
    knowledge_scope_code,
    allowed_origins,
    is_active,
    label
) values (
    'demo_team360',
    'embed-secret-key-change-in-production',
    'team360_sales_diagnosis',
    'team360_live',
    'team360_public_site',
    'pkg_sales_diagnosis',
    'ks_team360_sales_diagnosis',
    '["http://localhost:3050", "https://team360.live"]'::jsonb,
    true,
    'Team360 public demo embed client'
) on conflict (client_id) do nothing;
