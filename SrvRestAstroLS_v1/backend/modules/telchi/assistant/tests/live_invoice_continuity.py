"""Focused real Luna + Foundation execution; fixture identity and repository port.

No HTTP server, operational conversation writes, or WhatsApp sends. A separate
real-RBAC evidence check is necessary; this probe does not certify channel readiness.
"""
import argparse
import asyncio
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path

from modules.telchi.assistant.handler import PostgresConversationStore
from modules.telchi.assistant.luna import LunaInterpreter
from modules.telchi.assistant.state_engine import EMPTY
from modules.telchi.assistant.capabilities import SalesCapabilities
from modules.telchi.datalake.invoice_lines_query import PUBLICATION, SNAPSHOT, PERMISSION
from .test_assistant import setup, context, event
from .test_result_references import DatabasePort, PERMISSION as DOCUMENT_PERMISSION


async def probe(full_conversation=False):
    db = DatabasePort()
    owner = ['dev', 'telchi', 'workspace', 'channel', 'user']
    state = dict(deepcopy(EMPTY), metric='sales.latest_documents', limit=3)
    db.thread = dict(telchi_assistant_v1=dict(owner=owner, state=state,
        history={'invoice-result': state}, history_order=['invoice-result'],
        result_reference=dict(result_id='invoice-result', selected_ordinal=1),
        document_reference=dict(result_id='invoice-result', selected_ordinal=1)))
    db.events['invoice-result'] = dict(environment='dev', telchi_assistant_v1=dict(
        owner=owner, confirmed_state=state, business_rbac_verified=True, required_permission=DOCUMENT_PERMISSION,
        execution_status='executed', response_prepared={'classification': 'DIRECT_AVAILABLE'},
        execution_result=dict(capability='sales.latest_documents.v1',
            source=dict(publication_id=PUBLICATION, snapshot_id=SNAPSHOT, updated_at='2026-09-28T18:18:35.264000'),
            rows=[dict(doc_entry='11532517', doc_num='260192728', doc_date='2026-09-24T00:00:00')])) )
    if full_conversation:
        db.thread = {}
        db.events = {}
    h, _, _, _ = setup([])
    # Actual repository read/save, session port only; no public Messaging writes.
    from contextlib import asynccontextmanager
    @asynccontextmanager
    async def turn(ctx):
        yield await h.store.repository.load(db, ctx)
    class Store(PostgresConversationStore):
        async def save(self, ctx, current, audit):
            await self.repository.save(db, ctx, current, audit)
    h.store = Store(None)
    h.store.turn = turn
    h.capabilities = SalesCapabilities()
    h.interpreter = LunaInterpreter()
    async def allowed(ctx, conn=None, *, required_permission=None):
        return required_permission is None or required_permission in ctx.sender_identity.permissions
    h.authorization.allowed = allowed
    c = context()
    c = replace(c, sender_identity=replace(c.sender_identity, permissions=c.sender_identity.permissions | {PERMISSION, DOCUMENT_PERMISSION}))
    report = dict(timestamp=datetime.now(timezone.utc).isoformat(), identity='fixture', rbac='fixture',
        persistence='real repository serialization, in-memory SQL port', foundation='real read-only CURRENT pinned 1408',
        whatsapp_sent=0, runtime_replaced=False, full_conversation=full_conversation, turns=[])
    args = dict(state=state, history={}, enterprise_context=h.authorization.enterprise_context(c),
                document_context=dict(result_id='invoice-result', row_count=1, fields={'doc_num':'número de factura','doc_date':'fecha'},
                                      selected_ordinal=1, entity_label='factura', historical=True))
    try:
        preflight = await h.interpreter.interpret(text='¿De qué fecha es esta factura?', turn_id='preflight', **args)
        report['preflight'] = dict(metadata=h.interpreter.last_metadata, proposal=preflight)
        assert preflight['intent'] == 'DOCUMENT_REFERENCE' and preflight['action'] == 'SELECT_DOCUMENT'
        questions = ['Me podés decir cuáles son los productos de esta factura',
                     '¿Qué cantidad tiene?', '¿Y el primero?', 'Volvamos a la factura']
        if full_conversation:
            questions = ['Mostrame las últimas 5 facturas de venta de Telchi',
                         'De esas cinco, mostrame las tres más recientes',
                         '¿Cuál es el número de factura de la segunda de esas tres?',
                         '¿Y la primera?'] + questions + ['¿Cuál es su número?']
        for i, text in enumerate(questions, 1):
            response = await h.handle(event(text), replace(c, correlation_id=f'live-{i}'))
            audit = db.events[f'live-{i}']['telchi_assistant_v1']
            report['turns'].append(dict(question=text, classification=response.classification,
                text=response.text, proposal=audit['interpretation_proposed'],
                capability_calls=audit['capability_calls'], result=audit.get('execution_result'),
                metadata=h.interpreter.last_metadata))
            assert response.classification == 'DIRECT_AVAILABLE', response.text
        products = next(t['result'] for t in report['turns'] if t['result'] and t['result']['capability'] == 'sales.invoice_lines.v1')
        assert products['document']['doc_num'] == '260192728'
        assert products['rows'][0]['item_code'] == 'L00003'
        assert products['rows'][0]['quantity'] == '10'
        assert sum(t['capability_calls'] for t in report['turns']) == (3 if full_conversation else 1)
        # Ordinal 2 interpretation is tested with a two-row descriptor only.
        # The real invoice has ONE line: never pretend it has a second product.
        p = await h.interpreter.interpret(text='¿Cuánto tiene del segundo producto?', turn_id='ordinal-probe',
            result_context=dict(result_id='two-row-descriptor',row_count=2,fields={'quantity':'cantidad documental'},
                                selected_ordinal=None,entity_label='producto',historical=True), **args)
        report['second_product_descriptor_only'] = p
        assert p['intent'] == 'RESULT_REFERENCE' and p['result_reference'] == dict(result_id='two-row-descriptor',ordinal=2,field='quantity')
        report['LUNA_REAL_INTERPRETATION'] = 'PASS'
    except Exception as exc:
        report['LUNA_REAL_INTERPRETATION'] = 'FAIL'
        report['error'] = type(exc).__name__ + ': ' + str(exc)[:300]
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--full-conversation', action='store_true')
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit('Refusing to overwrite evidence')
    report = asyncio.run(probe(args.full_conversation))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False)+'\n')
    print(json.dumps({'LUNA_REAL_INTERPRETATION': report['LUNA_REAL_INTERPRETATION'], 'turns': len(report['turns'])}))


if __name__ == '__main__':
    main()
