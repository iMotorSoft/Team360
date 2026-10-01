"""Focused tests for TELCHI_PURCHASE_TO_WAREHOUSE_RECEIPT_RECONCILIATION_V1.

Pure logic tests (no Data Lake, no SAP). The live gate run is the evidence
runner in ``run_gate.py``.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from modules.telchi.investigation.validation.purchase_to_warehouse_receipt_reconciliation_v1.reconciliation import (  # noqa: E402
    LinkResult,
    PoLine,
    ReceiptLine,
    Resolver,
    classify,
    uom_compatible,
)


def _po(item="M00001", qty="100", npm="1", uom="UNI") -> PoLine:
    return PoLine(
        po_entry="100", line_num="0", item_code=item, quantity=qty, num_per_msr=npm,
        unit_msr=uom, whs_code="2A-AMD", line_status="C", tipo_compra="LF",
        description="x", po_docdate=date(2026, 1, 1), ship_date=date(2026, 1, 10),
        open_qty="0", po_docnum="262000100", card_code="PL000001", po_canceled="N",
    )


def _rl(entry="200", ln="0", be="100", bt="22", bl="0", item="M00001", qty="100",
        npm="1", uom="UNI", canceled="N") -> ReceiptLine:
    return ReceiptLine(
        doc_entry=entry, line_num=ln, base_entry=be, base_type=bt, base_line=bl,
        item_code=item, quantity=qty, num_per_msr=npm, unit_msr=uom, whs_code="2A-AMD",
        doc_date=date(2026, 1, 5), canceled=canceled, doc_num="262000200",
        card_code="PL000001",
    )


def test_classify_exact_single():
    assert classify(Decimal("100"), Decimal("100"), 1, True) == "EXACT_RECEIPT"


def test_classify_multi_complete():
    assert classify(Decimal("100"), Decimal("100"), 3, True) == "MULTI_RECEIPT_COMPLETE"


def test_classify_partial_single_and_multi():
    assert classify(Decimal("100"), Decimal("60"), 1, True) == "PARTIAL_RECEIPT"
    assert classify(Decimal("100"), Decimal("60"), 2, True) == "MULTI_RECEIPT_PARTIAL"


def test_classify_over():
    assert classify(Decimal("100"), Decimal("120"), 1, True) == "OVER_RECEIPT"
    assert classify(Decimal("100"), Decimal("120"), 4, True) == "OVER_RECEIPT"


def test_classify_no_receipt_wins_over_missing_uom():
    # absence of any receipt is a documentary fact, quantity comparison not needed
    assert classify(None, None, 0, False) == "NO_RECEIPT"


def test_classify_not_determinable_on_uom():
    assert classify(Decimal("100"), Decimal("100"), 1, False) == "NOT_DETERMINABLE"
    assert classify(None, Decimal("100"), 1, True) == "NOT_DETERMINABLE"


def test_uom_compatible_same_unit():
    ok, note = uom_compatible(_po(uom="UNI"), _rl(uom="UNI"))
    assert ok and "UNI" in note


def test_uom_incompatible_different_units():
    ok, _ = uom_compatible(_po(uom="UNI"), _rl(uom="KG"))
    assert not ok


def test_uom_absent_falls_back_to_explicit_num_per_msr():
    ok, _ = uom_compatible(_po(uom=None, npm="30"), _rl(uom=None, npm="30"))
    assert ok
    ok2, _ = uom_compatible(_po(uom=None, npm="30"), _rl(uom=None, npm="1"))
    assert not ok2
    ok3, _ = uom_compatible(_po(uom=None, npm=None), _rl(uom=None, npm=None))
    assert not ok3


def test_resolver_direct_po():
    po = _po()
    rl = _rl()
    r = Resolver({rl.key: rl}, {}, {po.key: po})
    res = r.resolve_memo(rl.key)
    assert res == LinkResult(("100", "0"), "DIRECT_PO")


def test_resolver_via_ap_invoice():
    po = _po()
    rl = _rl(bt="18", be="43110", bl="0")
    inv = {"doc_entry": "43110", "line_num": "0", "base_entry": "100",
           "base_line": "0", "base_type": "22"}
    r = Resolver({rl.key: rl}, {("43110", "0"): inv}, {po.key: po})
    assert r.resolve_memo(rl.key) == LinkResult(("100", "0"), "VIA_AP_INVOICE")


def test_resolver_via_grpo_chain():
    po = _po()
    final = _rl(entry="300", ln="0", bt="18", be="43110", bl="0")
    base = _rl(entry="200", ln="0", bt="18", be="43110", bl="0")
    grpo = _rl(entry="400", ln="0", bt="20", be="300", bl="0")
    inv = {"doc_entry": "43110", "line_num": "0", "base_entry": "100",
           "base_line": "0", "base_type": "22"}
    r = Resolver({final.key: final, base.key: base, grpo.key: grpo},
                 {("43110", "0"): inv}, {po.key: po})
    assert r.resolve_memo(grpo.key) == LinkResult(("100", "0"), "VIA_AP_INVOICE")


def test_resolver_no_base_document():
    po = _po()
    rl = _rl(bt="-1", be=None, bl=None)
    r = Resolver({rl.key: rl}, {}, {po.key: po})
    res = r.resolve_memo(rl.key)
    assert res.po_key is None and res.path == "NO_BASE_DOCUMENT"


def test_resolver_missing_ap_line():
    rl = _rl(bt="18", be="99999", bl="0")
    r = Resolver({rl.key: rl}, {}, {})
    res = r.resolve_memo(rl.key)
    assert res.path == "AP_LINE_NOT_MATERIALIZED"


def test_resolver_depth_limit_is_cycle_safe():
    po = _po()
    a = _rl(entry="500", bt="20", be="600", bl="0")
    b = _rl(entry="600", bt="20", be="500", bl="0")
    r = Resolver({a.key: a, b.key: b}, {}, {po.key: po})
    res = r.resolve_memo(a.key)
    assert res.po_key is None and res.path == "MAX_DEPTH"