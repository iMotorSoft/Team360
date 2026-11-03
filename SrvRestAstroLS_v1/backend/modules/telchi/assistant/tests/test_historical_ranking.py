"""Historical positions and partial answers; no live model or Foundation claims."""
import asyncio
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
import hashlib
import json

import pytest
from .test_product_monetary_ranking import ranked, proposal, ranking_fixture
from .test_sales_business_contract import setup
from .test_assistant import event, latest
from modules.telchi.assistant import state_engine as engine
from modules.telchi.assistant.capabilities import SalesCapabilities, format_result
from modules.telchi.assistant.historical_ranking import execute, format_historical
from modules.telchi.datalake import product_line_amount_ranking_query as ranking
from modules.telchi.datalake.tests.test_product_line_amount_ranking_query import db
from modules.telchi.datalake.tests.test_category_line_amount_query import con, OPTIONS

JULY = dict(start='2026-07-01', end_exclusive='2026-08-01')
AUGUST = dict(start='2026-08-01', end_exclusive='2026-09-01')


def state():
    out = engine.process(ranked(), proposal({'/ranking_target_item_code': 'SAP-A',
        '/period': JULY, '/comparison': AUGUST}), {}, 'history')
    assert out['committed']
    return out['state_after']


def fixture(options, *, target=True, partial=False):
    r = ranking_fixture()
    r['parameters'] = deepcopy(options)
    start = options['date_from']
    end = start[:8]+'24'
    r['coverage'].update(first_date=end, last_date=end)
    r['category_total'].update(first_date=end, last_date=end)
    if not target:
        r['full_breakdown'][0]['item_code'] = 'OTHER'
        r['rows'] = deepcopy(r['full_breakdown'])
        r['reconciliation']['breakdown_sha256'] = hashlib.sha256(json.dumps(r['full_breakdown'], sort_keys=True).encode()).hexdigest()
    if partial:
        r.update(accreditation='partial', exceptions=[dict(doc_entry='1',doc_num='123',line_num='0',item_code='SAP-A',
            header_currency='BS',line_currency='USD',original_line_total='19.25',excluded=True,
            reason='currency_not_accredited',impact='amount_and_position_may_change',audit_required=True)])
    return ranking.validate_result(options, r)


def test_two_periods_category_and_target_are_independent():
    async def run():
        calls = []
        async def query(options, **kwargs):
            calls.append(deepcopy(options))
            return fixture(options)
        caps = SalesCapabilities(ranking_query=query)
        s = state()
        assert caps.availability(s).allowed
        result = await caps.execute(s)
        assert [o['date_from'] for o in calls] == ['2026-07-01', '2026-08-01']
        assert all(o['category']=='LAB_FINISHED_PRODUCT' and 'item_code' not in o for o in calls)
        assert len(result['periods']) == 2
        text = format_result(result)
        assert 'Julio 2026: puesto 1' in text and 'Agosto 2026: puesto 1' in text
        assert 'cierre completo' in text
    asyncio.run(run())


@pytest.mark.parametrize('second', ['partial', 'failed', 'absent'])
def test_one_period_does_not_erase_another(second):
    async def run():
        async def query(options, **kwargs):
            if options['date_from'] == '2026-08-01':
                if second == 'failed':
                    raise ranking.RankingError('ranking_reconciliation_failed', {'difference':'9'})
                return fixture(options, target=second!='absent', partial=second=='partial')
            return fixture(options)
        result = await execute(state(), 'LAB_FINISHED_PRODUCT', query, 30)
        text = format_historical(result)
        assert 'Julio 2026: puesto 1' in text
        if second == 'partial':
            assert 'ranking parcial' in text and 'factura N.º 123' in text
            assert '19,25' in text and 'pueden cambiar' in text and 'USD 19,25' not in text
        elif second == 'failed':
            assert 'no asigno una cifra ni una posición' in text
            assert result['periods'][1]['evidence'] == {'difference':'9'}
        else:
            assert 'no aparece' in text and 'venta cero' in text
        assert 'Diferencia de importe' not in text
    asyncio.run(run())


def test_target_beyond_top_five_is_found():
    async def run():
        async def query(options, **kwargs):
            r = fixture(options)
            full = [dict(item_code=f'P{i}',description='Product',amount=str(100-i),line_count=1,document_count=1) for i in range(7)]
            full[-1]['item_code'] = 'SAP-A'
            r['full_breakdown'] = full
            r['rows'] = full[:5]
            r['category_total'].update(amount=str(sum(Decimal(row['amount']) for row in full)),product_count=7,line_count=7,document_count=1)
            r['classification']['quality_lines'] = {'VALIDATED':7}
            r['reconciliation'] = ranking.reconcile(full,r['category_total'])
            r['reconciliation']['breakdown_sha256'] = hashlib.sha256(json.dumps(full,sort_keys=True).encode()).hexdigest()
            return r
        r = await execute(state(),'LAB_FINISHED_PRODUCT',query,30)
        assert all(p['target']['position']==7 and p['comparable_products']==7 for p in r['periods'])
    asyncio.run(run())


@pytest.mark.parametrize('bad', ['A B', '', True, 'x'*51])
def test_bad_target_rejected(bad):
    out = engine.process(ranked(),proposal({'/ranking_target_item_code':bad}),{},'bad')
    assert not out['committed']


def test_new_query_clears_target_and_other_metrics_cannot_use_it():
    s = state()
    p = proposal({'/metric':'sales.coverage','/requested_metrics':['sales.coverage'],'/schema_version':2})
    p['intent']='NEW_QUERY'
    out = engine.process(s,p,{},'new')
    assert out['committed'] and not out['state_after'].get('ranking_target_item_code')
    assert not SalesCapabilities().availability(dict(s,metric='sales.net_amount',requested_metrics=['sales.net_amount'])).allowed


def test_internal_mixed_currency_only_verified_amounts_contribute(db):
    db.execute("INSERT INTO lines VALUES ('SAP_B1_HANA','INV1','1','2','R','19.25','USD','capture','2026-09-24')")
    exceptions = []
    full,total,_,_,rec = ranking.aggregate(db,'headers','lines','crosswalk','products',dict(OPTIONS,limit=5),exceptions=exceptions)
    assert full[0]['amount']=='70.130000' and total['line_count']==1
    assert Decimal(rec['difference'])==0
    assert exceptions[0]['item_code']=='R' and exceptions[0]['original_line_total']=='19.25'
    assert exceptions[0]['impact']=='amount_and_position_may_change'


def test_all_internal_rows_incompatible_no_fabricated_position(db):
    db.execute("UPDATE lines SET currency='USD' WHERE item_code='R'")
    exceptions=[]
    full,total,*_ = ranking.aggregate(db,'headers','lines','crosswalk','products',dict(OPTIONS,limit=5),exceptions=exceptions)
    assert not full and total['line_count']==0 and len(exceptions)==1


@pytest.mark.parametrize('sql', [
    "INSERT INTO lines SELECT * FROM lines",
    "UPDATE lines SET item_code='wrong' WHERE item_code='R'",
    "UPDATE crosswalk SET status='UNKNOWN' WHERE \"ItemCode\"='R'",
    "UPDATE lines SET raw_extraction_id='other' WHERE item_code='R'",
])
def test_partial_mode_does_not_hide_integrity_errors(db, sql):
    db.execute(sql)
    with pytest.raises(Exception):
        ranking.aggregate(db,'headers','lines','crosswalk','products',dict(OPTIONS,limit=5),exceptions=[])


def test_external_anomaly_is_audited_not_called_internal_exclusion():
    async def run():
        async def query(options, **kwargs):
            r = fixture(options)
            r['external_currency_anomalies'] = [dict(doc_num='123',item_code='RAW',header_currency='BS',line_currency='USD')]
            return r
        s = state()
        r = await execute(s,'LAB_FINISHED_PRODUCT',query,30)
        assert 'RAW' not in format_historical(r)
        s['ranking_detail']='exceptions'
        r = await execute(s,'LAB_FINISHED_PRODUCT',query,30)
        text = format_historical(r)
        assert 'RAW' in text and 'fuera de la categoría' in text
        assert 'No se excluyeron operaciones' in text
    asyncio.run(run())


def test_permission_checked_before_any_historical_period():
    async def run():
        s = state()
        p = proposal({'/'+k:v for k,v in s.items() if k not in {'pending','product_context'}})
        handler, store, calls, context = setup([p])
        async def forbidden(*args,**kwargs):
            raise AssertionError('must not access Foundation')
        handler.capabilities = SalesCapabilities(ranking_query=forbidden)
        response = await handler.handle(event('histórico'),context)
        assert response.classification=='DENIED' and latest(store)['capability_calls']==0
    asyncio.run(run())
