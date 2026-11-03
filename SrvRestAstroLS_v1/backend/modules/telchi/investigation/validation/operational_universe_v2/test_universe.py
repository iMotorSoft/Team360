"""Synthetic graph/union/ledger tests and reconciliation of real offline artifacts."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from . import analyze as a, selective as s
from ..controlled_physical_capture_v1.capture import destination_lock, digest, file_inventory


def header(code, kind='P'):
    return dict(Code=code,TreeType=kind)


def line(parent, child, number=0, kind=4):
    return dict(Father=parent,Code=child,ChildNum=number,VisOrder=number,Type=kind)


def event(key, family='sales', recent=True):
    return dict(item_code=key,event_kind=family,first_date='2026-01-01',
                last_date='2026-09-24',recent=recent,historical=not recent)


def test_union_identity_reference_classification_and_receipts():
    graph = a.graph_membership([header('P')],[line('P','INPUT')])
    products, sets = a.universe([event(' P'),event('P'),event('P','sales_return'),
        event('P','production_receipt'),event('INPUT','production_consumption'),
        event('OLD',recent=False)],graph,{'P':'reference-P'},
        {'P':'1',' P':None,'INPUT':'4','OLD':'unknown'})
    by = {p['ItemCode']:p for p in products}
    assert list(by)==[' P','INPUT','OLD','P']
    assert by[' P']['canonical_product_id'] is None  # no invented/trimmed identity
    assert by['P']['has_sales'] and by['P']['has_sales_returns']
    assert by['P']['has_production_receipt'] and not by['P']['has_production_consumption']
    assert by['P']['physical_status']=='EXPLICIT'
    assert by['INPUT']['physical_status']=='OBSERVED_NOT_EXPLICIT'
    assert by[' P']['classification_observed'] and by[' P']['U_FormaFarmac'] is None
    assert by['OLD']['activity_class']=='HISTORICAL_OBSERVED'
    assert sets['has_production_receipt']=={'P'}


@pytest.mark.parametrize('code,explicit',[(None,False),('0',False),('1',True),('2',True),
    ('3',True),('4',False),('5',False),('9',False),('',False),(1,False)])
def test_exact_sap_codes_no_inference(code, explicit):
    p,_ = a.universe([event('LIQUIDO')],a.graph_membership([],[]),{}, {'LIQUIDO':code})
    assert (p[0]['physical_status']=='EXPLICIT') is explicit
    missing,_ = a.universe([event('LIQUIDO')],a.graph_membership([],[]),{}, {})
    assert missing[0]['physical_status']=='NOT_QUERIED'


def test_multilevel_diamond_shared_components_cycles_and_no_movement():
    hs = [header(k) for k in ('P','A','B','C')]
    ls = [line('P','A'),line('P','B',1),line('A','C'),line('B','C'),line('C','LEAF'),line('C','P',1)]
    g = a.graph_membership(hs,ls)
    assert g['parents']=={'P','A','B','C'}
    assert g['components']=={'A','B','C','P','LEAF'}
    assert 'LEAF' in g['multilevel']
    paths = [p['path'] for p in g['paths'] if p['root']=='P' and p['component']=='LEAF']
    assert sorted(paths)==[['P','A','C','LEAF'],['P','B','C','LEAF']]
    assert g['cycles'] and all(p['component'] in p['path'][:-1] for p in g['cycles'])
    p,_ = a.universe([],g,{}, {})
    assert len(p)==5 and all(x['activity_class']=='BOM_WITHOUT_OBSERVED_MOVEMENT' for x in p)
    assert not any(x['has_production_consumption'] or x['has_sales'] for x in p)
    assert not g['truncated']
    with pytest.raises(RuntimeError,match='no_partial_result'):
        a.graph_membership(hs,ls,max_paths=1)


def test_resource_sales_bom_and_orphans_preserved_not_in_universe():
    g = a.graph_membership([header('P'),header('S','S'),header('UNKNOWN','?')],
        [line('P','RESOURCE',kind=290),line('S','SALE_COMPONENT'),
         line('ORPHAN','X'),line('UNKNOWN','Y')])
    assert g['parents']=={'P'} and not g['components']
    assert len(g['excluded'])==4
    assert {e['exclusion'] for e in g['excluded']}=={'NON_ITEM_COMPONENT','NON_PRODUCTION_BOM','ORPHAN_HEADER'}
    assert len(a.universe([],g,{}, {})[0])==1
    assert a.graph_membership([],[])['parents']==set()


@pytest.mark.parametrize('bad',[None,'',42,'  '])
def test_invalid_identity_rejected(bad):
    with pytest.raises(RuntimeError,match='identity'):
        a.universe([event(bad)],a.graph_membership([],[]),{}, {})


def test_duplicate_documentary_bom_keys_rejected():
    with pytest.raises(RuntimeError,match='duplicate_bom_header'):
        a.graph_membership([header('A'),header('A')],[])
    with pytest.raises(RuntimeError,match='duplicate_bom_line'):
        a.graph_membership([header('A')],[line('A','B'),line('A','C')])


@pytest.mark.parametrize('n,queries,blocks',[(0,0,0),(1,1,1),(25,1,1),(26,2,1),(125,5,1),(126,6,2),(3242,130,26)])
def test_selective_exact_plan(n,queries,blocks):
    keys = [f'K{i:06}' for i in range(n)]
    p = s.plan_for(keys)
    assert len(p['batches'])==queries
    assert len({b['block'] for b in p['batches']})==blocks
    assert [k for b in p['batches'] for k in b['parameters']]==keys
    assert all(1<=len(b['parameters'])<=25 and b['sql'].count('?')==len(b['parameters']) for b in p['batches'])
    assert 'K000001' not in str([b['sql'] for b in p['batches']])
    assert s.plan_for(keys)==p
    if n:
        mutated=deepcopy(p); mutated['controls']['max_items_per_select']=100
        with pytest.raises(RuntimeError,match='plan_mismatch'):
            s.validate_plan(mutated)


@pytest.mark.parametrize('keys',[['B','A'],['A','A'],[''],[None]])
def test_plan_rejects_invalid_keys(keys):
    with pytest.raises(ValueError):
        s.plan_for(keys)


def test_parametrization_and_missing_completed_vs_incomplete():
    p=s.plan_for(["A' OR 1=1 --",'B'])
    assert "OR 1=1" not in p['batches'][0]['sql']
    b=s.response_batch(p,0,[dict(ItemCode='B',U_FormaFarmac=None)],observed_at='now',fetch_complete=True)
    assert b['not_returned']==["A' OR 1=1 --"]
    assert b['rows'][0]['U_FormaFarmac'] is None
    with pytest.raises(RuntimeError,match='incomplete_fetch'):
        s.response_batch(p,0,[],observed_at='now',fetch_complete=False)


@pytest.mark.parametrize('rows',[
    [{'ItemCode':'C','U_FormaFarmac':'1'}],
    [{'ItemCode':'A','U_FormaFarmac':'1'}]*2,
    [{'ItemCode':'B','U_FormaFarmac':'1'},{'ItemCode':'A','U_FormaFarmac':'1'}],
    [{'ItemCode':'A'}], [{'ItemCode':None,'U_FormaFarmac':'1'}]])
def test_bad_selective_response(rows):
    with pytest.raises(RuntimeError):
        s.response_batch(s.plan_for(['A','B']),0,rows,observed_at='now',fetch_complete=True)


@pytest.fixture
def ledger(tmp_path,monkeypatch):
    monkeypatch.setattr(s,'PRIVATE',tmp_path)
    root=tmp_path/'new-ledger'; root.mkdir()
    p=s.plan_for(['A','B'])
    with destination_lock(root):
        s.initialize(root,p)
        s.reserve_request(root,p,0,reserved_at='before-query')
    return root,p


def test_idempotent_missing_terminal_checkpoint(ledger):
    root,p=ledger
    with destination_lock(root):
        cp=s.commit_response(root,p,0,[dict(ItemCode='A',U_FormaFarmac='2')],observed_at='now',fetch_complete=True)
        before=file_inventory(root)
        assert s.recover(root,p)==cp
        assert s.commit_response(root,p,0,[dict(ItemCode='A',U_FormaFarmac='2')],observed_at='now',fetch_complete=True)==cp
        assert file_inventory(root)==before
        b=json.loads((root/cp['batches'][0]['file']).read_text())
        assert b['not_returned']==['B']
        assert not s.query_slot_allowed(p,1,elapsed_query_pause=100,elapsed_block_pause=100,
                                       remaining_seconds=100,closure_reserve_seconds=1)
        with pytest.raises(RuntimeError,match='conflict'):
            s.commit_response(root,p,0,[],observed_at='now',fetch_complete=True)


@pytest.mark.parametrize('stage',['batch_before','batch_after','checkpoint_before','checkpoint_after'])
def test_fault_recovery_without_requery(ledger,monkeypatch,stage):
    root,p=ledger
    original=s.save
    def failing(path,value):
        target='selective-000000.json' if stage.startswith('batch') else 'checkpoint.json'
        if path.name==target:
            if stage.endswith('after'):
                original(path,value)
            raise OSError('injected_interruption')
        original(path,value)
    with destination_lock(root):
        monkeypatch.setattr(s,'save',failing)
        with pytest.raises(OSError,match='injected'):
            s.commit_response(root,p,0,[],observed_at='now',fetch_complete=True)
        monkeypatch.setattr(s,'save',original)
        cp=s.recover(root,p)
        assert len(cp['batches'])==1
        before=file_inventory(root)
        assert s.recover(root,p)==cp and file_inventory(root)==before
        assert json.loads((root/'selective-000000.json').read_text())['not_returned']==['A','B']


def test_uncertain_request_never_automatically_retried(ledger):
    root,p=ledger
    with destination_lock(root):
        before=file_inventory(root)
        s.recover(root,p)
        assert file_inventory(root)==before
        with pytest.raises(RuntimeError,match='no_retry'):
            s.reserve_request(root,p,0,reserved_at='retry')
        assert not s.query_slot_allowed(p,0,elapsed_query_pause=100,elapsed_block_pause=100,
            remaining_seconds=100,closure_reserve_seconds=2,has_unresolved_request=True)


def test_corruption_untracked_and_plan_binding(ledger):
    root,p=ledger
    with destination_lock(root):
        s.commit_response(root,p,0,[],observed_at='now',fetch_complete=True)
        (root/'selective-000000.json').write_text('{}')
        with pytest.raises(RuntimeError,match='hash_mismatch'):
            s.recover(root,p)
    with pytest.raises(RuntimeError,match='plan_mismatch'):
        s.read_state(root,s.plan_for(['OTHER']))


def test_untracked_tmp_and_lock_exclusion(ledger):
    root,p=ledger
    with destination_lock(root):
        with pytest.raises(RuntimeError,match='already_running'):
            with destination_lock(root):
                pass
        (root/'pending.json.tmp').write_text('uncertain')
        with pytest.raises(RuntimeError,match='temporary'):
            s.recover(root,p)


def test_no_shared_output_destination(tmp_path):
    with pytest.raises(RuntimeError,match='private_isolated'):
        s.initialize(tmp_path,s.plan_for(['A']))
    # Analyzer rejects outside report root BEFORE creating directories/scanning sources.
    rejected=tmp_path/'shared'
    with pytest.raises(RuntimeError,match='repository_telchi_report'):
        a.main(rejected)
    assert not rejected.exists()


def test_future_scheduler_limits():
    p=s.plan_for([f'{i:03}' for i in range(150)])
    args=dict(elapsed_query_pause=10,elapsed_block_pause=30,remaining_seconds=20,closure_reserve_seconds=2)
    assert s.query_slot_allowed(p,5,**args)
    for k,v in [('elapsed_query_pause',9.99),('elapsed_block_pause',29.99),('remaining_seconds',13.49),('closure_reserve_seconds',0)]:
        assert not s.query_slot_allowed(p,5,**dict(args,**{k:v}))


def test_real_sales_and_returns_exclude_canceled_documents():
    root=a.REPORT_ROOT/'operational-universe-v2-20261029-final'
    report=json.loads((root/'activity_reaccredited/report.json').read_text())
    with a.v1.DuckLakeConnector().session(read_only=True) as c:
        c.execute('SET threads=2')
        c.execute("SET memory_limit='512MB'")
        foundation=a.v1.FoundationReader().resolve_on(c)
        assert foundation.foundation_publication_id==report['inventory']['foundation']['id']
        for family,component,header in [('sales','sales','sales_document'),
                ('sales_return','credit_memo','credit_memo_document')]:
            relation=foundation.relation(component,header)
            invalid=c.execute(f"SELECT count(*) FROM read_parquet(?) e LEFT JOIN {relation} h "
                "ON e.doc_entry=h.doc_entry AND h.source_system='SAP_B1_HANA' "
                "WHERE e.event_kind=? AND (h.doc_entry IS NULL OR h.canceled IS DISTINCT FROM 'N' "
                "OR try_cast(e.quantity AS DECIMAL(38,10)) IS NULL "
                "OR try_cast(e.quantity AS DECIMAL(38,10))<=0)",
                [str(root/'activity_reaccredited/evidence.parquet'),family]).fetchone()[0]
            assert invalid==0
            assert any(x['canceled'] in ('Y','C') for x in report['inventory'][header]['document_rules'])


def test_real_artifacts_reconcile():
    root=a.REPORT_ROOT/'operational-universe-v2-20261029-final'
    r=json.loads((root/'report.json').read_text())
    products=json.loads((root/'products.json').read_text())
    plan=json.loads((root/'selective_plan.json').read_text())
    s.validate_plan(plan)
    keys=[p['ItemCode'] for p in products]
    assert keys==sorted(set(keys)) and len(keys)==r['counts']['total_unique']==8001
    assert plan['item_codes']==[p['ItemCode'] for p in products if not p['classification_observed']]
    assert len(plan['item_codes'])==r['counts']['pending']==3242
    assert len(plan['batches'])==r['counts']['select_queries']==130
    for flag in [*a.FLAGS.values(),'is_bom_parent','is_bom_component','is_multilevel_bom_component']:
        assert sum(p[flag] for p in products)==r['counts'][flag]
    assert sum(x['products'] for x in r['classification'])==r['counts']['covered']==4759
    assert r['counts']['explicit_physical']+r['counts']['observed_not_explicit']==4759
    assert r['counts']['missing_reference']==len(r['identity_missing_reference'])==43
    assert all(p['canonical_product_id'] is None for p in products if not p['reference_match'])
    assert all(e.get('header_extraction_id') for p in products for e in p['bom_evidence'])
    assert all(e.get('source_tables') for p in products for e in p['movement_evidence'])
    assert not r['bom']['truncated']
    assert not r['source_discovery']['production_receipt_candidates']
    assert r['production_receipts']['actual_enterprise_products'] is None
    assert r['counts']['exclusively_bom']==603
    assert r['safety']['hana_queries']==r['safety']['shared_data_writes']==0
    assert r['safety']['capture_unchanged'] and r['safety']['manifest_tree_unchanged']
    for name,h in json.loads((root/'artifact_hashes.json').read_text()).items():
        assert digest(root/name)==h
