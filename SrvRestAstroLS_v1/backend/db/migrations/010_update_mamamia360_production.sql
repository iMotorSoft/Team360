-- Team360 production update: mamamia360 embed client production configuration.
--
-- Run manually on production PostgreSQL after migration 008 and 009:
--   psql -d team360 -f 010_update_mamamia360_production.sql
--
-- WARNING:
--   1. This file contains a PLACEHOLDER secret. The operator MUST replace
--      'MAMAMIA360_HMAC_SECRET_REPLACE_IN_PRODUCTION' with the real secret
--      provided by the Team360 security team before executing.
--   2. Never log, print or store the real secret in the repository.
--   3. The SHA-256 fingerprint of the production secret can be verified
--      against the deployment checklist.
--
-- Changes from seed 009:
--   - Added https://www.mamamia360.com to allowed_origins
--   - Replaced placeholder HMAC secret with production secret
--   - Updated label to reflect production status

update embed_clients
set
    allowed_origins = '[
        "http://127.0.0.1:3050",
        "http://localhost:3050",
        "https://mamamia360.com",
        "https://www.mamamia360.com"
    ]'::jsonb,
    hmac_secret = 'MAMAMIA360_HMAC_SECRET_REPLACE_IN_PRODUCTION',
    label = 'Mamamia360 distribuidor piloto - PRODUCCION - Diagnosticador Vera embebible',
    updated_at_utc = now()
where client_id = 'mamamia360';
