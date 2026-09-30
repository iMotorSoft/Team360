"""Offline tests for update.py's logical publication boundary orchestration.

These exercise :func:`commit_foundation` and the publish fault matrix without
contacting SAP or touching the real DuckLake catalog. They prove the ordering
``PREPARING -> datasets -> VALIDATING -> READY_TO_COMMIT -> logical commit``
and that any pre-commit failure leaves the previous foundation CURRENT.
"""
from __future__ import annotations

import contextlib

import duckdb
import pytest

from modules.telchi.datalake import update as update_module
from modules.telchi.datalake import foundation_publication as fp


class _SharedDuck:
    def __init__(self) -> None:
        self.connection = duckdb.connect(":memory:")

    def factory(self):
        @contextlib.contextmanager
        def _open():
            yield self.connection

        return _open


@pytest.fixture()
def foundation_store() -> fp.FoundationPublicationStore:
    shared = _SharedDuck()
    store = fp.FoundationPublicationStore(connection_factory=shared.factory(), catalog="")
    store.ensure_schema()
    return store


def _applied() -> dict:
    return {
        "sales": {"publication_id": "pub_sales", "content_identity": "ci_sales", "published_at": "2026-09-22T00:00:01Z", "rows": {"sales_document": 2, "sales_line": 4}},
        "credit_memo": {"publication_id": "pub_credit", "content_identity": "ci_credit", "published_at": "2026-09-22T00:00:01Z", "rows": {"credit_memo_document": 1, "credit_memo_line": 2}},
        "inventory_movement": {"publication_id": "pub_oinm", "content_identity": "ci_oinm", "published_at": "2026-09-22T00:00:02Z", "rows": {"inventory_movement": 20}},
        "inventory": {"publication_id": "pub_oitw", "content_identity": "ci_oitw", "published_at": "2026-09-22T00:00:03Z", "rows": {"inventory_balance": 30}},
    }


def _reference() -> dict:
    return {"reference_version": "v2_test", "reference_path": "/tmp/ref", "reference_source_as_of": "2026-09-22T00:00:00Z"}


def _precommit(status: str = "PASS") -> dict:
    return {"status": status, "published_vs_captured_sap": "EXACT" if status == "PASS" else "MISMATCH"}


def _seed_current(foundation_store: fp.FoundationPublicationStore) -> fp.FoundationPublication:
    candidate = fp.prepare_candidate(foundation_store, update_run_id="run-old", reference_version="v2_old")
    foundation_store.update_components(candidate.foundation_publication_id, {
        "reference": fp.ComponentReference("reference", "v2_old", "t0", None, "h"),
        "sales": fp.ComponentReference("sales", "pub_sales_A", "t1", 1, "h"),
        "credit_memo": fp.ComponentReference("credit_memo", "pub_credit_A", "t1", 1, "h"),
        "oinm": fp.ComponentReference("oinm", "pub_oinm_A", "t2", 1, "h"),
        "oitw": fp.ComponentReference("oitw", "pub_oitw_A", "t3", 1, "h"),
    }, source_as_of="t3", validation_status="PASS")
    foundation_store.set_status(candidate.foundation_publication_id, fp.READY_TO_COMMIT, validated_at="t4")
    foundation_store.logical_commit(candidate.foundation_publication_id)
    return candidate


def test_commit_foundation_success_makes_candidate_current(foundation_store: fp.FoundationPublicationStore) -> None:
    previous = _seed_current(foundation_store)
    candidate = fp.prepare_candidate(foundation_store, update_run_id="run-new", reference_version="v2_test")
    result = update_module.commit_foundation(
        connector=None, foundation_store=foundation_store, candidate=candidate,
        applied=_applied(), reference=_reference(), source_as_of="t",
        precommit_validation=_precommit(), run_id="run-new",
    )
    assert result["status"] == "COMMITTED"
    current = fp.get_current_foundation(foundation_store)
    assert current.foundation_publication_id == candidate.foundation_publication_id
    assert current.sales_publication_id == "pub_sales"
    assert current.oinm_publication_id == "pub_oinm"
    assert current.oitw_publication_id == "pub_oitw"
    assert current.reference_version == "v2_test"
    assert current.component_count == 5
    assert foundation_store.get(previous.foundation_publication_id).status == fp.SUPERSEDED


@pytest.mark.parametrize("point", [
    fp.CommitFaultPoint.DURING_VALIDATION,
    fp.CommitFaultPoint.AFTER_REFERENCE,
    fp.CommitFaultPoint.BEFORE_LOGICAL_COMMIT,
    fp.CommitFaultPoint.DURING_LOGICAL_COMMIT,
])
def test_precommit_faults_preserve_current(foundation_store: fp.FoundationPublicationStore, point: str) -> None:
    previous = _seed_current(foundation_store)
    candidate = fp.prepare_candidate(foundation_store, update_run_id=f"run-{point}", reference_version="v2_test")
    with pytest.raises(Exception):
        update_module.commit_foundation(
            connector=None, foundation_store=foundation_store, candidate=candidate,
            applied=_applied(), reference=_reference(), source_as_of="t",
            precommit_validation=_precommit(), run_id="run-new", fault_point=point,
        )
    current = fp.get_current_foundation(foundation_store)
    assert current.foundation_publication_id == previous.foundation_publication_id
    assert current.sales_publication_id == "pub_sales_A"
    assert foundation_store.current_count() == 1
    assert foundation_store.get(candidate.foundation_publication_id).status == fp.FAILED


def test_failed_precommit_validation_never_commits(foundation_store: fp.FoundationPublicationStore) -> None:
    previous = _seed_current(foundation_store)
    candidate = fp.prepare_candidate(foundation_store, update_run_id="run-bad", reference_version="v2_test")
    with pytest.raises(Exception):
        update_module.commit_foundation(
            connector=None, foundation_store=foundation_store, candidate=candidate,
            applied=_applied(), reference=_reference(), source_as_of="t",
            precommit_validation=_precommit("FAIL"), run_id="run-bad",
        )
    current = fp.get_current_foundation(foundation_store)
    assert current.foundation_publication_id == previous.foundation_publication_id
    assert foundation_store.get(candidate.foundation_publication_id).status == fp.FAILED


def test_postcommit_fault_leaves_new_coherent_foundation(foundation_store: fp.FoundationPublicationStore) -> None:
    _seed_current(foundation_store)
    candidate = fp.prepare_candidate(foundation_store, update_run_id="run-after", reference_version="v2_test")
    with pytest.raises(fp.InjectedFailure):
        update_module.commit_foundation(
            connector=None, foundation_store=foundation_store, candidate=candidate,
            applied=_applied(), reference=_reference(), source_as_of="t",
            precommit_validation=_precommit(), run_id="run-after",
            fault_point=fp.CommitFaultPoint.AFTER_LOGICAL_COMMIT,
        )
    current = fp.get_current_foundation(foundation_store)
    assert current.foundation_publication_id == candidate.foundation_publication_id
    assert current.sales_publication_id == "pub_sales"
    assert foundation_store.current_count() == 1


def test_component_membership_uses_same_foundation_id(foundation_store: fp.FoundationPublicationStore) -> None:
    candidate = fp.prepare_candidate(foundation_store, update_run_id="run-c", reference_version="v2_test")
    update_module.commit_foundation(
        connector=None, foundation_store=foundation_store, candidate=candidate,
        applied=_applied(), reference=_reference(), source_as_of="t",
        precommit_validation=_precommit(), run_id="run-c",
    )
    publication = foundation_store.get(candidate.foundation_publication_id)
    assert publication is not None
    assert publication.component_count == 5
    assert publication.sales_publication_id == "pub_sales"
    assert publication.oinm_publication_id == "pub_oinm"
    assert publication.oitw_publication_id == "pub_oitw"
    # Every component belongs to the committed publication id.
    assert publication.foundation_publication_id == candidate.foundation_publication_id


@pytest.mark.parametrize("fault_point, expected_calls", [
    (fp.CommitFaultPoint.AFTER_SALES, [update_module.SALES_DOMAIN]),
    (fp.CommitFaultPoint.AFTER_CREDIT_MEMO, [update_module.SALES_DOMAIN, update_module.CREDIT_MEMO_DOMAIN]),
    (fp.CommitFaultPoint.AFTER_OINM, [update_module.SALES_DOMAIN, update_module.CREDIT_MEMO_DOMAIN, update_module.OINM_DOMAIN]),
    (fp.CommitFaultPoint.AFTER_OITW, [update_module.SALES_DOMAIN, update_module.CREDIT_MEMO_DOMAIN, update_module.OINM_DOMAIN, update_module.OITW_DOMAIN]),
])
def test_publish_fault_injection_stops_between_domains(fault_point: str, expected_calls: list[str]) -> None:
    """publish() aborts at each physical publication boundary."""
    calls: list[str] = []

    class FakeReceipt:
        def __init__(self, name: str) -> None:
            self.publication_identity = name
            self.content_identity = name + "_ci"
            self.published_at = "t"

    class FakeBoundary:
        def __init__(self, **kwargs) -> None:
            pass

        def publish(self, *, idempotency_key, candidate, metadata=None):
            calls.append(candidate.domain)
            return FakeReceipt("pub_" + candidate.domain)

    class FakeCandidate:
        def __init__(self, domain: str) -> None:
            self.domain = domain
            self.tables = {domain: [1]}
            self.content_identity = domain + "_ci"

    original = update_module.TransactionalPublicationBoundary
    update_module.TransactionalPublicationBoundary = FakeBoundary
    try:
        candidates = {
            update_module.SALES_DOMAIN: FakeCandidate(update_module.SALES_DOMAIN),
            update_module.CREDIT_MEMO_DOMAIN: FakeCandidate(update_module.CREDIT_MEMO_DOMAIN),
            update_module.OINM_DOMAIN: FakeCandidate(update_module.OINM_DOMAIN),
            update_module.OITW_DOMAIN: FakeCandidate(update_module.OITW_DOMAIN),
        }
        with pytest.raises(update_module.UpdateAbort):
            update_module.publish(
                connector=None, store=None, table_names={}, candidates=candidates,
                run_id="run-fault", dry_run=False,
                fault_point=fault_point,
            )
    finally:
        update_module.TransactionalPublicationBoundary = original
    assert calls == expected_calls