"""Exact catalog accreditation reuse, never arbitrary ancestry bypass."""
from copy import deepcopy
from types import SimpleNamespace
import ast
from pathlib import Path

import pytest
from modules.telchi.datalake.foundation_publication import FoundationPublication, ComponentReference, FoundationReaderError
from modules.telchi.datalake.foundation_read_binding import make_binding, digest
from modules.telchi.datalake.foundation_manifest import validate_manifest
from modules.telchi.datalake import operational_domains as obs
from modules.telchi.datalake.operational_overlap import CONTRACT as OVERLAP


def fixture():
    names=('reference','sales','credit_memo','oinm','oitw','material_supply','purchasing','receivables_collections')
    refs={name:ComponentReference(name,name+'_sealed',source_as_of='2026-11-01') for name in names[:5]}
    components={name:dict(name=name,publication_id=name+'_sealed',source_as_of='2026-11-01') for name in names}
    manifest=dict(foundation_publication_id='base',candidate_kind='FOUNDATION_INDEPENDENT_FACTS_SUCCESSION_V1',
        base_snapshot_id=1400,facts_base_snapshot_id=1408,components=components,
        permissions={'production':['EXISTING']},sales_coverage=[{'end':'2026-10-31'}],
        operational_observations={'contract':obs.CONTRACT})
    base=FoundationPublication('base','original',reference_version='reference_sealed',components=refs,
        manifest=manifest,source_as_of='2026-11-01',status='CURRENT')
    access=SimpleNamespace(commit_snapshot_id=1900,ducklake_snapshot_id=1408)
    binding=make_binding(base,access,commercial=True,physical=dict(reference='reference_sealed',
        products_sha256='a'*64,crosswalk_sha256='b'*64))
    new=deepcopy(manifest)
    new.update(foundation_publication_id='candidate',base_foundation_publication_id='base',
        update_run_id='new',independent_facts_succession={'contract':obs.CONTRACT},
        operational_observations={'contract':obs.CONTRACT,'overlap':{'contract':OVERLAP}})
    candidate=FoundationPublication('candidate','new',previous_foundation_publication_id='base',
        reference_version=base.reference_version,components=deepcopy(refs),manifest=new,source_as_of=base.source_as_of)
    calls=[]
    store=SimpleNamespace(connection_factory=None,get=lambda fid:base if fid=='base' else None,
        read_binding=lambda fid:(calls.append(fid) or binding))
    return base,candidate,binding,store,calls


def test_unchanged_accredited_base_does_not_replay_cxc_or_recurse(monkeypatch):
    base,candidate,binding,store,calls=fixture()
    # The ancestor has no own base ID: recursion would fail. Its durable
    # publisher receipt, not a worker-provided assertion, is the trust root.
    validated=[]
    monkeypatch.setattr(obs,'validate_transition',lambda publication,ancestor,components,*args:
        (validated.append((publication,ancestor)) or components))
    assert validate_manifest(store,candidate)==base.manifest['components']
    assert calls==['base']
    assert validated==[(candidate,base)]


@pytest.mark.parametrize('field,value',[
    ('base_snapshot_id',1401),('facts_base_snapshot_id',1409),
    ('permissions',{'production':['EXPANDED']}),('sales_coverage',[{'end':'2026-11-30'}]),
    ('new_permission','INVENTED'),
])
def test_inherited_selector_or_permission_change_rejected(field,value):
    _,candidate,_,store,_=fixture()
    candidate.manifest[field]=value
    with pytest.raises(FoundationReaderError,match='accredited ancestor'):
        validate_manifest(store,candidate)


@pytest.mark.parametrize('component',['sales','credit_memo','receivables_collections','material_supply','oitw'])
def test_even_one_component_metadata_change_invalidates_reuse(component):
    _,candidate,_,store,_=fixture()
    candidate.manifest['components'][component]['source_as_of']='2026-11-02'
    with pytest.raises(FoundationReaderError,match='accredited ancestor'):
        validate_manifest(store,candidate)


@pytest.mark.parametrize('change',['digest','manifest','financial','physical','other_base','missing'])
def test_invalid_or_incomplete_catalog_receipt_cannot_be_replaced_by_candidate_assertion(change):
    base,candidate,binding,store,_=fixture()
    candidate.manifest['operational_observations']['alleged_receipt']=deepcopy(binding)
    if change=='digest': binding['receipt_sha256']='0'*64
    elif change=='manifest':
        binding['manifest_sha256']='0'*64
        binding['receipt_sha256']=digest({k:v for k,v in binding.items() if k!='receipt_sha256'})
    elif change=='other_base':
        binding['foundation_publication_id']='someone_else'
        binding['receipt_sha256']=digest({k:v for k,v in binding.items() if k!='receipt_sha256'})
    elif change in {'financial','physical'}:
        binding['commercial' if change=='financial' else 'physical']=False if change=='financial' else None
        if change=='financial': binding['physical']=None
        binding['receipt_sha256']=digest({k:v for k,v in binding.items() if k!='receipt_sha256'})
    else:
        def missing(_): raise FoundationReaderError('FOUNDATION_READ_BINDING_REQUIRED')
        store.read_binding=missing
    with pytest.raises(FoundationReaderError):
        validate_manifest(store,candidate)


def test_catalog_component_and_top_level_cutoff_also_frozen():
    base,candidate,_,store,_=fixture()
    candidate.source_as_of='2026-11-02'
    with pytest.raises(FoundationReaderError,match='accredited ancestor'):
        validate_manifest(store,candidate)
    candidate.source_as_of=base.source_as_of
    candidate.components['sales']=ComponentReference('sales','other',source_as_of='2026-11-01')
    with pytest.raises(FoundationReaderError):
        validate_manifest(store,candidate)


def test_unchanged_stock_metadata_does_not_hide_changed_physical_bytes(tmp_path,monkeypatch):
    base,candidate,binding,store,_=fixture()
    monkeypatch.setattr(obs.durable,'DATA_ROOT',tmp_path)
    path=tmp_path/'staging/sealed/stock.parquet'; path.parent.mkdir(parents=True)
    path.write_bytes(b'original-sealed-stock')
    metadata={'path':str(path),'sha256':obs.durable.file_hash(path)}
    for publication in (base,candidate):
        publication.manifest['components']['oitw']['independent_facts_contract']={'dataset':deepcopy(metadata)}
    fresh=make_binding(base,SimpleNamespace(commit_snapshot_id=1900,ducklake_snapshot_id=1408),
        commercial=True,physical=dict(reference=base.reference_version,products_sha256='a'*64,crosswalk_sha256='b'*64))
    binding.clear(); binding.update(fresh)
    assert obs.accredited_base_components(store,candidate,base)==base.manifest['components']
    path.write_bytes(b'changed-but-metadata-identical')
    with pytest.raises(FoundationReaderError,match='inherited stock bytes changed'):
        obs.accredited_base_components(store,candidate,base)


def test_actual_consumption_obeys_its_own_cutoff_without_removing_source_facts(tmp_path):
    obs.durable.seal(tmp_path/'cycle-plan.json',{'year_start':'2026-01-01','end_exclusive':'2026-11-01'})
    with obs.database() as con:
        con.execute('''CREATE TABLE production_issue AS SELECT 1 AS DocEntry,0 AS LineNum,'M1' AS ItemCode,
            202.0 AS BaseType,10 AS BaseEntry,DATE '2026-10-31' AS DocDate,'N' AS CANCELED,
            '5' AS Quantity,'KG' AS unitMsr,NULL::VARCHAR AS UomCode,'1' AS NumPerMsr
            UNION ALL SELECT 2,0,'M1',202,10,DATE '2026-11-01','N','100','KG',NULL,'1' ''')
        con.execute("CREATE TABLE oitm AS SELECT 'M1' AS ItemCode")
        con.execute('CREATE TABLE production_order AS SELECT 10 AS DocEntry')
        result=obs.build_observed_consumption(con,tmp_path)
        assert result['window_end']=='2026-10-31'
        assert result['included_issue_lines']==1 and result['excluded_issue_lines']==1
        assert con.execute('SELECT actual_consumption_qty FROM observed_material_actual_consumption').fetchone()[0]=='5.000000'
        assert con.execute('SELECT count(*) FROM production_issue').fetchone()[0]==2


def test_publication_runner_does_not_install_crashing_watchdog():
    root=Path(__file__).resolve().parents[6]
    path=root/'data/reports/telchi/stock-production-october-v1/finalize_publication.py'
    calls=[node for node in ast.walk(ast.parse(path.read_text())) if isinstance(node,ast.Call)]
    assert not any(isinstance(node.func,ast.Attribute) and node.func.attr=='dump_traceback_later' for node in calls)
