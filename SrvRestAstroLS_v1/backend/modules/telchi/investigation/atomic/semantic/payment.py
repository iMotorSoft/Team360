"""Pure semantic logic: payment, cancellation, matching, valuation, reconciliation.

All functions are storage-independent and unit-testable without a DB.
Only classify from CONFIRMED SAP evidence.
"""

# ---- Payment method (T04 / §18) ---------------------------------------------------------
CASH = "CASH"
CHECK = "CHECK"
TRANSFER = "TRANSFER"
CARD = "CARD"
ON_ACCOUNT = "ON_ACCOUNT"
BILL_EXCHANGE = "BILL_EXCHANGE"
MIXED = "MIXED"
OTHER = "OTHER"
UNKNOWN = "UNKNOWN"

# field -> instrument (ORCT header cash-sum fields, confirmed)
_ORCT_INSTRUMENT = [
    ("CashSum", CASH),
    ("CheckSum", CHECK),
    ("TrsfrSum", TRANSFER),
    ("CreditSum", CARD),
    ("NoDocSum", ON_ACCOUNT),
    ("BoeSum", BILL_EXCHANGE),
]


def classify_payment_method(sums: dict) -> str:
    """Classify a payment's instruments from header sum fields (T04).

    sums: {field: amount}; a missing field counts as 0.
    MIXED when >1 instrument present; OTHER when none recognized.
    """
    instruments = []
    for field, label in _ORCT_INSTRUMENT:
        amt = sums.get(field, 0) or 0
        if amt > 0:
            instruments.append(label)
    if len(instruments) > 1:
        return MIXED
    if len(instruments) == 1:
        return instruments[0]
    return OTHER


# ---- Cancellation state (T15 / §14: CANCELED N/Y/C) ---------------------------
def cancellation_state(raw) -> str:
    """Map minimal SAP CANCELED raw value to semantic class."""
    if raw is None:
        return "UNKNOWN"
    raw = str(raw).strip().upper()
    if raw == "N":
        return "VALID"
    if raw == "Y":
        return "CANCELED_ORIGINAL"
    if raw == "C":
        return "CANCELED_REVERSAL"
    return "UNKNOWN"


# ---- Match method assignment (§12: choose_match_method) -----------------------
def choose_match_method(reference_kind: str, exact_candidate: str) -> str:
    """Assign match_method. Never present INFERRED as DIRECT_REFERENCE."""
    known = {
        "SAP_BASEENTRY", "EXTERNAL_ID", "FOLIO", "INTEGRATION_ID",
        "EXACT_DOCUMENT_ID", "BATCH_REFERENCE", "AMOUNT_TIME_MATCH",
        "ITEM_QUANTITY_MATCH", "MANUAL_CONFIRMED",
    }
    if exact_candidate in known:
        return exact_candidate
    return "INFERRED"


# ---- Valuation (§16) --------------------------------------------------------
def sale_value(quantity: float, effective_sale_price: float) -> float:
    return round(float(quantity) * float(effective_sale_price), 4)


def cost_value(quantity: float, unit_cost: float) -> float:
    return round(float(quantity) * float(unit_cost), 4)


# ---- Cash vs goods reconciliation (§19-22, §52) ------------------------------
CONSISTENT = "SALE_CASH_STOCK_CONSISTENT"
CASH_MISSING = "CASH_MISSING"
STOCK_LINK_MISSING = "STOCK_LINK_MISSING"
SALE_DOCUMENT_MISSING = "SALE_DOCUMENT_MISSING"
HIGH_PRIORITY_REVIEW = "HIGH_PRIORITY_REVIEW"
REVIEW_REQUIRED = "REVIEW_REQUIRED"


def reconcile_expected_cash(expected_cash: float, actual_cash: float, tolerance: float = 0.01) -> dict:
    diff = round(expected_cash - actual_cash, 4)
    unexplained = diff
    if abs(diff) <= tolerance:
        unexplained = 0.0
    return {
        "expected_cash": round(expected_cash, 4),
        "actual_cash": round(actual_cash, 4),
        "difference": diff,
        "explained": 0.0,
        "unexplained": unexplained,
        "status": CONSISTENT if unexplained == 0 else REVIEW_REQUIRED,
    }


# ---- Production capacity (§21/23, T18/T19/T20) --------------------------------
def max_producible(available_by_component: dict[str, float],
                   required_per_unit: dict[str, float]) -> dict:
    """MAX_PRODUCIBLE = MIN(available / required); identifies bottleneck."""
    if not required_per_unit:
        return {"max": None, "bottleneck": None, "component_missing": []}
    possible = {}
    zero_comps = []
    for comp, req in required_per_unit.items():
        if req <= 0:
            continue
        avail = available_by_component.get(comp, 0.0) or 0.0
        if avail <= 0:
            possible[comp] = 0.0
            zero_comps.append(comp)
            continue
        possible[comp] = float(avail) / float(req)
    if not possible:
        comps = sorted(required_per_unit)
        return {"max": 0.0, "bottleneck": comps[0], "component_missing": [comps[0]]}
    bottleneck = min(possible, key=possible.get)
    return {
        "max": possible[bottleneck],
        "bottleneck": bottleneck,
        "component_missing": sorted(set(zero_comps)),
        "zero_components": sorted(zero_comps),
    }


def coverage_days(finished_available: float, demand_rate_per_day: float) -> float | None:
    if not finished_available or finished_available <= 0:
        return 0.0
    if not demand_rate_per_day or demand_rate_per_day <= 0:
        return None
    return round(finished_available / demand_rate_per_day, 2)
