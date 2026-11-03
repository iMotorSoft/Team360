"""Synthetic-only, no HANA driver/config imported and no external services."""
import hashlib
import json
import multiprocessing
import pytest
from modules.telchi.investigation.validation.controlled_physical_capture_v1 import capture


def inventory(root):
    return {str(p.relative_to(root)): capture.digest(p) for p in root.rglob('*') if p.is_file()}


def seed(root, batches=2, size=100):
    root.mkdir()
    cp = dict(last_key=None, rows=0, batches=[])
    for number in range(batches):
        rows = [{'ItemCode': f'{i:06d}', 'U_FormaFarmac': '4'}
                for i in range(number * size, (number + 1) * size)]
        name = f'batch-{number + 1:04d}.json'
        capture.save(root / name, dict(observed_at='2026-01-01T00:00:00+00:00', rows=rows))
        cp['batches'].append(dict(file=name, sha256=capture.digest(root / name), rows=size,
            query_sha256=hashlib.sha256(capture.query(size, number > 0).encode()).hexdigest()))
        cp.update(rows=(number + 1) * size, last_key=rows[-1]['ItemCode'])
    capture.save(root / 'checkpoint.json', cp)
    capture.save(root / 'operation.json', dict(started_at='2026-01-01', finished_at='2026-01-01'))
    return root


class FakeConnection:
    def __init__(self, *, error=None, malformed=None, end=10000):
        self.calls, self.cursors = [], []
        self.closed = False
        self.error, self.malformed, self.end = error, malformed, end

    def cursor(self):
        conn = self
        class Cursor:
            description = [('ItemCode',), ('U_FormaFarmac',)]
            closed = False
            def setquerytimeout(self, seconds):
                assert seconds == 3
            def execute(self, sql, params):
                conn.calls.append((sql, params))
                assert 'OFFSET' not in sql
                assert 1 <= int(sql.split()[2]) <= 25
                assert ('WHERE "ItemCode" > ?' in sql) == bool(params)
                if conn.error:
                    raise conn.error('sensitive driver message')
            def fetchall(self):
                sql, params = conn.calls[-1]
                start = int(params[0]) + 1 if params else 0
                limit = int(sql.split()[2])
                result = [(f'{i:06d}', '4') for i in range(start, min(start + limit, conn.end))]
                return conn.malformed(result, params) if conn.malformed else result
            def close(self):
                self.closed = True
        cur = Cursor()
        self.cursors.append(cur)
        return cur

    def close(self):
        self.closed = True


@pytest.fixture(autouse=True)
def no_live_hana(monkeypatch, tmp_path):
    monkeypatch.setattr(capture, 'PRIVATE', tmp_path)
    monkeypatch.setattr(capture, 'destination_preflight', lambda root: {'synthetic': True})
    # Crash tests exercise atomic rename/journal boundaries, not physical power loss.
    # Avoid hundreds of real device flushes on the shared development disk.
    monkeypatch.setattr(capture.os, 'fsync', lambda fd: None)
    def forbidden():
        pytest.fail('Live HANA connector must never be invoked')
    monkeypatch.setattr(capture, 'connect_hana', forbidden)


def execute(root, conn=None, **kwargs):
    conn = conn or FakeConnection()
    pauses = []
    ticks = iter(range(100))
    result = capture.run(root, connect_factory=lambda: conn, sleep=pauses.append,
                         clock=lambda: next(ticks) * .01, **kwargs)
    assert conn.closed and all(c.closed for c in conn.cursors)
    assert result['cursor_opened'] == result['cursor_closed']
    return conn, result, pauses


def test_legacy_4400_fork_resume_no_repeats_sessions(tmp_path):
    original = seed(tmp_path / 'original', batches=44)
    before = inventory(original)
    target = tmp_path / 'continued'
    conn, state, pauses = execute(target, resume=True, resume_from=original)
    assert state['queries'] == state['batches'] == 5
    assert state['rows'] == 4525 and state['initial_rows'] == 4400
    assert conn.calls[0] == (capture.query(25, True), ('004399',))
    assert [params[0] for _, params in conn.calls] == ['004399', '004424', '004449', '004474', '004499']
    assert pauses == [10] * 4
    rows, seen, last = capture.recover(target)
    assert len(rows) == len(seen) == 4525 and last == '004524'
    assert [r['ItemCode'] for r in rows] == [f'{i:06d}' for i in range(4525)]
    assert inventory(original) == before
    for name in before:
        if name != 'checkpoint.json':
            assert capture.digest(target / name) == before[name]
    first_session = inventory(target / 'sessions')
    _, state2, _ = execute(target, resume=True)
    assert state2['initial_rows'] == 4525 and state2['rows'] == 4650
    assert len(list((target / 'sessions').glob('*.json'))) == 2
    assert all(inventory(target / 'sessions')[k] == v for k, v in first_session.items())
    cp = json.loads((target / 'checkpoint.json').read_text())
    assert len({e['session_id'] for e in cp['batches'][44:]}) == 2
    assert all(json.loads((target / e['file']).read_text())['observed_at'] for e in cp['batches'])
    assert state['consistency'] == capture.CONSISTENCY
    assert inventory(original) == before


def test_fresh_defaults_and_eof(tmp_path):
    conn, state, pauses = execute(tmp_path / 'new', FakeConnection(end=51))
    assert state['queries'] == 3 and state['rows'] == 51 and state['eof']
    assert conn.calls[0] == (capture.query(25), ())
    assert pauses == [10, 10]


@pytest.mark.parametrize('error', [ValueError, RuntimeError, KeyboardInterrupt])
def test_error_no_retries_and_cleanup(tmp_path, error):
    conn, state, pauses = execute(tmp_path / 'new', FakeConnection(error=error))
    assert state['queries'] == 1 and state['batches'] == state['rows'] == 0
    assert state['retries'] == 0 and state['connection_attempts'] == 1 and pauses == []
    assert len(conn.calls) == 1
    assert 'sensitive' not in json.dumps(state)


def test_latency_stops_after_saving_inflight_result(tmp_path):
    ticks = iter([0, 1.501])
    conn = FakeConnection()
    pauses = []
    state = capture.run(tmp_path / 'new', connect_factory=lambda: conn,
        clock=lambda: next(ticks), sleep=pauses.append)
    assert state['queries'] == 1 and state['rows'] == 25
    assert state['stop_reason'] == 'latency_threshold_exceeded' and pauses == []
    assert len(capture.recover(tmp_path / 'new')[0]) == 25
    assert conn.closed and all(c.closed for c in conn.cursors)


@pytest.mark.parametrize('mutation', ['hash', 'last', 'count', 'path', 'query', 'version', 'json', 'overlap', 'oversize'])
def test_corrupt_or_incompatible_checkpoint_rejected_before_connect(tmp_path, mutation):
    root = seed(tmp_path / 'old')
    cp = json.loads((root / 'checkpoint.json').read_text())
    if mutation == 'hash':
        (root / 'batch-0001.json').write_text('{}')
    elif mutation == 'last':
        cp['last_key'] = 'bogus'
    elif mutation == 'count':
        cp['rows'] += 1
    elif mutation == 'path':
        cp['batches'][0]['file'] = '../outside.json'
    elif mutation == 'query':
        cp['batches'][0]['query_sha256'] = 'wrong'
    elif mutation == 'version':
        cp['version'] = 999
    elif mutation in ('overlap', 'oversize'):
        path = root / 'batch-0002.json'
        batch = json.loads(path.read_text())
        batch['rows'] = batch['rows'] + batch['rows'] if mutation == 'oversize' else json.loads((root / 'batch-0001.json').read_text())['rows']
        capture.save(path, batch)
        cp['batches'][1]['sha256'] = capture.digest(path)
    capture.save(root / 'checkpoint.json', cp)
    if mutation == 'json':
        (root / 'checkpoint.json').write_text('{')
    with pytest.raises(RuntimeError):
        capture.run(root, resume=True)


@pytest.mark.parametrize('keys,last,seen', [(['A','A'],None,set()), (['B','A'],None,set()), (['A'],'A',set()), (['A'],None,{'A'}), ([''],None,set())])
def test_reject_bad_keys(keys, last, seen):
    with pytest.raises(RuntimeError):
        capture.validate([{'ItemCode': k, 'U_FormaFarmac': '4'} for k in keys], last, seen)


@pytest.mark.parametrize('malformed', [lambda rows,p: [(p[0], '4')] + rows[1:],
    lambda rows,p: rows[::-1], lambda rows,p: rows + [('999999', '4')]])
def test_invalid_query_result_never_committed(tmp_path, malformed):
    root = seed(tmp_path / 'old')
    before = capture.digest(root / 'checkpoint.json')
    conn, state, pauses = execute(root, FakeConnection(malformed=malformed), resume=True)
    assert state['queries'] == 1 and state['batches'] == 0 and not pauses
    assert capture.digest(root / 'checkpoint.json') == before
    assert not (root / 'pending.json').exists()


@pytest.mark.parametrize('point', ['before_batch', 'after_batch', 'after_checkpoint'])
def test_interruption_recovery_idempotent(tmp_path, monkeypatch, point):
    root = seed(tmp_path / 'old')
    prefix = {p.name: capture.digest(p) for p in root.glob('batch-*.json')}
    real_save = capture.save
    def crash(path, value):
        if point == 'before_batch' and path.name == 'batch-0003.json':
            raise KeyboardInterrupt()
        real_save(path, value)
        if point == 'after_batch' and path.name == 'batch-0003.json':
            raise KeyboardInterrupt()
        if point == 'after_checkpoint' and path.name == 'checkpoint.json':
            raise KeyboardInterrupt()
    monkeypatch.setattr(capture, 'save', crash)
    _, state, _ = execute(root, resume=True)
    assert state['queries'] == 1 and (root / 'pending.json').exists()
    monkeypatch.setattr(capture, 'save', real_save)
    with capture.destination_lock(root):
        cp, _, _, last = capture.recover_pending(root)
        first = inventory(root)
        assert capture.recover_pending(root)[0] == cp
        assert inventory(root) == first
    expected = 200 if point == 'before_batch' else 225
    assert cp['rows'] == expected and last == f'{expected - 1:06d}'
    conn, state, _ = execute(root, resume=True, max_queries=1)
    assert conn.calls[0][1] == (last,)
    rows, seen, _ = capture.recover(root)
    assert len(rows) == len(seen) == expected + 25
    assert all(capture.digest(root / k) == v for k, v in prefix.items())


def lock_worker(root, pipe):
    try:
        with capture.destination_lock(root):
            pipe.send('unexpected_lock')
    except RuntimeError as exc:
        pipe.send(str(exc))
    finally:
        pipe.close()


def test_cross_process_exclusive_lock(tmp_path):
    root = seed(tmp_path / 'old')
    ctx = multiprocessing.get_context('spawn')
    parent, child = ctx.Pipe()
    with capture.destination_lock(root):
        proc = ctx.Process(target=lock_worker, args=(root, child))
        proc.start()
        try:
            assert parent.poll(5)
            assert parent.recv() == 'capture_already_running'
        finally:
            proc.join(5)
            assert not proc.is_alive() and proc.exitcode == 0
            child.close(); parent.close()
    with capture.destination_lock(root):
        pass


@pytest.mark.parametrize('kwargs', [dict(batch_size=26), dict(max_queries=6), dict(pause_seconds=9),
    dict(latency_seconds=2), dict(pause_seconds=float('nan')), dict(latency_seconds=0)])
def test_unsafe_controls_rejected(tmp_path, kwargs):
    with pytest.raises(RuntimeError, match='unsafe_controls'):
        capture.run(tmp_path / 'new', **kwargs)
    assert not (tmp_path / 'new').exists()


def test_explicit_resume_required(tmp_path):
    root = seed(tmp_path / 'old')
    before = inventory(root)
    with pytest.raises(FileExistsError):
        capture.run(root)
    assert inventory(root) == before


def test_connection_failure_not_retried(tmp_path):
    calls = []
    def fail():
        calls.append(1)
        raise ValueError('sensitive')
    state = capture.run(tmp_path / 'new', connect_factory=fail)
    assert calls == [1] and state['queries'] == 0 and not state['connection_closed']


def test_atomic_save_flushes_file_and_directory(tmp_path, monkeypatch):
    import stat
    flushed = []
    monkeypatch.setattr(capture.os, 'fsync', lambda fd: flushed.append(capture.os.fstat(fd).st_mode))
    capture.save(tmp_path / 'atomic.json', {'ok': True})
    assert len(flushed) == 2
    assert stat.S_ISREG(flushed[0]) and stat.S_ISDIR(flushed[1])
    assert not (tmp_path / 'atomic.json.tmp').exists()


@pytest.mark.parametrize('damage', ['bad_json', 'foreign_base', 'bad_prefix', 'bad_hash', 'untracked'])
def test_corrupt_journal_or_untracked_batch_rejected(tmp_path, monkeypatch, damage):
    root = seed(tmp_path / 'old')
    real_save = capture.save
    def crash(path, value):
        real_save(path, value)
        if path.name == 'batch-0003.json':
            raise KeyboardInterrupt()
    monkeypatch.setattr(capture, 'save', crash)
    execute(root, resume=True)
    monkeypatch.setattr(capture, 'save', real_save)
    pending = root / 'pending.json'
    journal = json.loads(pending.read_text())
    if damage == 'bad_json':
        pending.write_text('{')
    elif damage == 'foreign_base':
        journal['base_sha256'] = 'wrong'
        real_save(pending, journal)
    elif damage == 'bad_prefix':
        journal['checkpoint']['batches'][0]['rows'] = 999
        real_save(pending, journal)
    elif damage == 'bad_hash':
        (root / 'batch-0003.json').write_text('{}')
    else:
        pending.unlink()
    with pytest.raises(RuntimeError):
        capture.run(root, resume=True)


def test_second_capture_cannot_run_while_locked(tmp_path):
    root = seed(tmp_path / 'old')
    before = inventory(root)
    with capture.destination_lock(root):
        with pytest.raises(RuntimeError, match='capture_already_running'):
            capture.run(root, resume=True)
    assert inventory(root) == before


def test_multisession_analyzer_fails_before_any_lake_access(tmp_path):
    from modules.telchi.investigation.validation.controlled_physical_capture_v1 import analyze
    root = tmp_path / 'capture'
    (root / 'sessions').mkdir(parents=True)
    with pytest.raises(RuntimeError, match='consistency_accreditation'):
        analyze.analyze(root)


def test_fork_preserves_previous_sessions_and_lineage(tmp_path):
    original = seed(tmp_path / 'old')
    target = tmp_path / 'continued'
    execute(target, resume=True, resume_from=original, max_queries=1)
    before = inventory(target)
    fork = tmp_path / 'fork'
    conn, state, _ = execute(fork, resume=True, resume_from=target, max_queries=1)
    assert conn.calls[0][1] == ('000224',)
    assert state['rows'] == 250
    assert inventory(target) == before
    assert len(list((fork / 'sessions').glob('*.json'))) == 2
    assert json.loads((fork / 'origin.json').read_text())['inherited_origin']['source'] == str(original)


def test_completed_capture_cannot_repeat_query(tmp_path):
    root = tmp_path / 'new'
    execute(root, FakeConnection(end=1))
    with pytest.raises(RuntimeError, match='already_complete'):
        capture.run(root, resume=True)


def test_more_conservative_controls(tmp_path):
    conn, state, pauses = execute(tmp_path / 'new', batch_size=7, max_queries=2,
                                pause_seconds=12, latency_seconds=1)
    assert state['rows'] == 14 and state['queries'] == 2 and pauses == [12]
    assert conn.calls == [(capture.query(7), ()), (capture.query(7, True), ('000006',))]


def test_resume_4775_preserves_entire_prefix(tmp_path):
    source = seed(tmp_path / 'source', batches=47)
    execute(source, resume=True, max_queries=3)
    assert capture.read_checkpoint(source)[0]['rows'] == 4775
    before = inventory(source)
    conn, state, _ = execute(tmp_path / 'new', resume=True, resume_from=source)
    assert state['initial_rows'] == 4775 and state['rows'] == 4900
    assert conn.calls[0][1] == ('004774',)
    assert inventory(source) == before
    assert len(capture.recover(tmp_path / 'new')[1]) == 4900
    for name, value in before.items():
        if name not in ('checkpoint.json', 'origin.json'):
            assert capture.digest(tmp_path / 'new' / name) == value


@pytest.mark.parametrize('name', ['pending.json', 'batch-0003.json', 'checkpoint.json'])
def test_write_error_stops_and_preserves_prefix(tmp_path, monkeypatch, name):
    root = seed(tmp_path / 'old')
    before = {p.name: capture.digest(p) for p in root.glob('batch-*.json')}
    real_save = capture.save
    def fail(path, value):
        if path.name == name:
            raise OSError('simulated write failure')
        real_save(path, value)
    monkeypatch.setattr(capture, 'save', fail)
    _, state, pauses = execute(root, resume=True)
    assert state['queries'] == 1 and not pauses and state['stop_reason'] == 'OSError'
    assert all(capture.digest(root / k) == v for k, v in before.items())
    monkeypatch.setattr(capture, 'save', real_save)
    with capture.destination_lock(root):
        cp, _, _, _ = capture.recover_pending(root)
    assert cp['rows'] == (225 if name == 'checkpoint.json' else 200)


def test_destination_pressure_prevents_creation_and_connection(tmp_path, monkeypatch):
    def blocked(root):
        raise capture.PersistenceBlocked('destination_device_sustained_pressure')
    monkeypatch.setattr(capture, 'destination_preflight', blocked)
    with pytest.raises(capture.PersistenceBlocked):
        capture.run(tmp_path / 'new')
    assert not (tmp_path / 'new').exists()


def test_probe_failure_prevents_connection(tmp_path, monkeypatch):
    def fail(*args):
        raise capture.PersistenceBlocked('destination_probe_write_failed')
    monkeypatch.setattr(capture, 'verify_probe', fail)
    with pytest.raises(capture.PersistenceBlocked):
        capture.run(tmp_path / 'new')
    assert capture.read_checkpoint(tmp_path / 'new')[0]['rows'] == 0


def test_pressure_between_queries_closes_connection(tmp_path, monkeypatch):
    checks = []
    def check(root):
        checks.append(root)
        if len(checks) == 3:
            raise capture.PersistenceBlocked('destination_device_sustained_pressure')
        return {}
    monkeypatch.setattr(capture, 'destination_preflight', check)
    _, state, _ = execute(tmp_path / 'new')
    assert state['queries'] == 1 and state['rows'] == 25
    assert state['stop_reason'] == 'PersistenceBlocked'


def test_slow_commit_stops_after_one_durable_batch(tmp_path, monkeypatch):
    ticks = iter([0, 10.001])
    monkeypatch.setattr(capture.time, 'monotonic', lambda: next(ticks))
    _, state, pauses = execute(tmp_path / 'new')
    assert state['queries'] == 1 and state['rows'] == 25 and not pauses
    assert state['persistence_block'] == 'destination_commit_latency_exceeded'
    assert capture.read_checkpoint(tmp_path / 'new')[0]['rows'] == 25


@pytest.mark.parametrize('mode', ['file', 'directory'])
def test_real_save_sync_failure_before_connect(tmp_path, monkeypatch, mode):
    import stat
    def fail(fd):
        if stat.S_ISDIR(capture.os.fstat(fd).st_mode) == (mode == 'directory'):
            raise OSError('simulated fsync error')
    monkeypatch.setattr(capture.os, 'fsync', fail)
    with pytest.raises(OSError, match='fsync error'):
        capture.run(tmp_path / 'new')


@pytest.mark.parametrize('seconds', [3, 3.2326, 5, 9.999, 10])
def test_slow_successful_commits_continue_without_duplicates(tmp_path, monkeypatch, seconds):
    ticks = iter([0, seconds, 20, 20 + seconds])
    monkeypatch.setattr(capture.time, 'monotonic', lambda: next(ticks))
    _, state, pauses = execute(tmp_path / 'new', max_queries=2)
    assert state['queries'] == state['batches'] == 2 and pauses == [10]
    assert state['stop_reason'] == 'query_budget_exhausted'
    assert state['persistence_seconds'] == 10
    assert state['persistence_ms'] == pytest.approx([seconds * 1000] * 2)
    cp, rows, seen, _ = capture.read_checkpoint(tmp_path / 'new')
    assert cp['rows'] == len(rows) == len(seen) == 50


@pytest.mark.parametrize('mode', ['file_sync', 'directory_sync', 'readback_hash'])
def test_commit_integrity_errors_stop_without_second_query(tmp_path, monkeypatch, mode):
    root = seed(tmp_path / 'old')
    real_save = capture.save
    def fail(path, value):
        if path.name == 'batch-0003.json':
            if mode != 'readback_hash':
                import stat
                def sync_error(fd):
                    is_dir = stat.S_ISDIR(capture.os.fstat(fd).st_mode)
                    if is_dir == (mode == 'directory_sync'):
                        monkeypatch.setattr(capture.os, 'fsync', lambda fd: None)
                        raise OSError('simulated sync failure')
                monkeypatch.setattr(capture.os, 'fsync', sync_error)
            real_save(path, value)
            if mode == 'readback_hash':
                path.write_bytes(b'corrupt content')
        else:
            real_save(path, value)
    monkeypatch.setattr(capture, 'save', fail)
    _, state, pauses = execute(root, resume=True)
    assert state['queries'] == 1 and not pauses
    assert state['stop_reason'] == ('RuntimeError' if mode == 'readback_hash' else 'OSError')
    assert state['stop_reason'] != 'PersistenceBlocked'


def test_short_write_never_replaces_committed_file(tmp_path, monkeypatch):
    import io
    from pathlib import Path
    path = tmp_path / 'checkpoint.json'
    capture.save(path, {'previous': True})
    before = path.read_bytes()
    real_open = Path.open
    class ShortWrite(io.BytesIO):
        def write(self, data):
            return len(data) - 1
    def opened(self, *args, **kwargs):
        if self == path.with_suffix('.json.tmp'):
            return ShortWrite()
        return real_open(self, *args, **kwargs)
    monkeypatch.setattr(Path, 'open', opened)
    with pytest.raises(OSError, match='short_capture_write'):
        capture.save(path, {'new': True})
    assert path.read_bytes() == before


def test_cli_resume_contract(tmp_path, monkeypatch):
    import sys
    calls = []
    def offline_run(root, **kwargs):
        calls.append((root, kwargs))
        return {'stop_reason': 'query_budget_exhausted'}
    monkeypatch.setattr(capture, 'run', offline_run)
    monkeypatch.setattr(sys, 'argv', ['capture', str(tmp_path / 'new'), '--resume',
        '--resume-from', str(tmp_path / 'old'), '--batch-size', '25', '--max-queries', '5',
        '--pause-seconds', '10', '--latency-seconds', '1.5'])
    assert capture.main() == 0
    root, kwargs = calls[0]
    assert root == tmp_path / 'new'
    assert kwargs == dict(resume=True, resume_from=tmp_path / 'old', batch_size=25,
                          max_queries=5, pause_seconds=10, latency_seconds=1.5)
