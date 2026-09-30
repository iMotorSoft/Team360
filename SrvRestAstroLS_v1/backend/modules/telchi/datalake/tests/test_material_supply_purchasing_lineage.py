"""Contract tests for TELCHI_DATALAKE_MATERIAL_SUPPLY_DERIVATION_V1 — purchasing lineage.

Pure functions only: no SAP, no Data Root, no DuckLake.
"""
from __future__ import annotations

from modules.telchi.datalake.material_supply_purchasing_lineage import (
    classify_receipt_line,
    index_by_key,
    lineage_coverage,
    pdn1_basetype_distribution,
    resolve_receipt_lineage,
)


def _receipt(basetype, baseentry, baseline, **extra):
    return {"DocEntry": "500", "LineNum": "0", "ItemCode": "I1", "Quantity": 5,
            "DocDate": "2026-05-01", "BaseType": basetype, "BaseEntry": baseentry, "BaseLine": baseline, **extra}


def test_direct_po_receipt_is_source_native():
    po = [{"DocEntry": "900", "LineNum": "1", "DocDate": "2026-04-01"}]
    record = classify_receipt_line(_receipt(22, 900, 1), {}, index_by_key(po))
    assert record["lineage_path_type"] == "DIRECT_PO_RECEIPT"
    assert record["lineage_confidence"] == "SOURCE_NATIVE"
    assert record["po_docentry"] == "900"


def test_indirect_receipt_via_ap_invoice_resolves_po():
    ap = [{"DocEntry": "300", "LineNum": "0", "BaseType": 22, "BaseEntry": "900", "BaseLine": "1", "DocDate": "2026-04-15"}]
    po = [{"DocEntry": "900", "LineNum": "1", "DocDate": "2026-04-01"}]
    record = classify_receipt_line(_receipt(18, 300, 0), index_by_key(ap), index_by_key(po))
    assert record["lineage_path_type"] == "INDIRECT_PO_RECEIPT_VIA_AP_INVOICE"
    assert record["lineage_confidence"] == "SOURCE_NATIVE"
    assert record["po_docentry"] == "900"
    assert record["intermediate_doc"]["type"] == "AP_INVOICE"


def test_ap_invoice_without_po_is_other_document_chain():
    ap = [{"DocEntry": "300", "LineNum": "0", "BaseType": 20, "BaseEntry": "7", "BaseLine": "0", "DocDate": "2026-04-15"}]
    record = classify_receipt_line(_receipt(18, 300, 0), index_by_key(ap), {})
    assert record["lineage_path_type"] == "OTHER_DOCUMENT_CHAIN"
    assert record["po_docentry"] is None


def test_missing_ap_index_is_unresolved_not_fabricated():
    record = classify_receipt_line(_receipt(18, 300, 0), {}, {})
    assert record["lineage_path_type"] == "UNRESOLVED"
    assert record["lineage_confidence"] == "NONE"


def test_free_text_receipt_has_no_po_lineage():
    record = classify_receipt_line(_receipt(-1, 0, 0), {}, {})
    assert record["lineage_path_type"] == "NO_PO_LINEAGE"


def test_lineage_coverage_partial_ratio():
    records = [
        {"lineage_path_type": "DIRECT_PO_RECEIPT"},
        {"lineage_path_type": "INDIRECT_PO_RECEIPT_VIA_AP_INVOICE"},
        {"lineage_path_type": "UNRESOLVED"},
        {"lineage_path_type": "NO_PO_LINEAGE"},
        {"lineage_path_type": "OTHER_DOCUMENT_CHAIN"},
    ]
    coverage = lineage_coverage(records)
    assert coverage["total_receipt_lines"] == 5
    assert coverage["DEFENSIBLE_PO_LINEAGE_LINES"] == 2
    assert coverage["lineage_coverage_ratio"] == 0.4
    assert coverage["PURCHASING_LINEAGE_STATUS"] == "PARTIAL"


def test_lineage_coverage_unresolved_when_none_covered():
    assert lineage_coverage([{"lineage_path_type": "UNRESOLVED"}])["PURCHASING_LINEAGE_STATUS"] == "UNRESOLVED"


def test_pdn1_basetype_distribution_counts():
    lines = [{"BaseType": 18}, {"BaseType": "18"}, {"BaseType": 22}, {"BaseType": None}]
    distribution = pdn1_basetype_distribution(lines)
    assert distribution["by_basetype"]["18"] == 2
    assert distribution["by_basetype"]["22"] == 1
    assert distribution["by_basetype"]["None"] == 1
    assert distribution["total_receipt_lines"] == 4


def test_resolve_receipt_lineage_never_matches_by_item_or_date():
    # Same item/supplier/quantity/date but different document keys -> must not link.
    po = [{"DocEntry": "1", "LineNum": "0", "ItemCode": "I1", "DocDate": "2026-05-01"}]
    receipt = _receipt(18, 999, 0, ItemCode="I1")
    ap = [{"DocEntry": "300", "LineNum": "0", "BaseType": 22, "BaseEntry": "1", "BaseLine": "0"}]
    records = resolve_receipt_lineage([receipt], ap, po)
    # base entry 999 does not exist in the AP index -> unresolved, not matched to PO 1.
    assert records[0]["lineage_path_type"] == "UNRESOLVED"