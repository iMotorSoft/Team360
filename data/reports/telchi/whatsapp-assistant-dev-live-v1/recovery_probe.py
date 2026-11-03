"""Recovery evidence: read-only PG/Meta/Evolution inspection, no sends or DDL.
Run from backend using existing venv. Outputs only explicit safe summaries.
"""
import asyncio
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, parse_qsl, urlencode

import httpx
import psycopg
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.rows import dict_row
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent


def digest(value):
    return hashlib.sha256(str(value).encode()).hexdigest()


async def main():
    output = ROOT / sys.argv[1]
    if output.exists() or output.parent != ROOT:
        raise SystemExit('Refusing overwrite or external output')
    for k, v in dotenv_values('../.env.backend-dev.local').items():
        if v is not None:
            os.environ[k] = v
    c = json.loads(subprocess.check_output(['podman', 'inspect', 'evolution-api']))[0]
    env = dict(v.split('=', 1) for v in c['Config']['Env'] if '=' in v)
    result = {'timestamp': datetime.now(timezone.utc).isoformat(), 'read_only': True,
              'container': {'id': c['Id'], 'state': c['State']['Status'],
                            'exit_code': c['State']['ExitCode'], 'image': c['ImageName'],
                            'finished_at': c['State']['FinishedAt']}}
    uri = urlparse(env['DATABASE_CONNECTION_URI'])
    uri = uri._replace(query=urlencode([(k,v) for k,v in parse_qsl(uri.query) if k != 'schema']))
    dsn = conninfo_to_dict(uri.geturl())
    dsn.update(host='127.0.0.1')
    opts = '-c default_transaction_read_only=on -c statement_timeout=5000'
    async with await psycopg.AsyncConnection.connect(make_conninfo(**dsn), connect_timeout=5,
            options=opts, row_factory=dict_row, application_name='telchi-evolution-recovery-readonly') as conn:
        async def query(sql, params=None):
            return await (await conn.execute(sql, params)).fetchall()
        result['evolution_database'] = (await query("SELECT current_database() AS database,current_user AS role,current_setting('server_version') AS version,current_setting('transaction_read_only') AS read_only"))[0]
        result['evolution_migrations'] = (await query('SELECT count(*) AS total,count(*) FILTER (WHERE finished_at IS NULL AND rolled_back_at IS NULL) AS unfinished FROM evolution_api._prisma_migrations'))[0]
        result['evolution_tables'] = await query("SELECT tablename FROM pg_tables WHERE schemaname='evolution_api' ORDER BY tablename")
        rows = await query('SELECT id,name,"integration","connectionStatus" FROM evolution_api."Instance" ORDER BY name')
        result['instances'] = [{'id_hash': digest(r['id']), 'name': r['name'], 'integration': r['integration'], 'connection_status': r['connectionStatus']} for r in rows]
        result['evolution_message_counts'] = (await query('SELECT (SELECT count(*) FROM evolution_api."Message") AS messages,(SELECT count(*) FROM evolution_api."MessageUpdate") AS updates'))[0]
    from modules.db.settings import get_database_settings
    settings = get_database_settings()
    u = urlparse(settings.dsn)
    result['team360_target'] = {'host': u.hostname, 'port': u.port, 'database': u.path.lstrip('/'), 'exclusive_dev_attested': False}
    async with await psycopg.AsyncConnection.connect(settings.dsn, connect_timeout=5, options=opts,
            row_factory=dict_row, application_name='telchi-team360-recovery-readonly') as conn:
        async def query(sql, params=None):
            return await (await conn.execute(sql, params)).fetchall()
        result['database_inventory'] = await query("SELECT datname,pg_get_userbyid(datdba) AS owner FROM pg_database WHERE datallowconn AND NOT datistemplate ORDER BY datname")
        result['database_activity'] = await query("SELECT datname,application_name,client_addr::text AS client_addr,state,count(*) AS n FROM pg_stat_activity WHERE backend_type='client backend' GROUP BY 1,2,3,4 ORDER BY 1,2")
        result['team360_schema'] = await query("SELECT schemaname,tablename FROM pg_tables WHERE tablename ILIKE '%migration%' OR tablename='messaging_phone_bindings' ORDER BY 1,2")
        result['team360_roles'] = await query("SELECT rolname,rolsuper,rolcreatedb,rolcreaterole FROM pg_roles WHERE rolname ILIKE '%team360%' OR rolname='evolution_api' ORDER BY rolname")
        from modules.messaging.repository import MessagingRepository
        b = await MessagingRepository().binding(conn,workspace_slug=os.environ['TEAM360_MESSAGING_WORKSPACE_SLUG'],channel_alias=os.environ['TEAM360_MESSAGING_CHANNEL_ALIAS'],provider='evolution',instance=os.environ['TEAM360_EVOLUTION_INSTANCE'])
        result['channel'] = {k: getattr(b,k) for k in ('environment','module','tenant_id','receiver_context')}
        result['permission_codes'] = await query('SELECT permission_code FROM core_permissions ORDER BY permission_code')
        result['identity_counts'] = await query('SELECT status,count(*) AS n FROM core_users GROUP BY status')
    async with httpx.AsyncClient(timeout=10, trust_env=False, follow_redirects=False) as api:
        result['evolution_api'] = {}
        base = os.environ['TEAM360_EVOLUTION_BASE_URL'].rstrip('/')
        result['endpoint_matches_port'] = urlparse(base).port == 18180
        for label, path in [('health','/'),('connection','/instance/connectionState/team360-meta-dev'),('webhook','/webhook/find/team360-meta-dev')]:
            try:
                r = await api.get(base+path, headers={'apikey': env['AUTHENTICATION_API_KEY']})
                info = {'http_status': r.status_code}
                if r.is_success:
                    data = r.json()
                    if label == 'connection':
                        info['state'] = (data.get('instance') or {}).get('state')
                    elif label == 'health':
                        info['version'] = data.get('version')
                    else:
                        data = data.get('webhook',data)
                        info.update(enabled=data.get('enabled'),events=data.get('events'),url_present=bool(data.get('url')),header_configured='x-team360-webhook-token' in (data.get('headers') or {}))
                result['evolution_api'][label] = info
            except Exception as exc:
                result['evolution_api'][label] = {'error_type':type(exc).__name__}
        graph = 'https://graph.facebook.com/'+os.getenv('META_TEAM360_GRAPH_VERSION','v23.0')
        app = os.environ['META_TEAM360_APP_ID']
        waba = os.environ['META_TEAM360_WABA_ID']
        token = os.environ['META_TEAM360_WABA_TOKEN']
        app_token = app+'|'+os.environ['META_TEAM360_APP_SECRET']
        result['meta'] = {'app_id_hash':digest(app),'waba_id_hash':digest(waba)}
        for label, path, auth, params in [
            ('app',app,app_token,{'fields':'id,name'}),
            ('subscriptions',app+'/subscriptions',app_token,None),
            ('waba_subscribed_apps',waba+'/subscribed_apps',token,None),
            ('phone',os.environ['META_TEAM360_PHONE_NUMBER_ID'],token,{'fields':'id,code_verification_status,platform_type'}),
            ('token_debug','debug_token',app_token,{'input_token':token})]:
            try:
                r = await api.get(graph+'/'+path,headers={'Authorization':'Bearer '+auth},params=params)
                data = r.json()
                info = {'http_status':r.status_code}
                if r.is_success:
                    if label == 'app':
                        info.update(name=data.get('name'),matches_configured_app=str(data.get('id'))==app)
                    elif label == 'subscriptions':
                        entries=data.get('data',[])
                        info.update(entry_count=len(entries),pagination=bool((data.get('paging') or {}).get('next')),whatsapp_active=any(e.get('object')=='whatsapp_business_account' and e.get('active') is True for e in entries))
                    elif label == 'waba_subscribed_apps':
                        entries=data.get('data',[])
                        info.update(entry_count=len(entries),pagination=bool((data.get('paging') or {}).get('next')),configured_app_present=any(str((e.get('whatsapp_business_api_data') or {}).get('id'))==app for e in entries))
                    elif label == 'phone':
                        info.update(verification=data.get('code_verification_status'),platform=data.get('platform_type'))
                    else:
                        d=data.get('data',{})
                        info.update(valid=d.get('is_valid'),app_matches=str(d.get('app_id'))==app,expires_at=d.get('expires_at'),data_access_expires_at=d.get('data_access_expires_at'),scopes=d.get('scopes'))
                else:
                    info['error_code']=(data.get('error') or {}).get('code')
                result['meta'][label]=info
            except Exception as exc:
                result['meta'][label]={'error_type':type(exc).__name__}
    output.write_text(json.dumps(result,indent=2,default=str)+'\n')
    print('Evidence written:',output.name)


if __name__=='__main__':
    asyncio.run(main())
