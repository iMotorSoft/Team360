"""Focused tests for TELCHI_AP_INVOICED_WITHOUT_WAREHOUSE_RECEIPT_V1.

Pure logic tests (no Data Lake, no SAP). The live gate run is the evidence
runner in ``run_gate.py``.
"""
from __future__ import annotations

from decimal import Decimal

from modules.telchi.investigation.validation.ap_invoiced_without_warehouse_receipt_v1.ap_invoice_no_grpo import (  # noqa: E402
    CATEGORY_LABELS,
    CLASS_ORDER,
    Evidence,
    advance_invoice_evidence,
    classify,
    import_invoice_evidence,
)


def test_class_order_has_no_duplicates_and_is_labeled():
    assert len(CLASS_ORDER) == len(set(CLASS_ORDER))
    assert set(CLASS_ORDER) == set(CATEGORY_LABELS)


def test_cancelled_po_wins():
    cat, _ = classify(Evidence(po_canceled=True, advance_invoice=True))
    assert cat == "CANCELLED_OR_REVERSED"


def test_cancelled_invoice_wins():
    cat, _ = classify(Evidence(invoice_canceled=True, linked_inbound_base=Decimal("3000")))
    assert cat == "CANCELLED_OR_REVERSED"


def test_purchase_reversal_wins():
    cat, _ = classify(Evidence(purchase_reversal=True, linked_inbound_base=Decimal("10")))
    assert cat == "CANCELLED_OR_REVERSED"


def test_non_inventory_exception_wins():
    cat, _ = classify(Evidence(non_inventory=True, advance_invoice=True))
    assert cat == "NON_INVENTORY_EXCEPTION"


def test_historical_lineage_gap_when_receipt_window_starts_after_po():
    cat, _ = classify(Evidence(receipt_window_covers_po=False))
    assert cat == "HISTORICAL_LINEAGE_GAP"


def test_receipt_outside_window():
    cat, _ = classify(Evidence(receipt_outside_window=True))
    assert cat == "RECEIPT_OUTSIDE_WINDOW"


def test_uom_issue():
    cat, _ = classify(Evidence(uom_issue=True))
    assert cat == "QUANTITY_UOM_ISSUE"


def test_receipt_alternate_lineage_beats_inventory_entry():
    cat, _ = classify(Evidence(receipt_linked=True, linked_inbound_base=Decimal("3000")))
    assert cat == "RECEIPT_FOUND_ALTERNATE_LINEAGE"


def test_inventory_entry_without_grpo():
    cat, reason = classify(Evidence(linked_inbound_base=Decimal("3000")))
    assert cat == "INVENTORY_ENTRY_WITHOUT_GRPO"
    assert "OINM" in reason


def test_inventory_entry_beats_documentary_evidence():
    cat, _ = classify(Evidence(linked_inbound_base=Decimal("3000"), advance_invoice=True,
                               import_invoice=True))
    assert cat == "INVENTORY_ENTRY_WITHOUT_GRPO"


def test_direct_ap_invoice_on_advance_invoice_documentation():
    cat, reason = classify(Evidence(advance_invoice=True))
    assert cat == "DIRECT_AP_INVOICE_NO_GRPO"
    assert "ANTICIPADA" in reason


def test_direct_ap_invoice_on_import_invoice_documentation():
    cat, reason = classify(Evidence(import_invoice=True))
    assert cat == "DIRECT_AP_INVOICE_NO_GRPO"
    assert "moneda extranjera" in reason


def test_true_invoiced_without_receipt_is_the_residual():
    cat, reason = classify(Evidence())
    assert cat == "TRUE_INVOICED_WITHOUT_RECEIPT"
    assert "sin GRPO" in reason


def test_not_determinable_without_invoice_evidence():
    cat, _ = classify(Evidence(invoice_determinable=False))
    assert cat == "NOT_DETERMINABLE"


def test_advance_invoice_evidence_variants():
    assert advance_invoice_evidence("SOLICITUD DE FACTURA ANTICIPADA DE FECHA 25/06/26")
    assert advance_invoice_evidence("SOLICITU DE FACTURA ANTICIPADA DISALI - 25/06/26")
    assert advance_invoice_evidence(None, "FACTURA ANTICIPADA COMPRA DE ENV.1/08")
    assert not advance_invoice_evidence("FACT 4739 EQUIPO PETROLERO")
    assert not advance_invoice_evidence(None, None)


def test_import_invoice_evidence_uses_document_currency():
    assert import_invoice_evidence("USD")
    assert import_invoice_evidence(" usd ")
    assert not import_invoice_evidence("BS")
    assert not import_invoice_evidence(None)
