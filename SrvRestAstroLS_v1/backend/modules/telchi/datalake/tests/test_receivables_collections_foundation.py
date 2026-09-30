from __future__ import annotations

import contextlib
import json
from datetime import date
from decimal import Decimal

import duckdb
import pytest

from modules.telchi.datalake.foundation_publication import (
    CURRENT,
    READY_TO_COMMIT,
    ComponentReference,
    FoundationPublicationStore,
    PublicationBoundaryError,
    prepare_candidate,
)
from modules.telchi.datalake.receivables_collections_foundation import (
    COMPONENT_NAME,
    DATASET_NAMES,
    ReceivablesComponentError,
    analytical_result_hash_v2,
    analytical_result_hash_v3,
    build_component,
    canonical_analytical_json,
    canonical_hash,
    canonicalize_analytical_result,
    create_candidate,
    mark_ready,
    resolve_current,
    validate_pinned_candidate,
)


class Shared:
    def __init__(self):
        self.connection = duckdb.connect(":memory:")

    @contextlib.contextmanager
    def factory(self):
        yield self.connection


@pytest.fixture()
def store():
    shared = Shared()
    value = FoundationPublicationStore(shared.factory, catalog="")
    value.ensure_schema()
    return value


def base(store):
    candidate = prepare_candidate(store, update_run_id="base-run", reference_version="ref-v1")
    refs = {
        "reference": ComponentReference("reference", "ref-v1", "2026-09-24"),
        "sales": ComponentReference("sales", "sales-v1", "2026-09-24"),
        "credit_memo": ComponentReference("credit_memo", "credit-v1", "2026-09-24"),
        "oinm": ComponentReference("oinm", "oinm-v1", "2026-09-24"),
        "oitw": ComponentReference("oitw", "oitw-v1", "2026-09-24"),
    }
    material = {"name": "material_supply", "publication_id": "material-v1", "datasets": {"status": {"file_references": ["x"]}}}
    store.update_components(candidate.foundation_publication_id, refs, source_as_of="2026-09-24", manifest={
        "foundation_publication_id": candidate.foundation_publication_id,
        "candidate_kind": "MATERIAL_SUPPLY_V1",
        "base_snapshot_id": 42,
        "components": {name: ref.as_dict() for name, ref in refs.items()} | {"material_supply": material},
    })
    store.set_status(candidate.foundation_publication_id, READY_TO_COMMIT)
    store.logical_commit(candidate.foundation_publication_id)
    return store.get(candidate.foundation_publication_id)


def component():
    atomic = {"derivation_id": "atomic-v1", "discovery_fingerprint": "discovery", "aging_config_version": "aging-v1"}
    derivation = {
        "derivation_id": "business-v1", "derivation_version": "1.0.0", "source_as_of": "2026-09-28T18:18:35.264000",
        "datasets": [{"DATASET": name, "ROW_COUNT": count} for name, count in zip(DATASET_NAMES, (10, 20, 3))],
    }
    reproducibility = {"after": {name: [count, index + 100] for index, (name, count) in enumerate(zip(DATASET_NAMES, (10, 20, 3)))}}
    return build_component(atomic_contract=atomic, derivation_contract=derivation, reproducibility=reproducibility, business_built_at="audit-only-A")


def test_component_identity_excludes_built_at():
    first = component()
    second = dict(first)
    second["business_derivation_built_at"] = "audit-only-B"
    assert first["publication_id"] == second["publication_id"]
    assert first["component_fingerprint"] == second["component_fingerprint"]


def test_candidate_adds_only_receivables_and_preserves_six(store):
    current = base(store)
    built = component()
    candidate = create_candidate(store, base_publication=current, base_snapshot_id=84, component=built, update_run_id="fresh-run", candidate_created_at="created")
    pinned = validate_pinned_candidate(store, candidate.foundation_publication_id)
    assert set(pinned.component_versions) == set(current.manifest["components"]) | {COMPONENT_NAME}
    for name in current.manifest["components"]:
        assert pinned.manifest["components"][name] == current.manifest["components"][name]
    assert pinned.snapshot_id == 84
    assert pinned.relation("receivable_settlement_status").endswith('AT (VERSION => 84))')
    assert pinned.component["component_fingerprint"] == canonical_hash({key: pinned.component[key] for key in (
        "component_name", "atomic_derivation_id", "atomic_discovery_fingerprint", "derivation_id", "derivation_version",
        "aging_config_version", "source_as_of", "currency_reporting_basis", "historical_asof_grain", "intraday_asof",
        "qr_source_status", "final_contado_business_rule_defined", "datasets",
    )})


def test_productive_resolution_uses_only_current(store):
    current = base(store)
    candidate = create_candidate(store, base_publication=current, base_snapshot_id=84, component=component(), update_run_id="fresh-run", candidate_created_at="created")
    mark_ready(store, candidate.foundation_publication_id)
    store.logical_commit(candidate.foundation_publication_id)
    productive = resolve_current(store)
    assert productive.foundation_publication_id == candidate.foundation_publication_id
    assert productive.reader_mode == "PRODUCTIVE_CURRENT"


def test_missing_receivables_fails_closed(store):
    base(store)
    with pytest.raises(ReceivablesComponentError):
        resolve_current(store)


def test_invalid_component_version_fails_closed(store):
    current = base(store)
    candidate = create_candidate(store, base_publication=current, base_snapshot_id=84, component=component(), update_run_id="fresh-run", candidate_created_at="created")
    with store.connection_factory() as connection:
        publication = store.get(candidate.foundation_publication_id)
        publication.manifest["components"][COMPONENT_NAME]["component_fingerprint"] = "bad"
        connection.execute("UPDATE ops.foundation_publications_v1 SET manifest_json=? WHERE foundation_publication_id=?", [__import__("json").dumps(publication.manifest), candidate.foundation_publication_id])
    with pytest.raises(ReceivablesComponentError, match="fingerprint"):
        validate_pinned_candidate(store, candidate.foundation_publication_id)


def test_missing_receivables_referenced_dataset_fails_closed(store):
    current = base(store)
    candidate = create_candidate(store, base_publication=current, base_snapshot_id=84, component=component(), update_run_id="fresh-run", candidate_created_at="created")
    with store.connection_factory() as connection:
        publication = store.get(candidate.foundation_publication_id)
        del publication.manifest["components"][COMPONENT_NAME]["datasets"]["collection_method_fact"]
        connection.execute("UPDATE ops.foundation_publications_v1 SET manifest_json=? WHERE foundation_publication_id=?", [json.dumps(publication.manifest), candidate.foundation_publication_id])
    with pytest.raises(ReceivablesComponentError, match="datasets are incomplete"):
        validate_pinned_candidate(store, candidate.foundation_publication_id)


def test_invalid_receivables_publication_reference_fails_closed(store):
    current = base(store)
    candidate = create_candidate(store, base_publication=current, base_snapshot_id=84, component=component(), update_run_id="fresh-run", candidate_created_at="created")
    with store.connection_factory() as connection:
        publication = store.get(candidate.foundation_publication_id)
        publication.manifest["components"][COMPONENT_NAME]["publication_id"] = ""
        connection.execute("UPDATE ops.foundation_publications_v1 SET manifest_json=? WHERE foundation_publication_id=?", [json.dumps(publication.manifest), candidate.foundation_publication_id])
    with pytest.raises(ReceivablesComponentError, match="component receivables_collections is incomplete"):
        validate_pinned_candidate(store, candidate.foundation_publication_id)


def test_publication_id_collision_never_overwrites(store):
    prepare_candidate(store, update_run_id="same", reference_version="ref")
    with pytest.raises(PublicationBoundaryError, match="collision"):
        prepare_candidate(store, update_run_id="same", reference_version="ref")


def analytical_payload(*, amount=Decimal("10.00"), **metadata):
    return {
        "query_contract_version": "receivables-gold-v1",
        "receivables_component_version": "receivables-v1",
        "receivables_component_fingerprint": "fingerprint-v1",
        "source_as_of": "2026-09-28T18:18:35.264000",
        "query_name": "current_board",
        "query_version": "1.0.0",
        "scope": {"as_of_date": "2026-09-28"},
        "as_of_date": "2026-09-28",
        "reporting_currency_basis": "bob local",
        "metrics": {"TOTAL_OPEN_RECEIVABLES": amount},
        "semantic_flags": {"HISTORICAL_ASOF_GRAIN": "DAILY_CLOSE"},
        **metadata,
    }


def test_comparator_v2_reproduces_v1_false_mismatch_without_false_negative():
    pinned = analytical_payload(
        reader_mode="EXPLICIT_PINNED_VALIDATION",
        foundation_publication_id="foundation_candidate",
        publication_context="PINNED_CANDIDATE",
        publication_status="READY_TO_COMMIT",
        run_id="v1-pinned-run",
        execution_timestamp="2026-09-29T02:00:00Z",
    )
    productive = analytical_payload(
        reader_mode="PRODUCTIVE_CURRENT",
        foundation_publication_id="foundation_current",
        publication_context="PRODUCTIVE_CURRENT",
        publication_status="CURRENT",
        run_id="v1-productive-run",
        execution_timestamp="2026-09-29T02:30:00Z",
        first_current_snapshot_id=1312,
    )
    assert canonicalize_analytical_result(pinned) == canonicalize_analytical_result(productive)
    assert analytical_result_hash_v2(pinned) == analytical_result_hash_v2(productive)


def test_comparator_v2_detects_true_financial_mismatch():
    pinned = analytical_payload(amount=Decimal("10.00"), reader_mode="EXPLICIT_PINNED_VALIDATION")
    productive = analytical_payload(amount=Decimal("10.01"), reader_mode="PRODUCTIVE_CURRENT")
    assert analytical_result_hash_v2(pinned) != analytical_result_hash_v2(productive)


def test_comparator_v2_numeric_and_set_normalization_is_deterministic():
    first = analytical_payload(amount=Decimal("10.000"))
    second = analytical_payload(amount=10.0)
    first["metrics"]["supported_states"] = {"OPEN", "SETTLED"}
    second["metrics"]["supported_states"] = {"SETTLED", "OPEN"}
    assert analytical_result_hash_v2(first) == analytical_result_hash_v2(second)


def test_comparator_v2_hash_survives_raw_json_evidence_roundtrip():
    in_memory = analytical_payload(amount=Decimal("4263720.230000"))
    persisted = json.loads(json.dumps(in_memory, default=str))
    assert analytical_result_hash_v2(in_memory) == analytical_result_hash_v2(persisted)


ROUNDTRIP_CASES = (
    ("decimal_zero", Decimal("0")),
    ("decimal_zero_scale", Decimal("0.00")),
    ("decimal_52_49", Decimal("52.49")),
    ("decimal_large", Decimal("4263720.23")),
    ("decimal_trailing_scale", Decimal("1115195.2300")),
    ("decimal_negative", Decimal("-20.00")),
    ("nested_dict", {"outer": {"amount": Decimal("52.4900")}}),
    ("decimal_list", [Decimal("0.00"), Decimal("52.49"), Decimal("4263720.2300")]),
    ("dict_insertion_order", {"z": Decimal("2.00"), "a": Decimal("1.00")}),
    ("null", None),
    ("date", date(2026, 9, 28)),
    ("boolean_source_flag", {"source_validated": True, "fallback_used": False}),
    ("very_small_nonzero", Decimal("0.0000000000000000000000001")),
    ("very_large", Decimal("999999999999999999999999999999.9900")),
)


@pytest.mark.parametrize(("case_name", "value"), ROUNDTRIP_CASES, ids=[item[0] for item in ROUNDTRIP_CASES])
def test_comparator_v3_decimal_json_roundtrip_matrix(case_name, value):
    del case_name
    before = analytical_payload(amount=value)
    canonical_before = canonicalize_analytical_result(before)
    hash_before = analytical_result_hash_v3(before)
    persisted = json.loads(json.dumps(before, default=str, sort_keys=False))
    canonical_after = canonicalize_analytical_result(persisted)
    hash_after = analytical_result_hash_v3(persisted)
    assert canonical_before == canonical_after
    assert hash_before == hash_after
    assert canonical_analytical_json(before) == canonical_analytical_json(persisted)


def test_comparator_v3_dict_insertion_order_is_irrelevant():
    first = analytical_payload(amount={"a": Decimal("1.00"), "b": Decimal("2.00")})
    second = analytical_payload(amount={"b": Decimal("2.000"), "a": Decimal("1.0")})
    assert analytical_result_hash_v3(first) == analytical_result_hash_v3(second)


def test_comparator_v3_true_financial_change_changes_hash():
    before = analytical_payload(amount=Decimal("4263720.23"))
    after = analytical_payload(amount=Decimal("4263720.24"))
    assert analytical_result_hash_v3(before) != analytical_result_hash_v3(after)


def test_comparator_v3_non_analytical_metadata_does_not_change_hash():
    pinned = analytical_payload(amount=Decimal("4263720.23"), reader_mode="PINNED")
    productive = analytical_payload(amount=Decimal("4263720.2300"), reader_mode="PRODUCTIVE")
    assert analytical_result_hash_v3(pinned) == analytical_result_hash_v3(productive)
