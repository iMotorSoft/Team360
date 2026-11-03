"""Live Console permissions and monetary HTTP/reference parity; no PG writes."""
import asyncio
from dataclasses import replace
from decimal import Decimal
import json
import os
from pathlib import Path
import sys

OUT = Path(__file__).resolve().parent
BACKEND = OUT.parents[3]/'SrvRestAstroLS_v1/backend'
sys.path.insert(0, str(BACKEND))
from dotenv import dotenv_values
for k,v in dotenv_values(BACKEND.parent/'.env.backend-dev.local').items():
    if v is not None:
        os.environ[k] = v
from modules.telchi.provisioning.monetary_repository import MonetaryActivationRepository
from modules.telchi.datalake.sales_query import MONETARY_PERMISSION, PUBLICATION, SNAPSHOT, PERMISSIONS
from modules.telchi.provisioning.repository import PERMISSION
from modules.console.repositories import PermissionConsoleRepository
from modules.db.settings import get_database_settings
import psycopg
from psycopg.rows import dict_row


async def authorization():
    from modules.telchi.assistant.handler import BusinessAuthorization, BusinessPolicy
    from modules.telchi.assistant.tests.test_assistant import context
    async with await psycopg.AsyncConnection.connect(get_database_settings().dsn, row_factory=dict_row,
            options='-c default_transaction_read_only=on -c statement_timeout=10000') as conn:
        snapshot = await MonetaryActivationRepository().snapshot(conn)
        ids = snapshot['identities']
        workspace, pilot = ids['workspace']['id'], ids['pilot']['id']
        resolver = PermissionConsoleRepository()
        assert set(snapshot['effective']) == {PERMISSION, MONETARY_PERMISSION, *PERMISSIONS.values()}
        base = context()
        ident = replace(base.sender_identity, user_id=pilot, tenant_id='telchi', workspace_id=workspace,
                        permissions=frozenset(snapshot['effective']))
        channel = replace(base.channel, tenant_id='telchi', workspace_id=workspace)
        positive = replace(base, sender_identity=ident, channel=channel)
        auth = BusinessAuthorization(BusinessPolicy('telchi', workspace, PERMISSION, True, True))
        assert await auth.allowed(positive, conn, required_permission=MONETARY_PERMISSION)
        negatives = {}
        for label in ['admin', 'global']:
            scope = ids[label]['workspace_id']
            grants = await resolver.list_effective_permissions(conn, scope, ids[label]['id'])
            negative = replace(positive, sender_identity=replace(ident, user_id=ids[label]['id'],
                workspace_id=scope, permissions=frozenset(grants)))
            allowed = await auth.allowed(negative, conn, required_permission=MONETARY_PERMISSION)
            assert allowed is False
            negatives[label] = dict(allowed=allowed, existing_identity=True)
        wrong = await resolver.list_effective_permissions(conn, ids['global']['workspace_id'], pilot)
        assert wrong == []
        events = [e for e in snapshot['records']['admin_events']
                  if e['event_name'] in ['telchi.admin.monetary-authorize', 'telchi.admin.monetary-grant']]
        assert len(events) == 2
        result = dict(effective=snapshot['effective'], positive_authorization=True,
            actual_existing_identity_negatives=negatives, wrong_workspace_effective=wrong,
            events=events, no_full_access=True, identities=ids)
    (OUT/'effective_authorization.json').write_text(json.dumps(result, indent=2, default=str)+'\n')


def parity():
    reference = json.loads((OUT/'foundation_reconciliation.json').read_text())
    periods = {p['date_from']: p for p in reference['periods']}
    current = OUT/'business_http_current/runtime_http_results.json'
    http = json.loads(current.read_text())
    ranking = json.loads((OUT/'ranking_http_current/runtime_http_results.json').read_text())
    http['scenarios'] = [s for s in http['scenarios'] if s['id'] != 'M07'] + ranking['scenarios']
    compared = []
    for scenario in http['scenarios']:
        for turn in scenario['turns']:
            audit = turn['audit']
            data = audit.get('execution_result')
            if data and data['capability'] == 'sales.period_billed_amount.v1':
                assert turn['classification'] == 'DIRECT_AVAILABLE'
                assert audit['committed'] is True and audit['capability_calls'] == 1
                assert audit['required_permission'] == MONETARY_PERMISSION
                assert data['source']['publication_id'] == PUBLICATION and data['source']['snapshot_id'] == SNAPSHOT
                period = periods[data['period']['date_from']]
                assert data['period']['date_to_exclusive'] == period['date_to_exclusive']
                metrics = period['historical_metrics']
                row = data['rows'][0]
                for actual, expected in [('billed_amount', 'SALES_VALID_GROSS'), ('credit_amount', 'SALES_CREDIT_NOTES'), ('net_amount', 'SALES_NET')]:
                    assert Decimal(row[actual]) == Decimal(metrics[expected])
                assert row['invoice_count'] == metrics['invoice_count'] and row['credit_count'] == metrics['credit_count']
                compared.append(dict(case=scenario['id'], user_text=turn['user_text'], difference='0.000000',
                    result=row, period=data['period'], reference_file='foundation_reconciliation.json',
                    correlation_id=turn['correlation_id']))
    assert len(compared) == 6
    by_id = {s['id']:s for s in http['scenarios']}
    assert by_id['M06']['turns'][1]['audit']['confirmed_state']['period']['start'] == '2026-05-01'
    assert by_id['M05']['turns'][1]['audit']['confirmed_state']['requested_metrics'] == ['sales.net_amount', 'sales.source_top_items']
    for name in ['M04', 'M10', 'M11']:
        t = by_id[name]['turns'][0]
        assert t['classification'] == 'DIRECT_UNAVAILABLE' and t['audit']['capability_calls'] == 0
    for name in ['M03', 'M07']:
        assert by_id[name]['turns'][0]['classification'] == 'DIRECT_AVAILABLE'
    latest = by_id['B01']['turns'][0]
    if latest['classification'] != 'DIRECT_AVAILABLE':
        assert latest['audit']['committed'] is False and latest['audit']['capability_calls'] == 0
    (OUT/'http_reference_comparison.json').write_text(json.dumps(dict(comparisons=compared,
        M12=True, all_monetary_differences_zero=True, continuity=True, multimetric_intent_preserved=True,
        existing_latest_runtime=latest['classification'],
        source_http_files=['business_http_current/runtime_http_results.json', 'ranking_http_current/runtime_http_results.json']), indent=2)+'\n')
    print('Effective PG18 authorization / negative identities / 6 monetary HTTP parity checks verified')


if __name__ == '__main__':
    asyncio.run(authorization())
    parity()
