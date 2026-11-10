"""Real Luna + CURRENT Foundation through the WhatsApp dispatcher, NO outbound.

SQL/identity are explicit fixtures; actual ConversationRepository serialization
is used. Does NOT modify PostgreSQL, permissions, gates or runtime configuration.
"""
import argparse
import asyncio
import json
from pathlib import Path

import pytest

from modules.telchi.assistant.capabilities import SalesCapabilities
from modules.telchi.assistant.luna import LunaInterpreter
from modules.telchi.assistant.state_engine import EMPTY
from modules.telchi.datalake import sales_query
from .test_contextual_components import QUESTIONS, setup_dispatch, durable_runtime


async def probe():
    interpreter = LunaInterpreter()
    preflight = await interpreter.interpret(text='¿Cuánto facturamos?', state=EMPTY, history={}, turn_id='preflight')
    if preflight.get('action') != 'ASK':
        raise RuntimeError('preflight_must_clarify_period')
    report = dict(preflight=interpreter.last_metadata, persistence='SQL/identity fixtures; actual ConversationRepository',
                  foundation='real CURRENT read-only', whatsapp_sent=0, postgres_writes=0,
                  processes_restarted=0, turns=[])
    current = sales_query.PUBLICATION
    with pytest.MonkeyPatch.context() as mp:
        handler, db, _, _, _, dispatch = setup_dispatch(mp, [])
        mp.setattr(sales_query, 'PUBLICATION', current)
        handler.capabilities = SalesCapabilities(timeout_seconds=180)
        handler.turn_timeout_seconds = 300
        enqueue, sends = durable_runtime(mp, dispatch)
        report['route'] = 'DurableWorker -> MessageDispatcher -> TelchiHandler -> ConversationRepository'
        for n, question in enumerate(QUESTIONS, 1):
            interpreter = LunaInterpreter()
            handler.interpreter = interpreter
            delivered = await enqueue(question, n)
            a = db.events.get(f'turn-{n}', {}).get('telchi_assistant_v1', {})
            classification = a.get('response_prepared', {}).get('classification')
            report['turns'].append(dict(question=question, text=delivered['text'], classification=classification,
                proposal=a.get('interpretation_proposed'), decision=a.get('decision'), capability_calls=a.get('capability_calls'),
                calculation=a.get('monetary_calculation'), model=interpreter.last_metadata))
            print(json.dumps(dict(turn=n, classification=classification, decision=a.get('decision')), ensure_ascii=False), flush=True)
            if classification in {'ERROR','DENIED'}:
                break
        report['outbound_fixture_responses'] = len(sends)
        report['pass'] = (len(report['turns']) == len(sends) == 4
            and all(t['classification'] == ('NEEDS_CLARIFICATION' if i == 1 else 'DIRECT_AVAILABLE')
                    for i,t in enumerate(report['turns']))
            and all(t['decision'] == 'LOCAL_CALCULATION' and t['capability_calls'] == 0 for t in report['turns'][2:])
            and '4,00 %' in report['turns'][2]['text'] and '96,00 %' in report['turns'][3]['text'])
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit('refusing to overwrite evidence')
    report = asyncio.run(probe())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
        f.write('\n')
    if not report['pass']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
