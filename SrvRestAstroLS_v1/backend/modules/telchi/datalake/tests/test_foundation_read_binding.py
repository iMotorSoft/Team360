"""Read-path regression: physical validation is publisher work, never query work."""
from copy import deepcopy
from dataclasses import replace
import json

import pytest

from modules.telchi.datalake import foundation_reader as readers, sales_succession as succession
from modules.telchi.datalake.foundation_publication import FoundationReaderError, PublicationBoundaryError
from modules.telchi.datalake.foundation_read_binding import make_binding, digest
from .test_foundation_reader import connector, store, complete, reader
from modules.telchi.datalake import sales_foundation_promotion as promotion


def accredit(connector, store, suffix='A'):
    candidate = complete(store, suffix)
    access = reader(connector).get_current_foundation()
    publication = store.get(candidate.foundation_publication_id)
    binding = make_binding(publication, access, commercial=True)
    store.accredit_read_binding(publication, binding)
    return publication, binding


def fast(connector):
    return readers.FoundationReader(connector, metadata_catalog='')


def forbidden(*args, **kwargs):
    raise AssertionError('physical revalidation/history search on query path')


def test_fast_reader_does_not_search_or_validate_files(connector, store, monkeypatch):
    publication, binding = accredit(connector, store)
    monkeypatch.setattr(readers, '_resolve_commit_snapshot', forbidden)
    monkeypatch.setattr(readers, '_verify_component_publications', forbidden)
    monkeypatch.setattr(succession, 'validate_successor', forbidden)
    from modules.telchi.datalake import foundation_manifest, sales_facts_transition
    monkeypatch.setattr(foundation_manifest, 'validate_manifest', forbidden)
    monkeypatch.setattr(sales_facts_transition, 'verify_files', forbidden)
    monkeypatch.setattr(__import__('pathlib').Path, 'read_bytes', forbidden)
    for _ in range(3):
        access = fast(connector).get_current_foundation()
        assert access.foundation_publication_id == publication.foundation_publication_id
        assert access.ducklake_snapshot_id == access.commit_snapshot_id == 42
        assert access.read_binding == binding
        assert succession.admit(access, connector.connection) is None
        assert 'VERSION => 42' in access.sales('sales_document')


def test_fast_physical_metadata_does_not_hash_reference(connector, store, monkeypatch):
    candidate = complete(store, 'A')
    access = reader(connector).get_current_foundation()
    publication = store.get(candidate.foundation_publication_id)
    metadata = dict(reference=publication.reference_version, products_sha256='a'*64, crosswalk_sha256='b'*64)
    store.accredit_read_binding(publication, make_binding(publication, access, commercial=True, physical=metadata))
    monkeypatch.setattr(__import__('pathlib').Path, 'read_bytes', forbidden)
    monkeypatch.setattr(succession, 'validate_successor', forbidden)
    access = fast(connector).get_current_foundation()
    assert succession.physical_metadata(access) == metadata
    assert succession.admit(access, connector.connection, physical=True) == metadata


def test_missing_binding_fails_closed_without_reaccreditation(connector, store, monkeypatch):
    complete(store, 'A')
    monkeypatch.setattr(readers, '_resolve_commit_snapshot', forbidden)
    with pytest.raises(FoundationReaderError, match='READ_BINDING_REQUIRED'):
        fast(connector).get_current_foundation()
    # The failed read transaction was closed; explicit update validation works.
    assert reader(connector).get_current_foundation().ducklake_snapshot_id == 42


def test_current_switch_is_not_cached_and_old_access_stays_pinned(connector, store):
    a, _ = accredit(connector, store, 'A')
    old = fast(connector).get_current_foundation()
    b = complete(store, 'B', commit=False)
    with pytest.raises(PublicationBoundaryError, match='ATOMIC_ACCREDITATION_REQUIRED'):
        store.logical_commit(b.foundation_publication_id)
    assert fast(connector).get_current_foundation().foundation_publication_id == a.foundation_publication_id
    def approve(publication, con):
        full = replace(reader(connector).resolve_on(con), ducklake_snapshot_id=43, commit_snapshot_id=43)
        return make_binding(publication, full, commercial=True)
    store.logical_commit(b.foundation_publication_id, accredit=approve)
    new = fast(connector).get_current_foundation()
    assert old.foundation_publication_id == a.foundation_publication_id
    assert new.foundation_publication_id == b.foundation_publication_id
    assert old.foundation.sales_publication_id == 'sales-A'
    assert new.foundation.sales_publication_id == 'sales-B'
    assert 'VERSION => 42' in old.sales('sales_document')
    assert 'VERSION => 43' in new.sales('sales_document')
    # Retained publications keep their accreditation for rollback/inspection.
    assert store.read_binding(a.foundation_publication_id)


@pytest.mark.parametrize('mutation', ['id', 'snapshot', 'bool_snapshot', 'manifest', 'coverage', 'cutoff', 'hash', 'null', 'activation', 'anchor'])
def test_invalid_binding_rejected(connector, store, mutation):
    publication, original = accredit(connector, store)
    binding = deepcopy(original)
    if mutation == 'id': binding['foundation_publication_id'] = 'other'
    if mutation == 'snapshot': binding['snapshot_id'] = 999
    if mutation == 'bool_snapshot': binding['snapshot_id'] = True
    if mutation == 'manifest': binding['manifest_sha256'] = '0'*64
    if mutation == 'coverage': binding['coverage'] = [{'complete': True}]
    if mutation == 'cutoff': binding['source_as_of'] = 'different'
    if mutation == 'activation': binding['activation'] = dict(protocol='untrusted', prepared_snapshot_id=42)
    if mutation == 'anchor': binding['activation'] = dict(protocol='atomic-current-receipt-v1', prepared_snapshot_id=99)
    if mutation == 'hash': binding['receipt_sha256'] = '0'*64
    elif mutation != 'null':
        binding['receipt_sha256'] = digest({k:v for k,v in binding.items() if k != 'receipt_sha256'})
    if mutation == 'null': binding = None
    connector.connection.execute('UPDATE ops.foundation_publications_v1 SET read_binding_json=?', [json.dumps(binding)])
    with pytest.raises(FoundationReaderError):
        fast(connector).get_current_foundation()


def test_manifest_change_invalidates_receipt(connector, store):
    publication, _ = accredit(connector, store)
    publication.manifest['base_snapshot_id'] = 43
    connector.connection.execute('UPDATE ops.foundation_publications_v1 SET manifest_json=?', [json.dumps(publication.manifest)])
    with pytest.raises(FoundationReaderError, match='READ_BINDING_INVALID'):
        fast(connector).get_current_foundation()


def test_receipt_is_immutable_and_cas_protected(connector, store):
    publication, binding = accredit(connector, store)
    store.accredit_read_binding(publication, binding)  # idempotent recovery
    changed = deepcopy(binding)
    changed['commercial'] = False
    changed['receipt_sha256'] = digest({k:v for k,v in changed.items() if k != 'receipt_sha256'})
    with pytest.raises(PublicationBoundaryError, match='IMMUTABLE'):
        store.accredit_read_binding(publication, changed)
    b = complete(store, 'B', commit=False)
    def approve(current, con):
        return make_binding(current, reader(connector).resolve_on(con), commercial=True)
    store.logical_commit(b.foundation_publication_id, accredit=approve)
    with pytest.raises(PublicationBoundaryError, match='CURRENT_CHANGED'):
        store.accredit_read_binding(publication, binding)


def test_result_binding_only_checks_metadata(connector, store, monkeypatch):
    accredit(connector, store)
    from modules.telchi.datalake import ducklake
    monkeypatch.setattr(ducklake, 'DuckLakeConnector', lambda: connector)
    actual = fast(connector)
    monkeypatch.setattr(readers, 'FoundationReader', lambda *_: actual)
    monkeypatch.setattr(succession, 'validate_successor', forbidden)
    access = actual.get_current_foundation()
    source = succession.source_metadata(access)
    assert succession.result_binding(source) is None
    with pytest.raises(ValueError, match='binding_mismatch'):
        succession.result_binding(dict(source, snapshot_id=999))
    with pytest.raises(FoundationReaderError, match='accreditation missing'):
        succession.result_binding(source, physical=True)


@pytest.mark.parametrize('failure', [None, 'reader', 'commercial', 'physical'])
def test_real_publisher_receipt_follows_full_gates(connector, store, monkeypatch, tmp_path, failure):
    candidate = complete(store, 'A')
    current = store.get(candidate.foundation_publication_id)
    access = reader(connector).get_current_foundation()
    events = []
    class UpdateReader:
        def __init__(self, connector, *, full_validation):
            assert full_validation is True
        def resolve_on(self, con):
            events.append('reader')
            if failure == 'reader': raise RuntimeError('gate failed')
            return access
    from modules.telchi.datalake import ducklake
    monkeypatch.setattr(ducklake, 'DuckLakeConnector', lambda: connector)
    monkeypatch.setattr(promotion, 'FoundationPublicationStore', lambda *args: store)
    monkeypatch.setattr(readers, 'FoundationReader', UpdateReader)
    def validate(store, publication, snapshot, *, physical, _reader_validated):
        gate = 'physical' if physical else 'commercial'
        events.append(gate)
        assert _reader_validated
        if failure == gate: raise RuntimeError('gate failed')
    monkeypatch.setattr(succession, 'validate_successor', validate)
    metadata = dict(reference=current.reference_version, products_sha256='a'*64, crosswalk_sha256='b'*64)
    monkeypatch.setattr(succession, 'physical_metadata', lambda *_: metadata)
    publisher = promotion.real_promotion(tmp_path/'journal')
    if failure:
        with pytest.raises(RuntimeError, match='gate failed'):
            publisher.verify_reader(current)
        with pytest.raises(FoundationReaderError, match='READ_BINDING_REQUIRED'):
            store.read_binding(current.foundation_publication_id)
    else:
        publisher.verify_reader(current)
        receipt = store.read_binding(current.foundation_publication_id)
        assert receipt['physical'] == metadata and receipt['commercial'] is True
        assert events == ['reader', 'commercial', 'physical']
        publisher.verify_reader(current)
        assert receipt == store.read_binding(current.foundation_publication_id)


def test_accredited_dataset_dispatch_keeps_only_light_checks(connector, store, monkeypatch):
    accredit(connector, store)
    access = fast(connector).get_current_foundation()
    from modules.telchi.datalake import operational_domains, product_commercial_semantics as semantics
    flags = []
    def observed(*args, verify_physical):
        flags.append(verify_physical)
        return 'pinned observation'
    def semantic(*args, verify_physical):
        flags.append(verify_physical)
        return 'pinned semantics'
    access.manifest['components'][semantics.COMPONENT] = {}  # dispatch-only fixture
    monkeypatch.setattr(operational_domains, 'relation', observed)
    monkeypatch.setattr(semantics, 'dataset_relation', semantic)
    monkeypatch.setattr(semantics, 'read_component', semantic)
    assert access.operational_observation('production', 'orders') == 'pinned observation'
    assert access.product_semantics_relation('fixture') == 'pinned semantics'
    assert access.product_commercial_semantics() == 'pinned semantics'
    assert flags == [False, False, False]
    full = replace(access, read_binding=None)
    full.operational_observation('production', 'orders')
    full.product_semantics_relation('fixture')
    full.product_commercial_semantics()
    assert flags[-3:] == [True, True, True]


def test_denied_commercial_accreditation(connector, store):
    candidate = complete(store, 'A')
    publication = store.get(candidate.foundation_publication_id)
    access = reader(connector).get_current_foundation()
    store.accredit_read_binding(publication, make_binding(publication, access))
    with pytest.raises(FoundationReaderError, match='accreditation missing'):
        succession.admit(fast(connector).get_current_foundation(), connector.connection)
