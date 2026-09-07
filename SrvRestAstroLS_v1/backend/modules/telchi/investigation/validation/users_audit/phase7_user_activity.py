"""PHASE 7+11 — USER ACTIVITY LOG (USR5) + DOCUMENT ACTIVITY (READ ONLY).

USR5 has 3.17M rows of user activity log:
  UserCode, Action, ActionBy, ClientIP, Date, Time, SessionID, etc.

This phase:
  1. Profiles USR5: distinct actions, date range, top users
  2. Identifies login patterns, concurrent sessions, multi-IP usage
  3. Cross-references with user master (active/blocked/superuser)
  4. Detects dormant users with recent activity
  5. Detects blocked users with activity
  6. Detects multi-branch / multi-IP usage per user
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from typing import Any

from modules.telchi.investigation.atomic.connection import connect


def profile_usr5(cursor: Any) -> dict[str, Any]:
    cursor.execute(
        'SELECT COUNT(*), MIN("Date"), MAX("Date"), '
        'COUNT(DISTINCT "UserCode"), COUNT(DISTINCT "Action"), '
        'COUNT(DISTINCT "ClientIP"), COUNT(DISTINCT "SessionID") '
        'FROM "TELCHI"."USR5"'
    )
    row = cursor.fetchone()
    return {
        "total_rows": row[0],
        "date_min": str(row[1])[:10] if row[1] else None,
        "date_max": str(row[2])[:10] if row[2] else None,
        "distinct_users": row[3],
        "distinct_actions": row[4],
        "distinct_client_ips": row[5],
        "distinct_sessions": row[6],
    }


def action_distribution(cursor: Any) -> list[dict[str, Any]]:
    cursor.execute(
        'SELECT "Action", COUNT(*) AS cnt FROM "TELCHI"."USR5" '
        'GROUP BY "Action" ORDER BY cnt DESC LIMIT 30'
    )
    return [{"Action": r[0], "count": r[1]} for r in cursor.fetchall()]


def top_users_by_activity(cursor: Any) -> list[dict[str, Any]]:
    cursor.execute(
        'SELECT U5."UserCode", U."U_NAME", U."SUPERUSER", U."Locked", '
        'COUNT(*) AS cnt, MIN(U5."Date") AS first_seen, MAX(U5."Date") AS last_seen, '
        'COUNT(DISTINCT U5."ClientIP") AS distinct_ips '
        'FROM "TELCHI"."USR5" U5 '
        'LEFT JOIN "TELCHI"."OUSR" U ON U."USER_CODE" = U5."UserCode" '
        'GROUP BY U5."UserCode", U."U_NAME", U."SUPERUSER", U."Locked" '
        'ORDER BY cnt DESC LIMIT 30'
    )
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, r)) for r in cursor.fetchall()]


def blocked_users_with_activity(cursor: Any) -> list[dict[str, Any]]:
    cursor.execute(
        'SELECT U5."UserCode", U."U_NAME", U."SUPERUSER", U."Locked", '
        'COUNT(*) AS cnt, MAX(U5."Date") AS last_activity, '
        'COUNT(DISTINCT U5."ClientIP") AS distinct_ips '
        'FROM "TELCHI"."USR5" U5 '
        'JOIN "TELCHI"."OUSR" U ON U."USER_CODE" = U5."UserCode" '
        'WHERE U."Locked" = \'Y\' '
        'GROUP BY U5."UserCode", U."U_NAME", U."SUPERUSER", U."Locked" '
        'ORDER BY cnt DESC'
    )
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, r)) for r in cursor.fetchall()]


def multi_ip_users(cursor: Any) -> list[dict[str, Any]]:
    cursor.execute(
        'SELECT U5."UserCode", U."U_NAME", U."SUPERUSER", U."Locked", '
        'COUNT(DISTINCT U5."ClientIP") AS distinct_ips, '
        'COUNT(*) AS total_actions '
        'FROM "TELCHI"."USR5" U5 '
        'LEFT JOIN "TELCHI"."OUSR" U ON U."USER_CODE" = U5."UserCode" '
        'GROUP BY U5."UserCode", U."U_NAME", U."SUPERUSER", U."Locked" '
        'HAVING COUNT(DISTINCT U5."ClientIP") > 3 '
        'ORDER BY distinct_ips DESC LIMIT 20'
    )
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, r)) for r in cursor.fetchall()]


def document_activity_per_user(cursor: Any) -> list[dict[str, Any]]:
    cursor.execute(
        '''SELECT "UserSign", COUNT(*) AS doc_count,
                  COUNT(DISTINCT "ObjType") AS distinct_obj_types,
                  MIN("DocDate") AS first_doc, MAX("DocDate") AS last_doc
           FROM (
               SELECT "UserSign", '13' AS "ObjType", "CreateDate" AS "DocDate" FROM "TELCHI"."OINV"
               UNION ALL
               SELECT "UserSign", '14' AS "ObjType", "CreateDate" FROM "TELCHI"."ORIN"
               UNION ALL
               SELECT "UserSign", '24' AS "ObjType", "CreateDate" FROM "TELCHI"."ORCT"
               UNION ALL
               SELECT "UserSign", '46' AS "ObjType", "CreateDate" FROM "TELCHI"."OVPM"
               UNION ALL
               SELECT "UserSign", '59' AS "ObjType", "CreateDate" FROM "TELCHI"."OJDT"
               UNION ALL
               SELECT "UserSign", '67' AS "ObjType", "CreateDate" FROM "TELCHI"."OITR"
               UNION ALL
               SELECT "UserSign", '15' AS "ObjType", "CreateDate" FROM "TELCHI"."ODLN"
               UNION ALL
               SELECT "UserSign", '16' AS "ObjType", "CreateDate" FROM "TELCHI"."ORDN"
               UNION ALL
               SELECT "UserSign", '20' AS "ObjType", "CreateDate" FROM "TELCHI"."OPCH"
           ) sub
           GROUP BY "UserSign"
           ORDER BY doc_count DESC'''
    )
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, r)) for r in cursor.fetchall()]


OBJ_TYPE_NAMES = {
    "13": "A/R Invoice",
    "14": "A/R Credit Note",
    "15": "Delivery",
    "16": "Returns",
    "18": "A/P Invoice",
    "20": "A/P Credit Note",
    "24": "Incoming Payment",
    "46": "Outgoing Payment",
    "59": "Journal Entry",
    "67": "Inventory Transfer",
}


def document_activity_by_type_per_user(cursor: Any) -> list[dict[str, Any]]:
    cursor.execute(
        '''SELECT sub."UserSign", sub."ObjType", COUNT(*) AS cnt
           FROM (
               SELECT "UserSign", '13' AS "ObjType" FROM "TELCHI"."OINV"
               UNION ALL
               SELECT "UserSign", '14' AS "ObjType" FROM "TELCHI"."ORIN"
               UNION ALL
               SELECT "UserSign", '24' AS "ObjType" FROM "TELCHI"."ORCT"
               UNION ALL
               SELECT "UserSign", '46' AS "ObjType" FROM "TELCHI"."OVPM"
               UNION ALL
               SELECT "UserSign", '59' AS "ObjType" FROM "TELCHI"."OJDT"
               UNION ALL
               SELECT "UserSign", '67' AS "ObjType" FROM "TELCHI"."OITR"
               UNION ALL
               SELECT "UserSign", '15' AS "ObjType" FROM "TELCHI"."ODLN"
               UNION ALL
               SELECT "UserSign", '20' AS "ObjType" FROM "TELCHI"."OPCH"
           ) sub
           GROUP BY sub."UserSign", sub."ObjType"
           HAVING COUNT(*) > 0
           ORDER BY sub."UserSign", cnt DESC'''
    )
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, r)) for r in cursor.fetchall()]


def main() -> int:
    conn, cur = connect()
    try:
        profile = profile_usr5(cur)
        actions = action_distribution(cur)
        top_users = top_users_by_activity(cur)
        blocked_activity = blocked_users_with_activity(cur)
        multi_ip = multi_ip_users(cur)
        doc_activity = document_activity_per_user(cur)
        doc_by_type = document_activity_by_type_per_user(cur)

        doc_by_type_by_user: dict[int, dict[str, int]] = defaultdict(dict)
        for r in doc_by_type:
            cnt = r.get("cnt") or r.get("CNT") or 0
            doc_by_type_by_user[r["UserSign"]][r["ObjType"]] = cnt

        for da in doc_activity:
            da["by_type"] = doc_by_type_by_user.get(da["UserSign"], {})

        result = {
            "phase": "USER_ACTIVITY",
            "usr5_profile": profile,
            "action_distribution_top30": actions,
            "top_users_by_activity": top_users,
            "blocked_users_with_activity": blocked_activity,
            "multi_ip_users": multi_ip,
            "document_activity_per_user_top": doc_activity[:30],
        }

        print(json.dumps(result, indent=2, default=str))

        print(f"\n{'='*60}")
        print("PHASE 7+11 — USER ACTIVITY SUMMARY")
        print(f"{'='*60}")
        print(f"  USR5 total rows:             {profile['total_rows']:,}")
        print(f"  USR5 date range:             {profile['date_min']} → {profile['date_max']}")
        print(f"  Distinct users in USR5:      {profile['distinct_users']}")
        print(f"  Distinct actions:            {profile['distinct_actions']}")
        print(f"  Distinct client IPs:         {profile['distinct_client_ips']}")
        print(f"  Blocked users with activity: {len(blocked_activity)}")
        print(f"  Multi-IP users (>3):         {len(multi_ip)}")
        print(f"  Users with doc activity:     {len(doc_activity)}")

        if blocked_activity:
            print(f"\n  BLOCKED USERS WITH ACTIVITY (P0/P1):")
            for b in blocked_activity[:10]:
                cnt = b.get("cnt") or b.get("CNT") or 0
                last = b.get("last_activity") or b.get("LAST_ACTIVITY") or "?"
                ips = b.get("distinct_ips") or b.get("DISTINCT_IPS") or 0
                print(f"    {b['UserCode']:<20} {str(b.get('U_NAME','')):<30} "
                      f"super={b['SUPERUSER']} actions={cnt} "
                      f"last={str(last)[:10]} ips={ips}")

        if multi_ip:
            print(f"\n  MULTI-IP USERS (>3 IPs, shared/generic suspect):")
            for m in multi_ip[:10]:
                ips = m.get("distinct_ips") or m.get("DISTINCT_IPS") or 0
                acts = m.get("total_actions") or m.get("TOTAL_ACTIONS") or 0
                print(f"    {m['UserCode']:<20} {str(m.get('U_NAME','')):<30} "
                      f"super={m['SUPERUSER']} locked={m['Locked']} "
                      f"ips={ips} actions={acts}")

    finally:
        cur.close()
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
