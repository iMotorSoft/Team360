"""Material stock position domain (pure logic, READ ONLY contracts).

Semantics discovered against real SAP HANA (2026-08-27) - TELCHI:

Stock (OITW):
  OnHand   = physical stock, net of all movements. EXACT vs OINM ledger:
             OITW.OnHand == SUM(OINM.InQty) - SUM(OINM.OutQty) over the full
             OINM window. 0 negative; 32 locked rows.
  IsCommited = committed to open sales/delivery (not physically available).
  OnOrder  = on open purchase orders (ordered, not received) -> separate
             layer, never summed into physical stock.
  Consig   = consignment (anomaly: negative total).
  AVAILABLE_PHYSICAL_STOCK = OnHand - IsCommited.

Warehouse function: resolved via name + U_TYPE (SAP/DMS) + U_TIPO
(01=import / 03=regular) + Inactive. 82 warehouses; explicit mapping below,
with keyword fallback; any unresolved role -> WAREHOUSE_ROLE_UNRESOLVED.

Item classification: group name (OITB) + production membership (OWOR) +
BOM membership (ITT1) + flags (Invnt/Sell/Prchse) + item name (packaging
regex). OITB.ItemClass / RawMtrl are NOT discriminating (all '2'/'N').
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

# ---------------------------------------------------------------------------
# Warehouse role taxonomy (82 warehouses)
# ---------------------------------------------------------------------------

ROLE_RAW_MATERIAL = "RAW_MATERIAL"
ROLE_PACKAGING = "PACKAGING"
ROLE_PRODUCTION = "PRODUCTION"
ROLE_FINISHED_GOOD = "FINISHED_GOOD"
ROLE_BRANCH = "BRANCH"
ROLE_DISPENSING = "DISPENSING"
ROLE_DISTRIBUTION = "DISTRIBUTION"
ROLE_TRANSIT = "TRANSIT"
ROLE_IMPORT = "IMPORT"
ROLE_MOBILE = "MOBILE"
ROLE_QUARANTINE = "QUARANTINE"
ROLE_DAMAGED = "DAMAGED"
ROLE_EXPIRED = "EXPIRED"
ROLE_CONSIGNMENT = "CONSIGNMENT"
ROLE_RETURNS = "RETURNS"
ROLE_OTHER = "OTHER"
ROLE_UNRESOLVED = "WAREHOUSE_ROLE_UNRESOLVED"

# Canonical mapping (name evidence + U_TYPE + U_TIPO). Single source of truth.
WAREHOUSE_ROLES: dict[str, str] = {
    "01": ROLE_TRANSIT,
    "2A-AMD": ROLE_DISPENSING,
    "2A-AMK": ROLE_BRANCH,
    "2A-DAN": ROLE_DAMAGED,
    "2A-DEV": ROLE_RETURNS,
    "2A-EXT": ROLE_DAMAGED,
    "2A-KIT": ROLE_PRODUCTION,
    "2A-MAG": ROLE_DISPENSING,
    "2A-MEI": ROLE_OTHER,
    "2A-MKT": ROLE_OTHER,
    "2A-SAL": ROLE_BRANCH,
    "2A-SMK": ROLE_BRANCH,
    "2A-TRAN": ROLE_TRANSIT,
    "ALM-CON": ROLE_OTHER,
    "ALM-IMP": ROLE_IMPORT,
    "BE-DT1": ROLE_DISTRIBUTION,
    "CBBA-DT1": ROLE_DISTRIBUTION,
    "CHQ-DT1": ROLE_DISTRIBUTION,
    "CM-AMD": ROLE_DISPENSING,
    "CM-DAN": ROLE_DAMAGED,
    "CM-SAL": ROLE_BRANCH,
    "DMS-DEV": ROLE_RETURNS,
    "DMS-PROF": ROLE_OTHER,
    "DV-SAL": ROLE_BRANCH,
    "LAB-A1": ROLE_OTHER,
    "LAB-C1": ROLE_QUARANTINE,
    "LAB-D0": ROLE_MOBILE,
    "LAB-D1": ROLE_MOBILE,
    "LAB-D2": ROLE_MOBILE,
    "LAB-D3": ROLE_MOBILE,
    "LAB-D4": ROLE_MOBILE,
    "LAB-D5": ROLE_MOBILE,
    "LAB-D6": ROLE_MOBILE,
    "LAB-D7": ROLE_MOBILE,
    "LAB-D8": ROLE_MOBILE,
    "LAB-D9": ROLE_MOBILE,
    "LAB-D10": ROLE_MOBILE,
    "LAB-D11": ROLE_MOBILE,
    "LAB-D12": ROLE_MOBILE,
    "LAB-DAN": ROLE_DAMAGED,
    "LAB-DES": ROLE_MOBILE,
    "LAB-IMP": ROLE_IMPORT,
    "LAB-M1": ROLE_RAW_MATERIAL,
    "LAB-P1": ROLE_PRODUCTION,
    "LAB-P2": ROLE_PRODUCTION,
    "LAB-P3": ROLE_PRODUCTION,
    "LAB-P4": ROLE_PRODUCTION,
    "LAB-P5": ROLE_QUARANTINE,
    "LAB-T1": ROLE_FINISHED_GOOD,
    "LAB-T2": ROLE_FINISHED_GOOD,
    "LAB-T3": ROLE_FINISHED_GOOD,
    "LAB-T4": ROLE_FINISHED_GOOD,
    "LAB-T5": ROLE_CONSIGNMENT,
    "LAB-T6": ROLE_RETURNS,
    "LAB-T7": ROLE_DAMAGED,
    "LAB-T8": ROLE_EXPIRED,
    "LAB-TRAN": ROLE_TRANSIT,
    "LAB-VMP": ROLE_OTHER,
    "LPZ-D1": ROLE_MOBILE,
    "LPZ-D2": ROLE_MOBILE,
    "LPZ-DAN": ROLE_DAMAGED,
    "LPZ-DT1": ROLE_DISTRIBUTION,
    "LPZ-T1": ROLE_FINISHED_GOOD,
    "MAG-M1": ROLE_RAW_MATERIAL,
    "MAG-P1": ROLE_PRODUCTION,
    "MAG-T1": ROLE_FINISHED_GOOD,
    "NTG-T1": ROLE_FINISHED_GOOD,
    "OR-DT1": ROLE_DISTRIBUTION,
    "PO-DT1": ROLE_DISTRIBUTION,
    "RC-SAL": ROLE_BRANCH,
    "SAA-DAN": ROLE_DAMAGED,
    "SAA-M1": ROLE_RAW_MATERIAL,
    "SAA-P1": ROLE_PRODUCTION,
    "SAA-T1": ROLE_FINISHED_GOOD,
    "SAA-T2": ROLE_PRODUCTION,
    "SAA-T3": ROLE_PRODUCTION,
    "SAL-TRS": ROLE_TRANSIT,
    "SAP-R1": ROLE_TRANSIT,
    "SCZ-DT1": ROLE_DISTRIBUTION,
    "TJ-DT1": ROLE_DISTRIBUTION,
    "UR-SAL": ROLE_BRANCH,
    "VI-SAL": ROLE_BRANCH,
}

# Keyword fallback for robustness (applied only when explicit map misses).
_WAREHOUSE_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("IMPORTACION", ROLE_IMPORT),
    ("MATERIA PRIMA", ROLE_RAW_MATERIAL),
    ("GRANEL", ROLE_RAW_MATERIAL),
    ("PROCESO", ROLE_PRODUCTION),
    ("ETIQUETADO", ROLE_PRODUCTION),
    ("REACONDICIONADO", ROLE_PRODUCTION),
    ("TERMINADO", ROLE_FINISHED_GOOD),
    ("CONSIGNACION", ROLE_CONSIGNMENT),
    ("TRANSIT", ROLE_TRANSIT),
    ("TRANSITORIO", ROLE_TRANSIT),
    ("SALON", ROLE_BRANCH),
    ("MEDICAMENTOS", ROLE_DISPENSING),
    ("MAGISTRAL", ROLE_DISPENSING),
    ("DISTRIBUCION", ROLE_DISTRIBUTION),
    ("MOVIL", ROLE_MOBILE),
    ("CONTROL DE CALIDAD", ROLE_QUARANTINE),
    ("RETENCION", ROLE_QUARANTINE),
    ("DANADOS", ROLE_DAMAGED),
    ("DAÑADOS", ROLE_DAMAGED),
    ("VENCIDOS", ROLE_EXPIRED),
    ("DEVOLUCIONES", ROLE_RETURNS),
    ("ENTREGAS PARCIALES", ROLE_RETURNS),
)


def resolve_warehouse_role(whs_code: str, whs_name: str, u_type: str | None,
                           u_tipo: str | None, inactive: str | None) -> str:
    """Resolve warehouse function. Explicit map first, keyword fallback,
    else UNRESOLVED."""
    if whs_code in WAREHOUSE_ROLES:
        return WAREHOUSE_ROLES[whs_code]
    name = (whs_name or "").upper()
    for kw, role in _WAREHOUSE_KEYWORDS:
        if kw in name:
            return role
    if u_type and u_type.upper() == "DMS":
        return ROLE_MOBILE
    if u_tipo == "01":
        return ROLE_IMPORT
    return ROLE_UNRESOLVED


# ---------------------------------------------------------------------------
# Item classification
# ---------------------------------------------------------------------------

ITEM_FINISHED_GOOD = "FINISHED_GOOD"
ITEM_SEMI_FINISHED = "SEMI_FINISHED"
ITEM_PACKAGING = "PACKAGING"
ITEM_RAW_MATERIAL = "RAW_MATERIAL"
ITEM_INPUT = "INPUT"
ITEM_TRADED_GOOD = "TRADED_GOOD"
ITEM_SERVICE = "SERVICE"
ITEM_OTHER = "OTHER"
ITEM_UNRESOLVED = "ITEM_CLASS_UNRESOLVED"

# Groups of interest (OITB.ItmsGrpCod -> name)
GROUP_SERVICIOS = 141
GROUP_ACTIVO_FIJO = 144
GROUP_INSUMO = 129
GROUP_MAT_ACONDICIONADO = 130
GROUP_MAT_LAB = 131
GROUP_MAT_VIDRIO = 117
GROUP_REACTIVO = 133
GROUP_IMPORTACION = 119
FRACCIONADO_GROUPS = {125, 126, 127, 128}

PACKAGING_RE = re.compile(
    r"FRASCO|TAPA|ETIQUETA|CAJA|ENVASE|BOLSA|CAPSULA|BLISTER|SACHET|POTE|"
    r"GOTERO|SPRAY|CONTRA|BOBINA|AMPOLLA|CASCO|BIDON|TURRIL|GALON|CINTA|"
    r"BOTELLA|ENVOLTURA|PRECINTO|STICKER|SERIGRAFIA|TAPON|DOSIFICADOR",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ItemFacts:
    itemcode: str
    itemname: str
    item_type: str | None
    itms_grp: int | None
    invnt_item: str | None
    sell_item: str | None
    prchse_item: str | None
    is_produced: bool = False
    is_bom_component: bool = False
    invnt_uom: str | None = None

    @property
    def is_service_like(self) -> bool:
        return self.itms_grp == GROUP_SERVICIOS or (
            self.invnt_item != "Y" and self.sell_item != "Y" and self.prchse_item != "Y")

    @property
    def is_fixed_asset(self) -> bool:
        return self.itms_grp == GROUP_ACTIVO_FIJO or self.item_type == "F"

    @property
    def looks_packaging(self) -> bool:
        return (self.itms_grp == GROUP_MAT_ACONDICIONADO
                or bool(PACKAGING_RE.search(self.itemname or "")))


def classify_item(facts: ItemFacts) -> str:
    """Evidence-based item classification (ordered rules)."""
    if facts.is_fixed_asset:
        return ITEM_OTHER
    if facts.is_service_like:
        return ITEM_SERVICE
    if facts.is_produced:
        return ITEM_FINISHED_GOOD if facts.sell_item == "Y" else ITEM_SEMI_FINISHED
    if facts.is_bom_component:
        if facts.looks_packaging:
            return ITEM_PACKAGING
        return ITEM_RAW_MATERIAL
    if facts.looks_packaging:
        return ITEM_PACKAGING
    if facts.itms_grp in FRACCIONADO_GROUPS:
        return ITEM_RAW_MATERIAL
    if facts.itms_grp in (GROUP_INSUMO, GROUP_MAT_LAB, GROUP_MAT_VIDRIO, GROUP_REACTIVO):
        return ITEM_INPUT
    if facts.sell_item == "Y" and facts.prchse_item == "Y":
        return ITEM_TRADED_GOOD
    if facts.prchse_item == "Y" and facts.invnt_item == "Y":
        return ITEM_INPUT
    if facts.sell_item == "Y":
        return ITEM_TRADED_GOOD
    return ITEM_UNRESOLVED


# ---------------------------------------------------------------------------
# Stock semantics
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class StockPosition:
    itemcode: str
    whscode: str
    onhand: float
    is_committed: float
    on_order: float
    consig: float
    locked: str | None
    uom: str | None

    @property
    def available_physical(self) -> float:
        """SAP B1: available = OnHand - IsCommited (floor at 0 is NOT applied
        here; negative available is a real signal of oversell/commitment)."""
        return self.onhand - self.is_committed


def availability_quality(onhand: float, available: float) -> str:
    if onhand < 0:
        return "NEGATIVE_STOCK"
    if available < 0:
        return "COMMITTED_OVER_STOCK"
    return "OK"


# ---------------------------------------------------------------------------
# Invariants (TEST P0 of the stock domain)
# ---------------------------------------------------------------------------

def invariant_no_negative_onhand(negative_count: int) -> tuple[bool, str]:
    ok = negative_count == 0
    return ok, "ONHAND_NON_NEGATIVE" if ok else "ONHAND_NEGATIVE_FOUND"


def invariant_warehouse_roles_resolved(unresolved: list[str]) -> tuple[bool, str]:
    ok = not unresolved
    return ok, "WAREHOUSE_ROLES_RESOLVED" if ok else "WAREHOUSE_ROLE_UNRESOLVED"


def invariant_no_duplicate_item_whs(dup_count: int) -> tuple[bool, str]:
    ok = dup_count == 0
    return ok, "ITEM_WHS_UNIQUE" if ok else "ITEM_WHS_DUPLICATED"


def invariant_item_whs_integrity(missing_item: int, missing_whs: int) -> tuple[bool, str]:
    ok = missing_item == 0 and missing_whs == 0
    return ok, "ITEM_WHS_INTEGRITY" if ok else "ITEM_WHS_ORPHAN"


def invariant_uom_compatible(uoms: Iterable[str]) -> bool:
    """A position is only summed within a single UOM; never across UOMs.
    This is a guard: empty or single-uom sets are compatible; mixed sets are
    flagged to the caller (returns False)."""
    distinct = {u for u in uoms if u}
    return len(distinct) <= 1


# ---------------------------------------------------------------------------
# Reconciliation
# ---------------------------------------------------------------------------

def reconcile_ledger(onhand: float, in_qty: float | None, out_qty: float | None,
                      tolerance: float = 1e-6) -> tuple[bool, float, str]:
    """OITW.OnHand == SUM(OINM.InQty) - SUM(OINM.OutQty)."""
    computed = float(in_qty or 0.0) - float(out_qty or 0.0)
    diff = float(onhand or 0.0) - computed
    ok = abs(diff) <= tolerance
    return ok, diff, "LEDGER_RECONCILED" if ok else "LEDGER_MISMATCH"