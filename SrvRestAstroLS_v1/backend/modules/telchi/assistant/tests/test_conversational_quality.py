"""Regression replay of audited 19/10 turns, deterministic arithmetic and fences."""
import asyncio
from copy import deepcopy
from dataclasses import replace
import json
import os
from pathlib import Path

import pytest

from modules.telchi.assistant import monetary_comparison as mc, state_engine as se
from modules.telchi.assistant.handler import PostgresConversationStore
from .test_assistant import event, run, proposal
from .test_result_references import persistent_handler

FIXTURE = json.loads((Path(__file__).parent/'fixtures/conversational_quality_audited.json').read_text())['turns']
OWNER = ['dev','telchi','workspace','channel','user']


@pytest.fixture(autouse=True)
def historical_monetary_binding(monkeypatch):
    # Replay the immutable audited payload under its ORIGINAL binding. Never
    # relabel historical amounts as CURRENT, or relax the runtime validator.
    from modules.telchi.datalake import sales_query
    historical = FIXTURE[1]['audit']['execution_result']['source']['publication_id']
    if historical != sales_query.PUBLICATION:
        assert mc.accredited(FIXTURE[1]['audit'], FIXTURE[1]['id'], OWNER) is None
    monkeypatch.setattr(sales_query, 'PUBLICATION', historical)


def results():
    return [mc.accredited(t['audit'], t['id'], OWNER) for t in FIXTURE[1:3]]


def compare(mode='difference', reverse=False):
    a,b = results()
    if reverse:
        a,b = b,a
    return dict(intent='MONETARY_COMPARISON', action='CALCULATE', clarification=None,
                comparison=dict(target_id=a['result_id'], baseline_id=b['result_id'], mode=mode))


def test_audited_root_cause_and_equivalent_turns():
    failed, succeeded = FIXTURE[:2]
    assert failed['audit']['previous_state'] == succeeded['audit']['previous_state']
    assert '/product_context' in failed['audit']['interpretation_proposed']['state_delta']['unset']
    # Direct patch rejects the service-owned field; only NEW_QUERY disposal is safe.
    with pytest.raises(ValueError, match='unknown_path'):
        se.patch(failed['audit']['previous_state'], failed['audit']['interpretation_proposed']['state_delta'])
    for turn in FIXTURE[:3]:
        a = turn['audit']
        p = se.process(a['previous_state'], a['interpretation_proposed'], {}, turn['id'])
        assert p['committed'] is True
        assert p['state_after']['period'] == (FIXTURE[1]['audit']['confirmed_state']['period'] if turn == failed else a['confirmed_state']['period'])
    bad = deepcopy(failed['audit']['interpretation_proposed'])
    bad['state_delta']['set']['/product_context'] = {'rows': []}
    assert not se.process(failed['audit']['previous_state'], bad, {}, 'bad')['committed']
    bad = deepcopy(failed['audit']['interpretation_proposed'])
    bad['intent'] = 'REFINE'
    assert not se.process(failed['audit']['previous_state'], bad, {}, 'bad')['committed']
    bad['state_delta']['unset'] = ['/pending']
    assert not se.process(failed['audit']['previous_state'], bad, {}, 'bad')['committed']
    bad = deepcopy(failed['audit']['interpretation_proposed'])
    bad['state_delta']['unset'].append('/product_context')
    assert not se.process(failed['audit']['previous_state'], bad, {}, 'bad')['committed']


def test_exact_arithmetic_order_percentage_and_partial():
    record,text = mc.calculate(compare(), results(), OWNER)
    assert record['difference'] == '-1673673.340000'
    assert 'BS -1.673.673,34' in text
    assert 'parcial' in text and 'no es una caída' in text
    assert record['target']['partial'] and not record['baseline']['partial']
    record,text = mc.calculate(compare('percent'), results(), OWNER)
    assert '-15,84 %' in text
    assert record['baseline']['amount'] == '10565113.130000'
    record,text = mc.calculate(compare(reverse=True), results(), OWNER)
    assert record['difference'] == '1673673.340000'
    assert 'BS 1.673.673,34' in text
    assert all('amount' not in r for r in mc.descriptors(results())['results'])
    assert '8891439' not in str(mc.descriptors(results()))


@pytest.mark.parametrize('mutation', ['currency','metric','definition','source','owner','overlap','zero','empty','missing','extra'])
def test_incompatible_ambiguous_and_missing(mutation):
    rs,p = results(),compare('percent')
    if mutation in {'currency','metric','definition','source','owner'}:
        rs[0][mutation] = 'different'
    elif mutation == 'overlap':
        rs[0]['period'] = deepcopy(rs[1]['period'])
    elif mutation == 'zero':
        rs[1]['amount'] = '0'
    elif mutation == 'empty':
        rs = []
    elif mutation == 'missing':
        p['comparison']['baseline_id'] = 'unaccredited'
    else:
        p['amount'] = 1
    with pytest.raises((ValueError, KeyError)):
        mc.calculate(p, rs, OWNER)


@run
async def test_handler_local_reauthorization_and_cache(monkeypatch):
    handler,db,llm,calls,checks,c = persistent_handler(monkeypatch,[compare(),compare('percent')])
    # Repository port is covered separately with actual PostgreSQL.
    db.thread = {'telchi_assistant_v1': dict(owner=OWNER, state=deepcopy(FIXTURE[2]['audit']['confirmed_state']),
        history={t['id']:t['audit']['confirmed_state'] for t in FIXTURE[1:3]},
        history_order=[t['id'] for t in FIXTURE[1:3]])}
    for t in FIXTURE[1:3]:
        db.events[t['id']] = {'environment':'dev','telchi_assistant_v1':deepcopy(t['audit'])}
    async def load(*args):
        return results()
    monkeypatch.setattr(handler.store.repository,'load_monetary_results',load)
    async def allowed(ctx,conn=None,*,required_permission=None):
        return required_permission in (None,mc.MONETARY_PERMISSION)
    handler.authorization.allowed = allowed
    for n in (3,4):
        response = await handler.handle(event(),replace(c,correlation_id=f'local-{n}'))
        assert response.classification == 'DIRECT_AVAILABLE', response.text
        a = db.events[f'local-{n}']['telchi_assistant_v1']
        assert a['capability_calls'] == 0 and a['execution_result'] is None
        assert a['confirmed_state'] == FIXTURE[2]['audit']['confirmed_state']
    assert not calls
    async def revoked(ctx,conn=None,*,required_permission=None):
        return required_permission is None
    handler.authorization.allowed = revoked
    cached = await handler.handle(event(),replace(c,correlation_id='local-4'))
    assert cached.classification == 'DENIED'
    async def revoke_during(**kwargs):
        handler.authorization.allowed = revoked
        return compare()
    handler.authorization.allowed = allowed
    handler.interpreter.interpret = revoke_during
    assert (await handler.handle(event(),replace(c,correlation_id='local-5'))).classification == 'DENIED'
    assert not calls


@run
async def test_handler_missing_results_never_executes(monkeypatch):
    handler,db,_,calls,_,c = persistent_handler(monkeypatch,[compare()])
    response = await handler.handle(event('¿Cuál fue la diferencia?'),c)
    assert response.classification == 'NEEDS_CLARIFICATION'
    assert not calls
    assert db.events[c.correlation_id]['telchi_assistant_v1']['capability_calls'] == 0


@pytest.mark.parametrize('field,value', [('owner', []), ('business_rbac_verified', False),
    ('execution_status','failed'), ('required_permission','other')])
def test_only_accredited_audits(field,value):
    audit = deepcopy(FIXTURE[1]['audit'])
    audit[field] = value
    assert mc.accredited(audit,'id',OWNER) is None


@pytest.mark.skipif(os.getenv('TEAM360_RESULT_REFERENCE_POSTGRES_TEST') != '1', reason='PG opt-in required')
def test_postgres_reload_local_calculation(monkeypatch):
    async def exercise():
        from contextlib import asynccontextmanager
        from psycopg.types.json import Jsonb
        from modules.db.pool import create_pool,open_pool,close_pool
        from modules.db.settings import get_database_settings
        pool = create_pool(get_database_settings(min_size=1,max_size=1))
        await open_pool(pool)
        try:
            async with pool.connection() as conn:
                await conn.execute('CREATE TEMP TABLE message_threads (id text, channel_id text, workspace_id text, metadata_jsonb jsonb)')
                await conn.execute('CREATE TEMP TABLE message_events (id text,thread_id text,channel_id text,workspace_id text,direction text,event_type text,payload_jsonb jsonb)')
                history = {t['id']:t['audit']['confirmed_state'] for t in FIXTURE[1:3]}
                saved = dict(owner=OWNER,state=FIXTURE[2]['audit']['confirmed_state'],history=history,history_order=list(history))
                await conn.execute("INSERT INTO message_threads VALUES ('conversation','channel','workspace',%s)",(Jsonb({'telchi_assistant_v1':saved}),))
                for t in FIXTURE[1:3]:
                    await conn.execute("INSERT INTO message_events VALUES (%s,'conversation','channel','workspace','inbound','message',%s)",
                        (t['id'],Jsonb({'environment':'dev','telchi_assistant_v1':t['audit']})))
            handler,_,llm,calls,_,c = persistent_handler(monkeypatch,[compare(),compare('percent')])
            @asynccontextmanager
            async def tx(_):
                async with pool.connection() as conn:
                    yield conn
            monkeypatch.setattr('modules.telchi.assistant.handler.transaction',tx)
            async def allowed(ctx,conn=None,*,required_permission=None):
                return required_permission in (None,mc.MONETARY_PERMISSION)
            handler.authorization.allowed = allowed
            for n in (3,4):
                async with pool.connection() as conn:
                    await conn.execute("INSERT INTO message_events VALUES (%s,'conversation','channel','workspace','inbound','message',%s)",
                        (f'pg-{n}',Jsonb({'environment':'dev'})))
                handler.store = PostgresConversationStore(pool)
                response = await handler.handle(event(),replace(c,correlation_id=f'pg-{n}'))
                assert response.classification == 'DIRECT_AVAILABLE', response.text
            assert not calls
            assert llm.calls[1]['monetary_context']['previous'] == {
                k: compare()['comparison'][k] for k in ('target_id','baseline_id')}
            async with pool.connection() as conn:
                row = await (await conn.execute("SELECT payload_jsonb FROM message_events WHERE id='pg-4'")).fetchone()
                audit = row['payload_jsonb']['telchi_assistant_v1']
                assert audit['capability_calls'] == 0 and audit['monetary_calculation']['difference'] == '-1673673.340000'
                for key,value in [('workspace_id','other'),('tenant_id','other')]:
                    changed = replace(c,channel=replace(c.channel,**{key:value}))
                    assert (await handler.handle(event(),changed)).classification != 'DIRECT_AVAILABLE'
        finally:
            await close_pool(pool)
    asyncio.run(exercise())
