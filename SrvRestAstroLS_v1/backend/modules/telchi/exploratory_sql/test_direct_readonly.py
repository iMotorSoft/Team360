"""Real DuckDB tests, fictional data; no external service/identity/channel claims."""
import asyncio
from dataclasses import replace
from decimal import Decimal
import json
import threading

import httpx
import pytest

from .contracts import Budget, Decision, ExploratoryQueryProposal
from .direct_readonly import DirectReadonlyExecutor, foundation_gate
from .research import LunaSQL, investigate
from .synthetic import synthetic_context


def proposal(sql="SELECT sum(amount) AS total FROM invoices", **kwargs):
    return ExploratoryQueryProposal(sql=sql, objective="Synthetic total", justification="Independent test",
        expected_grain="all invoice headers", expected_result="BS total",
        requested_sources=("invoices",), **kwargs)


def test_actual_readonly_and_cleanup():
    ctx = synthetic_context()
    with DirectReadonlyExecutor(ctx) as executor:
        path = executor._path
        decision, result = executor.execute(proposal(), ctx)
        assert decision.decision == Decision.ALLOW
        assert result.status == "COMPLETED" and result.rows == ((Decimal("200.00"),),)
        assert result.publication == ctx.publication and result.snapshot == ctx.snapshot
        assert result.bytes_read is None and result.cpu_seconds is None
        import duckdb
        with duckdb.connect(str(path), read_only=True) as db:
            with pytest.raises(duckdb.InvalidInputException):
                db.execute("DELETE FROM invoices")
    assert not path.exists()
    assert not any(t.name == "telchi-readonly-deadline" for t in threading.enumerate())


@pytest.mark.parametrize("sql", [
    "DELETE FROM invoices", "CREATE TABLE evil AS SELECT 1", "SELECT * FROM invoices",
    "COPY invoices TO '/tmp/evil'", "ATTACH '/tmp/x' AS x", "INSTALL httpfs", "LOAD httpfs",
    "SET enable_external_access=true", "SELECT content FROM read_text('/etc/passwd')",
    "SELECT * FROM read_parquet('https://example.invalid/x')", "SELECT * FROM postgres_scan('x','x','x')",
    "SELECT * FROM duckdb_settings()", "SELECT amount FROM invoices; DELETE FROM invoices",
    "SELECT query('DELETE FROM invoices') FROM invoices", "SELECT amount FROM other_tenant.invoices",
])
def test_rejected_before_open(sql, monkeypatch):
    ctx = synthetic_context()
    with DirectReadonlyExecutor(ctx) as executor:
        import duckdb
        original = duckdb.connect
        opened = []
        def connect(path, *args, **kwargs):
            opened.append(path)
            assert path == ":memory:"  # parser only, never fixture execution
            return original(path, *args, **kwargs)
        monkeypatch.setattr(duckdb, "connect", connect)
        decision, result = executor.execute(proposal(sql), ctx)
        assert decision.decision != Decision.ALLOW
        assert result.status == "NOT_EXECUTED"


def test_permission_context_cancel_and_budget():
    ctx = synthetic_context(budget=Budget(queries=1))
    with DirectReadonlyExecutor(ctx) as executor:
        for bad in (replace(ctx, permissions=frozenset()), replace(ctx, snapshot="other"),
                    replace(ctx, organization="other")):
            decision, result = executor.execute(proposal(), bad)
            assert decision.decision == Decision.DENY and result.status == "NOT_EXECUTED"
        cancelled = threading.Event()
        cancelled.set()
        assert executor.execute(proposal(), ctx, cancel=cancelled)[0].decision == Decision.RESOURCE_BLOCKED
        assert executor.execute(proposal(), ctx)[1].status == "COMPLETED"
        assert executor.execute(proposal(), ctx)[0].reason == "research_budget_exhausted"


def test_rows_and_result_bytes_bounded():
    ctx = synthetic_context()
    with DirectReadonlyExecutor(ctx) as executor:
        p = proposal("SELECT id FROM invoices", requested_budget=Budget(result_rows=1))
        result = executor.execute(p, ctx)[1]
        assert result.truncated and len(result.rows) == 1 and result.total_count is None
        p = proposal(requested_budget=Budget(result_bytes=1))
        result = executor.execute(p, ctx)[1]
        assert result.truncated and not result.rows


def test_binding_error_is_redacted():
    ctx = synthetic_context()
    with DirectReadonlyExecutor(ctx) as executor:
        decision, result = executor.execute(proposal("SELECT sum(amount), id FROM invoices"), ctx)
        assert decision.reason == "sql_binding_error_check_catalog_types_and_grouping"
        assert result.status == "NOT_EXECUTED"
        assert "Binder" not in str(result)


def test_deadline_and_cleanup():
    ctx = synthetic_context(budget=Budget(query_seconds=0.000001))
    with DirectReadonlyExecutor(ctx) as executor:
        decision, result = executor.execute(proposal(), ctx)
        assert decision.decision == Decision.RESOURCE_BLOCKED and result.status == "NOT_EXECUTED"
    assert not any(t.name == "telchi-readonly-deadline" for t in threading.enumerate())


@pytest.mark.parametrize("claim_value,expected", [("200.00", "PASS"), ("500", "FAIL"),
                                                ("not a number", "PARTIAL"), ("NaN", "PARTIAL"),
                                                (None, "PARTIAL")])
def test_synthetic_controller_fake_model_not_live_evidence(claim_value, expected):
    class Fake:
        calls = []
        def __init__(self): self.n = 0
        async def next(self, payload, **kwargs):
            self.n += 1
            if self.n <= 2:
                if self.n == 2:
                    assert payload["observations"][0]["result"]["rows"] == ((Decimal("200.00"),),)
                return dict(action="query", **{k: v for k, v in vars(proposal(
                    "SELECT sum(amount) AS total FROM invoices" if self.n == 1 else
                    "SELECT count(*) AS n FROM invoices WHERE channel_id IS NULL")).items()
                    if k in {"sql", "objective", "justification", "expected_grain", "expected_result"}},
                    requested_sources=["invoices"])
            return dict(action="final", answer="Datos ficticios: Bs 200 de cabeceras. Limitaciones.",
                        claims=[dict(metric="invoice_header_total_bs", value=claim_value)])
    result = asyncio.run(investigate(Fake()))
    assert result["status"] == expected and len(result["turns"]) == 2
    assert result["answer_state"] == "UNVERIFIED"
    assert result["foundation"]["status"] == "BLOCKED"


def test_responses_config_fixed(monkeypatch):
    from ..assistant.luna import CREDENTIAL_ENV, MODEL
    monkeypatch.setenv(CREDENTIAL_ENV, "fictional-test-key")
    def respond(request):
        body = json.loads(request.content)
        assert str(request.url) == "https://api.openai.com/v1/responses"
        assert body["model"] == MODEL and body["reasoning"] == {"effort": "medium"}
        assert body["store"] is False and body["max_output_tokens"] == 4096
        return httpx.Response(200, json=dict(model=MODEL, reasoning={"effort": "medium"},
            status="completed", output=[dict(type="message", content=[dict(type="output_text",
            text='{"action":"final","answer":"test"}')])]))
    luna = LunaSQL(transport=httpx.MockTransport(respond))
    assert asyncio.run(luna.next({}))["action"] == "final"
    assert luna.calls[0]["fallback"] is False


@pytest.mark.parametrize("mode", ["commentary", "identical_finals", "different_finals"])
def test_responses_multiple_messages_phase_regression(monkeypatch, mode):
    from ..assistant.luna import CREDENTIAL_ENV, MODEL
    monkeypatch.setenv(CREDENTIAL_ENV, "fictional-test-key")
    final = dict(type="message", role="assistant", status="completed", phase="final_answer",
                 content=[dict(type="output_text", text='{"action":"final","answer":"safe"}')])
    other = dict(final, content=[dict(type="output_text", text='{"action":"query","sql":"rejected"}')])
    if mode == "commentary":
        other["phase"] = "commentary"
    elif mode == "identical_finals":
        other = final
    def respond(request):
        return httpx.Response(200, json=dict(model=MODEL, reasoning={"effort": "medium"},
                                            status="completed", output=[other, final]))
    luna = LunaSQL(transport=httpx.MockTransport(respond))
    if mode == "different_finals":
        with pytest.raises(RuntimeError, match="ambiguous_model_messages"):
            asyncio.run(luna.next({}))
    else:
        assert asyncio.run(luna.next({}))["answer"] == "safe"


def test_fanout_is_not_billing():
    from .contracts import CandidateRelation
    from .verifier import IndependentVerifier, profile_synthetic_relation
    ctx = synthetic_context()
    p = proposal("SELECT sum(i.amount) AS wrong FROM invoices i INNER JOIN movements m "
                 "ON i.id=m.invoice_id WHERE i.id=1",
                 candidate_relations=(CandidateRelation("invoices", "id", "movements", "invoice_id"),))
    p = replace(p, requested_sources=("invoices", "movements"))
    with DirectReadonlyExecutor(ctx) as executor:
        result = executor.execute(p, ctx)[1]
        assert result.status == "COMPLETED" and result.rows == ((Decimal("500.00"),),)
        verifier = IndependentVerifier()
        assert verifier.verify_synthetic_invoice_total(result.rows[0][0],
            invoice_ids=frozenset({1})).state == "REJECTED"
        assert verifier.verify_synthetic_invoice_total(Decimal("100"),
            invoice_ids=frozenset({1})).state == "REFERENCE_MATCH"
        profile = profile_synthetic_relation("invoices", "id", "movements", "invoice_id",
                                             amount_column="amount")
        assert profile.cardinality == "ONE_TO_MANY" and profile.multiplication


def test_no_real_data_gate():
    gate = foundation_gate()
    assert gate["status"] == "BLOCKED" and gate["foundation_opened"] is False
