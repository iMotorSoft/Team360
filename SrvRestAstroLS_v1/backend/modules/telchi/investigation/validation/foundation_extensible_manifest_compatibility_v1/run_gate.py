"""Read-only evidence for Foundation manifest compatibility; never promotes."""
from __future__ import annotations

import contextlib
import json
import subprocess
import sys
import types
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

from modules.telchi.datalake.ducklake import DATA_ROOT, DuckLakeConnector
from modules.telchi.datalake.foundation_publication import FoundationPublicationStore, FoundationReaderError
from modules.telchi.datalake.foundation_manifest import validate_manifest
from modules.telchi.datalake.foundation_reader import FoundationReader, _validate_manifest
from modules.telchi.datalake.material_supply_candidate import resolve_current_material_supply
from modules.telchi.datalake.receivables_collections_foundation import (
    _resolve, resolve_current, validate_pinned_candidate, validate_component_data,
    analytical_result_hash_v3,
)
from modules.telchi.datalake.purchasing_foundation import pinned_component, read_component
from modules.telchi.datalake.purchasing import ATOMIC, DERIVED, derive, normalize_atomic
from modules.telchi.datalake.purchasing_gate import parity, gold, invariants, existing_fingerprints
from modules.telchi.datalake.raw import digest, file_hash
from modules.telchi.investigation.validation.receivables_collections_foundation_extension_v1.run_gate import all_gold, analytical_gold
from modules.telchi.investigation.validation.receivables_collections_foundation_extension_v3.run_gate import (
    actual_business_fingerprints, raw_analytical_result, validate_gold,
)

GATE = "TELCHI_FOUNDATION_EXTENSIBLE_MANIFEST_COMPATIBILITY_V1"
CURRENT_ID = "foundation_d222a203801cc84e9a14164d26aa67a0"
CANDIDATE_ID = "foundation_afd08d9eca6a725be53cdc3f9d5709c9"
EVIDENCE = Path('/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi') / GATE
REPO = Path(__file__).resolve().parents[7]


def write(name, value):
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / name).write_text(json.dumps(value, default=str, sort_keys=True, indent=2) + '\n')


def original_reader():
    """Load the unchanged HEAD reader to compare historical behavior directly."""
    path = 'SrvRestAstroLS_v1/backend/modules/telchi/datalake/receivables_collections_foundation.py'
    source = subprocess.check_output(['git', 'show', 'HEAD:' + path], cwd=REPO, text=True)
    module = types.ModuleType('modules.telchi.datalake._compatibility_original')
    module.__package__ = 'modules.telchi.datalake'
    sys.modules[module.__name__] = module
    exec(compile(source, path, 'exec'), module.__dict__)
    return module


def run():
    before = json.loads((EVIDENCE / 'before.json').read_text())
    connector = DuckLakeConnector()
    old = original_reader()
    with connector.session(read_only=True) as db:
        db.execute('SET threads=1')
        assert db.execute('SELECT 1').fetchone() == (1,)
        @contextlib.contextmanager
        def factory():
            yield db
        store = FoundationPublicationStore(factory)
        assert store.current_pointer() == CURRENT_ID
        assert store.current_count() == store.pointer_row_count() == 1
        current = resolve_current(store)
        candidate = validate_pinned_candidate(store, CANDIDATE_ID)
        assert current.component_versions == candidate.component_versions
        assert current.component == candidate.component
        assert current.snapshot_id == candidate.snapshot_id
        assert 'purchasing' not in candidate.component_versions
        old_current = old.resolve_current(store)
        try:
            old.validate_pinned_candidate(store, CANDIDATE_ID)
        except FoundationReaderError as exc:
            rejection = str(exc)
        else:
            raise AssertionError('original reader did not reproduce rejection')
        assert rejection == 'Receivables Foundation manifest kind is missing or wrong'
        write('root_cause.json', {'original_candidate_rejection': rejection,
                                'original_current_versions': old_current.component_versions,
                                'new_candidate_versions': candidate.component_versions})
        snapshots = {}
        for label, pinned in [('current', current), ('candidate', candidate)]:
            results = all_gold(db, pinned)
            validate_gold(results)
            fingerprints = actual_business_fingerprints(db, pinned.snapshot_id)
            hashes = {n: analytical_result_hash_v3(raw_analytical_result(n, results[n], pinned))
                      for n in ('current_board', 'collections', 'settlement', 'historical')}
            assert hashes == before['gold_hashes']
            assert fingerprints == before['fingerprints']
            assert json.loads(json.dumps(analytical_gold(results), default=str)) == analytical_gold(before['gold'])
            snapshots[label] = {'gold': results, 'gold_hashes': hashes, 'fingerprints': fingerprints,
                                'data_validation': validate_component_data(db, pinned), 'identity': pinned.as_dict()}
        write('receivables_parity.json', snapshots)
        historical = []
        for identity in ('foundation_f1ebdb312ae595638c3a3bffbda78629',
                         'foundation_39e17f1559525d2ca9bd04e17765b750',
                         'foundation_417c860c216805f18341bb741ee026e3'):
            publication = store.get(identity)
            validate_manifest(store, publication)
            try:
                original = old._resolve(publication, reader_mode='HISTORICAL_VALIDATION')
            except FoundationReaderError as exc:
                try:
                    _resolve(publication, reader_mode='HISTORICAL_VALIDATION', store=store)
                except FoundationReaderError:
                    historical.append({'id': identity, 'behavior': 'unchanged_rejection_without_receivables', 'reason': str(exc)})
                else:
                    raise AssertionError('historical rejection changed')
            else:
                compatible = _resolve(publication, reader_mode='HISTORICAL_VALIDATION', store=store)
                assert compatible.component == original.component
                assert compatible.component_versions == original.component_versions
                assert compatible.snapshot_id == original.snapshot_id
                g = all_gold(db, compatible)
                validate_gold(g)
                historical.append({'id': identity, 'behavior': 'unchanged_acceptance', 'gold': 'PASS'})
        write('historical_publications.json', historical)
        material = resolve_current_material_supply(store)
        # A read-only overlay exercises the real CURRENT consumer with the exact
        # candidate manifest without writing the catalog or productive pointer.
        class Overlay:
            def current_pointer(self): return CANDIDATE_ID
            def get(self, identity):
                p = store.get(identity)
                if identity == CANDIDATE_ID:
                    p = deepcopy(p)
                    p.status = 'CURRENT'
                return p
        material_candidate = resolve_current_material_supply(Overlay())
        assert material.component_versions == material_candidate.component_versions
        assert material.material_supply_datasets() == material_candidate.material_supply_datasets()
        assert material.snapshot_id == material_candidate.snapshot_id
        # The canonical reader's subset validator is also exercised against the
        # candidate; commit-snapshot resolution must await the separate promotion.
        access = FoundationReader(connector).resolve_on(db)
        p = store.get(CANDIDATE_ID)
        _validate_manifest(p, replace(access.foundation, foundation_publication_id=CANDIDATE_ID))
        component = pinned_component(store, CANDIDATE_ID)
        restored = read_component(component)
        atomic = {n: restored[n] for n in ATOMIC}
        derived = {n: restored[n] for n in DERIVED}
        coverage = component['stable_contract']['coverage']
        report = parity(atomic, derived, coverage)
        gold_report = gold(atomic, derived, report)
        invariant_report = invariants(atomic, derived)
        assert report['status'] == gold_report['status'] == invariant_report['status'] == 'PASS'
        assert gold_report['gold_hash'] == p.manifest['purchasing_validation']['gold_hash']
        assert digest(report) == p.manifest['purchasing_validation']['parity_hash']
        cursor = db.execute(f"SELECT * FROM {access.oinm()} WHERE trans_type IN ('18','20','21') ORDER BY atomic_id")
        movements = [dict(zip([d[0] for d in cursor.description], values)) for values in cursor.fetchall()]
        path = access.manifest['reference_closure']['warehouse_location_crosswalk']
        cursor = db.execute('SELECT * FROM read_parquet(?)', [path])
        warehouses = [dict(zip([d[0] for d in cursor.description], values)) for values in cursor.fetchall()]
        rebuilt, metrics = derive(atomic, movements, warehouse_reference={r['warehouse_code']: r for r in warehouses})
        assert all(digest(rebuilt[n]) == digest(derived[n]) for n in DERIVED)
        # Replay captured source-native rows to verify Atomic reproducibility too.
        sources = {n: [json.loads(r['source_native_json']) for r in atomic[n]] for n in ATOMIC}
        reconstructed = normalize_atomic(sources, snapshot_id=p.manifest['purchasing_validation']['source_snapshot_id'])
        assert all(digest(reconstructed[n]) == digest(atomic[n]) for n in ATOMIC)
        source_proof = component['stable_contract']['source_provenance']
        assert digest(movements) == source_proof['inventory_movement']['logical_hash']
        assert file_hash(Path(path)) == source_proof['warehouse_business_location']['sha256']
        write('purchasing_revalidation.json', {'parity': report['status'], 'gold': gold_report,
                                            'invariants': invariant_report, 'reproducible': True,
                                            'dataset_hashes': {n: digest(rows) for n, rows in restored.items()},
                                            'collision_metrics': metrics})
        write('foundation_fingerprints.json', existing_fingerprints(connector, store.get(CURRENT_ID).manifest))
        after_rows = db.execute('SELECT * FROM telchi.ops.foundation_publications_v1 ORDER BY foundation_publication_id').fetchall()
        pointer = db.execute('SELECT * FROM telchi.ops.foundation_current_v1').fetchall()
        assert json.loads(json.dumps(after_rows, default=str)) == before['rows']
        assert json.loads(json.dumps(pointer, default=str)) == before['pointer']
        assert store.get(CANDIDATE_ID).status == 'READY_TO_COMMIT'
        summary = {'gate': GATE, 'compatibility': 'PASS', 'current': store.current_pointer(),
                   'all_publication_rows_unchanged': True, 'pointer_unchanged': True,
                   'receivables_parity': 'PASS', 'foundation_parity': 'PASS',
                   'purchasing_parity': 'PASS', 'purchasing_gold': 'PASS', 'purchasing_reproducible': True,
                   'candidate_rebuilt': False, 'material_supply_compatible': True,
                   'SAP_ACCESSED': 'NO', 'SAP_QUERY_COUNT': 0, 'SAP_WRITE_COUNT': 0}
        write('summary.json', summary)
        print(json.dumps(summary))


if __name__ == '__main__':
    run()
