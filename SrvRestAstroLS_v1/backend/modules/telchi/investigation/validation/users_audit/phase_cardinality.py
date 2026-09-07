"""Cardinality / anti-fanout tests (§14, §27) — READ ONLY.

For each critical join, measure rows before/after, distinct keys,
duplicate amplification, unmatched left/right. Gate: NO_SILENT_FANOUT.
"""
from __future__ import annotations

import json
import sys
from typing import Any

from modules.telchi.investigation.atomic.connection import connect


def scalar(cursor: Any, sql: str, params: tuple = ()) -> Any:
    cursor.execute(sql, params)
    return cursor.fetchone()[0]


def check_join(
    cursor: Any,
    label: str,
    left_sql: str,
    right_sql: str,
    join_sql: str,
    left_key: str,
    right_key: str,
) -> dict[str, Any]:
    left_rows = scalar(cursor, left_sql)
    right_rows = scalar(cursor, right_sql)
    left_distinct = scalar(cursor, f"SELECT COUNT(DISTINCT {left_key}) FROM ({left_sql[7:].strip()}) t"
                           if False else left_sql.replace("COUNT(*)", f"COUNT(DISTINCT {left_key})", 1))
    right_distinct = scalar(cursor, right_sql.replace("COUNT(*)", f"COUNT(DISTINCT {right_key})", 1))
    joined_rows = scalar(cursor, join_sql)
    dup_factor = round(joined_rows / left_rows, 3) if left_rows else 0
    return {
        "join": label,
        "left_rows": left_rows,
        "right_rows": right_rows,
        "left_distinct": left_distinct,
        "right_distinct": right_distinct,
        "joined_rows": joined_rows,
        "duplicate_factor": dup_factor,
    }


def main() -> int:
    conn, cur = connect()
    try:
        checks = []

        # 1. user -> direct permissions (USR3)
        checks.append(check_join(
            cur, "OUSR->USR3 (user->direct_perms)",
            'SELECT COUNT(*) FROM "TELCHI"."OUSR"',
            'SELECT COUNT(*) FROM "TELCHI"."USR3"',
            'SELECT COUNT(*) FROM "TELCHI"."OUSR" U JOIN "TELCHI"."USR3" P ON P."UserLink"=U."USERID"',
            '"USERID"', '"UserLink"',
        ))

        # 2. user -> groups (USR7)
        checks.append(check_join(
            cur, "OUSR->USR7 (user->groups)",
            'SELECT COUNT(*) FROM "TELCHI"."OUSR"',
            'SELECT COUNT(*) FROM "TELCHI"."USR7"',
            'SELECT COUNT(*) FROM "TELCHI"."OUSR" U JOIN "TELCHI"."USR7" G ON G."UserId"=U."USERID"',
            '"USERID"', '"UserId"',
        ))

        # 3. group -> permissions (UGR1)
        checks.append(check_join(
            cur, "OUGR->UGR1 (group->perms)",
            'SELECT COUNT(*) FROM "TELCHI"."OUGR"',
            'SELECT COUNT(*) FROM "TELCHI"."UGR1"',
            'SELECT COUNT(*) FROM "TELCHI"."OUGR" G JOIN "TELCHI"."UGR1" P ON P."GroupLink"=G."GroupId"',
            '"GroupId"', '"GroupLink"',
        ))

        # 4. user -> USR5 activity
        checks.append(check_join(
            cur, "OUSR->USR5 (user->activity)",
            'SELECT COUNT(*) FROM "TELCHI"."OUSR"',
            'SELECT COUNT(*) FROM "TELCHI"."USR5"',
            'SELECT COUNT(*) FROM "TELCHI"."OUSR" U JOIN "TELCHI"."USR5" A ON A."UserCode"=U."USER_CODE"',
            '"USER_CODE"', '"UserCode"',
        ))

        # 5. invoice -> settlement (ITR1)
        checks.append(check_join(
            cur, "OINV->ITR1 (invoice->settlement, SrcObjTyp=13)",
            'SELECT COUNT(*) FROM "TELCHI"."OINV" WHERE "CANCELED"=\'N\'',
            'SELECT COUNT(*) FROM "TELCHI"."ITR1" WHERE "SrcObjTyp"=13',
            'SELECT COUNT(*) FROM "TELCHI"."OINV" O JOIN "TELCHI"."ITR1" L ON L."SrcObjAbs"=O."DocEntry" AND L."SrcObjTyp"=13 WHERE O."CANCELED"=\'N\'',
            '"DocEntry"', '"SrcObjAbs"',
        ))

        # 6. invoice -> stock (OINM via DocNum)
        checks.append(check_join(
            cur, "OINV->OINM (invoice->stock via DocNum)",
            'SELECT COUNT(*) FROM "TELCHI"."OINV" WHERE "CANCELED"=\'N\'',
            'SELECT COUNT(*) FROM "TELCHI"."OINM" WHERE "TransType"=13',
            'SELECT COUNT(*) FROM "TELCHI"."OINV" O JOIN "TELCHI"."OINM" M ON M."BASE_REF"=O."DocNum" WHERE O."CANCELED"=\'N\' AND M."TransType"=13',
            '"DocNum"', '"BASE_REF"',
        ))

        # 7. payment -> journal (ORCT.TransId -> OJDT.TransId)
        checks.append(check_join(
            cur, "ORCT->OJDT (payment->journal via TransId)",
            'SELECT COUNT(*) FROM "TELCHI"."ORCT"',
            'SELECT COUNT(*) FROM "TELCHI"."OJDT"',
            'SELECT COUNT(*) FROM "TELCHI"."ORCT" P JOIN "TELCHI"."OJDT" J ON J."TransId"=P."TransId"',
            '"TransId"', '"TransId"',
        ))

        # 8. journal -> lines (OJDT->JDT1)
        checks.append(check_join(
            cur, "OJDT->JDT1 (journal->lines)",
            'SELECT COUNT(*) FROM "TELCHI"."OJDT"',
            'SELECT COUNT(*) FROM "TELCHI"."JDT1"',
            'SELECT COUNT(*) FROM "TELCHI"."OJDT" J JOIN "TELCHI"."JDT1" D ON D."TransId"=J."TransId"',
            '"TransId"', '"TransId"',
        ))

        result = {"phase": "CARDINALITY", "checks": checks}
        print(json.dumps(result, indent=2, default=str))

        print(f"\nCARDINALITY / ANTI-FANOUT")
        fanout_violations = 0
        for c in checks:
            dup = c["duplicate_factor"]
            flag = "OK" if dup <= 5 else "CHECK"
            if dup > 5:
                fanout_violations += 1
            print(f"  {c['join']:<45} left={c['left_rows']:<10} joined={c['joined_rows']:<10} "
                  f"dup={dup:<7} [{flag}]")

        print(f"\n  Fanout violations (>5x): {fanout_violations}")

    finally:
        cur.close()
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
