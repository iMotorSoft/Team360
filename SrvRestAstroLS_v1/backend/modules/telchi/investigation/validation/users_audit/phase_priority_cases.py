"""Priority user cases — post-block activity, corrupted dates, multi-IP (READ ONLY).

Investigates per §9-§11:
  - smercado / sruiz: post-block activity classification
  - manager6: corrupted date (3916-10-14) root cause
  - manager: 45 IPs -> account classification
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from typing import Any

from modules.telchi.investigation.atomic.connection import connect


def post_block_analysis(cursor: Any, user_code: str) -> dict[str, Any]:
    cursor.execute(
        '''SELECT "USERID", "USER_CODE", "U_NAME", "Locked", "updateDate",
                  "SUPERUSER", "createDate"
           FROM "TELCHI"."OUSR" WHERE "USER_CODE"=?''',
        (user_code,),
    )
    u = cursor.fetchone()
    if u is None:
        return {"user": user_code, "error": "not_found"}

    uid = u[0]
    lock_update = str(u[4])[:10] if u[4] else None

    # events after updateDate
    cursor.execute(
        '''SELECT "Action", "ClientIP", "Date", "Time", "SessionID", "ProcName", "Source"
           FROM "TELCHI"."USR5" WHERE "UserCode"=? AND "Date" > ?
           ORDER BY "Date", "Time"''',
        (user_code, lock_update),
    )
    cols = [d[0] for d in cursor.description]
    events = [dict(zip(cols, r)) for r in cursor.fetchall()]

    actions = Counter(e["Action"] for e in events)
    ips = Counter(e["ClientIP"] for e in events)

    return {
        "user": user_code,
        "userid": uid,
        "locked": u[2],
        "update_date": lock_update,
        "superuser": u[5],
        "post_block_events": len(events),
        "actions": dict(actions),
        "ips": dict(ips),
        "first_event": str(events[0]["Date"])[:10] if events else None,
        "last_event": str(events[-1]["Date"])[:10] if events else None,
        "sample_events": events[:5],
    }


def manager6_date_analysis(cursor: Any) -> dict[str, Any]:
    cursor.execute(
        '''SELECT "Date", "Time", "Action", "ClientIP", COUNT(*)
           FROM "TELCHI"."USR5" WHERE "UserCode"='manager6'
           GROUP BY "Date", "Time", "Action", "ClientIP"
           ORDER BY "Date" DESC LIMIT 20'''
    )
    cols = [d[0] for d in cursor.description]
    return {
        "user": "manager6",
        "rows": [dict(zip(cols, r)) for r in cursor.fetchall()],
    }


def manager_ip_analysis(cursor: Any) -> dict[str, Any]:
    cursor.execute(
        '''SELECT "ClientIP", COUNT(*) AS cnt, MIN("Date") AS first_seen, MAX("Date") AS last_seen
           FROM "TELCHI"."USR5" WHERE "UserCode"='manager'
           GROUP BY "ClientIP" ORDER BY cnt DESC'''
    )
    cols = [d[0] for d in cursor.description]
    ips = [dict(zip(cols, r)) for r in cursor.fetchall()]

    # date range of manager activity
    cursor.execute(
        'SELECT MIN("Date"), MAX("Date") FROM "TELCHI"."USR5" WHERE "UserCode"=\'manager\''
    )
    mn, mx = cursor.fetchone()

    return {
        "user": "manager",
        "distinct_ips": len(ips),
        "date_min": str(mn)[:10] if mn else None,
        "date_max": str(mx)[:10] if mx else None,
        "ips": ips,
    }


def main() -> int:
    conn, cur = connect()
    try:
        results = {
            "phase": "PRIORITY_CASES",
            "smercado": post_block_analysis(cur, "smercado"),
            "sruiz": post_block_analysis(cur, "sruiz"),
            "manager6": manager6_date_analysis(cur),
            "manager": manager_ip_analysis(cur),
        }
        print(json.dumps(results, indent=2, default=str))

        print(f"\nPRIORITY CASES")
        for k in ("smercado", "sruiz"):
            r = results[k]
            print(f"\n  {k}: locked={r.get('locked')} update={r.get('update_date')} "
                  f"post_block_events={r.get('post_block_events')}")
            print(f"    actions={r.get('actions')}")
            print(f"    ips={r.get('ips')}")

        m6 = results["manager6"]
        print(f"\n  manager6: {len(m6['rows'])} distinct event rows")
        for r in m6["rows"][:5]:
            print(f"    date={r.get('Date')} action={r.get('Action')} ip={r.get('ClientIP')}")

        mg = results["manager"]
        print(f"\n  manager: {mg['distinct_ips']} IPs, {mg['date_min']}..{mg['date_max']}")
        for ip in mg["ips"][:10]:
            cnt = ip.get("cnt") or ip.get("CNT") or 0
            fs = ip.get("first_seen") or ip.get("FIRST_SEEN")
            ls = ip.get("last_seen") or ip.get("LAST_SEEN")
            print(f"    {str(ip.get('ClientIP')):<40} cnt={cnt} "
                  f"{str(fs)[:10]}..{str(ls)[:10]}")

    finally:
        cur.close()
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
