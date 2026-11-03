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


def extensible_base(store):
    original = base(store)
    candidate = create_candidate(store, base_publication=original, base_snapshot_id=84,
                                 component=component(), update_run_id="rc-base", candidate_created_at="created")
    mark_ready(store, candidate.foundation_publication_id)
    store.logical_commit(candidate.foundation_publication_id)
    return store.get(candidate.foundation_publication_id)


def extension(store, original, *, name="independent", legacy=False):
    from copy import deepcopy
    from modules.telchi.datalake.foundation_manifest import EXTENSIBLE_KIND
    candidate = prepare_candidate(store, update_run_id="extend-" + name, reference_version=original.reference_version)
    manifest = deepcopy(original.manifest)
    stable = {"contract_version": "1.0.0", "schema_version": "1.0.0", "dataset_hashes": {"extra_data": "a" * 64},
              "source_provenance": {"sealed": "capture-v1"},
              "dependencies": {"foundation_publication_id": original.foundation_publication_id,
                               "base_snapshot_id": 84, "reference_version": original.reference_version,
                               "components_hash": canonical_hash(original.manifest["components"])}}
    sha = canonical_hash(stable)
    extra = {"name": name, "publication_id": name + "_" + sha[:24], "component_fingerprint": sha,
             "content_identity": sha, "stable_contract": stable,
             "datasets": {"extra_data": {"logical_hash": "a" * 64, "row_count": 1,
                                         "file_references": ["sealed.parquet"], "file_hashes": ["b" * 64]}}}
    manifest.update(foundation_publication_id=candidate.foundation_publication_id,
                    candidate_kind="PURCHASING_FOUNDATION_V1" if legacy else EXTENSIBLE_KIND,
                    manifest_schema_version="1.0.0")
    manifest["purchasing_base_publication_id" if legacy else "base_foundation_publication_id"] = original.foundation_publication_id
    manifest["components"][name] = extra
    store.update_components(candidate.foundation_publication_id, original.components,
                            source_as_of=original.source_as_of, manifest=manifest)
    return store.get(candidate.foundation_publication_id)


def replace_manifest(store, publication):
    with store.connection_factory() as db:
        db.execute("UPDATE ops.foundation_publications_v1 SET manifest_json=? WHERE foundation_publication_id=?",
                   [json.dumps(publication.manifest), publication.foundation_publication_id])


@pytest.mark.parametrize("name,legacy", [("purchasing", True), ("future_component", False)])
def test_independent_addition_preserves_required_contract(store, name, legacy):
    original = extensible_base(store)
    before = resolve_current(store)
    added = extension(store, original, name=name, legacy=legacy)
    after = validate_pinned_candidate(store, added.foundation_publication_id)
    assert after.component_versions == before.component_versions
    assert after.component == before.component
    assert after.snapshot_id == before.snapshot_id
    assert name not in after.component_versions
    assert store.current_pointer() == original.foundation_publication_id


@pytest.mark.parametrize("mutation", [
    "missing_required", "wrong_id", "wrong_fingerprint", "wrong_kind", "wrong_schema", "duplicate",
    "invalid_extra", "version_mixing", "snapshot_mixing", "missing_provenance", "missing_base",
    "extra_hash", "foundation_id", "required_schema", "extra_schema", "missing_stable_field",
])
def test_extensible_negative_matrix(store, mutation):
    original = extensible_base(store)
    added = extension(store, original)
    m = added.manifest
    c = m["components"]
    if mutation == "missing_required": del c["sales"]
    elif mutation == "wrong_id": c["receivables_collections"]["publication_id"] = "wrong"
    elif mutation == "wrong_fingerprint": c["receivables_collections"]["component_fingerprint"] = "bad"
    elif mutation == "wrong_kind": m["candidate_kind"] = "UNKNOWN_FOUNDATION_V1"
    elif mutation == "wrong_schema": m["manifest_schema_version"] = "2.0.0"
    elif mutation == "duplicate": c["alias"] = dict(c["receivables_collections"])
    elif mutation == "invalid_extra": c["independent"] = None
    elif mutation == "version_mixing": c["sales"]["publication_id"] = "other-publication"
    elif mutation == "snapshot_mixing": m["base_snapshot_id"] = 85
    elif mutation == "missing_provenance": del c["independent"]["stable_contract"]["source_provenance"]
    elif mutation == "missing_base": m["base_foundation_publication_id"] = "absent"
    elif mutation == "extra_hash": c["independent"]["datasets"]["extra_data"]["logical_hash"] = "bad"
    elif mutation == "foundation_id": m["foundation_publication_id"] = "other"
    elif mutation == "required_schema": c["receivables_collections"]["derivation_version"] = "2.0.0"
    elif mutation == "extra_schema": c["independent"]["stable_contract"]["schema_version"] = "2.0.0"
    elif mutation == "missing_stable_field": del c["receivables_collections"]["aging_config_version"]
    replace_manifest(store, added)
    with pytest.raises(ReceivablesComponentError):
        validate_pinned_candidate(store, added.foundation_publication_id)
    assert store.current_pointer() == original.foundation_publication_id


def test_two_successive_independent_additions_and_material_consumer(store):
    from modules.telchi.datalake.material_supply_candidate import resolve_current_material_supply
    original = extensible_base(store)
    first = extension(store, original, name="future_one")
    mark_ready(store, first.foundation_publication_id)
    store.logical_commit(first.foundation_publication_id)
    second = extension(store, store.get(first.foundation_publication_id), name="future_two")
    pinned = validate_pinned_candidate(store, second.foundation_publication_id)
    assert len(pinned.manifest["components"]) == 9
    assert len(pinned.component_versions) == 7
    mark_ready(store, second.foundation_publication_id)
    store.logical_commit(second.foundation_publication_id)
    assert resolve_current(store).component == original.manifest["components"][COMPONENT_NAME]
    material = resolve_current_material_supply(store)
    assert len(material.component_versions) == 6
    assert material.snapshot_id == 84


def test_legacy_additions_without_extension_provenance_fail(store):
    original = extensible_base(store)
    added = extension(store, original)
    added.manifest["candidate_kind"] = "RECEIVABLES_COLLECTIONS_FOUNDATION_V1"
    replace_manifest(store, added)
    with pytest.raises(ReceivablesComponentError, match="extension envelope"):
        validate_pinned_candidate(store, added.foundation_publication_id)


def test_duplicate_json_logical_key_is_rejected_before_resolution(store):
    original = extensible_base(store)
    manifest_json = json.dumps(original.manifest)
    duplicate_json = manifest_json.replace('"components": {', '"components": {"sales": {"name": "sales", "publication_id": "shadow"},', 1)
    with store.connection_factory() as db:
        db.execute("UPDATE ops.foundation_publications_v1 SET manifest_json=? WHERE foundation_publication_id=?",
                   [duplicate_json, original.foundation_publication_id])
    with pytest.raises(ReceivablesComponentError, match="identity mismatch"):
        resolve_current(store)


@pytest.mark.parametrize("mutation", ["dataset_structure", "dataset_schema", "schema_version", "publication_id", "fingerprint", "stable_field"])
def test_legacy_required_contract_remains_strict(store, mutation):
    original = extensible_base(store)
    c = original.manifest['components'][COMPONENT_NAME]
    if mutation == 'dataset_structure': c['datasets'] = list(DATASET_NAMES)
    elif mutation == 'dataset_schema': c['datasets'][DATASET_NAMES[0]]['ducklake_schema'] = 'atomic'
    elif mutation == 'schema_version': c['derivation_version'] = '2.0.0'
    elif mutation == 'publication_id': c['publication_id'] = 'other'
    elif mutation == 'fingerprint': c['component_fingerprint'] = 'bad'
    elif mutation == 'stable_field': del c['aging_config_version']
    replace_manifest(store, original)
    with pytest.raises(ReceivablesComponentError):
        resolve_current(store)


def test_unhashable_manifest_kind_fails_with_contract_error(store):
    original = extensible_base(store)
    added = extension(store, original)
    added.manifest['candidate_kind'] = ['corrupt']
    replace_manifest(store, added)
    with pytest.raises(ReceivablesComponentError, match='kind'):
        validate_pinned_candidate(store, added.foundation_publication_id)
