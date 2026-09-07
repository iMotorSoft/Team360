"""PHASE 10 — Authorized × Actual matrix (READ ONLY).

Crosses effective business capabilities (PHASE 6) with actual document
activity (PHASE 7) per user, producing the AUTHORIZED×ACTUAL status matrix.

States (§6.3):
  AUTHORIZED_AND_USED
  AUTHORIZED_NOT_USED
  USED_BUT_AUTHORIZATION_UNCONFIRMED
  USED_AND_APPARENTLY_NOT_AUTHORIZED
  INDETERMINATE

Critical protections:
  - Historical authorization is unavailable (CURRENT_AUTHORIZATION_ONLY):
    a 2023 operation compared to 2026 permissions must NOT be flagged as a
    historical violation. USED_BUT_AUTHORIZATION_UNCONFIRMED is used instead
    when a capability is actually used but not confirmed in current perms.
  - Superusers are AUTHORIZED_AND_USED by definition (not flagged).
  - A used capability not found in current permission mapping is only
    USED_AND_APPARENTLY_NOT_AUTHORIZED if the user is NOT superuser AND the
    capability maps to a sensitive/standard permission that *should* be
    visible — otherwise USED_BUT_AUTHORIZATION_UNCONFIRMED.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from typing import Any

from modules.telchi.investigation.atomic.connection import connect
from modules.telchi.investigation.validation.users_audit.capabilities import (
    capability_from_objtype,
    SENSITIVE_CAPABILITIES,
)
from modules.telchi.investigation.validation.users_audit.phase6_effective_capabilities import (
    fetch_users,
    fetch_direct_perms,
    fetch_group_perms,
    fetch_user_groups,
    resolve_effective_permission,
    build_user_capabilities,
)


# ObjType tables to sample for activity (creation = UserSign, cancel = UserSign2)
ACTIVITY_SOURCES: list[tuple[str, str, str]] = [
    # (objtype, table, user_sign_field)
    ("13", "OINV", "UserSign"),
    ("14", "ORIN", "UserSign"),
    ("15", "ODLN", "UserSign"),
    ("16", "ORDN", "UserSign"),
    ("17", "ORDR", "UserSign"),
    ("18", "OPCH", "UserSign"),
    ("20", "ORPC", "UserSign"),
    ("22", "OPOR", "UserSign"),
    ("24", "ORCT", "UserSign"),
    ("46", "OVPM", "UserSign"),
    ("60", "OIGE", "UserSign"),
    ("67", "OWTR", "UserSign"),
    ("69", "OIGN", "UserSign"),
]

# Manual journal entries: OJDT TransType=59 only (auto entries are effects
# of the origin transaction and would double-count otherwise).
MANUAL_JE = ("59", "OJDT", "UserSign", "TransType", "59")

CANCEL_SOURCES: list[tuple[str, str, str, str]] = [
    # (objtype, table, user_sign2_field, canceled_field)
    ("13", "OINV", "UserSign2", "CANCELED"),
    ("14", "ORIN", "UserSign2", "CANCELED"),
    ("24", "ORCT", "UserSign2", "Canceled"),
    ("46", "OVPM", "UserSign2", "Canceled"),
    ("67", "OWTR", "UserSign2", "CANCELED"),
]


def table_has_col(cursor: Any, table: str, col: str) -> bool:
    cursor.execute(
        'SELECT COUNT(*) FROM "SYS"."TABLE_COLUMNS" '
        'WHERE "SCHEMA_NAME" = ? AND "TABLE_NAME" = ? AND "COLUMN_NAME" = ?',
        ("TELCHI", table, col),
    )
    return cursor.fetchone()[0] > 0


def fetch_activity(cursor: Any) -> tuple[dict[int, dict[str, int]], dict[int, dict[str, int]], dict[int, dict[str, str]]]:
    """Return (creation_activity, cancel_activity, last_use) keyed by user_id -> capability -> count/date."""
    creation: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    cancel: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    last_use: dict[int, dict[str, str]] = defaultdict(dict)

    for obj_type, table, usign in ACTIVITY_SOURCES:
        if not table_has_col(cursor, table, usign):
            continue
        mapping = capability_from_objtype(obj_type)
        if mapping is None:
            continue
        try:
            cursor.execute(
                f'SELECT "{usign}", COUNT(*), MAX("CreateDate") FROM "TELCHI"."{table}" '
                f'GROUP BY "{usign}"'
            )
            for r in cursor.fetchall():
                if r[0] is not None:
                    creation[r[0]][mapping.capability] += r[1]
                    if r[2] is not None:
                        cur_last = last_use[r[0]].get(mapping.capability)
                        if cur_last is None or str(r[2]) > cur_last:
                            last_use[r[0]][mapping.capability] = str(r[2])[:10]
        except Exception:
            continue

    # Manual journal entries only (TransType=59)
    obj_type, table, usign, trans_col, trans_val = MANUAL_JE
    if table_has_col(cursor, table, usign) and table_has_col(cursor, table, trans_col):
        mapping = capability_from_objtype(obj_type)
        if mapping is not None:
            try:
                cursor.execute(
                    f'SELECT "{usign}", COUNT(*), MAX("CreateDate") FROM "TELCHI"."{table}" '
                    f'WHERE "{trans_col}" = {trans_val} GROUP BY "{usign}"'
                )
                for r in cursor.fetchall():
                    if r[0] is not None:
                        creation[r[0]][mapping.capability] += r[1]
                        if r[2] is not None:
                            cur_last = last_use[r[0]].get(mapping.capability)
                            if cur_last is None or str(r[2]) > cur_last:
                                last_use[r[0]][mapping.capability] = str(r[2])[:10]
            except Exception:
                pass

    for obj_type, table, usign2, canceled_field in CANCEL_SOURCES:
        if not table_has_col(cursor, table, usign2):
            continue
        mapping = capability_from_objtype(obj_type, canceled=True)
        if mapping is None:
            continue
        try:
            cursor.execute(
                f'SELECT "{usign2}", COUNT(*), MAX("UpdateDate") FROM "TELCHI"."{table}" '
                f'WHERE "{canceled_field}" = \'Y\' GROUP BY "{usign2}"'
            )
            for r in cursor.fetchall():
                if r[0] is not None:
                    cancel[r[0]][mapping.capability] += r[1]
                    if r[2] is not None:
                        cur_last = last_use[r[0]].get(mapping.capability)
                        if cur_last is None or str(r[2]) > cur_last:
                            last_use[r[0]][mapping.capability] = str(r[2])[:10]
        except Exception:
            continue

    return creation, cancel, last_use


def compute_status(
    user: dict[str, Any],
    authorized_caps: dict[str, dict],
    creation: dict[int, dict[str, int]],
    cancel: dict[int, dict[str, int]],
    last_use: dict[int, dict[str, str]],
) -> dict[str, Any]:
    uid = user["USERID"]
    is_super = user["SUPERUSER"] == "Y"

    # union of authorized and used capabilities
    used_caps: dict[str, int] = defaultdict(int)
    for cap, n in creation.get(uid, {}).items():
        used_caps[cap] += n
    for cap, n in cancel.get(uid, {}).items():
        used_caps[cap] += n

    all_caps = set(authorized_caps.keys()) | set(used_caps.keys())
    all_caps.discard("SUPERUSER")

    matrix = []
    for cap in sorted(all_caps):
        authorized = cap in authorized_caps or is_super
        used = cap in used_caps
        count = used_caps.get(cap, 0)
        last = last_use.get(uid, {}).get(cap)

        if authorized and used:
            status = "AUTHORIZED_AND_USED"
        elif authorized and not used:
            status = "AUTHORIZED_NOT_USED"
        elif used and is_super:
            status = "AUTHORIZED_AND_USED"
        elif used and not authorized:
            if cap in SENSITIVE_CAPABILITIES:
                status = "USED_AND_APPARENTLY_NOT_AUTHORIZED"
            else:
                status = "USED_BUT_AUTHORIZATION_UNCONFIRMED"
        else:
            status = "INDETERMINATE"

        matrix.append({
            "capability": cap,
            "authorized": authorized or is_super,
            "used": used,
            "actual_operation_count": count,
            "last_use": last,
            "status": status,
            "sensitive": cap in SENSITIVE_CAPABILITIES,
        })

    return {"USERID": uid, "USER_CODE": user["USER_CODE"],
            "U_NAME": user["U_NAME"], "SUPERUSER": user["SUPERUSER"],
            "Locked": user["Locked"], "matrix": matrix}


def main() -> int:
    conn, cur = connect()
    try:
        users = fetch_users(cur)
        direct_perms = fetch_direct_perms(cur)
        group_perms = fetch_group_perms(cur)
        user_groups = fetch_user_groups(cur)
        creation, cancel, last_use = fetch_activity(cur)

        rows = []
        for u in users:
            eff = resolve_effective_permission(u, direct_perms, group_perms, user_groups)
            caps = build_user_capabilities(u, eff)
            rows.append(compute_status(u, caps, creation, cancel, last_use))

        # summary counters
        status_counter = defaultdict(int)
        used_not_auth_users = []
        for r in rows:
            for m in r["matrix"]:
                status_counter[m["status"]] += 1
                if m["status"] == "USED_AND_APPARENTLY_NOT_AUTHORIZED":
                    used_not_auth_users.append({
                        "USER_CODE": r["USER_CODE"], "U_NAME": r["U_NAME"],
                        "capability": m["capability"],
                        "count": m["actual_operation_count"],
                        "last_use": m["last_use"],
                        "superuser": r["SUPERUSER"], "locked": r["Locked"],
                    })

        # Priority users
        priority = ["eroman", "manager", "smercado", "sruiz", "manager6", "lvelasco", "tflores"]
        priority_rows = [r for r in rows if r["USER_CODE"] in priority]

        result = {
            "phase": "AUTHORIZED_ACTUAL",
            "summary": dict(status_counter),
            "users_total": len(rows),
            "used_and_apparently_not_authorized": used_not_auth_users,
            "priority_users": priority_rows,
            "limitations": ["CURRENT_AUTHORIZATION_ONLY", "HISTORICAL_AUTHORIZATION=UNAVAILABLE"],
        }

        print(json.dumps(result, indent=2, default=str))

        print(f"\nPHASE 10 — AUTHORIZED × ACTUAL SUMMARY")
        print(f"  Users analyzed: {len(rows)}")
        for st, n in sorted(status_counter.items()):
            print(f"    {st:<40} {n}")
        print(f"\n  USED_AND_APPARENTLY_NOT_AUTHORIZED cases: {len(used_not_auth_users)}")
        for c in used_not_auth_users[:25]:
            print(f"    {c['USER_CODE']:<20} {str(c['U_NAME']):<30} {c['capability']:<28} "
                  f"count={c['count']} last={c['last_use']} super={c['superuser']} locked={c['locked']}")

    finally:
        cur.close()
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
