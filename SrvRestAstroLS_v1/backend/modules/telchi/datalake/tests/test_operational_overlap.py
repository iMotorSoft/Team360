"""Offline regression for explicit observation overlaps and receipt exposure."""
from copy import deepcopy
import pytest
from modules.telchi.datalake import operational_overlap as overlap
from modules.telchi.datalake import operational_domains as obs
from modules.telchi.datalake.foundation_publication import FoundationReaderError


def test_receipt_dispatch_requires_production_revision():
    assert 'production_receipt' not in overlap.groups({})['production']
    assert 'production_receipt' not in overlap.groups({'overlap':{'domains':['movements']}})['production']
    assert 'production_receipt' in overlap.groups({'overlap':{'domains':['production']}})['production']


@pytest.mark.parametrize('field,value', [('sql','SELECT wrong'),('params',[]),('keys',['wrong']),
    ('sums',[]),('nullable_keys',True),('ordered_keys',False),('semantic_scope',{'kind':'OTHER'})])
def test_source_projection_drift_fails_closed(tmp_path, monkeypatch, field, value):
    monkeypatch.setattr(overlap.durable,'DATA_ROOT',tmp_path)
    directory=tmp_path/'raw/sap/full-data-lake-refresh-capture-v1/run/receipt'; directory.mkdir(parents=True)
    plan=dict(sql='SELECT exact',params=['start','end'],keys=['DocEntry','LineNum'],sums=['Quantity'],
        nullable_keys=False,ordered_keys=True,semantic_scope={'kind':'ACTUAL'})
    plan[field]=value
    overlap.durable.seal(directory/'intent.json',{'plan':plan})
    monkeypatch.setattr(overlap,'verify_capture',lambda *_:{'pages':[]})
    with pytest.raises(FoundationReaderError,match='projection/scope mismatch'):
        overlap.capture(directory,sql='SELECT exact',params=['start','end'],keys=['DocEntry','LineNum'],sums=['Quantity'],kind='ACTUAL')


@pytest.mark.parametrize('change',['quantity','duplicate','schema','bytes'])
def test_overlap_output_replays_cells_not_just_declared_hash(tmp_path,monkeypatch,change):
    monkeypatch.setattr(overlap.durable,'DATA_ROOT',tmp_path)
    monkeypatch.setattr(overlap,'groups',lambda *_:{'production':('production_receipt',)})
    def replay(con,stable):
        con.execute('CREATE TABLE production_receipt AS SELECT 1 AS DocEntry,0 AS LineNum,10 AS Quantity UNION ALL SELECT 2,0,20')
        return {'production':{'receipt_rows':2}}
    monkeypatch.setattr(overlap,'replay',replay)
    directory=tmp_path/'staging/revision'; directory.mkdir(parents=True)
    path=directory/'production_receipt.parquet'
    sql={'quantity':'SELECT 1 AS DocEntry,0 AS LineNum,11 AS Quantity UNION ALL SELECT 2,0,19',
         'duplicate':'SELECT 1 AS DocEntry,0 AS LineNum,10 AS Quantity UNION ALL SELECT 1,0,10',
         'schema':"SELECT '1' AS DocEntry,0 AS LineNum,10 AS Quantity UNION ALL SELECT '2',0,20",
         'bytes':'SELECT 1 AS DocEntry,0 AS LineNum,10 AS Quantity UNION ALL SELECT 2,0,20'}[change]
    with obs.database() as con:
        con.execute('COPY ('+sql+') TO '+overlap.literal(path)+' (FORMAT PARQUET)')
    metadata=dict(path=str(path),sha256=overlap.durable.file_hash(path),row_count=2,
        schema=[['DocEntry','INTEGER'],['LineNum','INTEGER'],['Quantity','INTEGER']])
    if change=='bytes': path.write_bytes(b'tampered')
    stable={'overlap':{'coverage':{'production':{'receipt_rows':2}}},'datasets':{'production_receipt':metadata}}
    with pytest.raises(FoundationReaderError,match='(bytes|schema/count|exact replay) mismatch'):
        overlap.verify(stable)


def test_live_reader_rejects_same_count_different_cells(tmp_path, monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(overlap.durable,'DATA_ROOT',tmp_path)
    monkeypatch.setattr(overlap,'groups',lambda *_:{'production':('production_receipt',)})
    def replay(con,stable):
        con.execute('CREATE TABLE production_receipt AS SELECT 1 AS DocEntry,0 AS LineNum,10 AS Quantity')
        return {'production':{'receipt_rows':1}}
    monkeypatch.setattr(overlap,'replay',replay)
    directory=tmp_path/'staging/revision'; directory.mkdir(parents=True)
    path=directory/'receipt.parquet'
    with obs.database() as con:
        con.execute('COPY (SELECT 1 AS DocEntry,0 AS LineNum,10 AS Quantity) TO '+overlap.literal(path)+' (FORMAT PARQUET)')
        metadata=dict(path=str(path),sha256=overlap.durable.file_hash(path),row_count=1,
            schema=[['DocEntry','INTEGER'],['LineNum','INTEGER'],['Quantity','INTEGER']])
        stable={'overlap':{'coverage':{'production':{'receipt_rows':1}}},'datasets':{'production_receipt':metadata}}
        reader=SimpleNamespace(operational_observation=lambda *_:'(SELECT 1 AS DocEntry,0 AS LineNum,99 AS Quantity)')
        with pytest.raises(FoundationReaderError,match='live overlap reader exact replay mismatch'):
            overlap.verify(stable,reader=reader,con=con)


def test_unaffected_observation_cannot_be_rebound(monkeypatch):
    old_stable={'capture_root':'raw-root','limits':{},'reconciliation_path':'proof','reconciliation_sha256':'digest',
        'datasets':{'collection_payment':{'path':'sealed'}}}
    monkeypatch.setattr(obs,'observation_contract',lambda _:old_stable)
    stable=deepcopy(old_stable)
    stable['overlap']={'ancestor_sha256':overlap.durable.digest(old_stable),'domains':['production']}
    stable['datasets']['collection_payment']={'path':'replacement'}
    with pytest.raises(FoundationReaderError,match='unaffected observation changed'):
        overlap.validate_ancestor(stable,{})


def test_independent_later_domain_retains_prior_bounded_observation(monkeypatch):
    old_stable={'capture_root':'raw-root','limits':{},'reconciliation_path':'proof','reconciliation_sha256':'digest',
        'datasets':{'collection_payment':{'path':'sealed'}},
        'overlap':{'recovery_root':'cycle','domains':['movements'],'movement_evidence':{'sha256':'sealed'}}}
    monkeypatch.setattr(obs,'observation_contract',lambda _:old_stable)
    monkeypatch.setattr(overlap,'verify',lambda *_:None)
    stable=deepcopy(old_stable)
    stable['overlap'].update(ancestor_sha256=overlap.durable.digest(old_stable),domains=['movements','production'])
    overlap.validate_ancestor(stable,{})
    stable['overlap']['domains']=['production']
    with pytest.raises(FoundationReaderError,match='previous bounded overlap was lost'):
        overlap.validate_ancestor(stable,{})


def test_bom_effectivity_not_inferred_from_receipt_contract():
    from modules.telchi.datalake.production_receipt_capture import SPEC
    assert SPEC.header_table=='OIGN' and SPEC.line_table=='IGN1'
    assert SPEC.key_fields==('DocEntry','LineNum')
    assert SPEC.quantity_field=='Quantity'
