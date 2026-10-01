"""Offline purchasing build, real gold/parity and candidate-only execution.

Run with an explicit --base-id. Source facts come from sealed capture manifests;
regression expectations are closed investigation evidence, never runtime imports.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from .ducklake import DATA_ROOT, DuckLakeConnector
from .foundation_publication import FoundationPublicationStore, READY_TO_COMMIT, utc_now
from .foundation_reader import FoundationReader
from .material_supply_fact_capture import write_json
from .purchasing import (
    ATOMIC, DERIVED, RESOLVED, VERSION, DocumentaryResolver, base_qty, derive,
    line_key, normalize_atomic, number, purchase_summary, valid, PurchasingError,
)
from .purchasing_foundation import (
    GATE, component_identity, create_candidate, load_source_snapshot,
    materialize, pinned_component, read_component,
)
from .raw import digest, file_hash
from modules.telchi.runtime.config import open_safe_duckdb

EVIDENCE_BASE = Path(__file__).resolve().parents[1] / "investigation/validation"
RECON = EVIDENCE_BASE / "purchase_to_warehouse_receipt_reconciliation_v1/evidence/po_line_reconciliation_20261001T002820.jsonl"
AP = EVIDENCE_BASE / "ap_invoiced_without_warehouse_receipt_v1/evidence/ap_invoice_no_grpo_lines_20261001T014033.jsonl"
OUTPUT = Path("/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi") / GATE


def invariants(atomic: dict, derived: dict) -> dict:
    checks = {}
    lines = {line_key(row): row for name in ATOMIC if name.endswith("_line") for row in atomic[name]}
    for name, rows in atomic.items():
        keys = [(r["source_system"], r["object_type"], r["doc_entry"], r["line_num"] if name.endswith("_line") else None) for r in rows]
        checks[name + "_unique"] = len(keys) == len(set(keys))
        checks[name + "_source_preserved"] = all(r["source_row_hash"] and r["source_native_json"] for r in rows)
        if name.endswith("_line"):
            checks[name + "_base_conversion"] = all(number(r["base_quantity"]) == base_qty(r) for r in rows)
    for edge in derived[DERIVED[0]]:
        if edge["resolution_status"] in RESOLVED:
            if not edge["po_key"] or tuple(edge["po_key"]) not in lines or lines[tuple(edge["po_key"])]["object_type"] != "22":
                checks["rooted_lineage"] = False
    checks.setdefault("rooted_lineage", True)
    movement_keys = [r["movement_key"] for r in derived[DERIVED[1]]]
    checks["no_movement_fanout"] = len(movement_keys) == len(set(movement_keys))
    for row in derived[DERIVED[1]]:
        if row["resolution_status"] in RESOLVED:
            target = lines.get(tuple(row["target_line_key"]))
            if not target or target["object_type"] != str(row["trans_type"]) or target["item_code"] != row["item_code"] or target["line_num"] != str(row["doc_line_num"]) or row["candidate_count"] != 1:
                checks["movement_identity_product"] = False
        elif row["target_line_key"] is not None:
            checks["unknown_not_matched"] = False
    checks.setdefault("movement_identity_product", True)
    checks.setdefault("unknown_not_matched", True)
    return {"status": "PASS" if all(checks.values()) else "FAIL", "checks": checks}


def ap_rules(atomic: dict, derived: dict, summary: list[dict]) -> list[dict]:
    """Snapshot-independent derived categories; never written as atomic facts."""
    invoices = defaultdict(list)
    for row in atomic["ap_invoice_line"]:
        if row["base_type"] == "22" and valid(row):
            invoices[(row["base_entry"], row["base_line"])].append(row)
    po_index = {(r["doc_entry"], r["line_num"]): r for r in atomic["purchase_order_line"]}
    headers = {r["doc_entry"]: r for r in atomic["ap_invoice"]}
    links = defaultdict(list)
    for row in derived["purchase_inventory_receipt"]:
        if row["target_line_key"]:
            links[tuple(row["target_line_key"])].append(row)
    resolver = DocumentaryResolver(atomic)
    # A cancelled documentary receipt still proves that an AP line isn't in
    # the investigated no-document universe; it never counts as valid quantity.
    documented = {tuple(e["po_key"])[2:] for e in derived["purchasing_document_lineage"]
                  if e["target_document_type"] == "purchase_receipt" and e["po_key"]}
    result = []
    for purchase in summary:
        key = (purchase["po_entry"], purchase["line_num"])
        po = po_index[key]
        if po["line_status"] != "C" or key in documented or base_qty(po) is None or base_qty(po) <= 0:
            continue
        options = sorted(invoices.get(key, []), key=lambda r: (r["doc_entry"], r["line_num"]))
        if not options:
            continue
        invoice = options[0]
        if resolver.resolve(line_key(invoice))["resolution_status"] not in RESOLVED:
            continue
        header = headers[invoice["doc_entry"]]
        movements = links.get(line_key(invoice), [])
        inbound = sum((number(m["in_qty"]) for m in movements if m["resolution_status"] in RESOLVED and m.get("effective_status") == "EFFECTIVE"), Decimal(0))
        unknown = any(m["resolution_status"] not in RESOLVED for m in movements)
        unknown = unknown or any(str(m["trans_type"]) == "18" and str(m["base_ref"]) == invoice["doc_num"]
                                 and str(m["doc_line_num"]) == invoice["line_num"] and m["resolution_status"] == "UNRESOLVED"
                                 for m in derived["purchase_inventory_receipt"])
        if purchase["status"] == "OUT_OF_COVERAGE":
            category = "HISTORICAL_LINEAGE_GAP"
        elif unknown:
            category = "NOT_DETERMINABLE"
        elif inbound > 0:
            category = "INVENTORY_ENTRY_WITHOUT_GRPO"
        elif re.search("ANTICIPAD", str(po.get("comments") or "") + str(header.get("comments") or ""), re.I) or (header.get("currency") and header["currency"] != "BS"):
            category = "DIRECT_AP_INVOICE_NO_GRPO"
        else:
            category = "TRUE_INVOICED_WITHOUT_RECEIPT"
        result.append({"po_entry": key[0], "po_line": key[1], "inv_entry": invoice["doc_entry"],
                       "inv_line": invoice["line_num"], "item_code": po["item_code"],
                       "purchased_base": str(base_qty(po)), "category": category,
                       "linked_inbound_base": str(inbound), "warehouse_planned": po["warehouse_code"]})
    return result


def parity(atomic: dict, derived: dict, coverage: dict) -> dict:
    """Compare every gold universe line and source receipt key, not just counts."""
    expected = [json.loads(s) for s in RECON.read_text().splitlines()]
    expected_ap = [json.loads(s) for s in AP.read_text().splitlines()]
    actual = purchase_summary(atomic, derived[DERIVED[0]], coverage=coverage)
    actual_ap = ap_rules(atomic, derived, actual)
    diffs = []
    def compare(exp, got, keys, fields, numeric):
        e = {tuple(r[k] for k in keys): r for r in exp}
        a = {tuple(r[k] for k in keys): r for r in got}
        if len(e) != len(exp) or len(a) != len(got) or set(e) != set(a):
            diffs.append({"universe_key_difference": len(set(e) ^ set(a)), "expected": len(exp), "actual": len(got)})
        for key in sorted(set(e) & set(a)):
            for field in fields:
                x, y = e[key].get(field), a[key].get(field)
                equal = number(x) == number(y) if field in numeric else x == y
                if not equal:
                    diffs.append({"key": key, "field": field, "expected": x, "actual": y})
            if "receipts" in e[key]:
                expected_keys = sorted([[r["receipt_entry"], r["line"]] for r in e[key]["receipts"]])
                if expected_keys != a[key]["receipt_keys"]:
                    diffs.append({"key": key, "field": "receipt_keys"})
    compare(expected, actual, ("po_entry", "line_num"),
            ("item_code", "supplier", "status", "purchased_base", "received_base", "n_receipts", "n_receipt_lines", "warehouses_received"),
            {"purchased_base", "received_base"})
    compare(expected_ap, actual_ap, ("po_entry", "po_line"),
            ("inv_entry", "inv_line", "item_code", "purchased_base", "category", "linked_inbound_base", "warehouse_planned"),
            {"purchased_base", "linked_inbound_base"})
    return {"status": "FAIL" if diffs else "PASS", "differences": diffs,
            "reconciliation_lines": len(actual), "classifications": dict(Counter(r["status"] for r in actual)),
            "ap_lines": len(actual_ap), "ap_classifications": dict(Counter(r["category"] for r in actual_ap)),
            "ap_base_units": str(sum((number(r["purchased_base"]) for r in actual_ap), Decimal(0))),
            "expected_source_hashes": {str(p): file_hash(p) for p in (RECON, AP)},
            "summary": actual, "ap_results": actual_ap}


def gold(atomic: dict, derived: dict, report: dict) -> dict:
    purchases = {(r["po_docnum"], r["line_num"]): r for r in report["summary"]}
    aps = {(r["po_entry"], r["po_line"]): r for r in report["ap_results"]}
    checks = []
    for doc, line, status, ordered, received, count, warehouses in (
        ("262003319", "0", "EXACT_RECEIPT", "25", "25", 1, ["2A-AMD"]),
        ("262000256", "0", "MULTI_RECEIPT_COMPLETE", "11353", "11353", 2, None),
        ("262000013", "0", "PARTIAL_RECEIPT", "1000", "1", 1, None),
        ("262000248", "0", "OVER_RECEIPT", "65000", "67000", 5, None),
        ("262002290", "0", "NO_RECEIPT", "45", "0", 0, None),
        ("262001421", "2", "MULTI_RECEIPT_COMPLETE", "2000", "2000", 2, ["LAB-M1", "SAA-M1"]),
    ):
        row = purchases.get((doc, line), {})
        ok = row.get("status") == status and number(row.get("purchased_base")) == number(ordered) and number(row.get("received_base")) == number(received) and row.get("n_receipts") == count
        if warehouses is not None:
            ok = ok and row.get("warehouses_received") == warehouses
        checks.append({"case": doc + "/" + line, "pass": ok, "actual": row})
    for doc, lines, category in (("262002089", ["0"], "DIRECT_AP_INVOICE_NO_GRPO"),
                                 ("262000492", ["0", "1"], "INVENTORY_ENTRY_WITHOUT_GRPO"),
                                 ("262002290", ["0"], "TRUE_INVOICED_WITHOUT_RECEIPT")):
        for line in lines:
            purchase = purchases.get((doc, line), {})
            row = aps.get((purchase.get("po_entry"), line), {})
            checks.append({"case": "AP:" + doc + "/" + line, "pass": row.get("category") == category, "actual": row})
    receipt_headers = [r for r in atomic["purchase_receipt"] if r["doc_num"] in ("262000014", "262000019")]
    reversal = [r for r in derived[DERIVED[1]] if str(r["trans_type"]) == "20" and str(r["base_ref"]) in ("262000014", "262000019")]
    checks.append({"case": "CANCELLATION_REVERSAL", "pass": sorted(r["canceled"] for r in receipt_headers) == ["C", "Y"] and len(reversal) == 2 and all(r.get("effective_status") == "CANCELLED_OR_UNKNOWN" for r in reversal) and sum((number(r["in_qty"]) - number(r["out_qty"]) for r in reversal), Decimal(0)) == 0,
                   "headers": receipt_headers, "movements": reversal})
    collisions = [r for r in derived[DERIVED[1]] if str(r["base_ref"]) == "262000261" and str(r["trans_type"]) == "20"]
    checks.append({"case": "BASE_REF_COLLISION", "pass": bool(collisions) and all(r["base_ref_candidate_documents"] >= 3 and r["resolution_status"] in RESOLVED and r["purchasing_doc_entry"] == "24669" for r in collisions), "movements": collisions})
    return {"status": "PASS" if all(c["pass"] for c in checks) else "FAIL", "checks": checks, "gold_hash": digest(checks)}


def existing_fingerprints(connector, base: dict) -> dict:
    """Read exact existing files/tables to prove no functional component drift."""
    result = {}
    with connector.session(read_only=True) as db:
        access = FoundationReader(connector).resolve_on(db)
        if access.foundation_publication_id != base["foundation_publication_id"]:
            raise PurchasingError("CURRENT changed during canonical read")
        for component, tables in (("sales", ("sales_document", "sales_line")), ("credit_memo", ("credit_memo_document", "credit_memo_line")), ("oinm", ("inventory_movement",)), ("oitw", ("inventory_balance",)), ("receivables_collections", ("receivable_settlement_status", "collection_method_fact", "commercial_term_classification"))):
            for table in tables:
                relation = access.relation(component, table)
                result[component + ":" + table] = list(db.execute(f"SELECT count(*), bit_xor(hash(t)) FROM {relation} t").fetchone())
        result["reference"] = {name: file_hash(access.reference(name)) for name in ("products", "warehouses", "suppliers")}
    for component in ("material_supply",):
        result[component] = {name: [file_hash(Path(path)) for path in entry["file_references"]] for name, entry in base["components"][component]["datasets"].items()}
    return result


def run(*, base_id: str, run_id: str, evidence_root: Path = OUTPUT) -> dict:
    """Build immutable files then exact pinned candidate; CURRENT is never written."""
    output = evidence_root / run_id
    if output.exists():
        raise PurchasingError("execution evidence already exists")
    output.mkdir(parents=True)
    test = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "modules/telchi/datalake/tests"],
                          cwd=Path(__file__).resolve().parents[3], text=True, capture_output=True)
    test_record = {"command": "python -m pytest -q -p no:cacheprovider modules/telchi/datalake/tests",
                   "exit_code": test.returncode, "stdout": test.stdout, "stderr": test.stderr,
                   "status": "PASS" if test.returncode == 0 else "FAIL"}
    write_json(output / "tests.json", test_record)
    if test.returncode:
        raise PurchasingError("permanent regression tests failed; candidate creation forbidden")
    connector = DuckLakeConnector()
    store = FoundationPublicationStore(connector.session)
    base = store.get(base_id)
    if base is None or store.current_pointer() != base_id:
        raise PurchasingError("explicit base-id must be CURRENT")
    before = digest(base.as_dict())
    snapshot = base.manifest["base_snapshot_id"]
    baseline = existing_fingerprints(connector, base.manifest)
    facts, sources, coverage = load_source_snapshot(DATA_ROOT / "raw/sap/TELCHI_DATALAKE_MATERIAL_SUPPLY_FACT_CAPTURE_V1", ATOMIC[:4])
    extra, extra_sources, extra_coverage = load_source_snapshot(DATA_ROOT / "raw/sap/TELCHI_DATALAKE_MATERIAL_SUPPLY_PURCHASING_LINEAGE_V1", ATOMIC[4:])
    facts.update(extra); sources.update(extra_sources); coverage.update(extra_coverage)
    source_id = digest(sources)
    atomic = normalize_atomic(facts, snapshot_id=source_id)
    with connector.session(read_only=True) as db:
        access = FoundationReader(connector).resolve_on(db)
        if access.foundation_publication_id != base_id:
            raise PurchasingError("CURRENT changed before inventory read")
        movement_snapshot = access.ducklake_snapshot_id
        cursor = db.execute(f"SELECT * FROM {access.oinm()} WHERE trans_type IN ('18','20','21') ORDER BY atomic_id")
        names = [d[0] for d in cursor.description]
        movements = [dict(zip(names, values)) for values in cursor.fetchall()]
    sources["inventory_movement"] = {"publication_id": base.manifest["components"]["oinm"]["publication_id"], "snapshot_id": movement_snapshot,
                                      "scope": "trans_type=18,20,21", "logical_hash": digest(movements)}
    crosswalk_path = Path(base.manifest["reference_closure"]["warehouse_location_crosswalk"])
    if DATA_ROOT.resolve() not in crosswalk_path.resolve().parents:
        raise PurchasingError("warehouse crosswalk outside Data Root")
    with open_safe_duckdb() as db:
        cursor = db.execute("SELECT * FROM read_parquet(?)", [str(crosswalk_path)])
        columns = [d[0] for d in cursor.description]
        warehouse_rows = [dict(zip(columns, values)) for values in cursor.fetchall()]
    warehouse_reference = {r["warehouse_code"]: r for r in warehouse_rows}
    if len(warehouse_reference) != len(warehouse_rows):
        raise PurchasingError("duplicate warehouse crosswalk")
    sources["warehouse_business_location"] = {"reference_version": base.reference_version, "path": str(crosswalk_path), "sha256": file_hash(crosswalk_path)}
    derived, metrics = derive(atomic, movements, warehouse_reference=warehouse_reference)
    invariant_report = invariants(atomic, derived)
    datasets = atomic | derived
    report = parity(atomic, derived, coverage)
    gold_report = gold(atomic, derived, report)
    write_json(output / "parity.json", report)
    write_json(output / "gold.json", gold_report)
    write_json(output / "collision_metrics.json", metrics)
    write_json(output / "coverage.json", coverage)
    write_json(output / "invariants.json", invariant_report)
    write_json(output / "effective_schema.json", {name: {"fields": sorted({field for row in rows for field in row}), "row_count": len(rows), "layer": "atomic" if name in ATOMIC else "derived", "algorithm_version": VERSION} for name, rows in datasets.items()})
    write_json(output / "lineage_samples.json", derived[DERIVED[0]][:20])
    write_json(output / "collision_report.json", [r for r in derived[DERIVED[1]] if r["collision_detected"]])
    if report["status"] != "PASS" or gold_report["status"] != "PASS" or invariant_report["status"] != "PASS":
        raise PurchasingError("gold/parity drift; candidate creation forbidden; inspect evidence")
    stable = component_identity(datasets, source=sources, coverage=coverage,
                                base={"foundation_publication_id": base_id, "base_snapshot_id": snapshot,
                                      "reference_version": base.reference_version, "components_hash": digest(base.manifest["components"])})
    component = materialize(datasets, stable)
    restored = read_component(component)
    restored_atomic = {n: restored[n] for n in ATOMIC}
    restored_derived = {n: restored[n] for n in DERIVED}
    physical_parity = parity(restored_atomic, restored_derived, coverage)
    physical_gold = gold(restored_atomic, restored_derived, physical_parity)
    if physical_parity["status"] != "PASS" or physical_gold["status"] != "PASS" or physical_gold["gold_hash"] != gold_report["gold_hash"]:
        raise PurchasingError("materialized gold/parity drift")
    validation = {"parity": "PASS", "gold": "PASS", "invariants": "PASS", "tests": "PASS", "tests_hash": digest(test_record), "gold_hash": physical_gold["gold_hash"],
                  "parity_hash": digest(physical_parity), "source_snapshot_id": source_id}
    store.acquire_run_lock(run_id, owner=GATE)
    candidate_id = None
    try:
        if digest(store.get(base_id).as_dict()) != before or store.current_pointer() != base_id:
            raise PurchasingError("base changed during build")
        candidate_id = create_candidate(store, base_id=base_id, component=component, validation=validation, run_id=run_id)
        pinned = pinned_component(store, candidate_id)
        if digest(pinned) != digest(component):
            raise PurchasingError("pinned component drift")
        if existing_fingerprints(connector, base.manifest) != baseline:
            raise PurchasingError("existing component data changed")
        store.set_status(candidate_id, READY_TO_COMMIT, validated_at=utc_now())
        if store.current_pointer() != base_id or digest(store.get(base_id).as_dict()) != before:
            raise PurchasingError("CURRENT changed")
    except Exception as exc:
        if candidate_id:
            store.mark_failed(candidate_id, str(exc))
        raise
    finally:
        store.release_run_lock(run_id)
    result = {"gate": GATE + "_PASS", "foundation_candidate_id": candidate_id, "purchasing_publication_id": component["publication_id"],
              "candidate_status": READY_TO_COMMIT, "candidate_manifest_hash": digest(store.get(candidate_id).manifest),
              "FOUNDATION_CURRENT_MODIFIED": "NO", "foundation_current": base_id,
              "PURCHASING_COMPONENT_IMPLEMENTED": "YES", "COLLISION_SAFE_RESOLVER": "PASS",
              "GOLD_CASES": "PASS", "PARITY": "PASS", "CANDIDATE_CREATED": "YES", "READY_FOR_PROMOTION": "YES",
              "SAP_ACCESSED": "NO", "SAP_QUERY_COUNT": 0, "SAP_WRITE_COUNT": 0,
              "metrics": metrics, "row_counts": {n: len(r) for n, r in datasets.items()},
              "gold_hash": physical_gold["gold_hash"], "existing_components_fingerprints": baseline,
              "existing_components_unchanged": True, "version_mixing": False, "fallback_used": False,
              "execution_id": run_id, "finished_at": utc_now(), "evidence_directory": str(output)}
    write_json(output / "component.json", component)
    write_json(output / "candidate_manifest.json", store.get(candidate_id).manifest)
    write_json(output / "summary.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-id", required=True)
    parser.add_argument("--run-id", default="purchasing-v1-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    args = parser.parse_args()
    print(json.dumps(run(base_id=args.base_id, run_id=args.run_id), indent=2, default=str))


if __name__ == "__main__":
    main()
