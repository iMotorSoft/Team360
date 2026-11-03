"""Closed conversational scope, permission reuse and physical presentation."""
from copy import deepcopy

import pytest

from modules.telchi.assistant import business_plan, state_engine as engine
from modules.telchi.assistant.capabilities import SalesCapabilities, format_result
from modules.telchi.datalake import commercial_line_amount_by_query as query, physical_sales_dimension as dim
from modules.telchi.datalake.tests.test_commercial_line_amount_by_query import con, options  # noqa: F401
from modules.telchi.datalake.tests.test_physical_sales_dimension import setup, source
from .test_business_conversation import scoped_state


def state(**values):
    return scoped_state(metric='sales.commercial_line_amount_by',requested_metrics=['sales.commercial_line_amount_by'],
                        group_by='physical_state',period=dict(start='2026-07-01',end_exclusive='2026-09-01'),**values)


def result(con):
    base=setup(con); cte,args,rows,total=source(con,base)
    for row in rows: row['label']=dim.LABELS[row['key']]
    p=dim.profile(con,cte,args)
    p.update(reference=query.PHYSICAL_REFERENCE,products_sha256=query.PHYSICAL_PRODUCTS_SHA256,
             crosswalk_sha256=query.PHYSICAL_CROSSWALK_SHA256)
    params=options(group_by='physical_state',filters=dict(category=None,item_code=None,card_code=None))
    return dict(capability=query.CAPABILITY,parameters=params,plan=query.plan_of(params),definition=query.MEASURE,
        currency='BS',rows=rows,full_breakdown=rows,total=total,universe_total=None,
        period_breakdown=[],exceptions=[],accreditation='verified',coverage=dict(first_date='2026-07-10',last_date='2026-08-11',complete=False),
        reconciliation=query.reconcile(rows,total,'physical_state'),physical_classification=p,
        source=dict(publication_id=query.PHYSICAL_PUBLICATION,snapshot_id=1408,updated_at='2026-10-30'),
        limitations=query.LIMITATIONS,read_only=True,sap_accessed=False)


def test_measured_read_default_does_not_override_explicit_budget():
    assert SalesCapabilities().timeout_seconds == 60
    assert SalesCapabilities(timeout_seconds=3).timeout_seconds == 3


def test_physical_scope_uses_existing_permission_and_never_truncates_categories():
    s=state(limit=3)
    engine.validate(s)
    assert SalesCapabilities().availability(s).allowed
    assert SalesCapabilities().required_permissions(s)==[query.PERMISSION]
    assert business_plan.build(s)['limit']==9


def test_exact_comparison_preserves_two_windows_without_counting_the_gap():
    s=state(comparison=dict(start='2026-06-01',end_exclusive='2026-06-30'),period_mode='compare')
    s['period']=dict(start='2026-07-01',end_exclusive='2026-07-30')
    engine.validate(s)
    assert SalesCapabilities().availability(s).allowed
    plan=business_plan.build(s)
    assert plan['periods']==[s['comparison'],s['period']]
    assert plan['breakdown_by']=='period'
    assert plan['date_from']=='2026-06-01' and plan['date_to_exclusive']=='2026-07-30'


def test_top_and_daily_are_closed_physical_views():
    for view in ('products','day'):
        s=state(breakdown_by=view,physical_focus='LIQUID',limit=5)
        engine.validate(s)
        plan=business_plan.build(s)
        assert plan['physical_focus']=='LIQUID' and plan['breakdown_by']==view
        if view=='products': assert plan['detail_limit']==5
    with pytest.raises(ValueError): engine.validate(state(physical_focus='inferred_from_name'))


def test_real_contract_and_answer_show_unknown_money_and_observation_not_effectiveness(con):
    r=result(con)
    assert query.validate_result(r['parameters'],r) is r
    text=format_result(r)
    assert 'Bs 170,00' in text and 'Bs 30,00' in text
    assert 'Sin clasificación explícita' in text and 'Medicamento (4' in text and 'No corresponde (5)' in text
    assert 'no necesariamente vigente' in text and 'antes de NC' in text
    assert query.PHYSICAL_PUBLICATION in text and query.PHYSICAL_REFERENCE in text
    assert len(text)<4096
    for key in ('products_sha256','crosswalk_sha256','reference'):
        changed=deepcopy(r); changed['physical_classification'][key]='tampered'
        with pytest.raises(ValueError): query.validate_result(changed['parameters'],changed)


def test_top_products_and_daily_series_preserve_the_full_universe(con):
    r=result(con)
    r['parameters'].update(breakdown_by='products',physical_focus='LIQUID',detail_limit=1)
    r['plan']=query.plan_of(r['parameters'])
    assert query.validate_result(r['parameters'],r) is r
    text=format_result(r)
    assert 'P1: Bs 170,00' in text and 'Total de líneas acreditadas: Bs 200,00' in text
    r['parameters'].pop('detail_limit'); r['parameters']['breakdown_by']='day'
    r['plan']=query.plan_of(r['parameters'])
    text=format_result(r)
    assert 'Evolución diaria' in text and '2026-07-10: LIQUID 120,00' in text
