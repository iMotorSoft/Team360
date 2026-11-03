"""Offline evidence orchestration; existing Reference/Foundation implementations only.

No catalog connection, capture recovery, master refresh or shared activation.
Run from backend with: uv run --no-sync python -m modules.telchi.investigation.validation.physical_reference_candidate_v2.run
"""
from collections import Counter
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import sys

import duckdb

from modules.telchi.datalake import reference_update as ru, update, foundation_reader as fr
from modules.telchi.datalake import foundation_publication as fp
from modules.telchi.datalake.foundation_manifest import validate_manifest
from modules.telchi.datalake.reference_compatibility import reference_projection
from ..controlled_physical_capture_v1 import capture
from ..operational_universe_v2 import selective

REPO = Path(__file__).resolve().parents[7]
PRIVATE = capture.PRIVATE
SHARED = Path('/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi')
ORIGINAL = PRIVATE / 'physical-capture-physical-capture-to10000-20261029-v1-c04-b04'
SELECTIVE = PRIVATE / 'physical-selective-final167-20261029-v1-b02'
ORIGINAL_SHA = '7b8bbb992fcb83e3d0ec4ae4951084fad90fa12e5c7761ce0f408bf9b7b69099'
SELECTIVE_SHA = 'efac34ab7ae8492dbd748d652ad734ceb8ebe902d1eafbc9f03a851969851245'
UNIVERSE = REPO / 'data/reports/telchi/operational-universe-v2-20261029-final'
EVIDENCE = REPO / 'data/reports/telchi/reference-v2-foundation-offline-final'
ANCESTOR = Path('/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi/TELCHI_RECEIVABLES_COLLECTIONS_FOUNDATION_EXTENSION_V3/fresh_candidate_manifest.json')


def load(path):
    return json.loads(path.read_text())


def check(condition, reason):
    if not condition:
        raise RuntimeError(reason)


def hashes(root):
    return {str(p.relative_to(root)): capture.digest(p) for p in sorted(root.rglob('*')) if p.is_file()}


def stat_inventory(root):
    # Exact metadata inventory including files not consumed by this task. No full facts scan.
    return {str(p.relative_to(root)): [p.stat().st_size, p.stat().st_mtime_ns, p.stat().st_ino]
            for p in sorted(root.rglob('*')) if p.is_file()}


def consolidated():
    check(capture.digest(ORIGINAL/'checkpoint.json') == ORIGINAL_SHA, 'original_checkpoint_sha')
    check(capture.digest(SELECTIVE/'checkpoint.json') == SELECTIVE_SHA, 'selective_checkpoint_sha')
    roots = [ORIGINAL]
    root = SELECTIVE
    inherited = None
    while True:
        check(root not in roots and root.resolve().parent == PRIVATE.resolve(), 'invalid_lineage')
        roots.append(root)
        check(not any((root/name).exists() for name in ('pending.json', 'request.json', 'intent.json')), 'pending_journal')
        plan = load(root/'plan.json')
        cp = selective.read_state(root, plan)
        if inherited is not None:
            count, entries = inherited
            check(cp['batches'] == entries[:count], 'inherited_prefix_changed')
        lineage_path = root/'lineage.json'
        if not lineage_path.exists():
            break
        lineage = load(lineage_path)
        parent = Path(lineage['source'])
        check(capture.digest(parent/'checkpoint.json') == lineage['checkpoint_sha256'], 'lineage_checkpoint_sha')
        inherited = (lineage['inherited_batches'], cp['batches'])
        root = parent
    before = {str(p): hashes(p) for p in roots}
    check(not (ORIGINAL/'pending.json').exists(), 'original_pending')
    cp, _, seen, _ = capture.read_checkpoint(ORIGINAL)
    check(len(seen) == 10000, 'original_count')
    check({p.name for p in ORIGINAL.glob('batch-*.json')} == {b['file'] for b in cp['batches']}, 'original_orphans')
    all_found = {}
    for entry in cp['batches']:
        batch = load(ORIGINAL/entry['file'])
        for row in batch['rows']:
            all_found[row['ItemCode']] = dict(row, observed_at=batch['observed_at'])
    cp = selective.read_state(SELECTIVE, load(SELECTIVE/'plan.json'))
    requested, absent = set(), set()
    for entry in cp['batches']:
        batch = load(SELECTIVE/entry['file'])
        check(not requested.intersection(batch['requested']), 'duplicate_request')
        requested.update(batch['requested'])
        absent.update(batch['not_returned'])
        for row in batch['rows']:
            check(row['ItemCode'] not in all_found, 'duplicate_found_identity')
            all_found[row['ItemCode']] = dict(row, observed_at=batch['observed_at'])
    check({p.name for p in SELECTIVE.glob('selective-*.json')} == {b['file'] for b in cp['batches']}, 'selective_orphans')
    for rel, expected in load(UNIVERSE/'artifact_hashes.json').items():
        check(capture.digest(UNIVERSE/rel) == expected, 'universe_artifact_sha:'+rel)
    products = load(UNIVERSE/'products.json')
    keys = [p['ItemCode'] for p in products]
    check(keys == sorted(set(keys)) and len(keys) == 8001, 'universe_identity_order')
    universe = set(keys)
    check(requested == universe - seen, 'selective_request_partition')
    check(universe == (universe & all_found.keys()) | absent and not absent & all_found.keys(), 'universe_partition')
    operational = [all_found[k] for k in keys if k in all_found]
    distribution = dict(Counter(row['U_FormaFarmac'] for row in operational))
    check(distribution == {'0':6642,'1':695,'2':93,'3':490,'4':37,'5':1}, 'physical_distribution')
    check(len(operational) == 7958 and len(absent) == 43, 'final_counts')
    closure = load(REPO/'data/reports/telchi/selective-final167-20261029-v1/report.json')
    check(sorted(absent) == closure['not_returned_itemcodes'], 'not_returned_report_mismatch')
    frozen = dict(operational=operational, not_returned=sorted(absent),
        captured_outside_universe=[all_found[k] for k in sorted(all_found.keys()-universe)],
        sources={str(ORIGINAL): ORIGINAL_SHA, str(SELECTIVE): SELECTIVE_SHA},
        consistency=capture.CONSISTENCY)
    return frozen, products, roots, before


def publication(manifest, previous=None):
    components = {name: fp.ComponentReference(**{k:v for k,v in entry.items()
                   if k in fp.ComponentReference.__dataclass_fields__})
                  for name,entry in manifest['components'].items() if name in fp.COMPONENT_NAMES}
    return fp.FoundationPublication(foundation_publication_id=manifest['foundation_publication_id'],
        update_run_id='offline-replay-'+manifest['foundation_publication_id'],
        previous_foundation_publication_id=previous,
        reference_version=components['reference'].publication_id, components=components,
        manifest=deepcopy(manifest), validation_status='OFFLINE_REPLAY')


def simulate(root, manifest, ancestor, candidate, snapshot):
    # Disk-backed, private local metadata only. No DuckLake extensions or connector.
    db = duckdb.connect(str(root/'publication-simulation.duckdb'), config={'threads':2, 'memory_limit':'512MB'})
    @contextmanager
    def factory():
        yield db
    store = fp.FoundationPublicationStore(factory, catalog='')
    store.ensure_schema()
    try:
        for m in (ancestor, manifest):
            p = publication(m, store.current_pointer())
            store.create_candidate(p)
            store.logical_commit(p.foundation_publication_id)
        old_id = store.current_pointer()
        old = deepcopy(store.get(old_id).manifest)
        validate_manifest(store, store.current_publication())
        update.DATA_ROOT = root
        fr.DATA_ROOT = root
        ref = {k:candidate[k] for k in ('reference_version','reference_path')}
        def publish(fault=None):
            return update.publish_reference_only(connector=None, foundation_store=store, reference=ref,
                base_data_snapshot_id=snapshot, fault_point=fault)
        outcomes = {}
        for fault in (fp.CommitFaultPoint.DURING_VALIDATION, fp.CommitFaultPoint.AFTER_REFERENCE,
                      fp.CommitFaultPoint.BEFORE_LOGICAL_COMMIT, fp.CommitFaultPoint.DURING_LOGICAL_COMMIT):
            try:
                publish(fault)
                raise AssertionError('fault did not fire')
            except fp.InjectedFailure:
                pass
            check(store.current_pointer() == old_id and store.current_count() == 1, 'partial_publication')
            check(store.get(old_id).manifest == old, 'original_manifest_changed')
            outcomes[fault] = 'PASS_OLD_CURRENT_INTACT'
        check(publish()['status'] == 'COMMITTED', 'publication_failed')
        current = store.current_publication()
        components = validate_manifest(store, current)
        for name, entry in old['components'].items():
            if name != 'reference':
                check(components[name] == entry, 'sealed_component_changed:'+name)
        check(publish()['status'] == 'NOOP', 'publication_not_noop')
        access_reader = fr.FoundationReader(connector=object(), snapshot_resolver=lambda *_: snapshot+999,
            component_verifier=lambda *_: None, metadata_catalog='')
        access = access_reader.resolve_on(db)
        check(access.ducklake_snapshot_id == snapshot, 'data_snapshot_changed')
        check(access.manifest_base_snapshot_id == manifest['base_snapshot_id'], 'derivation_snapshot_changed')
        check(access.reference('products').is_file(), 'reader_reference_missing')
        check(access_reader.resolve_on(db).foundation_publication_id == current.foundation_publication_id, 'reader_incoherent')
        store.logical_rollback(old_id, expected_current_foundation_publication_id=current.foundation_publication_id,
                               reason='isolated offline recovery exercise')
        check(store.current_pointer() == old_id, 'rollback_failed')
        check(access.foundation_publication_id == current.foundation_publication_id and access.ducklake_snapshot_id == snapshot,
              'pinned_reader_changed_after_rollback')
        try:
            publish(fp.CommitFaultPoint.AFTER_LOGICAL_COMMIT)
            raise AssertionError('postcommit fault missing')
        except fp.InjectedFailure:
            pass
        store.fault_point = None
        check(store.current_pointer() != old_id and publish()['status'] == 'NOOP', 'postcommit_recovery_failed')
        outcomes.update(publication='PASS', noop='PASS', rollback='PASS', recovery='PASS',
                        reader_snapshot=snapshot, derivation_snapshot=manifest['base_snapshot_id'],
                        reader_mode='REAL_REFERENCE_AND_MANIFEST; FACT_VERIFIER_INJECTED_OFFLINE')
        ru.write_json(root/'simulated-foundation-manifest.json', store.current_publication().manifest)
        return outcomes, components
    finally:
        db.close()


def main(attempt=''):
    print('START shared metadata inventory', flush=True)
    EVIDENCE.mkdir(parents=True, exist_ok=False)
    before_shared = stat_inventory(SHARED)
    ru.write_json(EVIDENCE/'shared-files-before.json', before_shared)
    print('VERIFY captures and operational evidence', flush=True)
    frozen, products, capture_roots, before_capture = consolidated()
    frozen_hash = ru.digest(frozen)
    destination = PRIVATE / ('physical-reference-offline-' + frozen_hash[:24] + attempt)
    destination.mkdir(mode=0o700, exist_ok=False)
    ru.write_json(destination/'consolidated.json', frozen)
    base_report = load(UNIVERSE/'activity_reaccredited/report.json')
    foundation = base_report['inventory']['foundation']
    manifest = foundation['manifest']
    reference = Path(foundation['reference_path'])
    crosswalk = SHARED/'crosswalk/_versions'/reference.name
    check(capture.digest(reference/'products/part-00000.parquet') == base_report['inventory']['reference']['sha256'], 'accredited_reference_changed')
    root = destination/'candidate'
    print('PREPARE physical-only Reference', flush=True)
    candidate = ru.prepare_physical_reference(previous_reference=reference, previous_crosswalk=crosswalk,
                                               observations=frozen['operational'], candidate_root=root)
    print('VALIDATE real Reference projection', flush=True)
    proof = reference_projection(reference, Path(candidate['reference_path']))
    # Replay base in the local root; never point a local mutable pointer at shared roots.
    shutil.copytree(reference, root/'reference/_versions'/reference.name)
    shutil.copytree(crosswalk, root/'crosswalk/_versions'/reference.name)
    _, _, ref_rows = ru.read_parquet_rows(reference/'products/part-00000.parquet')
    refs = {r['source_native_id'] for r in ref_rows if r['source_system']=='SAP_HANA'}
    keys = {p['ItemCode'] for p in products}
    missing = sorted(keys - refs)
    historical = load(UNIVERSE/'report.json')['identity_missing_reference']
    check(missing == historical, 'historical_missing_reference_changed')
    absent = set(frozen['not_returned'])
    reconciliation = dict(existing_reference=sorted(keys & refs),
        sap_found_absent_reference=candidate['pending_structural_identities'], not_returned=sorted(absent),
        observed_absent_reference=missing, reference_outside_operational=sorted(refs-keys),
        absent_reference_intersection_not_returned=sorted(set(missing)&absent),
        absent_reference_only=sorted(set(missing)-absent), not_returned_only=sorted(absent-set(missing)),
        pending=[dict(ItemCode=k, reason='NOT_RETURNED_NO_ACCREDITED_MASTER_IDENTITY_NO_CANONICAL_MAPPING') for k in missing])
    ancestor = load(ANCESTOR)
    check(ancestor['foundation_publication_id'] == manifest['purchasing_base_publication_id'], 'ancestor_identity')
    print('VERIFY sealed component files', flush=True)
    dataset_checks = {}
    for name, entry in manifest['components'].items():
        for dataset, meta in entry.get('datasets', {}).items():
            for path, expected in zip(meta.get('file_references', []), meta.get('file_hashes', []), strict=True):
                check(capture.digest(Path(path)) == expected, 'sealed_dataset_hash_changed:'+dataset)
                dataset_checks[path] = expected
    print('SIMULATE Foundation recovery/publication', flush=True)
    outcomes, components = simulate(root, manifest, ancestor, candidate, foundation['snapshot'])
    print('VERIFY real candidate NOOP', flush=True)
    noop = ru.prepare_physical_reference(previous_reference=Path(candidate['reference_path']),
        previous_crosswalk=Path(candidate['crosswalk_path']), observations=frozen['operational'],
        candidate_root=destination/'noop-replay')
    check(noop['status']=='NOOP' and noop['reference_version']==candidate['reference_version'], 'candidate_noop_failed')
    print('VERIFY shared/capture preservation', flush=True)
    check(all(hashes(p)==before_capture[str(p)] for p in capture_roots), 'capture_changed')
    after_shared = stat_inventory(SHARED)
    check(before_shared == after_shared, 'shared_files_changed')
    ru.write_json(EVIDENCE/'shared-files-after.json', after_shared)
    ru.write_json(destination/'candidate-seal.json', hashes(root/'reference/_versions'/candidate['reference_version']))
    report = dict(verdict='PARTIAL', reason='Offline candidate complete; final regression/LAT gates pending.',
        branch='feature/console-backend-core', entity='TELCHI', stage='DEVELOPMENT',
        candidate=candidate, consolidated=dict(path=str(destination/'consolidated.json'), content_sha256=frozen_hash,
            file_sha256=capture.digest(destination/'consolidated.json'), operational_universe=8001, found=7958,
            not_returned=43, pending_capture=0, captured_outside_universe=len(frozen['captured_outside_universe'])),
        distribution=dict(Counter(row['U_FormaFarmac'] for row in frozen['operational'])), explicit_physical=1278,
        reconciliation_counts={key:len(value) for key,value in reconciliation.items()},
        foundation=dict(id=foundation['id'], data_snapshot=foundation['snapshot'], base_snapshot=manifest['base_snapshot_id'],
            compatibility='PASS_ON_REAL_CANDIDATE_AND_FROZEN_MANIFEST', components={name:dict(status='PRESERVED_EXACT' if name!='reference' else 'COMPATIBLE_PHYSICAL_ONLY', publication_id=entry['publication_id']) for name,entry in components.items()},
            simulation=outcomes, live_catalog_accessed=False, sealed_dataset_files_verified=len(dataset_checks)),
        safety=dict(shared_file_inventory_unchanged=True, shared_files=len(before_shared), capture_roots_unchanged=len(capture_roots),
            hana_connections=0, network_connections=0, shared_writes=0, original_reference_hash=capture.digest(reference/'products/part-00000.parquet'),
            reference_pointer_diverges_from_foundation=True, publication_real=False, commits=0),
        limitations=['Frozen Foundation identity/manifest from accredited operational-universe report; live CURRENT not queried.',
            'No offline DuckLake catalog export: physical fact and Receivables fingerprints are not recomputed; exact dependencies and snapshot IDs preserved.',
            '43 missing Reference identities equal NOT_RETURNED only after independent key comparison; no deletion/creation inferred.',
            'Historical reference_current pointer differs from Foundation; future controlled publication must reconcile under exclusive lock.'])
    for name, value in [('report',report), ('identity-reconciliation',reconciliation), ('reference-compatibility',proof),
                        ('sealed-dataset-hashes',dataset_checks), ('capture-inventories',before_capture),
                        ('base-foundation-manifest',manifest), ('base-ancestor-manifest',ancestor)]:
        ru.write_json(EVIDENCE/(name+'.json'), value)
    print(json.dumps(report, ensure_ascii=False, indent=2))


def install_offline_guard():
    protected = [SHARED.resolve(), ORIGINAL.resolve(), SELECTIVE.resolve()]
    def guard(event, args):
        if event in ('socket.connect', 'socket.getaddrinfo'):
            raise RuntimeError('OFFLINE_NETWORK_FORBIDDEN')
        paths = []
        if event == 'open':
            path, mode, flags = args
            if (isinstance(mode, str) and any(c in mode for c in 'wax+')) or (isinstance(flags,int) and flags & 3):
                paths = [path]
        elif event in ('os.remove','os.rmdir','os.mkdir','os.chmod','os.truncate'):
            paths = [args[0]]
        elif event in ('os.rename','os.link','os.symlink'):
            paths = list(args[:2])
        for path in paths:
            if isinstance(path, (str, bytes)):
                resolved = Path(path).resolve()
                if any(resolved.is_relative_to(p) for p in protected):
                    raise RuntimeError('SHARED_OR_CAPTURE_WRITE_FORBIDDEN:'+str(resolved))
    sys.addaudithook(guard)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attempt', default='', help='New evidence/private suffix after an interrupted attempt')
    args = parser.parse_args()
    check(not args.attempt or (args.attempt.startswith('-') and args.attempt[1:].isalnum()), 'invalid_attempt')
    EVIDENCE = EVIDENCE.with_name(EVIDENCE.name + args.attempt)
    install_offline_guard()
    main(args.attempt)
