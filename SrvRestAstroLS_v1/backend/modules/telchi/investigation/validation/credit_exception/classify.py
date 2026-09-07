"""PHASE 8/27/28 — Classification engine for the credit-exception cases.

Consumes evidence/case_bundle.json (built by extract_all.py from the exact
as-of reconstruction, doc-chain, payments, retail linkage, SAP actors).

Precedence (each case gets ONE primary reason; evidence[] lists the factors):
  1 CUSTOMER_EXCEPTION_FLAG            VENCREVENC='Y' customer
  2 PAYMENT_BEFORE_EFFECTIVE_BLOCK_CHECK  retail cash (CREDITO=N) settled
                                        same-day (payment covers the sale)
  3 CREDIT_NOTE_OR_RECONCILIATION      settled by credit note (ORIN side)
  4 RETAIL_CREDIT_AUTHORIZATION_LOG    retail auth event <= sale time
  5 ORDER_AUTHORIZED_BEFORE_OVERDUE    base order existed while no overdue
  6 DELIVERY_FLOW_EXPLAINS_TIMING      invoice based on delivery (DlnLimit=N)
  7 SUPERUSER_AUTHORIZATION            executer is a SAP superuser/technical
  8 SAP_FULL_AUTHORIZATION             executer has FULL credit deviation auth
  9 TECHNICAL_INTEGRATION_PATH         DMS direct channel with tech users
 10 RULE_THRESHOLD_NOT_MET             overdue amount residual/negligible
 11 OVERDUE_RECONSTRUCTION_FALSE_POSITIVE  reconstruction artifact (clamped)
 12 UNRESOLVED                          evidence gap
 13 UNEXPLAINED                         no evidence explains the sale

Confidence levels: EXACT / STRONG / HEURISTIC / UNKNOWN.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from modules.telchi.investigation.paths import EVIDENCE_ROOT

HERE = Path(__file__).parent
EVIDENCE = EVIDENCE_ROOT / "credit_exception" / "evidence"
TOLERANCE = 0.01

REASON_DESC = {
    "CUSTOMER_EXCEPTION_FLAG": "cliente con flag de excepción de crédito (U_SO1_01VENCREVENC='Y')",
    "PAYMENT_BEFORE_EFFECTIVE_BLOCK_CHECK": "venta de contado cubierta el mismo día (no extensión de crédito)",
    "CREDIT_NOTE_OR_RECONCILIATION": "factura liquidada con nota de crédito/reconciliación",
    "RETAIL_CREDIT_AUTHORIZATION_LOG": "evento de autorización Retail One en la ventana de la venta",
    "ORDER_AUTHORIZED_BEFORE_OVERDUE": "pedido previo autorizado sin vencidos en la fecha del pedido",
    "DELIVERY_FLOW_EXPLAINS_TIMING": "factura derivada de entrega (control de entrega DlnLimit=N)",
    "SUPERUSER_AUTHORIZATION": "ejecutor con autorización de superusuario/técnico SAP",
    "SAP_FULL_AUTHORIZATION": "ejecutor con autorización total de desviación de línea de crédito",
    "TECHNICAL_INTEGRATION_PATH": "canal de integración técnica DMS (usuario técnico)",
    "RULE_THRESHOLD_NOT_MET": "saldo vencido residual/tolerancia no alcanza umbral",
    "OVERDUE_RECONSTRUCTION_FALSE_POSITIVE": "artefacto de reconstrucción (aplicación previa)",
    "UNRESOLVED": "sin datos suficientes para clasificar",
    "UNEXPLAINED": "sin evidencia que explique la venta",
}

CONF_LEVEL = {
    "CUSTOMER_EXCEPTION_FLAG": "STRONG",
    "PAYMENT_BEFORE_EFFECTIVE_BLOCK_CHECK": "STRONG",
    "CREDIT_NOTE_OR_RECONCILIATION": "EXACT",
    "RETAIL_CREDIT_AUTHORIZATION_LOG": "HEURISTIC",
    "ORDER_AUTHORIZED_BEFORE_OVERDUE": "EXACT",
    "DELIVERY_FLOW_EXPLAINS_TIMING": "STRONG",
    "SUPERUSER_AUTHORIZATION": "STRONG",
    "SAP_FULL_AUTHORIZATION": "STRONG",
    "TECHNICAL_INTEGRATION_PATH": "STRONG",
    "RULE_THRESHOLD_NOT_MET": "STRONG",
    "OVERDUE_RECONSTRUCTION_FALSE_POSITIVE": "EXACT",
    "UNRESOLVED": "UNKNOWN",
    "UNEXPLAINED": "UNKNOWN",
}


def classify_one(c: dict) -> dict:
    ev: list[str] = []
    warn: list[str] = []
    is_retail = bool(c["retail"].get("matched"))
    credito_n = c["retail"].get("credito") == "N"
    fully_paid = bool(c.get("fully_paid"))
    paid_days = c.get("days_to_first_any")
    auth_ev = c["retail"].get("auth_events_window") or []
    auth_before = any(e.get("timing") in ("BEFORE_SALE", "SAME_TIME_WINDOW") for e in auth_ev)
    over_limit = bool(c.get("over_limit_before") or c.get("over_limit_after"))
    full_auth = c.get("excel_credit_auth") == "FULL"
    superuser = c.get("superuser") == "Y"
    order_exists = c.get("order_entry") is not None
    delivery_exists = c.get("delivery_entry") is not None
    retail_flag = c["origin"] == "SAP" and c["retailone"] == "Y"
    reason = None

    if c["vencrevenc_y"]:
        reason = "CUSTOMER_EXCEPTION_FLAG"
        ev.append(f"U_SO1_01VENCREVENC='Y' para {c['cardcode']}")
    elif is_retail and credito_n and fully_paid:
        reason = "PAYMENT_BEFORE_EFFECTIVE_BLOCK_CHECK"
        ev.append(f"venta Retail One {c['retail'].get('tipo')} con U_SO1_CREDITO='N' (POS contado)")
        if paid_days is not None:
            ev.append(f"liquidada a los {paid_days} días de la venta")
        warn.append("el control TN no es legible (PARTIAL); venta de contado Retail One")
    elif c.get("settled_by_credit_note"):
        reason = "CREDIT_NOTE_OR_RECONCILIATION"
        ev.append("factura liquidada con nota de crédito (lado ORIN de la reconciliación)")
    elif is_retail and auth_before:
        reason = "RETAIL_CREDIT_AUTHORIZATION_LOG"
        ev.append(f"{len(auth_ev)} evento(s) de autorización en ventana ±60min")
        ev.append("identificadores: " + ",".join(e["identificador"] for e in auth_ev[:4]))
        warn.append("significado de IDENTIFICADOR no documentado (diccionario addon ausente)")
    elif order_exists and c.get("any_overdue_at_order") is False:
        reason = "ORDER_AUTHORIZED_BEFORE_OVERDUE"
        ev.append(f"pedido {c.get('order_num')} ({c.get('order_date')}) sin vencidos en esa fecha")
    elif delivery_exists:
        reason = "DELIVERY_FLOW_EXPLAINS_TIMING"
        ev.append(f"factura basada en entrega {c['delivery_entry']} ({c['delivery_date']})")
        warn.append("OADM.DlnLimit=N; ODLN no referencia crédito en el grafo TN; el bloqueo en OINV no reproducible (PARTIAL)")
    elif over_limit and (full_auth or superuser):
        reason = "SAP_FULL_AUTHORIZATION"
        ev.append(f"ejecutor {c['sap_user']} con autorización total (Excel) y exposición sobre límite en la venta")
        warn.append("HISTORICAL_AUTHORIZATION=UNAVAILABLE; override SAP no registrado en el log")
    elif c.get("origin") == "DMS":
        reason = "TECHNICAL_INTEGRATION_PATH"
        ev.append("canal DMS")
        if c.get("sap_user") == "dms":
            ev.append("usuario técnico 'dms' (integración)")
        warn.append("DMS_HUMAN_OPERATOR_IDENTITY=UNRESOLVED")
    elif retail_flag and not is_retail:
        reason = "UNRESOLVED"
        ev.append("venta Retail One sin registro VENTA recuperable (cliente+fecha+total no resolvió)")
        warn.append("linkage R1->OINV por cliente+fecha+monto con tolerancia; folio no siempre recuperable")
    elif is_retail and credito_n and not fully_paid:
        reason = "UNRESOLVED"
        ev.append(f"venta POS {c['retail'].get('tipo')} con U_SO1_CREDITO='N' pero sin liquidación en SAP")
        warn.append("cobranza POS pendiente o recepción no aplicada; TN y diccionario R1 no legibles")
    elif superuser:
        reason = "SUPERUSER_AUTHORIZATION"
        ev.append(f"ejecutor superusuario {c['sap_user']} (USERID {c['usersign']})")
        warn.append("no hay evidencia de que SUPERUSER exima del Transaction Notification")
    elif full_auth and c.get("origin") == "SAP" and c.get("retailone") == "N":
        reason = "SAP_FULL_AUTHORIZATION"
        ev.append(f"ejecutor {c['sap_user']} con autorización total (Excel); vencido {c['overdue_amount_at_sale']}")
        warn.append("HISTORICAL_AUTHORIZATION=UNAVAILABLE; la exención del TN no es demostrable (PARTIAL)")
    elif (c.get("overdue_amount_at_sale") or 0) <= 1.0:
        reason = "RULE_THRESHOLD_NOT_MET"
        ev.append(f"vencido en la fecha de venta {c['overdue_amount_at_sale']} (residual/tolerancia)")
    elif c.get("applied_note", "").startswith("overapplied"):
        reason = "OVERDUE_RECONSTRUCTION_FALSE_POSITIVE"
        ev.append(c["applied_note"])
    else:
        reason = "UNEXPLAINED"
        ev.append("ninguna evidencia de autorización, pedido previo, contado o flujo técnico")
        warn.append("TN_SOURCE_INSPECTION=PARTIAL; HISTORICAL_AUTHORIZATION=UNAVAILABLE")

    conf = CONF_LEVEL[reason]
    return {
        "case_id": f"{c['cardcode']}_{c['docentry']}",
        "doc_entry": c["docentry"],
        "classification": reason,
        "reason_code": reason,
        "reason_description": REASON_DESC[reason],
        "confidence": conf,
        "warning": warn,
        "evidence": ev,
    }


def main() -> int:
    bundle = json.loads((EVIDENCE / "case_bundle.json").read_text(encoding="utf-8"))
    classified = []
    for c in bundle:
        cl = classify_one(c)
        classified.append({**c, **cl})

    dist = Counter(x["classification"] for x in classified)
    confd = Counter(x["confidence"] for x in classified)
    # executive buckets
    exec_buckets = Counter()
    for x in classified:
        if x["confidence"] == "EXACT":
            exec_buckets["EXACTLY_EXPLAINED"] += 1
        elif x["confidence"] == "STRONG":
            exec_buckets["STRONGLY_EXPLAINED"] += 1
        elif x["confidence"] == "HEURISTIC":
            exec_buckets["HEURISTICALLY_EXPLAINED"] += 1
        else:
            exec_buckets[x["classification"]] += 1  # UNRESOLVED / UNEXPLAINED

    # baseline 287 (prior gate) intersection
    prior = json.loads((EVIDENCE.parent.parent / "credit_control" / "evidence" / "phase78_sale_credit_state.json")
                       .read_text(encoding="utf-8"))["all_overdue_sales"]
    prior_keys = {(s["cardcode"], s["docentry"]) for s in prior}
    base287 = [x for x in classified if (x["cardcode"], x["doc_entry"]) in prior_keys]
    base287_dist = Counter(x["classification"] for x in base287)

    # channel x classification
    chan_x_reason = defaultdict(Counter)
    for x in classified:
        ch = "RETAIL_ONE" if (x["origin"] == "SAP" and x["retailone"] == "Y") else (
            "DMS" if x["origin"] == "DMS" else "SAP_DIRECT")
        chan_x_reason[ch][x["classification"]] += 1

    # repeat customers / users
    by_cust = defaultdict(lambda: {"n": 0, "amount": 0.0, "open": 0.0})
    for x in classified:
        cc = by_cust[x["cardcode"]]
        cc["n"] += 1
        cc["amount"] += float(x["doctotal"])
        cc["open"] += float(x.get("open_now") or 0)
        cc["channels"] = set(cc.get("channels", set()))
        cc["channels"].add("RETAIL_ONE" if (x["origin"] == "SAP" and x["retailone"] == "Y")
                           else "DMS" if x["origin"] == "DMS" else "SAP_DIRECT")
    by_user = defaultdict(lambda: {"n": 0, "amount": 0.0})
    for x in classified:
        k = f"{x['sap_user']}"
        by_user[k]["n"] += 1
        by_user[k]["amount"] += float(x["doctotal"])

    (EVIDENCE / "classified_cases.json").write_text(
        json.dumps(classified, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    report = {
        "total": len(classified),
        "classification_distribution": dict(dist),
        "confidence_distribution": dict(confd),
        "executive_buckets": dict(exec_buckets),
        "baseline_287": {
            "total_prior": len(prior_keys),
            "present_in_revalidated": sum(1 for x in classified if (x["cardcode"], x["doc_entry"]) in prior_keys),
            "classification_distribution": dict(base287_dist),
        },
        "channel_x_reason": {k: dict(v) for k, v in chan_x_reason.items()},
        "repeat_customers": sorted(
            ({"cardcode": k, **v} for k, v in by_cust.items()), key=lambda r: -r["n"])[:25],
        "repeat_users": sorted(
            ({"user": k, **v} for k, v in by_user.items()), key=lambda r: -r["n"])[:25],
        "open_amount_total": round(sum(x.get("open_now") or 0 for x in classified), 2),
        "unexplained": [x for x in classified if x["classification"] in ("UNEXPLAINED", "UNRESOLVED")],
    }
    (EVIDENCE / "classification_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(json.dumps({
        "total": len(classified),
        "classification_distribution": dict(dist),
        "executive_buckets": dict(exec_buckets),
        "baseline287_present_distribution": dict(base287_dist),
        "baseline287_present": report["baseline_287"]["present_in_revalidated"],
        "open_amount_total": report["open_amount_total"],
        "channel_x_reason": {k: dict(v) for k, v in chan_x_reason.items()},
    }, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())