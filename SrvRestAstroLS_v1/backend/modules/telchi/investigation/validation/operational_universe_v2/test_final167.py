"""Offline exact seven-SELECT authorization and stop/closure regression."""
from types import SimpleNamespace

import pytest

from . import final167 as f, selective as s, transport
from .test_final_completion import final_chain
from .test_transport import Adapter
from ..controlled_physical_capture_v1 import capture as c
from ..controlled_physical_capture_v1.orchestrate import Budget


@pytest.fixture
def chain167(final_chain, monkeypatch, tmp_path):
    _, adapters, plan, source, clock = final_chain
    for i in range(120, 123):
        s.reserve_request(source, plan, i, reserved_at='test')
        s.commit_response(source, plan, i, [dict(ItemCode=k, U_FormaFarmac='0')
            for k in plan['batches'][i]['parameters']], observed_at='test', fetch_complete=True)
    f.previous.CONTROL.mkdir()
    ancestor = tmp_path/'physical-selective-ancestor120'
    ancestor.mkdir()
    monkeypatch.setattr(f.previous, 'SOURCE', ancestor)
    monkeypatch.setattr(f, 'SOURCE', source)
    monkeypatch.setattr(f, 'SOURCE_SHA', c.digest(source/'checkpoint.json'))
    monkeypatch.setattr(f, 'CONTROL', tmp_path/'physical-selective-final167')
    monkeypatch.setattr(f, 'review_source', lambda _: (s.read_state(source, plan), {}))
    monkeypatch.setattr(f, 'time', SimpleNamespace(monotonic=clock))
    monkeypatch.setattr(f, 'Budget', lambda _: Budget(clock=clock))
    original = transport.run

    def run(*, slow_at=None, mode='ok'):
        calls = 0
        def connect():
            assert all(a.connection_closed for a in adapters)
            a = Adapter(clock, mode)
            original_cursor = a.cursor
            def cursor():
                nonlocal calls
                calls += 1
                a.mode = 'slow' if calls == slow_at else mode
                return original_cursor()
            a.cursor = cursor
            adapters.append(a)
            return a
        def bounded(*args, **kwargs):
            return original(*args, **kwargs, connect_factory=connect, clock=clock,
                sleep=clock.sleep, preflight=lambda _: {}, probe=lambda *_: {})
        monkeypatch.setattr(transport, 'run', bounded)
        return f.run(authorize=True)
    return run, adapters, plan, source, clock


def test_exact_167_two_then_five_queries(chain167):
    run, adapters, plan, source, clock = chain167
    before = c.file_inventory(source)
    report = run()
    assert report['verdict'] == 'PASS' and report['additional_selects'] == 7
    assert [b['session']['queries'] for b in report['blocks']] == [2, 5]
    calls = [call for a in adapters for call in a.calls]
    assert calls == [(b['sql'], b['parameters']) for b in plan['batches'][123:]]
    assert [len(params) for _, params in calls] == [25]*6+[17]
    assert [a.opened for a in adapters] == [2, 5]
    assert all(a.connection_closed and a.opened == a.closed for a in adapters)
    assert clock.pauses == [30, 10, 30, 10, 10, 10, 10]
    assert c.file_inventory(source) == before and report['prior_captures_unchanged']
    with pytest.raises(RuntimeError, match='one_shot_control'):
        run()
    assert len(adapters) == 2


@pytest.mark.parametrize('slow_at', range(1, 8))
def test_any_slow_query_persisted_without_later_select(chain167, slow_at):
    run, adapters, _, source, _ = chain167
    before = c.file_inventory(source)
    report = run(slow_at=slow_at)
    assert report['verdict'] == 'PARTIAL'
    assert report['additional_selects'] == slow_at
    assert sum(len(a.calls) for a in adapters) == slow_at
    assert all(a.connection_closed and a.opened == a.closed for a in adapters)
    assert c.file_inventory(source) == before
    with pytest.raises(RuntimeError, match='one_shot_control'):
        run()


@pytest.mark.parametrize('mode', ['disconnect', 'timeout', 'unexpected'])
def test_uncertain_response_never_retried(chain167, mode):
    run, adapters, _, _, _ = chain167
    report = run(mode=mode)
    assert report['verdict'] == 'PARTIAL' and report['additional_selects'] == 1
    assert len(adapters) == 1 and adapters[0].connection_closed
    with pytest.raises(RuntimeError, match='one_shot_control'):
        run()
