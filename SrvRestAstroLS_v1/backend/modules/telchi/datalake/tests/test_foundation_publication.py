"""Contract tests for TELCHI_DATALAKE_GLOBAL_LOGICAL_PUBLICATION_BOUNDARY_V1.

These tests use a real DuckDB connection (in-memory, shared across calls) as the
metadata catalog backing store. They never contact SAP, never touch the real
DuckLake catalog and never write Data Root. They cover the publication model,
the logical-commit atomicity, the fault-injection matrix, the reader contract
and the run lock / stale recovery.
"""
from __future__ import annotations

import contextlib

import duckdb
import pytest

from modules.telchi.datalake.foundation_publication import (
    COMPONENT_NAMES,
    CURRENT,
    FAILED,
    FOUNDATION_COMPONENT_COUNT,
    PREPARING,
    READY_TO_COMMIT,
    SUPERSEDED,
    VALIDATING,
    CommitFaultPoint,
    ComponentReference,
    FoundationPublicationStore,
    FoundationReaderError,
    InjectedFailure,
    get_current_foundation,
    prepare_candidate,
)


class _SharedDuck:
    """A single in-memory DuckDB shared by a connection factory."""

    def __init__(self) -> None:
        self.connection = duckdb.connect(":memory:")

    def factory(self):
        @contextlib.contextmanager
        def _open():
            yield self.connection

        return _open


@pytest.fixture()
def store() -> FoundationPublicationStore:
    shared = _SharedDuck()
    result = FoundationPublicationStore(connection_factory=shared.factory(), catalog="")
    result.ensure_schema()
    return result


def _complete_candidate(store: FoundationPublicationStore, run_id: str = "run-1"):
    candidate = prepare_candidate(store, update_run_id=run_id, reference_version="v2_test")
    components = {
        "reference": ComponentReference("reference", "v2_test", "2026-09-22T00:00:00Z", None, "refhash"),
        "sales": ComponentReference("sales", "pub_sales", "2026-09-22T00:00:01Z", 10, "saleshash"),
        "credit_memo": ComponentReference("credit_memo", "pub_credit", "2026-09-22T00:00:01Z", 5, "credithash"),
        "oinm": ComponentReference("oinm", "pub_oinm", "2026-09-22T00:00:02Z", 20, "oinmhash"),
        "oitw": ComponentReference("oitw", "pub_oitw", "2026-09-22T00:00:03Z", 30, "oitwhash"),
    }
    store.update_components(
        candidate.foundation_publication_id, components,
        source_as_of="2026-09-22T00:00:03Z", validation_status="PASS",
        manifest={"components": {name: c.as_dict() for name, c in components.items()}},
    )
    store.set_status(candidate.foundation_publication_id, VALIDATING)
    store.set_status(candidate.foundation_publication_id, READY_TO_COMMIT, validated_at="2026-09-22T00:00:04Z")
    return candidate


def _commit_new(store: FoundationPublicationStore, run_id: str = "run-1"):
    candidate = _complete_candidate(store, run_id)
    result = store.logical_commit(candidate.foundation_publication_id)
    assert result["status"] == "COMMITTED"
    return candidate


# ---------------------------------------------------------------------------
# Publication model / single current publication
# ---------------------------------------------------------------------------


def test_single_current_publication_after_commit(store: FoundationPublicationStore) -> None:
    candidate = _commit_new(store)
    assert store.current_count() == 1
    assert store.current_pointer() == candidate.foundation_publication_id
    current = store.current_publication()
    assert current is not None and current.status == CURRENT


def test_candidate_is_not_current_before_commit(store: FoundationPublicationStore) -> None:
    candidate = _complete_candidate(store, "run-pre")
    publication = store.get(candidate.foundation_publication_id)
    assert publication is not None and publication.status == READY_TO_COMMIT
    assert store.current_count() == 0
    assert store.current_pointer() is None
    with pytest.raises(FoundationReaderError):
        get_current_foundation(store)


def test_component_membership_is_exactly_five(store: FoundationPublicationStore) -> None:
    candidate = _commit_new(store)
    current = get_current_foundation(store)
    assert current.component_count == FOUNDATION_COMPONENT_COUNT
    assert current.foundation_publication_id == candidate.foundation_publication_id
    assert current.reference_version == "v2_test"
    assert current.sales_publication_id == "pub_sales"
    assert current.oinm_publication_id == "pub_oinm"
    assert current.oitw_publication_id == "pub_oitw"
    publication = store.get(candidate.foundation_publication_id)
    assert publication is not None
    for name in COMPONENT_NAMES:
        assert publication.component(name) is not None


def test_logical_commit_supersedes_previous_and_keeps_it_inspectable(store: FoundationPublicationStore) -> None:
    first = _commit_new(store, "run-a")
    second = _commit_new(store, "run-b")
    assert store.current_count() == 1
    assert store.current_pointer() == second.foundation_publication_id
    old = store.get(first.foundation_publication_id)
    assert old is not None and old.status == SUPERSEDED
    assert old.committed_at is not None
    assert second.previous_foundation_publication_id == first.foundation_publication_id


def test_logical_commit_refuses_incomplete_candidate(store: FoundationPublicationStore) -> None:
    candidate = prepare_candidate(store, update_run_id="run-incomplete", reference_version=None)
    with pytest.raises(Exception):
        store.logical_commit(candidate.foundation_publication_id)
    assert store.current_count() == 0
    assert store.current_pointer() is None


# ---------------------------------------------------------------------------
# Fault-injection matrix (pre-commit preserves A, post-commit gives coherent B)
# ---------------------------------------------------------------------------


def _apply_fault(store: FoundationPublicationStore, point: str) -> bool:
    """Return True if the logical commit still happened (post-commit fault)."""
    store.fault_point = point
    candidate = _complete_candidate(store, f"run-{point}")
    committed = False
    try:
        store.logical_commit(candidate.foundation_publication_id)
        committed = True
    except InjectedFailure:
        store.mark_failed(candidate.foundation_publication_id, point)
    return committed


@pytest.mark.parametrize("point", [
    CommitFaultPoint.DURING_VALIDATION,
    CommitFaultPoint.AFTER_REFERENCE,
    CommitFaultPoint.BEFORE_LOGICAL_COMMIT,
    CommitFaultPoint.DURING_LOGICAL_COMMIT,
])
def test_precommit_faults_preserve_previous_current(store: FoundationPublicationStore, point: str) -> None:
    first = _commit_new(store, "run-old")
    committed = _apply_fault(store, point)
    assert committed is False
    assert store.current_count() == 1
    assert store.current_pointer() == first.foundation_publication_id
    current = get_current_foundation(store)
    assert current.foundation_publication_id == first.foundation_publication_id
    # Exactly one CURRENT; the failed candidate never became CURRENT.
    assert store.current_count() == 1


def test_fail_during_commit_is_atomic_no_ambiguity(store: FoundationPublicationStore) -> None:
    first = _commit_new(store, "run-old")
    store.fault_point = CommitFaultPoint.DURING_LOGICAL_COMMIT
    candidate = _complete_candidate(store, "run-during")
    with pytest.raises(InjectedFailure):
        store.logical_commit(candidate.foundation_publication_id)
    # Rolled back: pointer and statuses are exactly the previous state.
    assert store.current_pointer() == first.foundation_publication_id
    assert store.current_count() == 1
    candidate_row = store.get(candidate.foundation_publication_id)
    assert candidate_row is not None and candidate_row.status == READY_TO_COMMIT
    assert store.metrics["logical_commit_rollback_count"] >= 1


def test_fail_after_commit_leaves_new_valid_foundation(store: FoundationPublicationStore) -> None:
    _commit_new(store, "run-old")
    store.fault_point = CommitFaultPoint.AFTER_LOGICAL_COMMIT
    candidate = _complete_candidate(store, "run-after")
    with pytest.raises(InjectedFailure):
        store.logical_commit(candidate.foundation_publication_id)
    # The commit already happened; the foundation is coherent B, not ambiguous.
    assert store.current_count() == 1
    assert store.current_pointer() == candidate.foundation_publication_id
    current = get_current_foundation(store)
    assert current.foundation_publication_id == candidate.foundation_publication_id
    assert current.sales_publication_id == "pub_sales"


# ---------------------------------------------------------------------------
# Reader contract / fail-closed
# ---------------------------------------------------------------------------


def test_reader_never_mixes_component_versions(store: FoundationPublicationStore) -> None:
    first = _commit_new(store, "run-a")
    # Perturb B's components so a mix would be detectable.
    second = prepare_candidate(store, update_run_id="run-b", reference_version="v2_new")
    store.update_components(second.foundation_publication_id, {
        "reference": ComponentReference("reference", "v2_new", "t", None, "h"),
        "sales": ComponentReference("sales", "pub_sales_B", "t", 1, "h"),
        "credit_memo": ComponentReference("credit_memo", "pub_credit_B", "t", 1, "h"),
        "oinm": ComponentReference("oinm", "pub_oinm_B", "t", 1, "h"),
        "oitw": ComponentReference("oitw", "pub_oitw_B", "t", 1, "h"),
    }, source_as_of="t", validation_status="PASS")
    store.set_status(second.foundation_publication_id, READY_TO_COMMIT, validated_at="t")
    # Before commit the reader must still return A's five components.
    before = get_current_foundation(store)
    assert before.foundation_publication_id == first.foundation_publication_id
    assert before.sales_publication_id == "pub_sales"
    assert before.reference_version == "v2_test"
    store.logical_commit(second.foundation_publication_id)
    after = get_current_foundation(store)
    assert after.sales_publication_id == "pub_sales_B"
    assert after.reference_version == "v2_new"
    assert after.foundation_publication_id == second.foundation_publication_id


def test_reader_fails_closed_when_pointer_missing(store: FoundationPublicationStore) -> None:
    with pytest.raises(FoundationReaderError):
        get_current_foundation(store)


def test_reader_fails_closed_when_component_missing(store: FoundationPublicationStore) -> None:
    candidate = prepare_candidate(store, update_run_id="run-partial", reference_version="v2")
    store.update_components(candidate.foundation_publication_id, {
        "reference": ComponentReference("reference", "v2", "t", None, "h"),
        "sales": ComponentReference("sales", "pub_sales", "t", 1, "h"),
        "oinm": ComponentReference("oinm", None, None, None, None),
        "oitw": ComponentReference("oitw", "pub_oitw", "t", 1, "h"),
    }, source_as_of="t", validation_status="PASS")
    # A partial candidate must never become CURRENT. The logical commit refuses
    # it (fail closed) and the reader also fails closed because nothing coherent
    # is resolvable.
    with pytest.raises(Exception):
        store.logical_commit(candidate.foundation_publication_id)
    assert store.current_count() == 0
    assert store.current_pointer() is None
    with pytest.raises(FoundationReaderError):
        get_current_foundation(store)


def test_reader_fails_closed_on_corrupt_pointer(store: FoundationPublicationStore) -> None:
    candidate = _commit_new(store)
    with store.connection_factory() as connection:
        connection.execute("UPDATE ops.foundation_current_v1 SET foundation_publication_id = 'missing'")
    with pytest.raises(FoundationReaderError):
        get_current_foundation(store)


def test_reader_reports_two_current_as_error(store: FoundationPublicationStore) -> None:
    first = _commit_new(store, "run-a")
    second = _commit_new(store, "run-b")
    # Force a corrupt double-CURRENT state directly to prove fail-closed.
    with store.connection_factory() as connection:
        connection.execute(
            "UPDATE ops.foundation_publications_v1 SET status = 'CURRENT' WHERE foundation_publication_id = ?",
            [first.foundation_publication_id],
        )
    with pytest.raises(FoundationReaderError):
        get_current_foundation(store)
    assert second.foundation_publication_id != first.foundation_publication_id


# ---------------------------------------------------------------------------
# Run lock / stale recovery
# ---------------------------------------------------------------------------


def test_active_run_guard_aborts_second_run(store: FoundationPublicationStore) -> None:
    first = store.acquire_run_lock("run-1")
    assert first["status"] == "ACQUIRED"
    second = store.acquire_run_lock("run-2")
    assert second["status"] == "ACTIVE_UPDATE_RUN_DETECTED"
    assert second["current_pointer_unchanged"] == "YES"


def test_stale_run_is_abandoned_without_touching_current(store: FoundationPublicationStore) -> None:
    current = _commit_new(store, "run-current")
    store.acquire_run_lock("run-stale")
    result = store.acquire_run_lock("run-new", stale_after_seconds=0)
    assert result["status"] == "ACQUIRED"
    assert result["STALE_CANDIDATE_FOUND"] == "YES"
    assert store.current_pointer() == current.foundation_publication_id
    assert get_current_foundation(store).foundation_publication_id == current.foundation_publication_id


def test_abandon_stale_candidates_keeps_current(store: FoundationPublicationStore) -> None:
    current = _commit_new(store, "run-current")
    stale = prepare_candidate(store, update_run_id="run-stale", reference_version="v2")
    abandoned = store.abandon_stale_candidates()
    assert stale.foundation_publication_id in abandoned
    assert store.current_pointer() == current.foundation_publication_id
    assert store.get(stale.foundation_publication_id).status == FAILED


def test_logical_commit_is_idempotent(store: FoundationPublicationStore) -> None:
    candidate = _commit_new(store, "run-idem")
    again = store.logical_commit(candidate.foundation_publication_id)
    assert again["status"] == "ALREADY_CURRENT"
    assert store.current_count() == 1


def test_exact_logical_rollback_is_atomic_and_compare_and_swap(store: FoundationPublicationStore) -> None:
    old = _commit_new(store, "run-old")
    new = _commit_new(store, "run-new")
    result = store.logical_rollback(
        old.foundation_publication_id,
        expected_current_foundation_publication_id=new.foundation_publication_id,
        reason="post-promotion validation failed",
    )
    assert result["status"] == "ROLLED_BACK"
    assert store.current_pointer() == old.foundation_publication_id
    assert store.current_count() == 1
    assert store.get(new.foundation_publication_id).status == SUPERSEDED


def test_logical_rollback_refuses_stale_expected_current(store: FoundationPublicationStore) -> None:
    old = _commit_new(store, "run-old")
    new = _commit_new(store, "run-new")
    with pytest.raises(Exception, match="compare-and-swap"):
        store.logical_rollback(
            old.foundation_publication_id,
            expected_current_foundation_publication_id="foundation_stale",
            reason="must not move pointer",
        )
    assert store.current_pointer() == new.foundation_publication_id


def test_set_status_cannot_forge_current(store: FoundationPublicationStore) -> None:
    candidate = prepare_candidate(store, update_run_id="run-forge", reference_version="v2")
    with pytest.raises(Exception):
        store.set_status(candidate.foundation_publication_id, CURRENT)
    assert store.current_count() == 0