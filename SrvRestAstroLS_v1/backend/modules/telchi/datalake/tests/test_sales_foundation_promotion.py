from pathlib import Path

import duckdb
import pytest

from modules.telchi.datalake import sales_incremental as inc
from modules.telchi.datalake import sales_foundation_promotion as p
from modules.telchi.datalake.foundation_manifest import validate_manifest
from modules.telchi.datalake.foundation_publication import CommitFaultPoint
from modules.telchi.datalake.reference_update import POINTER_NAME, active_pointer, reference_publication_lock
from modules.telchi.datalake.sales_facts_transition import verify_files
from .test_receivables_collections_foundation import store
from .test_sales_facts_transition import built


@pytest.fixture
def prepared(tmp_path, store, built):
    base, candidate, _ = built
    data = tmp_path/'data'
    before = dict(current_reference_version='v2_old')
    for version in ('v2_old', candidate.reference_version):
        for family, key in (('reference','reference_path'), ('crosswalk','crosswalk_path')):
            root = data/family/'_versions'/version
            root.mkdir(parents=True)
            with duckdb.connect(config={'threads':1}) as con:
                con.execute('COPY (SELECT 1 AS identity) TO ? (FORMAT PARQUET)', [str(root/'part.parquet')])
            if version == 'v2_old': before[key] = str(root)
    (data/'manifests').mkdir()
    inc.seal(data/'manifests'/POINTER_NAME, before)
    path = tmp_path/'candidate.json'
    inc.seal(path, candidate.as_row())
    def validate(c):
        validate_manifest(store,c)
        if 'sales_facts_revalidation' in c.manifest: verify_files(c.manifest)
    def reader(c):
        current = store.current_publication()
        assert current.foundation_publication_id == c.foundation_publication_id
        return dict(foundation=current.foundation_publication_id, reference=current.reference_version)
    promo = p.Promotion(store, data, tmp_path/'journal', validate=validate, verify_reader=reader, resource_check=lambda:None)
    plan = promo.prepare(path)
    authorization = dict(contract=p.CONTRACT, action='PROMOTE', candidate=plan['candidate'], base=plan['base'],
        manifest_sha256=plan['manifest_sha256'], reference=candidate.reference_version,
        retained_component_cutoffs=plan['retained_component_cutoffs'],
        authorized_by='ISOLATED_TEST_ONLY', authorization_reference='fixture-no-live-authority')
    return promo, plan, authorization


@pytest.mark.parametrize('point',['before_commit','after_commit','during_activation','after_activation'])
def test_interruption_recovery_and_duplicate_noop(prepared, point):
    promo,plan,auth=prepared
    def fault(at):
        if at == point: raise InterruptedError(point)
    with pytest.raises(InterruptedError): promo.promote(auth, fault=fault)
    expected = plan['base'] if point == 'before_commit' else plan['candidate']
    assert promo.store.current_pointer()==expected
    # Readers remain pinned to exactly one Reference while activation lags.
    assert promo.store.current_publication().reference_version == promo.store.get(expected).reference_version
    assert promo.promote(auth)['status']=='TECHNICALLY_ACTIVATED_READER_VERIFIED'
    assert promo.promote(auth)['candidate']==plan['candidate']
    assert active_pointer(promo.data_root)[0]==plan['reference_after']
    assert promo.rollback(reason='isolated gate')['status']=='ROLLED_BACK'
    assert promo.rollback(reason='isolated gate')['status']=='ROLLED_BACK'
    assert active_pointer(promo.data_root)[0]==plan['reference_before']
    assert promo.store.current_pointer()==plan['base']
    with pytest.raises(RuntimeError,match='ROLLED_BACK'): promo.promote(auth)


def test_canonical_after_commit_fault_recovery(prepared):
    promo,plan,auth=prepared
    promo.store.fault_point=CommitFaultPoint.AFTER_LOGICAL_COMMIT
    with pytest.raises(Exception): promo.promote(auth)
    assert promo.store.current_pointer()==plan['candidate']
    promo.store.fault_point=None
    assert promo.promote(auth)['candidate']==plan['candidate']


@pytest.mark.parametrize('mutation',['candidate','reference','pointer','current','authorization','lock'])
def test_fail_closed(prepared, mutation):
    promo,plan,auth=prepared
    if mutation=='candidate': Path(plan['candidate_path']).write_text('{}')
    if mutation=='reference':
        next(Path(plan['reference_after']['reference_path']).glob('*.parquet')).write_bytes(b'corrupt')
    if mutation=='pointer':
        path=promo.data_root/'manifests'/POINTER_NAME
        pointer=inc.read_json(path);pointer['build_id']='other-writer'
        path.write_text(__import__('json').dumps(pointer))
    if mutation=='current':
        # Different preparation ancestor exercises CAS before any real commit.
        plan['base']='different'
        path=promo.journal/'plan.json';path.write_text(__import__('json').dumps(plan))
        auth['base']='different'
    if mutation=='authorization': auth['candidate']='not-authorized'
    if mutation=='lock': promo.store.acquire_run_lock('other-writer')
    before=promo.store.current_pointer()
    with pytest.raises((RuntimeError,ValueError,PermissionError,KeyError)):
        promo.promote(auth)
    assert promo.store.current_pointer()==before


def test_owner_instruction_without_nominal_approval_publishes(prepared):
    # The owner's instruction to publish this exact plan is the authority.
    # `authorized_by` / `authorization_reference` are optional trace, not gates.
    promo,plan,_=prepared
    assert not (promo.journal/'authorization.json').exists()
    assert promo.promote()['candidate']==plan['candidate']
    assert not (promo.journal/'authorization.json').exists()
    assert (promo.journal/'committed.json').exists() and (promo.journal/'activated.json').exists()


def test_optional_trace_is_recorded_once_and_never_blocks_replay(prepared):
    promo,plan,_=prepared
    first=dict(authorized_by='operator note',authorization_reference='session note')
    assert promo.promote(first)['candidate']==plan['candidate']
    assert inc.read_json(promo.journal/'authorization.json')==first
    # A later run with different human wording neither rewrites nor blocks.
    assert promo.promote({'authorization_reference':'other note'})['candidate']==plan['candidate']
    assert inc.read_json(promo.journal/'authorization.json')==first


def test_rollback_without_recorded_trace_keeps_reason_audit(prepared):
    promo,plan,_=prepared
    promo.promote()
    assert promo.rollback(reason='owner rollback')['status']=='ROLLED_BACK'
    assert promo.store.current_pointer()==plan['base']
    with pytest.raises(ValueError): promo.rollback(reason='')


def test_incremental_row_does_not_invent_ancestor_catalog_fields(tmp_path,built):
    from copy import deepcopy
    _,candidate,_=built
    candidate=deepcopy(candidate)
    # Canonical catalog intentionally stores only core identity/source columns
    # for retained ancestors. A richer ancestor manifest is not a catalog write.
    candidate.manifest['components']['reference']['content_identity']='/frozen/reference'
    path=tmp_path/'incremental-row.json';inc.seal(path,candidate.as_row())
    loaded=p.load_candidate(path)
    assert loaded.component('reference').content_identity is None
    assert loaded.component_hash()==candidate.component_hash()


def test_reference_lock_and_cas(prepared):
    promo,plan,_=prepared
    with reference_publication_lock(promo.data_root) as publish:
        with pytest.raises(BlockingIOError):
            with reference_publication_lock(promo.data_root): pass
        with pytest.raises(RuntimeError,match='COMPARE_AND_SWAP'):
            publish({},plan['reference_after'])
        assert publish(plan['reference_before'],plan['reference_after'])=='PUBLISHED'
        assert publish(plan['reference_after'],plan['reference_after'])=='NOOP'


def test_rollback_still_available_after_candidate_corruption(prepared):
    promo,plan,auth=prepared
    promo.promote(auth)
    Path(plan['candidate_path']).write_text('{}')
    assert promo.rollback(reason='candidate corruption')['status']=='ROLLED_BACK'


def test_interrupted_rollback_rolls_forward_to_previous_pair(prepared,monkeypatch):
    promo,plan,auth=prepared
    promo.promote(auth)
    original=promo.store.logical_rollback
    def interrupted(*args,**kwargs):
        original(*args,**kwargs)
        raise InterruptedError('after rollback commit')
    monkeypatch.setattr(promo.store,'logical_rollback',interrupted)
    with pytest.raises(InterruptedError):promo.rollback(reason='isolated recovery')
    assert promo.store.current_pointer()==plan['base']
    assert active_pointer(promo.data_root)[0]==plan['reference_after']
    monkeypatch.setattr(promo.store,'logical_rollback',original)
    promo.rollback(reason='isolated recovery')
    assert active_pointer(promo.data_root)[0]==plan['reference_before']


def test_retained_reader_during_commit(prepared):
    from modules.telchi.datalake.foundation_reader import FoundationReader
    promo,plan,auth=prepared
    reader=FoundationReader(metadata_catalog='',snapshot_resolver=lambda *_:100,
        component_verifier=lambda *_:None,verify_reference_path=False)
    with promo.store.connection_factory() as con:
        old=reader.resolve_on(con)
    promo.promote(auth)
    with promo.store.connection_factory() as con:
        new=reader.resolve_on(con)
        assert con.execute('SELECT count(*) FROM '+new.sales('sales_document')).fetchone()[0]==1
    assert old.foundation_publication_id==plan['base']
    assert new.foundation_publication_id==plan['candidate']
    assert old.manifest['components']!=new.manifest['components']


def test_prepare_no_publication_and_reader_failure_recoverable(prepared):
    promo,plan,auth=prepared
    assert promo.store.current_pointer()==plan['base']
    assert active_pointer(promo.data_root)[0]==plan['reference_before']
    original=promo.verify_reader
    promo.verify_reader=lambda _: (_ for _ in ()).throw(RuntimeError('reader'))
    with pytest.raises(RuntimeError,match='reader'): promo.promote(auth)
    assert not (promo.journal/'verified.json').exists()
    promo.verify_reader=original
    promo.promote(auth)
    assert (promo.journal/'verified.json').exists()
