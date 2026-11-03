"""Real identity/RBAC/Luna/Foundation/PG, isolated inbox, SIMULATED outbound.

No listener, Evolution mutation, business grants, SAP or external WhatsApp.
Output checkpoints permit a subsequent process to resume the durable conversation.
"""
import argparse
import asyncio
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from time import monotonic
from uuid import uuid4

from modules.db.pool import create_pool, open_pool, close_pool
from modules.db.settings import get_database_settings
from modules.db.transaction import transaction
from modules.messaging.domain.messages import InboundMessage, OutboundMessageReceipt
from modules.messaging.handlers import ChannelContext, MessageDispatcher
from modules.messaging.identity import PostgresPhoneIdentityResolver
from modules.messaging.repository import MessagingRepository
from modules.messaging.service import MessagingService
from modules.messaging.durable import DurableWorker
from modules.telchi.assistant import whatsapp_dev as dev, whatsapp_dev_lifecycle as lifecycle
from modules.telchi.assistant.handler import BusinessPolicy, BusinessAuthorization, PostgresConversationStore, TelchiHandler, registration
from modules.telchi.assistant.capabilities import SalesCapabilities
from modules.telchi.assistant.conversation_controls import OPTIONS
from .live_operational_authorized import QUESTIONS

TURNS = [QUESTIONS[2], 'Continuar', '¿Y cuáles fueron los cinco principales proveedores?',
         'Nueva consulta', QUESTIONS[0], QUESTIONS[1], QUESTIONS[3], QUESTIONS[4]]


async def run(output, max_turns):
    lifecycle.load_config(dev.PRIVATE_ROOT / 'whatsapp-dev-control.json')
    approval_path = dev.PRIVATE_ROOT / 'whatsapp-dev-session-approval.json'
    approval = dev.read_approval(approval_path)
    srv, settings = dev.configuration()
    binding = await dev.check_database(approval, settings, srv.evolution)
    report = json.loads(output.read_text()) if output.exists() else dict(
        verdict='PARTIAL', scope='real backend; simulated outbound; NOT external WhatsApp',
        receiver='durable-local-' + uuid4().hex, workspace_id=binding.workspace_id,
        user_id=approval['user_id'], instance=binding.provider_instance,
        source_sha256=dev.source_digest(), whatsapp_sent=0, turns=[])
    binding = replace(binding, receiver_context=report['receiver'])
    policy = BusinessPolicy(approval['tenant_id'], approval['workspace_id'], None,
        approval['module_enabled'], approval['whole_workspace_scope_verified'],
        pilot_access_check=lambda: dev.unchanged_approval(approval_path, approval),
        pilot_user_id=approval['user_id'], pilot_approval_sha256=dev.approval_digest(approval))
    pool = create_pool(replace(get_database_settings(), min_size=1, max_size=4))
    await open_pool(pool)
    def save():
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_suffix('.pending.json')
        temporary.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
        temporary.replace(output)
    class Sender:
        calls = 0
        def send_text(self, *, destination, text):
            assert destination == settings.authorized_sender and len(text) <= 4096
            self.calls += 1
            return OutboundMessageReceipt('local-durable-' + uuid4().hex, '')
    try:
        channel = ChannelContext(binding.channel_id,binding.provider,binding.provider_instance,
            binding.receiver_context,binding.tenant_id,binding.workspace_id,binding.module,binding.environment)
        handler = TelchiHandler(store=PostgresConversationStore(pool), authorization=BusinessAuthorization(policy),
            capabilities=SalesCapabilities(timeout_seconds=180),turn_timeout_seconds=300)
        if not report['turns']:
            from modules.telchi.assistant.state_engine import EMPTY
            await handler.interpreter.interpret(text='¿Cuánto facturamos?',state=EMPTY,history={},
                turn_id='durable-preflight', enterprise_context={'own_company':{'name':'Telchi','aliases':[]}})
            report['model_preflight'] = handler.interpreter.last_metadata
            save()
        dispatcher = MessageDispatcher(channels=(channel,),handlers={'telchi':registration(handler)},
            identities=PostgresPhoneIdentityResolver(pool),environment='dev')
        sender, repository = Sender(), MessagingRepository()
        service = MessagingService(pool=pool,repository=repository,binding=binding,sender=sender,
            authorized_sender='',dispatcher=dispatcher,durable=True)
        for index in range(len(report['turns']),min(len(TURNS),len(report['turns'])+max_turns)):
            question = TURNS[index]
            # Stable IDs across a probe process crash, never duplicate execution.
            external_id = report['receiver'] + '-' + str(index)
            event = InboundMessage('evolution','whatsapp',external_id,'',settings.authorized_sender,
                (binding.receiver_context,),'',question,datetime.now(timezone.utc),
                {'provider_instance':binding.provider_instance,'local_probe':True,'external_whatsapp':False})
            started = monotonic()
            ingress = await service.process(event,t0_ms=0,t1_ms=0)
            ingress_ms = (monotonic()-started)*1000
            duplicates = await asyncio.gather(*(service.process(event,t0_ms=0,t1_ms=0) for _ in range(10)))
            assert duplicates == ['duplicate']*10
            # New worker per turn proves restart-independent retrieval of work.
            assert await DurableWorker(service).tick()
            async with transaction(pool) as conn:
                rows = await repository.evidence(conn,binding)
            inbound = next(r for r in rows if r['direction']=='inbound' and r['provider_message_id']==external_id)
            outbound = [r for r in rows if r['direction']=='outbound' and r['event_type']=='message'
                        and r['correlation_id']==str(inbound['id'])]
            assert len(outbound)==1 and outbound[0]['status']=='completed'
            audit = inbound['payload_jsonb'].get('telchi_assistant_v1',{})
            response = outbound[0]['payload_jsonb']['text']
            result = dict(index=index,question=question,ingress=ingress,ingress_ms=round(ingress_ms,2),
                total_seconds=round(monotonic()-started,2),duplicates=10,outbound_logical=1,
                classification=audit.get('response_prepared',{}).get('classification'),
                decision=audit.get('decision'),execution_status=audit.get('execution_status'),
                capability_calls=audit.get('capability_calls'),analysis_context_id=audit.get('analysis_context_id'),
                confirmed_state=audit.get('confirmed_state'),model=handler.interpreter.last_metadata,
                response_sha256=hashlib.sha256(response.encode()).hexdigest(),response_length=len(response),
                options=response.endswith(OPTIONS),job=inbound['payload_jsonb']['durable_job'],
                outbound_status=outbound[0]['status'],transport_status=outbound[0]['transport_status'])
            report['turns'].append(result)
            save()
            print(json.dumps({k:result[k] for k in ('index','ingress_ms','total_seconds','classification','execution_status','options')}),flush=True)
        report['backend_probe_completed'] = len(report['turns']) == len(TURNS)
        # A completed probe is evidence, NOT a full backend or external PASS.
        save()
    finally:
        await close_pool(pool)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--max-turns',type=int,default=3)
    args=parser.parse_args()
    asyncio.run(run(args.output,args.max_turns))
