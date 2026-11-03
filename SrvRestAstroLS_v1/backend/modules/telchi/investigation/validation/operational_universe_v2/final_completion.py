"""One-shot authorized final 242 identities; immutable reviewed latency ancestor.

Reuses the unchanged transport/ledger. The prior PARTIAL control is never reset.
Admission is durable before each fresh destination; this entrypoint cannot resume.
"""
import argparse
from contextlib import ExitStack, nullcontext
import json
from pathlib import Path
import statistics
import time

from . import continuation, selective as ledger, transport
from ..controlled_physical_capture_v1 import capture as base, persistence
from ..controlled_physical_capture_v1.orchestrate import Budget, cooperative_signals

SOURCE = base.PRIVATE/'physical-selective-phase5-20261029-control-v1-b23'
SOURCE_SHA = 'af90849c8a39448073b664d47aa89035a5c71ae4123d85df7a0c047caab43bd9'
PRIOR_SHA = '69841e60a718e0fd80aa0e79a88ca7d235882827dbf1dda8ab8f009aaa80b460'
CONTROL = base.PRIVATE/'physical-selective-final242-20261029-v1'
EVIDENCE = transport.ROOT/'data/reports/telchi/selective-final242-20261029-v1'


def durable(root, plan):
    if any(p.is_symlink() for p in root.rglob('*')):
        raise RuntimeError('symlink')
    if (any((root/n).exists() for n in ('request.json', 'pending.json', '.persistence-probe.json'))
            or list(root.rglob('*.tmp'))):
        raise RuntimeError('unresolved_persistence')
    cp = ledger.read_state(root, plan)
    if {p.name for p in root.glob('selective-*.json')} != {e['file'] for e in cp['batches']}:
        raise RuntimeError('untracked_response')
    return cp


def review(prior):
    blocks = prior['blocks']
    values = [v for b in blocks for v in b['session']['hana_seconds']]
    for i, b in enumerate(blocks):
        s = b['session']
        if (s['queries'] != 5 or s['retries'] or not s['connection_closed'] or
                s['cursors_opened'] != 5 or s['cursors_closed'] != 5 or
                s.get('close_error') or len(s['hana_seconds']) != 5 or
                len(s['persistence_seconds']) != 5 or max(s['persistence_seconds']) > 10 or
                s['status'] != ('PARTIAL' if i == 22 else 'BLOCKS_COMPLETE') or
                s['reason'] != ('hana_latency_exceeded' if i == 22 else 'block_budget_exhausted')):
            raise RuntimeError('unexpected_prior_transport_state')
    if (len(values) != 115 or [i for i, v in enumerate(values) if v > 1.5] != [114]
            or values[-1] != 1.7392748710008163 or max(values[-6:-1]) >= 1.0):
        raise RuntimeError('latency_review_not_isolated')
    ordered = sorted(values)
    return dict(verdict='CONTINUATION_ALLOWED', hana_queries=0, count=115,
        seconds=values, minimum=min(values), median=statistics.median(values),
        p90_nearest_rank=ordered[103], p95_nearest_rank=ordered[109],
        p99_nearest_rank=ordered[113], maximum=max(values),
        near_limit_1_to_1_5_seconds=[], exceeded_queries=[115], last_15_seconds=values[-15:],
        connection_errors_recorded=0, connection_losses_recorded=0,
        transport_anomaly='One SELECT/fetch wall-clock spike; transport/server split unavailable.',
        conclusion='No persistent anomaly demonstrated. Exact durable response retained; no replay.')


def verify_source(plan, prior):
    continuation.verify_history(prior, plan)
    cp = durable(SOURCE, plan)
    if base.digest(SOURCE/'checkpoint.json') != SOURCE_SHA or len(cp['batches']) != 120:
        raise RuntimeError('reviewed_checkpoint_mismatch')
    if cp['batches'][:115] != ledger.read_state(Path(prior['last_valid_destination']), plan)['batches']:
        raise RuntimeError('reviewed_prefix_mismatch')
    sessions = list((SOURCE/'sessions').glob('*.json'))
    if len(sessions) != 1 or json.loads(sessions[0].read_text()) != prior['blocks'][-1]['session']:
        raise RuntimeError('reviewed_session_mismatch')
    batches = [json.loads((SOURCE/e['file']).read_text()) for e in cp['batches']]
    requested = [k for b in batches for k in b['requested']]
    missing = [k for b in batches for k in b['not_returned']]
    if (requested != plan['item_codes'][:3000] or len(missing) != 43 or
            len(plan['item_codes'][3000:]) != 242 or len(plan['batches']) != 130 or
            len(plan['batches'][-1]['parameters']) != 17):
        raise RuntimeError('identity_reconciliation_failed')
    before = base.file_inventory(SOURCE)
    for _ in range(2):
        if ledger.recover(SOURCE, plan) != cp or base.file_inventory(SOURCE) != before:
            raise RuntimeError('recovery_not_idempotent')
    return cp


def run(*, authorize=False):
    plan = transport.validate_origin()
    report = dict(verdict='PARTIAL', blocks=[], additional_selects=0,
        last_durable_destination=str(SOURCE), checkpoint_sha256=SOURCE_SHA,
        branch='feature/console-backend-core', automatic_retries=0, concurrency=1)
    with ExitStack() as stack:
        # Same original exclusion anchor as all prior continuation cycles.
        for root in (continuation.ORIGIN, continuation.CONTROL, SOURCE):
            stack.enter_context(base.destination_lock(root))
        if base.digest(continuation.CONTROL/'report.json') != PRIOR_SHA:
            raise RuntimeError('prior_control_changed')
        prior = json.loads((continuation.CONTROL/'report.json').read_text())
        report['offline_latency_review'] = review(prior)
        cp = verify_source(plan, prior)
        baseline = {str(p): base.file_inventory(p) for p in base.PRIVATE.iterdir()
                    if p.is_dir() and (p.name.startswith('physical-capture-') or
                                      p.name.startswith('physical-selective-'))}
        report.update(integrity='PASS', resolved_before=3000, pending_before=242,
                      previous_capture_directories=len(baseline), recovery='IDEMPOTENT_NO_WRITES')
        if not authorize:
            return report
        if CONTROL.exists():
            raise RuntimeError('one_shot_control_already_exists_no_automatic_resume')
        report['destination_preflight'] = persistence.preflight(base.PRIVATE)
        CONTROL.mkdir(mode=0o700, exist_ok=False)
        base.sync_directory(CONTROL.parent)
        stack.enter_context(base.destination_lock(CONTROL))
        base.save(CONTROL/'baseline.json', baseline)
        base.save(CONTROL/'report.json', report)
        budget = Budget(900)
        source = SOURCE
        with cooperative_signals(budget):
            try:
                for number in range(1, 3):
                    if not budget.can_start_block():
                        raise RuntimeError(budget.reason())
                    if base.file_inventory(SOURCE) != baseline[str(SOURCE)]:
                        raise RuntimeError('origin_changed')
                    root = base.PRIVATE/f'{CONTROL.name}-b{number:02d}'
                    if root.exists():
                        raise RuntimeError('destination_exists')
                    report['attempt'] = str(root)
                    base.save(CONTROL/'report.json', report)
                    with (nullcontext() if source == SOURCE else base.destination_lock(source)):
                        durable(source, plan)
                        persistence.preflight(base.PRIVATE)
                        root.mkdir(mode=0o700, exist_ok=False)
                        base.sync_directory(root.parent)
                        with base.destination_lock(root):
                            started = time.monotonic()
                            continuation.seed(source, root, plan, cp)
                            prefix_seconds = time.monotonic()-started
                            if prefix_seconds > 10:
                                raise persistence.PersistenceBlocked('prefix_budget_exceeded')
                            initial = cp
                            state = transport.run(root, plan, resume=True, max_blocks=1,
                                budget=budget, _destination_lock=lambda _: nullcontext())
                            report['blocks'].append(dict(destination=str(root), session=state,
                                duration_seconds=time.monotonic()-started, prefix_seconds=prefix_seconds))
                            report['additional_selects'] += state['queries']
                            base.save(CONTROL/'report.json', report)
                            cp = durable(root, plan)
                            if cp['batches'][:len(initial['batches'])] != initial['batches']:
                                raise RuntimeError('prefix_changed')
                            report.update(last_durable_destination=str(root),
                                          checkpoint_sha256=base.digest(root/'checkpoint.json'))
                            report.pop('attempt')
                            base.save(CONTROL/'report.json', report)
                            # Includes the fifth SELECT latency: never admit another block on PARTIAL.
                            continuation.clean_state(root, plan)
                            if state['queries'] != 5 or len(cp['batches']) != 120+5*number:
                                raise RuntimeError('unexpected_block_count')
                            if report['additional_selects'] > 10:
                                raise RuntimeError('query_budget_exceeded')
                            source = root
                report['verdict'] = 'PASS'
            except BaseException as exc:
                report.update(verdict='PARTIAL', stop_reason=type(exc).__name__)
                if isinstance(exc, (RuntimeError, persistence.PersistenceBlocked)):
                    report['stop_detail'] = str(exc)
            finally:
                report['prior_captures_unchanged'] = all(base.file_inventory(Path(p)) == v
                                                        for p, v in baseline.items())
                if not report['prior_captures_unchanged']:
                    report['verdict'] = 'FAIL'
                report['finished_at'] = base.utc()
                base.save(CONTROL/'report.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--authorize-hana', choices=['FINAL_242_EXPLICITLY_AUTHORIZED'])
    args = parser.parse_args()
    result = run(authorize=bool(args.authorize_hana))
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    base.save(EVIDENCE/('execution.json' if args.authorize_hana else 'offline-review.json'), result)
    print(json.dumps(result), flush=True)
    return 0 if result['verdict'] == 'PASS' or not args.authorize_hana else 1


if __name__ == '__main__':
    raise SystemExit(main())
