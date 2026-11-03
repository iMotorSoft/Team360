"""Bounded read-only DEV inspection; no secrets or telephone values in output."""
import asyncio, json, os
from pathlib import Path
from datetime import datetime, timezone
from dotenv import dotenv_values
import psycopg
from psycopg.rows import dict_row
import httpx

ROOT=Path(__file__).resolve().parent
async def main():
    for k,v in dotenv_values('../.env.backend-dev.local').items():
        if v is not None: os.environ[k]=v
    from modules.db.settings import get_database_settings
    from modules.console.repositories import PermissionConsoleRepository
    from modules.messaging.providers.evolution.config import EvolutionConfig
    result={'timestamp':datetime.now(timezone.utc).isoformat()}
    async with await psycopg.AsyncConnection.connect(get_database_settings().dsn,row_factory=dict_row,options='-c default_transaction_read_only=on -c statement_timeout=5000') as c:
        async def q(s,p=None): return await (await c.execute(s,p)).fetchall()
        result['database']=await q('SELECT current_database() AS database,current_setting(\'server_version\') AS version')
        result['workspace']=await q("SELECT w.id,w.slug,w.status,o.id AS organization_id,o.organization_code,o.status AS organization_status FROM core_workspaces w JOIN core_organizations o ON o.id=w.organization_id WHERE o.organization_code='telchi'")
        result['users']=await q("SELECT id,workspace_id,email,status FROM core_users WHERE email IN ('devfull@telchiai.com','admin@telchiai.com') ORDER BY email")
        for u in result['users']:
            u['permissions']=sorted(await PermissionConsoleRepository().list_effective_permissions(c,str(u['workspace_id']),str(u['id'])))
        result['permission_scope']=await q("SELECT permission_code,description FROM core_permissions WHERE permission_code='telchi.sales.source_quantity.read.v1'")
        result['migration_objects']=await q("SELECT to_regclass('public.messaging_phone_bindings') AS phone_table,to_regprocedure('public.messaging_phone_binding_audit()') AS audit_function")
        result['dependencies']=await q("SELECT name,to_regclass(name) AS object FROM unnest(ARRAY['core_users','core_workspaces','core_events','communication_providers']) AS name")
        result['channels']=await q("SELECT c.id,w.slug,c.channel_alias,c.status,c.metadata_jsonb - 'receiver_context' AS metadata FROM communication_channels c JOIN core_workspaces w ON w.id=c.workspace_id JOIN communication_providers p ON p.id=c.provider_id WHERE p.code='evolution'")
        result['transport_indexes']=await q("SELECT indexname FROM pg_indexes WHERE indexname LIKE 'uq_messaging_transport_%'")
        result['flow_settings']=await q("SELECT automation_enabled FROM flow_operational_settings")
    config=EvolutionConfig.from_env()
    async with httpx.AsyncClient(timeout=15,trust_env=False) as client:
        for label,path in [('connection','/instance/connectionState/'),('webhook','/webhook/find/')]:
            r=await client.get(config.base_url+path+config.instance,headers={'apikey':config.api_key}); r.raise_for_status(); d=r.json()
            if label=='connection': result[label]={'status':r.status_code,'state':d.get('instance',{}).get('state'),'instance':config.instance}
            else:
                d=d.get('webhook',d);result[label]={'enabled':d.get('enabled'),'events':d.get('events'),'url_configured':bool(d.get('url'))}
        r=await client.get('https://graph.facebook.com/'+os.getenv('META_TEAM360_GRAPH_VERSION','v20.0')+'/'+os.environ['META_TEAM360_PHONE_NUMBER_ID'],headers={'Authorization':'Bearer '+os.environ['META_TEAM360_WABA_TOKEN']},params={'fields':'id,display_phone_number,code_verification_status,platform_type'})
        result['receiver']={'status':r.status_code}
        if r.is_success:
            d=r.json(); result['receiver'].update(id_matches=str(d['id'])==os.environ['META_TEAM360_PHONE_NUMBER_ID'],verified=d.get('code_verification_status'),platform=d.get('platform_type'))
            private=Path('/media/issajar/DEVELOP/Projects/iMotorSoft/ai/private/telchi/whatsapp-live-v1');private.mkdir(mode=0o700,exist_ok=True)
            path=private/'receiver.json'; fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
            with os.fdopen(fd,'w') as f: json.dump(d,f)
    (ROOT/'binding-preflight.json').write_text(json.dumps(result,indent=2,default=str)+'\n')
    print(json.dumps(result,indent=2,default=str))
if __name__=='__main__': asyncio.run(main())
