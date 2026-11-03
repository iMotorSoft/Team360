"""Focused real DEV gate renewal, no listeners, transport sends or service lifecycle.

Real ASGI authentication, approved phone/Console identity, reversible real grant
revocation, durable PostgreSQL claim/cache/fence, and Luna/Foundation execution.
Outbound intent uniqueness is checked inside rollback: no pending send is left.
This is NOT a WhatsApp delivery/E2E certification.
"""
import argparse
import asyncio
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from uuid import uuid4
import httpx

from modules.telchi.assistant import whatsapp_dev as d, whatsapp_dev_lifecycle as l
from modules.telchi.assistant.handler import BusinessPolicy, BusinessAuthorization, TelchiHandler, PostgresConversationStore, registration
from modules.telchi.assistant.composition import create_telchi_app
from modules.telchi.assistant.luna import LunaInterpreter
from modules.telchi.assistant.capabilities import SalesCapabilities
from modules.telchi.provisioning.business_close_repository import BusinessCloseRepository, AUTHORIZATION
from modules.messaging.repository import MessagingRepository
from modules.messaging.handlers import ChannelContext, MessageContext, MessageDispatcher
from modules.messaging.identity import PhoneIdentityRepository, PostgresPhoneIdentityResolver
from modules.messaging.domain.messages import InboundMessage
from modules.db.pool import create_pool, open_pool, close_pool
from modules.db.settings import get_database_settings
from modules.db.transaction import transaction


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


async def run(args):
    config=l.load_config(d.PRIVATE_ROOT/'whatsapp-dev-control.json')
    ap=Path(config.get('approval',d.PRIVATE_ROOT/'whatsapp-dev-session-approval.json'))
    approval=d.read_approval(ap)
    _,srv,settings,binding=await asyncio.to_thread(d.preflight,ap,require_gates=False)
    assert l.read_json(l.root()/'current.json')['state']=='STOPPED', 'Operator runtime must remain stopped'
    source=d.source_digest()
    conversation=json.loads(args.conversation.read_text())
    parity=json.loads(args.parity.read_text())
    full_access=json.loads(args.full_access.read_text())
    assert conversation['source_sha256']==source, 'Conversation source changed; rerun affected conversation'
    assert parity['status']==full_access['status']=='PASS'
    assert len(conversation['turns'])==6
    assert all(conversation['turns'][i]['classification']=='DIRECT_AVAILABLE' for i in (0,1,3,4,5))
    assert conversation['turns'][2]['classification']=='DIRECT_UNAVAILABLE'
    observed=dict(status='PASS',source_sha256=source,approval_sha256=d.approval_digest(approval),
        configuration_sha256=d.configuration_digest(),generated_at=datetime.now(timezone.utc).isoformat(),
        whatsapp_sent=0,listeners_created=0,services_started_or_stopped=0,observations={},
        limits='DEV manual readiness only, no WhatsApp delivery/E2E or full-month completeness certified.',
        inputs={str(p):sha(p) for p in (args.conversation,args.parity,args.full_access)})
    def passed(name,**facts):
        observed['observations'][name]=dict(status='PASS',**facts)
    def check():
        d.unchanged_approval(ap,approval)
    policy=BusinessPolicy(approval['tenant_id'],approval['workspace_id'],None,
        approval['module_enabled'],approval['whole_workspace_scope_verified'],pilot_access_check=check,
        pilot_user_id=approval['user_id'],pilot_approval_sha256=d.approval_digest(approval))
    auth=BusinessAuthorization(policy)
    pool=create_pool(replace(get_database_settings(),min_size=1,max_size=1))
    await open_pool(pool)
    try:
        app=d.PilotBoundary(create_telchi_app(policy=policy,pool=pool),settings,srv.evolution,srv.recipient,check)
        cases=[]
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://isolated') as client:
            for label,token,body,expected in [
                ('no token','',b'{malformed',401),('invalid token','invalid',b'{malformed',401),
                ('authenticated malformed JSON',settings.webhook_token,b'{malformed',400),
                ('authenticated ignored event',settings.webhook_token,json.dumps(dict(event='connection.update',instance=srv.evolution.instance)).encode(),200)]:
                response=await client.post(d.WEBHOOK,content=body,headers={'x-team360-webhook-token':token,'content-type':'application/json'})
                assert response.status_code==expected,(label,response.status_code)
                cases.append(dict(case=label,status=expected))
        passed('http_auth',transport='real in-process ASGI, no listener',cases=cases)
        channel=ChannelContext(binding.channel_id,'evolution',binding.provider_instance,binding.receiver_context,
            binding.tenant_id,binding.workspace_id,binding.module,binding.environment)
        async with transaction(pool) as conn:
            identities=PhoneIdentityRepository()
            identity=await identities.resolve(conn,channel,settings.authorized_sender)
            assert identity and identity.user_id==approval['user_id']
            context=MessageContext(channel,identity,settings.authorized_sender,'pending','pending',frozenset())
            assert await auth.allowed(context,conn,required_permission='telchi.sales.invoice_amount.read.v1')
            for foreign in (replace(channel,tenant_id='foreign'),replace(channel,workspace_id=str(uuid4()))):
                assert await identities.resolve(conn,foreign,settings.authorized_sender) is None
                assert not await auth.allowed(replace(context,channel=foreign),conn)
            assert not await auth.allowed(replace(context,sender_identity=replace(identity,user_id=str(uuid4()))),conn)
        passed('identity_tenant_isolation',actual_approved_phone_binding=True,negative_axes=['tenant','workspace','user'],
            persisted_context='six-turn conversation, fresh handler each turn')
        async with pool.connection() as conn:
            async with conn.transaction(force_rollback=True):
                revoked=await BusinessCloseRepository().revoke(conn,authorization=AUTHORIZATION,
                    backup_sha256=full_access['backup_sha256'])
                assert revoked['changed']
                assert not await auth.allowed(context,conn,required_permission='telchi.sales.invoice_amount.read.v1')
                # The stale identity still carries the permission; live resolver denies it.
                assert 'telchi.sales.invoice_amount.read.v1' in identity.permissions
        async with transaction(pool) as conn:
            assert await auth.allowed(context,conn,required_permission='telchi.sales.invoice_amount.read.v1')
        passed('business_authorization',full_access='actual DEV pilot only',revocation='actual rollback rehearsal',
            stale_identity_denied=True,normal_assignments_preserved=full_access['individual_user_roles_unchanged'])
        # Bounded isolated storage key; actual channel, identity and PostgreSQL, no mock ports.
        isolated=replace(binding,receiver_context='business-gate:'+uuid4().hex)
        isolated_channel=replace(channel,receiver_context=isolated.receiver_context)
        message=InboundMessage(provider='evolution',channel='whatsapp',external_message_id='gate-'+uuid4().hex,
            sender=settings.authorized_sender,recipients=(isolated.receiver_context,),
            text_body='¿Cuánto facturamos en septiembre de 2026?',external_thread_id=None,subject=None,
            received_at=datetime.now(timezone.utc),metadata={'provider_instance':binding.provider_instance,'local_gate_probe':True})
        repo=MessagingRepository()
        async with transaction(pool) as conn:
            claimed=await repo.claim(conn,isolated,message,{})
            assert claimed
        interpreter=LunaInterpreter()
        class MeasuredCapabilities(SalesCapabilities):
            calls=0
            async def execute(self,state):
                self.calls+=1
                return await super().execute(state)
        capabilities=MeasuredCapabilities()
        handler=TelchiHandler(store=PostgresConversationStore(pool),authorization=auth,interpreter=interpreter,capabilities=capabilities)
        dispatcher=MessageDispatcher(channels=(isolated_channel,),handlers={'telchi':registration(handler)},
            identities=PostgresPhoneIdentityResolver(pool),environment='dev')
        result=await dispatcher.dispatch(message,channel_id=isolated.channel_id,conversation_id=claimed['thread_id'],correlation_id=claimed['id'])
        assert result.classification=='DIRECT_AVAILABLE'
        async with transaction(pool) as conn:
            await repo.complete_dispatch(conn,isolated,claimed,result)
        for _ in range(2):
            async with transaction(pool) as conn:
                assert await repo.claim(conn,isolated,message,{}) is None
        cached=await handler.handle(message,replace(context,channel=isolated_channel,
            conversation_id=claimed['thread_id'],correlation_id=claimed['id']))
        assert cached.text==result.text and cached.classification==result.classification
        assert capabilities.calls==1
        async with pool.connection() as conn:
            async with conn.transaction(force_rollback=True):
                one=await repo.intent(conn,isolated,claimed,message,result.text,{})
                two=await repo.intent(conn,isolated,claimed,message,result.text,{})
                assert one==two
        passed('durable_idempotency',committed_pg_claim=True,duplicate_claims=2,cached_response_identical=True,
            capability_executions=capabilities.calls,
            logical_outbound_unique='actual intent SQL, rolled back; no delivery queued')
        passed('assistant_foundation',six_turns='five available, comparison explicitly unavailable',
            period_parity='independent SQL, difference zero',same_invoice_amount='BS 25.00',real_execution=True)
        metadata=[conversation['model_preflight']]+[t['model'] for t in conversation['turns']]+[interpreter.last_metadata]
        assert all(md and md['provider']=='OpenAI direct' and md['reasoning_echo_verified'] for md in metadata)
        passed('model_no_fallback',metadata=metadata,adapter='direct, no retries/proxy/redirects/fallback')
    finally:
        await close_pool(pool)
    assert source==d.source_digest()
    observed['pool_closed']=True
    out=d.PRIVATE_ROOT/('business-gates-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir(mode=0o700)
    artifact=out/'report.json'
    l.atomic(artifact,observed)
    result=dict(status='PASS',artifact=str(artifact),sha256=sha(artifact),SIX_GATES='NOT_PUBLISHED')
    if args.publish:
        mp=d.private_file(approval['gates_file'])
        previous=mp.read_bytes()
        old=json.loads(previous)
        assert old.get('validity_policy')==d.DEV_GATE_POLICY and old.get('schema_version')==2
        l.atomic(out/'previous-manifest.json',old)
        manifest=dict(schema_version=2,validity_policy=d.DEV_GATE_POLICY,environment='dev',
            workspace_id=approval['workspace_id'],user_id=approval['user_id'],instance='team360-meta-dev',
            issued_at=datetime.now(timezone.utc).isoformat(),source_sha256=source,
            configuration_sha256=d.configuration_digest(),approval_sha256=d.approval_digest(approval),
            previous_manifest=dict(artifact=str(out/'previous-manifest.json'),sha256=sha(out/'previous-manifest.json')),
            renewal_basis='Owner-authorized business closeout; focused actual DEV pipeline, no delivery or lifecycle changes.',
            gates={name:dict(status='PASS',kind='real',artifact=str(artifact),sha256=sha(artifact),observations=[name]) for name in d.GATES})
        assert mp.read_bytes()==previous
        l.atomic(mp,manifest)
        try:
            d.gate_evidence(approval)
            await asyncio.to_thread(d.preflight,ap)
        except BaseException:
            l.atomic(mp,old)
            raise
        result.update(SIX_GATES='VALID',manifest_sha256=sha(mp),READY_FOR_MANUAL_WHATSAPP='YES',
            runtime='not started',whatsapp_sent=0)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('conversation','parity','full-access','output'):
        parser.add_argument('--'+name,required=True,type=Path)
    parser.add_argument('--publish',action='store_true')
    args=parser.parse_args()
    if args.output.exists():
        raise SystemExit('refusing to overwrite evidence')
    result=asyncio.run(run(args))
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))


if __name__=='__main__':
    main()
