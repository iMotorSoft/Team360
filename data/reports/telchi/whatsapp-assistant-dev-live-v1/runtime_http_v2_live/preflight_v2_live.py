"""Read-only Phase A/D preflight for the WhatsApp live retest V2.

No secrets or telephone values are written to disk. Evolution and Meta are
queried read-only; PostgreSQL is opened with default_transaction_read_only.
"""
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path('/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/SrvRestAstroLS_v1/backend')))
from dotenv import dotenv_values  # noqa: E402

ROOT = Path(__file__).resolve().parent
BACKEND = Path('/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/SrvRestAstroLS_v1/backend')


async def main():
    for k, v in dotenv_values(str(BACKEND.parent / '.env.backend-dev.local')).items():
        if v is not None:
            os.environ[k] = v
    os.environ.update(TEAM360_ENV='dev', TEAM360_MESSAGING_DEV_ENABLED='1',
                      TEAM360_MESSAGING_DISPATCH_MODE='horizontal_v1',
                      TEAM360_MESSAGING_WORKSPACE_SLUG='telchi_dev',
                      TEAM360_MESSAGING_CHANNEL_ALIAS='telchi_whatsapp_dev',
                      TEAM360_SRV05_EVOLUTION_ENABLED='1')
    import httpx
    import psycopg
    from psycopg.rows import dict_row
    from modules.db.settings import get_database_settings
    from modules.console.repositories import PermissionConsoleRepository
    from modules.messaging.providers.evolution.config import EvolutionConfig

    result = {'timestamp': datetime.now(timezone.utc).isoformat(), 'read_only': True}
    async with await psycopg.AsyncConnection.connect(
            get_database_settings().dsn, row_factory=dict_row,
            options='-c default_transaction_read_only=on -c statement_timeout=5000') as c:
        async def q(sql, p=None):
            return await (await c.execute(sql, p)).fetchall()
        result['database'] = await q("SELECT current_database() AS database, current_setting('server_version') AS version")
        result['workspace'] = await q(
            "SELECT w.id, w.slug, w.status, o.organization_code FROM core_workspaces w "
            "JOIN core_organizations o ON o.id=w.organization_id WHERE o.organization_code='telchi'")
        users = await q("SELECT id, workspace_id, email, status FROM core_users "
                        "WHERE email IN ('devfull@telchiai.com','admin@telchiai.com') ORDER BY email")
        for u in users:
            u['permissions'] = sorted(await PermissionConsoleRepository().list_effective_permissions(
                c, str(u['workspace_id']), str(u['id'])))
        result['users'] = users
        result['permission_scope'] = await q(
            "SELECT permission_code, description FROM core_permissions "
            "WHERE permission_code='telchi.sales.source_quantity.read.v1'")
        result['phone_binding'] = await q(
            "SELECT environment, provider, tenant_id, user_id, verification_status, "
            "verified_at_utc IS NOT NULL AS verified, revoked_at_utc IS NULL AS active "
            "FROM messaging_phone_bindings WHERE environment='dev' AND provider='evolution' "
            "AND tenant_id='telchi' AND verification_status='verified' AND revoked_at_utc IS NULL")
        result['channel'] = await q(
            "SELECT w.slug, c.channel_alias, c.status, c.metadata_jsonb->>'provider_instance' AS provider_instance, "
            "c.metadata_jsonb->>'dispatch_mode' AS dispatch_mode, c.metadata_jsonb->>'runner_context' AS runner_context, "
            "c.metadata_jsonb->>'provider' AS provider, (c.metadata_jsonb->>'receiver_context') IS NOT NULL AS receiver_set "
            "FROM communication_channels c JOIN core_workspaces w ON w.id=c.workspace_id "
            "JOIN communication_providers p ON p.id=c.provider_id "
            "WHERE w.slug='telchi_dev' AND c.channel_alias='telchi_whatsapp_dev'")
        result['transport_indexes'] = await q(
            "SELECT indexname FROM pg_indexes WHERE indexname LIKE 'uq_messaging_transport_%' ORDER BY indexname")
        result['threads_count'] = await q("SELECT count(*) AS n FROM message_threads")

    config = EvolutionConfig.from_env()
    result['evolution_config'] = {'base_url': config.base_url, 'instance': config.instance}
    async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
        for label, path in [('connection', '/instance/connectionState/'), ('webhook', '/webhook/find/')]:
            try:
                r = await client.get(config.base_url + path + config.instance, headers={'apikey': config.api_key})
                d = r.json()
                if label == 'connection':
                    result[label] = {'status': r.status_code, 'state': d.get('instance', {}).get('state')}
                else:
                    d = d.get('webhook', d)
                    result[label] = {'status': r.status_code, 'enabled': d.get('enabled'),
                                     'events': d.get('events'), 'url_configured': bool(d.get('url'))}
            except Exception as exc:  # noqa: BLE001
                result[label] = {'error_type': type(exc).__name__}
        try:
            r = await client.get(
                'https://graph.facebook.com/' + os.getenv('META_TEAM360_GRAPH_VERSION', 'v20.0')
                + '/' + os.environ['META_TEAM360_PHONE_NUMBER_ID'],
                headers={'Authorization': 'Bearer ' + os.environ['META_TEAM360_WABA_TOKEN']},
                params={'fields': 'id,display_phone_number,code_verification_status,platform_type'})
            result['receiver'] = {'status': r.status_code}
            if r.is_success:
                d = r.json()
                result['receiver'].update(id_matches=str(d['id']) == os.environ['META_TEAM360_PHONE_NUMBER_ID'],
                                          verified=d.get('code_verification_status'),
                                          platform=d.get('platform_type'))
        except Exception as exc:  # noqa: BLE001
            result['receiver'] = {'error_type': type(exc).__name__}

    (ROOT / 'preflight_v2_live.json').write_text(json.dumps(result, indent=2, default=str) + '\n')
    print(json.dumps(result, indent=2, default=str))


if __name__ == '__main__':
    asyncio.run(main())