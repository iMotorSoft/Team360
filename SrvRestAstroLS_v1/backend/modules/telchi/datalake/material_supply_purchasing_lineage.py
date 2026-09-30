"""TELCHI_DATALAKE_MATERIAL_SUPPLY_PURCHASING_LINEAGE_V1.

Source-native reconstruction of the real purchasing document chain that links
a goods receipt line (``OPDN``/``PDN1``) to its originating purchase order line
(``OPOR``/``POR1``).

Discovered against real SAP Business One / HANA (READ ONLY, 2026-09-24):

    PDN1.BaseType = 18   ->  AP Invoice line (OPCH / PCH1)
    PCH1.BaseType = 22   ->  Purchase Order line (POR1)

For 2026 receipts this resolves 16,542 / 16,542 ``BaseType=18`` lines to a
``PCH1`` row and 16,537 to a ``POR1`` row.  No fuzzy matching is ever used:
only source-native ``BaseType``/``BaseEntry``/``BaseLine`` links count.

This module reuses the frozen fact-capture infrastructure
(:func:`~modules.telchi.datalake.material_supply_fact_capture.discover_columns`,
``build_select``, :func:`~modules.telchi.datalake.raw.write_raw`) and the single
HANA adapter :class:`~modules.telchi.datalake.source.HanaReadOnlySource`.  It
never invents a second writer, adapter, SQL-safety layer or resource guard.
"""
from __future__ import annotations

from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Mapping

from .ducklake import DATA_ROOT
from .material_supply_fact_capture import (
    CaptureAbort,
    DatasetSpec,
    _f,
    discover_columns,
    offline_validate,
    read_persisted_rows,
    run_capture,
    write_json,
)

GATE = "TELCHI_DATALAKE_MATERIAL_SUPPLY_PURCHASING_LINEAGE_V1"
RAW_ROOT = DATA_ROOT / "raw" / "sap" / GATE
CAPTURE_YEAR = 2026

# SAP Business One object type codes used by the discovered chain.
OBJ_AP_INVOICE = 18
OBJ_GOODS_RECEIPT_PO = 20
OBJ_PURCHASE_ORDER = 22
OBJ_FREE_TEXT = -1


AP_INVOICE_DATASETS: tuple[DatasetSpec, ...] = (
    DatasetSpec(
        name="ap_invoice", header_table="OPCH", line_table=None, date_field="DocDate",
        key_fields=("DocEntry",), quantity_field=None, kind="month",
        fields=(
            _f("DocEntry", "H"), _f("DocNum", "H"), _f("CardCode", "H"), _f("CardName", "H"),
            _f("DocDate", "H"), _f("DocDueDate", "H"), _f("CANCELED", "H"), _f("DocStatus", "H"),
            _f("DocCur", "H"), _f("DocTotal", "H"), _f("U_TIPOCOMPRA", "H"), _f("Series", "H"),
            _f("UserSign", "H"), _f("NumAtCard", "H"), _f("Comments", "H"),
        ),
    ),
    DatasetSpec(
        name="ap_invoice_line", header_table="OPCH", line_table="PCH1", date_field="DocDate",
        key_fields=("DocEntry", "LineNum"), quantity_field="Quantity", kind="month",
        fields=(
            _f("DocEntry", "H"), _f("DocNum", "H"), _f("CardCode", "H"), _f("DocDate", "H"),
            _f("U_TIPOCOMPRA", "H"),
            _f("LineNum", "L"), _f("ItemCode", "L"), _f("Dscription", "L"), _f("WhsCode", "L"),
            _f("Quantity", "L"), _f("OpenQty", "L"), _f("LineStatus", "L"), _f("unitMsr", "L"),
            _f("NumPerMsr", "L"), _f("UomCode", "L"), _f("BaseType", "L"), _f("BaseEntry", "L"),
            _f("BaseLine", "L"), _f("Price", "L"), _f("Currency", "L"), _f("LineTotal", "L"),
            _f("Project", "L"), _f("U_LOTE", "L"), _f("U_VENCLOTE", "L"),
            _f("PoTrgNum", "L"), _f("PoTrgEntry", "L"), _f("PoLineNum", "L"),
        ),
    ),
)

AP_DATASET_NAMES: tuple[str, ...] = tuple(spec.name for spec in AP_INVOICE_DATASETS)

# Receipt / AP / PO datasets reused from the immutable fact-capture V1 baseline.
FACT_CAPTURE_ROOT = DATA_ROOT / "raw" / "sap" / "TELCHI_DATALAKE_MATERIAL_SUPPLY_FACT_CAPTURE_V1"


# ---------------------------------------------------------------------------
# SAP read-only capture of the additional A/P invoice facts
# ---------------------------------------------------------------------------


def capture_ap_invoices(
    source: Any,
    *,
    root: Path = RAW_ROOT,
    as_of: date,
    run_id: str | None = None,
    skip_control: bool = False,
    logger: Any = print,
) -> dict[str, Any]:
    """Capture OPCH/PCH1 for the requested 2026 window into a new raw root."""
    return run_capture(
        source=source, datasets=AP_INVOICE_DATASETS, root=root, run_id=run_id,
        as_of=as_of, skip_control=skip_control, gate=GATE, logger=logger,
    )


def ap_invoice_offline_validate(root: Path = RAW_ROOT) -> dict[str, Any]:
    return offline_validate(root, AP_DATASET_NAMES)


# ---------------------------------------------------------------------------
# Offline lineage reconstruction (persisted raw only, never SAP)
# ---------------------------------------------------------------------------


def _int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _basetype_key(value: Any) -> str:
    parsed = _int(value)
    return str(parsed) if parsed is not None else "None"


def pdn1_basetype_distribution(receipt_lines: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    rows = list(receipt_lines)
    counter: Counter[str] = Counter()
    for row in rows:
        counter[_basetype_key(row.get("BaseType"))] += 1
    total = len(rows)
    distribution = []
    for base_type, count in counter.most_common():
        distribution.append({
            "BaseType": base_type,
            "count": count,
            "percentage": round(100.0 * count / total, 4) if total else 0.0,
            "sap_semantics": {
                "18": "AP_INVOICE_OPCH",
                "20": "GOODS_RECEIPT_PO_OPDN",
                "22": "PURCHASE_ORDER_POR1",
                "-1": "FREE_TEXT_MANUAL",
                "None": "NULL_BASETYPE",
            }.get(base_type, "OTHER"),
        })
    return {"total_receipt_lines": total, "distribution": distribution,
            "by_basetype": {item["BaseType"]: item["count"] for item in distribution}}


def index_by_key(rows: Iterable[Mapping[str, Any]]) -> dict[tuple[str, str], Mapping[str, Any]]:
    """Index persisted rows by their exact ``(DocEntry, LineNum)`` key."""
    index: dict[tuple[str, str], Mapping[str, Any]] = {}
    for row in rows:
        key = (str(row.get("DocEntry")), str(row.get("LineNum")))
        index.setdefault(key, row)
    return index


def classify_receipt_line(
    receipt_line: Mapping[str, Any],
    ap_index: Mapping[tuple[str, str], Mapping[str, Any]],
    po_index: Mapping[tuple[str, str], Mapping[str, Any]],
) -> dict[str, Any]:
    """Classify one receipt line using only source-native document links.

    Returns a record with ``lineage_path_type``, ``lineage_confidence`` and the
    resolved keys.  It never matches by item, supplier, quantity or date.
    """
    receipt_key = (str(receipt_line.get("DocEntry")), str(receipt_line.get("LineNum")))
    base_type = _int(receipt_line.get("BaseType"))
    base_entry = _int(receipt_line.get("BaseEntry"))
    base_line = _int(receipt_line.get("BaseLine"))
    record: dict[str, Any] = {
        "receipt_docentry": receipt_key[0],
        "receipt_linenum": receipt_key[1],
        "receipt_docdate": str(receipt_line.get("DocDate")) if receipt_line.get("DocDate") is not None else None,
        "receipt_itemcode": receipt_line.get("ItemCode"),
        "receipt_quantity": receipt_line.get("Quantity"),
        "receipt_basetype": receipt_line.get("BaseType"),
        "receipt_baseentry": receipt_line.get("BaseEntry"),
        "receipt_baseline": receipt_line.get("BaseLine"),
        "intermediate_doc": None,
        "po_docentry": None,
        "po_linenum": None,
        "lineage_path_type": "UNRESOLVED",
        "lineage_confidence": "NONE",
    }
    if base_type == OBJ_PURCHASE_ORDER:
        po = po_index.get((str(base_entry), str(base_line)))
        if po is not None:
            record.update({
                "po_docentry": str(base_entry), "po_linenum": str(base_line),
                "lineage_path_type": "DIRECT_PO_RECEIPT", "lineage_confidence": "SOURCE_NATIVE",
            })
        else:
            record["lineage_path_type"] = "UNRESOLVED"
            record["lineage_confidence"] = "NONE"
        return record
    if base_type == OBJ_AP_INVOICE:
        ap = ap_index.get((str(base_entry), str(base_line)))
        if ap is None:
            record["lineage_path_type"] = "UNRESOLVED"
            record["lineage_confidence"] = "NONE"
            return record
        record["intermediate_doc"] = {"type": "AP_INVOICE", "DocEntry": str(base_entry), "LineNum": str(base_line),
                                      "DocDate": str(ap.get("DocDate")) if ap.get("DocDate") is not None else None}
        ap_base_type = _int(ap.get("BaseType"))
        ap_base_entry = _int(ap.get("BaseEntry"))
        ap_base_line = _int(ap.get("BaseLine"))
        if ap_base_type == OBJ_PURCHASE_ORDER:
            po = po_index.get((str(ap_base_entry), str(ap_base_line)))
            if po is not None:
                record.update({
                    "po_docentry": str(ap_base_entry), "po_linenum": str(ap_base_line),
                    "po_docdate": str(po.get("DocDate")) if po.get("DocDate") is not None else None,
                    "lineage_path_type": "INDIRECT_PO_RECEIPT_VIA_AP_INVOICE",
                    "lineage_confidence": "SOURCE_NATIVE",
                })
            else:
                record["lineage_path_type"] = "UNRESOLVED"
                record["lineage_confidence"] = "NONE"
        else:
            record["lineage_path_type"] = "OTHER_DOCUMENT_CHAIN"
            record["lineage_confidence"] = "SOURCE_NATIVE_NO_PO"
        return record
    if base_type in (OBJ_GOODS_RECEIPT_PO,):
        # A goods receipt copied from another goods receipt: keep the chain,
        # do not treat it as a purchase order.
        record["lineage_path_type"] = "OTHER_DOCUMENT_CHAIN"
        record["lineage_confidence"] = "SOURCE_NATIVE_NO_PO"
        return record
    if base_type in (OBJ_FREE_TEXT, None):
        record["lineage_path_type"] = "NO_PO_LINEAGE"
        record["lineage_confidence"] = "SOURCE_NATIVE_NO_PO"
        return record
    record["lineage_path_type"] = "OTHER_DOCUMENT_CHAIN"
    record["lineage_confidence"] = "SOURCE_NATIVE_NO_PO"
    return record


def resolve_receipt_lineage(
    receipt_lines: Iterable[Mapping[str, Any]],
    ap_lines: Iterable[Mapping[str, Any]],
    po_lines: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    ap_index = index_by_key(ap_lines)
    po_index = index_by_key(po_lines)
    return [classify_receipt_line(line, ap_index, po_index) for line in receipt_lines]


def lineage_coverage(records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    for record in records:
        counts[str(record["lineage_path_type"])] += 1
    covered = counts["DIRECT_PO_RECEIPT"] + counts["INDIRECT_PO_RECEIPT_VIA_AP_INVOICE"]
    total = sum(counts.values())
    if total == 0 or covered == 0:
        status = "UNRESOLVED"
    elif covered == total:
        status = "SUPPORTED"
    else:
        status = "PARTIAL"
    return {
        "total_receipt_lines": total,
        "DIRECT_PO_RECEIPT_LINES": counts["DIRECT_PO_RECEIPT"],
        "INDIRECT_PO_RECEIPT_VIA_AP_INVOICE": counts["INDIRECT_PO_RECEIPT_VIA_AP_INVOICE"],
        "OTHER_DOCUMENT_CHAIN": counts["OTHER_DOCUMENT_CHAIN"],
        "NO_PO_LINEAGE": counts["NO_PO_LINEAGE"],
        "UNRESOLVED_LINEAGE": counts["UNRESOLVED"],
        "DEFENSIBLE_PO_LINEAGE_LINES": covered,
        "lineage_coverage_ratio": round(covered / total, 6) if total else 0.0,
        "PURCHASING_LINEAGE_STATUS": status,
    }


def build_pdn_linkage_metrics(
    receipt_lines: Iterable[Mapping[str, Any]],
    ap_lines: Iterable[Mapping[str, Any]],
    po_lines: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Compute the required Phase-A linkage counters from persisted raw only."""
    ap_index = index_by_key(ap_lines)
    po_index = index_by_key(po_lines)
    base18 = 0
    base18_linked_pch1 = 0
    pch1_lines_from_pdni = 0
    pch1_basetype22 = 0
    pch1_linked_por1 = 0
    for line in receipt_lines:
        if _int(line.get("BaseType")) != OBJ_AP_INVOICE:
            continue
        base18 += 1
        ap = ap_index.get((str(line.get("BaseEntry")), str(line.get("BaseLine"))))
        if ap is None:
            continue
        base18_linked_pch1 += 1
        pch1_lines_from_pdni += 1
        if _int(ap.get("BaseType")) == OBJ_PURCHASE_ORDER:
            pch1_basetype22 += 1
            if (str(ap.get("BaseEntry")), str(ap.get("BaseLine"))) in po_index:
                pch1_linked_por1 += 1
    return {
        "PDN1_BASETYPE18_LINES": base18,
        "PDN1_BASETYPE18_LINKED_TO_PCH1": base18_linked_pch1,
        "PDN1_BASETYPE18_NOT_LINKED": base18 - base18_linked_pch1,
        "PCH1_LINES_FROM_PDNI": pch1_lines_from_pdni,
        "PCH1_BASETYPE22": pch1_basetype22,
        "PCH1_LINKED_TO_POR1": pch1_linked_por1,
        "PCH1_WITHOUT_PO_LINEAGE": pch1_lines_from_pdni - pch1_linked_por1,
    }


# ---------------------------------------------------------------------------
# Lead time samples (pure; the caller decides the profiles)
# ---------------------------------------------------------------------------


def receipt_lead_time_samples(
    records: Iterable[Mapping[str, Any]],
    po_lines_index: Mapping[tuple[str, str], Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Return one sample per resolvable receipt line with exact PO lineage.

    ``order_to_receipt_days`` = receipt DocDate - PO DocDate.  Negative values
    are retained as anomalies, never clamped.
    """
    samples: list[dict[str, Any]] = []
    for record in records:
        if record.get("po_docentry") is None or record.get("po_linenum") is None:
            continue
        po = po_lines_index.get((str(record["po_docentry"]), str(record["po_linenum"])))
        if po is None:
            continue
        try:
            po_date = date.fromisoformat(str(po.get("DocDate"))[:10])
            receipt_date = date.fromisoformat(str(record.get("receipt_docdate"))[:10])
        except (TypeError, ValueError):
            continue
        samples.append({
            "receipt_docentry": record["receipt_docentry"],
            "receipt_linenum": record["receipt_linenum"],
            "po_docentry": record["po_docentry"],
            "po_linenum": record["po_linenum"],
            "itemcode": record.get("receipt_itemcode"),
            "supplier": po.get("CardCode"),
            "po_docdate": po_date.isoformat(),
            "receipt_docdate": receipt_date.isoformat(),
            "order_to_receipt_days": (receipt_date - po_date).days,
            "lineage_path_type": record.get("lineage_path_type"),
        })
    return samples


# ---------------------------------------------------------------------------
# Persistence of the lineage path table
# ---------------------------------------------------------------------------


def persist_lineage_paths(records: list[dict[str, Any]], *, root: Path = RAW_ROOT,
                          run_id: str, as_of: str) -> dict[str, Any]:
    """Persist the derived lineage path table through the raw writer (auditable)."""
    from .raw import write_raw

    metadata = {
        "gate": GATE, "dataset": "purchase_lineage_path", "segment": "full",
        "source_system": "TELCHI_DATA_LAKE_DERIVATION", "generated_from": "raw Fact Capture V1 + AP capture",
        "source_as_of": as_of, "logical_key": ["receipt_docentry", "receipt_linenum"],
        "sap_access_mode": "READ_ONLY", "sap_write_count": 0, "run_id": run_id,
    }
    return write_raw(
        root=root, segment_id="purchase_lineage_path/full",
        extraction_id=f"{run_id}_purchase_lineage_path_full", rows=records, metadata=metadata,
    )


__all__ = [
    "GATE",
    "RAW_ROOT",
    "FACT_CAPTURE_ROOT",
    "AP_INVOICE_DATASETS",
    "AP_DATASET_NAMES",
    "capture_ap_invoices",
    "ap_invoice_offline_validate",
    "pdn1_basetype_distribution",
    "index_by_key",
    "classify_receipt_line",
    "resolve_receipt_lineage",
    "lineage_coverage",
    "build_pdn_linkage_metrics",
    "receipt_lead_time_samples",
    "persist_lineage_paths",
    "CaptureAbort",
    "read_persisted_rows",
    "write_json",
]