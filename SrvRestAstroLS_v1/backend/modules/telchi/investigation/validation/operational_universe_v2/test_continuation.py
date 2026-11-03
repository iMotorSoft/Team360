"""Offline immutable continuation, failure admission and lifecycle tests."""
import multiprocessing
import signal

import pytest

from . import continuation as n, selective as s
from .test_transport import Adapter, Clock, Cursor, lock_child
from ..controlled_physical_capture_v1 import capture as c
from ..controlled_physical_capture_v1.orchestrate import Budget, cooperative_signals


@pytest.fixture
def chain(tmp_path, monkeypatch):
    monkeypatch.setattr(s, 'PRIVATE', tmp_path)
    monkeypatch.setattr(c, 'connect_hana', lambda: pytest.fail('REAL_HANA_FORBIDDEN'))
    origin, control = tmp_path/'micro', tmp_path/'control'
    plan = s.plan_for([f'K{i:05}' for i in range(3242)])
    origin.mkdir()
    with c.destination_lock(origin):
        s.initialize(origin, plan)
        for i in range(5):
            s.reserve_request(origin, plan, i, reserved_at='observed')
            s.commit_response(origin, plan, i,
                [dict(ItemCode=k, U_FormaFarmac='0') for k in plan['batches'][i]['parameters']],
                observed_at='observed', fetch_complete=True)
    expected = c.digest(origin/'checkpoint.json')
    before = c.file_inventory(origin)
    clock = Clock()
    adapters = []
    def run(mode='ok', factory=None, **kwargs):
        def connect():
            assert all(a.connection_closed for a in adapters)
            adapter = factory() if factory else Adapter(clock, mode)
            adapters.append(adapter)
            return adapter
        return n.cycle(origin, control, plan, expected_origin_sha=expected,
            clock=clock, sleep=clock.sleep, connect_factory=connect,
            preflight=kwargs.pop('preflight', lambda _: {}), probe=lambda *_: {},
            budget=kwargs.pop('budget', Budget(clock=clock)), **kwargs)
    return origin, control, plan, clock, adapters, before, run


def test_exact_25_block_chain_all_destinations_frozen_and_last_17(chain):
    origin,control,plan,clock,adapters,before,run = chain
    snapshots = {}
    for i in range(7):
        report = run()
        assert report['status'] == ('COMPLETE' if i == 6 else 'CYCLE_COMPLETE')
        for root, inventory in snapshots.items():
            assert c.file_inventory(root) == inventory
        for entry in report['history']:
            from pathlib import Path
            snapshots[Path(entry['destination'])] = entry['inventory']
    assert report['queries'] == 125 and report['completed'] == 130
    assert len(report['blocks']) == len(adapters) == 25
    assert len({x['destination'] for x in report['history']}) == 26
    assert c.file_inventory(origin) == before
    calls = [call for a in adapters for call in a.calls]
    assert calls == [(b['sql'], b['parameters']) for b in plan['batches'][5:]]
    keys = [k for _,params in calls for k in params]
    assert len(keys) == len(set(keys)) == 3117
    assert not set(keys) & set(plan['item_codes'][:125])
    assert len(calls[-1][1]) == 17
    assert all(a.connection_closed and a.opened == a.closed == 5 for a in adapters)
    assert clock.pauses == [pause for _ in range(25) for pause in [30,10,10,10,10]]
    assert all(x['duration_seconds'] < 1800 for x in report['cycles'])
    root = next(reversed(snapshots))
    with c.destination_lock(root):
        cp = s.recover(root, plan)
        inventory = c.file_inventory(root)
        assert cp == s.recover(root, plan)
        assert c.file_inventory(root) == inventory
    # Completion is idempotent and opens no new connection.
    assert run()['queries'] == 125 and len(adapters) == 25


@pytest.mark.parametrize('mode', ['timeout', 'disconnect', 'interrupt', 'slow', 'unexpected'])
def test_query_anomalies_close_and_inhibit_future_cycles(chain, mode):
    origin,control,plan,_,adapters,before,run = chain
    result = run(mode)
    assert result['status'] == 'PARTIAL' and result['completed'] == 5
    assert result['queries'] == 1 and result['prior_integrity'] == 'PASS'
    assert adapters[0].connection_closed and adapters[0].opened == adapters[0].closed == 1
    assert c.file_inventory(origin) == before
    from pathlib import Path
    root = Path(result['attempt'])
    with c.destination_lock(root):
        cp = s.recover(root, plan)
    assert len(cp['batches']) == (6 if mode == 'slow' else 5)
    with pytest.raises(RuntimeError, match='previous_attempt'):
        run()
    assert len(adapters) == 1


@pytest.mark.parametrize('stage', ['after_journal', 'after_checkpoint', 'slow_persistence'])
def test_persistence_failure_preserves_recovery_without_requery(chain, monkeypatch, stage):
    origin,_,plan,clock,adapters,before,run = chain
    original = s.save
    triggered = False
    def fault(path, value):
        nonlocal triggered
        original(path, value)
        target = 'pending.json' if stage == 'after_journal' else 'checkpoint.json'
        if path.name == target and path.parent != origin and not triggered:
            triggered = True
            if stage == 'slow_persistence':
                clock.now += 10.1
            else:
                raise OSError('injected_durable_failure')
    monkeypatch.setattr(s, 'save', fault)
    result = run()
    assert result['status'] == 'PARTIAL' and result['queries'] == 1
    assert adapters[0].connection_closed and adapters[0].closed == 1
    monkeypatch.setattr(s, 'save', original)
    from pathlib import Path
    root = Path(result['attempt'])
    with c.destination_lock(root):
        cp = s.recover(root, plan)
        assert len(cp['batches']) == 6
        snapshot = c.file_inventory(root)
        assert s.recover(root, plan) == cp and c.file_inventory(root) == snapshot
    assert c.file_inventory(origin) == before
    with pytest.raises(RuntimeError, match='previous_attempt'):
        run()
    assert len(adapters) == 1


def test_slow_fifth_query_is_durable_but_never_authorizes_next_block(chain):
    origin,_,plan,clock,adapters,before,run = chain
    class SlowFifth(Adapter):
        def cursor(self):
            self.mode = 'slow' if self.opened == 4 else 'ok'
            return super().cursor()
    result = run(factory=lambda: SlowFifth(clock))
    assert result['status'] == 'PARTIAL' and result['queries'] == 5
    assert result['completed'] == 5  # Last fully certified ancestor.
    assert result['blocks'][-1]['completed'] == 10  # Latest durable ledger.
    from pathlib import Path
    latest = Path(result['attempt'])
    with c.destination_lock(latest):
        assert len(s.recover(latest, plan)['batches']) == 10
        snapshot = c.file_inventory(latest)
        assert len(s.recover(latest, plan)['batches']) == 10
        assert snapshot == c.file_inventory(latest)
        with pytest.raises(RuntimeError, match='source_session_not_certified'):
            n.clean_state(latest, plan)
    assert adapters[0].connection_closed and adapters[0].opened == adapters[0].closed == 5
    assert c.file_inventory(origin) == before
    with pytest.raises(RuntimeError, match='previous_attempt'):
        run()
    assert len(adapters) == 1


def test_cooperative_signal_during_fetch_finishes_commit_and_closes(chain):
    origin,_,plan,clock,adapters,before,run = chain
    budget = Budget(clock=clock)
    class StopCursor(Cursor):
        def fetchall(self):
            signal.raise_signal(signal.SIGTERM)
            return super().fetchall()
    class StopAdapter(Adapter):
        def cursor(self):
            self.opened += 1
            return StopCursor(self)
    previous = signal.getsignal(signal.SIGTERM)
    with cooperative_signals(budget):
        result = run(factory=lambda: StopAdapter(clock), budget=budget)
    assert signal.getsignal(signal.SIGTERM) == previous
    assert result['status'] == 'PARTIAL' and result['queries'] == 1
    assert adapters[0].connection_closed and adapters[0].opened == adapters[0].closed == 1
    from pathlib import Path
    with c.destination_lock(Path(result['attempt'])):
        assert len(s.recover(Path(result['attempt']), plan)['batches']) == 6
    assert c.file_inventory(origin) == before


def test_stop_before_first_block_does_not_connect(chain):
    _,_,_,clock,adapters,_,run = chain
    budget = Budget(clock=clock)
    budget.request_stop()
    assert run(budget=budget)['status'] == 'PARTIAL'
    assert not adapters


def test_connection_close_failure_stops_next_block(chain):
    _,_,_,clock,adapters,_,run = chain
    class BadClose(Adapter):
        def close(self):
            raise ConnectionError('injected')
    result = run(factory=lambda: BadClose(clock))
    assert result['status'] == 'PARTIAL' and len(adapters) == 1
    assert len(result['blocks']) == 1 and not result['blocks'][0]['session']['connection_closed']
    with pytest.raises(RuntimeError, match='previous_attempt'):
        run()


def test_cursor_close_failure_stops_next_query(chain):
    _,_,_,clock,adapters,_,run = chain
    class BadCursor(Cursor):
        def close(self):
            raise ConnectionError('injected')
    class BadAdapter(Adapter):
        def cursor(self):
            self.opened += 1
            return BadCursor(self)
    result = run(factory=lambda: BadAdapter(clock))
    assert result['status'] == 'PARTIAL' and result['queries'] == 1
    assert adapters[0].connection_closed and adapters[0].closed == 0


def test_global_origin_lock_excludes_other_process_even_after_first_cycle(chain):
    origin,_,_,_,adapters,_,run = chain
    run(max_blocks=1)
    context = multiprocessing.get_context('spawn')
    queue = context.Queue()
    with c.destination_lock(origin):
        process = context.Process(target=lock_child, args=(str(origin), queue))
        process.start()
        try:
            assert queue.get(timeout=10) == 'capture_already_running'
            with pytest.raises(RuntimeError, match='capture_already_running'):
                run()
        finally:
            process.join(timeout=10)
            if process.is_alive():
                process.terminate(); process.join(timeout=5)
            queue.close(); queue.join_thread()
        assert process.exitcode == 0
    assert len(adapters) == 1


def test_existing_destination_never_overwritten(chain):
    origin,control,_,_,adapters,_,run = chain
    root = control.parent/f'{control.name}-b01'
    root.mkdir()
    (root/'preserve').write_bytes(b'untouched')
    result = run()
    assert result['status'] == 'PARTIAL' and not adapters
    assert (root/'preserve').read_bytes() == b'untouched'


def test_ancestor_corruption_blocks_before_connect(chain):
    origin,_,_,_,adapters,_,run = chain
    run(max_blocks=1)
    (origin/'selective-000000.json').write_text('{}')
    with pytest.raises(RuntimeError, match='hash_mismatch'):
        run()
    assert len(adapters) == 1


def test_other_control_cannot_fork_same_origin(chain):
    origin,control,plan,_,adapters,_,run = chain
    run(max_blocks=1)
    with pytest.raises(RuntimeError, match='other_continuation_control'):
        n.cycle(origin, control.parent/'other', plan,
                expected_origin_sha=c.digest(origin/'checkpoint.json'), preflight=lambda _: {})
    assert len(adapters) == 1


def test_prefix_persistence_budget_stops_before_connection(chain, monkeypatch):
    _,_,_,clock,adapters,_,run = chain
    seed = n.seed
    def slow(*args):
        seed(*args)
        clock.now += 10.1
    monkeypatch.setattr(n, 'seed', slow)
    result = run()
    assert result['status'] == 'PARTIAL' and not adapters
    assert result['stop_detail'] == 'prefix_persistence_budget_exceeded'
