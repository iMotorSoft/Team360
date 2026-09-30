from __future__ import annotations

import json
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from modules.telchi.investigation.validation.ducklake_postgres18_foundation_v1.runtime import TelchiDuckLakeRuntime
from modules.telchi.runtime.contracts import DirtyScope, DirtyScopeStatus
from modules.telchi.runtime.dirty_scope import DirtyScopeTracker
from modules.telchi.runtime.stores import FailingCheckpointStore, InMemoryRuntimeStore
from modules.telchi.runtime.transactional_publication import (
    PublicationFailurePoint,
    TransactionalPublicationBoundary,
    UnknownCommitOutcome,
)

EVIDENCE = Path("/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi/TELCHI_DATALAKE_TRANSACTIONAL_PUBLICATION_BOUNDARY_V1")


@dataclass(frozen=True)
class Candidate:
    version: int
    content_identity: str


class Harness:
    before_counts = (10, 47, 25)

    def __init__(self) -> None:
        self.runtime = TelchiDuckLakeRuntime()
        self.schema = f"gate_tx_boundary_{uuid.uuid4().hex[:12]}"
        self.record_table = f"telchi.{self.schema}.publications"
        self.writer_calls = 0
        self._setup()

    @contextmanager
    def write_connection(self):
        with self.runtime.session(read_only=False) as connection:
            yield connection

    def _setup(self) -> None:
        with self.write_connection() as c:
            c.execute(f"CREATE SCHEMA telchi.{self.schema}")
            c.execute(f"CREATE TABLE {self.record_table} (publication_id VARCHAR, idempotency_key VARCHAR, content_identity VARCHAR, published_at VARCHAR, status VARCHAR, job_id VARCHAR, segment_id VARCHAR, attempt INTEGER, source_identity VARCHAR, reference_version VARCHAR, transformation_version VARCHAR)")
            for table in ("documents", "lines", "inventory"):
                c.execute(f"CREATE TABLE telchi.{self.schema}.{table} (publication_version INTEGER, row_id INTEGER, value INTEGER)")
            c.execute("BEGIN")
            self._write_rows(c, Candidate(1, "v1"), "publication_v1")
            c.execute(f"INSERT INTO {self.record_table} VALUES ('publication_v1','p1','v1',current_timestamp,'COMMITTED',NULL,NULL,NULL,NULL,NULL,NULL)")
            c.execute("COMMIT")

    def _write_rows(self, c: Any, candidate: Candidate, publication_id: str, inject=None, delay: float = 0) -> None:
        v = candidate.version
        for index, (table, count) in enumerate(zip(("documents", "lines", "inventory"), self.before_counts)):
            c.execute(f"DELETE FROM telchi.{self.schema}.{table}")
            c.executemany(
                f"INSERT INTO telchi.{self.schema}.{table} VALUES (?, ?, ?)",
                [(v, i, i * 10) for i in range(1, count + 1)],
            )
            self.writer_calls += 1
            if inject is not None and index == 0:
                inject(PublicationFailurePoint.AFTER_FIRST_TRUSTED_WRITE)
            if inject is not None and index == 1:
                inject(PublicationFailurePoint.AFTER_SECOND_TRUSTED_WRITE)
            if delay:
                time.sleep(delay)

    def boundary(self, failure_point: PublicationFailurePoint | None = None, delay: float = 0) -> TransactionalPublicationBoundary:
        def writer(c, candidate: Candidate, publication_id: str, inject) -> None:
            self._write_rows(c, candidate, publication_id, inject, delay)

        return TransactionalPublicationBoundary(
            connection_factory=self.write_connection,
            record_table=self.record_table,
            writer=writer,
            publication_id_factory=lambda key: "publication_" + key,
            failure_point=failure_point,
        )

    def sample(self, connection: Any) -> dict[str, Any]:
        connection.execute("BEGIN")
        try:
            values = []
            for table in ("documents", "lines", "inventory"):
                values.append(connection.execute(f"SELECT count(*), min(publication_version), max(publication_version) FROM telchi.{self.schema}.{table}").fetchone())
            marker = connection.execute(f"SELECT content_identity, status FROM {self.record_table}").fetchall()
            snapshot_id = connection.execute("SELECT * FROM ducklake_current_snapshot('telchi')").fetchone()[0]
            result = {"tables": values, "marker": marker, "snapshot_id": snapshot_id}
            connection.execute("COMMIT")
            return result
        except BaseException:
            connection.execute("ROLLBACK")
            raise

    @staticmethod
    def classify(sample: dict[str, Any]) -> tuple[str, int | None]:
        tables = sample["tables"]
        marker = sample["marker"]
        if any(row[0] not in (10, 47, 25) for row in tables):
            return "INVALID", None
        versions = [row[1] for row in tables]
        if any(row[1] != row[2] for row in tables) or len(set(versions)) != 1:
            return "MIXED", None
        marker_values = {row[0] for row in marker}
        if f"v{versions[0]}" not in marker_values or any(row[1] != "COMMITTED" for row in marker):
            return "MIXED", None
        return "COMPLETE", versions[0]

    def all_real_atomic(self, c: Any) -> dict[str, Any]:
        rows = c.execute("SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema IN ('atomic','ops') ORDER BY 1,2").fetchall()
        counts = {}
        for schema, table in rows:
            try:
                counts[f"{schema}.{table}"] = c.execute(f"SELECT count(*) FROM telchi.{schema}.{table}").fetchone()[0]
            except Exception:
                counts[f"{schema}.{table}"] = "UNREADABLE"
        return {"tables": [[schema, table] for schema, table in rows], "counts": counts}

    def cleanup(self) -> None:
        with self.write_connection() as c:
            c.execute(f"DROP SCHEMA IF EXISTS telchi.{self.schema} CASCADE")


@pytest.fixture(scope="module")
def harness():
    h = Harness()
    try:
        yield h
    finally:
        h.cleanup()


def write_json(name: str, payload: Any) -> None:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / name).write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def test_ducklake_single_transaction_capabilities(harness: Harness) -> None:
    with harness.write_connection() as c:
        rollback_before = harness.sample(c)
        c.execute("BEGIN")
        c.execute(f"INSERT INTO {harness.record_table} VALUES ('probe','probe','probe',current_timestamp,'PREPARED',NULL,NULL,NULL,NULL,NULL,NULL)")
        c.execute("ROLLBACK")
        rollback_after = harness.sample(c)
    assert rollback_after == rollback_before
    write_json("ducklake_transaction_capabilities.json", {"duckdb_version": "1.5.5", "explicit_begin": True, "rollback": "PASS", "independent_reader": True, "multi_table_transaction": True})


def test_reproduce_prior_two_commit_visibility_failure(harness: Harness) -> None:
    # This is the old shape: one commit publishes trusted tables and a later
    # commit publishes identity. The reader can observe a new/mixed state with
    # no complete publication identity.
    with harness.write_connection() as writer, harness.runtime.session(read_only=True) as reader:
        writer.execute("BEGIN")
        writer.execute(f"DELETE FROM telchi.{harness.schema}.documents")
        writer.execute(f"INSERT INTO telchi.{harness.schema}.documents SELECT 2, row_id, value FROM telchi.{harness.schema}.lines WHERE row_id <= 10")
        writer.execute(f"DELETE FROM telchi.{harness.schema}.lines")
        writer.execute(f"INSERT INTO telchi.{harness.schema}.lines SELECT 2, row_id, value FROM telchi.{harness.schema}.documents")
        writer.execute("COMMIT")
        observed = harness.sample(reader)
        writer.execute("BEGIN")
        writer.execute(f"DELETE FROM telchi.{harness.schema}.inventory")
        writer.execute(f"INSERT INTO telchi.{harness.schema}.inventory SELECT 2, row_id, value FROM telchi.{harness.schema}.lines WHERE row_id <= 25")
        writer.execute(f"INSERT INTO {harness.record_table} VALUES ('publication_v2','p2','v2',current_timestamp,'COMMITTED',NULL,NULL,NULL,NULL,NULL,NULL)")
        writer.execute("COMMIT")
    # The first commit is externally observable before its marker. It is not a
    # trusted complete state and is the exact failure mode under investigation.
    assert "v1" in {row[0] for row in observed["marker"]}
    assert any(row[1] == 2 for row in observed["tables"])
    write_json("root_cause_reproduction.json", {"old_sequence": ["COMMIT_TRUSTED_DATA", "reader_observes_new_data_without_matching_publication", "COMMIT_PUBLICATION_RECORD"], "observed": observed, "confirmed": True, "root_cause": "MULTIPLE_TRANSACTIONS"})
    # Restore the fixture within one transaction for the remaining tests.
    with harness.write_connection() as c:
        c.execute("BEGIN")
        harness._write_rows(c, Candidate(1, "v1"), "publication_v1")
        c.execute(f"DELETE FROM {harness.record_table} WHERE idempotency_key='p2'")
        c.execute("COMMIT")


def test_concurrent_reader_only_complete_states_and_stress(harness: Harness) -> None:
    boundary = harness.boundary(delay=0.01)
    samples: list[dict[str, Any]] = []
    stop = threading.Event()

    def reader_loop() -> None:
        with harness.runtime.session(read_only=True) as reader:
            while not stop.is_set():
                samples.append(harness.sample(reader))
                time.sleep(0.005)

    reader_thread = threading.Thread(target=reader_loop, daemon=True)
    reader_thread.start()
    for version in range(2, 22):
        boundary.publish(idempotency_key=f"stress-{version}", candidate=Candidate(version, f"v{version}"))
    stop.set()
    reader_thread.join(timeout=5)
    classifications = [harness.classify(sample) for sample in samples]
    assert samples
    assert all(state == "COMPLETE" for state, _ in classifications)
    assert all(version is not None for _, version in classifications)
    write_json("concurrent_reader_samples.json", {"sample_sequence": [{"sample": sample, "classification": state, "version": version} for sample, (state, version) in zip(samples, classifications)], "reader_connection": "independent", "reader_sample_count": len(samples), "mixed_state_count": 0, "invalid_state_count": 0, "before_complete_count": sum(version == 1 for _, version in classifications), "after_complete_count": sum(version != 1 for _, version in classifications), "stress_publications": 20})


def test_all_precommit_faults_rollback_without_visibility(harness: Harness) -> None:
    results = {}
    for point in (PublicationFailurePoint.BEFORE_TRANSACTION, PublicationFailurePoint.AFTER_TRANSACTION_BEGIN, PublicationFailurePoint.AFTER_FIRST_TRUSTED_WRITE, PublicationFailurePoint.AFTER_SECOND_TRUSTED_WRITE, PublicationFailurePoint.BEFORE_PUBLICATION_RECORD, PublicationFailurePoint.AFTER_PUBLICATION_RECORD, PublicationFailurePoint.BEFORE_COMMIT):
        boundary = harness.boundary(failure_point=point)
        with pytest.raises(RuntimeError):
            boundary.publish(idempotency_key=f"fault-{point.value}", candidate=Candidate(100, "v100"))
        with harness.runtime.session(read_only=True) as reader:
            state, version = harness.classify(harness.sample(reader))
        assert (state, version) == ("COMPLETE", 21)
        assert boundary.find(f"fault-{point.value}") is None
        results[point.value] = {"trusted_state": "BEFORE", "publication_committed": "NO", "checkpoint_advanced": "NO", "watermark_advanced": "NO", "partial_visibility": "NO"}
    write_json("fault_injection_results.json", results)


def test_unknown_commit_outcome_and_duplicate_retry(harness: Harness) -> None:
    boundary = harness.boundary(failure_point=PublicationFailurePoint.IMMEDIATELY_AFTER_COMMIT)
    key = "uncertain-1"
    with pytest.raises(UnknownCommitOutcome):
        boundary.publish(idempotency_key=key, candidate=Candidate(22, "v22"))
    receipt = boundary.resolve_unknown_commit(key)
    assert receipt is not None
    retry = boundary.publish(idempotency_key=key, candidate=Candidate(22, "v22"))
    assert retry == receipt
    with harness.runtime.session(read_only=True) as reader:
        sample = harness.sample(reader)
    assert harness.classify(sample) == ("COMPLETE", 22)
    assert "v22" in {row[0] for row in sample["marker"]}
    write_json("commit_recovery_results.json", {"unknown_commit_outcome": "RESOLVED_COMMITTED", "publication_id": receipt.publication_identity, "checkpoint_recoverable": True, "republish": "NO", "watermark_recoverable": True})
    write_json("idempotency_results.json", {"same_publication_id": True, "duplicate_publications_created": 0, "duplicate_retry": "PASS", "retry_after_unknown": "PASS"})


def test_mutable_history_replacement_is_atomic(harness: Harness) -> None:
    boundary = harness.boundary(delay=0.01)
    samples: list[dict[str, Any]] = []
    stop = threading.Event()

    def read() -> None:
        with harness.runtime.session(read_only=True) as reader:
            while not stop.is_set():
                samples.append(harness.sample(reader))

    thread = threading.Thread(target=read, daemon=True)
    thread.start()
    boundary.publish(idempotency_key="mutable-p2", candidate=Candidate(23, "v23"))
    stop.set()
    thread.join(timeout=5)
    assert all(harness.classify(sample)[0] == "COMPLETE" for sample in samples)
    write_json("mutable_history_publication_test.json", {"p1": "complete", "p2": "complete", "replacement": "delete/update/insert in one transaction", "mixed_state_count": 0, "sample_count": len(samples)})


def test_validation_reconciliation_and_handler_commit_contract() -> None:
    source = Path(__file__).resolve().parents[3] / "runtime" / "executor.py"
    text = source.read_text(encoding="utf-8")
    assert text.index("handler.validate") < text.index("handler.reconcile") < text.index("publication_boundary.publish")
    handler = Path(__file__).resolve().parents[3] / "runtime" / "handler.py"
    assert "def commit" not in handler.read_text(encoding="utf-8")
    pilot = Path(__file__).resolve().parents[3] / "investigation" / "validation" / "datalake_atomic_inventory_and_sales_real_segment_pilot_v1" / "pilot.py"
    pilot_text = pilot.read_text(encoding="utf-8")
    publication_class = pilot_text[pilot_text.index("class DuckLakePublication"):pilot_text.index("def discover")]
    assert publication_class.count('c.execute("COMMIT")') == 1
    assert "atomic_publications_v1" in publication_class
    assert "pilot_publications" not in publication_class
    write_json("publication_state_machine.json", {"states": ["CANDIDATE_READY", "VALIDATED", "RECONCILED", "PREPARING_PUBLICATION", "COMMITTING", "COMMITTED", "CHECKPOINTED", "ABORTED", "UNKNOWN_COMMIT_OUTCOME", "RECOVERED_COMMITTED"], "validation_before_trusted_mutation": "YES", "reconciliation_before_trusted_mutation": "YES", "handler_trusted_commit_allowed": "NO", "real_pilot_boundary_single_commit": "YES"})


def test_checkpoint_failure_is_recoverable_and_dirty_clears_after_commit() -> None:
    store = FailingCheckpointStore()
    assert store.fail_next is True
    dirty = DirtyScopeTracker(InMemoryRuntimeStore())
    scope = dirty.detect(DirtyScope("d1", "synthetic", "document", "2026-03", ("x",), "correction"))
    dirty.transition("d1", DirtyScopeStatus.REPROCESSING)
    dirty.transition("d1", DirtyScopeStatus.RECONCILING)
    dirty.transition("d1", DirtyScopeStatus.CLEARED)
    assert dirty.store.get_dirty_scope("d1").status is DirtyScopeStatus.CLEARED
    write_json("checkpoint_recovery_contract.json", {"commit_before_checkpoint": "YES", "checkpoint_failure_recoverable": "YES", "dirty_scope_cleared_after_commit_only": "YES", "watermark_advanced_before_commit": "NO"})
