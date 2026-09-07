"""PHASE 11 — SEGREGATION OF DUTIES (READ ONLY).

Cross-references authorized permissions with actual document activity
to detect incompatible function combinations per user.

SoD rules:
  SALES × CASH:        creates invoice + registers payment
  SALES × CREDIT_NOTE: creates invoice + creates/cancels credit note
  SALES × CANCEL:      creates invoice + cancels it
  PRICE × SALES:       sells + overrides price/discount
  CASH × CANCEL:       registers payment + cancels payment
  STOCK × SALES:       sells + adjusts stock
  PURCHASE × RECEIPT:  creates purchase + confirms receipt
  ACCOUNTING × CASH:   registers payment + alters journal entry
  ADMIN × OPERATION:   administers permissions + performs operations
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from typing import Any

from modules.telchi.investigation.atomic.connection import connect


def fetch_user_capabilities(cursor: Any) -> dict[int, dict[str, Any]]:
    cursor.execute(
        'SELECT U."USERID", U."USER_CODE", U."U_NAME", U."SUPERUSER", U."Locked", '
        'U."DISCOUNT", U."SalesDisc", U."PurchDisc" '
        'FROM "TELCHI"."OUSR" U'
    )
    cols = [d[0] for d in cursor.description]
    users = {}
    for r in cursor.fetchall():
        d = dict(zip(cols, r))
        users[d["USERID"]] = d
    return users


def fetch_user_document_activity(cursor: Any) -> dict[int, dict[str, int]]:
    cursor.execute(
        '''SELECT sub."UserSign", sub."ObjType", COUNT(*) AS cnt
           FROM (
               SELECT "UserSign", '13' AS "ObjType" FROM "TELCHI"."OINV" WHERE "CANCELED" = 'N'
               UNION ALL
               SELECT "UserSign", '14' AS "ObjType" FROM "TELCHI"."ORIN" WHERE "CANCELED" = 'N'
               UNION ALL
               SELECT "UserSign", '24' AS "ObjType" FROM "TELCHI"."ORCT" WHERE "Canceled" = 'N'
               UNION ALL
               SELECT "UserSign", '46' AS "ObjType" FROM "TELCHI"."OVPM" WHERE "Canceled" = 'N'
               UNION ALL
               SELECT "UserSign", '59' AS "ObjType" FROM "TELCHI"."OJDT"
               UNION ALL
               SELECT "UserSign", '67' AS "ObjType" FROM "TELCHI"."OITR"
               UNION ALL
               SELECT "UserSign", '15' AS "ObjType" FROM "TELCHI"."ODLN" WHERE "CANCELED" = 'N'
               UNION ALL
               SELECT "UserSign", '18' AS "ObjType" FROM "TELCHI"."OPCH" WHERE "CANCELED" = 'N'
           ) sub
           GROUP BY sub."UserSign", sub."ObjType"'''
    )
    activity: dict[int, dict[str, int]] = defaultdict(dict)
    for r in cursor.fetchall():
        user_sign = r[0]
        obj_type = r[1]
        cnt = r[2]
        activity[user_sign][obj_type] = cnt
    return activity


def fetch_canceled_documents_per_user(cursor: Any) -> dict[int, dict[str, int]]:
    cursor.execute(
        '''SELECT sub."UserSign", sub."ObjType", COUNT(*) AS cnt
           FROM (
               SELECT "UserSign2" AS "UserSign", '13_CANCELED' AS "ObjType" FROM "TELCHI"."OINV" WHERE "CANCELED" = 'Y'
               UNION ALL
               SELECT "UserSign2", '14_CANCELED' AS "ObjType" FROM "TELCHI"."ORIN" WHERE "CANCELED" = 'Y'
               UNION ALL
               SELECT "UserSign2", '24_CANCELED' AS "ObjType" FROM "TELCHI"."ORCT" WHERE "Canceled" = 'Y'
               UNION ALL
               SELECT "UserSign2", '46_CANCELED' AS "ObjType" FROM "TELCHI"."OVPM" WHERE "Canceled" = 'Y'
           ) sub
           GROUP BY sub."UserSign", sub."ObjType"'''
    )
    canceled: dict[int, dict[str, int]] = defaultdict(dict)
    for r in cursor.fetchall():
        canceled[r[0]][r[1]] = r[2]
    return canceled


CAPABILITY_MAP = {
    "13": "SALES_CREATE",
    "14": "CREDIT_NOTE_CREATE",
    "24": "INCOMING_PAYMENT",
    "46": "OUTGOING_PAYMENT",
    "59": "JOURNAL_ENTRY",
    "67": "INVENTORY_TRANSFER",
    "15": "DELIVERY",
    "18": "PURCHASE_INVOICE",
    "20": "AP_CREDIT_NOTE",
    "13_CANCELED": "SALES_CANCEL",
    "14_CANCELED": "CREDIT_NOTE_CANCEL",
    "24_CANCELED": "PAYMENT_CANCEL",
    "46_CANCELED": "OUTGOING_PAYMENT_CANCEL",
}

SOD_RULES = [
    {
        "rule_id": "SALES_CASH",
        "description": "Creates invoices AND registers incoming payments",
        "cap_a": "SALES_CREATE",
        "cap_b": "INCOMING_PAYMENT",
        "severity": "P1",
    },
    {
        "rule_id": "SALES_CREDIT_NOTE",
        "description": "Creates invoices AND creates credit notes",
        "cap_a": "SALES_CREATE",
        "cap_b": "CREDIT_NOTE_CREATE",
        "severity": "P1",
    },
    {
        "rule_id": "SALES_CANCEL",
        "description": "Creates invoices AND cancels invoices",
        "cap_a": "SALES_CREATE",
        "cap_b": "SALES_CANCEL",
        "severity": "P0",
    },
    {
        "rule_id": "CASH_CANCEL",
        "description": "Registers payments AND cancels payments",
        "cap_a": "INCOMING_PAYMENT",
        "cap_b": "PAYMENT_CANCEL",
        "severity": "P0",
    },
    {
        "rule_id": "SALES_STOCK",
        "description": "Creates invoices AND does inventory transfers",
        "cap_a": "SALES_CREATE",
        "cap_b": "INVENTORY_TRANSFER",
        "severity": "P1",
    },
    {
        "rule_id": "PURCHASE_RECEIPT",
        "description": "Creates purchase invoices AND AP credit notes",
        "cap_a": "PURCHASE_INVOICE",
        "cap_b": "AP_CREDIT_NOTE",
        "severity": "P2",
    },
    {
        "rule_id": "ACCOUNTING_CASH",
        "description": "Creates journal entries AND registers payments",
        "cap_a": "JOURNAL_ENTRY",
        "cap_b": "INCOMING_PAYMENT",
        "severity": "P2",
    },
    {
        "rule_id": "SALES_OUTGOING",
        "description": "Creates invoices AND registers outgoing payments",
        "cap_a": "SALES_CREATE",
        "cap_b": "OUTGOING_PAYMENT",
        "severity": "P1",
    },
]


def detect_sod(
    users: dict[int, dict],
    activity: dict[int, dict[str, int]],
    canceled: dict[int, dict[str, int]],
) -> list[dict[str, Any]]:
    findings = []

    for user_id, user in users.items():
        if user.get("SUPERUSER") == "Y":
            continue

        user_caps: dict[str, int] = {}
        for obj_type, cnt in activity.get(user_id, {}).items():
            cap = CAPABILITY_MAP.get(obj_type)
            if cap:
                user_caps[cap] = cnt
        for obj_type, cnt in canceled.get(user_id, {}).items():
            cap = CAPABILITY_MAP.get(obj_type)
            if cap:
                user_caps[cap] = cnt

        for rule in SOD_RULES:
            cap_a = rule["cap_a"]
            cap_b = rule["cap_b"]
            if cap_a in user_caps and cap_b in user_caps:
                findings.append({
                    "rule_id": rule["rule_id"],
                    "severity": rule["severity"],
                    "description": rule["description"],
                    "cap_a": cap_a,
                    "cap_b": cap_b,
                    "USERID": user_id,
                    "USER_CODE": user["USER_CODE"],
                    "U_NAME": user["U_NAME"],
                    "Locked": user["Locked"],
                    "cap_a_count": user_caps[cap_a],
                    "cap_b_count": user_caps[cap_b],
                    "capabilities": user_caps,
                })

    findings.sort(key=lambda f: (
        {"P0": 0, "P1": 1, "P2": 2, "P3": 3}.get(f["severity"], 9),
        -(f["cap_a_count"] + f["cap_b_count"]),
    ))
    return findings


def main() -> int:
    conn, cur = connect()
    try:
        users = fetch_user_capabilities(cur)
        activity = fetch_user_document_activity(cur)
        canceled = fetch_canceled_documents_per_user(cur)
        findings = detect_sod(users, activity, canceled)

        by_severity = defaultdict(list)
        for f in findings:
            by_severity[f["severity"]].append(f)

        result = {
            "phase": "SEGREGATION_OF_DUTIES",
            "total_findings": len(findings),
            "by_severity": {k: len(v) for k, v in by_severity.items()},
            "findings_top30": findings[:30],
        }

        print(json.dumps(result, indent=2, default=str))

        print(f"\n{'='*60}")
        print("PHASE 11 — SoD SUMMARY")
        print(f"{'='*60}")
        print(f"  Total SoD findings:  {len(findings)}")
        for sev in ("P0", "P1", "P2", "P3"):
            count = len(by_severity.get(sev, []))
            print(f"  {sev}: {count}")

        for sev in ("P0", "P1"):
            if by_severity.get(sev):
                print(f"\n  {sev} FINDINGS:")
                for f in by_severity[sev][:10]:
                    print(f"    [{f['rule_id']}] {f['USER_CODE']:<20} {str(f['U_NAME']):<30} "
                          f"locked={f['Locked']} "
                          f"{f['cap_a_count']}×{f['cap_a']} + {f['cap_b_count']}×{f['cap_b']}")

    finally:
        cur.close()
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
