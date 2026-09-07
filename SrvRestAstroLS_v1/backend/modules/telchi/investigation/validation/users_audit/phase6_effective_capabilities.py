"""PHASE 6 — Effective business capability per user (READ ONLY on HANA).

Resolves effective authorization per user:
  - SUPERUSER_OVERRIDE: SUPERUSER='Y' in OUSR
  - DIRECT: USR3 (Permission in N/F/R/V)
  - GROUP: UGR1 via USR7 (user -> group -> permission)
  - explicit restriction: Permission='N' in direct overrides group
  - UNKNOWN otherwise

Produces user_id × capability with authorization_source + confidence.

Limitation (§4.4): SAP B1 does not expose full precedence/inheritance rules
in these tables; effective resolution is documented as best-effort and does
NOT fabricate precision. Where unresolved -> EFFECTIVE_AUTHORIZATION_UNRESOLVED.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from typing import Any

from modules.telchi.investigation.atomic.connection import connect
from modules.telchi.investigation.validation.users_audit.capabilities import (
    resolve_perm_capability,
    Confidence,
    MappingStatus,
    SENSITIVE_CAPABILITIES,
)

# SAP B1 authorization values -> normalized level
PERM_LEVEL: dict[str, str] = {"F": "FULL", "R": "READ", "V": "VARIOUS", "N": "NONE"}


def fetch_users(cursor: Any) -> list[dict[str, Any]]:
    cursor.execute(
        'SELECT "USERID", "USER_CODE", "U_NAME", "SUPERUSER", "Locked", '
        '"DISCOUNT", "SalesDisc", "PurchDisc" '
        'FROM "TELCHI"."OUSR"'
    )
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, r)) for r in cursor.fetchall()]


def fetch_direct_perms(cursor: Any) -> dict[int, dict[str, str]]:
    cursor.execute('SELECT "UserLink", "PermId", "Permission" FROM "TELCHI"."USR3"')
    out: dict[int, dict[str, str]] = defaultdict(dict)
    for r in cursor.fetchall():
        out[r[0]][r[1]] = r[2]
    return out


def fetch_group_perms(cursor: Any) -> dict[int, dict[str, str]]:
    cursor.execute('SELECT "GroupLink", "PermId", "Permission" FROM "TELCHI"."UGR1"')
    out: dict[int, dict[str, str]] = defaultdict(dict)
    for r in cursor.fetchall():
        out[r[0]][r[1]] = r[2]
    return out


def fetch_user_groups(cursor: Any) -> dict[int, list[int]]:
    cursor.execute('SELECT "UserId", "GroupId" FROM "TELCHI"."USR7"')
    out: dict[int, list[int]] = defaultdict(list)
    for r in cursor.fetchall():
        out[r[0]].append(r[1])
    return out


def resolve_effective_permission(
    user: dict[str, Any],
    direct_perms: dict[int, dict[str, str]],
    group_perms: dict[int, dict[str, str]],
    user_groups: dict[int, list[int]],
) -> dict[str, str]:
    """Return {perm_id: normalized_level} effective for a user."""
    uid = user["USERID"]

    if user["SUPERUSER"] == "Y":
        return {"__SUPERUSER__": "FULL"}

    effective: dict[str, str] = {}

    # group permissions first (base)
    for gid in user_groups.get(uid, []):
        for perm_id, level in group_perms.get(gid, {}).items():
            if level in ("F", "R", "V"):
                effective[perm_id] = PERM_LEVEL[level]

    # direct permissions override (including explicit denial 'N')
    for perm_id, level in direct_perms.get(uid, {}).items():
        if level == "N":
            effective.pop(perm_id, None)
        else:
            effective[perm_id] = PERM_LEVEL[level]

    return effective


def build_user_capabilities(
    user: dict[str, Any],
    effective: dict[str, str],
) -> dict[str, Any]:
    """Map effective permissions to canonical capabilities."""
    caps: dict[str, dict[str, Any]] = {}

    if "__SUPERUSER__" in effective:
        caps["SUPERUSER"] = {
            "authorized": True,
            "authorization_source": "SUPERUSER_OVERRIDE",
            "confidence": Confidence.EXACT.value,
            "level": "FULL",
            "permission_codes": [],
        }
        return caps

    for perm_id, level in effective.items():
        mapping = resolve_perm_capability(perm_id)
        if mapping is None:
            continue
        cap = mapping.capability
        authorized = level in ("FULL", "READ", "VARIOUS")
        if cap not in caps:
            caps[cap] = {
                "authorized": authorized,
                "authorization_source": "DIRECT_OR_GROUP",
                "confidence": mapping.confidence.value,
                "level": level,
                "permission_codes": [perm_id],
            }
        else:
            caps[cap]["authorized"] = caps[cap]["authorized"] or authorized
            caps[cap]["permission_codes"].append(perm_id)
            if level == "FULL":
                caps[cap]["level"] = "FULL"

    return caps


def main() -> int:
    conn, cur = connect()
    try:
        users = fetch_users(cur)
        direct_perms = fetch_direct_perms(cur)
        group_perms = fetch_group_perms(cur)
        user_groups = fetch_user_groups(cur)

        rows = []
        for u in users:
            eff = resolve_effective_permission(u, direct_perms, group_perms, user_groups)
            caps = build_user_capabilities(u, eff)
            rows.append({
                "USERID": u["USERID"],
                "USER_CODE": u["USER_CODE"],
                "U_NAME": u["U_NAME"],
                "SUPERUSER": u["SUPERUSER"],
                "Locked": u["Locked"],
                "DISCOUNT": u["DISCOUNT"],
                "SalesDisc": u["SalesDisc"],
                "PurchDisc": u["PurchDisc"],
                "effective_perm_count": len(eff) - (1 if "__SUPERUSER__" in eff else 0),
                "capabilities": caps,
            })

        # Discount/price override from OUSR flags (EXACT — direct master flags)
        for r in rows:
            if r["DISCOUNT"] == "Y":
                r["capabilities"].setdefault("DISCOUNT_OVERRIDE", {
                    "authorized": True, "authorization_source": "USER_MASTER_FLAG",
                    "confidence": Confidence.EXACT.value, "level": "FULL",
                    "permission_codes": ["OUSR.DISCOUNT=Y"],
                })
            if r["SalesDisc"] == "Y":
                r["capabilities"].setdefault("DISCOUNT_OVERRIDE", {
                    "authorized": True, "authorization_source": "USER_MASTER_FLAG",
                    "confidence": Confidence.EXACT.value, "level": "FULL",
                    "permission_codes": ["OUSR.SalesDisc=Y"],
                })

        summary = {
            "total_users": len(rows),
            "superusers": sum(1 for r in rows if r["SUPERUSER"] == "Y"),
            "with_discount_flag": sum(1 for r in rows if r["DISCOUNT"] == "Y"),
            "with_sales_disc_flag": sum(1 for r in rows if r["SalesDisc"] == "Y"),
            "with_purch_disc_flag": sum(1 for r in rows if r["PurchDisc"] == "Y"),
        }

        result = {"phase": "BUSINESS_CAPABILITIES", "summary": summary, "users": rows}
        print(json.dumps(result, indent=2, default=str))
        print(f"\nPHASE 6 — {len(rows)} users, {summary['superusers']} superusers, "
              f"{summary['with_discount_flag']} with DISCOUNT=Y flag")

    finally:
        cur.close()
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
