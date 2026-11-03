"""Supplement real-candidate simulations without repeating capture consolidation."""
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
import shutil

import duckdb

from modules.telchi.datalake import foundation_publication as fp, foundation_reader as fr, update
from modules.telchi.datalake.reference_compatibility import reference_projection
from modules.telchi.datalake.foundation_manifest import validate_manifest
from .run import EVIDENCE, SHARED, load, check, hashes, stat_inventory, install_offline_guard, ru


def main(evidence):
    report = load(evidence/'report.json')
    candidate = report['candidate']
    root = Path(candidate['reference_path']).parents[2]
    before = hashes(Path(candidate['reference_path']))
    update.DATA_ROOT = fr.DATA_ROOT = root
    database = root/'concurrent-reader-simulation.duckdb'
    check(not database.exists(), 'simulation_already_exists')
    shutil.copyfile(root/'publication-simulation.duckdb', database)
    db = duckdb.connect(str(database), config={'threads':2, 'memory_limit':'512MB'})
    @contextmanager
    def factory():
        yield db
    store = fp.FoundationPublicationStore(factory, catalog='')
    result = {}
    try:
        old = store.current_publication()
        reader = fr.FoundationReader(connector=object(), snapshot_resolver=lambda *_: 9999,
            component_verifier=lambda *_: None, metadata_catalog='')
        pinned = reader.resolve_on(db)
        # Two prepared complete publications race against the same real baseline.
        prepared = []
        for label in ('stale', 'winner'):
            c = fp.prepare_candidate(store, update_run_id='real-candidate-cas-'+label,
                                     reference_version=old.reference_version)
            manifest = deepcopy(old.manifest)
            manifest['foundation_publication_id'] = c.foundation_publication_id
            store.update_components(c.foundation_publication_id, old.components, manifest=manifest)
            validate_manifest(store, store.get(c.foundation_publication_id))
            prepared.append(c.foundation_publication_id)
        check(reader.resolve_on(db).foundation_publication_id==old.foundation_publication_id, 'prepared_visible')
        store.logical_commit(prepared[1])
        try:
            store.logical_commit(prepared[0])
            raise AssertionError('stale CURRENT accepted')
        except fp.PublicationBoundaryError as exc:
            check('compare-and-swap' in str(exc), 'unexpected_cas_error')
        check(pinned.foundation_publication_id==old.foundation_publication_id and pinned.ducklake_snapshot_id==1408,
              'pinned_reader_mixed_snapshots')
        check(reader.resolve_on(db).foundation_publication_id==prepared[1], 'new_reader_not_coherent')
        check(store.current_count()==1, 'partial_current')
        check(store.get(old.foundation_publication_id).manifest==old.manifest, 'old_snapshot_manifest_changed')
        result.update(compare_and_swap='PASS', preparing_not_visible='PASS',
                      concurrent_pinned_readers='PASS', exact_snapshot_preservation='PASS')
        # Preserve the real candidate. Deliberately incomplete NEW fixture rejected.
        incomplete = root/'reference/_versions/incomplete-rejection-fixture'
        incomplete.mkdir()
        (root/'crosswalk/_versions/incomplete-rejection-fixture').mkdir()
        try:
            update.publish_reference_only(connector=None, foundation_store=store,
                reference={'reference_version':incomplete.name, 'reference_path':str(incomplete)},
                base_data_snapshot_id=1408)
            raise AssertionError('incomplete Reference accepted')
        except fp.FoundationReaderError:
            pass
        check(store.current_pointer()==prepared[1], 'incompatible_candidate_changed_current')
        result['real_reference_dataset_registry_rejection']='PASS'
        # Unknown additions cannot disappear through Reference-only publication.
        current = store.current_publication()
        original = deepcopy(current.manifest)
        damaged = deepcopy(original)
        damaged['components']['unknown_component']={'name':'unknown_component', 'publication_id':'unknown_v1'}
        store.update_components(current.foundation_publication_id, current.components, manifest=damaged)
        try:
            update.publish_reference_only(connector=None, foundation_store=store,
                reference={'reference_version':incomplete.name, 'reference_path':str(incomplete)},
                base_data_snapshot_id=1408)
            raise AssertionError('unknown component silently dropped')
        except fp.FoundationReaderError:
            pass
        check('unknown_component' in store.current_publication().manifest['components'], 'unknown_component_dropped')
        store.update_components(current.foundation_publication_id, current.components, manifest=original)
        result['unknown_component_not_discarded']='PASS_REJECTED_EXPLICITLY'
        base_version = load(evidence/'base-foundation-manifest.json')['components']['reference']['publication_id']
        base = root/'reference/_versions'/base_version
        reference_projection(base, Path(candidate['reference_path']))
        # Replay final producer code against the sealed candidate; no activation.
        observations = load(Path(report['consolidated']['path']))['operational']
        replay = ru.prepare_physical_reference(previous_reference=Path(candidate['reference_path']),
            previous_crosswalk=Path(candidate['crosswalk_path']), observations=observations,
            candidate_root=root.parent/'final-code-noop-replay')
        check(replay['status']=='NOOP' and replay['reference_version']==candidate['reference_version'], 'final_code_not_noop')
        check(hashes(Path(candidate['reference_path']))==before, 'real_candidate_changed')
        result['final_code_candidate_noop']='PASS'
        result['real_candidate_seal_unchanged']=True
        ru.write_json(evidence/'real-candidate-additional-validation.json', result)
        print(result)
    finally:
        db.close()


def verify_preservation(evidence):
    report = load(evidence/'report.json')
    check(stat_inventory(SHARED) == load(evidence/'shared-files-before.json'), 'shared_snapshot_inventory_changed')
    for root, expected in load(evidence/'capture-inventories.json').items():
        check(hashes(Path(root)) == expected, 'original_capture_changed')
    candidate = report['candidate']
    reference, crosswalk = Path(candidate['reference_path']), Path(candidate['crosswalk_path'])
    seal = load(reference.parents[3]/'candidate-seal.json')
    check(hashes(reference) == seal, 'candidate_physical_seal_changed')
    check(ru.digest(ru.version_content(reference, crosswalk)) == candidate['content_fingerprint'], 'candidate_content_hash_changed')
    result = dict(status='PASS', shared_files=report['safety']['shared_files'],
        shared_stat_inventory_unchanged=True, capture_sha256_inventories_unchanged=True,
        candidate_physical_seal_unchanged=True, candidate_logical_hash=candidate['content_fingerprint'],
        catalog_connections=0, shared_writes=0)
    ru.write_json(evidence/'final-preservation.json', result)
    print(result)


if __name__=='__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--preservation-only', action='store_true')
    args = parser.parse_args()
    install_offline_guard()
    evidence = EVIDENCE.with_name(EVIDENCE.name+'-r2')
    if args.preservation_only:
        verify_preservation(evidence)
    else:
        main(evidence)
