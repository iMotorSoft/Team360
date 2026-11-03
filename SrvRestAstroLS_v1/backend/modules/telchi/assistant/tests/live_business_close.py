"""Six business questions through real dispatcher, phone identity, Console, PG,
Luna and pinned Foundation. No mock ports, network listener or outbound transport.
Uses the owner's existing private DEV approval; does not activate WhatsApp or
claim that local dispatch is a received WhatsApp message. Creates DEV audit rows.
"""
import argparse
import asyncio
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4

from modules.telchi.assistant import whatsapp_dev as dev, whatsapp_dev_lifecycle as lifecycle
from modules.telchi.datalake.query_profile import Trace
from modules.telchi.assistant.handler import BusinessPolicy, BusinessAuthorization, TelchiHandler, PostgresConversationStore, registration
from modules.telchi.assistant.dev_runtime_http import _run_turn
from modules.telchi.assistant.luna import LunaInterpreter
from modules.telchi.assistant.state_engine import EMPTY
from modules.telchi.assistant.capabilities import SalesCapabilities
from modules.messaging.domain.messages import InboundMessage
from modules.db.pool import create_pool, open_pool, close_pool
from modules.db.settings import get_database_settings

QUESTIONS = ['¿Cuánto facturamos en septiembre de 2026?', '¿Y en agosto?',
             '¿Cuál fue la diferencia?', 'Mostrame las últimas cinco facturas.',
             '¿Qué productos tiene la primera?', '¿Cuánto vale esa factura?']


async def run(*, questions=None, diagnostic_dev=False, diagnostic_worker_seconds=90, diagnostic_turn_seconds=120, checkpoint=None):
    if (not 1 <= diagnostic_worker_seconds <= 300 or not diagnostic_worker_seconds < diagnostic_turn_seconds <= 600
            or (not diagnostic_dev and (diagnostic_worker_seconds, diagnostic_turn_seconds) != (90, 120))):
        raise RuntimeError('invalid DEV diagnostic budget')
    if diagnostic_dev and os.getenv('TEAM360_ENV') not in {'dev', 'development'}:
        raise RuntimeError('diagnostic budget is DEV only')
    def new_interpreter():
        return LunaInterpreter(timeout_seconds=20, max_attempts=1) if diagnostic_dev else LunaInterpreter()
    config = lifecycle.load_config(dev.PRIVATE_ROOT/'whatsapp-dev-control.json')
    approval_path = Path(config.get('approval',dev.PRIVATE_ROOT/'whatsapp-dev-session-approval.json'))
    approval = dev.read_approval(approval_path)
    srv, settings = dev.configuration()
    if diagnostic_dev:
        if os.getenv('TEAM360_ENV') not in {'dev', 'development'}:
            raise RuntimeError('configured runtime must be DEV')
        os.environ['TEAM360_TELCHI_PRE_SQL_PROFILE'] = '1'
    binding = await dev.check_database(approval,settings,srv.evolution)
    if hashlib.sha256(settings.authorized_sender.encode()).hexdigest() != approval['sender_sha256']:
        raise PermissionError('pilot line mismatch')
    def access_check():
        dev.unchanged_approval(approval_path,approval)
    policy = BusinessPolicy(approval['tenant_id'],approval['workspace_id'],None,
        approval['module_enabled'],approval['whole_workspace_scope_verified'],
        pilot_access_check=access_check,pilot_user_id=approval['user_id'],
        pilot_approval_sha256=dev.approval_digest(approval))
    interpreter = new_interpreter()
    preflight_text = ('Quiero el importe de facturación de un período que todavía no indiqué. Preguntame el período.'
                      if diagnostic_dev else '¿Cuánto facturamos?')
    preflight = await interpreter.interpret(text=preflight_text,state=EMPTY,history={},turn_id='business-preflight',
        enterprise_context=dict(own_company={'name':'Telchi','aliases':[]},tenant_id=approval['tenant_id'],workspace_id=approval['workspace_id']))
    if preflight.get('action') != 'ASK' or preflight.get('clarification',{}).get('slot') != 'period':
        raise RuntimeError('missing period preflight must clarify: ' + json.dumps(preflight, ensure_ascii=False))
    report = dict(timestamp=datetime.now(timezone.utc).isoformat(),
        source_sha256=dev.source_digest(), model_preflight=interpreter.last_metadata,
        missing_period_proposal=preflight, services_started_or_stopped=0,listeners=0,whatsapp_sent=0,
        identity='actual approved DEV phone binding and Console resolver', persistence='actual PostgreSQL committed DEV audit rows',
        foundation='actual read-only pinned CURRENT', authentication='owner-authorized local probe, not a human login or WhatsApp ingress',
        turns=[])
    def save_checkpoint():
        if checkpoint is not None:
            path = Path(checkpoint)
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix('.pending.json')
            temporary.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str)+'\n')
            temporary.replace(path)
            print(json.dumps(dict(checkpoint=str(path), completed_turns=len(report['turns']),
                                  last_classification=report['turns'][-1]['classification'] if report['turns'] else None)), flush=True)
    save_checkpoint()
    pool = create_pool(replace(get_database_settings(),min_size=1,max_size=1))
    await open_pool(pool)
    conversation = 'business-close-'+uuid4().hex
    try:
        for question in (QUESTIONS if questions is None else questions):
            # Fresh handler/interpreter each turn proves durable context, not Python memory.
            interpreter = new_interpreter()
            handler = TelchiHandler(store=PostgresConversationStore(pool),authorization=BusinessAuthorization(policy),
                interpreter=interpreter,capabilities=SalesCapabilities(timeout_seconds=diagnostic_worker_seconds if diagnostic_dev else 60),
                turn_timeout_seconds=diagnostic_turn_seconds if diagnostic_dev else 80)
            message = InboundMessage(provider='evolution',channel='whatsapp',external_message_id='business-'+uuid4().hex,
                sender=settings.authorized_sender,recipients=(binding.receiver_context,),text_body=question,
                external_thread_id=None,subject=None,received_at=datetime.now(timezone.utc),metadata={'provider_instance':binding.provider_instance})
            trace = Trace()
            with trace.activate():
                result, ids, elapsed = await _run_turn(pool=pool,registrations={'telchi':registration(handler)},binding=binding,
                    message=message,conversation_key=conversation,authenticated_user_id=approval['user_id'])
            audit = ids['payload'].get('telchi_assistant_v1') or {}
            report['turns'].append(dict(question=question,text=result.text,classification=result.classification,
                event_id=ids['correlation_id'],thread_id=ids['conversation_id'],audit=audit,model=interpreter.last_metadata,
                elapsed_ms=elapsed, request_trace=trace.export()))
            save_checkpoint()
            if result.classification in {'ERROR','DENIED'}:
                break
        return report
    finally:
        await close_pool(pool)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--sales-finalization-dev', action='store_true')
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit('refusing to overwrite evidence')
    questions = ['¿Cuánto vendimos en septiembre de 2026?',
                 '¿Cuánto vendimos en octubre de 2026 hasta el día 29?'] if args.sales_finalization_dev else None
    report = asyncio.run(run(questions=questions, diagnostic_dev=args.sales_finalization_dev))
    if args.sales_finalization_dev:
        report['diagnostic_budget'] = dict(environment='DEV', turn_seconds=120, worker_seconds=90,
                                         model_seconds=20, model_attempts=1, production_changed=False)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x') as stream:
        json.dump(report,stream,indent=2,ensure_ascii=False)
        stream.write('\n')
    for turn in report['turns']:
        print(json.dumps({k:turn[k] for k in ('question','classification','text')},ensure_ascii=False))


if __name__ == '__main__':
    main()
