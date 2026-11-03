"""A derivation base snapshot must not replace the prior visible data snapshot."""
import pytest

from modules.telchi.datalake import foundation_reader as reader, update
from modules.telchi.datalake.foundation_manifest import validate_manifest
from .test_physical_reference_offline import eight, no_sap  # noqa: F401


def test_reader_preserves_distinct_commit_and_derivation_snapshots(eight):
    store, _, new, old_id = eight
    result = update.publish_reference_only(connector=None, foundation_store=store,
        reference={'reference_version': 'ref-v2', 'reference_path': str(new)}, base_data_snapshot_id=1408)
    assert result['status'] == 'COMMITTED'
    publication = store.current_publication()
    assert publication.manifest['base_snapshot_id'] == 84
    assert publication.manifest['reference_data_snapshot_id'] == 1408
    seen = []
    access_reader = reader.FoundationReader(snapshot_resolver=lambda *_: 9999,
        component_verifier=lambda _, __, snapshot: seen.append(snapshot), metadata_catalog='')
    with store.connection_factory() as db:
        access = access_reader.resolve_on(db)
    assert access.ducklake_snapshot_id == 1408 and seen == [1408]
    assert access.manifest_base_snapshot_id == 84
    assert 'VERSION => 1408' in access.sales('sales_line')
    assert store.get(old_id).manifest['base_snapshot_id'] == 84


@pytest.mark.parametrize('snapshot', [None, True, -1, 83])
def test_missing_or_invalid_snapshot_rejected(eight, snapshot):
    store, _, new, old_id = eight
    with pytest.raises(update.UpdateAbort, match='accredited data snapshot'):
        update.publish_reference_only(connector=None, foundation_store=store,
            reference={'reference_version': 'ref-v2', 'reference_path': str(new)},
            base_data_snapshot_id=snapshot)
    assert store.current_pointer() == old_id


def test_snapshot_field_cannot_be_omitted_from_refresh(eight):
    store, _, new, _ = eight
    update.publish_reference_only(connector=None, foundation_store=store,
        reference={'reference_version': 'ref-v2', 'reference_path': str(new)}, base_data_snapshot_id=1408)
    publication = store.current_publication()
    publication.manifest.pop('reference_data_snapshot_id')
    with pytest.raises(reader.FoundationReaderError, match='snapshot'):
        validate_manifest(store, publication)
