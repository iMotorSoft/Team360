from datetime import date
from dataclasses import asdict
import json

import pytest

from modules.telchi.datalake import sales_incremental as inc
from modules.telchi.datalake.source import HanaReadOnlySource, HanaTransportLimits


def row(entry=1, line=0, **kw):
    return dict(DocEntry=entry, LineNum=line, DocNum=entry, DocDate="2026-10-01",
                UpdateDate="2026-10-01", TransId=100+entry, ObjType=13, DocCur="BS",
                DocTotal="113.00", DocTotalSy="113.00", DocTotalFC="0.00", CANCELED="N",
                CardCode="C1", ItemCode="I1", Quantity="1", LineCurrency="BS", LineTotal="100.00",
                **kw)


class Cursor:
    def __init__(self, rows, fail=None):
        self.rows, self.fail, self.closed, self.timeout = rows, fail, False, None
        self.description = [(k,) for k in (rows[0] if rows else {})]
    def setquerytimeout(self, seconds):
        self.timeout = seconds
    def execute(self, sql, params):
        self.sql, self.params = sql, params
        if self.fail == "execute":
            raise TimeoutError("simulated statement timeout")
    def fetchmany(self, n):
        if self.fail == "fetch":
            raise ConnectionError("interrupted fetch")
        batch, self.rows = self.rows[:n], self.rows[n:]
        return [tuple(r.values()) for r in batch]
    def close(self):
        self.closed = True
        if self.fail == "close":
            raise RuntimeError("cursor close failed")


class Connection:
    def __init__(self):
        self.closed, self.cancelled = False, False
    def cancel(self):
        self.cancelled = True
    def rollback(self):
        pass
    def close(self):
        self.closed = True


def source_for(responses, fail=None):
    resources = []
    def connect():
        c, cur = Connection(), Cursor(responses.pop(0), fail)
        resources.append((c, cur))
        return c, cur
    return HanaReadOnlySource(connect_factory=connect, limits=HanaTransportLimits()), resources


@pytest.mark.parametrize("fail", [None, "execute", "fetch", "close"])
def test_driver_limits_cleanup_no_retry(fail):
    source, resources = source_for([[row()]], fail)
    if fail:
        with pytest.raises((TimeoutError, ConnectionError, RuntimeError)):
            source.query_read_only("test", inc.query("sales"), ())
    else:
        assert source.query_read_only("test", inc.query("sales"), ())[0]["DocEntry"] == 1
    assert len(resources) == 1
    connection, cursor = resources[0]
    assert cursor.timeout == 5
    assert cursor.closed and connection.closed
    assert source.query_log[0]["connection_closed"]
    if fail in ("execute", "fetch"):
        assert connection.cancelled


def test_row_limit_and_connect_error():
    source, resources = source_for([[row(i) for i in range(1001)]])
    with pytest.raises(RuntimeError, match="ROW_BUDGET"):
        source.query_read_only("cap", inc.query("sales"))
    assert resources[0][0].closed
    def failure():
        raise ConnectionError("no connection")
    source = HanaReadOnlySource(connect_factory=failure, limits=HanaTransportLimits())
    with pytest.raises(ConnectionError):
        source.query_read_only("connect", inc.query("sales"))
    assert len(source.query_log) == 1


def test_sql_full_documents_change_detection_and_scope():
    for domain in inc.DOMAINS:
        sql = inc.query(domain)
        assert 'TOP 5 H."DocEntry"' in sql and 'LEFT JOIN' in sql
        assert 'H."UpdateDate">=?' in sql and 'H."DocEntry">?' in sql
        assert 'TransId' in sql and 'TaxDate' in sql
        assert not any(t in sql for t in ("OINM", "OITW", "COUNT("))
    with pytest.raises(ValueError):
        inc.query("sales", limit=6)
    with pytest.raises(ValueError):
        inc.query("inventory")


def test_pilot_first_resume_duplicate_window_and_raw_integrity(tmp_path):
    root = tmp_path / "capture"
    p = inc.plan(date(2026, 10, 1))
    source, resources = source_for([[], [row()], [], [dict(row(), ObjType=14)]])
    state = inc.run(root, p, source, sleep=lambda _: None)
    assert len(state["completed"]) == 2, state
    assert all(c.closed and cur.closed for c, cur in resources)
    assert len(source.query_log) == 4
    empty, _ = source_for([])
    assert len(inc.run(root, p, empty)["completed"]) == 2
    assert not empty.query_log
    with pytest.raises(ValueError, match="plan changed"):
        inc.run(root, dict(p, run_id="other"), empty)
    cp = inc.recover(root, p)
    path = cp["sales"]["raw"]["path"]
    with open(path, "ab") as stream:
        stream.write(b"corruption")
    with pytest.raises(ValueError, match="hash mismatch"):
        inc.recover(root, p)


def test_recover_persisted_response_before_commit(tmp_path, monkeypatch):
    root = tmp_path / "capture"
    p = inc.plan(date(2026, 10, 1))
    source, _ = source_for([[], [row()]])
    original = inc.seal
    def interrupted(path, value):
        if path.name.endswith("commit.json"):
            raise OSError("interrupted persist")
        original(path, value)
    with monkeypatch.context() as m:
        m.setattr(inc, "seal", interrupted)
        state = inc.run(root, p, source, sleep=lambda _: None)
    assert state["reason"] == "OSError"
    assert inc.recover(root, p)["sales"]["metrics"]["documents"] == 1
    assert (root / "sales.commit.json").exists()


def test_uncertain_fetch_blocks_resume(tmp_path):
    root = tmp_path / "capture"
    p = inc.plan(date(2026, 10, 1))
    source, _ = source_for([[]])
    original = source.query_read_only
    def fetch(query_id, sql, params=()):
        if query_id.endswith("capture"):
            raise ConnectionError("lost during fetch")
        return original(query_id, sql, params)
    source.query_read_only = fetch
    state = inc.run(root, p, source, sleep=lambda _: None)
    assert state["reason"] == "ConnectionError"
    with pytest.raises(RuntimeError, match="UNCERTAIN_REQUEST"):
        inc.recover(root, p)


@pytest.mark.parametrize("change", [dict(LineNum=None), dict(DocCur=None), dict(DocTotal=None), dict(DocEntry=-1)])
def test_invalid_documents(change):
    with pytest.raises(ValueError):
        inc.validate_rows("sales", [dict(row(), **change)])


def test_duplicate_inconsistent_headers_currency_cancellation_and_late_change():
    with pytest.raises(ValueError, match="duplicate"):
        inc.validate_rows("sales", [row(), row()])
    with pytest.raises(ValueError, match="header"):
        inc.validate_rows("sales", [row(), dict(row(line=1), DocTotal="114")])
    original = inc.validate_rows("sales", [row()])
    changed = inc.validate_rows("sales", [dict(row(), UpdateDate="2026-10-28", DocTotal="125", CANCELED="Y")])
    assert changed["header_sha256"] != original["header_sha256"]
    assert changed["last_cursor"] == original["last_cursor"]
    assert changed["cancellations"] == 1
    assert inc.validate_rows("credit_memo", [dict(row(), DocCur="USD", ObjType=14)])["currencies"] == ["USD"]


def test_empty_pilot_and_incomplete_checkpoint(tmp_path):
    root = tmp_path / "capture"
    p = inc.plan(date(2026, 10, 1))
    source, _ = source_for([[], [], [], []])
    assert len(inc.run(root, p, source, sleep=lambda _: None)["completed"]) == 2
    (root / "sales.commit.json").write_text("{")
    with pytest.raises(json.JSONDecodeError):
        inc.recover(root, p)


def test_budget_cannot_expand_and_effective_limits_required(tmp_path):
    p = inc.plan(date(2026, 10, 1))
    with pytest.raises(ValueError, match="budget"):
        inc.validate_plan(dict(p, budget=dict(asdict(inc.PilotBudget()), max_queries=100)))
    with pytest.raises(ValueError, match="driver limits"):
        inc.run(tmp_path, p, HanaReadOnlySource())


def test_session_budget_no_connection(tmp_path):
    p = inc.plan(date(2026, 10, 1))
    source, resources = source_for([])
    times = iter([0, 150, 151])
    state = inc.run(tmp_path, p, source, clock=lambda: next(times))
    assert not resources and state["error_code"] == "STOP_OR_SESSION_BUDGET"


@pytest.mark.parametrize("domain", ["sales", "credit_memo"])
def test_whole_document_upsert_late_change_removed_line_idempotent(domain):
    previous = [row(), row(line=1), row(entry=2)]
    changed = dict(row(), UpdateDate="2026-10-29", CANCELED="Y", DocTotal="125")
    result, counts = inc.reconcile_documents(domain, previous, [changed, row(entry=3)])
    assert counts == dict(new=1, modified=1, unchanged=0, cancelled=1)
    assert len(result) == 3  # removed line is not left behind
    replay, counts = inc.reconcile_documents(domain, result, [row(entry=3), changed])
    assert replay == result
    assert counts == dict(new=0, modified=0, unchanged=2, cancelled=1)
    assert next(r for r in result if r["DocEntry"] == 2) == row(entry=2)


@pytest.mark.parametrize("domain,table", [("sales", "sales_line"), ("credit_memo", "credit_memo_line")])
def test_transform_preserves_accredited_string_key_identity(domain, table):
    manifest = dict(extraction_id="test", source_as_of="2026-10-29T00:00:00Z")
    integer_source = inc.transform_capture(domain, [row()], manifest)
    text_source = inc.transform_capture(domain, [dict(row(), DocEntry="1", LineNum="0")], manifest)
    assert integer_source.tables[table][0]["atomic_id"] == text_source.tables[table][0]["atomic_id"]
    assert integer_source.tables[table][0]["line_num"] == "0"


def test_continuation_uses_verified_native_cursor_without_network(tmp_path):
    p = inc.plan(date(2026, 10, 1))
    source, _ = source_for([[], [row()], [], [dict(row(), ObjType=14)]])
    assert len(inc.run(tmp_path, p, source, sleep=lambda _: None)["completed"]) == 2
    next_plan = inc.continuation_plan(tmp_path)
    assert next_plan["cursors_before"] == {"sales": 1, "credit_memo": 1}
    assert next_plan["business_from"] == p["business_from"]
    assert next_plan["continuation_plan_sha256"] == inc.digest(p)
    following, resources = source_for([[], [row(entry=2)], [], []])
    result = inc.run(tmp_path / "next", next_plan, following, sleep=lambda _: None)
    assert result["completed"]["sales"]["last_cursor"] == 2
    assert result["completed"]["credit_memo"]["last_cursor"] == 1
    assert resources[1][1].params[-1] == 1
    with pytest.raises(ValueError, match="native key"):
        inc.validate_rows("sales", [row()], after=1)


def test_cooperative_stop_during_fetch_commits_safe_response(tmp_path):
    import signal
    p = inc.plan(date(2026, 10, 1))
    source, _ = source_for([[], [row()]])
    original = source.query_read_only
    def fetch(query_id, sql, params=()):
        rows = original(query_id, sql, params)
        if query_id.endswith("capture"):
            signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
        return rows
    source.query_read_only = fetch
    state = inc.run(tmp_path, p, source, sleep=lambda _: None)
    assert set(state["completed"]) == {"sales"}
    assert len(source.query_log) == 2
    assert inc.recover(tmp_path, p)["sales"]["metrics"]["documents"] == 1


def test_interrupted_receipt_preserves_exact_source_no_retry(tmp_path, monkeypatch):
    p = inc.plan(date(2026, 10, 1))
    source, _ = source_for([[], [row()]])
    original = inc.seal
    def interrupted(path, value):
        if path.name.endswith("receipt.json"):
            raise OSError("interrupted receipt")
        original(path, value)
    monkeypatch.setattr(inc, "seal", interrupted)
    assert inc.run(tmp_path, p, source, sleep=lambda _: None)["reason"] == "OSError"
    assert inc.read_json(tmp_path / "sales.source.json")[0]["DocTotal"] == "113.00"
    with pytest.raises(RuntimeError, match="UNCERTAIN"):
        inc.recover(tmp_path, p)


def test_operation_deadline_cancels_and_closes(monkeypatch):
    from modules.telchi.datalake import source as mod
    source, resources = source_for([[row()]])
    ticks = iter([0, 31, 32])
    monkeypatch.setattr(mod.time, "perf_counter", lambda: next(ticks))
    with pytest.raises(TimeoutError, match="OPERATION_BUDGET"):
        source.query_read_only("deadline", inc.query("sales"))
    assert resources[0][0].cancelled and resources[0][0].closed


def test_driver_connect_options(monkeypatch):
    from modules.telchi.datalake import source as mod
    from hdbcli import dbapi
    captured = {}
    connection = Connection()
    connection.cursor = lambda: Cursor([])
    def connect(**kwargs):
        captured.update(kwargs)
        return connection
    monkeypatch.setattr(mod, "hana_config", lambda: dict(host="test", port="30015", user="u", password="p", schema="TELCHI"))
    monkeypatch.setattr(dbapi, "connect", connect)
    source = HanaReadOnlySource(limits=HanaTransportLimits())
    source.query_read_only("options", 'SELECT 1 AS "ok" FROM DUMMY')
    assert captured["connectTimeout"] == 8000
    assert captured["communicationTimeout"] == 15000
    assert connection.closed
