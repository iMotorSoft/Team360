"""TELCHI_PURCHASE_TO_WAREHOUSE_RECEIPT_RECONCILIATION_V1 - core module.

Data Lake only. READ ONLY. No SAP/HANA access of any kind.

Reconciles purchase documents against warehouse receipts at document + line +
ItemCode grain using explicit base/target documentary links materialized in the
Telchi Data Lake:

  purchase_order / purchase_order_line      (OPOR / POR1, fact capture V1)
  purchase_receipt / purchase_receipt_line  (OPDN / PDN1, fact capture V1)
  ap_invoice / ap_invoice_line              (OPCH / PCH1, purchasing lineage V1)
  atomic.inventory_movement                 (OINM, Foundation CURRENT component)
  reference products / warehouses / suppliers (Foundation reference component)

Chain of evidence (all links are source-native BaseType/BaseEntry/BaseLine):

  PO line  <-direct- receipt line                      (BaseType=22)
  PO line  <-invoice- receipt line -> AP invoice line  (BaseType=18 -> 22)
  PO line  <-grpo---- receipt line -> receipt line ... (BaseType=20, recursive)

Receipt validity excludes header CANCELED in {'Y','C'} (empirically validated:
'Y' originals are offset by paired 'C' reversal documents with net zero
movements in OINM). PO validity excludes CANCELED='Y'.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

DATA_ROOT = Path("/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi")
FACT_CAPTURE = DATA_ROOT / "raw" / "sap" / "TELCHI_DATALAKE_MATERIAL_SUPPLY_FACT_CAPTURE_V1"
PURCHASING_LINEAGE = DATA_ROOT / "raw" / "sap" / "TELCHI_DATALAKE_MATERIAL_SUPPLY_PURCHASING_LINEAGE_V1"
REFERENCE = DATA_ROOT / "reference"

GATE = "TELCHI_PURCHASE_TO_WAREHOUSE_RECEIPT_RECONCILIATION_V1"
SAP_ACCESSED = "NO"
SAP_QUERY_COUNT = 0
SAP_WRITE_COUNT = 0

# Items that model import charges / non-stockable expenses (I- prefix family:
# flete, ICE, seguros, peajes, IVA, comisiones...). Identified from the Data
# Lake reference component (name/product_group) and from the fact that they
# never post an OINM movement.
NON_STOCKABLE_ITEM_PREFIX = "I-"
NON_STOCKABLE_WAREHOUSE = "ALM-IMP"

CANCELLED_VALUES = {"Y", "C"}

CLASS_ORDER = [
    "EXACT_RECEIPT",
    "MULTI_RECEIPT_COMPLETE",
    "PARTIAL_RECEIPT",
    "MULTI_RECEIPT_PARTIAL",
    "OVER_RECEIPT",
    "NO_RECEIPT",
    "NOT_DETERMINABLE",
]


def _dec(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _base_qty(qty: Any, num_per: Any) -> Decimal | None:
    """Quantity expressed in the line's UoM; NumPerMsr converts to item base
    units. Semantics proven against OINM: movement_qty == Quantity * NumPerMsr
    for 15,660/15,660 matched valid receipt lines."""
    q = _dec(qty)
    if q is None:
        return None
    n = _dec(num_per)
    if n is None:
        return None
    return q * n


def _date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.fromisoformat(str(value)[:10]).date()
    except ValueError:
        return None


@dataclass
class PoLine:
    po_entry: str
    line_num: str
    item_code: str | None
    quantity: Any
    num_per_msr: Any
    unit_msr: str | None
    whs_code: str | None
    line_status: str | None
    tipo_compra: str | None
    description: str | None
    po_docdate: date | None
    ship_date: date | None
    open_qty: Any
    po_docnum: str | None
    card_code: str | None
    po_canceled: str | None

    @property
    def key(self) -> tuple[str, str]:
        return (self.po_entry, self.line_num)


@dataclass
class ReceiptLine:
    doc_entry: str
    line_num: str
    base_entry: str | None
    base_type: str | None
    base_line: str | None
    item_code: str | None
    quantity: Any
    num_per_msr: Any
    unit_msr: str | None
    whs_code: str | None
    doc_date: date | None
    canceled: str
    doc_num: str
    card_code: str | None

    @property
    def key(self) -> tuple[str, str]:
        return (self.doc_entry, self.line_num)


@dataclass
class LinkResult:
    po_key: tuple[str, str] | None
    path: str
    detail: str = ""


class Resolver:
    """Resolves a receipt line to its PO line through explicit base/target
    documentary links only. Memoized, depth limited, cycle safe."""

    def __init__(
        self,
        receipt_lines: dict[tuple[str, str], ReceiptLine],
        invoice_lines: dict[tuple[str, str], dict[str, Any]],
        po_lines: dict[tuple[str, str], PoLine],
        max_depth: int = 6,
    ) -> None:
        self.receipt_lines = receipt_lines
        self.invoice_lines = invoice_lines
        self.po_lines = po_lines
        self.max_depth = max_depth
        self._memo: dict[tuple[str, str], LinkResult] = {}

    def resolve(self, key: tuple[str, str], depth: int = 0) -> LinkResult:
        if key in self._memo and depth == 0:
            return self._memo[key]
        if depth > self.max_depth:
            return LinkResult(None, "MAX_DEPTH")
        line = self.receipt_lines.get(key)
        if line is None:
            return LinkResult(None, "RECEIPT_LINE_MISSING")
        bt, be, bl = line.base_type, line.base_entry, line.base_line
        if bt == "22":
            return LinkResult((be, bl), "DIRECT_PO")
        if bt == "18":
            inv = self.invoice_lines.get((be, bl))
            if inv is None:
                return LinkResult(None, "AP_LINE_NOT_MATERIALIZED")
            ibt = inv.get("base_type")
            if ibt == "22":
                return LinkResult((inv.get("base_entry"), inv.get("base_line")), "VIA_AP_INVOICE")
            if ibt == "20":
                # invoice line based on a GRPO: walk into that receipt line
                return self.resolve((inv.get("base_entry"), inv.get("base_line")), depth + 1)
            if ibt == "-1":
                return LinkResult(None, "AP_INVOICE_NO_PO")
            return LinkResult(None, f"AP_INVOICE_BASE_{ibt}")
        if bt == "20":
            return self.resolve((be, bl), depth + 1)
        if bt == "-1":
            return LinkResult(None, "NO_BASE_DOCUMENT")
        return LinkResult(None, f"BASE_TYPE_{bt}")

    def resolve_memo(self, key: tuple[str, str]) -> LinkResult:
        if key not in self._memo:
            self._memo[key] = self.resolve(key, 0)
        return self._memo[key]


def classify(purchased: Decimal | None, received: Decimal | None, n_receipts: int,
             uom_compatible: bool) -> str:
    if n_receipts == 0:
        return "NO_RECEIPT"
    if not uom_compatible or purchased is None:
        return "NOT_DETERMINABLE"
    if received is None:
        return "NOT_DETERMINABLE"
    if received == purchased:
        return "EXACT_RECEIPT" if n_receipts == 1 else "MULTI_RECEIPT_COMPLETE"
    if received < purchased:
        return "PARTIAL_RECEIPT" if n_receipts == 1 else "MULTI_RECEIPT_PARTIAL"
    return "OVER_RECEIPT"


def uom_compatible(po: PoLine, rc: ReceiptLine) -> tuple[bool, str]:
    """Compatible when both lines carry the same explicit unitMsr. When both
    unitMsr are absent, the explicit NumPerMsr (units per measure) must match;
    otherwise the comparison cannot be defended and the line is
    NOT_DETERMINABLE."""
    pu, ru = po.unit_msr, rc.unit_msr
    if pu is not None and ru is not None:
        return (pu == ru), f"unitMsr:{pu}|{ru}"
    pn, rn = _dec(po.num_per_msr), _dec(rc.num_per_msr)
    if pu is None and ru is None and pn is not None and pn == rn:
        return True, f"unitMsr_absent_numPerMsr:{pn}"
    return False, f"unitMsr_unresolvable:{pu}|{ru} numPerMsr:{po.num_per_msr}|{rc.num_per_msr}"


def build_datasets() -> dict[str, Any]:
    """Load the materialized datasets (read-only, Data Lake only)."""
    import duckdb

    con = duckdb.connect()

    def q(sql: str) -> list[tuple]:
        return con.execute(sql).fetchall()

    def cols(sql: str) -> list[str]:
        return [c[0] for c in con.execute(sql).fetchall()]

    po_glob = str(FACT_CAPTURE / "purchase_order" / "**" / "*.parquet")
    pol_glob = str(FACT_CAPTURE / "purchase_order_line" / "**" / "*.parquet")
    pr_glob = str(FACT_CAPTURE / "purchase_receipt" / "**" / "*.parquet")
    prl_glob = str(FACT_CAPTURE / "purchase_receipt_line" / "**" / "*.parquet")
    inv_glob = str(PURCHASING_LINEAGE / "ap_invoice" / "*" / "*" / "*.parquet")
    inl_glob = str(PURCHASING_LINEAGE / "ap_invoice_line" / "*" / "*" / "*.parquet")

    po_rows = q(
        "SELECT CAST(DocEntry AS VARCHAR), CAST(DocNum AS VARCHAR), CANCELED, "
        "CAST(DocDate AS DATE), CAST(CardCode AS VARCHAR), DocStatus, U_TIPOCOMPRA "
        f"FROM read_parquet('{po_glob}')"
    )
    pol_rows = q(
        "SELECT CAST(DocEntry AS VARCHAR), CAST(LineNum AS VARCHAR), ItemCode, Quantity, "
        "NumPerMsr, unitMsr, WhsCode, LineStatus, U_TIPOCOMPRA, Dscription, "
        "CAST(ShipDate AS DATE), OpenQty "
        f"FROM read_parquet('{pol_glob}')"
    )
    pr_rows = q(
        "SELECT CAST(DocEntry AS VARCHAR), CAST(DocNum AS VARCHAR), CANCELED, "
        "CAST(DocDate AS DATE), CAST(CardCode AS VARCHAR), DocStatus "
        f"FROM read_parquet('{pr_glob}')"
    )
    prl_rows = q(
        "SELECT CAST(DocEntry AS VARCHAR), CAST(LineNum AS VARCHAR), "
        "CAST(CAST(CAST(BaseEntry AS DOUBLE) AS BIGINT) AS VARCHAR) AS BaseEntry, "
        "CAST(CAST(BaseType AS DOUBLE) AS BIGINT) AS BaseType, "
        "CAST(CAST(CAST(BaseLine AS DOUBLE) AS BIGINT) AS VARCHAR) AS BaseLine, ItemCode, Quantity, NumPerMsr, "
        "unitMsr, WhsCode, CAST(DocDate AS DATE) "
        f"FROM read_parquet('{prl_glob}')"
    )
    inv_rows = q(
        "SELECT CAST(DocEntry AS VARCHAR), CAST(DocNum AS VARCHAR), CANCELED, "
        "CAST(DocDate AS DATE), CAST(CardCode AS VARCHAR), U_TIPOCOMPRA, DocStatus "
        f"FROM read_parquet('{inv_glob}')"
    )
    inl_rows = q(
        "SELECT CAST(DocEntry AS VARCHAR), CAST(LineNum AS VARCHAR), "
        "CAST(CAST(CAST(BaseEntry AS DOUBLE) AS BIGINT) AS VARCHAR) AS BaseEntry, "
        "CAST(CAST(BaseType AS DOUBLE) AS BIGINT) AS BaseType, "
        "CAST(CAST(CAST(BaseLine AS DOUBLE) AS BIGINT) AS VARCHAR) AS BaseLine, ItemCode, Quantity, NumPerMsr, "
        "unitMsr, WhsCode, CAST(DocDate AS DATE) "
        f"FROM read_parquet('{inl_glob}')"
    )
    products = q(
        "SELECT code, name, product_group, inventory_uom, purchase_uom "
        f"FROM read_parquet('{REFERENCE / 'products' / 'part-00000.parquet'}')"
    )
    warehouses = q(
        "SELECT code, name, warehouse_role_id "
        f"FROM read_parquet('{REFERENCE / 'warehouses' / 'part-00000.parquet'}')"
    )
    suppliers = q(
        "SELECT code, name "
        f"FROM read_parquet('{REFERENCE / 'suppliers' / 'part-00000.parquet'}')"
    )
    con.close()

    headers_po = {
        e: {"docnum": dn, "canceled": c, "docdate": d, "cardcode": cc, "status": st, "tipo": tp}
        for e, dn, c, d, cc, st, tp in po_rows
    }
    po_lines: dict[tuple[str, str], PoLine] = {}
    for (e, ln, item, qty, npm, um, whs, st, tipo, desc, ship, openq) in pol_rows:
        h = headers_po.get(e, {})
        po_lines[(e, ln)] = PoLine(
            po_entry=e, line_num=ln, item_code=item, quantity=qty, num_per_msr=npm,
            unit_msr=um, whs_code=whs, line_status=st, tipo_compra=tipo,
            description=desc, po_docdate=h.get("docdate"), ship_date=ship,
            open_qty=openq, po_docnum=h.get("docnum"), card_code=h.get("cardcode"),
            po_canceled=h.get("canceled"),
        )
    headers_pr = {
        e: {"docnum": dn, "canceled": c, "docdate": d, "cardcode": cc, "status": st}
        for e, dn, c, d, cc, st in pr_rows
    }
    receipt_lines: dict[tuple[str, str], ReceiptLine] = {}
    for (e, ln, be, bt, bl, item, qty, npm, um, whs, ddate) in prl_rows:
        h = headers_pr.get(e, {})
        receipt_lines[(e, ln)] = ReceiptLine(
            doc_entry=e, line_num=ln, base_entry=be, base_type=None if bt is None else str(bt),
            base_line=bl,
            item_code=item, quantity=qty, num_per_msr=npm, unit_msr=um, whs_code=whs,
            doc_date=ddate or h.get("docdate"), canceled=h.get("canceled", "N"),
            doc_num=h.get("docnum", ""), card_code=h.get("cardcode"),
        )
    headers_inv = {
        e: {"docnum": dn, "canceled": c, "docdate": d, "cardcode": cc, "tipo": tp, "status": st}
        for e, dn, c, d, cc, tp, st in inv_rows
    }
    invoice_lines: dict[tuple[str, str], dict[str, Any]] = {}
    for (e, ln, be, bt, bl, item, qty, npm, um, whs, ddate) in inl_rows:
        h = headers_inv.get(e, {})
        invoice_lines[(e, ln)] = {
            "doc_entry": e, "line_num": ln, "base_entry": be,
            "base_type": None if bt is None else str(bt),
            "base_line": bl, "item_code": item, "quantity": qty, "num_per_msr": npm,
            "unit_msr": um, "whs_code": whs,
            "doc_date": ddate or h.get("docdate"), "canceled": h.get("canceled", "N"),
            "doc_num": h.get("docnum"), "card_code": h.get("cardcode"),
            "tipo": h.get("tipo"), "po_entry": be if bt == "22" else None,
            "po_line": bl if bt == "22" else None,
        }
    return {
        "po_headers": headers_po,
        "po_lines": po_lines,
        "receipt_headers": headers_pr,
        "receipt_lines": receipt_lines,
        "invoice_headers": headers_inv,
        "invoice_lines": invoice_lines,
        "products": {r[0]: {"name": r[1], "group": r[2], "inv_uom": r[3], "pur_uom": r[4]} for r in products},
        "warehouses": {r[0]: {"name": r[1], "role": r[2]} for r in warehouses},
        "suppliers": {r[0]: r[1] for r in suppliers},
    }


def load_movements() -> dict[str, Any]:
    """OINM (Foundation CURRENT) read-only extract: TT20 goods receipt
    movements keyed by (base_ref = OPDN DocNum, doc_line_num) and TT21
    purchase-return movements aggregated."""
    from modules.telchi.datalake.ducklake import DuckLakeConnector

    connector = DuckLakeConnector()
    with connector.session(read_only=True) as conn:
        tt20 = conn.execute(
            "SELECT base_ref, doc_line_num, SUM(CAST(in_qty AS DOUBLE)), "
            "MAX(warehouse), COUNT(*), MIN(doc_date), MAX(doc_date) "
            "FROM telchi.atomic.inventory_movement WHERE trans_type='20' GROUP BY 1, 2"
        ).fetchall()
        tt20_docs = {r[0] for r in conn.execute(
            "SELECT DISTINCT base_ref FROM telchi.atomic.inventory_movement WHERE trans_type='20'"
        ).fetchall()}
        tt21 = conn.execute(
            "SELECT item_code, warehouse, card_code, SUM(CAST(out_qty AS DOUBLE)), COUNT(*), MIN(doc_date), MAX(doc_date) "
            "FROM telchi.atomic.inventory_movement WHERE trans_type='21' AND doc_date >= '2026-01-01' GROUP BY 1, 2, 3"
        ).fetchall()
        tt21_total = conn.execute(
            "SELECT COUNT(*), SUM(CAST(out_qty AS DOUBLE)), COUNT(DISTINCT card_code), MIN(doc_date), MAX(doc_date) "
            "FROM telchi.atomic.inventory_movement WHERE trans_type='21' AND doc_date >= '2026-01-01'"
        ).fetchone()
        tt18 = conn.execute(
            "SELECT COUNT(*), COUNT(DISTINCT base_ref), MIN(doc_date), MAX(doc_date) "
            "FROM telchi.atomic.inventory_movement WHERE trans_type='18' AND doc_date >= '2026-01-01'"
        ).fetchone()
        oinm_window = conn.execute(
            "SELECT MIN(doc_date), MAX(doc_date), COUNT(*) FROM telchi.atomic.inventory_movement WHERE doc_date >= '2026-01-01'"
        ).fetchone()
        foundation_pointer = conn.execute(
            "SELECT foundation_publication_id, status FROM telchi.ops.foundation_publications_v1 WHERE status='CURRENT'"
        ).fetchall()
    movements = {(r[0], str(r[1])): {"qty": r[2], "whs": r[3], "n": r[4]} for r in tt20}
    return {
        "tt20_by_line": movements,
        "tt20_docs": tt20_docs,
        "tt21_rows": tt21,
        "tt21_total": tt21_total,
        "tt18": tt18,
        "oinm_window": oinm_window,
        "foundation_current": foundation_pointer,
    }


def run_reconciliation(data: dict[str, Any], movements: dict[str, Any]) -> dict[str, Any]:
    po_lines: dict[tuple[str, str], PoLine] = data["po_lines"]
    receipt_lines: dict[tuple[str, str], ReceiptLine] = data["receipt_lines"]
    invoice_lines: dict[tuple[str, str], dict[str, Any]] = data["invoice_lines"]
    resolver = Resolver(receipt_lines, invoice_lines, po_lines)

    # ---------------------------------------------------------------- receipts
    path_stats: dict[str, int] = defaultdict(int)
    unresolved_samples: list[dict[str, Any]] = []
    resolved_po_missing = 0
    links: dict[tuple[str, str], list[tuple[ReceiptLine, LinkResult]]] = defaultdict(list)
    canceled_receipt_lines = 0
    unresolved_valid_receipt_lines = 0
    item_mismatch = 0
    uom_incompatible_pairs = 0
    fanout_check: dict[tuple[str, str], set] = defaultdict(set)
    receipts_without_movement: set[str] = set()
    movement_controls = {"matched": 0, "qty_equal": 0, "whs_equal": 0, "no_movement": 0}
    linked_receipt_docs: set[str] = set()

    tt20 = movements["tt20_by_line"]
    for key, rl in receipt_lines.items():
        if rl.canceled in CANCELLED_VALUES:
            canceled_receipt_lines += 1
            continue
        res = resolver.resolve_memo(key)
        path_stats[res.path] += 1
        if res.po_key is None:
            unresolved_valid_receipt_lines += 1
            if len(unresolved_samples) < 40:
                unresolved_samples.append({
                    "receipt_doc": rl.doc_num, "date": rl.doc_date.isoformat() if rl.doc_date else None,
                    "item": rl.item_code, "warehouse": rl.whs_code, "path": res.path,
                    "base_entry": rl.base_entry, "base_line": rl.base_line,
                })
            continue
        if res.po_key not in po_lines:
            unresolved_valid_receipt_lines += 1
            resolved_po_missing += 1
            if len(unresolved_samples) < 40:
                unresolved_samples.append({
                    "receipt_doc": rl.doc_num, "date": rl.doc_date.isoformat() if rl.doc_date else None,
                    "item": rl.item_code, "warehouse": rl.whs_code, "path": "PO_LINE_OUT_OF_EXTRACT",
                    "po_entry": res.po_key[0], "po_line": res.po_key[1],
                })
            continue
        po = po_lines[res.po_key]
        if po.po_canceled in CANCELLED_VALUES:
            # receipt linked to a cancelled PO: keep classified separately
            path_stats["LINKED_TO_CANCELLED_PO"] += 1
            continue
        if rl.item_code is not None and po.item_code is not None and rl.item_code != po.item_code:
            item_mismatch += 1
        ok, _ = uom_compatible(po, rl)
        if not ok:
            uom_incompatible_pairs += 1
        links[res.po_key].append((rl, res))
        fanout_check[key].add(res.po_key)
        linked_receipt_docs.add(rl.doc_num)
        mv = tt20.get((rl.doc_num, str(rl.line_num)))
        if mv is None:
            movement_controls["no_movement"] += 1
            receipts_without_movement.add(rl.doc_num)
        else:
            movement_controls["matched"] += 1
            b = _base_qty(rl.quantity, rl.num_per_msr)
            if b is not None and float(b) == float(mv["qty"]):
                movement_controls["qty_equal"] += 1
            if rl.whs_code is not None and rl.whs_code == mv["whs"]:
                movement_controls["whs_equal"] += 1

    fanout_violations = sum(1 for k, v in fanout_check.items() if len(v) > 1)

    # ------------------------------------------------------- classify PO lines
    main_universe: list[dict[str, Any]] = []
    non_inventory_lines: list[dict[str, Any]] = []
    cancelled_po_lines = 0
    for key, po in po_lines.items():
        if po.po_canceled in CANCELLED_VALUES:
            cancelled_po_lines += 1
            continue
        if po.item_code is None or _dec(po.quantity) in (None, Decimal("0")):
            non_inventory_lines.append({
                "reason": "NO_ITEM_OR_ZERO_QTY", "po_entry": po.po_entry,
                "line_num": po.line_num, "tipo": po.tipo_compra,
                "description": (po.description or "")[:80],
            })
            continue
        if po.item_code.startswith(NON_STOCKABLE_ITEM_PREFIX):
            non_inventory_lines.append({
                "reason": "IMPORT_CHARGE_ITEM", "po_entry": po.po_entry,
                "line_num": po.line_num, "tipo": po.tipo_compra,
                "item_code": po.item_code, "description": (po.description or "")[:80],
            })
            continue
        main_universe.append({"po": po, "key": key})  # type: ignore[arg-type]

    results: list[dict[str, Any]] = []
    for entry in main_universe:
        po: PoLine = entry["po"]  # type: ignore[assignment]
        key: tuple[str, str] = entry["key"]  # type: ignore[assignment]
        paired = links.get(key, [])
        purchased = _base_qty(po.quantity, po.num_per_msr)
        uom_ok = True
        uom_notes: list[str] = []
        received = Decimal("0")
        whs_set: set[str] = set()
        receipts: list[dict[str, Any]] = []
        for rl, res in sorted(paired, key=lambda x: (x[0].doc_date or date.max, x[0].doc_entry)):
            ok, note = uom_compatible(po, rl)
            if not ok:
                uom_ok = False
                uom_notes.append(note)
            if rl.item_code != po.item_code:
                uom_ok = False
                uom_notes.append(f"item_mismatch:{rl.item_code}")
            b = _base_qty(rl.quantity, rl.num_per_msr)
            if b is None:
                uom_ok = False
                uom_notes.append("receipt_base_qty_undetermined")
            else:
                received += b
            if rl.whs_code:
                whs_set.add(rl.whs_code)
            receipts.append({
                "receipt_doc": rl.doc_num, "receipt_entry": rl.doc_entry,
                "line": rl.line_num, "date": rl.doc_date.isoformat() if rl.doc_date else None,
                "qty_base": str(b) if b is not None else None,
                "qty_line_uom": str(_dec(rl.quantity)),
                "unit_msr": rl.unit_msr, "warehouse": rl.whs_code,
                "path": res.path,
            })
        if po.item_code is None or purchased is None:
            uom_ok = False
            uom_notes.append("purchase_base_qty_undetermined")
        status = classify(purchased, received if uom_ok else None, len({r["receipt_doc"] for r in receipts}), uom_ok)
        gap = None
        if uom_ok and purchased is not None:
            gap = received - purchased
        lead_days = None
        if receipts and receipts[0]["date"] and po.po_docdate:
            lead_days = (_date(receipts[0]["date"]) - po.po_docdate).days
        results.append({
            "po_entry": po.po_entry, "po_docnum": po.po_docnum, "line_num": po.line_num,
            "item_code": po.item_code, "supplier": po.card_code,
            "tipo_compra": po.tipo_compra, "po_date": po.po_docdate.isoformat() if po.po_docdate else None,
            "ship_date": po.ship_date.isoformat() if po.ship_date else None,
            "line_status": po.line_status, "warehouse_planned": po.whs_code,
            "uom": po.unit_msr, "num_per_msr": str(po.num_per_msr),
            "purchased_base": str(purchased) if purchased is not None else None,
            "received_base": str(received) if uom_ok and purchased is not None else None,
            "gap_base": str(gap) if gap is not None else None,
            "n_receipts": len({r["receipt_doc"] for r in receipts}),
            "n_receipt_lines": len(receipts),
            "warehouses_received": sorted(whs_set),
            "multi_warehouse": len(whs_set) > 1,
            "status": status,
            "uom_compatible": uom_ok,
            "uom_notes": uom_notes[:3],
            "receipts": receipts,
            "lead_days_first_receipt": lead_days,
        })

    # ------------------------------------------------------------- metrics
    class_stats: dict[str, dict[str, Any]] = {
        c: {"lines": 0, "purchased_base": Decimal("0"), "received_base": Decimal("0"),
            "comparable_lines": 0}
        for c in CLASS_ORDER
    }
    for r in results:
        s = class_stats[r["status"]]
        s["lines"] += 1
        if r["uom_compatible"] and r["purchased_base"] is not None:
            s["comparable_lines"] += 1
            s["purchased_base"] += Decimal(r["purchased_base"])
            if r["received_base"] is not None:
                s["received_base"] += Decimal(r["received_base"])

    total_main = len(results)
    total_purchased = sum((Decimal(r["purchased_base"]) for r in results
                           if r["purchased_base"] is not None), Decimal("0"))
    total_received = sum((Decimal(r["received_base"]) for r in results
                          if r["received_base"] is not None), Decimal("0"))
    uom_compatible_lines = sum(1 for r in results if r["uom_compatible"])
    uom_incompatible_lines = total_main - uom_compatible_lines
    fully_reconciled = sum(
        1 for r in results if r["status"] in ("EXACT_RECEIPT", "MULTI_RECEIPT_COMPLETE"))
    multi_receipt_lines = sum(1 for r in results if r["n_receipts"] > 1)
    multi_warehouse_lines = sum(1 for r in results if r["multi_warehouse"])

    # ------------------------------------------------------------ warehouse view
    wh_view: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "receipt_docs": set(), "receipt_lines": 0, "po_lines": set(),
        "qty_by_uom": defaultdict(Decimal), "difference_po_lines": set(),
    })
    for r in results:
        for rc in r["receipts"]:
            wh = rc["warehouse"] or "(sin almacen)"
            v = wh_view[wh]
            v["receipt_docs"].add(rc["receipt_doc"])
            v["receipt_lines"] += 1
            v["po_lines"].add((r["po_entry"], r["line_num"]))
            if r["status"] not in ("EXACT_RECEIPT", "MULTI_RECEIPT_COMPLETE"):
                v["difference_po_lines"].add((r["po_entry"], r["line_num"]))
            if rc["qty_line_uom"] is not None:
                v["qty_by_uom"][r["uom"] or "(sin uom)"] += Decimal(rc["qty_line_uom"])
    warehouse_rows = []
    for wh, v in sorted(wh_view.items(), key=lambda kv: -kv[1]["receipt_lines"]):
        warehouse_rows.append({
            "warehouse": wh,
            "warehouse_name": data["warehouses"].get(wh, {}).get("name"),
            "receipt_documents": len(v["receipt_docs"]),
            "receipt_lines": v["receipt_lines"],
            "po_lines_received": len(v["po_lines"]),
            "qty_base_by_uom": {k: str(x) for k, x in
                                sorted(v["qty_by_uom"].items(), key=lambda kv: -kv[1])},
            "difference_po_lines": len(v["difference_po_lines"]),
        })

    # ---------------------------------------------------- uom breakdown (totals)
    uom_breakdown: dict[str, dict[str, Decimal]] = defaultdict(
        lambda: {"purchased": Decimal("0"), "received": Decimal("0"), "lines": Decimal("0")})
    for r in results:
        u = r["uom"] or "(sin uom)"
        uom_breakdown[u]["lines"] += 1
        if r["purchased_base"] is not None:
            uom_breakdown[u]["purchased"] += Decimal(r["purchased_base"]) / (
                Decimal(str(r["num_per_msr"])) if _dec(r["num_per_msr"]) else Decimal("1"))
        if r["received_base"] is not None:
            uom_breakdown[u]["received"] += Decimal(r["received_base"]) / (
                Decimal(str(r["num_per_msr"])) if _dec(r["num_per_msr"]) else Decimal("1"))
    uom_rows = [
        {"uom": u, "lines": int(v["lines"]), "purchased_qty": str(v["purchased"]),
         "received_qty": str(v["received"])}
        for u, v in sorted(uom_breakdown.items(), key=lambda kv: -kv[1]["lines"])
    ]

    # -------------------------------------------------- invoice view (secondary)
    inv_view = _invoice_receipt_view(data, resolver)

    # ------------------------------------------------------------ exceptions
    def top(rows: list[dict[str, Any]], n: int = 15) -> list[dict[str, Any]]:
        out = []
        for r in rows[:n]:
            out.append({k: r[k] for k in (
                "po_docnum", "po_entry", "line_num", "item_code", "supplier", "po_date",
                "uom", "purchased_base", "received_base", "gap_base", "n_receipts",
                "warehouses_received", "status", "line_status", "lead_days_first_receipt")})
        return out

    by_gap = sorted(
        [r for r in results if r["gap_base"] is not None and Decimal(r["gap_base"]) < 0
         and r["status"] in ("PARTIAL_RECEIPT", "MULTI_RECEIPT_PARTIAL")],
        key=lambda r: Decimal(r["gap_base"]))
    by_no_receipt_gap = sorted(
        [r for r in results if r["status"] == "NO_RECEIPT"],
        key=lambda r: -(Decimal(r["purchased_base"]) if r["purchased_base"] else Decimal("0")))
    by_over = sorted(
        [r for r in results if r["gap_base"] is not None and Decimal(r["gap_base"]) > 0],
        key=lambda r: -Decimal(r["gap_base"]))
    no_receipt = by_no_receipt_gap
    no_receipt_open = sum(1 for r in results
                          if r["status"] == "NO_RECEIPT" and r["line_status"] == "O")
    no_receipt_closed = sum(1 for r in results
                            if r["status"] == "NO_RECEIPT" and r["line_status"] == "C")

    lead_days = [r["lead_days_first_receipt"] for r in results
                 if r["lead_days_first_receipt"] is not None]
    lead_days_sorted = sorted(lead_days)

    def pct(p: float) -> float | None:
        if not lead_days_sorted:
            return None
        idx = min(len(lead_days_sorted) - 1, int(round(p * (len(lead_days_sorted) - 1))))
        return lead_days_sorted[idx]

    # anti-false-positive: aggregate totals vs documental anomalies
    aggregate_purchased = total_purchased
    aggregate_received = total_received
    anomaly_no_receipt = class_stats["NO_RECEIPT"]["lines"]
    anomaly_over = class_stats["OVER_RECEIPT"]["lines"]

    reconciled_purchased = sum(
        (Decimal(r["purchased_base"]) for r in results
         if r["status"] in ("EXACT_RECEIPT", "MULTI_RECEIPT_COMPLETE")
         and r["purchased_base"] is not None), Decimal("0"))
    reconciled_received = sum(
        (Decimal(r["received_base"]) for r in results
         if r["status"] in ("EXACT_RECEIPT", "MULTI_RECEIPT_COMPLETE")
         and r["received_base"] is not None), Decimal("0"))

    no_receipt_by_month: dict[str, int] = defaultdict(int)
    for r in results:
        if r["status"] == "NO_RECEIPT" and r["po_date"]:
            no_receipt_by_month[r["po_date"][:7]] += 1

    late_receipts = sorted(
        [r for r in results if r["lead_days_first_receipt"] is not None
         and r["lead_days_first_receipt"] > 30],
        key=lambda r: -r["lead_days_first_receipt"])

    return {
        "universe": {
            "po_documents_total": len(data["po_headers"]),
            "po_documents_cancelled": sum(1 for h in data["po_headers"].values()
                                          if h["canceled"] in CANCELLED_VALUES),
            "po_documents_valid": sum(1 for h in data["po_headers"].values()
                                      if h["canceled"] not in CANCELLED_VALUES),
            "po_lines_total": len(po_lines),
            "po_lines_cancelled_docs": cancelled_po_lines,
            "po_lines_non_inventory": len(non_inventory_lines),
            "po_lines_main_universe": total_main,
            "receipt_documents_total": len(data["receipt_headers"]),
            "receipt_documents_cancelled": sum(1 for h in data["receipt_headers"].values()
                                               if h["canceled"] in CANCELLED_VALUES),
            "receipt_documents_valid": sum(1 for h in data["receipt_headers"].values()
                                           if h["canceled"] not in CANCELLED_VALUES),
            "receipt_lines_total": len(receipt_lines),
            "receipt_lines_cancelled": canceled_receipt_lines,
            "receipt_lines_valid": len(receipt_lines) - canceled_receipt_lines,
            "receipt_lines_linked_to_po": sum(len(v) for v in links.values()),
            "receipt_lines_unresolved_valid": unresolved_valid_receipt_lines,
            "receipt_lines_unresolved_by_path": dict(path_stats),
            "receipt_lines_resolved_po_out_of_extract": resolved_po_missing,
            "invoice_documents_total": len(data["invoice_headers"]),
            "invoice_lines_total": len(invoice_lines),
            "invoice_window": [
                str(min(h["docdate"] for h in data["invoice_headers"].values() if h["docdate"])),
                str(max(h["docdate"] for h in data["invoice_headers"].values() if h["docdate"])),
            ],
            "po_window": [
                str(min(h["docdate"] for h in data["po_headers"].values() if h["docdate"])),
                str(max(h["docdate"] for h in data["po_headers"].values() if h["docdate"])),
            ],
            "receipt_window": [
                str(min(h["docdate"] for h in data["receipt_headers"].values() if h["docdate"])),
                str(max(h["docdate"] for h in data["receipt_headers"].values() if h["docdate"])),
            ],
            "products_reference": len(data["products"]),
            "warehouses_reference": len(data["warehouses"]),
            "suppliers_reference": len(data["suppliers"]),
            "suppliers_in_purchases": len({r["supplier"] for r in results if r["supplier"]}),
        },
        "class_stats": {
            c: {"lines": v["lines"],
                "purchased_base": str(v["purchased_base"]),
                "received_base": str(v["received_base"]),
                "comparable_lines": v["comparable_lines"]}
            for c, v in class_stats.items()
        },
        "totals": {
            "main_universe_lines": total_main,
            "purchased_base_total": str(total_purchased),
            "received_base_total": str(total_received),
            "delta_base_total": str(total_received - total_purchased),
            "uom_compatible_lines": uom_compatible_lines,
            "uom_incompatible_lines": uom_incompatible_lines,
            "fully_reconciled_lines": fully_reconciled,
            "fully_reconciled_pct": round(100.0 * fully_reconciled / total_main, 2) if total_main else None,
            "multi_receipt_lines": multi_receipt_lines,
            "multi_warehouse_lines": multi_warehouse_lines,
            "no_receipt_open_lines": no_receipt_open,
            "no_receipt_closed_lines": no_receipt_closed,
            "lead_days_p50": pct(0.5), "lead_days_p90": pct(0.9), "lead_days_max": pct(1.0),
        },
        "controls": {
            "link_paths": dict(path_stats),
            "item_match_links": sum(len(v) for v in links.values()) - item_mismatch,
            "item_mismatch_links": item_mismatch,
            "uom_incompatible_pairs": uom_incompatible_pairs,
            "fanout_violations_receipt_line_to_multi_po": fanout_violations,
            "movement_controls": movement_controls,
            "receipts_docs_without_movement": sorted(receipts_without_movement)[:50],
            "receipts_docs_without_movement_count": len(receipts_without_movement),
            "cancelled_receipt_lines_excluded": canceled_receipt_lines,
            "aggregate_vs_documental": {
                "aggregate_purchased_base": str(aggregate_purchased),
                "aggregate_received_base": str(aggregate_received),
                "aggregate_delta_base": str(aggregate_received - aggregate_purchased),
                "lines_no_receipt": anomaly_no_receipt,
                "lines_over_receipt": anomaly_over,
                "reconciled_subset_purchased_base": str(reconciled_purchased),
                "reconciled_subset_received_base": str(reconciled_received),
                "reconciled_subset_delta_base": str(reconciled_received - reconciled_purchased),
                "line_level_anomalies_total": sum(
                    class_stats[c]["lines"] for c in
                    ("PARTIAL_RECEIPT", "MULTI_RECEIPT_PARTIAL", "OVER_RECEIPT", "NO_RECEIPT")),
            },
            "unresolved_receipt_samples": unresolved_samples,
        },
        "warehouse_rows": warehouse_rows,
        "uom_rows": uom_rows,
        "invoice_view": inv_view,
        "exceptions": {
            "no_receipt_top": top(no_receipt),
            "no_receipt_by_month": dict(sorted(no_receipt_by_month.items())),
            "partial_top": top(by_gap),
            "over_top": top(by_over),
            "late_receipts_over_30_days": top(late_receipts, 15),
            "multi_warehouse_sample": top([r for r in results if r["multi_warehouse"]], 10),
            "multi_receipt_sample": top([r for r in results if r["n_receipts"] > 1], 10),
        },
        "non_inventory_lines": non_inventory_lines[:50],
        "non_inventory_count": len(non_inventory_lines),
        "results": results,
    }


def _invoice_receipt_view(data: dict[str, Any], resolver: Resolver) -> dict[str, Any]:
    """Secondary transactional reconciliation: AP invoice line -> receipt line
    through the explicit BaseType=18 base/target link (receipt based on the
    invoice line), restricted to non-cancelled invoices."""
    invoice_lines = data["invoice_lines"]
    receipt_lines = data["receipt_lines"]
    by_invoice: dict[tuple[str, str], list[ReceiptLine]] = defaultdict(list)
    for rl in receipt_lines.values():
        if rl.canceled in CANCELLED_VALUES:
            continue
        if rl.base_type == "18" and rl.base_entry and rl.base_line:
            by_invoice[(rl.base_entry, rl.base_line)].append(rl)

    stats = {"invoice_lines_total": len(invoice_lines),
             "invoice_lines_cancelled": 0,
             "invoice_lines_po_based": 0,
             "invoice_lines_direct": 0,
             "invoice_lines_with_receipt": 0,
             "invoice_lines_without_receipt": 0,
             "invoice_lines_comparable": 0,
             "exact": 0, "partial": 0, "over": 0, "none": 0}
    gaps: list[Decimal] = []
    for key, inv in invoice_lines.items():
        if inv["canceled"] in CANCELLED_VALUES:
            stats["invoice_lines_cancelled"] += 1
            continue
        bt = inv.get("base_type")
        if bt == "22":
            stats["invoice_lines_po_based"] += 1
        elif bt == "-1":
            stats["invoice_lines_direct"] += 1
        paired = by_invoice.get(key, [])
        if not paired:
            stats["invoice_lines_without_receipt"] += 1
            continue
        stats["invoice_lines_with_receipt"] += 1
        inv_base = _base_qty(inv["quantity"], inv["num_per_msr"])
        rec_base = Decimal("0")
        ok = True
        for rl in paired:
            if inv["item_code"] and rl.item_code and inv["item_code"] != rl.item_code:
                ok = False
            if (inv["unit_msr"] is not None and rl.unit_msr is not None
                    and inv["unit_msr"] != rl.unit_msr):
                ok = False
            b = _base_qty(rl.quantity, rl.num_per_msr)
            if b is None:
                ok = False
            else:
                rec_base += b
        if not ok or inv_base is None:
            continue
        stats["invoice_lines_comparable"] += 1
        gaps.append(rec_base - inv_base)
        if rec_base == inv_base:
            stats["exact"] += 1
        elif rec_base < inv_base:
            stats["partial"] += 1
        else:
            stats["over"] += 1
    stats["positive_gaps"] = sum(1 for g in gaps if g > 0)
    stats["negative_gaps"] = sum(1 for g in gaps if g < 0)

    # timing: invoice date -> receipt date for invoice-linked receipts
    deltas: list[int] = []
    for key, inv in invoice_lines.items():
        if inv["canceled"] in CANCELLED_VALUES:
            continue
        paired = by_invoice.get(key, [])
        if not paired or not inv.get("doc_date"):
            continue
        rd = min((rl.doc_date for rl in paired if rl.doc_date), default=None)
        if rd is not None:
            deltas.append((rd - inv["doc_date"]).days)
    deltas.sort()
    if deltas:
        stats["invoice_to_receipt_days"] = {
            "n": len(deltas),
            "min": deltas[0],
            "p50": deltas[len(deltas) // 2],
            "max": deltas[-1],
            "same_day": sum(1 for d in deltas if d == 0),
            "receipt_before_invoice": sum(1 for d in deltas if d < 0),
            "receipt_after_invoice": sum(1 for d in deltas if d > 0),
        }
    return stats