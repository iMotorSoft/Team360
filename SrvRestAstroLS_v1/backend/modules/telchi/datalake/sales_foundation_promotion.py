"""Durable orchestration of the existing Reference and Foundation publishers.

No SAP dependency. Preparation never writes live metadata. Activation requires
binding the operation to the exact prepared plan (candidate bytes, manifest,
base, Reference and retained cutoffs), not a successful test. Any identity or
reference the operator adds is journaled as optional trace; it is never a
condition to publish. Foundation's logical commit is the visibility point:
readers use its pinned Reference even if a crash interrupts the independent
master-pointer activation.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
from pathlib import Path

from . import sales_incremental as inc
from .foundation_publication import (
    ComponentReference, FoundationPublicationStore, READY_TO_COMMIT, _COLUMN_NAMES, _row_to_publication,
)
from .reference_update import active_pointer, reference_publication_lock

CONTRACT = 'sales-foundation-promotion-v1'


def load_candidate(path):
    row = inc.read_json(path)
    candidate = _row_to_publication(tuple(row[k] for k in _COLUMN_NAMES))
    if not candidate.manifest:
        raise ValueError('CANDIDATE_ROW_INTEGRITY')
    from .sales_facts_transition import KIND
    from .reference_compatibility import KIND as REFERENCE_KIND
    kind = candidate.manifest.get('candidate_kind')
    from .independent_facts_succession import KIND as INDEPENDENT_KIND
    from .foundation_manifest import EXTENSIBLE_KIND
    if kind not in {KIND, REFERENCE_KIND, INDEPENDENT_KIND, EXTENSIBLE_KIND}:
        raise ValueError('SALES_TRANSITION_CANDIDATE_REQUIRED')
    if kind == EXTENSIBLE_KIND:
        rich_components = set()  # additive extension retains exact catalog rows
    elif kind == REFERENCE_KIND:
        rich_components = {'reference'}
    elif kind == INDEPENDENT_KIND:
        from .operational_domains import CONTRACT as OBSERVATIONS
        # Observation-only successors retain the exact catalog representation
        # of ALL components; promoting rich stock metadata here changes its
        # serialized component_hash even though stock was not replaced.
        proof = candidate.manifest.get('independent_facts_succession', {})
        from .receivables_collections_succession import CONTRACT as CXC_HISTORY
        # CxC also retains the exact catalog representation of stock/sales.
        # Only a stock replacement may enrich the stock catalog component.
        rich_components = set() if proof.get('contract') in {OBSERVATIONS, CXC_HISTORY} else {'oitw'}
    else:
        rich_components = {'sales', 'credit_memo'}
        if candidate.manifest['sales_facts_revalidation'].get('reference_append'):
            rich_components.add('reference')
    for name, ref in list(candidate.components.items()):
        entry = candidate.manifest['components'][name]
        if entry.get('publication_id') != ref.publication_id or entry.get('source_as_of') != ref.source_as_of:
            raise ValueError('CANDIDATE_COLUMN_MANIFEST_CONFLICT')
        # make_candidate retains catalog-deserialized ancestors, while replacing
        # only the changed components with rich metadata. Reproduce that exact
        # row contract; unchanged manifest metadata must not be invented in the
        # lossy legacy catalog columns when checking the stored component hash.
        if name in rich_components:
            candidate.components[name] = ComponentReference(**{k:entry.get(k) for k in ref.as_dict()})
    if candidate.as_row()['component_hash'] != row['component_hash']:
        raise ValueError('CANDIDATE_ROW_INTEGRITY')
    return candidate


def tree_hashes(root):
    root = Path(root)
    paths = sorted(root.rglob('*.parquet'))
    if not paths or root.is_symlink():
        raise ValueError('INCOMPLETE_REFERENCE_VERSION')
    if any(p.is_symlink() for p in paths):
        raise ValueError('SYMLINK_REFERENCE_VERSION')
    return {str(p.relative_to(root)): inc.file_hash(p) for p in paths}


class Promotion:
    def __init__(self, store, data_root, journal, *, validate, verify_reader, resource_check, accredit):
        self.store, self.data_root, self.journal = store, Path(data_root), Path(journal)
        self.validate, self.verify_reader, self.resource_check = validate, verify_reader, resource_check
        self.accredit = accredit

    def event(self, name, value):
        path = self.journal / (name + '.json')
        if path.exists():
            if inc.read_json(path) != value:
                raise RuntimeError('JOURNAL_EVENT_CONFLICT: ' + name)
        else:
            inc.seal(path, value)

    def prepare(self, candidate_path):
        self.resource_check()
        candidate = load_candidate(candidate_path)
        base = self.store.current_publication()
        if base is None or base.foundation_publication_id != candidate.previous_foundation_publication_id:
            raise RuntimeError('CURRENT_CHANGED_RECONCILIATION_REQUIRED')
        self.validate(candidate)
        pointer, _, _ = active_pointer(self.data_root)
        target = dict(current_reference_version=candidate.reference_version,
            reference_path=str(self.data_root/'reference/_versions'/candidate.reference_version),
            crosswalk_path=str(self.data_root/'crosswalk/_versions'/candidate.reference_version),
            previous_version=pointer.get('current_reference_version'), rollback=pointer,
            build_id=candidate.reference_version, source_as_of=candidate.source_as_of, gate=CONTRACT)
        plan = dict(contract=CONTRACT, candidate_path=str(Path(candidate_path).resolve()),
            candidate_sha256=inc.file_hash(candidate_path), candidate=candidate.foundation_publication_id,
            base=base.foundation_publication_id, manifest_sha256=inc.digest(candidate.manifest),
            base_manifest_sha256=inc.digest(base.manifest), reference_before=pointer, reference_after=target,
            reference_files=tree_hashes(target['reference_path']),
            crosswalk_files=tree_hashes(target['crosswalk_path']),
            retained_component_cutoffs={k:v.get('source_as_of') for k,v in candidate.manifest['components'].items()})
        self.journal.mkdir(parents=True, exist_ok=True, mode=0o700)
        with inc.locked(self.journal):
            self.event('plan', plan)
            rollback_roots = [pointer['reference_path'], pointer['crosswalk_path'],
                str(self.data_root/'reference/_versions'/base.reference_version),
                str(self.data_root/'crosswalk/_versions'/base.reference_version)]
            self.event('rollback-inputs', dict(plan_sha256=inc.digest(plan),
                roots={root:tree_hashes(root) for root in rollback_roots}))
        return plan

    def check_rollback_inputs(self, plan):
        inputs=inc.read_json(self.journal/'rollback-inputs.json')
        if inputs['plan_sha256']!=inc.digest(plan):
            raise RuntimeError('ROLLBACK_INPUT_PLAN_CONFLICT')
        for root,expected in inputs['roots'].items():
            if tree_hashes(root)!=expected:
                raise RuntimeError('ROLLBACK_INPUT_BYTES_CHANGED')

    def check(self, plan):
        self.check_rollback_inputs(plan)
        if inc.file_hash(Path(plan['candidate_path'])) != plan['candidate_sha256']:
            raise RuntimeError('CANDIDATE_BYTES_CHANGED')
        candidate = load_candidate(Path(plan['candidate_path']))
        if candidate.foundation_publication_id != plan['candidate'] or inc.digest(candidate.manifest) != plan['manifest_sha256']:
            raise RuntimeError('CANDIDATE_IDENTITY_CHANGED')
        for family, key in (('reference', 'reference_path'), ('crosswalk', 'crosswalk_path')):
            if tree_hashes(plan['reference_after'][key]) != plan[family+'_files']:
                raise RuntimeError('REFERENCE_BYTES_CHANGED')
        base = self.store.get(plan['base'])
        if base is None or inc.digest(base.manifest) != plan['base_manifest_sha256']:
            raise RuntimeError('BASE_MANIFEST_CHANGED')
        self.validate(candidate)
        return candidate

    @contextmanager
    def locked(self, plan):
        # Journal flock proves a same-run RUNNING lock is an interrupted process,
        # not a second active instance; Reference flock excludes master writers.
        with inc.locked(self.journal), reference_publication_lock(self.data_root) as publish:
            run = CONTRACT + ':' + plan['candidate']
            result = self.store.acquire_run_lock(run, owner=CONTRACT, stale_after_seconds=10**12)
            if result['status'] != 'ACQUIRED' and result.get('active_run_id') != run:
                raise RuntimeError('ACTIVE_PROMOTION_CONFLICT')
            status = 'FAILED'
            try:
                yield publish
                status = 'COMPLETED'
            finally:
                self.store.release_run_lock(run, status=status)

    def authorize(self, plan, authorization=None):
        # The owner's instruction to publish one exact candidate is the
        # authority. What must be unambiguous is *what* is published, so only
        # the technical binding is enforced. Nominal identity and approval
        # references are optional trace, never a blocking requirement, and no
        # agent may turn them back into an approval step.
        required = dict(contract=CONTRACT, action='PROMOTE', candidate=plan['candidate'], base=plan['base'],
            manifest_sha256=plan['manifest_sha256'], reference=plan['reference_after']['current_reference_version'],
            retained_component_cutoffs=plan['retained_component_cutoffs'])
        supplied = authorization or {}
        if any(k in supplied and supplied[k] != v for k,v in required.items()):
            raise PermissionError('EXACT_OPERATIONAL_AUTHORIZATION_REQUIRED')
        return required

    def trace(self, authorization):
        # Automatic traceability: the journal already seals the plan, intent,
        # commit, activation and reader verification. An optional operator note
        # is stored once and never rewritten, so recovery is never blocked by a
        # different human annotation.
        if not authorization:
            return
        path = self.journal/'authorization.json'
        if not path.exists():
            inc.seal(path, authorization)

    def promote(self, authorization=None, *, fault=lambda point: None):
        plan = inc.read_json(self.journal/'plan.json')
        self.authorize(plan, authorization)
        self.resource_check()
        with self.locked(plan) as publish:
            candidate = self.check(plan)
            current = self.store.current_pointer()
            pointer = active_pointer(self.data_root)[0]
            if (current not in (plan['base'], plan['candidate'])
                    or pointer not in (plan['reference_before'], plan['reference_after'])):
                raise RuntimeError('CONCURRENT_PUBLICATION_CONFLICT')
            if (self.journal/'rollback-intent.json').exists():
                raise RuntimeError('ROLLED_BACK_RUN_REQUIRES_NEW_PREPARATION')
            self.trace(authorization)
            self.event('commit-intent', dict(candidate=plan['candidate'], base=plan['base']))
            if current == plan['base']:
                # The exact prepared target is also valid after an interrupted
                # precommit master activation. No third-party pointer is adopted.
                existing = self.store.get(plan['candidate'])
                if existing is None:
                    self.store.create_candidate(candidate)
                elif inc.digest(existing.manifest) != plan['manifest_sha256']:
                    raise RuntimeError('DUPLICATE_CANDIDATE_CONFLICT')
                self.store.set_status(plan['candidate'], READY_TO_COMMIT)
                self.resource_check()
                fault('during_activation')
                # The master pointer is not Foundation's visibility boundary.
                # A crash here leaves the old Foundation/Reference pair pinned;
                # the same journal can resume from either master-pointer state.
                if pointer == plan['reference_before']:
                    publish(pointer, plan['reference_after'])
                fault('after_activation')
                fault('before_commit')
                self.store.logical_commit(plan['candidate'], accredit=self.accredit)
                fault('after_commit')
            self.event('committed', dict(candidate=plan['candidate']))
            self.event('activated', dict(reference=plan['reference_after']['current_reference_version']))
            if self.store.current_pointer() != plan['candidate']:
                raise RuntimeError('CURRENT_CHANGED_AFTER_COMMIT')
            # All expensive reader/business gates ran BEFORE atomic visibility.
            # Reentry after lost acknowledgement only checks the durable receipt.
            from .foundation_read_binding import validate_binding
            selected = self.store.get(plan['candidate'])
            receipt = self.store.read_binding(plan['candidate'])
            validate_binding(selected, receipt)
            result = dict(foundation=selected.foundation_publication_id,
                          reference=selected.reference_version, snapshot=receipt['snapshot_id'],
                          components=sorted(selected.manifest['components']))
            self.event('verified', result)
            return dict(status='TECHNICALLY_ACTIVATED_READER_VERIFIED', candidate=plan['candidate'], reader=result)

    def rollback(self, *, reason):
        if not reason:
            raise ValueError('AUDITED_ROLLBACK_REASON_REQUIRED')
        plan = inc.read_json(self.journal/'plan.json')
        trace_path = self.journal/'authorization.json'
        self.authorize(plan, inc.read_json(trace_path) if trace_path.exists() else None)
        self.resource_check()
        with self.locked(plan) as publish:
            # Rollback must remain possible when the *new* candidate is corrupt.
            # Verify the retained base identity, not the failed candidate bytes.
            base = self.store.get(plan['base'])
            if base is None or inc.digest(base.manifest) != plan['base_manifest_sha256']:
                raise RuntimeError('ROLLBACK_BASE_MANIFEST_CHANGED')
            self.check_rollback_inputs(plan)
            self.validate(base)
            pointer = active_pointer(self.data_root)[0]
            if pointer not in (plan['reference_before'], plan['reference_after']):
                raise RuntimeError('REFERENCE_ROLLBACK_CONFLICT')
            if self.store.current_pointer() not in (plan['base'], plan['candidate']):
                raise RuntimeError('CURRENT_ROLLBACK_CONFLICT')
            self.event('rollback-intent', dict(reason=reason))
            if self.store.current_pointer() == plan['candidate']:
                self.store.logical_rollback(plan['base'], expected_current_foundation_publication_id=plan['candidate'], reason=reason)
            if pointer == plan['reference_after']:
                publish(pointer, plan['reference_before'])
            result = self.verify_reader(self.store.get(plan['base']))
            self.event('rolled-back', dict(base=plan['base'], reader=result))
            return dict(status='ROLLED_BACK', base=plan['base'])


def real_promotion(journal):
    from .ducklake import DuckLakeConnector, DATA_ROOT
    from .foundation_manifest import validate_manifest
    from .sales_facts_transition import verify_files
    from .sales_sealed_revalidation import validate_physical_files
    from .foundation_reader import FoundationReader
    from modules.telchi.runtime.resource_guard import ResourceGuard
    connector = DuckLakeConnector()
    def resource():
        if not ResourceGuard(temp_directory=Path(journal).parent.resolve()).assess().allowed:
            raise RuntimeError('RESOURCE_BLOCKED')
    def validate(candidate):
        with connector.session(read_only=True) as con:
            con.execute('SET threads=1')
            @contextmanager
            def same(): yield con
            store = FoundationPublicationStore(same)
            validate_manifest(store, candidate)
            if candidate.manifest.get('sales_facts_revalidation', {}).get('incremental_plan'):
                # Future cycles must prove consumer compatibility before CAS,
                # not discover stale accreditation only after visibility.
                from .sales_succession import validate_successor
                for physical in (False, True):
                    validate_successor(store, candidate, candidate.manifest['facts_base_snapshot_id'],
                                       physical=physical, _reader_validated=True)
        if 'sales_facts_revalidation' in candidate.manifest:
            verify_files(candidate.manifest)
        validate_physical_files(candidate.manifest['components'])
        commercial = candidate.manifest['components'].get('commercial_purpose')
        if commercial is not None:
            from .commercial_purpose_candidate import verify_commercial_component
            verify_commercial_component(commercial)
    def reader(candidate, connection=None):
        @contextmanager
        def session():
            if connection is not None:
                yield connection
            else:
                with connector.session(read_only=True) as con:
                    yield con
        with session() as con:
            con.execute('SET threads=1'); con.execute("SET memory_limit='512MB'")
            # This is an already committed preparation checkpoint, NOT a guess
            # at the next catalog snapshot. Data relations remain independently
            # pinned by the manifest. The selection/receipt commit follows only
            # after every full gate succeeds on this transaction's metadata.
            anchor = connector.snapshot(con) if connection is not None else None
            if anchor is not None:
                # DuckLake overlays this transaction's own writes even on a
                # time-travel relation. Use a separate read-only transaction to
                # inspect the genuinely committed preparation checkpoint.
                with connector.session(read_only=True) as checkpoint:
                    staged = checkpoint.execute(
                        'SELECT status, manifest_json, component_hash FROM telchi.ops.foundation_publications_v1 '
                        f'AT (VERSION => {anchor}) WHERE foundation_publication_id = ?',
                        [candidate.foundation_publication_id],
                    ).fetchall()
                selected_hash = con.execute(
                    'SELECT component_hash FROM telchi.ops.foundation_publications_v1 '
                    'WHERE foundation_publication_id = ?', [candidate.foundation_publication_id],
                ).fetchone()[0]
                if (len(staged) != 1 or staged[0][0] != READY_TO_COMMIT
                        or json.loads(staged[0][1]) != candidate.manifest
                        or staged[0][2] != selected_hash):
                    raise RuntimeError('PREPARED_SNAPSHOT_BINDING_MISMATCH')
            options = dict(snapshot_resolver=lambda *_: anchor) if anchor is not None else {}
            access = FoundationReader(connector, full_validation=True, **options).resolve_on(con)
            if access.foundation_publication_id != candidate.foundation_publication_id or access.foundation.reference_version != candidate.reference_version:
                raise RuntimeError('LIVE_READER_IDENTITY_MISMATCH')
            if 'sales_facts_revalidation' in candidate.manifest:
                from .sales_continuity_candidate import commercial_answers, TABLES
                for domain, tables in TABLES.items():
                    access.require_sales_coverage(domain, '2026-09-01', '2026-10-30')
                    for table in tables:
                        con.execute(f'CREATE TEMP VIEW full_{table} AS SELECT * FROM {access.relation(domain, table)}')
                answers = commercial_answers(con, candidate.foundation_publication_id)
                report = inc.read_json(Path(candidate.manifest['sales_facts_revalidation']['report_path']))
                from .sales_refresh_cycle import verify_cycle_money
                for window in report['coverage']:
                    access.require_sales_coverage(window['domain'], window['start'], window['end'])
                verify_cycle_money(con, report)
                for table, dataset in report['datasets'].items():
                    if con.execute('SELECT count(*) FROM full_'+table).fetchone()[0] != dataset['row_count']:
                        raise RuntimeError('LIVE_READER_ROW_COUNT_MISMATCH')
                for key, value in report['commercial_answers'].items():
                    if key != 'metadata' and inc.digest(value) != inc.digest(answers[key]):
                        raise RuntimeError('LIVE_COMMERCIAL_RECONCILIATION_MISMATCH: '+key)
            result = dict(foundation=access.foundation_publication_id, reference=access.foundation.reference_version,
                          snapshot=access.ducklake_snapshot_id, components=sorted(access.manifest['components']))
            from .independent_facts_succession import stock_contract, verify_reader
            from .operational_domains import CONTRACT as OBSERVATIONS
            stock = stock_contract(access.manifest)
            if stock:
                proof = access.manifest.get('independent_facts_succession', {})
                from .foundation_manifest import EXTENSIBLE_KIND
                retained = (access.manifest.get('candidate_kind') == EXTENSIBLE_KIND or
                    (proof.get('contract') == OBSERVATIONS
                    and bool(access.manifest.get('operational_observations', {}).get('overlap'))))
                if retained:
                    # The canonical full reader just verified the catalog-issued
                    # ancestor receipt, exact component/snapshot/Reference
                    # inheritance AND the sealed stock file's physical SHA256.
                    # Its old aggregate/UoM query is not a changed-component gate.
                    result['stock'] = dict(status='UNCHANGED_ACCREDITED_COMPONENT_BYTES_REUSED',
                        sha256=stock['dataset']['sha256'])
                else:
                    result['stock'] = verify_reader(con, access)
            from .operational_domains import observation_contract, verify_reader as verify_observations
            if observation_contract(access.manifest):
                result['operational_observations'] = verify_observations(con, access)
            # Finalize only after every physical/business reader gate succeeded.
            # This is an update operation, never invoked by productive readers.
            from .foundation_read_binding import make_binding, validate_binding
            from .foundation_publication import FoundationReaderError
            from .sales_succession import validate_successor, physical_metadata
            @contextmanager
            def same(): yield con
            read_store = FoundationPublicationStore(same)
            current = read_store.get(access.foundation_publication_id)
            for physical in (False, True):
                validate_successor(read_store, current, access.ducklake_snapshot_id,
                                   physical=physical, _reader_validated=True)
            physical = physical_metadata(access)
            try:
                binding = read_store.read_binding(current.foundation_publication_id)
            except FoundationReaderError:
                binding = None
            if binding is None:
                binding = make_binding(current, access, commercial=True, physical=physical)
            else:
                # Preserve the first accreditation (including across rollback);
                # retries validate again but never rewrite an immutable receipt.
                validate_binding(current, binding)
                if (binding['snapshot_id'] != access.ducklake_snapshot_id
                        or binding['commercial'] is not True or binding['physical'] != physical):
                    raise RuntimeError('READ_BINDING_REACCREDITATION_CONFLICT')
            if connection is not None:
                # New atomic activation receipts identify their durable
                # preparation anchor separately from the selection transaction.
                from .foundation_read_binding import digest
                binding['activation'] = dict(protocol='atomic-current-receipt-v1',
                                             prepared_snapshot_id=anchor)
                binding['receipt_sha256'] = digest({k:v for k,v in binding.items() if k != 'receipt_sha256'})
                validate_binding(current, binding)
                resource()
                return binding
            FoundationPublicationStore(connector.session).accredit_read_binding(current, binding)
            return result
    return Promotion(FoundationPublicationStore(connector.session), DATA_ROOT, journal,
                     validate=validate, verify_reader=reader, resource_check=resource, accredit=reader)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'promote', 'rollback'])
    parser.add_argument('--journal', required=True, type=Path)
    parser.add_argument('--candidate', type=Path)
    parser.add_argument('--authorization', type=Path,
                        help='optional operator trace; never a condition to publish')
    parser.add_argument('--reason')
    args = parser.parse_args()
    if args.action == 'prepare' and args.candidate is None:
        parser.error('--candidate required')
    promotion = real_promotion(args.journal)
    if args.action == 'prepare': result = promotion.prepare(args.candidate)
    elif args.action == 'promote':
        result = promotion.promote(inc.read_json(args.authorization) if args.authorization else None)
    else: result = promotion.rollback(reason=args.reason)
    print(json.dumps(result, default=str, sort_keys=True))


if __name__ == '__main__': main()
