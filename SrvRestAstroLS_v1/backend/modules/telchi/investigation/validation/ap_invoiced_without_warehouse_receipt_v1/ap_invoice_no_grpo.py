"""TELCHI_AP_INVOICED_WITHOUT_WAREHOUSE_RECEIPT_V1 - core module.

Data Lake only. READ ONLY. No SAP/HANA access of any kind.

Explains case by case the 25 purchase lines reported as invoiced without any
warehouse receipt (683.025 base units) by
``TELCHI_PURCHASE_TO_WAREHOUSE_RECEIPT_RECONCILIATION_V1`` and assigns each one
exactly one category from the investigation brief.

Evidence sources (all source-native, no inference from ItemCode alone):

  purchase_order / purchase_order_line      (OPOR / POR1, fact capture V1)
  purchase_receipt / purchase_receipt_line  (OPDN / PDN1, fact capture V1)
  ap_invoice / ap_invoice_line              (OPCH / PCH1, purchasing lineage V1)
  atomic.inventory_movement                 (OINM, Foundation CURRENT)
  reference products / suppliers / warehouses

Lineage used to attribute or reject a candidate receipt/movement:

  receipt line --BaseType=18--> AP invoice line --BaseType=22--> PO line
  receipt line --BaseType=22--> PO line
  OINM trans_type=18 --base_ref=AP invoice DocNum + doc_line_num + ItemCode-->

``DocNum`` is NOT globally unique across OPOR/OPDN/OPCH (all three families share
the 2620xxxxx series, 3337 PO DocNums are also receipt DocNums), so a movement is
only attributed to a line when ``base_ref`` + ``doc_line_num`` + ``ItemCode`` +
``card_code`` agree with the AP invoice. Coincidence of ItemCode/quantity with
another purchase order is recorded as a rejected candidate, never as evidence.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from modules.telchi.investigation.validation.purchase_to_warehouse_receipt_reconciliation_v1.reconciliation import (  # noqa: E402
    CANCELLED_VALUES,
    DATA_ROOT,
    NON_STOCKABLE_ITEM_PREFIX,
    PURCHASING_LINEAGE,
    REFERENCE,
    PoLine,
    Resolver,
    _base_qty,
    _date,
    _dec,
    build_datasets,
    uom_compatible,
)

GATE = "TELCHI_AP_INVOICED_WITHOUT_WAREHOUSE_RECEIPT_V1"
SAP_ACCESSED = "NO"
SAP_QUERY_COUNT = 0
SAP_WRITE_COUNT = 0

LOCAL_CURRENCY = "BS"
EXTRACT_START = "2026-01-01"
LOOKBACK_DAYS = 45
ADVANCE_INVOICE_PATTERN = re.compile(r"ANTICIPAD", re.IGNORECASE)

# Reversal transaction types of the purchase side (AP credit memo / return).
PURCHASE_REVERSAL_TRANS_TYPES = {"19", "21"}

CLASS_ORDER = [
    "DIRECT_AP_INVOICE_NO_GRPO",
    "RECEIPT_FOUND_ALTERNATE_LINEAGE",
    "INVENTORY_ENTRY_WITHOUT_GRPO",
    "RECEIPT_OUTSIDE_WINDOW",
    "HISTORICAL_LINEAGE_GAP",
    "CANCELLED_OR_REVERSED",
    "NON_INVENTORY_EXCEPTION",
    "QUANTITY_UOM_ISSUE",
    "TRUE_INVOICED_WITHOUT_RECEIPT",
    "NOT_DETERMINABLE",
]

CATEGORY_LABELS = {
    "DIRECT_AP_INVOICE_NO_GRPO": "Factura AP directa desde la OC sin GRPO, con evidencia documental del flujo",
    "RECEIPT_FOUND_ALTERNATE_LINEAGE": "Recepción hallada por otra ruta documental (linaje explícito a la misma OC)",
    "INVENTORY_ENTRY_WITHOUT_GRPO": "Entrada física en OINM sin purchase_receipt asociado",
    "RECEIPT_OUTSIDE_WINDOW": "Recepción existente fuera de la ventana extraída",
    "HISTORICAL_LINEAGE_GAP": "Línea heredada cuyo linaje depende de documentos previos al extracto",
    "CANCELLED_OR_REVERSED": "OC/factura anulada o movimiento de compra revertido",
    "NON_INVENTORY_EXCEPTION": "Línea no inventariable (ítem de gasto, servicio o cantidad cero)",
    "QUANTITY_UOM_ISSUE": "Recepción presente con cantidad o UoM incompatible",
    "TRUE_INVOICED_WITHOUT_RECEIPT": "Factura válida sin GRPO, sin ingreso OINM y sin explicación documental",
    "NOT_DETERMINABLE": "No determinable dentro del Data Lake",
}


@dataclass
class Evidence:
    """Inputs required by :func:`classify`; kept Data Lake free for unit tests."""

    po_canceled: bool = False
    invoice_canceled: bool = False
    purchase_reversal: bool = False
    non_inventory: bool = False
    receipt_window_covers_po: bool = True
    receipt_outside_window: bool = False
    uom_issue: bool = False
    receipt_linked: bool = False
    linked_inbound_base: Decimal = Decimal("0")
    advance_invoice: bool = False
    import_invoice: bool = False
    invoice_determinable: bool = True

    @property
    def determinable(self) -> bool:
        return self.invoice_determinable and self.receipt_window_covers_po


def advance_invoice_evidence(*texts: str | None) -> bool:
    """True when a document comment explicitly requests an advance invoice."""
    for text in texts:
        if text and ADVANCE_INVOICE_PATTERN.search(text):
            return True
    return False


def import_invoice_evidence(doc_cur: str | None) -> bool:
    """Foreign currency AP invoice = import shipment invoice (supplier invoice or
    bill of lading captured in ``NumAtCard``)."""
    if doc_cur is None:
        return False
    return doc_cur.strip().upper() != LOCAL_CURRENCY


def classify(ev: Evidence) -> tuple[str, str]:
    """Exactly one category per line, first matching rule wins."""
    if ev.po_canceled:
        return "CANCELLED_OR_REVERSED", "OC anulada"
    if ev.invoice_canceled:
        return "CANCELLED_OR_REVERSED", "factura de compra anulada"
    if ev.purchase_reversal:
        return "CANCELLED_OR_REVERSED", "movimiento de compra revertido (trans_type de devolución/nota de crédito)"
    if ev.non_inventory:
        return "NON_INVENTORY_EXCEPTION", "línea no inventariable"
    if not ev.receipt_window_covers_po:
        return "HISTORICAL_LINEAGE_GAP", "la OC es anterior al inicio de la ventana de recepciones extraída"
    if ev.receipt_outside_window:
        return "RECEIPT_OUTSIDE_WINDOW", "existe recepción vinculada fuera de la ventana extraída"
    if ev.uom_issue:
        return "QUANTITY_UOM_ISSUE", "recepción vinculada con UoM o cantidad base incompatible"
    if ev.receipt_linked:
        return "RECEIPT_FOUND_ALTERNATE_LINEAGE", "recepción vinculada a la misma línea por linaje BaseEntry/BaseLine"
    if ev.linked_inbound_base > 0:
        return (
            "INVENTORY_ENTRY_WITHOUT_GRPO",
            "entrada OINM (base_ref=factura DocNum + línea + ItemCode) sin purchase_receipt",
        )
    if ev.advance_invoice or ev.import_invoice:
        reason = []
        if ev.advance_invoice:
            reason.append("solicitud explícita de FACTURA ANTICIPADA en el comentario")
        if ev.import_invoice:
            reason.append("factura de importación en moneda extranjera con referencia de embarque")
        return "DIRECT_AP_INVOICE_NO_GRPO", "factura directa de la OC (BaseType=22): " + " + ".join(reason)
    if ev.determinable:
        return (
            "TRUE_INVOICED_WITHOUT_RECEIPT",
            "orden cerrada, factura válida, sin GRPO, sin ingreso OINM y sin explicación documental",
        )
    return "NOT_DETERMINABLE", "el Data Lake no permite descartar la recepción (cobertura de ventana insuficiente)"


@dataclass
class Target:
    key: tuple[str, str]
    po: PoLine
    invoice_key: tuple[str, str]
    inv_base_entry: str
    inv_base_line: str
    inv_base_type: str
    purchased_base: Decimal


@dataclass
class Movement:
    trans_type: str
    doc_date: date
    item_code: str
    warehouse: str
    in_qty: Decimal
    out_qty: Decimal
    card_code: str | None
    base_ref: str | None
    doc_line_num: str | None


def load_document_detail() -> dict[str, Any]:
    """AP invoice header/line fields and PO comments not exposed by
    ``reconciliation.build_datasets`` (comments, NumAtCard, DocCur, DocTotal,
    invoice LineStatus/OpenQty)."""
    import duckdb

    inv_glob = str(PURCHASING_LINEAGE / "ap_invoice" / "*" / "*" / "*.parquet")
    inl_glob = str(PURCHASING_LINEAGE / "ap_invoice_line" / "*" / "*" / "*.parquet")
    po_glob = str(
        DATA_ROOT / "raw" / "sap" / "TELCHI_DATALAKE_MATERIAL_SUPPLY_FACT_CAPTURE_V1"
        / "purchase_order" / "*" / "*" / "*.parquet"
    )
    con = duckdb.connect()
    headers: dict[str, dict[str, Any]] = {}
    for row in con.execute(
        "SELECT CAST(DocEntry AS VARCHAR) AS e, CAST(DocNum AS VARCHAR) AS dn, CANCELED AS c, "
        "CAST(DocDate AS DATE) AS d, CAST(CardCode AS VARCHAR) AS cc, Comments AS cm, "
        "NumAtCard AS nac, DocTotal AS dt, DocCur AS dc, DocStatus AS st "
        f"FROM read_parquet('{inv_glob}')"
    ).fetchall():
        e, dn, c, d, cc, cm, nac, dt, dc, st = row
        headers[e] = {"docnum": dn, "canceled": c, "docdate": d, "cardcode": cc,
                      "comments": cm, "num_at_card": nac, "doc_total": dt,
                      "doc_cur": dc, "status": st}
    lines: dict[tuple[str, str], dict[str, Any]] = {}
    for row in con.execute(
        "SELECT CAST(DocEntry AS VARCHAR) AS e, CAST(LineNum AS VARCHAR) AS ln, "
        "LineStatus AS ls, OpenQty AS oq, Quantity AS q, "
        "CAST(CAST(CAST(BaseEntry AS DOUBLE) AS BIGINT) AS VARCHAR) AS be, "
        "CAST(CAST(BaseType AS DOUBLE) AS BIGINT) AS bt, "
        "CAST(CAST(CAST(BaseLine AS DOUBLE) AS BIGINT) AS VARCHAR) AS bl, "
        "ItemCode AS item, NumPerMsr AS npm "
        f"FROM read_parquet('{inl_glob}')"
    ).fetchall():
        e, ln, ls, oq, q, be, bt, bl, item, npm = row
        lines[(e, ln)] = {
            "line_status": ls, "open_qty": oq, "quantity": q, "item_code": item,
            "num_per_msr": npm, "base_entry": be, "base_type": None if bt is None else str(bt),
            "base_line": bl,
        }
    po_comments = {
        e: cm for e, cm in con.execute(
            "SELECT CAST(DocEntry AS VARCHAR) AS e, Comments AS cm "
            f"FROM read_parquet('{po_glob}')"
        ).fetchall()
    }
    con.close()
    return {"invoice_headers": headers, "invoice_lines": lines, "po_comments": po_comments}


def select_targets(data: dict[str, Any], detail: dict[str, Any]) -> list[Target]:
    """Universe: inventory PO line closed without any receipt + valid direct AP
    invoice (BaseType=22) pointing at that exact line."""
    po_lines: dict[tuple[str, str], PoLine] = data["po_lines"]
    invoice_lines: dict[tuple[str, str], dict[str, Any]] = data["invoice_lines"]
    inv_headers: dict[str, dict[str, Any]] = detail["invoice_headers"]

    resolver = Resolver(data["receipt_lines"], invoice_lines, po_lines)
    receipts_by_po: dict[tuple[str, str], list[str]] = defaultdict(list)
    for rkey, rl in data["receipt_lines"].items():
        res = resolver.resolve_memo(rkey)
        if res.po_key is not None:
            receipts_by_po[res.po_key].append(rkey)

    invoices_by_po: dict[tuple[str, str], list[tuple[str, str]]] = defaultdict(list)
    for ikey, il in invoice_lines.items():
        if il["base_type"] == "22":
            invoices_by_po[(il["base_entry"], il["base_line"])].append(ikey)

    targets: list[Target] = []
    for key, po in po_lines.items():
        if po.po_canceled in CANCELLED_VALUES:
            continue
        if po.line_status != "C":
            continue
        if po.item_code is None or _dec(po.quantity) in (None, Decimal("0")):
            continue
        if po.item_code.startswith(NON_STOCKABLE_ITEM_PREFIX):
            continue
        if receipts_by_po.get(key):
            continue
        for ikey in sorted(invoices_by_po.get(key, [])):
            inv_line = invoice_lines[ikey]
            header = inv_headers.get(inv_line["doc_entry"], {})
            if header.get("canceled") in CANCELLED_VALUES:
                continue
            purchased = _base_qty(po.quantity, po.num_per_msr)
            if purchased is None or purchased <= 0:
                continue
            targets.append(Target(
                key=key, po=po, invoice_key=ikey,
                inv_base_entry=inv_line["base_entry"] or "",
                inv_base_line=inv_line["base_line"] or "",
                inv_base_type=inv_line["base_type"] or "",
                purchased_base=purchased,
            ))
            break
    targets.sort(key=lambda t: (t.po.po_docnum or "", int(t.po.line_num)))
    return targets


def load_movements(items: set[str], base_refs: set[str]) -> dict[str, Any]:
    """OINM rows for the target ItemCodes (2026) plus every row whose
    ``base_ref`` is one of the target AP invoice DocNums (any date)."""
    from modules.telchi.datalake.ducklake import DuckLakeConnector

    def _q(values: set[str]) -> str:
        return ", ".join("'" + v.replace("'", "''") + "'" for v in sorted(values))

    connector = DuckLakeConnector()
    with connector.session(read_only=True) as conn:
        window = conn.execute(
            "SELECT MIN(doc_date), MAX(doc_date), COUNT(*) "
            "FROM telchi.atomic.inventory_movement WHERE doc_date >= ?", [EXTRACT_START]
        ).fetchone()
        full_window = conn.execute(
            "SELECT MIN(doc_date), MAX(doc_date), COUNT(*) FROM telchi.atomic.inventory_movement"
        ).fetchone()
        foundation = conn.execute(
            "SELECT foundation_publication_id, status FROM telchi.ops.foundation_publications_v1 "
            "WHERE status='CURRENT'"
        ).fetchall()
        tt18 = conn.execute(
            "SELECT COUNT(*), SUM(CAST(in_qty AS DOUBLE)) FROM telchi.atomic.inventory_movement "
            "WHERE trans_type='18' AND doc_date >= ?", [EXTRACT_START]
        ).fetchone()
        rows = conn.execute(
            "SELECT trans_type, doc_date, item_code, warehouse, in_qty, out_qty, card_code, "
            "base_ref, doc_line_num FROM telchi.atomic.inventory_movement "
            f"WHERE (item_code IN ({_q(items)}) AND doc_date >= '{EXTRACT_START}') "
            f"   OR base_ref IN ({_q(base_refs)})"
        ).fetchall()

    movements: list[Movement] = []
    for tt, dd, item, whs, iq, oq, card, bref, dln in rows:
        parsed = _date(dd)
        if parsed is None:
            continue
        movements.append(Movement(
            trans_type=str(tt), doc_date=parsed, item_code=item or "", warehouse=whs or "",
            in_qty=_dec(iq) or Decimal("0"), out_qty=_dec(oq) or Decimal("0"),
            card_code=card, base_ref=None if bref is None else str(bref),
            doc_line_num=None if dln is None else str(dln),
        ))
    as_of = _date(window[1])
    return {
        "rows": movements,
        "by_item": {i: [m for m in movements if m.item_code == i] for i in items},
        "by_base_ref": {r: [m for m in movements if m.base_ref == r] for r in base_refs},
        "window": window,
        "full_window": full_window,
        "as_of": as_of,
        "foundation_current": foundation,
        "tt18": tt18,
    }


def _receipt_lineage(receipt_docnum: str, receipt_by_docnum: dict[str, list[tuple[str, str]]],
                     resolver: Resolver, po_lines: dict[tuple[str, str], PoLine]) -> dict[str, Any]:
    po_keys: set[tuple[str, str]] = set()
    paths: set[str] = set()
    for rkey in receipt_by_docnum.get(receipt_docnum, []):
        res = resolver.resolve_memo(rkey)
        paths.add(res.path)
        if res.po_key is not None:
            po_keys.add(res.po_key)
    return {
        "receipt_doc": receipt_docnum,
        "resolve_paths": sorted(paths),
        "po_docnums": sorted({
            doc for k in po_keys if k in po_lines and (doc := po_lines[k].po_docnum) is not None
        }),
        "po_keys": sorted(f"{k[0]}/{k[1]}" for k in po_keys),
    }


def collect_evidence(target: Target, data: dict[str, Any], detail: dict[str, Any],
                     movements: dict[str, Any], resolver: Resolver,
                     receipt_by_docnum: dict[str, list[tuple[str, str]]]) -> dict[str, Any]:
    po = target.po
    inv_entry, inv_line = target.invoice_key
    invoice_lines = data["invoice_lines"]
    inv_line_row = invoice_lines[target.invoice_key]
    header = detail["invoice_headers"].get(inv_entry, {})
    inv_detail = detail["invoice_lines"].get(target.invoice_key, {})
    po_comments = detail["po_comments"].get(po.po_entry)

    invoice_docnum = header.get("docnum")
    inv_comments = header.get("comments")
    inv_date = _date(header.get("docdate"))
    po_date = po.po_docdate

    # ---------------------------------------------------------- receipts
    receipts_direct_po = [
        k for k, rl in data["receipt_lines"].items()
        if rl.base_entry == po.po_entry and rl.base_line == po.line_num
    ]
    receipts_direct_invoice = [
        k for k, rl in data["receipt_lines"].items()
        if rl.base_entry == inv_entry and rl.base_line == inv_line
    ]
    receipts_by_resolver = sorted({
        k for k in data["receipt_lines"]
        if resolver.resolve_memo(k).po_key == target.key
    })
    receipt_window = movements["window"]
    receipt_window_start = _date(receipt_window[0])
    receipt_window_end = _date(receipt_window[1])
    receipt_outside = [
        k for k in set(receipts_direct_po + receipts_direct_invoice + receipts_by_resolver)
        if data["receipt_lines"][k].doc_date is not None and receipt_window_start is not None
        and receipt_window_end is not None
        and not (receipt_window_start <= data["receipt_lines"][k].doc_date <= receipt_window_end)
    ]
    receipt_window_covers_po = not (
        po_date is None or receipt_window_start is None or po_date < receipt_window_start
    )

    # ---------------------------------------------------------- OINM linkage
    linked: list[Movement] = []
    if invoice_docnum:
        for m in movements["by_base_ref"].get(str(invoice_docnum), []):
            if m.item_code == (po.item_code or "") and m.doc_line_num == inv_line:
                linked.append(m)
    linked_in = sum((m.in_qty for m in linked), Decimal("0"))
    linked_out = sum((m.out_qty for m in linked), Decimal("0"))
    purchase_reversal = any(
        m.trans_type in PURCHASE_REVERSAL_TRANS_TYPES and m.out_qty > 0 for m in linked
    )

    window_start = (po_date - timedelta(days=LOOKBACK_DAYS)) if po_date else None
    as_of = movements["as_of"]
    item_rows = movements["by_item"].get(po.item_code or "", [])

    def _in_window(m: Movement) -> bool:
        if window_start is None or as_of is None:
            return False
        return window_start <= m.doc_date <= as_of

    same_supplier = [
        m for m in item_rows
        if m.card_code == po.card_code and m.in_qty > 0 and _in_window(m)
    ]
    same_supplier_same_whs = [m for m in same_supplier if m.warehouse == (po.whs_code or "")]
    exact_qty = [
        m for m in item_rows if m.in_qty == target.purchased_base and _in_window(m)
    ]

    def _annotate(rows: list[Movement]) -> list[dict[str, Any]]:
        out = []
        for m in sorted(rows, key=lambda x: (x.doc_date, x.trans_type)):
            entry: dict[str, Any] = {
                "trans_type": m.trans_type, "date": m.doc_date.isoformat(),
                "warehouse": m.warehouse, "in_qty": str(m.in_qty), "out_qty": str(m.out_qty),
                "card_code": m.card_code, "base_ref": m.base_ref,
                "doc_line_num": m.doc_line_num,
            }
            if m.trans_type == "20" and m.base_ref:
                lineage = _receipt_lineage(m.base_ref, receipt_by_docnum, resolver, data["po_lines"])
                entry["receipt_lineage"] = lineage
                entry["belongs_to_target_line"] = target.key in {
                    tuple(k.split("/", 1)) for k in lineage["po_keys"]
                }
            elif m.trans_type == "18" and m.base_ref and invoice_docnum:
                entry["matches_target_invoice"] = m.base_ref == str(invoice_docnum)
            out.append(entry)
        return out

    annotated_supplier = _annotate(same_supplier)
    annotated_exact = _annotate(exact_qty)
    rejected = [
        e for e in annotated_supplier + annotated_exact
        if not e.get("belongs_to_target_line") and not e.get("matches_target_invoice")
    ]
    # de-duplicate rejected candidates keeping first occurrence
    seen: set[tuple[Any, ...]] = set()
    rejected_unique = []
    for e in rejected:
        sig = (e["trans_type"], e["date"], e["warehouse"], e["in_qty"], e["base_ref"])
        if sig in seen:
            continue
        seen.add(sig)
        rejected_unique.append(e)

    # Exits of the same ItemCode in the planned warehouse on the OC/invoice date:
    # context only, they carry no documentary link to this purchase line.
    key_dates = {d for d in (po_date, inv_date) if d is not None}
    outbound_details = [
        {"trans_type": m.trans_type, "date": m.doc_date.isoformat(),
         "warehouse": m.warehouse, "out_qty": str(m.out_qty),
         "card_code": m.card_code, "base_ref": m.base_ref,
         "doc_line_num": m.doc_line_num}
        for m in sorted(item_rows, key=lambda x: (x.doc_date, x.trans_type))
        if m.out_qty > 0 and m.doc_date in key_dates
        and m.warehouse == (po.whs_code or "")
    ]
    same_day_out = [d for d in outbound_details if po_date is not None and d["date"] == po_date.isoformat()]
    inv_day_out = [d for d in outbound_details if inv_date is not None and d["date"] == inv_date.isoformat()]

    # ---------------------------------------------------------- classification
    receipt_linked = bool(receipts_by_resolver or receipts_direct_po or receipts_direct_invoice)
    uom_issue = False
    for rkey in receipts_by_resolver:
        rl = data["receipt_lines"][rkey]
        ok, _ = uom_compatible(po, rl)
        if not ok or (rl.item_code is not None and rl.item_code != po.item_code):
            uom_issue = True
            break

    advance = advance_invoice_evidence(inv_comments, po_comments)
    import_inv = import_invoice_evidence(header.get("doc_cur"))
    non_inventory = (
        po.item_code is None
        or po.item_code.startswith(NON_STOCKABLE_ITEM_PREFIX)
        or target.purchased_base <= 0
    )
    invoice_determinable = bool(inv_entry and invoice_docnum and inv_date is not None)

    ev = Evidence(
        po_canceled=po.po_canceled in CANCELLED_VALUES,
        invoice_canceled=header.get("canceled") in CANCELLED_VALUES,
        purchase_reversal=purchase_reversal,
        non_inventory=non_inventory,
        receipt_window_covers_po=receipt_window_covers_po,
        receipt_outside_window=bool(receipt_outside),
        uom_issue=uom_issue,
        receipt_linked=receipt_linked,
        linked_inbound_base=linked_in,
        advance_invoice=advance,
        import_invoice=import_inv,
        invoice_determinable=invoice_determinable,
    )
    category, reason = classify(ev)

    product = data["products"].get(po.item_code or "", {})
    supplier_name = data["suppliers"].get(po.card_code or "")
    row = {
        "po_entry": po.po_entry, "po_line": po.line_num, "po_docnum": po.po_docnum,
        "po_date": po_date.isoformat() if po_date else None,
        "po_line_status": po.line_status, "po_open_qty": str(po.open_qty),
        "po_canceled": po.po_canceled, "po_comments": po_comments,
        "item_code": po.item_code, "item_name": product.get("name"),
        "product_group": product.get("group"),
        "warehouse_planned": po.whs_code,
        "warehouse_name": data["warehouses"].get(po.whs_code or {}, {}).get("name"),
        "supplier": po.card_code, "supplier_name": supplier_name,
        "tipo_compra": po.tipo_compra,
        "purchased_base": str(target.purchased_base),
        "inv_entry": inv_entry, "inv_line": inv_line,
        "inv_docnum": invoice_docnum, "inv_date": inv_date.isoformat() if inv_date else None,
        "inv_canceled": header.get("canceled"), "inv_status": header.get("status"),
        "inv_currency": header.get("doc_cur"), "inv_total": str(header.get("doc_total")),
        "inv_num_at_card": header.get("num_at_card"),
        "inv_comments": inv_comments,
        "inv_line_status": inv_detail.get("line_status"),
        "inv_open_qty": str(inv_detail.get("open_qty")),
        "inv_quantity": str(inv_line_row.get("quantity")),
        "inv_base_type": target.inv_base_type, "inv_base_entry": target.inv_base_entry,
        "inv_base_line": target.inv_base_line,
        "days_po_to_inv": (inv_date - po_date).days if inv_date and po_date else None,
        "receipts_direct_to_po": len(receipts_direct_po),
        "receipts_direct_to_invoice": len(receipts_direct_invoice),
        "receipts_via_lineage": len(receipts_by_resolver),
        "receipts_outside_window": len(receipt_outside),
        "receipt_window": [receipt_window[0], receipt_window[1]],
        "receipt_window_covers_po": receipt_window_covers_po,
        "linked_movements": [
            {"trans_type": m.trans_type, "date": m.doc_date.isoformat(),
             "warehouse": m.warehouse, "in_qty": str(m.in_qty), "out_qty": str(m.out_qty),
             "card_code": m.card_code, "base_ref": m.base_ref,
             "doc_line_num": m.doc_line_num}
            for m in linked
        ],
        "linked_inbound_base": str(linked_in),
        "linked_outbound_base": str(linked_out),
        "purchase_reversal": purchase_reversal,
        "candidate_same_supplier": annotated_supplier,
        "candidate_same_supplier_same_whs": len(same_supplier_same_whs),
        "candidate_exact_qty": annotated_exact,
        "rejected_candidates": rejected_unique,
        "outbound_same_day_po": len(same_day_out),
        "outbound_same_day_inv": len(inv_day_out),
        "outbound_same_day_details": outbound_details,
        "days_inv_to_as_of": (as_of - inv_date).days if as_of and inv_date else None,
        "advance_invoice_evidence": advance,
        "import_invoice_evidence": import_inv,
        "invoice_determinable": invoice_determinable,
        "non_inventory_exception": non_inventory,
        "category": category,
        "category_label": CATEGORY_LABELS[category],
        "category_reason": reason,
    }
    return row


def analyze() -> dict[str, Any]:
    data = build_datasets()
    detail = load_document_detail()
    targets = select_targets(data, detail)

    items = {t.po.item_code or "" for t in targets}
    base_refs = set()
    for t in targets:
        header = detail["invoice_headers"].get(t.invoice_key[0], {})
        if header.get("docnum"):
            base_refs.add(str(header["docnum"]))

    resolver = Resolver(data["receipt_lines"], data["invoice_lines"], data["po_lines"])
    receipt_by_docnum: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for rkey, rl in data["receipt_lines"].items():
        if rl.doc_num:
            receipt_by_docnum[rl.doc_num].append(rkey)

    movements = load_movements(items, base_refs)

    results = [
        collect_evidence(t, data, detail, movements, resolver, receipt_by_docnum)
        for t in targets
    ]

    class_stats = {
        c: {"lines": 0, "purchased_base": Decimal("0")} for c in CLASS_ORDER
    }
    for row in results:
        cat = row["category"]
        class_stats[cat]["lines"] += 1
        class_stats[cat]["purchased_base"] += Decimal(row["purchased_base"])

    keys = [(r["po_entry"], r["po_line"]) for r in results]
    linked_keys = [
        (r["inv_docnum"], r["inv_line"], r["item_code"])
        for r in results if r["linked_movements"]
    ]
    controls = {
        "target_lines": len(results),
        "target_lines_expected": 25,
        "purchased_base_total": str(sum((Decimal(r["purchased_base"]) for r in results), Decimal("0"))),
        "purchased_base_expected": "683025",
        "duplicate_keys": len(keys) - len(set(keys)),
        "item_code_null": sum(1 for r in results if not r["item_code"]),
        "item_code_preserved": sum(1 for r in results if r["item_code"]),
        "invalid_po_lines": sum(
            1 for r in results
            if r["po_canceled"] in CANCELLED_VALUES or r["po_line_status"] != "C"
        ),
        "invalid_invoices": sum(
            1 for r in results
            if r["inv_canceled"] in CANCELLED_VALUES or not r["inv_docnum"]
        ),
        "unclassified": sum(1 for r in results if r["category"] not in CLASS_ORDER),
        "category_partition_ok": sum(class_stats[c]["lines"] for c in CLASS_ORDER) == len(results),
        "receipts_linked_to_targets": sum(
            r["receipts_direct_to_po"] + r["receipts_direct_to_invoice"] + r["receipts_via_lineage"]
            for r in results
        ),
        "linked_movement_key_collisions": len(linked_keys) - len(set(linked_keys)),
        "linked_movement_item_mismatch": sum(
            1 for r in results
            for m in r["linked_movements"] if m.get("card_code") not in (None, r["supplier"])
        ),
        "linked_movement_count": sum(len(r["linked_movements"]) for r in results),
        "reversal_detected": sum(1 for r in results if r["purchase_reversal"]),
        "rejected_candidates_total": sum(len(r["rejected_candidates"]) for r in results),
        "base_types_preserved": sorted({r["inv_base_type"] for r in results}),
        "base_entries_match_po": sum(
            1 for r in results if r["inv_base_entry"] != r["po_entry"] or r["inv_base_line"] != r["po_line"]
        ),
    }

    totals = {
        "target_lines": len(results),
        "purchased_base": str(sum((Decimal(r["purchased_base"]) for r in results), Decimal("0"))),
        "lines_with_receipt": sum(1 for r in results if r["receipts_via_lineage"] or r["receipts_direct_to_po"]),
        "lines_with_inventory_entry": sum(1 for r in results if Decimal(r["linked_inbound_base"]) > 0),
        "lines_without_any_movement": sum(1 for r in results if not r["linked_movements"]),
        "advance_invoice_lines": sum(1 for r in results if r["advance_invoice_evidence"]),
        "import_invoice_lines": sum(1 for r in results if r["import_invoice_evidence"]),
        "rejected_candidate_lines": sum(1 for r in results if r["rejected_candidates"]),
    }

    return {
        "results": results,
        "class_stats": {c: {"lines": s["lines"], "purchased_base": str(s["purchased_base"])}
                        for c, s in class_stats.items()},
        "totals": totals,
        "controls": controls,
        "windows": {
            "purchase_receipt_window": [movements["window"][0], movements["window"][1]],
            "movement_window_2026": [movements["full_window"][0], movements["full_window"][1]],
            "as_of": movements["as_of"].isoformat() if movements["as_of"] else None,
            "tt18_2026": {"movements": movements["tt18"][0],
                          "in_qty_base": str(movements["tt18"][1])},
        },
        "foundation_current": movements["foundation_current"],
    }
