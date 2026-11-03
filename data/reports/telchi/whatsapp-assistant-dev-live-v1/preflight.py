"""Read-only operational inspection. Run from backend with its existing venv.
No startup, DDL, enrollment, subscription changes or message sends.
Only allowlisted summaries are written; exception bodies/URLs are never logged.
"""
import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx
import psycopg
from psycopg.rows import dict_row
from dotenv import dotenv_values

OUTPUT = Path(__file__).resolve().parent / 'preflight-r2.json'


async def main():
    if OUTPUT.exists():
        raise SystemExit('Refusing to overwrite evidence')
    for key, value in dotenv_values('../.env.backend-dev.local').items():
        if value is not None:
            os.environ[key] = value
    result = {'timestamp': datetime.now(timezone.utc).isoformat(), 'read_only': True}
    result['config'] = {k: os.getenv(k) for k in (
        'TEAM360_ENV', 'TEAM360_SRV05_EVOLUTION_ENABLED',
        'TEAM360_MESSAGING_DEV_ENABLED', 'TEAM360_MESSAGING_DISPATCH_MODE',
        'TEAM360_MESSAGING_WORKSPACE_SLUG', 'TEAM360_MESSAGING_CHANNEL_ALIAS',
        'TEAM360_EVOLUTION_INSTANCE', 'AUTOMATION_DIAGNOSIS_REPOSITORY')}
    from modules.telchi.assistant.luna import CREDENTIAL_ENV
    result['luna_credential_present'] = bool(os.getenv(CREDENTIAL_ENV))
    from modules.db.settings import get_database_settings
    try:
        settings = get_database_settings()
        parsed = urlparse(settings.dsn)
        result['database_target'] = {'host': parsed.hostname, 'port': parsed.port,
                                     'database': parsed.path.lstrip('/'),
                                     'dev_exclusivity_attested': False}
        async with await psycopg.AsyncConnection.connect(
                settings.dsn, connect_timeout=5, row_factory=dict_row,
                options='-c default_transaction_read_only=on -c statement_timeout=5000',
                application_name='telchi-dev-live-readonly-preflight') as conn:
            async def query(sql, params=()):
                return await (await conn.execute(sql, params or None)).fetchall()
            result['database'] = (await query("SELECT current_database() AS database, current_setting('server_version') AS version, current_setting('transaction_read_only') AS read_only"))[0]
            result['schema'] = await query("SELECT tablename FROM pg_tables WHERE schemaname=current_schema() AND (tablename LIKE '%migration%' OR tablename IN ('messaging_phone_bindings','communication_channels','core_users','core_permissions')) ORDER BY tablename")
            result['transport_indexes'] = await query("SELECT indexname FROM pg_indexes WHERE schemaname=current_schema() AND indexname LIKE 'uq_messaging_transport_%' ORDER BY indexname")
            from modules.messaging.repository import MessagingRepository
            try:
                binding = await MessagingRepository().binding(conn,
                    workspace_slug=os.environ['TEAM360_MESSAGING_WORKSPACE_SLUG'],
                    channel_alias=os.environ['TEAM360_MESSAGING_CHANNEL_ALIAS'],
                    provider='evolution', instance=os.environ['TEAM360_EVOLUTION_INSTANCE'])
                result['channel'] = {k: getattr(binding, k) for k in ('workspace_id', 'channel_id', 'environment', 'module', 'tenant_id', 'receiver_context')}
            except Exception as exc:
                result['channel'] = {'error_type': type(exc).__name__}
            result['business_permission_candidates'] = await query("SELECT permission_code FROM core_permissions WHERE permission_code ILIKE '%telchi%' OR permission_code ILIKE '%sales%' OR permission_code ILIKE '%business%' ORDER BY permission_code")
            if any(r['tablename'] == 'messaging_phone_bindings' for r in result['schema']):
                result['binding_counts'] = await query("SELECT environment,verification_status,count(*) AS n FROM messaging_phone_bindings GROUP BY environment,verification_status")
    except Exception as exc:
        result['database_error_type'] = type(exc).__name__
    from modules.messaging.providers.evolution.config import EvolutionConfig
    async with httpx.AsyncClient(timeout=10, trust_env=False, follow_redirects=False) as client:
        try:
            config = EvolutionConfig.from_env()
            result['evolution'] = {}
            for label, endpoint in (
                    ('connection', f'/instance/connectionState/{config.instance}'),
                    ('webhook', f'/webhook/find/{config.instance}')):
                response = await client.get(config.base_url + endpoint, headers={'apikey': config.api_key})
                info = {'http_status': response.status_code}
                if response.is_success:
                    data = response.json()
                    if label == 'connection':
                        info['state'] = (data.get('instance') or {}).get('state')
                    else:
                        data = data.get('webhook', data)
                        info.update(enabled=data.get('enabled'), events=data.get('events'),
                                    callback_configured=bool(data.get('url')),
                                    private_header_configured='x-team360-webhook-token' in (data.get('headers') or {}))
                result['evolution'][label] = info
        except Exception as exc:
            result['evolution_error_type'] = type(exc).__name__
        token = os.getenv('META_TEAM360_WABA_TOKEN')
        version = os.getenv('META_TEAM360_GRAPH_VERSION', 'v23.0')
        if token:
            result['meta'] = {}
            for label, object_id, edge in (
                    ('waba_subscription', os.getenv('META_TEAM360_WABA_ID'), 'subscribed_apps'),
                    ('app_subscription', os.getenv('META_TEAM360_APP_ID'), 'subscriptions')):
                if not object_id:
                    continue
                try:
                    auth = token
                    if label == 'app_subscription':
                        secret = os.getenv('META_TEAM360_APP_SECRET')
                        if not secret:
                            result['meta'][label] = {'blocked': 'app_secret_missing'}
                            continue
                        auth = object_id + '|' + secret
                    response = await client.get(f'https://graph.facebook.com/{version}/{object_id}/{edge}', headers={'Authorization': 'Bearer ' + auth})
                    data = response.json()
                    info = {'http_status': response.status_code}
                    if response.is_success:
                        entries = data.get('data', [])
                        info['entry_count'] = len(entries)
                        info['pagination_present'] = bool((data.get('paging') or {}).get('next'))
                        if label == 'app_subscription':
                            info['whatsapp_active'] = any(e.get('object') == 'whatsapp_business_account' and e.get('active') is True for e in entries)
                        else:
                            info['team360_app_subscribed'] = any(str((e.get('whatsapp_business_api_data') or {}).get('id')) == os.getenv('META_TEAM360_APP_ID') for e in entries)
                    else:
                        info['graph_error_code'] = (data.get('error') or {}).get('code')
                    result['meta'][label] = info
                except Exception as exc:
                    result['meta'][label] = {'error_type': type(exc).__name__}
        else:
            result['meta'] = {'blocked': 'team360_waba_credential_missing'}
    OUTPUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    asyncio.run(main())
