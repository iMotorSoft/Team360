from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import duckdb
import pytest

from modules.telchi.datalake import sales_continuity as cap, sales_incremental as inc
from modules.telchi.datalake import sales_facts_transition as t
from modules.telchi.datalake.foundation_manifest import validate_manifest
from modules.telchi.datalake.foundation_reader import FoundationReader
from modules.telchi.datalake.foundation_publication import READY_TO_COMMIT, CommitFaultPoint
from .test_receivables_collections_foundation import store, extensible_base, extension
from .test_sales_controlled_block import source
from .test_sales_continuity import pair, Guard


@pytest.fixture
def built(tmp_path,store,monkeypatch):
    monkeypatch.setattr(inc,'DATA_ROOT',tmp_path)
    original=extensible_base(store)
    base=extension(store,original,name='purchasing',legacy=True)
    store.set_status(base.foundation_publication_id,READY_TO_COMMIT)
    store.logical_commit(base.foundation_publication_id)
    base=store.get(base.foundation_publication_id)
    h,rows=pair()
    root=tmp_path/'capture'
    s,_=source([[h],rows]+[[]]*117)
    assert cap.run(root,cap.make_plan({}),s,sleep=lambda _:None,guard=Guard())['status']=='CAPTURED_PASS'
    datasets={}
    con=duckdb.connect()
    try:
        for domain in inc.DOMAINS:
            candidate=inc.transform_capture(domain,rows,dict(extraction_id='test',source_as_of=inc.now()))
            for table,records in candidate.tables.items():
                json_path=tmp_path/(table+'.json');inc.seal(json_path,records)
                path=tmp_path/(table+'.parquet')
                columns='{'+','.join("'"+k+"':'VARCHAR'" for k in records[0])+'}'
                con.execute(f"COPY (SELECT * FROM read_json(?,columns={columns})) TO '{path}' (FORMAT PARQUET)",[str(json_path)])
                schema=[list(r[:2]) for r in con.execute('DESCRIBE SELECT * FROM read_parquet(?)',[str(path)]).fetchall()]
                datasets[table]=dict(path=str(path),sha256=inc.file_hash(path),row_count=1,schema=schema)
    finally: con.close()
    sha=inc.digest({})
    report=dict(blockers=[],material_supply=dict(unchanged=True,start='2026-06-26',end='2026-09-24',proofs={d:dict(unchanged=True,before_sha256=sha,after_sha256=sha) for d in inc.DOMAINS}),
                reference_missing={k:[] for k in ['customers','products','credit_customers','credit_products']},
                base_publication=base.foundation_publication_id,base_snapshot=90,capture_plan_sha256=inc.file_hash(root/'plan.json'),datasets=datasets)
    report_path=tmp_path/'reconciliation.json';inc.seal(report_path,report)
    candidate=t.make_candidate(base,report_path,root)
    return base,candidate,root


def test_valid_transition_preserves_seals_and_catalog_roundtrip(store,built):
    base,candidate,root=built
    assert validate_manifest(store,candidate)==candidate.manifest['components']
    t.verify_files(candidate.manifest)
    for name,entry in base.manifest['components'].items():
        if name not in inc.DOMAINS:
            assert candidate.manifest['components'][name]==entry
    store.create_candidate(candidate)
    reread=store.get(candidate.foundation_publication_id)
    validate_manifest(store,reread)
    assert store.current_pointer()==base.foundation_publication_id
    store.set_status(candidate.foundation_publication_id,READY_TO_COMMIT)
    store.logical_commit(candidate.foundation_publication_id)
    assert store.logical_commit(candidate.foundation_publication_id)['status']=='ALREADY_CURRENT'


def test_canonical_reader_pin_and_coverage(store,built):
    base,candidate,root=built
    store.create_candidate(candidate)
    store.set_status(candidate.foundation_publication_id,READY_TO_COMMIT)
    store.logical_commit(candidate.foundation_publication_id)
    # Metadata isolated in memory; file-backed facts real. The independent
    # catalog-backed components are fixture verified, not live SAP/PG claims.
    reader=FoundationReader(metadata_catalog='',snapshot_resolver=lambda *_:100,
                            component_verifier=lambda *_:None,verify_reference_path=False)
    with store.connection_factory() as con:
        access=reader.resolve_on(con)
        assert access.ducklake_snapshot_id==90 and access.manifest_base_snapshot_id==84
        assert con.execute('SELECT doc_entry FROM '+access.sales('sales_document')).fetchone()==('1',)
        assert 'VERSION => 90' in access.oinm()
        assert 'VERSION => 84' in access.receivables_collections('receivable_settlement_status')
        assert len(access.require_sales_coverage('sales','2026-09-01','2026-10-30'))==59
        assert len(access.require_sales_coverage('credit_memo','2026-10-02','2026-10-03'))==1
        with pytest.raises(Exception,match='not accredited'):
            access.require_sales_coverage('sales','2026-10-29','2026-10-31')
        with pytest.raises(Exception,match='not part'):
            access.sales('inventory_movement')


@pytest.mark.parametrize('mutation',['coverage','gap','snapshot','sealed','proof','fingerprint','schema','reference','base','catalog'])
def test_negative_transition_matrix(store,built,mutation):
    base,original,root=built
    p=deepcopy(original);m=p.manifest
    if mutation=='coverage': m['sales_coverage'].pop()
    if mutation=='gap': m['sales_coverage'][0]['complete']=False
    if mutation=='snapshot': m['base_snapshot_id']+=1
    if mutation=='sealed': m['components']['purchasing']['content_identity']='fake'
    if mutation=='proof': m['sales_facts_revalidation']['material_supply']['proofs']['sales']['after_sha256']='a'*64
    if mutation=='fingerprint': m['components']['sales']['content_identity']='fake'
    if mutation=='schema': m['components']['sales']['facts_contract']['datasets']['sales_document']['schema']=[]
    if mutation=='reference': p.reference_version='different'
    if mutation=='base': m['base_foundation_publication_id']='missing'
    if mutation=='catalog': p.components['sales']=replace(p.components['sales'],publication_id='different')
    with pytest.raises(Exception): validate_manifest(store,p)
    assert store.current_pointer()==base.foundation_publication_id


def test_physical_corruption_rejected(store,built):
    base,p,root=built
    path=Path(p.manifest['components']['sales']['facts_contract']['datasets']['sales_document']['path'])
    path.write_bytes(b'corrupt')
    with pytest.raises(Exception,match='hash'): t.verify_files(p.manifest)
    assert store.current_pointer()==base.foundation_publication_id


def test_fault_recovery_and_rollback(store,built):
    base,p,root=built
    store.create_candidate(p)
    store.set_status(p.foundation_publication_id,READY_TO_COMMIT)
    store.fault_point=CommitFaultPoint.DURING_LOGICAL_COMMIT
    with pytest.raises(Exception): store.logical_commit(p.foundation_publication_id)
    assert store.current_pointer()==base.foundation_publication_id
    store.fault_point=None
    validate_manifest(store,store.get(p.foundation_publication_id));t.verify_files(p.manifest)
    store.logical_commit(p.foundation_publication_id)
    result=store.logical_rollback(base.foundation_publication_id,expected_current_foundation_publication_id=p.foundation_publication_id,reason='isolated rollback test')
    assert store.current_pointer()==base.foundation_publication_id
