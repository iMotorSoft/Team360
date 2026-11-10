"""Opt-in LIVE validation of the product-ranking incident of 08/11/2026.

Run from backend:
    uv run python -m modules.telchi.assistant.tests.live_product_ranking_top_n

It uses the real interpreter (Luna), the real sales catalog and a real
read-only Foundation CURRENT read, with an in-process store and no WhatsApp,
Evolution, webhook or service restart. RBAC is resolved read-only from the
Console repository for the persisted DEV pilot identity; no grant is created.

Evidence goes to data/reports/telchi/top-n-product-ranking-v1/.
"""
import asyncio
from copy import deepcopy
from dataclasses import replace
import json
import os
from pathlib import Path
import sys

from dotenv import dotenv_values

from modules.messaging.handlers import ChannelContext, MessageContext, SenderIdentity
from modules.db.settings import get_database_settings
from modules.telchi.assistant.capabilities import SalesCapabilities
from modules.telchi.assistant.handler import BusinessAuthorization, BusinessPolicy, TelchiHandler
from modules.telchi.assistant.luna import LunaInterpreter, MODEL
from modules.telchi.assistant.state_engine import EMPTY, INTENT_V2

from .test_assistant import MemoryStore, event, latest

OUT = Path('../../data/reports/telchi/top-n-product-ranking-v1')
ENV = '../.env.backend-dev.local'
# Persisted DEV pilot identity of the audited conversation, never a fixture grant.
ENVIRONMENT, TENANT, WORKSPACE = 'dev', 'telchi', '3fb026a1-a4ba-44b3-b65b-fab452df7fc9'
CHANNEL, USER = '489e6f2c-8bac-4805-99ba-7dbe4d48c10e', '5015a69d-eb86-4ac9-b97f-c31dc06e2b59'
PERMISSION = 'telchi.sales.commercial_line_amount_by.read.v1'
OCTOBER = dict(start='2026-10-01', end_exclusive='2026-11-01')


def load_env():
    path = Path(ENV)
    if path.exists():
        for key, value in dotenv_values(path).items():
            if value is not None and key not in os.environ:
                os.environ[key] = value


async def effective_permissions():
    """Read-only resolution of the identity's real Console grants."""
    import psycopg
    from modules.console.repositories import PermissionConsoleRepository
    async with await psycopg.AsyncConnection.connect(get_database_settings().dsn) as conn:
        await conn.execute('SET TRANSACTION READ ONLY')
        return await PermissionConsoleRepository().list_effective_permissions(conn, WORKSPACE, USER)


def context(permissions, correlation_id):
    channel = ChannelContext(CHANNEL, 'evolution', 'instance', 'receiver', TENANT, WORKSPACE, TENANT)
    identity = SenderIdentity(USER, TENANT, WORKSPACE, permissions=frozenset(permissions))
    return MessageContext(channel, identity, '123456789', 'conversation', correlation_id, frozenset())


def seed(store, state):
    owner = [ENVIRONMENT, TENANT, WORKSPACE, CHANNEL, USER]
    store.states[tuple(owner) + ('conversation',)] = deepcopy(state)


def audit_of(store):
    return deepcopy(latest(store))


def scope_of(audit):
    state = audit.get('confirmed_state') or {}
    if audit.get('decision') == 'ASK' and state.get('pending'):
        state = state['pending']['proposed']
    return state


async def main():
    load_env()
    permissions = await effective_permissions()
    evidence = dict(model=MODEL, identity=dict(workspace=WORKSPACE, user=USER),
                    transport='in_process_handler; no WhatsApp/Evolution/webhook',
                    permissions=[p for p in permissions if p.startswith('telchi.')], turns=[],
                    checks={}, live_foundation=None)
    OUT.mkdir(parents=True, exist_ok=True)
    if PERMISSION not in permissions:
        evidence['status'] = 'BLOCKED'
        evidence['blocker'] = 'pilot identity has no commercial breakdown grant'
        (OUT / 'live.json').write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + '\n')
        print('BLOCKED: no commercial grant for the pilot identity')
        return

    interpreter = LunaInterpreter()
    # Pilot access is an in-process double (no transport, no approval artifact is
    # created). The commercial grants are the identity's real Console ones.
    policy = BusinessPolicy(TENANT, WORKSPACE, None, module_enabled=True,
                            whole_workspace_scope_verified=True,
                            pilot_access_check=lambda: None, pilot_user_id=USER)
    handler = TelchiHandler(store=MemoryStore(), authorization=BusinessAuthorization(policy),
                            interpreter=interpreter, capabilities=SalesCapabilities())
    store = handler.store

    # Direct-provider preflight: the real model and effort must be the audited ones.
    try:
        await interpreter.interpret(text='Importe de ventas de octubre de 2026',
                                    state=deepcopy(EMPTY | INTENT_V2), history={}, turn_id='preflight')
        evidence['luna_preflight'] = 'PASS'
    except Exception as exc:  # a technical failure is never a business answer
        evidence['luna_preflight'] = f'BLOCKED:{type(exc).__name__}'
        evidence['status'] = 'BLOCKED'
        (OUT / 'live.json').write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + '\n')
        print('LUNA_PREFLIGHT=BLOCKED', type(exc).__name__)
        return

    async def turn(text, seed_state=None, perms=None):
        if seed_state is not None:
            seed(store, seed_state)
        committed = len(store.audits)
        response = await handler.handle(
            event(text), context(perms or permissions, f'live-{len(evidence["turns"])}'))
        # A turn denied before the store boundary commits nothing: never reuse a
        # previous audit as if it belonged to this turn.
        audit = audit_of(store) if len(store.audits) > committed else {}
        audit.pop('owner', None)
        evidence['turns'].append(dict(text=text, classification=response.classification,
                                      committed=bool(audit), response=response.text, audit=audit))
        return response, audit

    # 1..5: the audited conversation, exactly as it happened.
    _, reset = await turn('nueva', seed_state={**deepcopy(EMPTY | INTENT_V2),
                                               'metric': 'sales.net_amount',
                                               'requested_metrics': ['sales.net_amount'],
                                               'period': dict(OCTOBER), 'limit': 10})
    proposed = (reset['confirmed_state'].get('pending') or {}).get('proposed') or {}
    evidence['checks']['NEW_QUERY_RESET'] = (
        'PASS' if proposed.get('period') is None
        and proposed.get('limit', 10) == 10
        and proposed.get('metric') is None
        and proposed.get('requested_metrics') == [] else 'FAIL')

    first, audit1 = await turn('dame los 3 productos mas vendidos de octubre 2026')
    ask = audit1['decision'] == 'ASK'
    if ask:
        _, audit2 = await turn('ambas')
    else:
        audit2 = audit1
    _, audit3 = await turn('quiero nombre de producto, importe total, cantidades totales para octubre 2026')

    def ranking_scope(audit):
        state = scope_of(audit)
        return (state.get('metric') == 'sales.commercial_line_amount_by'
                and state.get('group_by') == 'sap_product')

    def rows_of(audit):
        return ((audit.get('execution_result') or {}).get('rows') or [])

    def executes_top_three(audit):
        return (audit.get('execution_status') == 'executed' and ranking_scope(audit)
                and scope_of(audit).get('limit') == 3 and len(rows_of(audit)) == 3)

    evidence['checks']['REFORMULATION_RECOVERY'] = (
        'PASS' if audit3['execution_status'] == 'executed' and ranking_scope(audit3)
        and rows_of(audit3) and 'no admite límite' not in audit3['response_prepared']['text']
        and audit3['response_prepared']['classification'] == 'DIRECT_AVAILABLE' else 'FAIL')
    top = audit1 if executes_top_three(audit1) else audit2
    result = top.get('execution_result') or {}
    text = top['response_prepared']['text']
    rows = rows_of(top)
    from decimal import Decimal
    difference = (result.get('reconciliation') or {}).get('difference')
    quantity_difference = (result.get('reconciliation') or {}).get('quantity_difference')
    evidence['checks']['TOP_3_AMOUNT_AND_QUANTITY'] = (
        'PASS' if (top['response_prepared']['classification'] == 'DIRECT_AVAILABLE'
                   and len(rows) == 3 and all('quantity' in row for row in rows)
                   and text.count('unidades documentales') >= 3 and 'Bs ' in text
                   and difference is not None and Decimal(difference) == 0
                   and quantity_difference is not None and Decimal(quantity_difference) == 0)
        else 'FAIL')
    evidence['live_foundation'] = dict(
        publication=(result.get('source') or {}).get('publication_id'),
        snapshot=(result.get('source') or {}).get('snapshot_id'),
        limit=scope_of(top).get('limit'),
        rows=[dict(item_code=r['key'], description=r['label'], amount=r['amount'],
                   quantity=r['quantity']) for r in rows],
        reconciliation=result.get('reconciliation'))

    # 6: another criterion, another N, another period.
    _, by_quantity = await turn('dame los 3 productos mas vendidos por cantidad en octubre 2026')
    by_quantity_state = scope_of(by_quantity)
    evidence['checks']['TOP_3_BY_QUANTITY'] = (
        'PASS' if by_quantity['execution_status'] == 'executed'
        and by_quantity_state.get('ranking_by') == 'quantity'
        and len((by_quantity.get('execution_result') or {}).get('rows') or []) == 3 else 'FAIL')
    _, by_n = await turn('los 5 productos mas vendidos de septiembre de 2026')
    by_n_state = scope_of(by_n)
    evidence['checks']['TOP_5_OTHER_PERIOD'] = (
        'PASS' if by_n['execution_status'] == 'executed' and by_n_state.get('limit') == 5
        and by_n_state.get('period') == dict(start='2026-09-01', end_exclusive='2026-10-01') else 'FAIL')

    # 7: «ambas» completes an open metric clarification for a product ranking.
    # A strongly ambiguous wording (no N, no measure) no longer needs a question;
    # the historical pending question is seeded so the answer path is exercised.
    await turn('nueva')
    _, ambiguous = await turn('dame los productos mas vendidos de octubre 2026')
    if ambiguous['decision'] == 'ASK':
        _, completed = await turn('ambas')
    else:
        completed = ambiguous

    from modules.telchi.assistant import state_engine
    seeded = deepcopy(EMPTY | INTENT_V2)
    seeded['period'] = dict(OCTOBER)
    seeded['pending'] = dict(
        spec={'slot': 'metric', 'question': '¿Querés el importe, las cantidades o ambas?'},
        proposed={**deepcopy(EMPTY | INTENT_V2), 'period': dict(OCTOBER),
                  'group_by': 'sap_product', 'limit': 3, 'ranking_by': 'amount'},
        base_state_hash=state_engine.state_hash(seeded), source_turn_id='seeded-pending')
    _, answered = await turn('ambas', seed_state=seeded)

    def both_columns(audit):
        text = audit['response_prepared']['text']
        return (audit.get('execution_status') == 'executed' and ranking_scope(audit)
                and bool(rows_of(audit)) and all('quantity' in r for r in rows_of(audit))
                and 'unidades documentales' in text and 'Bs ' in text)

    asked = [t for t, was_asked in ((audit2, ask), (completed, ambiguous['decision'] == 'ASK')) if was_asked]
    evidence['clarification'] = dict(
        questions=[(t['confirmed_state'].get('pending') or {}).get('spec')
                   for t in (audit1, ambiguous) if t['decision'] == 'ASK'],
        asked_live=len(asked), answered_seeded=both_columns(answered),
        text=answered['response_prepared']['text'])
    evidence['checks']['CLARIFICATION_AMBAS'] = (
        'PASS' if (both_columns(answered) and all(both_columns(t) for t in asked)
                   if asked else both_columns(answered) and both_columns(audit2)
                   and both_columns(completed)) else 'FAIL')

    # 7: revocation and isolation.
    denied, denied_audit = await turn('dame los 3 productos mas vendidos de octubre 2026',
                                      perms=[p for p in permissions if p != PERMISSION])
    evidence['checks']['RBAC_REGRESSION'] = (
        'PASS' if denied.classification == 'DENIED'
        and (denied_audit.get('capability_calls') == 0 and denied_audit.get('decision') == 'DENIED')
        else 'FAIL')

    # 8: the previous contextual fix (4 % / 96 %) is re-accredited by its own
    # live gate (live_contextual_components), which needs the monetary-context
    # repository that this in-process store does not provide.
    contextual = OUT.parent / 'contextual-components-v1' / 'live.json'
    evidence['contextual_gate'] = str(contextual)
    evidence['checks']['PREVIOUS_CONTEXTUAL_FIX'] = (
        'PASS' if contextual.exists() and json.loads(contextual.read_text()).get('pass') is True
        else 'NOT_RUN_HERE')

    evidence['checks']['SIX_GATES'] = 'PASS' if all(
        v == 'PASS' for v in evidence['checks'].values()) else 'DEGRADED'
    evidence['status'] = evidence['checks']['SIX_GATES']
    (OUT / 'live.json').write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps(evidence['checks'], indent=2))
    print('LIVE_FOUNDATION', json.dumps(evidence['live_foundation'], ensure_ascii=False)[:800])


if __name__ == '__main__':
    asyncio.run(main())
    sys.exit(0)