"""Synthetic device pressure/capacity tests; no physical writes or SAP."""
from types import SimpleNamespace
import pytest
from modules.telchi.investigation.validation.controlled_physical_capture_v1 import persistence as p


def test_sustained_target_pressure_blocks_even_without_global_iowait(tmp_path, monkeypatch):
    monkeypatch.setattr(p, 'capacity', lambda root: {})
    monkeypatch.setattr(p, 'device_for', lambda root: tmp_path)
    # Two intervals: busy 90%, average device queue 5. Global iowait unused.
    readings = iter([[0] * 11, [10, 0, 0, 100, 10, 0, 0, 100, 5, 900, 5000],
                     [20, 0, 0, 200, 20, 0, 0, 200, 5, 1800, 10000]])
    monkeypatch.setattr(p, 'counters', lambda device: next(readings))
    ticks = iter([0, 1, 2])
    with pytest.raises(p.PersistenceBlocked, match='sustained_pressure'):
        p.preflight(tmp_path, sleep=lambda _: None, clock=lambda: next(ticks))


def test_transient_target_pressure_not_sustained(tmp_path, monkeypatch):
    monkeypatch.setattr(p, 'capacity', lambda root: {})
    monkeypatch.setattr(p, 'device_for', lambda root: tmp_path)
    readings = iter([[0] * 11, [10, 0, 0, 100, 10, 0, 0, 100, 5, 900, 5000],
                     [20, 0, 0, 110, 20, 0, 0, 110, 0, 910, 5010]])
    monkeypatch.setattr(p, 'counters', lambda device: next(readings))
    ticks = iter([0, 1, 2])
    assert p.preflight(tmp_path, sleep=lambda _: None, clock=lambda: next(ticks))['sap_status'] == 'NOT_MEASURED'


@pytest.mark.parametrize('changes', [dict(f_bavail=0), dict(f_favail=0), dict(f_flag=p.os.ST_RDONLY)])
def test_capacity_fails_closed(tmp_path, monkeypatch, changes):
    values = dict(f_flag=0, f_bavail=100000, f_frsize=4096, f_favail=1000)
    monkeypatch.setattr(p.os, 'statvfs', lambda root: SimpleNamespace(**(values | changes)))
    with pytest.raises(p.PersistenceBlocked):
        p.capacity(tmp_path)


def test_slow_flush_and_stuck_queue():
    assert p.pressured(dict(await_ms=251, busy_fraction=.1, average_queue=1, inflight=0))
    assert p.pressured(dict(await_ms=0, busy_fraction=1, average_queue=9, inflight=9))
    assert not p.pressured(dict(await_ms=10, busy_fraction=.9, average_queue=1, inflight=0))


def test_flush_counters_included():
    before = [0] * 17
    after = [0] * 17
    after[15:17] = [2, 1000]
    assert p.interval(before, after, 1)['await_ms'] == 500


def test_probe_readback_failure(tmp_path):
    def save(path, value):
        path.write_bytes(b'wrong')
    with pytest.raises(p.PersistenceBlocked, match='readback_mismatch'):
        p.verify_probe(tmp_path, save, lambda path: 'wrong', lambda root: None)


def test_probe_does_not_hide_sync_error(tmp_path):
    def save(path, value):
        raise OSError('fsync failure')
    with pytest.raises(p.PersistenceBlocked, match='probe_write_failed'):
        p.verify_probe(tmp_path, save, lambda path: '', lambda root: None)


@pytest.mark.parametrize('seconds', [3, 5, 9.999, 10])
def test_successful_slow_probe(tmp_path, seconds):
    from .capture import save, digest, sync_directory
    ticks = iter([0, seconds])
    result = p.verify_probe(tmp_path, save, digest, sync_directory, clock=lambda: next(ticks))
    assert result['roundtrip_ms'] == seconds * 1000
    assert not (tmp_path / '.persistence-probe.json').exists()


def test_probe_latency_stops_before_sap(tmp_path):
    import hashlib
    ticks = iter([0, 10.001])
    def save(path, value):
        path.write_bytes(b'{"probe": "bounded-durable-roundtrip-v1"}\n')
    with pytest.raises(p.PersistenceBlocked, match='sync_latency'):
        p.verify_probe(tmp_path, save, lambda path: hashlib.sha256(path.read_bytes()).hexdigest(),
                       lambda root: None, clock=lambda: next(ticks))
    assert not (tmp_path / '.persistence-probe.json').exists()
