"""PHASE 2 — SAP USER MASTER validation.

READ ONLY. Extracts the complete SAP user inventory and reconciles:
  - total users vs active vs blocked
  - users with/without employee
  - users with/without salesperson
  - superusers identified
  - users with no login ever or very old login
  - employee without user
  - salesperson without user
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from modules.telchi.investigation.atomic.connection import connect


SQL_PATH = Path(__file__).resolve().parents[2] / "sql" / "current" / "users" / "user_master_v1.sql"


def load_sql() -> str:
    return SQL_PATH.read_text(encoding="utf-8")


def fetch_users(cursor: Any) -> list[dict[str, Any]]:
    sql = load_sql()
    cursor.execute(sql)
    cols = [d[0] for d in cursor.description]
    rows = []
    for raw in cursor.fetchall():
        rows.append(dict(zip(cols, raw)))
    return rows


def reconcile_summary(users: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(users)
    active = sum(1 for u in users if u.get("Locked") == "N")
    blocked = sum(1 for u in users if u.get("Locked") == "Y")
    locked_unknown = total - active - blocked
    superusers = sum(1 for u in users if u.get("SUPERUSER") == "Y")

    with_employee = sum(1 for u in users if u.get("emp_empID") is not None)
    without_employee = total - with_employee

    with_salesperson = sum(1 for u in users if u.get("slp_SlpCode") is not None)
    without_salesperson = total - with_salesperson

    with_branch = sum(1 for u in users if u.get("branch_Code") is not None)

    never_logged_in = sum(1 for u in users if u.get("lastLogin") is None)
    logged_in_365_plus = 0
    from datetime import date, timedelta
    cutoff_365 = (date.today() - timedelta(days=365)).isoformat()
    cutoff_180 = (date.today() - timedelta(days=180)).isoformat()
    cutoff_90 = (date.today() - timedelta(days=90)).isoformat()

    dormant_365 = 0
    dormant_180 = 0
    dormant_90 = 0
    for u in users:
        ll = u.get("lastLogin")
        if ll is not None:
            ll_str = str(ll)[:10]
            if ll_str <= cutoff_365:
                dormant_365 += 1
            if ll_str <= cutoff_180:
                dormant_180 += 1
            if ll_str <= cutoff_90:
                dormant_90 += 1

    return {
        "total_users": total,
        "active": active,
        "blocked": blocked,
        "locked_status_unknown": locked_unknown,
        "superusers": superusers,
        "with_employee": with_employee,
        "without_employee": without_employee,
        "with_salesperson": with_salesperson,
        "without_salesperson": without_salesperson,
        "with_branch": with_branch,
        "never_logged_in": never_logged_in,
        "dormant_90_days": dormant_90,
        "dormant_180_days": dormant_180,
        "dormant_365_days": dormant_365,
    }


def fetch_employees_without_user(cursor: Any) -> list[dict[str, Any]]:
    cursor.execute(
        'SELECT E."empID", E."firstName", E."lastName", E."userId", '
        'E."status", E."Active", E."salesPrson" '
        'FROM "TELCHI"."OHEM" E '
        'LEFT JOIN "TELCHI"."OUSR" U ON U."USERID" = E."userId" '
        'WHERE U."USERID" IS NULL '
        'ORDER BY E."empID"'
    )
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, r)) for r in cursor.fetchall()]


def fetch_salespersons_without_user(cursor: Any) -> list[dict[str, Any]]:
    cursor.execute(
        'SELECT S."SlpCode", S."SlpName", S."EmpID", S."Active", S."Locked" '
        'FROM "TELCHI"."OSLP" S '
        'WHERE S."EmpID" NOT IN (SELECT "empID" FROM "TELCHI"."OHEM" WHERE "userId" IS NOT NULL) '
        'AND S."EmpID" IS NOT NULL '
        'ORDER BY S."SlpCode"'
    )
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, r)) for r in cursor.fetchall()]


def identify_generic_users(users: list[dict[str, Any]]) -> list[dict[str, Any]]:
    generic_patterns = (
        "CAJA", "VENTAS", "ADMIN", "POS", "SUCURSAL", "FARMACIA",
        "LABORATORIO", "SISTEMA", "SYSTEM", "INTEGRACION", "DMS",
        "RETAIL", "SYNC", "BATCH", "SERVICE", "USER", "TEST",
        "INVITADO", "GUEST", "PUBLIC", "COMMON", "SHARED",
    )
    found = []
    for u in users:
        code = (u.get("USER_CODE") or "").upper()
        name = (u.get("U_NAME") or "").upper()
        for pat in generic_patterns:
            if pat in code or pat in name:
                found.append({
                    "USERID": u["USERID"],
                    "USER_CODE": u["USER_CODE"],
                    "U_NAME": u["U_NAME"],
                    "Locked": u.get("Locked"),
                    "SUPERUSER": u.get("SUPERUSER"),
                    "match_pattern": pat,
                    "lastLogin": str(u.get("lastLogin"))[:10] if u.get("lastLogin") else None,
                })
                break
    return found


def main() -> int:
    conn, cur = connect()
    try:
        users = fetch_users(cur)
        summary = reconcile_summary(users)
        employees_no_user = fetch_employees_without_user(cur)
        salespersons_no_user = fetch_salespersons_without_user(cur)
        generic_users = identify_generic_users(users)

        superuser_list = [
            {
                "USERID": u["USERID"],
                "USER_CODE": u["USER_CODE"],
                "U_NAME": u["U_NAME"],
                "Locked": u.get("Locked"),
                "lastLogin": str(u.get("lastLogin"))[:10] if u.get("lastLogin") else None,
                "emp_firstName": u.get("emp_firstName"),
                "emp_lastName": u.get("emp_lastName"),
            }
            for u in users if u.get("SUPERUSER") == "Y"
        ]

        result = {
            "phase": "USER_MASTER",
            "summary": summary,
            "superusers": superuser_list,
            "generic_users_detected": generic_users,
            "employees_without_user_count": len(employees_no_user),
            "employees_without_user_sample": employees_no_user[:20],
            "salespersons_without_user_count": len(salespersons_no_user),
            "salespersons_without_user_sample": salespersons_no_user[:20],
        }

        print(json.dumps(result, indent=2, default=str))

        print(f"\n{'='*60}")
        print(f"PHASE 2 — SAP USER MASTER SUMMARY")
        print(f"{'='*60}")
        for k, v in summary.items():
            print(f"  {k:<30} {v}")
        print(f"\n  superusers_listed:         {len(superuser_list)}")
        print(f"  generic_users_detected:    {len(generic_users)}")
        print(f"  employees_without_user:    {len(employees_no_user)}")
        print(f"  salespersons_without_user: {len(salespersons_no_user)}")

    finally:
        cur.close()
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
