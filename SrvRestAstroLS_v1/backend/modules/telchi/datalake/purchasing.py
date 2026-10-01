"""Purchasing V1: source facts, deterministic documentary lineage and rules.

Pure domain code. No SAP, publication selection, filesystem or investigation
imports. Ambiguous and missing evidence never becomes a guessed relationship.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from .raw import digest

VERSION = "purchasing-v1.0.0"
FAMILIES = {"22": "purchase_order", "20": "purchase_receipt", "18": "ap_invoice"}
ATOMIC = tuple(name for family in FAMILIES.values() for name in (family, family + "_line"))
DERIVED = ("purchasing_document_lineage", "purchase_inventory_receipt")
RESOLVED = {"RESOLVED_EXACT", "RESOLVED_SUPPORTED"}
FIELDS = {
    "DocEntry": "doc_entry", "DocNum": "doc_num", "LineNum": "line_num",
    "CardCode": "card_code", "ItemCode": "item_code", "DocDate": "doc_date",
    "DocDueDate": "doc_due_date", "CANCELED": "canceled", "DocStatus": "doc_status",
    "Quantity": "quantity", "NumPerMsr": "num_per_msr", "unitMsr": "unit_msr",
    "UomCode": "uom_code", "WhsCode": "warehouse_code", "OpenQty": "open_qty",
    "LineStatus": "line_status", "BaseType": "base_type", "BaseEntry": "base_entry",
    "BaseLine": "base_line", "DocCur": "currency", "Currency": "line_currency",
    "DocTotal": "doc_total", "LineTotal": "line_total", "Price": "price",
    "Comments": "comments", "NumAtCard": "num_at_card", "ShipDate": "ship_date",
    "U_TIPOCOMPRA": "tipo_compra", "Dscription": "description",
}
IDENTITY_FIELDS = {"doc_entry", "doc_num", "line_num", "base_type", "base_entry", "base_line"}


class PurchasingError(ValueError):
    """The purchasing contract cannot be honored."""


def number(value: Any) -> Decimal | None:
    try:
        result = Decimal(str(value))
        return result if result.is_finite() else None
    except (InvalidOperation, ValueError, TypeError):
        return None


def identity(value: Any) -> str | None:
    value = number(value)
    return str(int(value)) if value is not None and value == value.to_integral_value() else None


def base_qty(row: Mapping[str, Any]) -> Decimal | None:
    qty, factor = number(row.get("quantity")), number(row.get("num_per_msr"))
    return qty * factor if qty is not None and factor is not None and factor > 0 else None


def valid(row: Mapping[str, Any]) -> bool:
    return row.get("canceled") == "N"


def line_key(row: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return (row["source_system"], row["object_type"], row["doc_entry"], row["line_num"])


def normalize_atomic(inputs: Mapping[str, list[dict]], *, snapshot_id: str) -> dict[str, list[dict]]:
    """Retain every source field, exact keys, factor and technical conversion."""
    if set(inputs) != set(ATOMIC):
        raise PurchasingError("six atomic datasets required")
    result: dict[str, list[dict]] = {}
    for object_type, family in FAMILIES.items():
        headers: dict[str, dict] = {}
        for dataset in (family, family + "_line"):
            rows, keys = [], set()
            for source in inputs[dataset]:
                row = {target: source.get(field) for field, target in FIELDS.items()}
                for field in IDENTITY_FIELDS:
                    row[field] = identity(row[field])
                row.update(source_system="SAP_HANA", object_type=object_type,
                           snapshot_id=snapshot_id, source_row_hash=digest(source),
                           source_native_json=json.dumps(source, sort_keys=True, default=str))
                if row["doc_entry"] is None or int(row["doc_entry"]) < 0:
                    raise PurchasingError(f"invalid DocEntry in {dataset}")
                if dataset.endswith("_line"):
                    if row["line_num"] is None or int(row["line_num"]) < 0:
                        raise PurchasingError(f"invalid LineNum in {dataset}")
                    header = headers.get(row["doc_entry"])
                    if header is None:
                        raise PurchasingError(f"orphan header in {dataset}")
                    for field in ("doc_num", "card_code", "doc_date", "canceled", "doc_status"):
                        if row[field] is None:
                            row[field] = header[field]
                        elif header[field] is not None and str(row[field]) != str(header[field]):
                            raise PurchasingError(f"header/line {field} mismatch in {dataset}")
                    converted = base_qty(row)
                    row.update(base_quantity=str(converted) if converted is not None else None,
                               conversion_status="SUPPORTED" if converted is not None else "UNKNOWN",
                               conversion_provenance="SAP.Quantity*SAP.NumPerMsr" if converted is not None else None)
                    key = line_key(row)
                else:
                    key = (row["source_system"], object_type, row["doc_entry"])
                    headers[row["doc_entry"]] = row
                if key in keys:
                    raise PurchasingError(f"duplicate identity in {dataset}: {key}")
                keys.add(key)
                rows.append(json.loads(json.dumps(row, default=str)))
            result[dataset] = sorted(rows, key=lambda r: (int(r["doc_entry"]), int(r["line_num"] or 0)))
    return result


def compatible(left: Mapping, right: Mapping) -> bool:
    if base_qty(left) is None or base_qty(right) is None:
        return False
    a, b = left.get("unit_msr"), right.get("unit_msr")
    if a is not None and b is not None:
        return a == b
    return a is None and b is None and number(left.get("num_per_msr")) == number(right.get("num_per_msr"))


class DocumentaryResolver:
    def __init__(self, atomic: Mapping[str, list[dict]], *, max_depth: int = 8):
        self.lines = {line_key(row): row for family in FAMILIES.values() for row in atomic[family + "_line"]}
        if len(self.lines) != sum(len(atomic[f + "_line"]) for f in FAMILIES.values()):
            raise PurchasingError("duplicate documentary key")
        self.max_depth = max_depth

    def resolve(self, key: tuple, *, seen: tuple = ()) -> dict:
        base = {"resolution_status": "UNRESOLVED", "resolution_method": VERSION,
                "po_key": None, "path": [], "resolution_reason": "UNKNOWN"}
        if key in seen:
            return base | {"resolution_reason": "CYCLE"}
        if len(seen) >= self.max_depth:
            return base | {"resolution_reason": "MAX_DEPTH"}
        row = self.lines.get(key)
        if row is None:
            return base | {"resolution_status": "OUT_OF_COVERAGE", "resolution_reason": "BASE_LINE_NOT_MATERIALIZED"}
        if key[1] == "22":
            return base | {"resolution_status": "RESOLVED_EXACT", "resolution_reason": "SOURCE_NATIVE",
                           "po_key": list(key), "path": [list(key)]}
        bt, be, bl = row.get("base_type"), row.get("base_entry"), row.get("base_line")
        if bt == "-1":
            return base | {"resolution_status": "NOT_APPLICABLE", "resolution_reason": "NO_BASE_DOCUMENT"}
        if bt not in FAMILIES or be is None or bl is None or int(be) < 0 or int(bl) < 0:
            return base | {"resolution_reason": "INVALID_OR_UNSUPPORTED_BASE"}
        target_key = (key[0], bt, be, bl)
        target = self.lines.get(target_key)
        if target is None:
            return base | {"resolution_status": "OUT_OF_COVERAGE", "resolution_reason": "BASE_LINE_NOT_MATERIALIZED",
                           "path": [list(key), list(target_key)]}
        evidence_path = [list(key), list(target_key)]
        if not row.get("item_code") or not target.get("item_code"):
            return base | {"resolution_reason": "ITEM_UNKNOWN", "path": evidence_path}
        if row["item_code"] != target["item_code"]:
            return base | {"resolution_reason": "ITEM_MISMATCH", "path": evidence_path}
        if row.get("card_code") and target.get("card_code") and row["card_code"] != target["card_code"]:
            return base | {"resolution_reason": "SUPPLIER_MISMATCH", "path": evidence_path}
        resolved = self.resolve(target_key, seen=seen + (key,))
        return resolved | {"path": [list(key)] + resolved["path"]}

    def lineage(self) -> list[dict]:
        edges = []
        for key, row in sorted(self.lines.items()):
            if key[1] == "22":
                continue
            result = self.resolve(key)
            bt, be, bl = row.get("base_type"), row.get("base_entry"), row.get("base_line")
            target_key = (key[0], bt, be, bl)
            target = self.lines.get(target_key)
            # Immediate source-native edge and the full rooted path coexist.
            immediate = "RESOLVED_EXACT" if target else result["resolution_status"]
            if target and (not row.get("item_code") or row.get("item_code") != target.get("item_code")
                           or (row.get("card_code") and target.get("card_code") and row["card_code"] != target["card_code"])):
                immediate = "UNRESOLVED"
            edge = result | {
                "lineage_id": digest([VERSION, key, target_key]),
                "source_system": key[0], "source_document_type": FAMILIES.get(bt),
                "source_doc_entry": be, "source_line_num": bl,
                "target_document_type": FAMILIES[key[1]], "target_doc_entry": key[2], "target_line_num": key[3],
                "relation_type": f"{FAMILIES.get(bt, 'UNKNOWN')}->{FAMILIES[key[1]]}",
                "edge_resolution_status": immediate,
                "base_type": bt, "base_entry": be, "base_line": bl,
                "item_match_status": "MATCH" if target and row.get("item_code") == target.get("item_code") else "UNKNOWN_OR_MISMATCH",
                "uom_match_status": "SUPPORTED" if target and compatible(row, target) else "UNRESOLVED",
                "effective_status": "EFFECTIVE" if target and all(valid(self.lines[tuple(k)]) for k in result["path"] if tuple(k) in self.lines) else "CANCELLED_OR_UNKNOWN",
                "snapshot_id": row["snapshot_id"], "provenance": row["source_row_hash"],
            }
            edges.append(edge)
        return edges


class MovementResolver:
    """Type-first, collision-safe crosswalk; candidate multiplicity is visible."""
    def __init__(self, atomic: Mapping[str, list[dict]], documentary: DocumentaryResolver):
        self.documentary = documentary
        self.by_ref: dict[str, list[dict]] = defaultdict(list)
        for family in FAMILIES.values():
            for row in atomic[family + "_line"]:
                if row.get("doc_num") is not None:
                    self.by_ref[row["doc_num"]].append(row)

    def resolve(self, movement: Mapping[str, Any]) -> dict:
        tt, ref, ln = (identity(movement.get(field)) for field in ("trans_type", "base_ref", "doc_line_num"))
        candidates = self.by_ref.get(ref, [])
        raw_docs = {(r["object_type"], r["doc_entry"]) for r in candidates}
        record = {"movement_key": movement.get("atomic_id"), "target_line_key": None,
                  "purchasing_doc_entry": None, "purchasing_line_num": None, "target_entity": FAMILIES.get(tt),
                  "po_key": None, "resolution_status": "UNRESOLVED", "resolution_method": VERSION,
                  "resolution_reason": "UNKNOWN", "base_ref_candidate_documents": len(raw_docs),
                  "collision_detected": len(raw_docs) > 1, "candidate_count": 0,
                  "match_fields": ["trans_type", "base_ref", "doc_line_num", "item_code"],
                  "card_code_status": "UNKNOWN", "warehouse_match_status": "UNKNOWN",
                  "quantity_match_status": "NOT_EVALUATED_PER_MOVEMENT", "direction": "UNKNOWN",
                  **{f: movement.get(f) for f in ("trans_type", "base_ref", "doc_line_num", "item_code", "card_code", "warehouse", "in_qty", "out_qty", "doc_date")}}
        record["doc_date"] = str(movement["doc_date"])[:10] if movement.get("doc_date") else None
        inbound, outbound = number(movement.get("in_qty")), number(movement.get("out_qty"))
        if inbound is not None and outbound is not None:
            record["direction"] = "IN" if inbound > 0 and outbound == 0 else "OUT" if outbound > 0 and inbound == 0 else "MIXED_OR_ZERO"
        if tt not in ("18", "20"):
            return record | {"resolution_status": "NOT_APPLICABLE", "resolution_reason": "RETURN_CROSSWALK_NOT_SUPPORTED" if tt == "21" else "NON_PURCHASING_OPERATION"}
        if ref is None or ln is None or not movement.get("item_code"):
            return record | {"resolution_reason": "INSUFFICIENT_DOCUMENTARY_IDENTITY"}
        typed = [r for r in candidates if r["object_type"] == tt and r["line_num"] == ln]
        if not typed:
            return record | {"resolution_status": "OUT_OF_COVERAGE", "resolution_reason": "DOCUMENT_LINE_NOT_MATERIALIZED"}
        matches = [r for r in typed if r.get("item_code") == movement["item_code"]]
        if not matches:
            return record | {"resolution_reason": "ITEM_MISMATCH"}
        if movement.get("card_code"):
            matches = [r for r in matches if not r.get("card_code") or r["card_code"] == movement["card_code"]]
            record["match_fields"].append("card_code")
            if not matches:
                return record | {"resolution_reason": "SUPPLIER_MISMATCH"}
        # OINM DocEntry is not assumed to mean OPCH/OPDN DocEntry. Only an
        # explicitly supplied/documented source-native crosswalk may narrow it.
        expected_entry = identity(movement.get("purchasing_doc_entry"))
        if expected_entry is not None:
            matches = [r for r in matches if r["doc_entry"] == expected_entry]
            record["match_fields"].append("purchasing_doc_entry")
        record["candidate_count"] = len(matches)
        if len(matches) != 1:
            return record | {"resolution_reason": "AMBIGUOUS_LINEAGE" if matches else "IDENTITY_CONTRADICTION"}
        row = matches[0]
        card_present = bool(movement.get("card_code") and row.get("card_code"))
        wh, doc_wh = movement.get("warehouse"), row.get("warehouse_code")
        rooted = self.documentary.resolve(line_key(row))
        return record | {
            "target_line_key": list(line_key(row)), "purchasing_doc_entry": row["doc_entry"],
            "purchasing_line_num": row["line_num"], "po_key": rooted["po_key"],
            "resolution_status": "RESOLVED_EXACT" if card_present else "RESOLVED_SUPPORTED",
            "resolution_reason": "TYPE_LINE_ITEM_UNIQUE", "provenance": row["source_row_hash"],
            "source_line_quantity": row["quantity"], "base_qty": row["base_quantity"],
            "source_line_uom": row["unit_msr"], "conversion_provenance": row["conversion_provenance"],
            "doc_line_warehouse": row["warehouse_code"], "movement_date": record["doc_date"],
            "root_resolution_status": rooted["resolution_status"],
            "card_code_status": "MATCH" if card_present else "ABSENT_BUT_UNIQUE",
            "warehouse_match_status": "UNKNOWN" if not wh or not doc_wh else "MATCH" if wh == doc_wh else "MISMATCH",
            "effective_status": "EFFECTIVE" if valid(row) else "CANCELLED_OR_UNKNOWN",
        }


def derive(atomic: Mapping[str, list[dict]], movements: list[dict], *, warehouse_reference: Mapping[str, dict] | None = None) -> tuple[dict[str, list[dict]], dict]:
    resolver = DocumentaryResolver(atomic)
    crosswalk = MovementResolver(atomic, resolver)
    seen = set()
    rows = []
    for movement in movements:
        key = movement.get("atomic_id")
        if not key or key in seen:
            raise PurchasingError("missing/duplicate inventory movement identity")
        seen.add(key)
        result = crosswalk.resolve(movement)
        warehouse = (warehouse_reference or {}).get(result["warehouse"], {})
        result.update(business_warehouse_location=warehouse.get("business_location_code"),
                      warehouse_mapping_status=warehouse.get("mapping_status", "UNKNOWN"),
                      warehouse_mapping_provenance=warehouse.get("mapping_basis"))
        rows.append(result)
    rows.sort(key=lambda r: r["movement_key"])
    fields = sorted({field for row in rows for field in row})
    rows = [{field: row.get(field) for field in fields} for row in rows]
    metrics = dict(Counter(r["resolution_status"] for r in rows))
    metrics.update(collisions_detected=sum(r["collision_detected"] for r in rows),
                   collisions_safely_resolved=sum(r["collision_detected"] and r["resolution_status"] in RESOLVED for r in rows),
                   ambiguous_collisions_preserved=sum(r["collision_detected"] and r["resolution_status"] == "UNRESOLVED" for r in rows),
                   false_fanout=0, item_code_mismatch=sum(r["resolution_reason"] == "ITEM_MISMATCH" for r in rows),
                   warehouse_mismatch=sum(r["warehouse_match_status"] == "MISMATCH" for r in rows))
    return {DERIVED[0]: resolver.lineage(), DERIVED[1]: rows}, metrics


def purchase_summary(atomic: Mapping[str, list[dict]], lineage: list[dict], *, coverage: Mapping) -> list[dict]:
    """Inventory PO quantities, with uncertainty propagated before absence."""
    receipt_index = {(r["doc_entry"], r["line_num"]): r for r in atomic["purchase_receipt_line"]}
    receipts: dict[tuple, list[dict]] = defaultdict(list)
    uncertain_po_keys = set()
    for edge in lineage:
        if edge["resolution_status"] == "UNRESOLVED":
            uncertain_po_keys.update(tuple(k) for k in edge["path"] if k[1] == "22")
        if edge["target_document_type"] == "purchase_receipt" and edge["resolution_status"] in RESOLVED and edge["po_key"]:
            row = receipt_index[(edge["target_doc_entry"], edge["target_line_num"])]
            if valid(row) and edge["effective_status"] == "EFFECTIVE":
                receipts[tuple(edge["po_key"])].append(row)
    out = []
    for row in atomic["purchase_order_line"]:
        if not valid(row) or not row.get("item_code") or row["item_code"].startswith("I-") or number(row.get("quantity")) in (None, Decimal(0)):
            continue
        linked = receipts.get(line_key(row), [])
        ordered = base_qty(row)
        ok = ordered is not None and line_key(row) not in uncertain_po_keys and all(compatible(row, r) for r in linked)
        window = coverage["purchase_receipt"]
        covered = window.get("absence_window_start") <= str(row["doc_date"])[:10] <= window["latest_available_date"] and not window.get("known_historical_gaps")
        qty = sum((base_qty(r) for r in linked), Decimal(0)) if ok and covered else None
        count = len({r["doc_entry"] for r in linked})
        if not covered:
            status = "OUT_OF_COVERAGE"
        elif not ok:
            status = "NOT_DETERMINABLE"
        elif not linked:
            status = "NO_RECEIPT"
        elif qty == ordered:
            status = "MULTI_RECEIPT_COMPLETE" if count > 1 else "EXACT_RECEIPT"
        elif qty < ordered:
            status = "MULTI_RECEIPT_PARTIAL" if count > 1 else "PARTIAL_RECEIPT"
        else:
            status = "OVER_RECEIPT"
        out.append({"po_entry": row["doc_entry"], "line_num": row["line_num"], "po_docnum": row["doc_num"],
                    "item_code": row["item_code"], "supplier": row["card_code"], "status": status,
                    "purchased_base": str(ordered) if ordered is not None else None,
                    "received_base": str(qty) if qty is not None else None,
                    "n_receipts": count, "n_receipt_lines": len(linked),
                    "warehouses_received": sorted({r["warehouse_code"] for r in linked if r["warehouse_code"]}),
                    "receipt_keys": sorted([[r["doc_entry"], r["line_num"]] for r in linked]),
                    "first_receipt_date": min((str(r["doc_date"])[:10] for r in linked), default=None),
                    "last_receipt_date": max((str(r["doc_date"])[:10] for r in linked), default=None),
                    "fully_received": qty == ordered if qty is not None and ordered is not None else None})
    return out
