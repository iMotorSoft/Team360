"""Phase B runner for TELCHI_DATALAKE_MATERIAL_SUPPLY_DERIVATION_AND_CANDIDATE_V1.

Builds and persists the five Material Supply derivations from the immutable raw
facts and the CURRENT Foundation components.  It never opens SAP.

Usage (from ``SrvRestAstroLS_v1/backend``)::

    uv run python modules/telchi/investigation/validation/\
datalake_material_supply_derivation_v1/run_derivation.py --as-of 2026-09-24
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
import time

from modules.telchi.datalake.ducklake import DATA_ROOT
from modules.telchi.datalake.foundation_reader import FoundationReader
from modules.telchi.datalake.material_supply_fact_capture import EVIDENCE_ROOT, read_persisted_rows, write_json
from modules.telchi.datalake.material_supply_derivation import (
    build_actual_consumption,
    build_equivalent_demand,
    build_lead_time_profiles,
    build_open_purchase_pipeline,
    build_parent_index,
    build_supply_status,
    split_bom_raw_materials,
)
from modules.telchi.datalake.material_supply_purchasing_lineage import (
    FACT_CAPTURE_ROOT,
    RAW_ROOT as LINEAGE_RAW_ROOT,
    resolve_receipt_lineage,
    receipt_lead_time_samples,
    index_by_key,
)
from modules.telchi.datalake.raw import write_raw

GATE = "TELCHI_DATALAKE_MATERIAL_SUPPLY_DERIVATION_V1"
BUSINESS_ROOT = DATA_ROOT / "business" / "material_supply" / GATE
SOURCE_AS_OF = "2026-09-24T00:00:00+00:00"
WINDOW_DAYS = 90
RAW_MATERIAL_WAREHOUSES = ("SAA-M1",)


def _hash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def _reference_products(reference_path: Path) -> dict[str, dict[str, Any]]:
    import duckdb
    files = [str(p) for p in (reference_path / "products").glob("*.parquet")]
    if not files:
        return {}
    connection = duckdb.connect()
    try:
        rows = connection.execute(
            "SELECT item_code, canonical_name, inventory_uom_id, sap_invnt_item, "
            "sap_sell_item, sap_prchse_item, sap_itms_grp_cod "
            f"FROM read_parquet({files!r})"
        ).fetchall()
    finally:
        connection.close()
    result = {}
    for item_code, name, uom, inv, sell, prch, grp in rows:
        if item_code:
            result[str(item_code)] = {
                "canonical_name": name, "inventory_uom": uom,
                "inventory_item": inv == "Y", "sell_item": sell == "Y",
                "purchase_item": prch == "Y", "item_group": grp,
            }
    return result


def _foundation_scalars(access: Any, window_start: date, window_end: date) -> dict[str, Any]:
    """Read the pinned Foundation components through one DuckLake connection."""
    from modules.telchi.datalake.ducklake import DuckLakeConnector

    connector = DuckLakeConnector()
    with connector.session(read_only=True) as connection:
        oitw = connection.execute(
            f"SELECT item_code, whs_code, on_hand, is_commited, on_order FROM {access.oitw()}"
        ).fetchall()
        sales = connection.execute(
            f"SELECT l.item_code, SUM(TRY_CAST(l.quantity AS DOUBLE)) FROM {access.sales('sales_line')} l "
            f"JOIN {access.sales('sales_document')} d ON d.doc_entry = l.doc_entry "
            f"WHERE d.doc_date >= ? AND d.doc_date < ? GROUP BY l.item_code",
            [window_start.isoformat(), (window_end + timedelta(days=1)).isoformat()],
        ).fetchall()
        credit = connection.execute(
            f"SELECT l.item_code, SUM(TRY_CAST(l.quantity AS DOUBLE)) FROM {access.credit_memo('credit_memo_line')} l "
            f"JOIN {access.credit_memo('credit_memo_document')} d ON d.doc_entry = l.doc_entry "
            f"WHERE d.doc_date >= ? AND d.doc_date < ? GROUP BY l.item_code",
            [window_start.isoformat(), (window_end + timedelta(days=1)).isoformat()],
        ).fetchall()
    return {
        "stock": [{"item_code": r[0], "whs_code": r[1], "on_hand": r[2], "is_commited": r[3], "on_order": r[4]} for r in oitw],
        "sales_window": {str(r[0]): float(r[1] or 0) for r in sales if r[0]},
        "credit_window": {str(r[0]): float(r[1] or 0) for r in credit if r[0]},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=GATE)
    parser.add_argument("--as-of", default="2026-09-24")
    parser.add_argument("--run-id", default="material-supply-derivation-2026-09-24")
    args = parser.parse_args(argv)
    as_of = date.fromisoformat(args.as_of)
    window_end = as_of
    window_start = as_of - timedelta(days=WINDOW_DAYS)

    access = FoundationReader().get_current_foundation()
    scalars = _foundation_scalars(access, window_start, window_end)
    products = _reference_products(access.reference_path)

    # Raw facts
    bom_headers = read_persisted_rows(FACT_CAPTURE_ROOT, "bom_header")
    bom_lines = read_persisted_rows(FACT_CAPTURE_ROOT, "bom_line")
    issue_lines = read_persisted_rows(FACT_CAPTURE_ROOT, "production_issue")
    po_lines = read_persisted_rows(FACT_CAPTURE_ROOT, "purchase_order_line")
    receipt_lines = read_persisted_rows(FACT_CAPTURE_ROOT, "purchase_receipt_line")
    ap_lines = read_persisted_rows(LINEAGE_RAW_ROOT, "ap_invoice_line")
    po_headers = read_persisted_rows(FACT_CAPTURE_ROOT, "purchase_order")

    base_by_parent = {str(h.get("Code")): float(h.get("Qauntity") or 0) for h in bom_headers}
    edges = split_bom_raw_materials(bom_lines, base_by_parent)
    parents = build_parent_index(edges)
    bom_children = {e["child"] for e in edges}
    bom_parents = {e["parent"] for e in edges}
    raw_materials = sorted(bom_children - bom_parents)

    # Actual consumption
    actual_rows = build_actual_consumption(issue_lines, window_start=window_start, window_end=window_end)
    actual_by_item = {r["item_code"]: r["actual_consumption_qty"] for r in actual_rows}

    # Equivalent demand over the business window. Sales/credit are all-time in the
    # foundation component; we scale by the window fraction defensibly declared.
    # The window filter is applied at document level where available.
    sales_by_item = scalars["sales_window"]
    credit_by_item = scalars["credit_window"]
    demand_rows = build_equivalent_demand(
        raw_materials=raw_materials,
        parents=parents,
        sales_by_item=sales_by_item,
        credit_by_item=credit_by_item,
        window_start=window_start,
        window_end=window_end,
    )
    # Convert the 90-day commercial-equivalent quantity into a daily basis.
    demand_by_item = {r["item_code"]: r["commercial_daily_equivalent_basis_qty"] for r in demand_rows}

    # Purchasing lineage
    lineage_records = resolve_receipt_lineage(receipt_lines, ap_lines, po_lines)
    pipeline_rows = build_open_purchase_pipeline(po_lines, lineage_records)
    po_index = index_by_key(po_lines)
    lead_samples = receipt_lead_time_samples(lineage_records, po_index)
    # Attach origin code from the PO header for lead-time grouping.
    po_origin = {str(h.get("DocEntry")): h.get("U_TIPOCOMPRA") for h in po_headers}
    po_origin.update({str(l.get("DocEntry")): l.get("U_TIPOCOMPRA") for l in po_lines})
    for sample in lead_samples:
        sample["origin_code"] = po_origin.get(str(sample["po_docentry"]))
    lead_profiles = build_lead_time_profiles(lead_samples)

    # Supply status for Saavedra raw-material warehouses. Scope to structural
    # raw materials (BOM component that is not itself a BOM parent) that hold
    # SAA-M1 stock, plus any SAA-M1 item with real production consumption.
    stock_rows = [r for r in scalars["stock"] if str(r.get("whs_code") or "") in RAW_MATERIAL_WAREHOUSES]
    raw_set = set(raw_materials)
    consumed = set(actual_by_item)
    scoped_items = sorted({str(r["item_code"]) for r in stock_rows if str(r["item_code"]) in raw_set or str(r["item_code"]) in consumed})
    stock_rows = [r for r in stock_rows if str(r.get("item_code")) in set(scoped_items)]
    status_items = {
        item: dict(
            products.get(item, {}),
            warehouse="SAA-M1",
            inventory_uom=(products.get(item) or {}).get("inventory_uom"),
            material_class="RAW_MATERIAL" if item in raw_set else "OTHER",
        )
        for item in scoped_items
    }
    status_rows = build_supply_status(
        stock_rows=stock_rows, items=status_items, actual_consumption=actual_by_item,
        equivalent_demand=demand_by_item, open_pipeline=pipeline_rows,
        lead_profiles=lead_profiles, source_as_of=SOURCE_AS_OF, window_days=WINDOW_DAYS,
    )

    datasets = {
        "material_actual_consumption": actual_rows,
        "material_equivalent_demand": demand_rows,
        "open_purchase_pipeline": pipeline_rows,
        "material_lead_time_profile": lead_profiles,
        "material_supply_status": status_rows,
    }
    manifests: dict[str, Any] = {}
    for name, rows in datasets.items():
        manifests[name] = write_raw(
            root=BUSINESS_ROOT, segment_id=f"{name}/full",
            extraction_id=f"{args.run_id}_{name}_full_{time.time_ns()}", rows=rows,
            metadata={
                "gate": GATE, "dataset": name, "segment": "full",
                "source_system": "TELCHI_DATA_LAKE_DERIVATION",
                "source_as_of": SOURCE_AS_OF, "run_id": args.run_id,
                "sap_access_mode": "READ_ONLY", "sap_write_count": 0,
                "foundation_publication_id": access.foundation_publication_id,
                "foundation_components": access.foundation.as_dict(),
            },
        )

    summary = {
        "gate": GATE, "run_id": args.run_id, "as_of": as_of.isoformat(),
        "window_start": window_start.isoformat(), "window_end": window_end.isoformat(),
        "foundation_publication_id": access.foundation_publication_id,
        "foundation_components": access.foundation.as_dict(),
        "sap_write_count": 0,
        "counts": {name: len(rows) for name, rows in datasets.items()},
        "raw_materials": len(raw_materials),
        "lead_samples": len(lead_samples),
        "lead_profiles": len(lead_profiles),
        "manifests": {name: m.get("manifest_path") for name, m in manifests.items()},
    }
    write_json(EVIDENCE_ROOT / "derivation_summary.json", summary)
    write_json(EVIDENCE_ROOT / "material_actual_consumption.json", {k: datasets[k] for k in ["material_actual_consumption"]})
    write_json(EVIDENCE_ROOT / "material_equivalent_demand.json", {"rows": demand_rows})
    write_json(EVIDENCE_ROOT / "open_purchase_pipeline.json", {"rows": pipeline_rows})
    write_json(EVIDENCE_ROOT / "material_lead_time_profile.json", {"rows": lead_profiles})
    write_json(EVIDENCE_ROOT / "material_supply_status.json", {"rows": status_rows})
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())