"""PHASE 9 — Application origin real-data validation (READ ONLY).

Classifies OINV documents by channel using the explicit UDF markers and
reports distribution + reconciliation (no silent fanout).
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from typing import Any

from modules.telchi.investigation.atomic.connection import connect
from modules.telchi.investigation.validation.users_audit.application_origin import (
    classify_origin,
    Origin,
    Confidence,
)


def classify_documents(cursor: Any, table: str = "OINV", limit: int = 0) -> dict[str, Any]:
    limit_sql = f" LIMIT {limit}" if limit > 0 else ""
    cursor.execute(
        f'SELECT "DocEntry", "U_ORIGIN", "U_SO1_01RETAILONE", "Series", "UserSign" '
        f'FROM "TELCHI"."{table}"{limit_sql}'
    )
    cols = [d[0] for d in cursor.description]
    distribution: Counter = Counter()
    confidence_by_origin: Counter = Counter()
    samples: dict[str, list] = {}

    for r in cursor.fetchall():
        d = dict(zip(cols, r))
        c = classify_origin(d.get("U_ORIGIN"), d.get("U_SO1_01RETAILONE"))
        origin = c.application_origin.value
        distribution[origin] += 1
        confidence_by_origin[(origin, c.confidence.value)] += 1
        if len(samples.get(origin, [])) < 3:
            samples.setdefault(origin, []).append({
                "DocEntry": d["DocEntry"],
                "U_ORIGIN": d["U_ORIGIN"],
                "U_SO1_01RETAILONE": d["U_SO1_01RETAILONE"],
                "Series": d["Series"],
                "confidence": c.confidence.value,
            })

    total = sum(distribution.values())
    return {
        "table": table,
        "total_classified": total,
        "distribution": dict(distribution),
        "confidence_by_origin": {
            f"{o}@{conf}": n for (o, conf), n in sorted(confidence_by_origin.items())
        },
        "samples": samples,
    }


def channel_by_user(cursor: Any, table: str = "OINV") -> list[dict[str, Any]]:
    cursor.execute(
        f'''SELECT U."USER_CODE", O."U_ORIGIN", O."U_SO1_01RETAILONE", COUNT(*) AS cnt
            FROM "TELCHI"."{table}" O
            LEFT JOIN "TELCHI"."OUSR" U ON U."USERID" = O."UserSign"
            GROUP BY U."USER_CODE", O."U_ORIGIN", O."U_SO1_01RETAILONE"
            ORDER BY cnt DESC'''
    )
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, r)) for r in cursor.fetchall()]


def main() -> int:
    conn, cur = connect()
    try:
        result = classify_documents(cur, "OINV")
        by_user = channel_by_user(cur, "OINV")

        # per-user channel profile
        user_channels: dict[str, Counter] = {}
        for r in by_user:
            ucode = r["USER_CODE"] or "?"
            origin = r["U_ORIGIN"]
            retail = r["U_SO1_01RETAILONE"]
            c = classify_origin(origin, retail).application_origin.value
            cnt = r.get("cnt") or r.get("CNT") or 0
            user_channels.setdefault(ucode, Counter())[c] += cnt

        # users spanning multiple channels
        multi_channel = []
        for ucode, chans in user_channels.items():
            if len(chans) > 1:
                multi_channel.append({"user": ucode, "channels": dict(chans)})

        result["multi_channel_users"] = multi_channel

        print(json.dumps(result, indent=2, default=str))
        print(f"\nPHASE 9 — OINV channel distribution:")
        for k, v in result["distribution"].items():
            print(f"  {k:<16} {v:>10} ({100*v/result['total_classified']:.1f}%)")
        print(f"\n  Multi-channel users: {len(multi_channel)}")
        for m in multi_channel[:10]:
            print(f"    {m['user']:<20} {m['channels']}")

    finally:
        cur.close()
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
