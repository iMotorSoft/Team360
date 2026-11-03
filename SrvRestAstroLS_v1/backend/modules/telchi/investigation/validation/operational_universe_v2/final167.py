"""One-shot final 167 authorization; unchanged ledger, transport and safety limits."""
import argparse
from contextlib import ExitStack, nullcontext
import json
from pathlib import Path
import time

from . import final_completion as previous, continuation, selective as ledger, transport
from ..controlled_physical_capture_v1 import capture as base, persistence
from ..controlled_physical_capture_v1.orchestrate import Budget, cooperative_signals

SOURCE = base.PRIVATE/'physical-selective-final242-20261029-v1-b01'
SOURCE_SHA = '420d0d2a335f139536cb612a4e7e7e342234eaf78da258bee531813096a7a2b0'
CONTROL = base.PRIVATE/'physical-selective-final167-20261029-v1'
EVIDENCE = transport.ROOT/'data/reports/telchi/selective-final167-20261029-v1'


def review_source(plan):
    prior = json.loads((continuation.CONTROL/'report.json').read_text())
    if base.digest(continuation.CONTROL/'report.json') != previous.PRIOR_SHA:
        raise RuntimeError('ancestor_control_changed')
    first = previous.review(prior)
    prefix = previous.verify_source(plan, prior)
    cp = previous.durable(SOURCE, plan)
    if base.digest(SOURCE/'checkpoint.json') != SOURCE_SHA or len(cp['batches']) != 123:
        raise RuntimeError('source_checkpoint_mismatch')
    if cp['batches'][:120] != prefix['batches']:
        raise RuntimeError('source_prefix_mismatch')
    sessions = [json.loads(p.read_text()) for p in (SOURCE/'sessions').glob('*.json')]
    if len(sessions) != 1:
        raise RuntimeError('source_session_count')
    state = sessions[0]
    if (state['queries'] != 3 or state['hana_seconds'] !=
            [0.5382619699994393, 0.1630020680022426, 1.9761375669986592] or
            state['reason'] != 'hana_latency_exceeded' or state['status'] != 'PARTIAL' or
            not state['connection_closed'] or state['cursors_opened'] != 3 or
            state['cursors_closed'] != 3 or state['retries'] or state.get('close_error') or
            len(state['persistence_seconds']) != 3 or max(state['persistence_seconds']) > 10):
        raise RuntimeError('source_session_anomaly')
    batches = [json.loads((SOURCE/e['file']).read_text()) for e in cp['batches']]
    requested = [k for b in batches for k in b['requested']]
    if (requested != plan['item_codes'][:3075] or len(set(requested)) != 3075 or
            sum(len(b['not_returned']) for b in batches) != 43 or
            [len(b['parameters']) for b in plan['batches'][123:]] != [25]*6+[17]):
        raise RuntimeError('remaining_identity_mismatch')
    before = base.file_inventory(SOURCE)
    for _ in range(2):
        if ledger.recover(SOURCE, plan) != cp or base.file_inventory(SOURCE) != before:
            raise RuntimeError('recovery_not_idempotent')
    return cp, dict(first_event=first, second_session=state,
        conclusion='Two isolated SELECT/fetch excesses; no persistent slowdown demonstrated; '
                   'no causal attribution or additional investigation queries.')


def run(*, authorize=False):
    plan = transport.validate_origin()
    report = dict(verdict='PARTIAL', blocks=[], additional_selects=0,
        last_durable_destination=str(SOURCE), checkpoint_sha256=SOURCE_SHA,
        automatic_retries=0, concurrency=1)
    with ExitStack() as stack:
        for root in (continuation.ORIGIN, continuation.CONTROL, previous.SOURCE,
                     previous.CONTROL, SOURCE):
            stack.enter_context(base.destination_lock(root))
        cp, review = review_source(plan)
        report['offline_latency_review'] = review
        baseline = {str(p): base.file_inventory(p) for p in base.PRIVATE.iterdir()
                    if p.is_dir() and p.name.startswith(('physical-capture-', 'physical-selective-'))}
        report.update(integrity='PASS', resolved_before=3075, pending_before=167,
                      previous_capture_directories=len(baseline))
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
                # Retain the original immutable plan boundaries: batches 123-124,
                # then 125-129. Exactly six sets of 25 and the final set of 17.
                for number, expected_queries in ((1, 2), (2, 5)):
                    if not budget.can_start_block():
                        raise RuntimeError(budget.reason())
                    if report['additional_selects'] + expected_queries > 7:
                        raise RuntimeError('query_budget_exceeded')
                    if any(base.file_inventory(Path(p)) != inv for p, inv in baseline.items()):
                        raise RuntimeError('prior_capture_changed')
                    root = base.PRIVATE/f'{CONTROL.name}-b{number:02d}'
                    if root.exists():
                        raise RuntimeError('destination_exists')
                    report['attempt'] = str(root)
                    base.save(CONTROL/'report.json', report)
                    with (nullcontext() if source == SOURCE else base.destination_lock(source)):
                        previous.durable(source, plan)
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
                            # Count attempted SELECTs even if durable validation fails.
                            report['additional_selects'] += state['queries']
                            base.save(CONTROL/'report.json', report)
                            cp = previous.durable(root, plan)
                            if cp['batches'][:len(initial['batches'])] != initial['batches']:
                                raise RuntimeError('prefix_changed')
                            report.update(last_durable_destination=str(root),
                                          checkpoint_sha256=base.digest(root/'checkpoint.json'))
                            report.pop('attempt')
                            base.save(CONTROL/'report.json', report)
                            # PARTIAL latency responses remain durable, never admit next block.
                            continuation.clean_state(root, plan)
                            if (state['queries'] != expected_queries or
                                    len(cp['batches']) != len(initial['batches'])+expected_queries):
                                raise RuntimeError('unexpected_block_count')
                            source = root
                if len(cp['batches']) != 130 or report['additional_selects'] != 7:
                    raise RuntimeError('incomplete_final_plan')
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
    parser.add_argument('--authorize-hana', choices=['FINAL_167_EXPLICITLY_AUTHORIZED'])
    args = parser.parse_args()
    result = run(authorize=bool(args.authorize_hana))
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    base.save(EVIDENCE/('execution.json' if args.authorize_hana else 'offline-review.json'), result)
    print(json.dumps(result), flush=True)
    return 0 if result['verdict'] == 'PASS' or not args.authorize_hana else 1


if __name__ == '__main__':
    raise SystemExit(main())
