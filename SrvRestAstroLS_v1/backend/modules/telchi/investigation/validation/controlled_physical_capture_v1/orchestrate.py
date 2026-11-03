"""Sequential bounded capture. Global 1800s admission budget; outer harness >=2400s.

SIGTERM/SIGINT request a cooperative stop, never interrupt a durable transaction.
No threads, subprocesses, retries or cancellation of an in-flight fsync.
"""
from contextlib import contextmanager
import argparse
import json
import math
from pathlib import Path
import signal
import time

from . import capture


class Budget:
    def __init__(self, seconds=1800, *, clock=time.monotonic, cleanup_seconds=60):
        if not math.isfinite(seconds) or not 0 < seconds <= 1800:
            raise ValueError('invalid_global_budget')
        self.clock = clock
        self.deadline = clock() + seconds
        self.cleanup_seconds = cleanup_seconds
        self.stop_requested = False

    def request_stop(self, *_):
        self.stop_requested = True

    def reason(self):
        return 'signal_stop_requested' if self.stop_requested else 'global_budget_exhausted'

    def can_start_query(self, pause=0):
        # Driver timeout + local persistence + verification/session/cleanup reserve.
        return not self.stop_requested and self.deadline - self.clock() > pause + 3 + 10 + self.cleanup_seconds

    def can_start_block(self):
        # Includes copying the cumulative prefix; rechecked after preparation.
        return not self.stop_requested and self.deadline - self.clock() > 180 + self.cleanup_seconds


@contextmanager
def cooperative_signals(budget):
    previous = {s: signal.getsignal(s) for s in (signal.SIGTERM, signal.SIGINT)}
    try:
        for s in previous:
            signal.signal(s, budget.request_stop)
        yield
    finally:
        for s, handler in previous.items():
            signal.signal(s, handler)


def run(source, control, *, max_blocks=5, seconds=1800, budget=None,
        runner=capture.run, sleep=time.sleep):
    if type(max_blocks) is not int or not 1 <= max_blocks <= 5:
        raise ValueError('invalid_block_budget')
    source, control = Path(source).resolve(), Path(control).resolve()
    if control.parent != capture.PRIVATE.resolve():
        raise ValueError('control_must_be_private')
    budget = budget or Budget(seconds)
    cp = capture.read_checkpoint(source)[0]
    if (source / 'pending.json').exists():
        raise RuntimeError('source_has_pending_commit')
    original = capture.file_inventory(source)
    control.mkdir(mode=0o700, exist_ok=False)
    report = dict(started_at=capture.utc(), origin=str(source), initial_rows=cp['rows'],
        global_seconds=seconds, cleanup_reserve_seconds=budget.cleanup_seconds,
        external_timeout_seconds=2400, blocks=[], rows=cp['rows'],
        last_valid_destination=str(source), checkpoint_sha256=capture.digest(source / 'checkpoint.json'),
        concurrency=1, retries=0, verdict='PARTIAL')
    capture.save(control / 'report.json', report)
    try:
        for number in range(1, max_blocks + 1):
            if not budget.can_start_block():
                report['reason'] = budget.reason()
                break
            if number > 1:
                sleep(30)
                if not budget.can_start_block():
                    report['reason'] = budget.reason()
                    break
            before = capture.file_inventory(source)
            base = capture.read_checkpoint(source)[0]
            destination = capture.PRIVATE / f'physical-capture-{control.name}-b{number:02d}'
            report['attempted_destination'] = str(destination)
            capture.save(control / 'report.json', report)
            state = runner(destination, resume=True, resume_from=source, budget=budget)
            try:
                verified, rows, seen, _ = capture.read_checkpoint(destination)
            except RuntimeError:
                report['verdict'] = 'FAIL'
                raise
            pending = (destination / 'pending.json').exists()
            integrity = (not pending and len(rows) == len(seen) and
                verified['batches'][:len(base['batches'])] == base['batches'] and
                before == capture.file_inventory(source) and
                state['cursor_opened'] == state['cursor_closed'])
            block = dict(block=number, destination=str(destination), queries=state['queries'],
                new_rows=verified['rows'] - base['rows'], rows=verified['rows'],
                sap_max_ms=max(state['durations_ms'], default=0),
                persistence_max_ms=max(state['persistence_ms'], default=0),
                checkpoint_sha256=capture.digest(destination / 'checkpoint.json'),
                connection_closed=state['connection_closed'], pending=pending,
                integrity='PASS' if integrity else 'FAIL', stop_reason=state.get('stop_reason'),
                session=state)
            report['blocks'].append(block)
            if not integrity:
                report.update(verdict='FAIL', reason='integrity_failure')
                break
            report.update(rows=verified['rows'], last_valid_destination=str(destination),
                          checkpoint_sha256=block['checkpoint_sha256'])
            capture.save(control / 'report.json', report)
            if (not state['connection_closed'] or
                state.get('stop_reason') not in ('query_budget_exhausted', 'eof') or
                block['sap_max_ms'] > 1500 or block['persistence_max_ms'] > 10000):
                report['reason'] = state.get('stop_reason', 'cleanup_not_certified')
                break
            source = destination
            if state['eof']:
                report.update(verdict='PASS', reason='eof')
                break
        else:
            report.update(verdict='PASS', reason='authorized_blocks_completed')
    except Exception as exc:
        report['reason'] = type(exc).__name__
        if isinstance(exc, capture.PersistenceBlocked):
            report['resource_block'] = str(exc)
    finally:
        origin = Path(report['origin'])
        report['original_unchanged'] = original == capture.file_inventory(origin)
        if not report['original_unchanged']:
            report.update(verdict='FAIL', reason='original_changed')
        report['finished_at'] = capture.utc()
        capture.save(control / 'report.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('control', type=Path)
    parser.add_argument('--seconds', type=float, default=1800)
    parser.add_argument('--max-blocks', type=int, default=5)
    args = parser.parse_args()
    budget = Budget(args.seconds)
    with cooperative_signals(budget):
        report = run(args.source, args.control, seconds=args.seconds,
                     max_blocks=args.max_blocks, budget=budget)
    print(json.dumps(report), flush=True)
    return 0 if report['verdict'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
