-- Team360 seed: mamamia360 embed client for controlled pilot.
--
-- Run manually after migration 008:
--   psql -d team360 -f 009_seed_mamamia360_embed_client.sql
--
-- WARNING: Replace hmac_secret with a real secret before production.
-- Never commit real secrets to the repository.

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
    'mamamia360',
    'mamamia360-embed-secret-change-in-production',
    'team360_sales_diagnosis',
    'team360_live',
    'team360_public_site',
    'pkg_sales_diagnosis',
    'ks_team360_sales_diagnosis',
    '["http://127.0.0.1:3050", "http://localhost:3050", "https://mamamia360.com", "https://www.mamamia360.com", "https://team360.live"]'::jsonb,
    true,
    'Mamamia360 distribuidor piloto - Diagnosticador Vera embebible'
) on conflict (client_id) do nothing;
