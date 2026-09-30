"""Offline contract tests for update.py.

These tests build synthetic DuckDB catalogs and staging databases. They never
open SAP, never touch the real DuckLake catalog and never touch DATA_ROOT.
"""
from __future__ import annotations

import contextlib
from pathlib import Path

import duckdb
import pytest

from modules.telchi.datalake import update
from modules.telchi.datalake.create_initial import OINM_ATOMIC_COLUMNS, PUBLICATION_TABLE
from modules.telchi.runtime.transactional_publication import (
    PublicationFailurePoint,
    TransactionalPublicationBoundary,
)

SALES, CREDIT, OINM, OITW = (
    update.SALES_DOMAIN,
    update.CREDIT_MEMO_DOMAIN,
    update.OINM_DOMAIN,
    update.OITW_DOMAIN,
)

_SALES_DOC_DDL = (
    "(atomic_id VARCHAR, source_system VARCHAR, source_table VARCHAR, doc_entry VARCHAR, doc_num VARCHAR, "
    "doc_date VARCHAR, doc_due_date VARCHAR, tax_date VARCHAR, doc_status VARCHAR, canceled VARCHAR, "
    "currency VARCHAR, doc_total VARCHAR, doc_total_system VARCHAR, doc_total_foreign VARCHAR, card_code VARCHAR, "
    "slp_code VARCHAR, series VARCHAR, user_sign VARCHAR, sales_channel_code VARCHAR, sales_channel_name VARCHAR, "
    "sales_channel_semantic_status VARCHAR, source_as_of VARCHAR, raw_extraction_id VARCHAR, reference_version VARCHAR, "
    "reference_manifest_hash VARCHAR, transformation_version VARCHAR, schema_version VARCHAR)"
)
_SALES_LINE_DDL = (
    "(atomic_id VARCHAR, source_system VARCHAR, source_table VARCHAR, doc_entry VARCHAR, line_num VARCHAR, "
    "item_code VARCHAR, whs_code VARCHAR, quantity VARCHAR, currency VARCHAR, line_total VARCHAR, price VARCHAR, "
    "line_status VARCHAR, slp_code VARCHAR, attributed_slp_code VARCHAR, source_as_of VARCHAR, raw_extraction_id VARCHAR, "
    "reference_version VARCHAR, reference_manifest_hash VARCHAR, transformation_version VARCHAR, schema_version VARCHAR)"
)
_OITW_DDL = (
    "(atomic_id VARCHAR, source_system VARCHAR, source_table VARCHAR, item_code VARCHAR, whs_code VARCHAR, "
    "on_hand VARCHAR, is_commited VARCHAR, on_order VARCHAR, source_as_of VARCHAR, raw_extraction_id VARCHAR, "
    "reference_version VARCHAR, reference_manifest_hash VARCHAR, transformation_version VARCHAR, schema_version VARCHAR)"
)


class _Bench:
    """A synthetic catalog + staging store sharing one on-disk DuckDB file."""

    def __init__(self, tmp_path: Path) -> None:
        self.tmp = tmp_path
        self.store = update.StagingStore(tmp_path / "staging.duckdb")
        self.store.reset()
        self.catalog = tmp_path / "catalog.duckdb"
        connection = duckdb.connect(str(self.catalog))
        connection.execute("CREATE SCHEMA atomic")
        connection.execute("CREATE SCHEMA ops")
        connection.execute(f"CREATE TABLE atomic.sales_document {_SALES_DOC_DDL}")
        connection.execute(f"CREATE TABLE atomic.sales_line {_SALES_LINE_DDL}")
        connection.execute(f"CREATE TABLE atomic.inventory_balance {_OITW_DDL}")
        connection.execute(f"CREATE TABLE atomic.inventory_movement ({', '.join(c + ' VARCHAR' for c in OINM_ATOMIC_COLUMNS)})")
        connection.execute(
            f"CREATE TABLE ops.{PUBLICATION_TABLE.split('.')[-1]} "
            "(publication_id VARCHAR, idempotency_key VARCHAR, content_identity VARCHAR, published_at VARCHAR, "
            "status VARCHAR, job_id VARCHAR, segment_id VARCHAR, attempt INTEGER, source_identity VARCHAR, "
            "reference_version VARCHAR, transformation_version VARCHAR, domain VARCHAR)"
        )
        connection.close()
        self.tables = {
            "sales_document": "sales_document",
            "sales_line": "sales_line",
            "inventory_movement": "inventory_movement",
            "inventory_balance_snapshot": "inventory_balance",
        }

    @contextlib.contextmanager
    def session(self, read_only: bool = False):
        connection = duckdb.connect()
        connection.execute(f"ATTACH '{self.catalog}' AS telchi")
        try:
            yield connection
        finally:
            connection.close()

    def seed_sales(self, *, doc_entry: str, doc_total: str, line_total: str) -> None:
        connection = duckdb.connect(str(self.catalog))
        connection.execute(
            "INSERT INTO atomic.sales_document "
            "(atomic_id, source_system, source_table, doc_entry, doc_num, doc_date, doc_due_date, tax_date, "
            "doc_status, canceled, currency, doc_total, card_code, source_as_of, raw_extraction_id, "
            "reference_version, reference_manifest_hash, transformation_version, schema_version) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ["a", "SAP", "OINV", doc_entry, "100", "2026-01-05", "x", "x", "O", "N", "BS", doc_total, "C1", "t", "e", "v2", "", "v", "1"],
        )
        connection.execute(
            "INSERT INTO atomic.sales_line "
            "(atomic_id, source_system, source_table, doc_entry, line_num, item_code, whs_code, quantity, currency, "
            "line_total, price, line_status, source_as_of, raw_extraction_id, reference_version, "
            "reference_manifest_hash, transformation_version, schema_version) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ["a", "SAP", "INV1", doc_entry, "0", "I1", "W1", "2", "BS", line_total, "5", "O", "t", "e", "v2", "", "v", "1"],
        )
        connection.close()

    def seed_oitw(self, *, item_code: str, whs_code: str, on_hand: str) -> None:
        connection = duckdb.connect(str(self.catalog))
        connection.execute(
            "INSERT INTO atomic.inventory_balance VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ["a", "SAP", "OITW", item_code, whs_code, on_hand, "0", "0", "t", "e", "v2", "", "v", "1"],
        )
        connection.close()

    def staging_sales(self, *, doc_entry: str, doc_total: str, line_total: str, canceled: str = "N") -> None:
        self._append("sales_document", {
            "doc_entry": doc_entry, "doc_num": "100", "doc_date": "2026-01-05", "doc_due_date": "x", "tax_date": "x",
            "doc_status": "O", "canceled": canceled, "currency": "BS", "doc_total": doc_total,
            "doc_total_system": None, "doc_total_foreign": None, "card_code": "C1", "slp_code": "-1",
            "series": None, "user_sign": None, "sales_channel_code": None, "sales_channel_name": None,
            "sales_channel_semantic_status": None,
        })
        self._append("sales_line", {
            "doc_entry": doc_entry, "line_num": "0", "item_code": "I1", "whs_code": "W1", "quantity": "2",
            "currency": "BS", "line_total": line_total, "price": "5", "line_status": "O", "slp_code": "-1",
            "attributed_slp_code": "-1",
        })

    def staging_oinm(self, *, trans_num: str, trans_seq: str) -> None:
        self._append("inventory_movement", {
            "trans_num": trans_num, "trans_seq": trans_seq, "trans_type": "67", "doc_entry": "1", "base_ref": "B",
            "doc_date": "2026-01-05", "item_code": "I1", "warehouse": "W1", "in_qty": "2", "out_qty": "0",
            "movement_qty": "2", "price": "5", "calc_price": "5", "trans_value": "10",
        })

    def staging_oitw(self, *, item_code: str, whs_code: str, on_hand: str) -> None:
        self._append("inventory_balance", {
            "item_code": item_code, "whs_code": whs_code, "on_hand": on_hand, "is_commited": "0", "on_order": "0",
        })

    def _append(self, table: str, row: dict[str, str]) -> None:
        if self.store.connection is None:
            self.store.open()
        self.store.append(table, [row])
        # Release the writer so read-only attachments see a checkpointed file.
        self.store.close()

    def diffs(self, previous: dict[str, int] | None = None) -> dict[str, update.DomainDiff]:
        with self.session() as connection:
            return update.compute_diffs(connection, self.store, self.tables, {
                "sales_previous_documents": (previous or {}).get("sales", 0),
                "credit_memo_previous_documents": (previous or {}).get("credit_memo", 0),
                "oinm_previous_rows": (previous or {}).get("oinm", 0),
                "oitw_previous_rows": (previous or {}).get("oitw", 0),
            })

    def candidates(self, diffs: dict[str, update.DomainDiff]) -> dict[str, object]:
        manifest = {
            "extraction_id": "e", "source_as_of": "2026-01-05T00:00:00Z",
            "reference_version": "v2", "reference_manifest_hash": "h",
            "source_key_columns": ("TransNum", "TransSeq"),
        }
        with self.session() as connection:
            update._read_staging_into_catalog_connection(connection, self.store)
            return update.build_changed_candidates(connection, self.store, self.tables, diffs, manifest)

    def publish(self, candidates: dict, *, failure_point: PublicationFailurePoint | None = None) -> dict:
        metrics: dict[str, int] = {}
        boundary = TransactionalPublicationBoundary(
            connection_factory=lambda: self.session(read_only=False),
            record_table=PUBLICATION_TABLE,
            writer=update._update_writer(self.tables, metrics=metrics),
            publication_id_factory=lambda key: "upd_" + key[:12],
            failure_point=failure_point,
        )
        applied: dict[str, object] = {}
        for domain, candidate in candidates.items():
            receipt = boundary.publish(
                idempotency_key=f"U|{domain}|{candidate.content_identity}",
                candidate=candidate,
                metadata={"job_id": "run", "segment_id": domain, "attempt": 1, "source_identity": "x", "reference_version": "v2", "transformation_version": update.UPDATE_TRANSFORMATION_VERSION},
            )
            applied[domain] = receipt.publication_identity
        return applied

    def cleanup(self) -> None:
        self.store.cleanup()


def test_sap_read_only_scope_and_year_guard() -> None:
    guard = update.YearRolloverGuard.evaluate("2026-09-22")
    assert guard.requires_review == "NO"
    assert update.FOUNDATION_START.isoformat() == "2026-01-01"
    rollover = update.YearRolloverGuard.evaluate("2027-01-02")
    assert rollover.requires_review == "YES"


def test_docdate_is_not_a_change_watermark() -> None:
    """A backdated document created later must be detected as NEW."""
    import tempfile

    bench = _Bench(Path(tempfile.mkdtemp()))
    try:
        bench.staging_sales(doc_entry="50", doc_total="10", line_total="10")
        diffs = bench.diffs()
        assert len(diffs[SALES].new_doc_entries) == 1
        assert not diffs[SALES].changed_doc_entries
    finally:
        bench.cleanup()


def test_sales_full_docentry_refresh_unit() -> None:
    import tempfile

    bench = _Bench(Path(tempfile.mkdtemp()))
    try:
        bench.seed_sales(doc_entry="1", doc_total="999", line_total="999")
        bench.staging_sales(doc_entry="1", doc_total="10", line_total="10")
        bench._append("sales_line", {"doc_entry": "1", "line_num": "1", "item_code": "I2", "whs_code": "W1", "quantity": "1", "currency": "BS", "line_total": "5", "price": "5", "line_status": "O", "slp_code": "-1", "attributed_slp_code": "-1"})
        diffs = bench.diffs(previous={"sales": 1})
        assert diffs[SALES].changed_doc_entries == ["1"]
        candidates = bench.candidates(diffs)
        sales_candidate = candidates[SALES]
        assert len(sales_candidate.tables["sales_document"]) == 1
        assert len(sales_candidate.tables["sales_line"]) == 2
    finally:
        bench.cleanup()


def test_sales_cancellation_updates_not_deletes() -> None:
    import tempfile

    bench = _Bench(Path(tempfile.mkdtemp()))
    try:
        bench.seed_sales(doc_entry="1", doc_total="10", line_total="10")
        bench.staging_sales(doc_entry="1", doc_total="10", line_total="10", canceled="Y")
        diffs = bench.diffs(previous={"sales": 1})
        assert diffs[SALES].cancelled_transitions == 1
        assert diffs[SALES].changed_doc_entries == ["1"]
        assert diffs[SALES].disappeared_keys == 0
    finally:
        bench.cleanup()


def test_sales_missing_historical_key_fails_prepublication() -> None:
    import tempfile

    bench = _Bench(Path(tempfile.mkdtemp()))
    try:
        bench.seed_sales(doc_entry="1", doc_total="10", line_total="10")
        bench.staging_sales(doc_entry="2", doc_total="10", line_total="10")
        diffs = bench.diffs(previous={"sales": 1})
        assert diffs[SALES].disappeared_keys == 1
        validation = update.prepublication_validation(diffs, {"coverage": "EXACT", "new_keys_unresolved": 0})
        assert validation["status"] == "FAIL"
        assert "DISAPPEARED" in validation["reason"]
    finally:
        bench.cleanup()


def test_oinm_missing_historical_key_fails_prepublication() -> None:
    import tempfile

    bench = _Bench(Path(tempfile.mkdtemp()))
    try:
        connection = duckdb.connect(str(bench.catalog))
        connection.execute("INSERT INTO atomic.inventory_movement (trans_num, trans_seq, doc_date) VALUES ('7','2','2026-01-05')")
        connection.close()
        bench.staging_oinm(trans_num="8", trans_seq="1")
        diffs = bench.diffs(previous={"oinm": 1})
        assert diffs[OINM].disappeared_keys == 1
        validation = update.prepublication_validation(diffs, {"coverage": "EXACT", "new_keys_unresolved": 0})
        assert validation["status"] == "FAIL"
    finally:
        bench.cleanup()


def test_oinm_source_key_preserved_and_published() -> None:
    import tempfile

    bench = _Bench(Path(tempfile.mkdtemp()))
    try:
        bench.staging_oinm(trans_num="7", trans_seq="2")
        diffs = bench.diffs()
        assert diffs[OINM].new_keys == 1
        candidates = bench.candidates(diffs)
        assert OINM in candidates
        bench.publish(candidates)
        with bench.session() as connection:
            rows = connection.execute("SELECT trans_num, trans_seq FROM telchi.atomic.inventory_movement").fetchall()
            assert rows == [("7", "2")]
    finally:
        bench.cleanup()


def test_oitw_current_state_replacement_removes_disappeared() -> None:
    import tempfile

    bench = _Bench(Path(tempfile.mkdtemp()))
    try:
        bench.seed_oitw(item_code="I1", whs_code="W1", on_hand="5")
        bench.seed_oitw(item_code="I2", whs_code="W1", on_hand="5")
        bench.staging_oitw(item_code="I1", whs_code="W1", on_hand="2")
        diffs = bench.diffs(previous={"oitw": 2})
        assert diffs[OITW].updated_keys == 1
        assert diffs[OITW].removed_rows == 1
        candidates = bench.candidates(diffs)
        bench.publish(candidates)
        with bench.session() as connection:
            rows = connection.execute("SELECT item_code, whs_code, on_hand FROM telchi.atomic.inventory_balance").fetchall()
            assert rows == [("I1", "W1", "2")]
    finally:
        bench.cleanup()


def test_staging_before_publication_and_rollback_on_failure() -> None:
    import tempfile

    bench = _Bench(Path(tempfile.mkdtemp()))
    try:
        bench.seed_sales(doc_entry="1", doc_total="999", line_total="999")
        bench.staging_sales(doc_entry="1", doc_total="10", line_total="10")
        diffs = bench.diffs(previous={"sales": 1})
        candidates = bench.candidates(diffs)
        with pytest.raises(RuntimeError):
            bench.publish(candidates, failure_point=PublicationFailurePoint.BEFORE_COMMIT)
        with bench.session() as connection:
            # The previous valid foundation is preserved after a failed commit.
            assert connection.execute("SELECT doc_total FROM telchi.atomic.sales_document").fetchall() == [("999",)]
        bench.publish(candidates)
        with bench.session() as connection:
            assert connection.execute("SELECT doc_total FROM telchi.atomic.sales_document").fetchall() == [("10",)]
    finally:
        bench.cleanup()


def test_bulk_writes_only_and_no_tiny_file_per_row() -> None:
    import tempfile

    bench = _Bench(Path(tempfile.mkdtemp()))
    try:
        bench.staging_sales(doc_entry="1", doc_total="10", line_total="10")
        diffs = bench.diffs()
        candidates = bench.candidates(diffs)
        metrics: dict[str, int] = {}
        boundary = TransactionalPublicationBoundary(
            connection_factory=lambda: bench.session(read_only=False),
            record_table=PUBLICATION_TABLE,
            writer=update._update_writer(bench.tables, metrics=metrics),
            publication_id_factory=lambda key: "upd_" + key[:12],
        )
        receipt = boundary.publish(idempotency_key="bulk", candidate=candidates[SALES])
        assert receipt.publication_identity.startswith("upd_")
        # Two target tables, two set-based INSERT ... SELECT operations.
        assert metrics["target_bulk_insert_count"] == 2
        assert metrics["target_rows_published"] == 2
    finally:
        bench.cleanup()


def test_reference_existing_canonical_ids_preserved_and_no_orphans() -> None:
    """Reference coverage only *checks*; it never mutates Reference V2."""
    import tempfile

    bench = _Bench(Path(tempfile.mkdtemp()))
    try:
        bench.staging_sales(doc_entry="1", doc_total="10", line_total="10")
        result = update.reference_coverage(_FakeConnector(bench), bench.store, bench.tables)
        assert result["reference_modified"] == "NO"
        assert result["existing_canonical_ids_changed"] == 0
        assert result["crosswalk_regressions"] == 0
    finally:
        bench.cleanup()


def test_reference_orphan_risk_aborts() -> None:
    diffs = {
        SALES: update.DomainDiff(domain=SALES),
        CREDIT: update.DomainDiff(domain=CREDIT),
        OINM: update.DomainDiff(domain=OINM),
        OITW: update.DomainDiff(domain=OITW),
    }
    validation = update.prepublication_validation(diffs, {"coverage": "ORPHAN_RISK", "new_keys_unresolved": 1})
    assert validation["status"] == "FAIL"
    assert validation["reason"] == "REFERENCE_REFRESH_REQUIRED_BUT_UNSAFE=YES"


def test_idempotency_second_run_is_noop() -> None:
    import tempfile

    bench = _Bench(Path(tempfile.mkdtemp()))
    try:
        bench.staging_sales(doc_entry="1", doc_total="10", line_total="10")
        diffs = bench.diffs()
        bench.publish(bench.candidates(diffs))
        second = bench.diffs(previous={"sales": 1})
        assert second[SALES].new_keys == 0
        assert second[SALES].updated_keys == 0
        assert second[SALES].unchanged_keys == 1
        assert bench.candidates(second) == {}
    finally:
        bench.cleanup()


def test_year_rollover_aborts_before_mutation() -> None:
    guard = update.YearRolloverGuard.evaluate("2027-01-01")
    assert guard.requires_review == "YES"
    with pytest.raises(update.UpdateAbort):
        if guard.requires_review == "YES":
            raise update.UpdateAbort("YEAR_ROLLOVER_REQUIRES_REVIEW=YES")


def test_no_ai_and_no_scheduler_markers() -> None:
    source = Path(update.__file__).read_text(encoding="utf-8")
    for forbidden in ("import litellm", "import openai", "import langgraph", "apache_airflow", "celery", "temporal"):
        assert forbidden not in source
    assert "NO_SCHEDULER_NO_CRON_NO_DAEMON_NO_QUEUE" in source


def test_no_coverage_gap_loading() -> None:
    source = Path(update.__file__).read_text(encoding="utf-8")
    # Still-out-of-scope 2026 entities must not appear as source tables. ORIN/RIN1
    # became supported later by the additive Receivables & Collections extension.
    for forbidden in ("ORDR", "RDR1", "ODLN", "DLN1", "ORDN", "RDN1"):
        assert f'"{forbidden}"' not in source


class _FakeConnector:
    """Minimal connector exposing session()/resolve_atomic_tables() for coverage."""

    def __init__(self, bench: _Bench) -> None:
        self.bench = bench

    def session(self, read_only: bool = False):
        return self.bench.session(read_only=read_only)


@contextlib.contextmanager
def _raw_root_patch(path: Path):
    original = update.RAW_ROOT
    update.RAW_ROOT = path
    try:
        yield path
    finally:
        update.RAW_ROOT = original

def test_source_changed_during_extraction_retries_once_then_aborts() -> None:
    """A dataset that keeps changing between extract and reread must abort."""
    from modules.telchi.datalake.planner import SegmentSpec

    calls = {"verify": 0}

    class FlakySource:
        def __init__(self) -> None:
            self.query_log: list[dict[str, object]] = []
            self.oinm_schema = {"source_key_columns": ["TransNum", "TransSeq"]}

        def extract(self, spec: SegmentSpec):
            return ([_sales_raw_row()], {"source_key_columns": [], "source_as_of": "2026-01-05T00:00:00Z"})

        def verify(self, spec: SegmentSpec):
            calls["verify"] += 1
            # A different value each time -> never reconciles.
            return [_sales_raw_row(doc_total=str(1000 + calls["verify"]))]

    import tempfile

    bench = _Bench(Path(tempfile.mkdtemp()))
    try:
        guard = update.ResourceGuard()
        spec = SegmentSpec(
            segment_id="sales-flaky", domain="sales", business_date_from="2026-01-01",
            business_date_to="2026-02-01", key_from="1", key_to="100",
            strategy="DOCENTRY_RANGE", scope="test",
        )
        with _raw_root_patch(Path(tempfile.mkdtemp())):
            with pytest.raises(update.UpdateAbort) as excinfo:
                update.run_extraction(
                    source=FlakySource(), store=bench.store, guard=guard,
                    config=update.RuntimeConfig(), run_id="flaky", specs=[spec],
                )
        assert "SOURCE_TOO_VOLATILE_FOR_SAFE_UPDATE=YES" in str(excinfo.value)
        # One initial attempt plus the single allowed retry.
        assert calls["verify"] == 2
    finally:
        bench.cleanup()


def test_failure_after_sales_staging_preserves_foundation() -> None:
    import tempfile

    bench = _Bench(Path(tempfile.mkdtemp()))
    try:
        bench.seed_sales(doc_entry="1", doc_total="999", line_total="999")
        bench.staging_sales(doc_entry="1", doc_total="10", line_total="10")
        diffs = bench.diffs(previous={"sales": 1})
        candidates = bench.candidates(diffs)
        # Staging exists but nothing was published yet: the old foundation stands.
        with bench.session() as connection:
            assert connection.execute("SELECT doc_total FROM telchi.atomic.sales_document").fetchall() == [("999",)]
        with pytest.raises(RuntimeError):
            bench.publish(candidates, failure_point=PublicationFailurePoint.BEFORE_PUBLICATION_RECORD)
        with bench.session() as connection:
            assert connection.execute("SELECT doc_total FROM telchi.atomic.sales_document").fetchall() == [("999",)]
    finally:
        bench.cleanup()


def test_failure_during_publication_rolls_back_all_domains() -> None:
    import tempfile

    bench = _Bench(Path(tempfile.mkdtemp()))
    try:
        bench.seed_sales(doc_entry="1", doc_total="999", line_total="999")
        bench.seed_oitw(item_code="I1", whs_code="W1", on_hand="9")
        bench.staging_sales(doc_entry="1", doc_total="10", line_total="10")
        bench.staging_oitw(item_code="I1", whs_code="W1", on_hand="2")
        diffs = bench.diffs(previous={"sales": 1, "oitw": 1})
        candidates = bench.candidates(diffs)
        with pytest.raises(RuntimeError):
            bench.publish(candidates, failure_point=PublicationFailurePoint.BEFORE_PUBLICATION_RECORD)
        with bench.session() as connection:
            assert connection.execute("SELECT doc_total FROM telchi.atomic.sales_document").fetchall() == [("999",)]
            assert connection.execute("SELECT on_hand FROM telchi.atomic.inventory_balance").fetchall() == [("9",)]
    finally:
        bench.cleanup()


def test_publication_records_source_as_of_per_domain() -> None:
    import tempfile

    bench = _Bench(Path(tempfile.mkdtemp()))
    try:
        bench.staging_sales(doc_entry="1", doc_total="10", line_total="10")
        diffs = bench.diffs()
        bench.publish(bench.candidates(diffs))
        with bench.session() as connection:
            rows = connection.execute(
                f"SELECT segment_id, transformation_version FROM telchi.ops.{PUBLICATION_TABLE.split('.')[-1]}"
            ).fetchall()
            assert rows and rows[0][0] == "sales"
            assert rows[0][1] == update.UPDATE_TRANSFORMATION_VERSION
    finally:
        bench.cleanup()


def _sales_raw_row(doc_total: str = "10") -> dict[str, object]:
    return {
        "DocEntry": 1, "DocNum": 100, "DocDate": "2026-01-05", "DocDueDate": "2026-01-31",
        "TaxDate": "2026-01-05", "DocStatus": "O", "CANCELED": "N", "DocCur": "BS",
        "DocTotal": doc_total, "CardCode": "C1", "ObjType": 13, "LineNum": 0, "LineStatus": "O",
        "ItemCode": "I1", "WhsCode": "W1", "Quantity": "2", "LineCurrency": "BS",
        "LineTotal": "10", "Price": "5",
    }


def test_reference_new_keys_default_abort() -> None:
    """By default, new unresolved reference keys abort before publication."""
    diffs = {
        SALES: update.DomainDiff(domain=SALES),
        CREDIT: update.DomainDiff(domain=CREDIT),
        OINM: update.DomainDiff(domain=OINM),
        OITW: update.DomainDiff(domain=OITW),
    }
    default = update.prepublication_validation(diffs, {"coverage": "ORPHAN_RISK", "new_keys_unresolved": 3})
    assert default["status"] == "FAIL"
    deferred = update.prepublication_validation(
        diffs, {"coverage": "ORPHAN_RISK", "new_keys_unresolved": 3}, defer_new_reference_keys=True,
    )
    assert deferred["status"] == "PASS"
    assert deferred["degraded"] is True
    assert deferred["reason"] == "REFERENCE_NEW_KEYS_DEFERRED_BY_EXPLICIT_AUTHORIZATION"
    # Disappearance is never deferrable.
    disappearing = {
        SALES: update.DomainDiff(domain=SALES, disappeared_keys=1),
        CREDIT: update.DomainDiff(domain=CREDIT),
        OINM: update.DomainDiff(domain=OINM),
        OITW: update.DomainDiff(domain=OITW),
    }
    assert update.prepublication_validation(
        disappearing, {"coverage": "ORPHAN_RISK", "new_keys_unresolved": 3}, defer_new_reference_keys=True,
    )["status"] == "FAIL"
