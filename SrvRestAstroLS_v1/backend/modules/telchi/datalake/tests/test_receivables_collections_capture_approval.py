"""Capture uses the existing canonical receipt validator, not historical IDs."""
from copy import deepcopy
from datetime import date
import json

import pytest

from modules.telchi.datalake import receivables_collections_atomic as atomic
from modules.telchi.datalake.foundation_publication import FoundationReaderError
from modules.telchi.datalake.foundation_read_binding import digest
from modules.telchi.datalake.foundation_reader import FoundationReader
from .test_foundation_reader import connector, store
from .test_foundation_read_binding import accredit


class Source:
    sap_write_count = 0

    def __init__(self):
        self.query_log = []

    def query_read_only(self, query_id, sql, params=()):
        self.query_log.append(query_id)
        if query_id == 'receivables_source_as_of':
            return [dict(source_date='2026-11-03', source_as_of='2026-11-03T00:00:00')]
        return []


@pytest.fixture
def setup(connector, store, monkeypatch, tmp_path):
    # Only adapt the fixture's catalog name, retaining the real fast validator.
    monkeypatch.setattr(atomic, 'FoundationReader', lambda c: FoundationReader(c, metadata_catalog=''))
    monkeypatch.setenv('TELCHI_DUCKDB_TEMP_DIRECTORY', str(tmp_path/'tmp'))
    monkeypatch.setattr(atomic, 'STATE_ROOT', tmp_path/'state')
    monkeypatch.setattr(atomic, 'EVIDENCE_ROOT', tmp_path/'evidence')
    return connector, store


@pytest.mark.parametrize('suffix', ['different-approved-base', 'successor-approved-base'])
def test_capture_plan_accepts_any_approved_current(setup, suffix):
    connector, store = setup
    publication, receipt = accredit(connector, store, suffix)
    source = Source()
    result = atomic.run_atomic(connector=connector, source=source, plan_only=True,
                               history_end=date(2026, 11, 1))
    assert result['FOUNDATION_CURRENT'] == publication.foundation_publication_id
    assert result['foundation_approval']['receipt_sha256'] == receipt['receipt_sha256']
    assert result['foundation_approval']['snapshot_id'] == 42
    assert result['segments'][-1] == 'payment_term-all'
    assert source.query_log == ['receivables_source_as_of']


@pytest.mark.parametrize('mutation', ['missing', 'hash', 'snapshot', 'components', 'manifest', 'status', 'pointer'])
def test_invalid_approval_fails_before_sap_or_writes(setup, mutation):
    connector, store = setup
    publication, receipt = accredit(connector, store)
    receipt = deepcopy(receipt)
    if mutation == 'missing':
        connector.connection.execute('UPDATE ops.foundation_publications_v1 SET read_binding_json=NULL')
    elif mutation == 'manifest':
        manifest = dict(publication.manifest, base_snapshot_id=43)
        connector.connection.execute('UPDATE ops.foundation_publications_v1 SET manifest_json=?', [json.dumps(manifest)])
    elif mutation == 'status':
        connector.connection.execute("UPDATE ops.foundation_publications_v1 SET status='SUPERSEDED'")
    elif mutation == 'pointer':
        connector.connection.execute('DELETE FROM ops.foundation_current_v1')
    else:
        if mutation == 'hash': receipt['receipt_sha256'] = '0'*64
        if mutation == 'snapshot': receipt['snapshot_id'] = 99
        if mutation == 'components': receipt['components'] = {}
        if mutation != 'hash':
            receipt['receipt_sha256'] = digest({k:v for k,v in receipt.items() if k != 'receipt_sha256'})
        connector.connection.execute('UPDATE ops.foundation_publications_v1 SET read_binding_json=?', [json.dumps(receipt)])
    source = Source()
    with pytest.raises(FoundationReaderError):
        atomic.run_atomic(connector=connector, source=source, plan_only=True, history_end=date(2026, 11, 1))
    assert source.query_log == []


def test_resume_rejects_approval_change_before_segment_writes(setup, monkeypatch):
    connector, store = setup
    publication, receipt = accredit(connector, store)
    approval = atomic._foundation_approval(connector)
    monkeypatch.setattr(atomic, '_latest_resumable', lambda: ('old', dict(
        segments={'old': {}}, history_end_exclusive='2026-11-01',
        foundation_approval=dict(approval, foundation_publication_id='different'))))
    with pytest.raises(atomic.AtomicBuildError, match='approval changed'):
        atomic.run_atomic(connector=connector, source=Source(), resume=True, history_end=date(2026, 11, 1))
    assert store.current_pointer() == publication.foundation_publication_id


def test_resume_rejects_unbound_legacy_checkpoint(setup, monkeypatch):
    connector, store = setup
    accredit(connector, store)
    monkeypatch.setattr(atomic, '_latest_resumable', lambda: ('old', dict(
        segments={'old': {}}, history_end_exclusive='2026-11-01')))
    with pytest.raises(atomic.AtomicBuildError, match='approval changed or missing'):
        atomic.run_atomic(connector=connector, source=Source(), resume=True, history_end=date(2026, 11, 1))


@pytest.mark.parametrize('drift', [False, True])
def test_completion_requires_same_approval(setup, monkeypatch, drift):
    connector, store = setup
    publication, _ = accredit(connector, store)
    original = atomic._foundation_approval
    calls = []

    def approval(c):
        value = original(c)
        calls.append(value)
        if drift and len(calls) == 3:
            return dict(value, receipt_sha256='different')
        return value

    monkeypatch.setattr(atomic, '_foundation_approval', approval)
    monkeypatch.setattr(atomic, 'plan_segments', lambda *args: [atomic.Segment('payment_term', None, None)])
    monkeypatch.setattr(atomic, 'publish_segment', lambda *args, **kw: {'transactional': True})
    monkeypatch.setattr(atomic, 'local_validations', lambda c: dict(status='PASS', counts={}, counts_2026={}))
    monkeypatch.setattr(atomic, 'validate_gold_cases', lambda c: dict(status='PASS'))
    monkeypatch.setattr(atomic, 'bounded_sap_reconciliation', lambda *args: dict(status='PASS'))
    monkeypatch.setattr(atomic, '_write_evidence', lambda **kw: None)
    if drift:
        with pytest.raises(atomic.AtomicBuildError, match='approval changed during capture'):
            atomic.run_atomic(connector=connector, source=Source(), run_id='test', history_end=date(2026, 11, 1))
    else:
        result = atomic.run_atomic(connector=connector, source=Source(), run_id='test', history_end=date(2026, 11, 1))
        assert result['FINAL_VERDICT'].endswith('_PASS')
        assert result['FOUNDATION_CURRENT_AFTER'] == publication.foundation_publication_id
        state = atomic._json(atomic._state_path('test'))
        assert state['foundation_approval'] == calls[0]
    assert store.current_pointer() == publication.foundation_publication_id


def test_cooperative_pacing_runs_only_for_pending_segments_before_guard_timer(setup, monkeypatch):
    connector, store = setup
    accredit(connector, store)
    approval=atomic._foundation_approval(connector)
    done=atomic.Segment('receivable_document',date(2026,9,1),date(2026,10,1))
    pending=atomic.Segment('payment_term',None,None)
    state=dict(segments={done.segment_id:dict(status='COMPLETED')},
        history_end_exclusive='2026-11-01',foundation_approval=approval)
    monkeypatch.setattr(atomic,'_latest_resumable',lambda:('paced',state))
    monkeypatch.setattr(atomic,'plan_segments',lambda *a:[done,pending])
    monkeypatch.setattr(atomic,'publish_segment',lambda *a,**kw:dict(transactional=True))
    monkeypatch.setattr(atomic,'local_validations',lambda c:dict(status='PASS',counts={},counts_2026={}))
    monkeypatch.setattr(atomic,'validate_gold_cases',lambda c:dict(status='PASS'))
    monkeypatch.setattr(atomic,'bounded_sap_reconciliation',lambda *a:dict(status='PASS'))
    monkeypatch.setattr(atomic,'_write_evidence',lambda **kw:None)
    original=atomic.ResourceGuard
    guards=[]
    def guard(**kw):
        g=original(**kw);guards.append(g);return g
    monkeypatch.setattr(atomic,'ResourceGuard',guard)
    called=[]
    def pace(segment):
        assert guards[0]._active_workers==0 and guards[0]._started_at is None
        called.append(segment.segment_id)
    source=Source()
    result=atomic.run_atomic(connector=connector,source=source,resume=True,
        history_end=date(2026,11,1),before_segment=pace)
    assert result['FINAL_VERDICT'].endswith('_PASS')
    assert called==['payment_term-all']
    assert source.query_log==['receivables_source_as_of','atomic_payment_term-all']


def test_capture_rechecks_approval_before_atomic_write(setup, monkeypatch):
    connector, store = setup
    publication, _ = accredit(connector, store)
    source = Source()
    original = source.query_read_only

    def query(*args, **kwargs):
        rows = original(*args, **kwargs)
        if args[0].startswith('atomic_'):
            connector.connection.execute('UPDATE ops.foundation_publications_v1 SET read_binding_json=NULL')
        return rows

    source.query_read_only = query
    monkeypatch.setattr(atomic, 'plan_segments', lambda *args: [atomic.Segment('payment_term', None, None)])
    monkeypatch.setattr(atomic, 'publish_segment', lambda *a, **kw: pytest.fail('must not write after approval loss'))
    with pytest.raises(FoundationReaderError):
        atomic.run_atomic(connector=connector, source=source, history_end=date(2026, 11, 1))
    assert store.current_pointer() == publication.foundation_publication_id
