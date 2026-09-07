"""PHASE 5 (+6) — Exception mechanism candidates + approval evidence (READ ONLY).

Covers OCRD UDFs, customer-block fields, Retail One sale credit fields,
Retail One authorization log (LOGAUTORIZA) and the ERP message queue.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from modules.telchi.investigation.paths import EVIDENCE_ROOT

from modules.telchi.investigation.atomic.connection import connect

EVIDENCE = EVIDENCE_ROOT / "credit_control" / "evidence"


def q(cur, sql):
    cur.execute(sql)
    cols = [d[0].lower() for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def main() -> int:
    conn, cur = connect()
    try:
        ocrd_udf = {}
        for col in ["U_ClienteExcepcional", "U_SO1_01AUTORIZARCOM", "U_SO1_01CLIENTBLOQ", "U_SO1_01VENCREVENC"]:
            rows = q(cur, f'SELECT "{col}" AS v, COUNT(*) AS n FROM "TELCHI"."OCRD" GROUP BY "{col}"')
            ocrd_udf[col] = rows

        # currently over credit limit customers (CardType C, CreditLine>0)
        over = q(cur, '''SELECT "CardCode","CardName","CreditLine","Balance",
            CASE WHEN "Balance" > "CreditLine" THEN 1 ELSE 0 END AS over
            FROM "TELCHI"."OCRD"
            WHERE "CardType"='C' AND "CreditLine" > 0 AND "Balance" > "CreditLine"
            ORDER BY ("Balance"-"CreditLine") DESC''')
        over_id = [r["cardcode"] for r in over]

        # active open invoices overdue as of today (definitive: never paid)
        overdue_now = q(cur, '''SELECT i."CardCode", COUNT(*) AS n_invoices,
            SUM(i."DocTotal"-i."PaidToDate") AS overdue_amount
            FROM "TELCHI"."OINV" i
            WHERE i."CANCELED"='N' AND i."PaidToDate" < i."DocTotal"
              AND i."DocDueDate" < CURRENT_DATE
            GROUP BY i."CardCode"''')
        overdue_amount = {r["cardcode"]: r for r in overdue_now}

        # Retail One sale credit/authorization fields distribution
        ro_sale = {}
        for col in ["U_SO1_CREDITO", "U_SO1_AUTORIZADO", "U_SO1_STATUS", "U_SO1_TIPOVALCUECRED"]:
            rows = q(cur, f'SELECT "{col}" AS v, COUNT(*) AS n FROM "TELCHI"."@SO1_01VENTA" GROUP BY "{col}"')
            ro_sale[col] = rows

        # Retail One authorization log summary
        log = {}
        log["total"] = q(cur, 'SELECT COUNT(*) AS n FROM "TELCHI"."@SO1_01LOGAUTORIZA"')[0]["n"]
        log["date_range"] = q(cur, 'SELECT MIN("U_SO1_FECHAACCESO") AS mn, MAX("U_SO1_FECHAACCESO") AS mx FROM "TELCHI"."@SO1_01LOGAUTORIZA"')[0]
        log["by_identificador"] = q(cur, '''SELECT "U_SO1_IDENTIFICADOR" AS id, COUNT(*) AS n,
            COUNT(DISTINCT "U_SO1_USUARIO") AS users
            FROM "TELCHI"."@SO1_01LOGAUTORIZA" GROUP BY "U_SO1_IDENTIFICADOR" ORDER BY n DESC''')
        log["self_vs_other"] = q(cur, '''SELECT SUM(CASE WHEN "U_SO1_USUARIO"="U_SO1_USUARIOAUTO" THEN 1 ELSE 0 END) AS self_auth,
            SUM(CASE WHEN "U_SO1_USUARIO"<>"U_SO1_USUARIOAUTO" THEN 1 ELSE 0 END) AS other_auth
            FROM "TELCHI"."@SO1_01LOGAUTORIZA"''')[0]

        # Retail One global config credit-related flags
        cfg = q(cur, 'SELECT * FROM "TELCHI"."@SO1_01CONFIGURACION"')
        cfg_row = cfg[0] if cfg else {}
        cfg_credit = {k: v for k, v in cfg_row.items()
                      if any(t.lower() in k for t in ["CRED", "VENC", "LIM", "EXC", "BLOQ", "PEDIDOSCRED", "MONTOMINVENC"])}

        # ERP message queue (Post Transaction Notice output) — object/transaction mix
        erp_msg = q(cur, '''SELECT "U_OBJECT_TYPE" AS obj, "U_TRANSACTION_TYPE" AS tx, COUNT(*) AS n
            FROM "TELCHI"."@UT_ERP_MESSAGE" GROUP BY "U_OBJECT_TYPE","U_TRANSACTION_TYPE" ORDER BY n DESC''')

        out = {
            "ocrd_udf_distributions": ocrd_udf,
            "customers_currently_over_limit": [
                {k: str(r[k.lower()]) for k in ("CardCode", "CardName", "CreditLine", "Balance")} for r in over
            ],
            "customers_overdue_now_count": len(overdue_amount),
            "overdue_amount_total": round(sum(float(v["overdue_amount"] or 0) for v in overdue_amount.values()), 2),
            "retail_one_sale_distributions": ro_sale,
            "retail_one_authorization_log": log,
            "retail_one_credit_config": cfg_credit,
            "erp_message_queue": erp_msg,
            "focus_customers_current_state": {
                c: overdue_amount.get(c) for c in ["C003542", "C008090", "C003531", "C007776", "E000043"]
            },
        }
        (EVIDENCE / "phase56_exception_approval.json").write_text(
            json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        print("over-limit customers:", len(over), "| overdue customers now:", len(overdue_amount))
        print("overdue total:", out["overdue_amount_total"])
        print("focus customers overdue state:", out["focus_customers_current_state"])
        print("RO config credit flags:", cfg_credit)
        print("ERP msg queue:", erp_msg)
        return 0
    finally:
        conn.rollback()
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
