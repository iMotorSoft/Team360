"""Focal Luna Medium semantic probe; no Foundation execution, PG writes or transport."""
import argparse
import asyncio
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
from time import perf_counter

from dotenv import dotenv_values
from modules.telchi.assistant import state_engine as engine
from modules.telchi.assistant.business_categories import interpreter_context
from modules.telchi.assistant.capabilities import SalesCapabilities
from modules.telchi.assistant.handler import unavailable_response
from modules.telchi.assistant.luna import LunaInterpreter, CREDENTIAL_ENV


async def run(output):
    root = Path(__file__).resolve().parents[6]
    if not os.getenv(CREDENTIAL_ENV):
        key = dotenv_values(root / 'SrvRestAstroLS_v1/.env.backend-dev.local').get(CREDENTIAL_ENV)
        if key:
            os.environ[CREDENTIAL_ENV] = key
    interpreter, catalog = LunaInterpreter(), SalesCapabilities()
    evidence = dict(scope='real interpreter + real State Engine/catalog; no data execution or live RBAC claim',
                    foundation_calls=0, whatsapp_sent=0, category_context=interpreter_context(), turns=[])
    state, history = deepcopy(engine.EMPTY), {}
    questions = [
        ('preflight', 'Cuánto facturamos en septiembre de 2026', 'sales.net_amount', None),
        ('raw_material', 'Cuánto vendimos de materia prima en septiembre', 'sales.net_amount', 'RAW_MATERIAL'),
        ('finished', '¿Y de productos terminados?', 'sales.net_amount', 'LAB_FINISHED_PRODUCT'),
        ('code', 'Buscame el producto L01128', 'products.search', None),
        ('text', 'Buscá productos que digan materia prima', 'products.search', None),
        ('production', '¿Cuánta materia prima consumimos en producción?', None, 'RAW_MATERIAL'),
    ]
    for name, question, metric, code in questions:
        start = perf_counter()
        turn = dict(name=name, question=question, before=deepcopy(state))
        try:
            raw = await interpreter.interpret(text=question, state=state, history=history, turn_id=name)
            processed = engine.process(state, raw, history, name)
            next_state = processed['state_after']
            available = catalog.availability(next_state)
            entity = next_state.get('entity_mention')
            checks = dict(committed=processed['committed'] is True, metric=next_state.get('metric') == metric,
                category=(entity == dict(text=code, type=None) if code else entity is None),
                no_category_search=(not code or not next_state.get('product_search_text')),
                compatible=(not available.allowed if code else available.allowed))
            if name in {'preflight', 'raw_material', 'finished'}:
                checks['period'] = next_state.get('period') == dict(start='2026-09-01', end_exclusive='2026-10-01')
            if name in {'code', 'text'}:
                checks['search_text'] = next_state.get('product_search_text') == ('L01128' if name == 'code' else 'materia prima')
            turn.update(raw=raw, processed=processed, availability=vars(available), checks=checks,
                        metadata=interpreter.last_metadata, status='PASS' if all(checks.values()) else 'FAIL')
            if code:
                turn['response'] = unavailable_response(next_state, available)
            state = deepcopy(next_state)
            history[name] = deepcopy(state)
        except Exception as exc:
            turn.update(status='BLOCKED', error_class=type(exc).__name__)
        turn['elapsed_seconds'] = round(perf_counter() - start, 3)
        evidence['turns'].append(turn)
        if name == 'preflight' and turn['status'] != 'PASS':
            break  # no semantic verdict if real provider/auth/model preflight failed
    evidence['source_hashes'] = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in Path(__file__).parents[1].glob('*.py')}
    evidence['status'] = 'PASS' if len(evidence['turns']) == 6 and all(t['status'] == 'PASS' for t in evidence['turns']) else 'BLOCKED_OR_FAILED'
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x') as stream:
        json.dump(evidence, stream, indent=2, ensure_ascii=False)
    print(json.dumps({'status': evidence['status'], 'turns': [{k:t[k] for k in ('name','status')} for t in evidence['turns']]}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    asyncio.run(run(parser.parse_args().output))
