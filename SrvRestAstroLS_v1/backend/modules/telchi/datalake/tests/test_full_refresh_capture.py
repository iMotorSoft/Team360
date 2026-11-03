from contextlib import closing
from dataclasses import replace
from pathlib import Path

import pytest

from modules.telchi.datalake import full_refresh_capture as cap
from modules.telchi.datalake.source import HanaReadOnlySource, HanaTransportLimits
from modules.telchi.datalake.tests.test_sales_incremental import Cursor, Connection
from modules.telchi.runtime.config import DuckDBSafetyProfile


@pytest.mark.parametrize('failure', [None, 'execute', 'fetch', 'close', 'early', 'rows'])
def test_single_statement_stream_cleanup(failure):
    connection = Connection()
    cursor = Cursor([dict(k=i) for i in range(4)], failure)
    source = HanaReadOnlySource(connect_factory=lambda: (connection, cursor),
                               limits=HanaTransportLimits(max_rows=2 if failure == 'rows' else 4))
    def run():
        with closing(source.stream_read_only('stream', 'SELECT "k" FROM "T" ORDER BY "k"', batch_size=2)) as rows:
            for batch in rows:
                assert len(batch) <= 2
                if failure == 'early':
                    break
    if failure in ('execute', 'fetch', 'close', 'rows'):
        with pytest.raises((TimeoutError, ConnectionError, RuntimeError)):
            run()
    else:
        run()
    assert connection.closed and cursor.closed
    assert source.query_log[0]['connection_closed']
    assert source.query_log[0]['status'] == ('FETCHED' if failure in (None, 'close') else 'FAILED')
    if failure == 'early':
        assert source.query_log[0]['error_type'] == 'GeneratorExit'


class Guard:
    def preflight(self):
        pass
    def checkpoint(self):
        pass


class Source:
    def __init__(self, budget, *, fail=False, mismatch=False, rows=None):
        self.limits, self.query_log = budget.transport(), []
        self.fail, self.mismatch = fail, mismatch
        self.rows = rows if rows is not None else [dict(k=i, qty='1.25') for i in range(4)]
        self.controls = 0
    def query_read_only(self, name, sql, params=()):
        self.query_log.append(dict(query_id=name))
        if 'clock' in name:
            return [dict(utc='2026-11-01T12:00:00', source_local='2026-11-01T08:00:00', source_date='2026-11-01')]
        self.controls += 1
        return [dict(rows=len(self.rows) + int(self.mismatch and self.controls > 1),
                     sum_qty=str(sum(cap.Decimal(r['qty']) for r in self.rows)))]
    def stream_read_only(self, *args, **kwargs):
        if self.fail:
            raise ConnectionError('interrupted')
        for i in range(0, len(self.rows), 2):
            yield self.rows[i:i+2]


def session(tmp_path, **options):
    budget = cap.DomainBudget(10, 120, 100)
    source = Source(budget, **options)
    return cap.CaptureSession(tmp_path, source, budget, guard=Guard(),
        profile=DuckDBSafetyProfile(temp_directory=tmp_path/'temp')), source


def capture(s):
    return s.capture('stock', 'SELECT "k", "qty" FROM "T" ORDER BY "k"', keys=['k'], sums=['qty'],
                     semantic_scope={'mode': 'CURRENT_STATE'})


def test_recovery_no_source_calls_and_corruption(tmp_path):
    s, source = session(tmp_path)
    result = capture(s)
    assert result['row_count'] == 4 and result['control']['sum_qty'] == '5.00'
    count = len(source.query_log)
    assert capture(s) == result
    assert len(source.query_log) == count
    path = Path(result['pages'][0]['path'])
    path.write_bytes(b'corrupt')
    with pytest.raises(ValueError, match='BYTES_CHANGED'):
        capture(s)


@pytest.mark.parametrize('options,match', [({'fail': True}, 'interrupted'),
    ({'mismatch': True}, 'CONTROL_CHANGED'),
    ({'rows': [dict(k=1, qty='1'), dict(k=1, qty='1')]}, 'DUPLICATE'),
    ({'rows': [dict(k=None, qty='1')]}, 'NULL')])
def test_no_completion_no_automatic_retry(tmp_path, options, match):
    s, source = session(tmp_path, **options)
    with pytest.raises((ValueError, ConnectionError), match=match):
        capture(s)
    assert not (tmp_path/'stock/complete.json').exists()
    assert (tmp_path/'stock/failure.json').exists()
    with pytest.raises(RuntimeError, match='INTERRUPTED_SNAPSHOT'):
        capture(s)


def test_offline_audit_never_calls_capture_a_publication(tmp_path):
    from modules.telchi.datalake.full_refresh_audit import audit
    s, _ = session(tmp_path/'inventory')
    capture(s)
    report = audit(tmp_path)
    assert report['publication'] is False
    assert report['captured_datasets']['stock']['rows'] == 4
    assert report['captured_datasets']['stock']['published'] is False
    assert report['relationships']['stock_products']['status'] == 'NOT_VERIFIED'


def test_partial_cli_is_not_success_exit(monkeypatch, tmp_path):
    from modules.telchi.datalake import full_refresh
    monkeypatch.setattr('sys.argv', ['refresh', '--run-id', 'test'])
    monkeypatch.setattr(full_refresh, 'run', lambda *args, **kwargs: dict(status='PARTIAL', root=str(tmp_path)))
    assert full_refresh.main() == 2
    assert 'accounting' not in full_refresh.BUDGETS
    for budget in full_refresh.BUDGETS.values():
        assert 0 < budget.max_selects <= 100 and budget.max_rows_per_statement <= 2000000


def test_stream_requires_limits_and_rejects_writes():
    source = HanaReadOnlySource()
    with pytest.raises(ValueError, match='limits'):
        list(source.stream_read_only('x', 'SELECT "k" FROM "T"'))
    with pytest.raises(ValueError, match='read-only'):
        list(source.stream_read_only('x', 'DELETE FROM "T"'))
    assert source.query_log == []


def test_empty_is_accredited_by_controls_not_raw_parquet(tmp_path):
    s, _ = session(tmp_path, rows=[])
    result = capture(s)
    assert result['row_count'] == 0 and result['pages'] == []
    cap.verify_capture(tmp_path/'stock')


def test_explicit_prefix_reconciliation_preserves_failure(tmp_path):
    from modules.telchi.datalake.full_refresh_reconciliation import reconcile_prefix
    s, source = session(tmp_path, mismatch=True)
    with pytest.raises(ValueError, match='CONTROL_CHANGED'):
        s.capture('stock', 'SELECT "k", "qty" FROM "T" WHERE "k">=? ORDER BY "k"', (0,),
                  keys=['k'], sums=['qty'], semantic_scope={})
    source.mismatch = False
    result = reconcile_prefix(s, tmp_path/'stock', native_field='T."k"')
    assert result['row_count'] == 4 and not result['coverage_complete']
    assert (tmp_path/'stock/failure.json').exists()
    assert not (tmp_path/'stock/complete.json').exists()
    assert result['recaptured_rows'] == 0


def test_changed_plan_and_budget_rejected(tmp_path):
    s, _ = session(tmp_path)
    capture(s)
    with pytest.raises(ValueError, match='PLAN_CONFLICT'):
        s.capture('stock', 'SELECT "k" FROM "T" ORDER BY "k"', keys=['k'], semantic_scope={})
    with pytest.raises(ValueError):
        cap.DomainBudget(0, 100, 100)
    s.budget = replace(s.budget, max_selects=1)
    with pytest.raises(RuntimeError, match='SELECT_BUDGET'):
        s.query('extra', 'SELECT "k" FROM "T"')
