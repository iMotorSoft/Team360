"""Additive commercial envelope regression, including strict inherited contracts."""
from contextlib import contextmanager
from copy import deepcopy

import duckdb
import pytest

from modules.telchi.datalake import commercial_purpose_candidate as commercial
from modules.telchi.datalake.foundation_manifest import validate_manifest, EXTENSIBLE_KIND
from modules.telchi.datalake.foundation_publication import (
    ComponentReference, FoundationPublicationStore, FoundationReaderError,
    prepare_candidate, READY_TO_COMMIT,
)
from modules.telchi.datalake.raw import digest


def extension(base, name):
    stable = dict(contract_version='1.0.0', schema_version='1.0.0',
        source_provenance={'receipt': 'exact'}, dataset_hashes={'rows': 'a'*64},
        dependencies=dict(foundation_publication_id=base.foundation_publication_id,
            base_snapshot_id=base.manifest['base_snapshot_id'], reference_version=base.reference_version,
            components_hash=digest(base.manifest['components'])))
    fingerprint = digest(stable)
    return dict(name=name, publication_id=name+'_'+fingerprint[:24],
        component_fingerprint=fingerprint, content_identity=fingerprint, stable_contract=stable,
        datasets={'rows': dict(logical_hash='a'*64, file_references=['/sealed/file.parquet'],
                                file_hashes=['b'*64], row_count=1)})


@pytest.fixture
def foundation():
    con = duckdb.connect()
    @contextmanager
    def session():
        yield con
    store = FoundationPublicationStore(session, catalog='')
    p = prepare_candidate(store, update_run_id='legacy', reference_version='ref-v1')
    refs = {name: ComponentReference(name, name+'-v1', '2026-10-31')
            for name in ('reference', 'sales', 'credit_memo', 'oinm', 'oitw')}
    refs['reference'] = ComponentReference('reference', 'ref-v1', '2026-10-31')
    entries = {name: ref.as_dict() for name, ref in refs.items()}
    entries.update({name: dict(name=name, publication_id=name+'-v1')
                    for name in ('material_supply', 'receivables_collections')})
    manifest = dict(foundation_publication_id=p.foundation_publication_id,
        candidate_kind='RECEIVABLES_COLLECTIONS_FOUNDATION_V1', base_snapshot_id=42,
        components=entries, sales_facts_revalidation={'sealed': True},
        permissions={'scope': 'unchanged'}, operational_observations={'sealed': True},
        sales_coverage=[{'start': '2026-10-01', 'end': '2026-11-01'}])
    store.update_components(p.foundation_publication_id, refs, manifest=manifest)
    store.set_status(p.foundation_publication_id, READY_TO_COMMIT)
    store.logical_commit(p.foundation_publication_id)
    old = store.get(p.foundation_publication_id)
    p = prepare_candidate(store, update_run_id='purchasing', reference_version=old.reference_version)
    manifest = deepcopy(old.manifest)
    manifest.update(foundation_publication_id=p.foundation_publication_id,
        candidate_kind=EXTENSIBLE_KIND, manifest_schema_version='1.0.0',
        base_foundation_publication_id=old.foundation_publication_id, update_run_id='purchasing')
    manifest['components']['purchasing'] = extension(old, 'purchasing')
    store.update_components(p.foundation_publication_id, dict(old.components), manifest=manifest)
    validate_manifest(store, store.get(p.foundation_publication_id))
    store.set_status(p.foundation_publication_id, READY_TO_COMMIT)
    store.logical_commit(p.foundation_publication_id)
    yield store, store.get(p.foundation_publication_id)
    con.close()


def candidate(store, base, monkeypatch):
    monkeypatch.setattr(commercial, 'build_extension_component', lambda *args: extension(base, 'commercial_purpose'))
    ref = ComponentReference('commercial_purpose', 'unused', '2026-10-31')
    p = commercial.create_commercial_purpose_candidate(store, base_foundation=base,
        base_snapshot_id=42, component=ref, dataset_manifests={}, update_run_id='commercial', source_as_of='2026-10-31')
    return store.get(p.foundation_publication_id)


def test_eight_plus_one_exact_catalog_and_metadata(foundation, monkeypatch):
    store, base = foundation
    before = deepcopy(base.as_dict())
    p = candidate(store, base, monkeypatch)
    assert p.manifest['candidate_kind'] == EXTENSIBLE_KIND
    assert p.components == base.components
    assert len(validate_manifest(store, p)) == 9
    assert commercial.validate_pinned_candidate(store, p.foundation_publication_id).snapshot_id == 42
    assert store.current_pointer() == base.foundation_publication_id
    assert store.get(base.foundation_publication_id).as_dict() == before
    for name, entry in base.manifest['components'].items():
        assert p.manifest['components'][name] == entry
    from modules.telchi.datalake.sales_facts_transition import uses_sealed_sales
    assert uses_sealed_sales(p.manifest)


@pytest.mark.parametrize('field', ['sales_coverage', 'permissions', 'operational_observations', 'facts_base_snapshot_id'])
def test_inherited_business_metadata_cannot_change(foundation, monkeypatch, field):
    store, base = foundation
    p = candidate(store, base, monkeypatch)
    p.manifest[field] = 'tampered'
    with pytest.raises(FoundationReaderError, match='inherited business'):
        validate_manifest(store, p)


@pytest.mark.parametrize('name', ['sales', 'material_supply', 'purchasing', 'receivables_collections'])
def test_no_existing_component_can_disappear(foundation, monkeypatch, name):
    store, base = foundation
    p = candidate(store, base, monkeypatch)
    del p.manifest['components'][name]
    with pytest.raises(FoundationReaderError):
        validate_manifest(store, p)


def test_existing_publisher_loads_extension_without_inventing_catalog_fields(foundation, monkeypatch, tmp_path):
    from modules.telchi.datalake.sales_foundation_promotion import load_candidate
    from modules.telchi.datalake.sales_incremental import seal
    store, base = foundation
    p = candidate(store, base, monkeypatch)
    path = tmp_path/'candidate.json'
    seal(path, p.as_row())
    loaded = load_candidate(path)
    assert loaded.as_row() == p.as_row()
    assert loaded.components == base.components


def test_extension_fingerprint_cannot_be_forged(foundation, monkeypatch):
    store, base = foundation
    p = candidate(store, base, monkeypatch)
    p.manifest['components']['commercial_purpose']['stable_contract']['source_provenance'] = {'forged': True}
    with pytest.raises(FoundationReaderError, match='fingerprint'):
        validate_manifest(store, p)


def test_wrong_base_snapshot_rejected_before_preparation(foundation, monkeypatch):
    store, base = foundation
    with pytest.raises(FoundationReaderError, match='CURRENT/snapshot'):
        commercial.create_commercial_purpose_candidate(store, base_foundation=base, base_snapshot_id=43,
            component=None, dataset_manifests={}, update_run_id='wrong', source_as_of='now')
    assert store.current_pointer() == base.foundation_publication_id
