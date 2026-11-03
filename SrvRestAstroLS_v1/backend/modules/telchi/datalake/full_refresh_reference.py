"""Offline master append from verified full-refresh captures; no source queries.

Uses the existing identity producer and Reference successor envelope. This is
not a multidomain facts adapter or a publisher. Existing attributes and every
independent dataset remain exact; new secondary relationships may be unknown.
"""
from copy import deepcopy
from pathlib import Path

from . import sales_incremental as inc
from . import sales_reference_release as release
from . import reference_update as ref
from .full_refresh_capture import CONTRACT, verify_capture
from .foundation_publication import ComponentReference, FoundationPublication

ADAPTER = 'CAPTURED_MASTER_APPEND_V1'
ENTITIES = ('customer', 'product', 'supplier')


def missing_observations(previous_reference, capture_root):
    previous_reference, capture_root = map(Path, (previous_reference, capture_root))
    if capture_root.resolve().parent != (inc.DATA_ROOT/'raw/sap'/CONTRACT).resolve():
        raise ValueError('MASTER_CAPTURE_OUTSIDE_CONTRACT')
    observations, receipts = {}, []
    for entity in ENTITIES:
        cfg = ref.ENTITY_CONFIG[entity]
        table, key = cfg['table'], cfg['key']
        directory = capture_root/'reference'/table.lower()
        result = verify_capture(directory)
        intent = inc.read_json(directory/'intent.json')
        sql = getattr(ref, table+'_SQL').strip() + ' ORDER BY "'+key+'"'
        if (intent['plan']['sql'] != sql or result['keys'] != [key]
                or result['semantic_scope']['kind'] != 'CURRENT_MASTER_SNAPSHOT'
                or result['status'] != 'CAPTURE_RECONCILED_NOT_PUBLISHED'):
            raise ValueError('MASTER_CAPTURE_SEMANTICS_INCOMPATIBLE')
        rows = []
        for page in result['pages']:
            path = Path(page['path'])
            if path.is_symlink() or directory.resolve() not in path.resolve().parents:
                raise ValueError('MASTER_CAPTURE_PATH_INVALID')
            rows.extend(ref.read_parquet_rows(path)[2])
        keys = [r[key] for r in rows]
        if (len(rows) != result['row_count'] or len(set(keys)) != len(keys)
                or any(not isinstance(k, str) or not k.strip() for k in keys)):
            raise ValueError('MASTER_CAPTURE_IDENTITIES_INVALID')
        old = ref.read_parquet_rows(ref._find(previous_reference, cfg['ref']))[2]
        existing = {r['source_native_id'] for r in old if r['source_system'] == 'SAP_HANA'}
        observed_at = result['source_before']['utc'] + '+00:00'
        observations[entity] = [{**r, '_source_extracted_at': observed_at} for r in rows
            if r[key] not in existing and (entity not in {'customer', 'supplier'}
                or r['CardType'] == ('C' if entity == 'customer' else 'S'))]
        receipts.append(dict(entity=entity, observed_at=observed_at,
            receipt_sha256=inc.file_hash(directory/'complete.json'),
            intent_sha256=inc.file_hash(directory/'intent.json'),
            pending=[], capture_rows=len(rows), new_keys=sorted(r[key] for r in observations[entity])))
    return observations, receipts


def make_candidate(base, reference_path, capture_root):
    """Build an isolated row; canonical Promotion still validates and commits it."""
    from .reference_compatibility import KIND
    from .sales_reference_release import append_proof
    previous = inc.DATA_ROOT/'reference/_versions'/base.reference_version
    reference_path = Path(reference_path)
    if reference_path.resolve().parent != (inc.DATA_ROOT/'reference/_versions').resolve():
        raise ValueError('REFERENCE_IMMUTABLE_ROOT_REQUIRED')
    proof = append_proof(previous, reference_path, capture_root)
    manifest = deepcopy(base.manifest)
    catalog = deepcopy(base.components)
    component = ComponentReference('reference', reference_path.name,
        source_as_of=proof['source_as_of'], content_identity=str(reference_path))
    catalog['reference'] = component
    manifest['components']['reference'] = component.as_dict()
    identity = 'foundation_'+inc.digest(dict(base=base.foundation_publication_id,
        components=manifest['components'], proof=proof, adapter=ADAPTER))[:32]
    snapshot = base.manifest.get('facts_base_snapshot_id', base.manifest.get('reference_data_snapshot_id'))
    if type(snapshot) is not int:
        raise ValueError('EXPLICIT_INDEPENDENT_DATA_SNAPSHOT_REQUIRED')
    manifest.update(foundation_publication_id=identity, update_run_id=Path(capture_root).name,
        candidate_kind=KIND, manifest_schema_version='1.0.0',
        base_foundation_publication_id=base.foundation_publication_id,
        reference_version=reference_path.name, reference_compatibility=proof,
        reference_compatibility_adapter=ADAPTER, reference_data_snapshot_id=snapshot)
    return FoundationPublication(identity, Path(capture_root).name,
        previous_foundation_publication_id=base.foundation_publication_id,
        reference_version=reference_path.name, components=catalog, manifest=manifest,
        source_as_of=proof['source_as_of'], validation_status='PASS')
