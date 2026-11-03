"""Bounded investigative HANA transport. Default CLI is offline validation.

Not a published runtime capability. Reuses V2 selective ledger, existing HANA
adapter, device guard, cooperative budget and directory lock. No background work.
"""
import argparse
import json
import time
import uuid
from pathlib import Path

from . import selective as ledger
from ..controlled_physical_capture_v1 import capture as base
from ..controlled_physical_capture_v1 import persistence
from ..controlled_physical_capture_v1.orchestrate import Budget, cooperative_signals

ROOT = Path(__file__).resolve().parents[7]
SOURCE = ROOT/'data/reports/telchi/operational-universe-v2-20261029-final'
MANIFEST_SHA = 'd08a8cf343cbf3e17d1a7878146e15f56807bd3b81dcb69f292c1e7af844d7fb'
CAPTURE = base.PRIVATE/'physical-capture-physical-capture-to10000-20261029-v1-c04-b04'
CAPTURE_SHA = '7b8bbb992fcb83e3d0ec4ae4951084fad90fa12e5c7761ce0f408bf9b7b69099'


def validate_origin():
    """Pinned local evidence and complete captured prefix; no SQL or network."""
    if base.digest(SOURCE/'artifact_hashes.json') != MANIFEST_SHA:
        raise RuntimeError('source_manifest_changed')
    inventory = json.loads((SOURCE/'artifact_hashes.json').read_text())
    for name, expected in inventory.items():
        p = SOURCE/name
        if p.is_symlink() or not p.resolve().is_relative_to(SOURCE.resolve()) or base.digest(p) != expected:
            raise RuntimeError('source_artifact_changed')
    report = json.loads((SOURCE/'report.json').read_text())
    products = json.loads((SOURCE/'products.json').read_text())
    plan = json.loads((SOURCE/'selective_plan.json').read_text())
    ledger.validate_plan(plan)
    with base.destination_lock(CAPTURE):
        if base.digest(CAPTURE/'checkpoint.json') != CAPTURE_SHA:
            raise RuntimeError('capture_checkpoint_changed')
        _, rows, seen, _ = base.read_checkpoint(CAPTURE)
        captured = {r['ItemCode']: r['U_FormaFarmac'] for r in rows}
    keys = [p['ItemCode'] for p in products]
    covered = [p for p in products if p['classification_observed']]
    missing = [p['ItemCode'] for p in products if not p['reference_match']]
    if (keys != sorted(set(keys)) or len(keys) != 8001 or len(covered) != 4759 or
            len(set(keys) & seen) != 4759 or
            plan['item_codes'] != sorted(set(keys)-seen) or len(plan['item_codes']) != 3242 or
            [p['ItemCode'] for p in covered] != sorted(set(keys)&seen) or
            any(p['U_FormaFarmac'] != captured[p['ItemCode']] for p in covered) or
            sum(p['physical_status']=='EXPLICIT' for p in products) != 1276 or
            missing != report['identity_missing_reference'] or len(missing) != 43 or
            any(p['canonical_product_id'] is not None for p in products if not p['reference_match']) or
            len(plan['batches']) != 130 or len({b['block'] for b in plan['batches']}) != 26 or
            len(plan['batches'][-1]['parameters']) != 17):
        raise RuntimeError('universe_discrepancy')
    return plan


def fetch(connection, batch, *, clock=time.monotonic, audit=None):
    """Exact plan SQL, bound qmark values; strict ordered response contract."""
    from modules.telchi.datalake.sql import assert_read_only_select
    sql, params = ledger.selective_query(batch['parameters'])
    if batch['sql'] != sql:
        raise RuntimeError('unexpected_selective_sql')
    assert_read_only_select(sql)
    cursor = connection.cursor()
    if audit is not None:
        audit['cursors_opened'] += 1
    try:
        # Driver cancellation is coarse (seconds); 1.5s policy is measured below.
        # Never abandon a driver/fsync thread to fake a hard wall-clock timeout.
        cursor.setquerytimeout(3)
        started = clock()
        cursor.execute(sql, params)
        raw = cursor.fetchall()
        elapsed = clock()-started
        if [d[0] for d in cursor.description] != ['ItemCode', 'U_FormaFarmac']:
            raise RuntimeError('unexpected_columns')
        if len(raw) > len(batch['parameters']) or any(len(row) != 2 for row in raw):
            raise RuntimeError('unexpected_response_shape')
        return [dict(zip(('ItemCode','U_FormaFarmac'), row)) for row in raw], elapsed
    finally:
        cursor.close()
        if audit is not None:
            audit['cursors_closed'] += 1


def run(root, plan, *, resume=False, max_blocks=1, budget=None,
        connect_factory=None, sleep=time.sleep, clock=time.monotonic,
        preflight=persistence.preflight, probe=persistence.verify_probe,
        _destination_lock=base.destination_lock):
    """One process/connection, <=5 queries/block, no retries. Caller authorizes SAP.

    Tests inject every network and device boundary. An unresolved intent blocks
    connection creation. Sessions resume only after validating durable output.
    """
    ledger.validate_plan(plan)
    if type(max_blocks) is not int or not 1 <= max_blocks <= 26:
        raise ValueError('invalid_block_budget')
    ledger.validate_destination(root)
    budget = budget or Budget(clock=clock)
    preflight(root if root.exists() else root.parent)
    if not resume:
        root.mkdir(mode=0o700, exist_ok=False)
        base.sync_directory(root.parent)
    # Continuation may already own the directory lock while seeding its prefix.
    with _destination_lock(root):
        if not resume:
            ledger.initialize(root, plan)
        cp = ledger.recover(root, plan)
        if (root/'request.json').exists():
            raise RuntimeError('uncertain_request_manual_review_no_retry')
        if len(cp['batches']) == len(plan['batches']):
            return dict(status='COMPLETE', queries=0, completed=len(cp['batches']))
        destination_evidence = preflight(root)
        evidence = probe(root, base.save, base.digest, base.sync_directory)
        sessions = root/'sessions'
        sessions.mkdir(mode=0o700, exist_ok=True)
        base.sync_directory(root)
        session = sessions/(uuid.uuid4().hex+'.json')
        state = dict(status='PARTIAL', queries=0, completed=len(cp['batches']),
            started_at=base.utc(), plan_sha256=plan['plan_sha256'],
            hana_seconds=[], persistence_seconds=[], connection_closed=False,
            cursors_opened=0, cursors_closed=0,
            retries=0, concurrency=1, controls=ledger.CONTROLS, probe=evidence,
            destination_checks=[destination_evidence])
        started = clock()
        base.save(session, state)
        if clock()-started > 10:
            raise persistence.PersistenceBlocked('session_persistence_budget_exceeded')
        connection = None
        try:
            # Conservative restart pause, even across process boundaries.
            if cp['batches']:
                if not budget.can_start_query(30):
                    state['reason'] = budget.reason()
                    return state
                sleep(30)
            first_block = len(cp['batches'])//5
            for index in range(len(cp['batches']), len(plan['batches'])):
                if index//5-first_block >= max_blocks:
                    state['reason'] = 'block_budget_exhausted'
                    break
                pause = (30 if index % 5 == 0 else 10) if state['queries'] else 0
                if not budget.can_start_query(pause):
                    state['reason'] = budget.reason()
                    break
                if pause:
                    sleep(pause)
                state['destination_checks'].append(preflight(root))
                if not budget.can_start_query():
                    state['reason'] = budget.reason()
                    break
                if connection is None:
                    connection = (connect_factory or base.connect_hana)()
                # Connection setup and preflight may consume the remaining budget.
                if not budget.can_start_query():
                    state['reason'] = budget.reason()
                    break
                started = clock()
                ledger.reserve_request(root, plan, index, reserved_at=base.utc())
                intent_seconds = clock()-started
                if intent_seconds > 10:
                    raise persistence.PersistenceBlocked('intent_persistence_budget_exceeded')
                if not budget.can_start_query():
                    state['reason'] = budget.reason()
                    break
                state['queries'] += 1
                rows, elapsed = fetch(connection, plan['batches'][index], clock=clock, audit=state)
                state['hana_seconds'].append(elapsed)
                started = clock()
                cp = ledger.commit_response(root, plan, index, rows,
                    observed_at=base.utc(), fetch_complete=True)
                state['completed'] = len(cp['batches'])
                persisted = clock()-started + intent_seconds
                state['persistence_seconds'].append(persisted)
                # Finish fsync/readback first, then inhibit further queries.
                base.save(session, state)
                persisted = clock()-started + intent_seconds
                state['persistence_seconds'][-1] = persisted
                if persisted > 10:
                    raise persistence.PersistenceBlocked('local_persistence_budget_exceeded')
                if elapsed > 1.5:
                    state['reason'] = 'hana_latency_exceeded'
                    break
            else:
                state['reason'] = 'plan_complete'
            if state.get('reason') in ('plan_complete','block_budget_exhausted'):
                state['status'] = 'COMPLETE' if state['completed']==len(plan['batches']) else 'BLOCKS_COMPLETE'
        except BaseException as exc:
            state['reason'] = type(exc).__name__  # No driver text/credentials.
            if isinstance(exc, persistence.PersistenceBlocked):
                state['persistence_block'] = str(exc)
        finally:
            if connection is not None:
                try:
                    connection.close()
                    state['connection_closed'] = True
                except BaseException as exc:
                    state.update(status='PARTIAL', close_error=type(exc).__name__)
            else:
                state['connection_closed'] = True
            state.update(finished_at=base.utc(), checkpoint_sha256=base.digest(root/'checkpoint.json'))
            base.save(session, state)
        return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['validate','recover','review-uncertain','run'])
    parser.add_argument('--destination', type=Path)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--max-blocks', type=int, default=1)
    parser.add_argument('--seconds', type=float, default=1800)
    parser.add_argument('--authorize-hana', choices=['SELECTIVE_CAPTURE_EXPLICITLY_AUTHORIZED'])
    parser.add_argument('--reason')
    args = parser.parse_args()
    if args.action == 'run' and not args.authorize_hana:
        parser.error('new explicit HANA authorization required')
    plan = validate_origin()
    if args.action == 'validate':
        print(json.dumps(dict(status='VALID', identities=len(plan['item_codes']),
            batches=130, blocks=26, last_batch=17, plan_sha256=plan['plan_sha256'], hana_queries=0)))
        return 0
    if args.destination is None:
        parser.error('--destination required')
    root = args.destination.absolute()
    ledger.validate_destination(root)
    if args.action != 'run':
        with base.destination_lock(root):
            cp = (ledger.acknowledge_uncertain(root, plan, reason=args.reason)
                if args.action=='review-uncertain' else ledger.recover(root, plan))
        print(json.dumps(dict(completed=len(cp['batches']), hana_queries=0,
                              unresolved_request=(root/'request.json').exists())))
        return 0
    before = base.file_inventory(CAPTURE)
    budget = Budget(args.seconds)
    with cooperative_signals(budget):
        result = run(root, plan, resume=args.resume, max_blocks=args.max_blocks, budget=budget)
    if base.file_inventory(CAPTURE) != before:
        raise RuntimeError('prior_capture_changed')
    print(json.dumps(result))
    return 0 if result['status'] in ('COMPLETE','BLOCKS_COMPLETE') else 1


if __name__ == '__main__':
    raise SystemExit(main())
