"""Atomic selection/receipt tests. All catalogs and files are isolated fixtures."""
from contextlib import contextmanager
import subprocess
import sys
from pathlib import Path

from modules.telchi.datalake.sales_foundation_promotion import load_candidate
from .test_foundation_reader import complete

import duckdb
import pytest

from modules.telchi.datalake.foundation_publication import FoundationPublicationStore, FoundationReaderError
from modules.telchi.datalake.foundation_reader import FoundationReader
from modules.telchi.datalake.foundation_read_binding import make_binding
from .test_sales_foundation_promotion import prepared, built, store


@pytest.mark.parametrize('failure', ['reader', 'receipt', 'interrupt'])
def test_failed_final_gate_rolls_back_selection_and_receipt(prepared, failure):
    promo, plan, _ = prepared
    original = promo.accredit
    def fail(candidate, con):
        binding = original(candidate, con)
        if failure == 'receipt':
            binding['manifest_sha256'] = '0'*64
            return binding
        if failure == 'interrupt':
            raise KeyboardInterrupt('simulated shutdown before atomic COMMIT')
        raise RuntimeError('final business reader failed')
    promo.accredit = fail
    with pytest.raises((RuntimeError, FoundationReaderError, KeyboardInterrupt)):
        promo.promote()
    assert promo.store.current_pointer() == plan['base']
    assert promo.store.get(plan['base']).status == 'CURRENT'
    assert promo.store.get(plan['candidate']).status == 'READY_TO_COMMIT'
    with pytest.raises(FoundationReaderError):
        promo.store.read_binding(plan['candidate'])
    promo.accredit = original
    promo.promote()
    assert promo.store.read_binding(plan['candidate'])['commercial'] is True


@pytest.mark.parametrize('native_ducklake', [False, True])
def test_concurrent_reader_sees_old_approval_until_atomic_commit(prepared, tmp_path, native_ducklake, request):
    promo, plan, _ = prepared
    original_store = promo.store
    path = tmp_path/'metadata.duckdb'
    if native_ducklake:
        host = duckdb.connect(config={'threads':2})
        request.addfinalizer(host.close)
        host.execute('LOAD ducklake')
        host.execute(f"ATTACH 'ducklake:{tmp_path}/lake.ducklake' AS telchi (DATA_PATH '{tmp_path}/lake-data')")
    @contextmanager
    def session():
        con = host.cursor() if native_ducklake else duckdb.connect(str(path), config={'threads':2})
        try:
            yield con
        finally:
            con.close()
    catalog = 'telchi' if native_ducklake else ''
    durable = FoundationPublicationStore(session, catalog=catalog)
    durable.ensure_schema()
    for publication in original_store.list_publications():
        durable.create_candidate(publication)
    with session() as con:
        con.execute(f'INSERT INTO {durable.pointer_table} VALUES (1, ?, ?)', [plan['base'], 'fixture'])
    base = durable.get(plan['base'])
    def full(con):
        return FoundationReader(metadata_catalog=catalog, snapshot_resolver=lambda *_:100,
            component_verifier=lambda *_:None, verify_reference_path=False).resolve_on(con)
    with session() as con:
        old_access = full(con)
    durable.accredit_read_binding(base, make_binding(base, old_access, commercial=True))
    fast = FoundationReader(metadata_catalog=catalog)
    def accredit(candidate, con):
        # This connection sees the pending selection, an independent reader
        # still sees the complete prior approval and never the missing receipt.
        access = full(con)
        assert access.foundation_publication_id == plan['candidate']
        with session() as other:
            during = fast.resolve_on(other)
            assert during.foundation_publication_id == plan['base']
        return make_binding(candidate, access, commercial=True)
    promo.store, promo.accredit = durable, accredit
    promo.promote()
    with session() as con:
        after = fast.resolve_on(con)
        assert after.foundation_publication_id == plan['candidate']
        assert after.read_binding['snapshot_id'] == 90
        assert con.execute('SELECT count(*) FROM '+after.sales('sales_document')).fetchone()[0] == 1
    assert old_access.foundation_publication_id == plan['base']
    assert durable.read_binding(plan['base'])
    # Reentry uses the already persisted receipt, never reruns full validation.
    promo.accredit = lambda *_: (_ for _ in ()).throw(AssertionError('unexpected reaccreditation'))
    assert promo.promote()['candidate'] == plan['candidate']


def test_process_exit_before_commit_preserves_durable_current(prepared, tmp_path):
    promo, plan, _ = prepared
    path = tmp_path/'crash-metadata.duckdb'
    @contextmanager
    def session():
        with duckdb.connect(str(path), config={'threads':2}) as con:
            yield con
    durable = FoundationPublicationStore(session, catalog='')
    durable.ensure_schema()
    for publication in promo.store.list_publications():
        durable.create_candidate(publication)
    with session() as con:
        con.execute(f'INSERT INTO {durable.pointer_table} VALUES (1, ?, ?)', [plan['base'], 'fixture'])
    durable.accredit_read_binding(durable.get(plan['base']), promo.store.read_binding(plan['base']))
    # Preparing a candidate is durable, but selecting it remains transactional.
    candidate = load_candidate(Path(plan['candidate_path']))
    durable.create_candidate(candidate)
    durable.set_status(plan['candidate'], 'READY_TO_COMMIT')
    child = '''
from contextlib import contextmanager
import duckdb, os, sys
from modules.telchi.datalake.foundation_publication import FoundationPublicationStore
@contextmanager
def session():
    with duckdb.connect(sys.argv[1], config={'threads':2}) as con:
        yield con
store=FoundationPublicationStore(session,catalog='')
def exit_before_commit(candidate,con):
    assert store._pointer_on_connection(con)==sys.argv[2]
    os._exit(73)
store.logical_commit(sys.argv[2],accredit=exit_before_commit)
'''
    result = subprocess.run([sys.executable, '-c', child, str(path), plan['candidate']], timeout=30, capture_output=True)
    assert result.returncode == 73, result.stderr.decode()
    assert durable.current_pointer() == plan['base']
    assert durable.get(plan['candidate']).status == 'READY_TO_COMMIT'
    assert durable.read_binding(plan['base'])
    with pytest.raises(FoundationReaderError):
        durable.read_binding(plan['candidate'])


def test_real_publisher_uses_verified_preparation_anchor(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from modules.telchi.datalake import ducklake, foundation_reader, sales_foundation_promotion as promotion, sales_succession
    from modules.telchi.runtime.resource_guard import ResourceGuard
    host = duckdb.connect(config={'threads':2})
    try:
        host.execute('LOAD ducklake')
        host.execute(f"ATTACH 'ducklake:{tmp_path}/publisher.ducklake' AS telchi (DATA_PATH '{tmp_path}/data')")
        class Connector:
            @contextmanager
            def session(self, *, read_only=False):
                con=host.cursor()
                try: yield con
                finally: con.close()
            def snapshot(self, con):
                return con.execute("SELECT id FROM ducklake_current_snapshot('telchi')").fetchone()[0]
        connector=Connector()
        store=FoundationPublicationStore(connector.session)
        store.ensure_schema()
        candidate=complete(store,'A',commit=False)
        reference=tmp_path/'reference/_versions/ref-A'
        reference.mkdir(parents=True)
        monkeypatch.setattr(ducklake,'DuckLakeConnector',lambda:connector)
        monkeypatch.setattr(foundation_reader,'DATA_ROOT',tmp_path)
        # Fixture legacy components have no real initial-publication registry;
        # metadata transaction/receipt/anchor behavior uses actual DuckLake.
        monkeypatch.setattr(foundation_reader,'_verify_component_publications',lambda *_:None)
        gates=[]
        def validate(*args,physical,**kwargs): gates.append(physical)
        monkeypatch.setattr(sales_succession,'validate_successor',validate)
        monkeypatch.setattr(sales_succession,'physical_metadata',lambda *_:dict(reference='ref-A',products_sha256='a'*64,crosswalk_sha256='b'*64))
        monkeypatch.setattr(ResourceGuard,'assess',lambda *_:SimpleNamespace(allowed=True))
        publisher=promotion.real_promotion(tmp_path/'journal')
        anchor=connector.snapshot(host)
        store.logical_commit(candidate.foundation_publication_id,accredit=publisher.accredit)
        binding=store.read_binding(candidate.foundation_publication_id)
        assert binding['activation']==dict(protocol='atomic-current-receipt-v1',prepared_snapshot_id=anchor)
        assert binding['commit_snapshot_id']==anchor
        assert connector.snapshot(host)>anchor
        assert gates==[False,True]
        with connector.session(read_only=True) as con:
            access=FoundationReader(connector).resolve_on(con)
            assert access.foundation_publication_id==candidate.foundation_publication_id
            assert access.read_binding==binding
    finally:
        host.close()
