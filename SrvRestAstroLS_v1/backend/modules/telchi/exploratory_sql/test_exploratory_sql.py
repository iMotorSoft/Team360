"""Cheap offline tests: no untrusted SQL execution, Foundation or network access."""
from dataclasses import FrozenInstanceError, replace
from decimal import Decimal
import json
from pathlib import Path
import threading

import pytest

from . import CONTRACT_VERSION, FEATURE_ENABLED_DEFAULT
from .contracts import (
    Budget, CandidateRelation, Column, Decision, ExploratoryQueryProposal,
    ExploratoryQueryResult, RelationState, TypedParameter,
)
from .executor import ExploratoryExecutor, ResearchBudget, probe_isolation
from .synthetic import CATALOG, ROWS, synthetic_context
from .validator import Visitor, Rejected, validate
from .verifier import (
    IndependentVerifier, count_matches, decimal_sum, partitions_reconcile,
    percentage_matches, profile_synthetic_relation, sum_matches,
)


def proposal(sql, *, sources=None, candidates=(), parameters=()):
    return ExploratoryQueryProposal(
        sql, "Investigate synthetic documentary relationships", "Synthetic data only",
        sources or tuple(t.name for t in CATALOG.tables), "declared_synthetic_grain",
        "Rows for independent verification", candidates, parameters=parameters,
    )


CANDIDATE = CandidateRelation("invoices", "id", "movements", "invoice_id")


@pytest.mark.parametrize("sql", [
    "SELECT id, amount FROM invoices",
    "SELECT channel_id, sum(amount) AS total, count(*) AS n FROM invoices GROUP BY channel_id ORDER BY channel_id",
    "SELECT count(DISTINCT invoice_id) AS n FROM movements",
    "SELECT id, amount * 2 AS doubled FROM invoices WHERE id IN (1, 2)",
    "SELECT id FROM invoices WHERE amount BETWEEN 1 AND 200",
    "SELECT id FROM invoices WHERE channel_id IS NULL OR seller_id = 1 ORDER BY id DESC LIMIT 2",
    "SELECT DISTINCT channel_id FROM invoices",
    "SELECT coalesce(channel_id, 0) AS channel FROM invoices",
    "SELECT CASE WHEN channel_id IS NULL THEN 'unknown' ELSE 'known' END AS channel FROM invoices",
    "SELECT invoice_id, count(*) AS n FROM movements GROUP BY invoice_id HAVING count(*) > 1",
    "SELECT x.id FROM (SELECT id FROM invoices WHERE id > 1) x ORDER BY x.id",
    "WITH x AS (SELECT invoice_id, sum(amount) AS amount FROM lines GROUP BY invoice_id) SELECT i.id, x.amount FROM invoices i LEFT JOIN x ON i.id = x.invoice_id",
    "SELECT i.id, l.amount FROM invoices i JOIN lines l ON i.id=l.invoice_id AND l.amount>1",
    "SELECT lower(name) AS name FROM products WHERE length(name)>1",
    # Hold-out relacional: designed after visitor implementation, not a business template.
    "WITH coverage AS (SELECT invoice_id, min(hour) AS first_hour, max(hour) AS last_hour, count(*) AS movements FROM movements GROUP BY invoice_id) SELECT s.name AS seller, i.id, coalesce(c.movements,0) AS movement_count, c.last_hour-c.first_hour AS span FROM invoices i JOIN sellers s ON i.seller_id=s.id LEFT JOIN coverage c ON i.id=c.invoice_id WHERE i.channel_id IS NULL ORDER BY i.id",
])
def test_admitted_relational_subset(sql):
    decision, query = validate(proposal(sql, candidates=(CANDIDATE,)), synthetic_context())
    assert decision.decision == Decision.ALLOW, decision
    assert query and query.generated_sql != sql
    assert query.query_id == decision.query_id
    assert query.version == CONTRACT_VERSION
    assert query.sources
    assert query.mandatory_checks == IndependentVerifier.REQUIRED
    # Regenerated SQL must itself be syntactically valid; parse only, no EXPLAIN
    # or execution, because no accredited sandbox is available on this host.
    import duckdb
    with duckdb.connect(config={"threads": "1", "enable_external_access": "false"}) as c:
        rebuilt = json.loads(c.execute("SELECT json_serialize_sql(?)", [query.generated_sql]).fetchone()[0])
    assert rebuilt["error"] is False
    names = {entry["key"] for entry in rebuilt["statements"][0]["named_param_map"]}
    assert names == {p.name for p in query.parameters}


ATTACKS = [
    "SELECT * FROM invoices",  # plain star intentionally not supported
    "SELECT id FROM other_tenant.invoices",
    "SELECT id FROM tenant_b.invoices",
    "SELECT secret FROM secrets",
    "SELECT id FROM duckdb_tables()",
    "SELECT table_name FROM information_schema.tables",
    "SELECT id FROM invoices; SELECT id FROM invoices",
    "SELECT id FROM invoices; DROP TABLE invoices",
    "CREATE TABLE exploit(id INTEGER)",
    "INSERT INTO invoices VALUES (7,1,1,1,1)",
    "UPDATE invoices SET amount=0",
    "DELETE FROM invoices",
    "COPY invoices TO '/tmp/telchi-exploratory-canary'",
    "COPY invoices FROM '/etc/passwd'",
    "ATTACH '/tmp/exploit.db' AS evil",
    "DETACH synthetic",
    "PRAGMA threads=8",
    "SET enable_external_access=true",
    "INSTALL httpfs",
    "LOAD httpfs",
    "CALL checkpoint()",
    "SELECT content FROM read_text('/etc/passwd')",
    "SELECT id FROM read_parquet('/etc/passwd')",
    "SELECT id FROM read_csv('https://example.invalid/secret')",
    "SELECT getenv('OpenAI_Key_JAI_query') FROM invoices",
    "SELECT current_setting('home_directory') FROM invoices",
    "SELECT error('sensitive') FROM invoices",
    "SELECT query('SELECT 1') FROM invoices",
    "SELECT id FROM query_table('invoices')",
    "WITH x AS (DELETE FROM invoices RETURNING id) SELECT id FROM x",
    "WITH x AS (SELECT id FROM read_parquet('/etc/passwd')) SELECT id FROM x",
    "WITH x AS (SELECT id FROM secret) SELECT id FROM x",
    "SELECT id FROM (SELECT id FROM read_csv('https://example.invalid')) x",
    "SELECT (SELECT content FROM read_text('/etc/passwd')) FROM invoices",
    "SELECT i.id FROM invoices i CROSS JOIN movements m",
    "SELECT i.id FROM invoices i JOIN movements m ON true",
    "SELECT i.id FROM invoices i JOIN movements m ON i.id=i.id",
    "SELECT i.id FROM invoices i JOIN movements m ON i.id=m.invoice_id OR 1=1",
    "SELECT i.id FROM invoices i NATURAL JOIN movements m",
    "SELECT i.id FROM invoices i JOIN movements m USING (id)",
    "SELECT i.id FROM invoices i, movements m",
    "SELECT i.id FROM invoices i JOIN movements m ON i.id>m.invoice_id",
    "WITH RECURSIVE x AS (SELECT id FROM invoices UNION ALL SELECT id FROM x) SELECT id FROM x",
    "SELECT id FROM invoices UNION ALL SELECT invoice_id FROM movements",
    "SELECT id, row_number() OVER () FROM invoices",
    "SELECT id FROM invoices ORDER BY random()",
    "SELECT id FROM invoices LIMIT 1000000000",
    "SELECT id FROM invoices OFFSET 1",
    'SELECT id AS "bad; DROP TABLE invoices" FROM invoices',
    'SELECT "../../private/secret" FROM invoices',
    'SELECT id FROM "invoices;DROP TABLE invoices"',
    "SELECT id FROM invoices WHERE id IN (SELECT invoice_id FROM movements)",
    "SELECT id FROM invoices WHERE exists(SELECT 1 FROM read_text('/etc/passwd'))",
    "SELECT id FROM invoices TABLESAMPLE 10 PERCENT",
    "SELECT id FROM invoices AT (VERSION => 1)",
    "SELECT id FROM invoices QUALIFY row_number() OVER ()=1",
    "SELECT count(*) FILTER (WHERE id>1) FROM invoices",
    "SELECT sum(amount ORDER BY id) FROM invoices",
    "SELECT main.sum(amount) FROM invoices",
    "SELECT * REPLACE (error('bad') AS id) FROM invoices",
    "SELECT COLUMNS('.*') FROM invoices",
    "SELECT [id] FROM invoices",
    "SELECT cast(id AS BLOB) FROM invoices",
    "PIVOT invoices ON id USING sum(amount)",
    "EXPORT DATABASE '/tmp/exploit'",
    "VACUUM",
]


@pytest.mark.parametrize("sql", ATTACKS)
def test_adversarial_rejected_before_execution(sql, monkeypatch, tmp_path):
    # Record all DuckDB commands: the only allowed execution is the trusted parser
    # invocation with untrusted SQL passed as DATA. Never EXPLAIN/bind/execute it.
    import duckdb
    real_connect = duckdb.connect
    commands = []

    class ParserConnection:
        def __enter__(self):
            self.connection = real_connect(":memory:", config={
                "threads": "1", "enable_external_access": "false",
                "autoload_known_extensions": "false", "autoinstall_known_extensions": "false"})
            return self

        def __exit__(self, *args):
            self.connection.close()

        def execute(self, command, values):
            commands.append((command, values))
            assert command == "SELECT json_serialize_sql(?)"
            return self.connection.execute(command, values)

    monkeypatch.setattr(duckdb, "connect", lambda *a, **k: ParserConnection())
    # No subprocess permitted on executor attempts, including successful validation.
    monkeypatch.setattr("subprocess.Popen", lambda *a, **k: pytest.fail("SQL process attempted"))
    canary = tmp_path / "canary"
    canary.write_text("unchanged")
    before = dict(ROWS)
    p = proposal(sql, candidates=(CANDIDATE,))
    decision, query = validate(p, synthetic_context())
    assert query is None and decision.decision != Decision.ALLOW
    assert sql not in decision.reason
    assert "/" not in decision.reason and "tenant_b" not in decision.reason
    blocked, result = ExploratoryExecutor(enabled=True).execute(p, synthetic_context())
    assert blocked.decision != Decision.ALLOW
    assert result.status == "NOT_EXECUTED" and not result.rows
    assert canary.read_text() == "unchanged" and ROWS == before
    assert all(command == "SELECT json_serialize_sql(?)" for command, _ in commands)


def test_contracts_immutable_and_model_has_no_authority_fields():
    p = proposal("SELECT id FROM invoices")
    assert not {"identity", "permissions", "organization", "workspace", "catalog", "snapshot"} & p.__dataclass_fields__.keys()
    with pytest.raises(FrozenInstanceError):
        p.sql = "DROP TABLE invoices"
    with pytest.raises(TypeError):
        ExploratoryQueryProposal(**(p.__dict__ | {"permissions": ["admin"]}))
    assert p.version == synthetic_context().version == CONTRACT_VERSION


@pytest.mark.parametrize("change", [
    {"organization": "other"}, {"workspace": "other"}, {"environment": "production"},
    {"identity": ""}, {"investigation_id": ""}, {"publication": "latest"}, {"snapshot": "latest"},
    {"sources": ("other",)}, {"permissions": frozenset()}, {"version": "v0"},
    {"catalog": replace(CATALOG, organization="other")},
])
def test_permissions_context_fail_closed(change):
    d, q = validate(proposal("SELECT id FROM invoices"), replace(synthetic_context(), **change))
    assert d.decision == Decision.DENY and q is None


def test_subset_authorization_and_column_resolution():
    ctx = replace(synthetic_context(), sources=("invoices",))
    d, q = validate(proposal("SELECT id FROM lines", sources=("lines",)), ctx)
    assert q is None
    for sql in ("SELECT secret FROM invoices", "SELECT m.id FROM invoices i", "SELECT id FROM invoices i JOIN lines l ON i.id=l.invoice_id"):
        assert validate(proposal(sql), synthetic_context())[1] is None


def test_candidate_never_automatically_accredited():
    sql = "SELECT i.id, count(*) AS n FROM invoices i JOIN movements m ON i.id=m.invoice_id GROUP BY i.id"
    assert validate(proposal(sql), synthetic_context())[1] is None
    d, q = validate(proposal(sql, candidates=(CANDIDATE,)), synthetic_context())
    assert d.decision == Decision.ALLOW
    assert q.relations[0].state == RelationState.INVESTIGATIVE


def test_typed_parameters_and_literal_injection():
    text = "'; COPY invoices TO '/tmp/escape'; --"
    p = proposal("SELECT id FROM products WHERE name=$name", parameters=(TypedParameter("name", "VARCHAR", text),))
    d, q = validate(p, synthetic_context())
    assert d.decision == Decision.ALLOW
    assert text not in q.generated_sql and q.parameters[0].value == text
    amount = TypedParameter("amount", "DECIMAL(18,2)", Decimal("10.50"))
    p = proposal("SELECT id FROM invoices WHERE amount>$amount", parameters=(amount,))
    assert validate(p, synthetic_context())[0].decision == Decision.ALLOW
    for params in ((), (TypedParameter("name", "FILE", "/etc/passwd"),),
                   (TypedParameter("name", "INTEGER", True),),
                   (TypedParameter("name", "VARCHAR", "x"), TypedParameter("unused", "INTEGER", 1))):
        assert validate(replace(p, sql="SELECT id FROM products WHERE name=$name", parameters=params), synthetic_context())[1] is None


def test_hash_binds_context_budget_parameters_grain():
    ctx = synthetic_context()
    p = proposal("SELECT id FROM invoices WHERE id=1")
    base = validate(p, ctx)[1]
    assert base.query_id == validate(p, ctx)[1].query_id
    assert base.query_id != validate(replace(p, sql=p.sql.replace("=1", "=2")), ctx)[1].query_id
    assert base.query_id != validate(replace(p, expected_grain="different"), ctx)[1].query_id
    assert base.query_id != validate(p, replace(ctx, investigation_id="different"))[1].query_id
    assert base.query_id != validate(p, replace(ctx, effective_budget=Budget(result_rows=5)))[1].query_id


@pytest.mark.parametrize("budget", [
    {"query_seconds": 0}, {"query_seconds": float("nan")}, {"process_memory_bytes": 2**50},
    {"threads": 8}, {"queries": -1}, {"concurrency": True}, {"result_rows": 1000},
    {"cpu_seconds": 0.5}, {"result_rows": 1.5},
])
def test_budget_invalid(budget):
    with pytest.raises(ValueError):
        Budget(**budget)


def test_effective_budget_and_combinatorial_join_limit():
    ctx = synthetic_context(budget=Budget(max_join_pairs=10))
    p = proposal("SELECT i.id FROM invoices i JOIN movements m ON i.id=m.invoice_id", candidates=(CANDIDATE,))
    d, q = validate(p, ctx)
    assert d.decision == Decision.RESOURCE_BLOCKED and d.reason == "join_pair_budget"
    assert q is None
    p = proposal("SELECT id FROM invoices " + "WHERE " + "(" * 100 + "id=1" + ")" * 100)
    # Parentheses alone do not increase logical AST complexity, but excessive SQL bytes do.
    assert validate(replace(p, sql="x" * 8193), ctx)[1] is None


def test_native_ast_unknown_fields_and_deep_unknown_functions_rejected():
    import duckdb
    with duckdb.connect(config={"threads": "1"}) as c:
        tree = json.loads(c.execute("SELECT json_serialize_sql(?)", ["SELECT id FROM invoices"]).fetchone()[0])
    node = tree["statements"][0]["node"]
    node["hidden_operation"] = {"type": "COPY"}
    with pytest.raises(Rejected, match="unknown_ast_fields"):
        Visitor(proposal("irrelevant"), synthetic_context()).query(node, {})
    assert validate(proposal("SELECT coalesce(abs(error('secret')),1) FROM invoices"), synthetic_context())[1] is None


def test_disabled_default_and_positive_sql_still_cannot_launch(monkeypatch):
    monkeypatch.setenv("TELCHI_EXPLORATORY_SQL_ENABLED", "true")
    monkeypatch.setattr("subprocess.Popen", lambda *a, **k: pytest.fail("worker attempted"))
    p, ctx = proposal("SELECT id FROM invoices"), synthetic_context()
    assert FEATURE_ENABLED_DEFAULT is False
    d, r = ExploratoryExecutor().execute(p, ctx)
    assert d.decision == Decision.DENY and d.reason == "feature_disabled"
    d, r = ExploratoryExecutor(enabled=True).execute(p, ctx)
    assert d.decision == Decision.RESOURCE_BLOCKED
    assert d.reason == "execution_isolation_not_accredited"
    assert r.status == "NOT_EXECUTED" and r.cpu_seconds is None and r.bytes_read is None


def test_preexecution_cancellation():
    cancel = threading.Event()
    cancel.set()
    d, r = ExploratoryExecutor(enabled=True).execute(proposal("SELECT id FROM invoices"), synthetic_context(), cancel=cancel)
    assert d.reason == "cancelled_before_execution" and r.status == "NOT_EXECUTED"


def test_budget_query_count_time_and_concurrency():
    clock = [0.0]
    b = ResearchBudget(Budget(queries=2), clock=lambda: clock[0])
    assert b.reserve() and not b.reserve()
    b.release()
    assert b.reserve()
    b.release()
    assert not b.reserve()
    b = ResearchBudget(Budget(), clock=lambda: clock[0])
    clock[0] = 11.0
    assert not b.reserve()


def test_probe_does_not_inherit_secrets_or_sql(monkeypatch):
    captured = {}
    def run(command, **kwargs):
        captured.update(kwargs)
        assert command[-1] == "/usr/bin/true"
        assert "--unshare-all" in command and "--die-with-parent" in command
        return type("Done", (), {"returncode": 1})()
    monkeypatch.setattr("subprocess.run", run)
    monkeypatch.setenv("OpenAI_Key_JAI_query", "fake-test-only")
    p = probe_isolation()
    assert not p.available
    assert set(captured["env"]) == {"PATH", "LANG"}
    assert captured["close_fds"] and captured["timeout"] == 3


def test_synthetic_relationship_profile():
    p = profile_synthetic_relation("invoices", "id", "movements", "invoice_id", amount_column="amount")
    assert p.state == RelationState.INVESTIGATIVE
    assert p.cardinality == "ONE_TO_MANY" and p.left_unique and not p.right_unique
    assert p.left_null_keys == 0 and p.right_null_keys == 1 and p.right_orphans == 1
    assert p.matched_pairs == 6 and p.left_join_rows == 7 and p.unmatched_left == 1
    assert p.coverage_percent == Decimal(2) * 100 / Decimal(3)
    assert p.multiplication and not p.totals_stable
    assert p.baseline_total == Decimal("200.00") and p.left_join_total == Decimal("600.00")
    assert ROWS["movements"][0][1:4] == ROWS["movements"][1][1:4]
    with pytest.raises(ValueError):
        profile_synthetic_relation("../../etc/passwd", "id", "invoices", "id")


def test_five_movements_do_not_become_five_invoices():
    verifier = IndependentVerifier()
    ids = frozenset({1})
    assert sum(r[1] == 1 for r in ROWS["movements"]) == 5
    assert verifier.verify_synthetic_invoice_total(Decimal("500.00"), invoice_ids=ids).state == "REJECTED"
    assert verifier.verify_synthetic_invoice_total(Decimal("100.00"), invoice_ids=ids).state == "REFERENCE_MATCH"
    p = proposal("SELECT sum(i.amount) AS total FROM invoices i JOIN movements m ON i.id=m.invoice_id", candidates=(CANDIDATE,))
    ctx = synthetic_context()
    d, q = validate(p, ctx)
    assert d.decision == Decision.ALLOW  # technically admitted SQL can be business-wrong
    r = ExploratoryQueryResult(q.query_id, (Column("total", "DECIMAL(18,2)"),),
        q.declared_grain, ((Decimal("580.00"),),), returned_count=1,
        publication=ctx.publication, snapshot=ctx.snapshot, status="COMPLETED")
    verification = verifier.verify(q, r, ctx)
    assert verification.state == "UNVERIFIED"
    assert not dict(verification.checks)["grain"]
    assert "header_amount_join_multiplication_risk" in verification.limitations
    assert verifier.verify_synthetic_invoice_total(Decimal("580.00")).state == "REJECTED"
    assert verifier.verify_synthetic_invoice_total(Decimal("200.00")).state == "REFERENCE_MATCH"


def test_independent_checks_and_no_model_opt_out():
    assert sum_matches([Decimal("1.10"), Decimal("2.20")], Decimal("3.30"))
    assert decimal_sum(iter([Decimal("1.10"), Decimal("2.20")])) == Decimal("3.30")
    assert count_matches([1, 2], 2) and not count_matches([1], True)
    assert percentage_matches(Decimal(1), Decimal(4), Decimal(25))
    assert not percentage_matches(Decimal(1), Decimal(0), Decimal(0))
    assert not percentage_matches(Decimal(1), Decimal(4), Decimal(26))
    assert partitions_reconcile([1, 2, 3], [[1, 2], [3]])
    assert not partitions_reconcile([1, 2, 3], [[1, 2], [2, 3]])
    with pytest.raises(ValueError, match="decimal_required"):
        decimal_sum([1.1])
    ctx = synthetic_context()
    q = validate(proposal("SELECT id FROM invoices"), ctx)[1]
    r = ExploratoryQueryResult(q.query_id, status="COMPLETED", declared_grain=q.declared_grain,
        publication=ctx.publication, snapshot=ctx.snapshot, evidence=("model says verified",))
    v = IndependentVerifier().verify(replace(q, mandatory_checks=()), r, ctx)
    assert v.state == "UNVERIFIED" and "mandatory_verifications_missing" in v.limitations
    assert not dict(IndependentVerifier().verify(q, replace(r, snapshot="other"), ctx).checks)["provenance"]


def test_no_registration_or_v1_dependency():
    root = Path(__file__).resolve().parents[1]
    for path in (root / "assistant").glob("*.py"):
        assert "exploratory_sql" not in path.read_text()
    for path in (root.parent / "messaging").glob("*.py"):
        assert "exploratory_sql" not in path.read_text()
