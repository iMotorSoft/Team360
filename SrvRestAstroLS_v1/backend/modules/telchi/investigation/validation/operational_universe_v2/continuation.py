"""Immutable-destination selective continuation; one connection per new block.

The original directory is the common exclusion anchor, held for the whole cycle.
The durable control records an attempt BEFORE creating a destination. An interrupted
attempt blocks subsequent cycles; recovery is offline, never an automatic requery.
"""
import argparse
from contextlib import nullcontext
import json
import os
from pathlib import Path
import time

from . import selective as ledger, transport
from ..controlled_physical_capture_v1 import capture as base, persistence
from ..controlled_physical_capture_v1.orchestrate import Budget, cooperative_signals

ORIGIN = base.PRIVATE/'physical-selective-phase3-20261029-micro-v1'
ORIGIN_SHA = 'db221fe7ed6280aa929c70f2d6395e9d97add618a2e52c291131ee09ae0ed4e5'
CONTROL = base.PRIVATE/'physical-selective-phase5-20261029-control-v1'


def clean_state(root, plan):
    """Read-only validation: prior captures must not need recovery or cleanup."""
    if any(p.is_symlink() for p in root.rglob('*')):
        raise RuntimeError('source_symlink')
    if (any((root/n).exists() for n in ('request.json', 'pending.json')) or
            list(root.rglob('*.tmp')) or (root/'.persistence-probe.json').exists()):
        raise RuntimeError('source_requires_offline_recovery')
    cp = ledger.read_state(root, plan)
    if {p.name for p in root.glob('selective-*.json')} != {e['file'] for e in cp['batches']}:
        raise RuntimeError('untracked_source_batch')
    for path in (root/'sessions').glob('*.json'):
        state = json.loads(path.read_text())
        if (state['status'] not in ('BLOCKS_COMPLETE', 'COMPLETE') or
                not state['connection_closed'] or state['retries'] != 0 or
                state['cursors_opened'] != state['cursors_closed'] or
                any(x > 1.5 for x in state['hana_seconds']) or
                any(x > 10 for x in state['persistence_seconds'])):
            raise RuntimeError('source_session_not_certified')
    return cp


def seed(source, root, plan, cp):
    """Caller holds BOTH directory locks. Copy bytes, never link mutable inodes."""
    if any(root.iterdir()):
        raise RuntimeError('destination_not_empty')
    for name in ['plan.json', *[e['file'] for e in cp['batches']], 'checkpoint.json']:
        data = (source/name).read_bytes()
        with (root/name).open('xb') as stream:
            if stream.write(data) != len(data):
                raise OSError('short_prefix_write')
            stream.flush()
            os.fsync(stream.fileno())
    base.save(root/'lineage.json', dict(source=str(source),
        checkpoint_sha256=base.digest(source/'checkpoint.json'),
        inherited_batches=len(cp['batches']), plan_sha256=plan['plan_sha256']))
    base.sync_directory(root)
    if ledger.read_state(root, plan) != cp:
        raise RuntimeError('prefix_copy_mismatch')


def verify_history(report, plan):
    """Check every frozen ancestor, not only the immediately preceding block."""
    previous = None
    for entry in report['history']:
        root = Path(entry['destination'])
        ledger.validate_destination(root)
        cp = clean_state(root, plan)
        if base.file_inventory(root) != entry['inventory']:
            raise RuntimeError('prior_destination_changed')
        if previous is not None and cp['batches'][:len(previous['batches'])] != previous['batches']:
            raise RuntimeError('ancestor_prefix_mismatch')
        previous = cp
    if previous is None or len(previous['batches']) != report['completed']:
        raise RuntimeError('control_checkpoint_mismatch')
    return previous


def cycle(origin, control, plan, *, expected_origin_sha, max_blocks=4,
          budget=None, clock=time.monotonic, sleep=time.sleep,
          connect_factory=None, preflight=persistence.preflight,
          probe=persistence.verify_probe):
    """At most four sequential blocks per <=1800s cycle; no retry of attempts.

    Resume uses only the durable control's last certified destination. A second
    control/branch is rejected by inspecting lineage under the origin lock.
    """
    if type(max_blocks) is not int or not 1 <= max_blocks <= 4:
        raise ValueError('invalid_cycle_block_budget')
    ledger.validate_plan(plan)
    for path in (origin, control):
        ledger.validate_destination(path)
    budget = budget or Budget(clock=clock)
    preflight(control.parent)
    with base.destination_lock(origin):
        if base.digest(origin/'checkpoint.json') != expected_origin_sha:
            raise RuntimeError('origin_checkpoint_changed')
        original = clean_state(origin, plan)
        if len(original['batches']) != 5:
            raise RuntimeError('expected_microcapture_five_batches')
        # A stale or different control must never fork the ledger from the micro.
        for path in origin.parent.glob('*/lineage.json'):
            lineage = json.loads(path.read_text())
            if lineage.get('origin') == str(origin) and lineage.get('control') != str(control):
                raise RuntimeError('other_continuation_control_exists')
        if not control.exists():
            control.mkdir(mode=0o700, exist_ok=False)
            base.sync_directory(control.parent)
        with base.destination_lock(control):
            report_path = control/'report.json'
            if report_path.exists():
                report = json.loads(report_path.read_text())
                if (report['origin'] != str(origin) or report['origin_sha256'] != expected_origin_sha or
                        report['plan_sha256'] != plan['plan_sha256']):
                    raise RuntimeError('control_origin_mismatch')
                if report['status'] not in ('CYCLE_COMPLETE', 'COMPLETE') or report.get('attempt'):
                    raise RuntimeError('previous_attempt_requires_offline_review')
            else:
                if any(control.iterdir()):
                    raise RuntimeError('incomplete_control_requires_review')
                report = dict(status='CYCLE_COMPLETE', origin=str(origin),
                    origin_sha256=expected_origin_sha, plan_sha256=plan['plan_sha256'],
                    completed=5, queries=0, blocks=[], cycles=[], history=[dict(
                        destination=str(origin), inventory=base.file_inventory(origin))])
            cp = verify_history(report, plan)
            cycle_start = clock()
            current_cycle = dict(started_at=base.utc(), first_batch=len(cp['batches']), blocks=0)
            report['cycles'].append(current_cycle)
            report['status'] = 'RUNNING'
            base.save(report_path, report)
            try:
                for _ in range(max_blocks):
                    cp = verify_history(report, plan)
                    if len(cp['batches']) == len(plan['batches']):
                        report['status'] = 'COMPLETE'
                        break
                    if not budget.can_start_block():
                        raise RuntimeError(budget.reason())
                    if len(cp['batches']) % 5:
                        raise RuntimeError('source_not_at_block_boundary')
                    if report['queries'] >= 125 or len(report['blocks']) >= 25:
                        raise RuntimeError('authorized_budget_exhausted')
                    source = Path(report['history'][-1]['destination'])
                    root = control.parent/f'{control.name}-b{len(cp["batches"])//5:02d}'
                    ledger.validate_destination(root)
                    if root.exists():
                        raise RuntimeError('next_destination_already_exists')
                    # Durable admission record: even a crash during prefix copying
                    # cannot cause a second process to query the same attempt.
                    report['attempt'] = str(root)
                    base.save(report_path, report)
                    source_context = nullcontext() if source == origin else base.destination_lock(source)
                    with source_context:
                        clean_state(source, plan)
                        preflight(control.parent)
                        root.mkdir(mode=0o700, exist_ok=False)
                        base.sync_directory(root.parent)
                        with base.destination_lock(root):
                            started = clock()
                            seed(source, root, plan, cp)
                            lineage = json.loads((root/'lineage.json').read_text())
                            base.save(root/'lineage.json', dict(lineage, origin=str(origin), control=str(control)))
                            if clock()-started > 10:
                                raise persistence.PersistenceBlocked('prefix_persistence_budget_exceeded')
                            state = transport.run(root, plan, resume=True, max_blocks=1,
                                budget=budget, clock=clock, sleep=sleep,
                                connect_factory=connect_factory, preflight=preflight, probe=probe,
                                _destination_lock=lambda _: nullcontext())
                            elapsed = clock()-started
                            after = ledger.read_state(root, plan)
                            block = dict(destination=str(root), initial_batch=len(cp['batches']),
                                completed=len(after['batches']), duration_seconds=elapsed, session=state)
                            report['blocks'].append(block)
                            report['queries'] += state['queries']
                            current_cycle['blocks'] += 1
                            if (state['status'] not in ('BLOCKS_COMPLETE', 'COMPLETE') or
                                    not state['connection_closed'] or
                                    state['cursors_opened'] != state['cursors_closed'] or
                                    state['queries'] != min(5, len(plan['batches'])-len(cp['batches'])) or
                                    len(after['batches']) != len(cp['batches'])+state['queries'] or
                                    after['batches'][:len(cp['batches'])] != cp['batches']):
                                raise RuntimeError('block_not_certified:' + state.get('reason', 'unknown'))
                            clean_state(root, plan)
                            verify_history(report, plan)
                            report['history'].append(dict(destination=str(root), inventory=base.file_inventory(root)))
                            report['completed'] = len(after['batches'])
                            report.pop('attempt')
                            base.save(report_path, report)
                else:
                    report['status'] = ('COMPLETE' if report['completed'] == len(plan['batches'])
                                        else 'CYCLE_COMPLETE')
            except BaseException as exc:
                report.update(status='PARTIAL', reason=type(exc).__name__)
                if isinstance(exc, (RuntimeError, persistence.PersistenceBlocked)):
                    report['stop_detail'] = str(exc)
            finally:
                current_cycle.update(finished_at=base.utc(), duration_seconds=clock()-cycle_start)
                report['last_valid_destination'] = report['history'][-1]['destination']
                report['checkpoint_sha256'] = base.digest(Path(report['last_valid_destination'])/'checkpoint.json')
                # A verified ancestor remains available even when the new attempt
                # has an uncertain intent or a recoverable journal.
                try:
                    verify_history(report, plan)
                    report['prior_integrity'] = 'PASS'
                except BaseException:
                    report.update(status='PARTIAL', prior_integrity='FAIL')
                base.save(report_path, report)
            return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--max-blocks', type=int, default=4)
    parser.add_argument('--seconds', type=float, default=1800)
    parser.add_argument('--authorize-hana', required=True,
                        choices=['SELECTIVE_CAPTURE_EXPLICITLY_AUTHORIZED'])
    args = parser.parse_args()
    plan = transport.validate_origin()
    budget = Budget(args.seconds)
    with cooperative_signals(budget):
        report = cycle(ORIGIN, CONTROL, plan, expected_origin_sha=ORIGIN_SHA,
                       max_blocks=args.max_blocks, budget=budget)
    print(json.dumps({k: v for k, v in report.items() if k != 'history'}), flush=True)
    return 0 if report['status'] in ('CYCLE_COMPLETE', 'COMPLETE') else 1


if __name__ == '__main__':
    raise SystemExit(main())
