"""Read-only controlled ASK/BLOCK/EXECUTE receipt validation; never sends messages.

Private manifest selects three real inbound UUIDs on one approved DEV Telchi
channel. Each case supplies kind, inbound_id, duplicate_receipt_file (the actual
successful webhook replay JSON). Operator must confirm visible device delivery
separately; HTTP acceptance alone cannot pass this probe.
"""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import uuid

import psycopg
from psycopg.rows import dict_row

from modules.console.login_cli import read_config, private_path, local_dsn, checked_target
from modules.db.settings import get_database_settings
from modules.messaging.repository import MessagingRepository
from modules.telchi.assistant.repository import ConversationRepository


def evaluate(events, cases, duplicates):
    if len(events) >= 100:
        raise ValueError('evidence_limit_reached')
    results = []
    for case in cases:
        iid = case['inbound_id']
        inbound = [e for e in events if e['id'] == iid and e['direction'] == 'inbound' and e['event_type'] == 'message']
        if len(inbound) != 1:
            raise AssertionError('one_inbound_required')
        source = inbound[0]
        payload = source['payload_jsonb']
        if payload.get('dev_adapter') or not payload.get('metadata', {}).get('raw_event_reference'):
            raise AssertionError('real_Evolution_ingress_required_not_HTTP_adapter')
        outbound = [e for e in events if e['direction'] == 'outbound' and e['event_type'] == 'message'
                    and e['correlation_id'] == iid]
        if len(outbound) != 1:
            raise AssertionError('exactly_one_outbound_required')
        reply = outbound[0]
        dispatch = payload.get('dispatch_result', {})
        audit = payload.get('telchi_assistant_v1', {})
        classification = dispatch.get('classification')
        expected = {'ASK': {'NEEDS_CLARIFICATION'}, 'BLOCK': {'DENIED', 'ERROR'}, 'EXECUTE': {'DIRECT_AVAILABLE'}}[case['kind']]
        if classification not in expected or dispatch.get('correlation_id') != iid or source['thread_id'] != reply['thread_id']:
            raise AssertionError('classification_or_correlation_mismatch')
        if case['kind'] != 'BLOCK' or audit:
            calls = 1 if case['kind'] == 'EXECUTE' else 0
            if audit.get('capability_calls') != calls or audit.get('execution_status') != ('executed' if calls else 'not_executed'):
                raise AssertionError('execution_contract_mismatch')
            if audit.get('response_prepared', {}).get('text') != dispatch.get('text'):
                raise AssertionError('prepared_response_changed')
        if reply['payload_jsonb'].get('text') != dispatch.get('text') or not reply['provider_message_id']:
            raise AssertionError('outbound_response_changed_or_unaccepted')
        callbacks = [e for e in events if e['event_type'] == 'status' and e['correlation_id'] == iid
                     and e['provider_message_id'] == reply['provider_message_id']
                     and e['transport_status'] in {'delivered', 'read'}
                     and e['payload_jsonb'].get('t_callback_ms')]
        if reply['transport_status'] not in {'delivered', 'read'} or not callbacks:
            raise AssertionError('effective_delivery_callback_missing')
        if duplicates[iid].get('results') != {'duplicate': 1}:
            raise AssertionError('actual_duplicate_webhook_response_required')
        results.append(dict(kind=case['kind'], inbound_id=iid, outbound_id=reply['id'],
            classification=classification, delivery=reply['transport_status'], correlation_id=iid,
            outbound_count=1, duplicate_response_observed=True,
            response_sha256=hashlib.sha256(dispatch['text'].encode()).hexdigest()))
    return dict(status='DELIVERY_OBSERVED', exchanges=results,
                E2E='NOT_DECLARED: requires human device confirmation and authorized business-result review')


async def run(args):
    cfg = read_config(args.auth_config)
    manifest = json.loads(private_path(args.manifest, existing=True).read_text())
    cases = manifest['cases']
    if len(cases) != 3 or {c['kind'] for c in cases} != {'ASK', 'BLOCK', 'EXECUTE'}:
        raise ValueError('exactly_three_controlled_contracts_required')
    ids = [str(uuid.UUID(c['inbound_id'])) for c in cases]
    if len(set(ids)) != 3 or any(i != c['inbound_id'] for i, c in zip(ids, cases)):
        raise ValueError('distinct_canonical_inbound_UUIDs_required')
    duplicates = {c['inbound_id']: json.loads(private_path(Path(c['duplicate_receipt_file']), existing=True).read_text()) for c in cases}
    # Existing operator connection, pinned READ ONLY. The semantics role is not
    # granted transport-table access just to run an evidence reader.
    dsn = get_database_settings().dsn
    local_dsn(dsn)
    async with await psycopg.AsyncConnection.connect(dsn, row_factory=dict_row, connect_timeout=5,
            options='-c statement_timeout=10000 -c lock_timeout=3000') as conn:
        async with conn.transaction():
            await conn.execute('SET TRANSACTION READ ONLY')
            await checked_target(conn, cfg['target'])
            binding = await MessagingRepository().binding(conn, workspace_slug=manifest['workspace_slug'],
                channel_alias=manifest['channel_alias'], provider='evolution', instance=manifest['instance'])
            if binding.environment != 'dev' or binding.module != 'telchi' or binding.tenant_id != 'telchi':
                raise PermissionError('approved_DEV_telchi_channel_required')
            events = await ConversationRepository().controlled_transport_evidence(conn, binding, ids)
            return evaluate(events, cases, duplicates)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('auth-config', 'manifest', 'output'):
        p.add_argument('--'+name, required=True, type=Path)
    args = p.parse_args()
    if args.output.exists():
        raise FileExistsError('new_report_path_required')
    try:
        report = asyncio.run(run(args))
    except Exception as exc:
        report = dict(status='NOT_PROVEN', error_class=type(exc).__name__, E2E='NOT_DECLARED')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as stream:
        json.dump(report, stream, indent=2)
    print('WHATSAPP_RECEIPTS='+report['status'])
    if report['status'] != 'DELIVERY_OBSERVED':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
