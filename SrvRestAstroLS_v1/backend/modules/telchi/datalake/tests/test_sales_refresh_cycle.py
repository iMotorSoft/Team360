from copy import deepcopy

import pytest

from modules.telchi.datalake import sales_refresh_cycle as cycle, sales_continuity as cap, sales_incremental as inc
from modules.telchi.datalake.foundation_manifest import validate_manifest
from modules.telchi.datalake.foundation_publication import READY_TO_COMMIT
from modules.telchi.datalake.sales_facts_transition import make_candidate
from .test_receivables_collections_foundation import store
from .test_sales_facts_transition import built
from .test_sales_continuity import pair, Guard
from .test_sales_controlled_block import source


@pytest.fixture
def future(store,built):
    _,candidate,_=built
    store.create_candidate(candidate)
    store.set_status(candidate.foundation_publication_id,READY_TO_COMMIT)
    store.logical_commit(candidate.foundation_publication_id)
    base=store.get(candidate.foundation_publication_id)
    plan=cycle.make_plan(base=base,published_end='2026-10-30',end_exclusive='2026-10-31',
        authorization_reference='ISOLATED_SOURCE_FIXTURE',overlap_days=1,late_dates=['2026-09-01'],
        late_change_evidence={'receipt':'fixture-modification-observation'})
    return base,plan


def test_bounded_overlap_and_late_dates_no_global_docentry(future):
    _,plan=future
    cycle.validate_plan(plan);cap.validate_plan(plan)
    assert len(plan['windows'])==6
    assert plan['global_change_watermark'] is None
    assert {w['start'] for w in plan['windows']}=={'2026-09-01','2026-10-29','2026-10-30'}
    assert 'DocEntry' not in str(plan)
    for key,value in [('budget',{}),('windows',[]),('global_change_watermark',123),('publication','AUTHORIZED')]:
        bad=deepcopy(plan);bad[key]=value
        with pytest.raises(ValueError):cycle.validate_plan(bad)
    with pytest.raises(ValueError):cycle.window_set('2026-10-30','2027-01-01',7,[])


def test_capture_cancelled_late_document_resume_and_upsert(tmp_path,future):
    _,plan=future
    h,rows=pair();h['CANCELED']='Y';rows[0]['CANCELED']='Y'
    s,_=source([[h],rows]+[[]]*5)
    root=tmp_path/'raw/sap'/cycle.CONTRACT/'future'
    root.parent.mkdir(parents=True,exist_ok=True)
    assert cycle.capture(root,plan,s,sleep=lambda _:None,guard=Guard())['status']=='CAPTURED_PASS'
    recovered=cap.recover(root)
    assert len(recovered[4])==6
    s,_=source([])
    assert not cycle.capture(root,plan,s,sleep=lambda _:None,guard=Guard())['queries_this_session']
    candidate=inc.transform_capture('sales',rows,dict(extraction_id='fixture',source_as_of=inc.now()))
    assert candidate.tables['sales_document'][0]['canceled']=='Y'
    assert 'CANCELED' not in cap.header_sql('sales').split('WHERE')[-1]


def test_incremental_transition_preserves_coverage_and_rejects_forgery(tmp_path,store,built,future):
    base,plan=future
    root=tmp_path/'raw/sap'/cycle.CONTRACT/'future'
    root.parent.mkdir(parents=True,exist_ok=True)
    s,_=source([[]]*6)
    cycle.capture(root,plan,s,sleep=lambda _:None,guard=Guard())
    report=inc.read_json(tmp_path/'reconciliation.json')
    report.update(base_publication=base.foundation_publication_id,incremental_plan=plan,
                  capture_plan_sha256=inc.file_hash(root/'plan.json'))
    path=tmp_path/'future-report.json';inc.seal(path,report)
    candidate=make_candidate(base,path,root)
    validate_manifest(store,candidate)
    assert len(candidate.manifest['sales_coverage'])==120
    old={w['id']:w for w in base.manifest['sales_coverage']}
    new={w['id']:w for w in candidate.manifest['sales_coverage']}
    for key in old:
        if key not in {w['id'] for w in plan['windows']}: assert new[key]==old[key]
    bad=deepcopy(candidate);bad.manifest['sales_coverage'].pop()
    with pytest.raises(Exception):validate_manifest(store,bad)
    with pytest.raises(RuntimeError,match='UNPUBLISHED'):
        cycle.record_published_watermark(tmp_path/'watermark.json',plan,candidate,reader_verified=True)
    assert not (tmp_path/'watermark.json').exists()
    store.create_candidate(candidate)
    store.set_status(candidate.foundation_publication_id,READY_TO_COMMIT)
    store.logical_commit(candidate.foundation_publication_id)
    effective=store.get(candidate.foundation_publication_id)
    watermark=cycle.record_published_watermark(tmp_path/'watermark.json',plan,effective,reader_verified=True)
    assert watermark['business_coverage_end_exclusive']=='2026-10-31'
    assert cycle.record_published_watermark(tmp_path/'watermark.json',plan,effective,reader_verified=True)==watermark


def test_cycle_money_including_cancelled_zero_and_outside_scope():
    import duckdb
    with duckdb.connect(config={'threads':1}) as con:
        for table in ('sales_document','credit_memo_document'):
            con.execute(f'CREATE TABLE full_{table}(source_system VARCHAR,doc_date VARCHAR,currency VARCHAR,canceled VARCHAR,doc_total VARCHAR)')
        con.execute("INSERT INTO full_sales_document VALUES ('SAP_B1_HANA','2026-10-30','BS','Y','100'),('SAP_B1_HANA','2026-01-01','BS','N','999')")
        report=dict(coverage=[dict(domain=d,start='2026-10-30',end='2026-10-31') for d in inc.DOMAINS],
                    raw_money=[dict(domain='sales',month='2026-10',currency='BS',cancelled='Y',documents=1,doc_total='100')])
        assert cycle.verify_cycle_money(con,report)==dict(groups=1,zero_tolerance=True)
        report['raw_money'][0]['doc_total']='99.99'
        with pytest.raises(ValueError,match='MONETARY'):cycle.verify_cycle_money(con,report)


def test_source_scope_and_watermark_not_assumed(future):
    base,_=future
    with pytest.raises(ValueError,match='WATERMARK'):
        cycle.make_plan(base=base,published_end='2026-10-29',end_exclusive='2026-11-01',authorization_reference='fixture')
    with pytest.raises(ValueError,match='EVIDENCE'):
        cycle.make_plan(base=base,published_end='2026-10-30',end_exclusive='2026-11-01',authorization_reference='fixture',late_dates=['2026-01-01'])
