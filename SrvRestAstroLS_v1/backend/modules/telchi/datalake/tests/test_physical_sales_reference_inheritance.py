"""Reference-only successors must retain sealed sales, not fall back to Atomic.

Small offline fixtures: real manifest, file hashing and reader; no SAP/PG.
"""
from copy import deepcopy
import pytest

from modules.telchi.datalake import reference_compatibility as compatibility
from modules.telchi.datalake import foundation_reader as reader
from modules.telchi.datalake.foundation_manifest import validate_manifest
from modules.telchi.datalake.foundation_publication import ComponentReference, READY_TO_COMMIT
from .test_sales_facts_transition import built, store  # noqa: F401
from .test_physical_reference_offline import eight  # noqa: F401


def test_prepare_only_roundtrips_through_durable_promotion_loader(eight, tmp_path):
    import json
    from modules.telchi.datalake import update, foundation_publication as fp
    from modules.telchi.datalake.sales_foundation_promotion import load_candidate
    store, _, new, old_id = eight
    result = update.publish_reference_only(connector=None, foundation_store=store,
        reference={'reference_version': 'ref-v2', 'reference_path': str(new), 'source_as_of': 'observed'},
        base_data_snapshot_id=84, prepare_only=True)
    assert result['status'] == 'PREPARED'
    assert store.current_pointer() == old_id
    identity = result['foundation_publication_id']
    with store.connection_factory() as con:
        row = con.execute(f'SELECT {fp._SELECT_COLUMNS} FROM {store.publications_table} '
                          'WHERE foundation_publication_id=?', [identity]).fetchone()
    path = tmp_path / 'prepared.json'
    path.write_text(json.dumps(dict(zip(fp._COLUMN_NAMES, row)), default=str))
    loaded = load_candidate(path)
    assert loaded.foundation_publication_id == identity
    assert loaded.status == READY_TO_COMMIT
    assert validate_manifest(store, loaded) == loaded.manifest['components']


def test_sales_dispatch_does_not_downgrade_a_corrupt_sales_envelope():
    from modules.telchi.datalake.sales_facts_transition import KIND, uses_sealed_sales
    assert uses_sealed_sales({'candidate_kind': KIND})  # must reach validation and fail
    assert uses_sealed_sales({'candidate_kind': compatibility.KIND, 'sales_facts_revalidation': {}})
    assert not uses_sealed_sales({'candidate_kind': compatibility.KIND})
    assert not uses_sealed_sales({'candidate_kind': 'FOUNDATION_BASE_V1'})


def commit(store, publication):
    store.create_candidate(publication)
    store.set_status(publication.foundation_publication_id, READY_TO_COMMIT)
    store.logical_commit(publication.foundation_publication_id)
    return store.get(publication.foundation_publication_id)


def successor(base, monkeypatch):
    p = deepcopy(base)
    identity = base.foundation_publication_id + '_physical'
    version = base.reference_version + '_physical'
    proof = dict(previous_reference_path=str(reader.DATA_ROOT / 'reference/_versions' / base.reference_version),
                 reference_path=str(reader.DATA_ROOT / 'reference/_versions' / version))
    # Compatibility projection has its own real-Parquet regression suite. This
    # fixture isolates inheritance and keeps the manifest/reader paths real.
    previous_projection = compatibility.reference_projection
    def projection(old, new):
        if str(old) == proof['previous_reference_path'] and str(new) == proof['reference_path']:
            return proof
        return previous_projection(old, new)
    monkeypatch.setattr(compatibility, 'reference_projection', projection)
    reference = ComponentReference('reference', version, content_identity=proof['reference_path'])
    p.foundation_publication_id = identity
    p.previous_foundation_publication_id = base.foundation_publication_id
    p.reference_version = version
    p.components['reference'] = reference
    p.manifest.update(foundation_publication_id=identity, candidate_kind=compatibility.KIND,
                      base_foundation_publication_id=base.foundation_publication_id,
                      reference_version=version, reference_data_snapshot_id=90,
                      reference_compatibility=proof)
    p.manifest['components']['reference'] = reference.as_dict()
    return p


def test_reference_successor_reads_exact_sealed_sales_and_keeps_snapshots(store, built, monkeypatch):
    _, sales, _ = built
    sales = commit(store, sales)
    p = successor(sales, monkeypatch)
    assert validate_manifest(store, p) == p.manifest['components']
    for name, entry in sales.manifest['components'].items():
        if name != 'reference':
            assert p.manifest['components'][name] == entry
    p = commit(store, p)
    r = reader.FoundationReader(metadata_catalog='', snapshot_resolver=lambda *_: 999,
                                component_verifier=lambda *_: None, verify_reference_path=False)
    with store.connection_factory() as con:
        access = r.resolve_on(con)
        assert access.ducklake_snapshot_id == 90
        assert access.manifest_base_snapshot_id == 84
        assert 'read_parquet' in access.sales('sales_document')
        assert 'read_parquet' in access.credit_memo('credit_memo_line')
        assert con.execute('SELECT doc_entry FROM ' + access.sales('sales_document')).fetchone() == ('1',)
        assert 'VERSION => 90' in access.oinm()
        assert 'VERSION => 84' in access.receivables_collections('receivable_settlement_status')
        assert len(access.require_sales_coverage('sales', '2026-10-01', '2026-10-30')) == 29
    # A second metadata-only successor must preserve the original facts too.
    chained = successor(p, monkeypatch)
    assert validate_manifest(store, chained) == chained.manifest['components']
    store.logical_rollback(sales.foundation_publication_id,
        expected_current_foundation_publication_id=p.foundation_publication_id, reason='offline regression')
    assert store.current_pointer() == sales.foundation_publication_id


@pytest.mark.parametrize('field', ['sales_coverage', 'sales_facts_revalidation', 'facts_base_snapshot_id'])
def test_reference_successor_rejects_changed_sales_provenance(store, built, monkeypatch, field):
    _, sales, _ = built
    sales = commit(store, sales)
    p = successor(sales, monkeypatch)
    p.manifest.pop(field)
    with pytest.raises(Exception, match='sales provenance'):
        validate_manifest(store, p)
    assert store.current_pointer() == sales.foundation_publication_id


def test_reference_successor_rejects_changed_data_snapshot(store, built, monkeypatch):
    _, sales, _ = built
    sales = commit(store, sales)
    p = successor(sales, monkeypatch)
    p.manifest['reference_data_snapshot_id'] = 999
    with pytest.raises(Exception, match='sales data snapshot'):
        validate_manifest(store, p)


def test_reference_successor_rechecks_physical_sales_files(store, built, monkeypatch):
    from pathlib import Path
    _, sales, _ = built
    sales = commit(store, sales)
    p = commit(store, successor(sales, monkeypatch))
    path = Path(p.manifest['components']['sales']['facts_contract']['datasets']['sales_line']['path'])
    path.write_bytes(b'corrupt fixture')
    r = reader.FoundationReader(metadata_catalog='', snapshot_resolver=lambda *_: 999,
                                component_verifier=lambda *_: None, verify_reference_path=False)
    with store.connection_factory() as con, pytest.raises(Exception, match='physical hash'):
        r.resolve_on(con)
