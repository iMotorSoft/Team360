"""Read-only sanitized live PG evidence; no telephone or business rows emitted."""
import asyncio,hashlib,json,os,sys
from pathlib import Path
from datetime import datetime,timezone
from dotenv import dotenv_values
import psycopg
from psycopg.rows import dict_row
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(Path.cwd()))
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,default=str).encode()).hexdigest()
async def main():
    for k,v in dotenv_values('../.env.backend-dev.local').items():
        if v is not None:os.environ[k]=v
    from modules.db.settings import get_database_settings
    from modules.messaging.repository import MessagingRepository
    from modules.console.repositories import PermissionConsoleRepository
    identity=json.loads((ROOT/'binding-phone-applied.json').read_text())
    async with await psycopg.AsyncConnection.connect(get_database_settings().dsn,row_factory=dict_row,options='-c default_transaction_read_only=on -c statement_timeout=5000') as c:
        repo=MessagingRepository();b=await repo.binding(c,workspace_slug='telchi_dev',channel_alias='telchi_whatsapp_dev',provider='evolution',instance='team360-meta-dev')
        rows=await repo.evidence(c,b)
        events=[]
        for row in rows:
            payload=row['payload_jsonb'];a=payload.get('telchi_assistant_v1') or {};r=a.get('execution_result') or {};p=a.get('response_prepared') or {};dispatch=payload.get('dispatch_result') or {}
            e={k:str(row[k]) if row[k] is not None else None for k in ('id','thread_id','correlation_id','direction','event_type','status','transport_status','occurred_at_utc')}
            e.update(provider_message_id_hash=digest(row['provider_message_id']),processing_state=payload.get('processing_state'),classification=dispatch.get('classification') or p.get('classification'),committed=a.get('committed'),decision=a.get('decision'),execution_status=a.get('execution_status'),capability=r.get('capability'),foundation_source=r.get('source'),result_hash=digest(r['rows']) if 'rows' in r else None,state_hash=digest(a['confirmed_state']) if 'confirmed_state' in a else None,previous_state_hash=digest(a['previous_state']) if 'previous_state' in a else None,timings=a.get('timings') or payload.get('timings'),outbound_initial_result=payload.get('initial_result'),delivered_at_ms=payload.get('t6_ms'),response_hash=digest(p.get('text') or dispatch.get('text') or payload.get('text')))
            if a.get('owner'):e['identity_matches_pilot']=a['owner'][-1]==identity['user_id']
            if row['direction']=='outbound' and row['event_type']=='message':
                e['delivery_evidence']='DELIVERED' if row['transport_status'] in ('delivered','read') else ('PROVIDER_ACCEPTED' if payload.get('initial_result')=='accepted' else 'NOT_CONFIRMED')
                e['device_received']='AWAITING_OPERATOR_CONFIRMATION'
            events.append(e)
        threads=await (await c.execute('SELECT id,metadata_jsonb FROM message_threads WHERE channel_id=%s AND provider_instance=%s',(b.channel_id,b.storage_instance))).fetchall()
        saved=[{'thread_id':str(t['id']),'durable_state_present':'telchi_assistant_v1' in t['metadata_jsonb'],'history_order':t['metadata_jsonb'].get('telchi_assistant_v1',{}).get('history_order',[]),'state_hash':digest(t['metadata_jsonb'].get('telchi_assistant_v1',{}).get('state'))} for t in threads]
        permissions=sorted(await PermissionConsoleRepository().list_effective_permissions(c,b.workspace_id,identity['user_id']))
    result={'observed_at':datetime.now(timezone.utc).isoformat(),'read_only':True,'channel_id':b.channel_id,'routing':'horizontal_v1','environment':'dev','pilot_permissions':permissions,'events':events,'conversations':saved}
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');path=ROOT/('binding-live-observation-'+stamp+'.json');path.write_text(json.dumps(result,indent=2)+'\n');(ROOT/'binding-live-latest.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
if __name__=='__main__':asyncio.run(main())
