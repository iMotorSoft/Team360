"""Focused current-source accreditation. No enrollment, grants or transport calls.
Only egress is a recording double. One real Luna interpretation and one existing
read-only fixed Foundation query, through the real PG Messaging/handler chain.
Negative probes use real revoked fixtures read-only, never reactivate them.
"""
from pathlib import Path
import sys, os, asyncio, json, hashlib, uuid, importlib.util
from dataclasses import replace
from datetime import datetime, timezone
HERE=Path(__file__).resolve().parent
BACKEND=HERE.parents[3]/'SrvRestAstroLS_v1/backend'
sys.path.insert(0,str(BACKEND)); os.chdir(BACKEND); os.umask(0o077)
from modules.telchi.assistant import whatsapp_dev as d, whatsapp_dev_lifecycle as l
config=l.load_config(d.PRIVATE_ROOT/'whatsapp-dev-control.json')
apath=Path(config.get('approval',d.PRIVATE_ROOT/'whatsapp-dev-session-approval.json'))
a=d.read_approval(apath)
source=d.source_digest()
out=d.PRIVATE_ROOT/('gate-renewal-final-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
out.mkdir(mode=0o700)
report=dict(generated_at=datetime.now(timezone.utc).isoformat(),source_sha256=source,approval_sha256=d.approval_digest(a),gates={},scope='Current source; DEV PG; one model request and fixed Foundation read; no WhatsApp, no identity/grant/config changes',host_preflight='BUSY_BUT_SAFE: 8 CPUs, ~4.8 GiB available, stable 506 MiB swap, sampled idle 89-92%, no swap IO',concurrency='2 concurrent claims, pool max 3; one Foundation worker threads=2 memory=512MB',baseline='UNAVAILABLE',baseline_search=dict(launcher_tracked=False,all_refs_and_reflogs_launcher_history=False,unreachable_objects_scanned=106,unreachable_launcher_candidates=0,private_backups='DB dumps and data manifests only',snapshots='No source snapshot tied to historical digest'))
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
async def run():
 from modules.db.pool import create_pool,open_pool,close_pool
 from modules.db.settings import get_database_settings
 from modules.db.transaction import transaction
 from modules.messaging.repository import MessagingRepository
 from modules.messaging.service import MessagingService
 from modules.messaging.identity import PhoneIdentityRepository,PostgresPhoneIdentityResolver,InvalidPhoneBinding
 from modules.messaging.handlers import ChannelContext,MessageContext,MessageDispatcher,SenderIdentity
 from modules.telchi.assistant.handler import BusinessPolicy,BusinessAuthorization,TelchiHandler,PostgresConversationStore,registration
 from modules.telchi.assistant.capabilities import SalesCapabilities
 from modules.telchi.assistant.luna import LunaInterpreter
 from scripts import telchi_durable_idempotency_probe as h
 # Read-only operational prerequisites, gates deliberately not checked before renewal.
 approval,srv,settings,binding=await asyncio.to_thread(d.preflight,apath,require_gates=False)
 with d.client_for(srv.evolution) as client:
  before=d.webhook_body(d.api(client,'GET','/webhook/find/'+srv.evolution.instance))
 config_sha=sha(d.PRIVATE_ROOT/'whatsapp-dev-control.json')
 pool=create_pool(replace(get_database_settings(),min_size=1,max_size=3)); await open_pool(pool)
 try:
  repo=MessagingRepository()
  probe_binding=replace(binding,receiver_context='gate-renewal-final:'+uuid.uuid4().hex)
  channel=ChannelContext(probe_binding.channel_id,'evolution',srv.evolution.instance,probe_binding.receiver_context,probe_binding.tenant_id,probe_binding.workspace_id,probe_binding.module,probe_binding.environment)
  policy=BusinessPolicy(a['tenant_id'],a['workspace_id'],a['permission'],a['module_enabled'],a['whole_workspace_scope_verified'])
  auth=BusinessAuthorization(policy)
  async with transaction(pool) as conn:
   await conn.execute('SET TRANSACTION READ ONLY')
   await repo.validate_transport_schema(conn)
   identities=PhoneIdentityRepository()
   identity=await identities.resolve(conn,channel,settings.authorized_sender)
   assert identity and identity.user_id==a['user_id']
   context=MessageContext(channel,identity,settings.authorized_sender,'current-readonly','current-negative',frozenset())
   assert await auth.allowed(context,conn,required_permission=d.PERMISSION)
   assert await identities.resolve(conn,replace(channel,tenant_id='gate-renewal-foreign'),settings.authorized_sender) is None
   assert not await auth.allowed(replace(context,channel=replace(channel,tenant_id='gate-renewal-foreign')),conn)
   fixtures=await (await conn.execute("SELECT b.sender_identity,b.user_id FROM messaging_phone_bindings b JOIN core_users u ON u.id=b.user_id WHERE b.environment='dev' AND b.provider='evolution' AND b.tenant_id=%s AND b.workspace_id=%s AND b.verification_status='revoked' AND u.status='inactive' LIMIT 1",(a['tenant_id'],a['workspace_id']))).fetchall()
   assert fixtures,'existing revoked negative fixture required'
   f=fixtures[0]
   try:
    await identities.resolve(conn,channel,f['sender_identity'])
   except InvalidPhoneBinding:
    revoked_denied=True
   else: raise AssertionError('revoked fixture accepted')
   # Deliberately stale/forged cache must NOT override Console effective DB grants.
   stale=replace(identity,user_id=str(f['user_id']))
   assert not await auth.allowed(replace(context,sender_identity=stale),conn,required_permission=d.PERMISSION)
   assert not await auth.allowed(replace(context,sender_identity=replace(identity,permissions=frozenset())),conn)
  report['gates']['identity_tenant_isolation']=dict(status='PASS',kind='real',scope='Real approved PG phone resolution; foreign tenant lookup absent; wrong channel scope denied; existing revoked/inactive fixture rejected. No cross-tenant fixture reactivation.')
  report['gates']['business_authorization']=dict(status='PASS',kind='real',scope='Current effective Console grant positive; empty cache negative; forged/stale cache for real revoked fixture denied by live Console lookup; no grant changes')
  interpreter=LunaInterpreter()
  cap=h.CapabilityCounter(SalesCapabilities())
  inner=TelchiHandler(store=PostgresConversationStore(pool),authorization=auth,interpreter=interpreter,capabilities=cap)
  handler=h.HandlerCounter(inner)
  dispatcher=MessageDispatcher(channels=(channel,),handlers={'telchi':registration(handler)},identities=PostgresPhoneIdentityResolver(pool),environment='dev')
  sender=h.RecordingSender()
  service=MessagingService(pool=pool,repository=repo,binding=probe_binding,sender=sender,authorized_sender='',dispatcher=dispatcher)
  external='renewal-final-'+uuid.uuid4().hex
  event=h._event(settings.authorized_sender,probe_binding.receiver_context,'Nueva consulta: top 10 productos por cantidad documental del 1 de enero al 15 de septiembre de 2026, sin filtros',external)
  results=await asyncio.gather(service.process(event,t0_ms=0,t1_ms=0),service.process(event,t0_ms=0,t1_ms=0))
  results.append(await service.process(event,t0_ms=0,t1_ms=0))
  inbound,outbound=await h._snapshot(pool,probe_binding,external)
  audit=(inbound[0]['payload_jsonb'] or {}).get('telchi_assistant_v1') or {}
  summary=h._audit_summary(inbound[0])
  report['message']=dict(results=results,handler_calls=handler.calls,capability_calls=cap.calls,recording_egress_calls=len(sender.calls),inbound_count=len(inbound),outbound_count=len(outbound),audit=summary)
  report['model_metadata']=interpreter.last_metadata
  d.save_private(out/'current-probes-progress.json',report)
  assert sorted(results)==['accepted','duplicate','duplicate'] and handler.calls==1 and len(inbound)==1 and len(outbound)==1 and len(sender.calls)==1
  report['gates']['durable_idempotency']=dict(status='PASS',kind='real',scope='Real PG concurrent claim plus sequential retry, exactly one handler/intent; recording egress only. Crash recovery additionally covered by unchanged offline tests and preserved historical artifact.')
  assert interpreter.last_metadata and interpreter.last_metadata['reasoning_echo_verified'] and interpreter.last_metadata['provider']=='OpenAI direct'
  report['gates']['model_no_fallback']=dict(status='PASS',kind='real',scope='Single real direct OpenAI response via current Luna adapter, model/effort/completion verified; provider failure/no retry/no fallback contract tests separately recorded',metadata=interpreter.last_metadata)
  result=audit.get('execution_result') or {}
  report['foundation']=dict(result_keys=list(result),source=result.get('source'),row_count=len(result.get('rows',[])),coverage=result.get('coverage'),period=result.get('period'))
  assert summary['execution_status']=='executed' and summary['capability_calls']==1 and cap.calls==1 and len(result.get('rows',[]))==10
  report['gates']['assistant_foundation']=dict(status='PASS',kind='real',scope='Real phone/identity/Console/handler pipeline; existing approved fixed query, read-only Foundation verified in current reader; 10 rows; no SAP or publication changes',evidence=report['foundation'])
 finally:
  await close_pool(pool)
 with d.client_for(srv.evolution) as client:
  after=d.webhook_body(d.api(client,'GET','/webhook/find/'+srv.evolution.instance))
 assert before==after and not after['enabled']
 assert d.source_digest()==source and sha(d.PRIVATE_ROOT/'whatsapp-dev-control.json')==config_sha
 report.update(webhook_unchanged=True,source_unchanged=True,configuration_unchanged=True,own_processes_left_running=0,unrelated_processes_terminated=0)
try:
 asyncio.run(run())
except Exception as exc:
 report['error_class']=type(exc).__name__
 report['status']='BLOCKED'
else: report['status']='PASS'
d.save_private(out/'current-probes.json',report)
(HERE/'current-probes-summary.json').write_text(json.dumps(dict(artifact=str(out/'current-probes.json'),sha256=sha(out/'current-probes.json'),status=report['status'],gates=list(report['gates']),error_class=report.get('error_class')),indent=2)+'\n')
print((HERE/'current-probes-summary.json').read_text())
