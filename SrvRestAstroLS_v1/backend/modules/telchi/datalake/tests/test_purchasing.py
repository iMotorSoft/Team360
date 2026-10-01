"""Permanent contract invariants; snapshot gold is exercised by purchasing_gate."""
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
import contextlib
import json

import pytest

from modules.telchi.datalake.purchasing import (
    ATOMIC, DocumentaryResolver, MovementResolver, PurchasingError,
    base_qty, derive, identity, normalize_atomic, purchase_summary,
)
from modules.telchi.datalake.purchasing_foundation import component_identity, materialize, read_component, create_candidate, pinned_component
from modules.telchi.datalake.foundation_publication import (
    ComponentReference, FoundationPublicationStore, FoundationReaderError, READY_TO_COMMIT, prepare_candidate,
)


def source():
    inputs = {name: [] for name in ATOMIC}
    for name, entry, number, base in (("purchase_order", 1, 90, None),
                                     ("ap_invoice", 2, 90, (22, 1, 0)),
                                     ("purchase_receipt", 3, 90, (18, 2, 0))):
        inputs[name] = [{"DocEntry": entry, "DocNum": number, "CANCELED": "N", "DocDate": "2026-01-10", "CardCode": "S1", "DocStatus": "C"}]
        inputs[name + "_line"] = [{"DocEntry": entry, "LineNum": 0, "ItemCode": "A", "Quantity": "2", "NumPerMsr": "10", "unitMsr": "BOX", "WhsCode": "W1", "LineStatus": "C",
                                  "BaseType": base[0] if base else -1, "BaseEntry": base[1] if base else None, "BaseLine": base[2] if base else None}]
    return inputs


def atomic(inputs=None):
    return normalize_atomic(inputs or source(), snapshot_id="sealed-test")


def movement(**kwargs):
    return {"atomic_id": "M1", "trans_type": "20", "base_ref": "90", "doc_line_num": "0", "item_code": "A", "card_code": "S1", "warehouse": "W1", "in_qty": "20", "out_qty": "0", "doc_date": "2026-01-10", **kwargs}


def coverage():
    return {name: {"absence_window_start": "2026-01-01", "earliest_available_date": "2026-01-10", "latest_available_date": "2026-01-31", "known_historical_gaps": []} for name in ATOMIC}


def resolve(a, m):
    return MovementResolver(a, DocumentaryResolver(a)).resolve(m)


@pytest.mark.parametrize("value", [None, "x", "1.5", float("nan"), float("inf")])
def test_invalid_key_never_coerces_to_zero(value):
    assert identity(value) is None


def test_atomic_retains_source_native_and_uom_factor():
    a = atomic()
    line = a["purchase_order_line"][0]
    assert line["base_quantity"] == "20"
    assert line["num_per_msr"] == "10"
    assert line["unit_msr"] == "BOX"
    assert line["source_native_json"] and line["source_row_hash"]
    assert line["conversion_provenance"] == "SAP.Quantity*SAP.NumPerMsr"


def test_duplicate_atomic_identity_rejected():
    inputs = source()
    inputs["purchase_order_line"] *= 2
    with pytest.raises(PurchasingError, match="duplicate"):
        atomic(inputs)


def test_orphan_header_rejected():
    inputs = source()
    inputs["purchase_order"] = []
    with pytest.raises(PurchasingError, match="orphan"):
        atomic(inputs)


def test_source_header_conflict_rejected():
    inputs = source()
    inputs["ap_invoice_line"][0]["CardCode"] = "OTHER"
    with pytest.raises(PurchasingError, match="mismatch"):
        atomic(inputs)


def test_base_ref_only_is_ambiguous_but_type_selects_document():
    a = atomic()
    row = resolve(a, movement())
    assert row["base_ref_candidate_documents"] == 3
    assert row["collision_detected"]
    assert row["resolution_status"] == "RESOLVED_EXACT"
    assert row["purchasing_doc_entry"] == "3"
    assert row["po_key"][2:] == ["1", "0"]
    assert resolve(a, movement(trans_type="18"))["purchasing_doc_entry"] == "2"


def test_same_family_collision_stays_unresolved():
    inputs = source()
    h, line = deepcopy(inputs["purchase_receipt"][0]), deepcopy(inputs["purchase_receipt_line"][0])
    h["DocEntry"] = line["DocEntry"] = 4
    inputs["purchase_receipt"].append(h)
    inputs["purchase_receipt_line"].append(line)
    row = resolve(atomic(inputs), movement())
    assert row["candidate_count"] == 2
    assert row["resolution_status"] == "UNRESOLVED"
    assert row["target_line_key"] is None


@pytest.mark.parametrize("field,value,reason", [("item_code", "OTHER", "ITEM_MISMATCH"), ("card_code", "OTHER", "SUPPLIER_MISMATCH")])
def test_contradictory_product_or_supplier_cannot_match(field, value, reason):
    row = resolve(atomic(), movement(**{field: value}))
    assert row["resolution_reason"] == reason
    assert row["resolution_status"] == "UNRESOLVED"


def test_missing_supplier_only_supported_if_unique():
    row = resolve(atomic(), movement(card_code=None))
    assert row["resolution_status"] == "RESOLVED_SUPPORTED"
    assert row["card_code_status"] == "ABSENT_BUT_UNIQUE"


def test_warehouse_mismatch_preserved_without_fuzzy_matching():
    row = resolve(atomic(), movement(warehouse="W2"))
    assert row["warehouse"] == "W2"
    assert row["warehouse_match_status"] == "MISMATCH"


def test_missing_document_is_out_of_coverage():
    row = resolve(atomic(), movement(base_ref="999"))
    assert row["resolution_status"] == "OUT_OF_COVERAGE"


def test_missing_line_number_never_matches_by_quantity():
    row = resolve(atomic(), movement(doc_line_num=None))
    assert row["resolution_status"] == "UNRESOLVED"
    assert row["target_line_key"] is None


def test_returns_are_not_subtracted_without_crosswalk():
    row = resolve(atomic(), movement(trans_type="21", in_qty="0", out_qty="20"))
    assert row["resolution_status"] == "NOT_APPLICABLE"
    assert row["resolution_reason"] == "RETURN_CROSSWALK_NOT_SUPPORTED"


def test_source_native_ap_path():
    a = atomic()
    result = DocumentaryResolver(a).resolve(("SAP_HANA", "20", "3", "0"))
    assert [r[1] for r in result["path"]] == ["20", "18", "22"]
    assert result["resolution_status"] == "RESOLVED_EXACT"


def test_cycle_and_max_depth_are_explicit():
    inputs = source()
    inputs["ap_invoice_line"][0].update(BaseType=20, BaseEntry=3)
    a = atomic(inputs)
    key = ("SAP_HANA", "20", "3", "0")
    assert DocumentaryResolver(a).resolve(key)["resolution_reason"] == "CYCLE"
    assert DocumentaryResolver(a, max_depth=1).resolve(key)["resolution_reason"] == "MAX_DEPTH"


def test_missing_base_is_out_of_coverage():
    inputs = source()
    inputs["ap_invoice_line"][0]["BaseEntry"] = 999
    assert DocumentaryResolver(atomic(inputs)).resolve(("SAP_HANA", "20", "3", "0"))["resolution_status"] == "OUT_OF_COVERAGE"


@pytest.mark.parametrize("factor", [None, "0", "-1", "NaN"])
def test_invalid_conversion_remains_unknown(factor):
    assert base_qty({"quantity": "20", "num_per_msr": factor}) is None


def test_multi_receipt_preserves_line_grain_and_warehouses():
    inputs = source()
    h, line = deepcopy(inputs["purchase_receipt"][0]), deepcopy(inputs["purchase_receipt_line"][0])
    inputs["purchase_receipt_line"][0]["Quantity"] = "1"
    h["DocEntry"] = line["DocEntry"] = 4
    h["DocNum"] = 91
    line.update(Quantity="1", WhsCode="W2")
    inputs["purchase_receipt"].append(h); inputs["purchase_receipt_line"].append(line)
    a = atomic(inputs)
    derived, _ = derive(a, [])
    row = purchase_summary(a, derived["purchasing_document_lineage"], coverage=coverage())[0]
    assert row["received_base"] == "20"
    assert row["n_receipts"] == 2 and row["n_receipt_lines"] == 2
    assert row["warehouses_received"] == ["W1", "W2"]
    assert row["status"] == "MULTI_RECEIPT_COMPLETE"


def test_cancelled_receipts_are_retained_and_excluded():
    inputs = source()
    inputs["purchase_receipt"][0]["CANCELED"] = "Y"
    a = atomic(inputs)
    derived, _ = derive(a, [movement()])
    assert len(a["purchase_receipt_line"]) == 1
    assert derived["purchase_inventory_receipt"][0]["effective_status"] == "CANCELLED_OR_UNKNOWN"
    assert purchase_summary(a, derived["purchasing_document_lineage"], coverage=coverage())[0]["received_base"] == "0"


def test_incompatible_uom_never_becomes_zero():
    inputs = source()
    inputs["purchase_receipt_line"][0]["unitMsr"] = "KG"
    a = atomic(inputs); derived, _ = derive(a, [])
    row = purchase_summary(a, derived["purchasing_document_lineage"], coverage=coverage())[0]
    assert row["received_base"] is None and row["status"] == "NOT_DETERMINABLE"


def test_outside_window_never_becomes_no_receipt():
    inputs = source(); inputs["purchase_order"][0]["DocDate"] = "2025-12-31"
    a = atomic(inputs); derived, _ = derive(a, [])
    row = purchase_summary(a, derived["purchasing_document_lineage"], coverage=coverage())[0]
    assert row["received_base"] is None and row["status"] == "OUT_OF_COVERAGE"


def test_duplicate_movements_fail_instead_of_fanout():
    with pytest.raises(PurchasingError, match="duplicate"):
        derive(atomic(), [movement(), movement()])


def test_materialization_roundtrip_idempotent_and_tamper_fails(tmp_path):
    a = atomic(); derived, _ = derive(a, [movement()]); datasets = a | derived
    stable = component_identity(datasets, source={"source": "sealed"}, coverage=coverage(), base={"snapshot_id": 1})
    component = materialize(datasets, stable, data_root=tmp_path)
    assert read_component(component, data_root=tmp_path) == datasets
    assert materialize(datasets, stable, data_root=tmp_path)["component_fingerprint"] == component["component_fingerprint"]
    path = Path(component["datasets"]["purchase_order"]["file_references"][0])
    path.write_bytes(b"damaged")
    with pytest.raises(Exception, match="hash"):
        read_component(component, data_root=tmp_path)


def test_mixed_resolved_and_unknown_rows_roundtrip(tmp_path):
    a = atomic()
    derived, _ = derive(a, [movement(doc_date="2026-01-10T00:00:00"), movement(atomic_id="M2", base_ref="999")])
    datasets = a | derived
    stable = component_identity(datasets, source={}, coverage=coverage(), base={})
    component = materialize(datasets, stable, data_root=tmp_path)
    assert read_component(component, data_root=tmp_path) == datasets


def test_item_mismatch_does_not_become_no_receipt():
    inputs = source()
    inputs["ap_invoice_line"][0]["ItemCode"] = "OTHER"
    a = atomic(inputs); derived, _ = derive(a, [])
    row = purchase_summary(a, derived["purchasing_document_lineage"], coverage=coverage())[0]
    assert row["status"] == "NOT_DETERMINABLE" and row["received_base"] is None


def test_cancelled_intermediate_invoice_never_counts_as_valid_receipt():
    inputs = source(); inputs["ap_invoice"][0]["CANCELED"] = "Y"
    a = atomic(inputs); derived, _ = derive(a, [])
    assert purchase_summary(a, derived["purchasing_document_lineage"], coverage=coverage())[0]["received_base"] == "0"


@pytest.fixture
def store():
    import duckdb
    connection = duckdb.connect()
    @contextlib.contextmanager
    def factory():
        yield connection
    value = FoundationPublicationStore(factory, catalog="")
    value.ensure_schema()
    yield value
    connection.close()


def base(store):
    initial = prepare_candidate(store, update_run_id="base", reference_version="ref-v1")
    refs = {name: ComponentReference(name, name + "-v1", "2026-09-24") for name in ("reference", "sales", "credit_memo", "oinm", "oitw")}
    refs["reference"] = ComponentReference("reference", "ref-v1", "2026-09-24")
    components = {name: ref.as_dict() for name, ref in refs.items()}
    components.update({name: {"publication_id": name + "-v1", "component_fingerprint": "sealed"} for name in ("material_supply", "receivables_collections")})
    store.update_components(initial.foundation_publication_id, refs, manifest={"base_snapshot_id": 42, "components": components})
    store.set_status(initial.foundation_publication_id, READY_TO_COMMIT)
    store.logical_commit(initial.foundation_publication_id)
    return store.get(initial.foundation_publication_id)


def built_component(tmp_path):
    a = atomic(); derived, _ = derive(a, [movement()]); datasets = a | derived
    return materialize(datasets, component_identity(datasets, source={}, coverage=coverage(), base={}), data_root=tmp_path)


def test_candidate_preserves_current_and_all_existing_components(store, tmp_path):
    current = base(store); before = deepcopy(current.as_dict())
    candidate_id = create_candidate(store, base_id=current.foundation_publication_id, component=built_component(tmp_path),
                                    validation={"gold": "PASS", "parity": "PASS", "invariants": "PASS"}, run_id="purchasing")
    assert pinned_component(store, candidate_id)["name"] == "purchasing"
    assert store.current_pointer() == current.foundation_publication_id
    assert store.get(current.foundation_publication_id).as_dict() == before
    assert store.metrics["logical_commit_count"] == 1  # base setup only
    assert set(store.get(candidate_id).manifest["components"]) == set(current.manifest["components"]) | {"purchasing"}


@pytest.mark.parametrize("gate", ["gold", "parity", "invariants"])
def test_candidate_forbidden_on_failed_validation(store, tmp_path, gate):
    current = base(store)
    validation = {"gold": "PASS", "parity": "PASS", "invariants": "PASS", gate: "FAIL"}
    with pytest.raises(PurchasingError, match="must pass"):
        create_candidate(store, base_id=current.foundation_publication_id, component=built_component(tmp_path), validation=validation, run_id="bad")
    assert store.metrics["candidate_create_count"] == 1  # base setup only


def test_pinned_candidate_rejects_version_mixing(store, tmp_path):
    current = base(store)
    cid = create_candidate(store, base_id=current.foundation_publication_id, component=built_component(tmp_path),
                           validation={"gold": "PASS", "parity": "PASS", "invariants": "PASS"}, run_id="purchasing")
    candidate = store.get(cid)
    candidate.manifest["components"]["oinm"]["publication_id"] = "wrong"
    store.update_components(cid, {}, manifest=candidate.manifest)
    with pytest.raises(FoundationReaderError, match="changed"):
        pinned_component(store, cid)


def test_missing_candidate_does_not_fallback_to_current(store):
    base(store)
    with pytest.raises(FoundationReaderError, match="missing"):
        pinned_component(store, "absent")


def test_ten_real_gold_cases_from_sealed_source_evidence():
    from modules.telchi.datalake.purchasing_gate import ap_rules, gold, invariants
    fixture = json.loads((Path(__file__).parent / "fixtures/purchasing_gold_v1.json").read_text())
    a = normalize_atomic(fixture["source"], snapshot_id="real-gold-v1")
    derived, metrics = derive(a, fixture["movements"])
    summary = purchase_summary(a, derived["purchasing_document_lineage"], coverage=fixture["coverage"])
    report = gold(a, derived, {"summary": summary, "ap_results": ap_rules(a, derived, summary)})
    assert report["status"] == "PASS", [c["case"] for c in report["checks"] if not c["pass"]]
    assert invariants(a, derived)["status"] == "PASS"
    assert metrics["collisions_safely_resolved"] > 0
