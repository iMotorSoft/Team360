"""Opt-in read-only reference + real Luna/Foundation regression; NO outbound transport.

Run from backend: uv run python -m modules.telchi.assistant.tests.live_horizontal_sales --output <new.json>
Identity, RBAC and conversation persistence are fixtures, explicitly not channel activation.
"""
import argparse
import asyncio
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from modules.db.settings import get_database_settings
from modules.telchi.assistant.capabilities import SalesCapabilities
from modules.telchi.assistant.handler import BusinessAuthorization, BusinessPolicy, TelchiHandler
from modules.telchi.assistant.luna import LunaInterpreter
from modules.telchi.datalake.foundation_reader import FoundationReader
from .test_assistant import MemoryStore, context, event, latest
from .test_horizontal_sales import QUESTIONS
from .test_sales_monetary import GRANT

EVENT_ID = '7b132911-ccb0-431d-91b8-efa29ab2305e'


async def trace():
    async with await psycopg.AsyncConnection.connect(get_database_settings().dsn, row_factory=dict_row) as c:
        await c.execute('SET TRANSACTION READ ONLY')
        await c.execute("SET LOCAL statement_timeout='5s'")
        row = await (await c.execute('''SELECT id::text,thread_id::text,occurred_at_utc,
            payload_jsonb->>'text' AS text,payload_jsonb->'telchi_assistant_v1' AS audit
            FROM message_events WHERE id=%s AND direction='inbound' ''', (EVENT_ID,))).fetchone()
        if not row:
            raise ValueError('original_trace_missing')
        audit = row['audit']
        # Never export sender, credentials or identity IDs to the evidence or interpreter.
        safe = {k:v for k,v in audit.items() if k not in ('owner','pilot_approval_sha256')}
        previous = await (await c.execute('''SELECT id::text,
            payload_jsonb->'telchi_assistant_v1'->'confirmed_state' AS state
            FROM message_events WHERE thread_id=%s AND occurred_at_utc<%s
            AND direction='inbound' AND payload_jsonb ? 'telchi_assistant_v1'
            ORDER BY occurred_at_utc DESC LIMIT 20''', (row['thread_id'], row['occurred_at_utc']))).fetchall()
        return dict(event_id=row['id'], received_utc=str(row['occurred_at_utc']),
                    text=row['text'], audit=safe,
                    retained_history={r['id']:r['state'] for r in reversed(previous)})


def reference():
    r = FoundationReader()
    out = dict(read_only=True, sap_accessed=False, queries=[])
    with r.connector.session(read_only=True) as c:
        c.execute('SET threads=2')
        c.execute("SET memory_limit='512MB'")
        c.execute("SET max_temp_directory_size='0B'")
        a = r.resolve_on(c)
        out['source'] = dict(publication_id=a.foundation_publication_id,
            snapshot_id=a.ducklake_snapshot_id, updated_at=a.foundation_data_as_of)
        # Different SQL shape from the capability: independent grouped aggregates,
        # all channels/currencies/statuses observed; no reuse of runtime SQL or totals.
        for kind, rel in [('invoices', a.sales('sales_document')), ('credits', a.credit_memo('credit_memo_document'))]:
            sql = f'''SELECT sales_channel_code,sales_channel_semantic_status,currency,canceled,
                COUNT(*) documents,COUNT(DISTINCT doc_entry) distinct_documents,COUNT(doc_total) amounts,
                SUM(CAST(doc_total AS DECIMAL(38,6))) amount,MIN(doc_date) first_date,MAX(doc_date) last_date
                FROM {rel} WHERE source_system=? AND doc_date>=? AND doc_date<? GROUP BY ALL'''
            args = ['SAP_B1_HANA','2026-08-01','2026-09-01']
            cur = c.execute(sql, args)
            rows = [dict(zip([x[0] for x in cur.description], row)) for row in cur.fetchall()]
            out['queries'].append(dict(kind=kind, sql=sql, parameters=args, rows=rows))
            selected = [row for row in rows if row['sales_channel_code']=='HORIZONTAL'
                        and row['currency']=='BS' and row['canceled']=='N']
            if len(selected) != 1 or selected[0]['sales_channel_semantic_status'] != 'CONFIRMED':
                raise ValueError('reference_channel_not_confirmed')
            selected = selected[0]
            if not selected['documents'] == selected['distinct_documents'] == selected['amounts']:
                raise ValueError('reference_integrity_failed')
            out[kind] = selected['amount']
        out['net'] = out['invoices'] - out['credits']
        out['publication_unchanged'] = r.resolve_on(c).foundation_publication_id == a.foundation_publication_id
    out['limitations'] = ('Materialized DMS series classification. Full DMS/U_ORIGIN census reconciliation, '
        'cross-channel credit attribution, unposted DMS returns and full historical coverage not certified. '
        'Active headers by DocDate in BS, source taxes/discounts retained; not collections.')
    return out


async def run():
    original = await trace()
    ref = reference()
    report = dict(timestamp=datetime.now(timezone.utc).isoformat(), original_trace=original,
        reference=ref, transport_calls=0, database_writes=0,
        simulated=['identity', 'RBAC', 'conversation persistence', 'transport'], turns=[])
    c = context()
    c = replace(c, sender_identity=replace(c.sender_identity,
        permissions=frozenset({'fixture.business.read', GRANT})))
    for n, text in enumerate([original['text'], *QUESTIONS]):
        store, llm = MemoryStore(), LunaInterpreter(max_attempts=1)
        owner = [c.channel.environment,c.channel.tenant_id,c.channel.workspace_id,c.channel.channel_id,c.sender_identity.user_id]
        key = tuple(owner) + (c.conversation_id,)
        # Replay only query context, never the inbound or provider pipeline.
        store.states[key] = deepcopy(original['audit']['previous_state'])
        store.history[key] = deepcopy(original['retained_history'])
        handler = TelchiHandler(store=store, authorization=BusinessAuthorization(
            BusinessPolicy('telchi','workspace','fixture.business.read',True,True)),
            interpreter=llm, capabilities=SalesCapabilities())
        response = await handler.handle(event(text), replace(c,correlation_id=f'horizontal-local-{n}'))
        audit = latest(store)
        result = audit.get('execution_result')
        passed = (response.classification == 'DIRECT_AVAILABLE' and audit['capability_calls']==1
            and result['period'] == dict(date_from='2026-08-01',date_to_exclusive='2026-09-01',currency='BS',sales_channel='HORIZONTAL')
            and result['source'] == ref['source']
            and Decimal(result['rows'][0]['billed_amount']) == ref['invoices']
            and Decimal(result['rows'][0]['credit_amount']) == ref['credits']
            and Decimal(result['rows'][0]['net_amount']) == ref['net'])
        report['turns'].append(dict(question=text, classification=response.classification,
            response=response.text, interpretation=audit['interpretation_proposed'],
            confirmed_state=audit['confirmed_state'], capability_calls=audit['capability_calls'],
            execution_result=result, luna_metadata=llm.last_metadata, luna_failure=llm.last_failure,
            reference_parity=passed))
        if not passed:
            break
    report['LOCAL_BUSINESS_REGRESSION'] = len(report['turns'])==5 and all(t['reference_parity'] for t in report['turns'])
    report['WHATSAPP_E2E'] = 'NOT_RUN'
    report['READY_FOR_HORIZONTAL_SALES_RETEST'] = 'NO: DEV runtime admission/gates not reaccredited or reopened by this probe'
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output',required=True)
    args = parser.parse_args()
    target = Path(args.output)
    if target.exists():
        raise SystemExit('Refusing overwrite')
    report = asyncio.run(run())
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(report,indent=2,ensure_ascii=False,default=str)+'\n')
    print(json.dumps({k:report[k] for k in ('LOCAL_BUSINESS_REGRESSION','WHATSAPP_E2E','READY_FOR_HORIZONTAL_SALES_RETEST')}))


if __name__ == '__main__':
    main()
