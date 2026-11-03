"""Replay recorded real Luna decisions through final handler; NOT live transport."""
import asyncio
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
from modules.telchi.assistant.tests.test_assistant import setup, plan, context, event, latest

ROOT = Path(__file__).resolve().parent

async def main():
    evidence = json.loads((ROOT / 'diagnosis-luna-smoke.json').read_text())
    proposals = [r['audit']['interpretation_proposed'] for r in evidence['turns']]
    handler, store, llm, calls = setup(proposals)
    c = context()
    owner = [c.channel.environment, c.channel.tenant_id, c.channel.workspace_id, c.channel.channel_id, c.sender_identity.user_id]
    key = tuple(owner) + (c.conversation_id,)
    store.states[key] = deepcopy(plan())
    records = []
    for n, record in enumerate(evidence['turns']):
        result = await handler.handle(event(record['text']), replace(c, correlation_id=f'smoke-{n}'))
        audit = deepcopy(latest(store)); audit.pop('owner')
        # Responses are not interpreter input; only state/history were used.
        assert audit['confirmed_state'] == record['audit']['confirmed_state']
        assert audit['committed'] is True
        if n:
            assert result.classification == 'DIRECT_UNAVAILABLE'
        records.append(dict(text=record['text'], audit=audit))
    assert not calls
    (ROOT / 'diagnosis-handler-replay-final.json').write_text(json.dumps(dict(status='PASS', turns=records,
        provider_calls=0, capability_calls=len(calls), provenance='Recorded actual Luna proposals replayed through final handler; NOT WhatsApp'), indent=2, ensure_ascii=False)+'\n')
    print('FINAL_HANDLER_REPLAY=PASS')

if __name__ == '__main__':
    asyncio.run(main())
