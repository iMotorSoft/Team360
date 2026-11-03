"""Offline deadline, signal and isolated interrupted-write recovery regressions."""
import json
import signal

import pytest

from . import capture, orchestrate
from .test_capture import FakeConnection, inventory, no_live_hana, seed


def test_exhausted_before_block_never_calls_runner(tmp_path):
    source = seed(tmp_path / 'source')
    now = [0]
    budget = orchestrate.Budget(clock=lambda: now[0])
    now[0] = 1800
    def forbidden(*a, **k):
        pytest.fail('runner started after deadline')
    report = orchestrate.run(source, tmp_path / 'control', budget=budget, runner=forbidden)
    assert report['blocks'] == [] and report['rows'] == 200
    assert report['reason'] == 'global_budget_exhausted' and report['original_unchanged']


@pytest.mark.parametrize('stop', ['deadline', 'signal'])
def test_stop_between_queries_finishes_commit_and_cleanup(tmp_path, monkeypatch, stop):
    now = [0]
    budget = orchestrate.Budget(clock=lambda: now[0])
    real = capture.save
    def save(path, value):
        real(path, value)
        if path.name == 'batch-0001.json':
            if stop == 'signal':
                budget.request_stop()
            else:
                now[0] = 1801
    monkeypatch.setattr(capture, 'save', save)
    conn = FakeConnection()
    result = capture.run(tmp_path / 'new', connect_factory=lambda: conn,
                         sleep=lambda _: None, budget=budget)
    assert result['queries'] == result['batches'] == 1
    assert result['rows'] == 25 and result['connection_closed'] and conn.closed
    assert result['cursor_closed'] == result['cursor_opened'] == 1
    assert result['stop_reason'] == budget.reason()
    assert capture.read_checkpoint(tmp_path / 'new')[0]['rows'] == 25
    assert not (tmp_path / 'new/pending.json').exists()


def test_budget_expired_during_preparation_no_connection(tmp_path):
    budget = orchestrate.Budget(seconds=1)
    def forbidden():
        pytest.fail('connection opened without query budget')
    state = capture.run(tmp_path / 'new', connect_factory=forbidden, budget=budget)
    assert state['queries'] == state['connection_attempts'] == 0
    assert state['stop_reason'] == 'global_budget_exhausted'
    assert 'finished_at' in state


@pytest.mark.parametrize('corrupt', [False, True])
def test_complete_tmp_recovery_isolated_and_idempotent(tmp_path, monkeypatch, corrupt):
    source = seed(tmp_path / 'source')
    real = capture.save
    def interrupted(path, value):
        if path.name == 'batch-0003.json':
            path.with_suffix('.json.tmp').write_bytes(capture.encoded(value))
            raise KeyboardInterrupt()
        real(path, value)
    monkeypatch.setattr(capture, 'save', interrupted)
    conn = FakeConnection()
    capture.run(source, resume=True, connect_factory=lambda: conn, sleep=lambda _: None)
    assert conn.closed
    monkeypatch.setattr(capture, 'save', real)
    if corrupt:
        (source / 'batch-0003.json.tmp').write_bytes(b'truncated')
    before = inventory(source)
    target = tmp_path / 'recovered'
    if corrupt:
        with pytest.raises(RuntimeError, match='tmp_hash_mismatch'):
            capture.recover_isolated(source, target)
    else:
        evidence = capture.recover_isolated(source, target)
        assert evidence['rows'] == evidence['unique_rows'] == 225
        assert evidence['adopted_tmp'] and evidence['idempotent']
        assert not (target / 'pending.json').exists()
        with capture.destination_lock(target):
            a = inventory(target)
            capture.recover_pending(target)
            assert a == inventory(target)
        assert capture.read_checkpoint(target)[3] == '000224'
    assert before == inventory(source)


def test_signal_handler_only_sets_flag_and_restores():
    budget = orchestrate.Budget()
    original = signal.getsignal(signal.SIGTERM)
    with orchestrate.cooperative_signals(budget):
        signal.raise_signal(signal.SIGTERM)
        assert budget.stop_requested and not budget.can_start_block()
        assert not budget.can_start_query()
    assert signal.getsignal(signal.SIGTERM) == original


def test_sequential_blocks_validate_before_next_and_preserve_prefix(tmp_path):
    source = seed(tmp_path / 'source')
    conns = []
    pauses = []
    def runner(root, **kwargs):
        conn = FakeConnection()
        conns.append(conn)
        assert all(c.closed for c in conns[:-1])
        return capture.run(root, connect_factory=lambda: conn, sleep=lambda _: None, **kwargs)
    report = orchestrate.run(source, tmp_path / 'control', max_blocks=2,
                             runner=runner, sleep=pauses.append)
    assert report['verdict'] == 'PASS' and report['rows'] == 450
    assert pauses == [30] and len(conns) == 2
    assert [b['new_rows'] for b in report['blocks']] == [125, 125]
    assert all(b['integrity'] == 'PASS' and b['connection_closed'] for b in report['blocks'])
    assert conns[1].calls[0][1] == ('000324',)


def test_failure_never_starts_another_block(tmp_path):
    source = seed(tmp_path / 'source')
    calls = []
    def runner(root, **kwargs):
        calls.append(root)
        return capture.run(root, connect_factory=lambda: FakeConnection(error=ValueError), **kwargs)
    report = orchestrate.run(source, tmp_path / 'control', runner=runner)
    assert len(calls) == 1 and report['verdict'] == 'PARTIAL'
    assert report['blocks'][0]['connection_closed']
