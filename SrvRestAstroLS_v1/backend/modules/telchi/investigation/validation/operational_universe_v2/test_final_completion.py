"""Offline final-authorization safety and exact remaining SQL coverage."""
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from . import final_completion as f, selective as s, transport
from .test_transport import Adapter, Clock
from ..controlled_physical_capture_v1 import capture as c
from ..controlled_physical_capture_v1.orchestrate import Budget


def prior_report():
    blocks = []
    for i in range(23):
        values = [.15]*5
        if i == 22:
            values[-1] = 1.7392748710008163
        blocks.append(dict(session=dict(queries=5, retries=0, connection_closed=True,
            cursors_opened=5, cursors_closed=5, hana_seconds=values,
            persistence_seconds=[.5]*5, status='PARTIAL' if i == 22 else 'BLOCKS_COMPLETE',
            reason='hana_latency_exceeded' if i == 22 else 'block_budget_exhausted')))
    return dict(blocks=blocks)


def test_offline_review_isolated_event():
    assert f.review(prior_report())['verdict'] == 'CONTINUATION_ALLOWED'


@pytest.mark.parametrize('fault', ['second_excess', 'nearby_slow', 'disconnect', 'retry', 'persistence'])
def test_review_refuses_other_anomalies(fault):
    prior = deepcopy(prior_report())
    state = prior['blocks'][-1]['session']
    if fault == 'second_excess':
        state['hana_seconds'][0] = 1.6
    elif fault == 'nearby_slow':
        state['hana_seconds'][2] = 1.2
    elif fault == 'disconnect':
        state['connection_closed'] = False
    elif fault == 'retry':
        state['retries'] = 1
    else:
        state['persistence_seconds'][0] = 11
    with pytest.raises(RuntimeError):
        f.review(prior)


@pytest.fixture
def final_chain(tmp_path, monkeypatch):
    monkeypatch.setattr(s, 'PRIVATE', tmp_path)
    monkeypatch.setattr(c, 'PRIVATE', tmp_path)
    source, prior, origin = [tmp_path/n for n in ('physical-selective-source', 'physical-selective-prior', 'physical-selective-micro')]
    for p in (source, prior, origin):
        p.mkdir()
    plan = s.plan_for([f'K{i:05}' for i in range(3242)])
    s.initialize(source, plan)
    for i in range(120):
        s.reserve_request(source, plan, i, reserved_at='test')
        s.commit_response(source, plan, i, [dict(ItemCode=k, U_FormaFarmac='0')
            for k in plan['batches'][i]['parameters']], observed_at='test', fetch_complete=True)
    c.save(prior/'report.json', prior_report())
    monkeypatch.setattr(f, 'SOURCE', source)
    monkeypatch.setattr(f, 'SOURCE_SHA', c.digest(source/'checkpoint.json'))
    monkeypatch.setattr(f, 'PRIOR_SHA', c.digest(prior/'report.json'))
    monkeypatch.setattr(f, 'CONTROL', tmp_path/'physical-selective-final')
    monkeypatch.setattr(f.continuation, 'ORIGIN', origin)
    monkeypatch.setattr(f.continuation, 'CONTROL', prior)
    monkeypatch.setattr(f, 'verify_source', lambda plan, _: s.read_state(source, plan))
    monkeypatch.setattr(transport, 'validate_origin', lambda: plan)
    monkeypatch.setattr(f.persistence, 'preflight', lambda _: {})
    clock = Clock()
    monkeypatch.setattr(f, 'time', SimpleNamespace(monotonic=clock))
    monkeypatch.setattr(f, 'Budget', lambda _: Budget(clock=clock))
    adapters = []
    original_run = transport.run
    def run(mode='ok'):
        def connect():
            assert all(a.connection_closed for a in adapters)
            a = Adapter(clock, mode)
            adapters.append(a)
            return a
        def bounded(*args, **kwargs):
            return original_run(*args, **kwargs, connect_factory=connect, clock=clock,
                sleep=clock.sleep, preflight=lambda _: {}, probe=lambda *_: {})
        monkeypatch.setattr(transport, 'run', bounded)
        return f.run(authorize=True)
    monkeypatch.setattr(c, 'connect_hana', lambda: pytest.fail('REAL_HANA_FORBIDDEN'))
    return run, adapters, plan, source, clock


def test_exact_final_242_once_with_two_closed_blocks(final_chain):
    run, adapters, plan, source, clock = final_chain
    before = c.file_inventory(source)
    result = run()
    assert result['verdict'] == 'PASS' and result['additional_selects'] == 10
    assert c.file_inventory(source) == before and result['prior_captures_unchanged']
    calls = [call for a in adapters for call in a.calls]
    assert calls == [(b['sql'], b['parameters']) for b in plan['batches'][120:]]
    assert sum(len(params) for _, params in calls) == 242 and len(calls[-1][1]) == 17
    assert all(a.connection_closed and a.opened == a.closed == 5 for a in adapters)
    assert clock.pauses == [30, 10, 10, 10, 10]*2
    with pytest.raises(RuntimeError, match='one_shot_control'):
        run()
    assert len(adapters) == 2


@pytest.mark.parametrize('mode', ['slow', 'disconnect', 'timeout', 'unexpected'])
def test_final_anomaly_never_starts_next_block_or_retries(final_chain, mode):
    run, adapters, _, source, _ = final_chain
    before = c.file_inventory(source)
    result = run(mode)
    assert result['verdict'] == 'PARTIAL' and result['additional_selects'] == 1
    assert len(adapters) == 1 and adapters[0].connection_closed
    assert c.file_inventory(source) == before
    with pytest.raises(RuntimeError, match='one_shot_control'):
        run()
    assert len(adapters) == 1
