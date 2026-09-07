"""Economic grouping of the 268 explained credit-exception cases.

Consumes the frozen gate evidence:
  validation/credit_exception/evidence/classified_cases.json   (2318 exact)
  validation/credit_control/evidence/phase78_sale_credit_state.json  (287 baseline)

Builds the 268 atomic explained cases (baseline 287 minus UNRESOLVED) and maps
each to a unique primary business group plus the secondary technical reason.

Taxonomy (executive):
  USER_AUTHORIZATION_FULL      <- SAP_FULL_AUTHORIZATION
  CUSTOMER_EXCEPTION           <- CUSTOMER_EXCEPTION_FLAG
  DOCUMENT_FLOW_PREAUTHORIZED  <- DELIVERY_FLOW_EXPLAINS_TIMING (DELIVERY_PREVIOUS)
                               <- ORDER_AUTHORIZED_BEFORE_OVERDUE (ORDER_PREVIOUS)
  NON_CREDIT_RETAIL_CASH       <- PAYMENT_BEFORE_EFFECTIVE_BLOCK_CHECK
  TECHNICAL_RECONCILIATION     <- TECHNICAL_INTEGRATION_PATH
                               <- CREDIT_NOTE_OR_RECONCILIATION

Payment decomposition (validated per-case in the prior gate):
  gross = doctotal
  paid  = paidtodate - credited            (cash settlements incl. same-day POS)
  credited = paidtodate capped by doctotal for cases settled_by_credit_note
  open  = open_now
  invariant: paid + credited + open == gross (tolerance 0.05)

Evidence emitted:
  grouped_cases.json          — 268 atomic rows with group fields
  grouping_report.json        — reconciliation + distributions
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from modules.telchi.investigation.paths import EVIDENCE_ROOT

HERE = Path(__file__).parent
EVIDENCE = EVIDENCE_ROOT / "credit_exception_economic" / "evidence"
TOLERANCE = 0.05

GROUP_OF_REASON = {
    "SAP_FULL_AUTHORIZATION": ("USER_AUTHORIZATION_FULL", "SAP_FULL_AUTHORIZATION"),
    "SUPERUSER_AUTHORIZATION": ("USER_AUTHORIZATION_FULL", "SUPERUSER_AUTHORIZATION"),
    "CUSTOMER_EXCEPTION_FLAG": ("CUSTOMER_EXCEPTION", "CUSTOMER_EXCEPTION_FLAG"),
    "DELIVERY_FLOW_EXPLAINS_TIMING": ("DOCUMENT_FLOW_PREAUTHORIZED", "DELIVERY_PREVIOUS"),
    "ORDER_AUTHORIZED_BEFORE_OVERDUE": ("DOCUMENT_FLOW_PREAUTHORIZED", "ORDER_PREVIOUS"),
    "PAYMENT_BEFORE_EFFECTIVE_BLOCK_CHECK": ("NON_CREDIT_RETAIL_CASH", "PAYMENT_BEFORE_EFFECTIVE_BLOCK_CHECK"),
    "TECHNICAL_INTEGRATION_PATH": ("TECHNICAL_RECONCILIATION", "TECHNICAL_INTEGRATION_PATH"),
    "CREDIT_NOTE_OR_RECONCILIATION": ("TECHNICAL_RECONCILIATION", "CREDIT_NOTE_OR_RECONCILIATION"),
}

GROUP_LABEL = {
    "USER_AUTHORIZATION_FULL": "Usuario FULL",
    "CUSTOMER_EXCEPTION": "Cliente con excepción",
    "DOCUMENT_FLOW_PREAUTHORIZED": "Flujo previo (entrega/pedido)",
    "NON_CREDIT_RETAIL_CASH": "Contado Retail One",
    "TECHNICAL_RECONCILIATION": "Integración / ajuste",
}

SECONDARY_LABEL = {
    "SAP_FULL_AUTHORIZATION": "Autorización FULL SAP",
    "SUPERUSER_AUTHORIZATION": "Autorización superusuario",
    "CUSTOMER_EXCEPTION_FLAG": "Flag U_SO1_01VENCREVENC='Y'",
    "DELIVERY_PREVIOUS": "Entrega previa (DlnLimit=N)",
    "ORDER_PREVIOUS": "Pedido previo sin vencidos",
    "PAYMENT_BEFORE_EFFECTIVE_BLOCK_CHECK": "Contado R1 cubierto el día",
    "TECHNICAL_INTEGRATION_PATH": "Canal técnico DMS",
    "CREDIT_NOTE_OR_RECONCILIATION": "NC / reconciliación",
}

# order used for the report's main table
GROUP_ORDER = [
    "USER_AUTHORIZATION_FULL",
    "CUSTOMER_EXCEPTION",
    "DOCUMENT_FLOW_PREAUTHORIZED",
    "NON_CREDIT_RETAIL_CASH",
    "TECHNICAL_RECONCILIATION",
]

FULL_DISTINCTION = {
    "full_by_superuser": {"soluone"},
    "full_by_technical": {"soluone", "dms", "b1i", "manager", "workflow"},
}


def channel_of(c: dict) -> str:
    if c["origin"] == "SAP" and c["retailone"] == "Y":
        return "RETAIL_ONE"
    if c["origin"] == "DMS":
        return "DMS"
    return "SAP_DIRECT"


def full_by(c: dict) -> str | None:
    """Distinguish FULL authorization origin where demonstrable.

    Full = evidencia de grupo Excel (FULL_BY_GROUP) salvo cuentas técnicas
    (FULL_BY_TECHNICAL, atribución upstream POS). No se clasifica nada como
    superusuario a menos que el caso haya sido resuelto por esa vía.
    """
    if c["classification"] != "SAP_FULL_AUTHORIZATION":
        return None
    if c["sap_user"] in FULL_DISTINCTION["full_by_technical"]:
        return "FULL_BY_TECHNICAL"
    if c.get("superuser") == "Y":
        return "FULL_BY_SUPERUSER"
    return "FULL_BY_GROUP"


def load_268() -> list[dict]:
    classified = json.loads((EVIDENCE_ROOT / "credit_exception" / "evidence" / "classified_cases.json")
                            .read_text(encoding="utf-8"))
    prior = json.loads((EVIDENCE_ROOT / "credit_control" / "evidence" / "phase78_sale_credit_state.json")
                       .read_text(encoding="utf-8"))["all_overdue_sales"]
    prior_keys = {(s["cardcode"], s["docentry"]) for s in prior}
    return [x for x in classified
            if (x["cardcode"], x["doc_entry"]) in prior_keys and x["classification"] != "UNRESOLVED"]


def monetary(c) -> float:
    return float(c or 0.0)


def decorate(c: dict) -> dict:
    primary, secondary = GROUP_OF_REASON[c["classification"]]
    paid_to_date = monetary(c["paidtodate"])
    total = monetary(c["doctotal"])
    credited = min(paid_to_date, total) if c.get("settled_by_credit_note") else 0.0
    paid = paid_to_date - credited
    row = dict(c)
    row.update({
        "primary_business_group": primary,
        "secondary_reason": secondary,
        "secondary_reason_label": SECONDARY_LABEL[secondary],
        "business_group_label": GROUP_LABEL[primary],
        "business_group_order": GROUP_ORDER.index(primary),
        "channel": channel_of(c),
        "full_by": full_by(c),
        "gross_sales_amount": round(total, 2),
        "paid_amount": round(paid, 2),
        "credited_amount": round(credited, 2),
        "open_amount": round(monetary(c["open_now"]), 2),
    })
    return row


def main() -> int:
    ex = load_268()
    rows = [decorate(c) for c in ex]

    # ---- reconciliation -------------------------------------------------
    distinct_entries = {r["doc_entry"] for r in rows}
    group_counts = Counter(r["primary_business_group"] for r in rows)
    secondary_counts = Counter(r["secondary_reason"] for r in rows)
    amount_by_group = defaultdict(float)
    for r in rows:
        amount_by_group[r["primary_business_group"]] += r["gross_sales_amount"]
    total_amount = sum(r["gross_sales_amount"] for r in rows)
    total_paid = sum(r["paid_amount"] for r in rows)
    total_credited = sum(r["credited_amount"] for r in rows)
    total_open = sum(r["open_amount"] for r in rows)

    assert len(rows) == 268, len(rows)
    assert len(distinct_entries) == 268
    assert sum(group_counts.values()) == 268
    assert len(GROUP_ORDER) == len(set(GROUP_ORDER) & set(group_counts))
    assert set(GROUP_ORDER) == set(group_counts)

    # paid+credited+open == gross per-case invariant
    divergences = [r["doc_entry"] for r in rows
                   if abs(r["paid_amount"] + r["credited_amount"] + r["open_amount"] - r["gross_sales_amount"]) > TOLERANCE]
    assert not divergences, divergences[:5]

    report = {
        "input_atomic": 268,
        "grouped_cases": len(rows),
        "distinct_doc_entry": len(distinct_entries),
        "no_double_count": sum(group_counts.values()) == len(rows) == len(distinct_entries),
        "group_case_counts": dict(group_counts),
        "secondary_reason_counts": dict(secondary_counts),
        "amount_by_group": {k: round(v, 2) for k, v in amount_by_group.items()},
        "total_gross_amount": round(total_amount, 2),
        "total_paid_amount": round(total_paid, 2),
        "total_credited_amount": round(total_credited, 2),
        "total_open_amount": round(total_open, 2),
        "amount_reconciliation": {
            "group_sum": round(sum(amount_by_group.values()), 2),
            "atomic_sum": round(total_amount, 2),
            "delta": round(sum(amount_by_group.values()) - total_amount, 6),
        },
        "paid_credited_open_reconciliation": {
            "paid": round(total_paid, 2),
            "credited": round(total_credited, 2),
            "open": round(total_open, 2),
            "sum": round(total_paid + total_credited + total_open, 2),
            "gross": round(total_amount, 2),
            "delta": round(total_paid + total_credited + total_open - total_amount, 6),
        },
        "first_sale_date": min(r["docdate"] for r in rows),
        "last_sale_date": max(r["docdate"] for r in rows),
        "explained_by_mechanism": {
            group: {
                "cases": group_counts[group],
                "amount": round(amount_by_group[group], 2),
            }
            for group in GROUP_ORDER
        },
    }

    (EVIDENCE / "grouped_cases.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    (EVIDENCE / "grouping_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding="utf-8")

    print(json.dumps({
        "grouped": len(rows),
        "distinct": len(distinct_entries),
        "sum_counts": sum(group_counts.values()),
        "groups": dict(group_counts),
        "total_gross": report["total_gross_amount"],
        "paid": report["total_paid_amount"],
        "credited": report["total_credited_amount"],
        "open": report["total_open_amount"],
        "first": report["first_sale_date"],
        "last": report["last_sale_date"],
    }, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())