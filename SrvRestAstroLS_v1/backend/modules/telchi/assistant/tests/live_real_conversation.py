"""Opt-in Luna smoke of one incident + linguistic variants. No WhatsApp/PG writes.

Run from backend: uv run python -m modules.telchi.assistant.tests.live_real_conversation
Uses the real interpreter/handler with external persistence and auth doubles.
"""
import asyncio
from copy import deepcopy
from dataclasses import replace
import json
import os
import sys
from pathlib import Path
from dotenv import dotenv_values
from modules.telchi.assistant.luna import LunaInterpreter, MODEL
from modules.telchi.assistant.handler import TelchiHandler
from .test_assistant import setup, plan, context, event, latest
from .test_real_conversation import FIXTURE, MAY, BOTH

OUT = Path('../../data/reports/telchi/whatsapp-assistant-dev-live-v1/diagnosis-luna-smoke.json')

def effective(state):
    return state['pending']['proposed'] if state['pending'] else state


def variant_ok(index, state):
    after = effective(state)
    return (after.get('requested_metrics') == BOTH if index in (1, 2) else
            after.get('temporal_reference') == 'latest_available_month' if index == 3 else after['period'] == MAY)


async def main():
    if '--recheck' in sys.argv:
        evidence = json.loads(OUT.read_text())
        indexes = [n for n, t in enumerate(FIXTURE['turns']) for _ in t.get('variations', [])]
        for n, variant in zip(indexes, evidence['variants'], strict=True):
            audit = variant['audit']
            variant['passed'] = (variant_ok(n, audit['confirmed_state']) and audit['committed']
                                 and audit['execution_status'] == 'not_executed'
                                 and audit['response_prepared']['classification'] != 'NEEDS_CLARIFICATION')
        evidence['status'] = 'PASS' if all(evidence['checks'].values()) and all(v['passed'] for v in evidence['variants']) else 'PARTIAL'
        evidence['evaluation_note'] = 'Pending proposed is the known intention for committed ASK; active state is deliberately protected. Recheck only, no new provider calls.'
        OUT.write_text(json.dumps(evidence, indent=2, ensure_ascii=False)+'\n')
        print(json.dumps(dict(status=evidence['status'], variants_passed=sum(v['passed'] for v in evidence['variants']))))
        return
    for k, v in dotenv_values('../.env.backend-dev.local').items():
        if v is not None:
            os.environ[k] = v
    llm = LunaInterpreter()
    records = []
    # Minimal direct-provider preflight: actual response verifies model/effort/auth.
    try:
        preflight = await llm.interpret(text='Importe de ventas durante mayo de 2026', state=deepcopy(plan()), history={}, turn_id='preflight')
    except Exception as exc:
        OUT.write_text(json.dumps({'status': 'BLOCKED', 'exception_class': type(exc).__name__, 'model': MODEL}, indent=2)+'\n')
        print('LUNA_PREFLIGHT=BLOCKED')
        return
    handler, store, _, calls = setup([])
    handler.interpreter = llm
    c = context()
    owner = [c.channel.environment, c.channel.tenant_id, c.channel.workspace_id, c.channel.channel_id, c.sender_identity.user_id]
    key = tuple(owner) + (c.conversation_id,)
    store.states[key] = deepcopy(plan())  # Mirror the documentary query before the six incident turns.
    snapshots = []
    for n, turn in enumerate(FIXTURE['turns']):
        response = await handler.handle(event(turn['text']), replace(c, correlation_id=f'smoke-{n}'))
        audit = deepcopy(latest(store))
        audit.pop('owner')
        records.append(dict(text=turn['text'], audit=audit))
        snapshots.append(deepcopy(audit['confirmed_state']))
        if n == 2:
            handler = TelchiHandler(store=store, authorization=handler.authorization, interpreter=llm, capabilities=handler.capabilities)
    checks = dict(committed=all(r['audit']['committed'] for r in records),
        both_metrics=snapshots[1].get('requested_metrics') == BOTH,
        priority=snapshots[2].get('requested_metrics') == BOTH,
        entity=all((s['pending']['proposed'] if s['pending'] else s).get('entity_mention', {}).get('text', '').lower() == 'calenta' for s in snapshots),
        latest_month=snapshots[3].get('temporal_reference') == 'latest_available_month' and snapshots[3]['period'] is None,
        may=snapshots[4]['period'] == snapshots[5]['period'] == MAY,
        no_execution=not calls,
        no_repeated_selection=all(r['audit']['response_prepared']['classification'] != 'NEEDS_CLARIFICATION' for r in records[1:]))
    variants = []
    # Variants are independent follow-ups to actual smoke states, not literal rules.
    for n, turn in enumerate(FIXTURE['turns']):
        for text in turn.get('variations', []):
            state = deepcopy(snapshots[n-1])
            handler, variant_store, _, variant_calls = setup([])
            handler.interpreter = llm
            variant_store.states[key] = state
            await handler.handle(event(text), replace(c, correlation_id='variant'))
            audit = deepcopy(latest(variant_store)); audit.pop('owner')
            expected = variant_ok(n, audit['confirmed_state'])
            variants.append(dict(text=text, audit=audit, passed=expected and audit['committed'] and not variant_calls
                                 and audit['response_prepared']['classification'] != 'NEEDS_CLARIFICATION'))
    passed = all(checks.values()) and all(v['passed'] for v in variants)
    OUT.write_text(json.dumps(dict(status='PASS' if passed else 'PARTIAL', metadata=llm.last_metadata,
        preflight=preflight, checks=checks, turns=records, variants=variants,
        boundary='Real Luna; auth/persistence/query doubles; NOT WhatsApp'), indent=2, ensure_ascii=False)+'\n')
    print(json.dumps(dict(status='PASS' if passed else 'PARTIAL', checks=checks, variants_passed=sum(v['passed'] for v in variants), variants=len(variants))))

if __name__ == '__main__':
    asyncio.run(main())
