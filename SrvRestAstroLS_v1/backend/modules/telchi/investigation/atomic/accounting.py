"""H4 CASH ACCOUNTING TRACEABILITY — pure semantics.

Chain proven on HANA (2023-02, read-only):
  SALE -> RECONCILIATION (ITR1 N:N) -> ORCT --TransId--> OJDT (1:1)
       -> JDT1[Account = ORCT.CashAcct] (Debit) -> OACT

Key audited facts (CONFIRMED on real data):
  * ORCT.TransId = OJDT.TransId joins 100% (29,319/29,319 Feb 2023); unique.
  * Cash entry = DEBIT on ORCT.CashAcct; customer credit is ContraAct side.
  * Mixed payments decompose exactly (cash line + transfer/check/card lines).
  * OACT.CashBox = 'N' even for real cash accounts ("Cajas ...") -> the flag
    does NOT mark physical cashboxes in Telchi; account family/naming does.
  * BPLId absent from journal lines and accounts -> branch linkage via account
    naming is HEURISTIC only.
"""
from __future__ import annotations

from modules.telchi.investigation.atomic.semantic.payment import (
    CASH, CHECK, TRANSFER, CARD, MIXED, OTHER, UNKNOWN,
    cancellation_state, classify_payment_method,
)

# ---- H4 status taxonomy (§14) -------------------------------------------------
CASH_ACCOUNTING_CONFIRMED = "CASH_ACCOUNTING_CONFIRMED"
CASH_PARTIALLY_CONFIRMED = "CASH_PARTIALLY_CONFIRMED"
CASH_JOURNAL_MISSING = "CASH_JOURNAL_MISSING"
CASH_ACCOUNT_MISMATCH = "CASH_ACCOUNT_MISMATCH"
CASH_AMOUNT_MISMATCH = "CASH_AMOUNT_MISMATCH"
CASH_NOT_CASHBOX = "CASH_NOT_CASHBOX"
CASH_ACCOUNT_UNRESOLVED = "CASH_ACCOUNT_UNRESOLVED"
CASH_CANCELED = "CASH_CANCELED"
CASH_MIXED_PAYMENT = "CASH_MIXED_PAYMENT"
NOT_APPLICABLE_TO_PHYSICAL_CASH = "NOT_APPLICABLE_TO_PHYSICAL_CASH"
REVIEW = "REVIEW"

DEFAULT_TOLERANCE = 0.01


def match_cash_journal_lines(journal_lines: list[dict],
                             expected_account) -> list[dict]:
    """Cash journal lines = JDT1 rows whose Account equals ORCT.CashAcct.

    Evidence-based (account identity), never line position or Line_ID.
    Preserves raw debit/credit and signed amount.
    """
    out = []
    for ln in journal_lines or []:
        if str(ln.get("Account")) == str(expected_account):
            raw_debit = float(ln.get("Debit") or 0)
            raw_credit = float(ln.get("Credit") or 0)
            out.append({
                "line_id": ln.get("Line_ID"),
                "account": ln.get("Account"),
                "raw_debit": raw_debit,
                "raw_credit": raw_credit,
                "signed_amount": round(raw_debit - raw_credit, 4),
                "contra_act": ln.get("ContraAct"),
                "line_memo": ln.get("LineMemo"),
                "bpl_id": ln.get("BPLId"),
            })
    return out


def evaluate_cash_accounting(payment: dict, journal_trans_id,
                             journal_lines: list[dict],
                             account_master: dict | None = None,
                             tolerance: float = DEFAULT_TOLERANCE) -> dict:
    """Build the H4 accounting trace for one ORCT payment.

    payment: physical ORCT columns (DocEntry, DocNum, TransId, Canceled,
             CashSum, CashAcct, DocCurr...).
    journal_lines: ALL JDT1 lines of the linked OJDT transaction (1:N).
    account_master: {AcctCode: {AcctName, CashBox, Postable}} subset.
    """
    canceled = cancellation_state(payment.get("Canceled"))
    # display breakdown (lowercase); classification uses the RAW physical row
    # because classify_payment_method reads SAP column names (DEC-022)
    instruments = {
        "cash": float(payment.get("CashSum") or 0),
        "check": float(payment.get("CheckSum") or 0),
        "transfer": float(payment.get("TrsfrSum") or 0),
        "card": float(payment.get("CreditSum") or 0),
    }
    method = classify_payment_method(payment)
    expected_account = payment.get("CashAcct")
    result = {
        "payment_docentry": payment.get("DocEntry"),
        "payment_docnum": payment.get("DocNum"),
        "trans_id": payment.get("TransId"),
        "journal_trans_id": journal_trans_id if journal_trans_id else None,
        "currency": payment.get("DocCurr"),
        "instruments": instruments,
        "payment_method": method,
        "canceled": canceled,
        "cash_account_expected": expected_account,
        "cash_account_actual": [],
        "journal_cash_amount": None,
        "amount_delta": None,
        "status": None,
        "explanation": [],
        "lineage": {
            "ORCT.DocEntry": payment.get("DocEntry"),
            "OJDT.TransId": journal_trans_id,
            "JDT1.lines": [ln.get("Line_ID") for ln in (journal_lines or [])],
        },
    }

    if canceled != "VALID":
        result["status"] = CASH_CANCELED
        result["explanation"].append("PAYMENT_CANCELED_REVERSAL_TRACEABLE")
        return result

    if not instruments["cash"] > 0:
        result["status"] = NOT_APPLICABLE_TO_PHYSICAL_CASH
        result["explanation"].append(f"METHOD={method}")
        return result

    # journal linkage
    if not journal_trans_id:
        result["status"] = CASH_JOURNAL_MISSING
        result["explanation"].append("NO_OJDT_FOR_TRANSID")
        return result

    cash_lines = match_cash_journal_lines(journal_lines, expected_account)
    result["cash_account_actual"] = [
        {"account": cl["account"], "line_id": cl["line_id"],
         "raw_debit": cl["raw_debit"], "raw_credit": cl["raw_credit"],
         "signed_amount": cl["signed_amount"]}
        for cl in cash_lines
    ]
    if not cash_lines:
        # no line hit the expected account: look at what WAS debited
        result["status"] = CASH_ACCOUNT_MISMATCH
        others = sorted({str(ln.get("Account")) for ln in (journal_lines or [])})
        result["explanation"].append(f"EXPECTED_{expected_account}_ABSENT")
        result["explanation"].append(f"ACCOUNTS_PRESENT={others[:6]}")
        return result

    journal_cash = round(sum(cl["signed_amount"] for cl in cash_lines), 4)
    delta = round(journal_cash - float(payment.get("CashSum") or 0), 4)
    result["journal_cash_amount"] = journal_cash
    result["amount_delta"] = delta

    if abs(delta) <= tolerance:
        result["status"] = CASH_ACCOUNTING_CONFIRMED
        result["explanation"].append("AMOUNT_EXACT")
    else:
        result["status"] = CASH_AMOUNT_MISMATCH
        result["explanation"].append(f"DELTA={delta}")

    # CashBox semantics audit (flag proved unreliable in Telchi)
    master = (account_master or {}).get(str(expected_account)) or {}
    result["acct_name"] = master.get("AcctName")
    result["cashbox_flag"] = master.get("CashBox")
    if master and str(master.get("CashBox")).upper() != "Y":
        result["explanation"].append("OACT_CASHBOX_FLAG_N")
    if len(result["cash_account_actual"]) > 1:
        result["explanation"].append("MULTIPLE_CASH_LINES_SAME_ACCOUNT")
    if method == MIXED:
        result["explanation"].append("MIXED_PAYMENT_DECOMPOSED")
    return result


# ---- branch linkage (HEURISTIC by rule §17: never CONFIRMED) -------------------
_BRANCH_NAME_TOKENS = (
    ("CASA MATRIZ", "casa_matriz"),
    ("2DO. ANILLO", "segundo_anillo"),
    ("VILLA", "villa"),
    ("ROCA CORONADO", "roca_coronado"),
    ("LA PAZ", "la_paz"),
    ("LABORATORIO", "laboratorio"),
)


def branch_from_account_name(acct_name) -> tuple[str | None, str]:
    """HEURISTIC branch inference from cash account naming.

    Returns (branch_token, confidence_class); confidence is always HEURISTIC
    because it parses names (rule §17/§46: never present as fact).
    """
    if not acct_name:
        return None, "UNRESOLVED"
    name = str(acct_name).upper()
    for token, branch in _BRANCH_NAME_TOKENS:
        if token in name:
            return branch, "HEURISTIC"
    if "DISTRIBUIDOR PLACA" in name:
        # 'Distribuidor Placa 4702-GIP MN' carries a warehouse-like plate code
        parts = name.split()
        try:
            idx = parts.index("PLACA")
            code = parts[idx + 1]
            return f"placa_{code.lower()}", "HEURISTIC"
        except (ValueError, IndexError):
            return None, "UNRESOLVED"
    return None, "UNRESOLVED"


def build_cash_accounting_trace(payment: dict, journal_lines: list[dict],
                                account_master: dict | None = None,
                                tolerance: float = DEFAULT_TOLERANCE) -> dict:
    """Full H4 trace incl. HEURISTIC branch token (clearly separated)."""
    tr = evaluate_cash_accounting(payment, payment.get("TransId"),
                                  journal_lines, account_master, tolerance)
    master = (account_master or {}).get(str(tr["cash_account_expected"])) or {}
    branch, cls = branch_from_account_name(master.get("AcctName"))
    tr["branch_heuristic"] = branch
    tr["branch_confidence"] = cls if branch else "UNRESOLVED"
    return tr