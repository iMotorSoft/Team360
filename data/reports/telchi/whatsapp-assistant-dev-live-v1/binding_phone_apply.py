"""Operator-confirmed fresh WhatsApp proof -> existing authorized DEV binding procedure."""
import asyncio,hashlib,json,os,subprocess,sys
from pathlib import Path
from datetime import datetime,timezone
from urllib.parse import urlparse,urlencode,parse_qsl
from uuid import uuid5,NAMESPACE_URL
from dotenv import dotenv_values
import psycopg
from psycopg.rows import dict_row
from psycopg.conninfo import conninfo_to_dict,make_conninfo
ROOT=Path(__file__).resolve().parent
PRIVATE=Path('/media/issajar/DEVELOP/Projects/iMotorSoft/ai/private/telchi/whatsapp-live-v1')
async def main():
    assert sys.argv[1:]==['--operator-confirmed-sent']
    for k,v in dotenv_values('../.env.backend-dev.local').items():
        if v is not None:os.environ[k]=v
    from modules.db.settings import get_database_settings
    from modules.messaging.identity import PhoneIdentityRepository
    from modules.messaging.handlers import ChannelContext
    from modules.messaging.repository import MessagingRepository
    from modules.telchi.provisioning.phone_binding import bind_verified_dev_phone
    session=json.loads((ROOT/'binding-active-session.json').read_text())
    observed=json.loads((ROOT/(session['run']+'-callback.json')).read_text())
    assert observed['proof_observed'] and observed['window_result']=='PROOF_PENDING_OPERATOR_CONFIRMATION'
    proof=json.loads((PRIVATE/'proof.json').read_text())
    sender=os.environ['TEAM360_MESSAGING_DEV_AUTHORIZED_SENDER']
    assert sender.endswith('6950') and proof['key']['remoteJid']==sender+'@s.whatsapp.net' and proof['key']['fromMe'] is False
    assert proof['messageTimestamp']>=int(datetime.fromisoformat(observed['window_start']).timestamp())
    assert (proof['message'].get('conversation') or proof['message'].get('extendedTextMessage',{}).get('text'))=='TELCHI DEV: soy devfull@telchiai.com y autorizo vincular esta linea para la prueba.'
    assert hashlib.sha256(str(proof['key'].get('id',proof['id'])).encode()).hexdigest()==observed['proof_message_id_hash']
    info=json.loads(subprocess.check_output(['podman','inspect','evolution-api']))[0];env=dict(x.split('=',1) for x in info['Config']['Env'] if '=' in x)
    u=urlparse(env['DATABASE_CONNECTION_URI']);u=u._replace(query=urlencode([(k,v) for k,v in parse_qsl(u.query) if k!='schema']));config=conninfo_to_dict(u.geturl());config['host']='127.0.0.1'
    async with await psycopg.AsyncConnection.connect(make_conninfo(**config),row_factory=dict_row,options='-c default_transaction_read_only=on -c statement_timeout=5000') as c:
        row=await (await c.execute('''SELECT m.id,m.key,m.message,m."messageTimestamp" FROM evolution_api."Message" m JOIN evolution_api."Instance" i ON i.id=m."instanceId" WHERE m.id=%s AND i.name='team360-meta-dev' ''',(proof['id'],))).fetchone()
        assert row==proof
    verification_ref='whatsapp-dev-proof:'+str(uuid5(NAMESPACE_URL,observed['proof_message_id_hash']))
    private_record=PRIVATE/'verification.json'
    fd=os.open(private_record,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,'w') as f:json.dump({'verification_ref':verification_ref,'proof_message_id_hash':observed['proof_message_id_hash'],'proof_timestamp':observed['proof_timestamp'],'operator_confirmation':'current user chat: enviado','identity':'devfull@telchiai.com','consent':'explicit message text plus owner confirmation','timestamp':datetime.now(timezone.utc).isoformat()},f,indent=2)
    initial=json.loads((ROOT/'binding-preflight.json').read_text());w=str(initial['workspace'][0]['id']);users={u['email']:str(u['id']) for u in initial['users']}
    dsn=get_database_settings().dsn;u=urlparse(dsn);assert u.hostname in ('localhost','127.0.0.1') and u.port==5432 and u.path=='/team360'
    async with await psycopg.AsyncConnection.connect(dsn,autocommit=True,row_factory=dict_row,application_name='telchi-dev-verified-phone-binding') as c:
        async with c.transaction():
            await c.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE; SET LOCAL lock_timeout='3s'; SET LOCAL statement_timeout='5s'")
            ident=await bind_verified_dev_phone(c,workspace_id=w,user_id=users['devfull@telchiai.com'],actor_user_id=users['admin@telchiai.com'],sender_identity=sender,verification_ref=verification_ref,consent_verified=True)
        b=await MessagingRepository().binding(c,workspace_slug='telchi_dev',channel_alias='telchi_whatsapp_dev',provider='evolution',instance='team360-meta-dev')
        channel=ChannelContext(b.channel_id,b.provider,b.provider_instance,b.receiver_context,b.tenant_id,b.workspace_id,b.module)
        identity=await PhoneIdentityRepository().resolve(c,channel,sender)
        assert identity and identity.user_id==users['devfull@telchiai.com'] and identity.permissions==frozenset({'telchi.sales.source_quantity.read.v1'})
        async with c.transaction(force_rollback=True):
            repeat=await bind_verified_dev_phone(c,workspace_id=w,user_id=identity.user_id,actor_user_id=users['admin@telchiai.com'],sender_identity=sender,verification_ref=verification_ref,consent_verified=True);assert repeat==ident
        audit=await (await c.execute("SELECT event_name,payload_jsonb FROM core_events WHERE entity_id=%s AND entity_type='messaging_phone_binding'",(ident,))).fetchall()
    result={'timestamp':datetime.now(timezone.utc).isoformat(),'phone_verification':'PASS','phone_binding':'PASS','binding_id':ident,'workspace_id':w,'user_id':identity.user_id,'environment':'dev','provider':'evolution','permissions':sorted(identity.permissions),'verification_ref':verification_ref,'proof_message_id_hash':observed['proof_message_id_hash'],'operator_confirmation_received':True,'idempotence':'PASS','audit':audit}
    (ROOT/'binding-phone-applied.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':asyncio.run(main())
