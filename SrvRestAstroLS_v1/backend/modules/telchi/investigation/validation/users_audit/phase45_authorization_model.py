"""PHASE 4+5 — ROLES / GROUPS / AUTHORIZATION MODEL (READ ONLY).

Extracts and validates:
  - Permission tree (OUPT) — hierarchy of all SAP B1 permissions
  - User groups (OUGR) — group definitions
  - User→Group assignments (USR7) — which users belong to which groups
  - Group permissions (UGR1) — what permissions each group has
  - User direct permissions (USR3) — direct user-level permissions
  - Employee roles (HEM6) — employee role assignments
  - Effective permission resolution per user (direct + inherited via group)
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from typing import Any

from modules.telchi.investigation.atomic.connection import connect


def fetch_permission_tree(cursor: Any) -> list[dict[str, Any]]:
    cursor.execute(
        'SELECT "AbsId", "Name", "Options", "FathId", "VisOrder", '
        '"Levels", "IsItem", "Action" FROM "TELCHI"."OUPT" ORDER BY "AbsId"'
    )
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, r)) for r in cursor.fetchall()]


def fetch_user_groups(cursor: Any) -> list[dict[str, Any]]:
    cursor.execute(
        'SELECT "GroupId", "GroupName", "GroupDec", "Allowences", '
        '"GroupType" FROM "TELCHI"."OUGR" ORDER BY "GroupId"'
    )
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, r)) for r in cursor.fetchall()]


def fetch_user_group_assignments(cursor: Any) -> list[dict[str, Any]]:
    cursor.execute(
        'SELECT "UserId", "GroupId", "Category", "StartDate", "DueDate" '
        'FROM "TELCHI"."USR7" ORDER BY "UserId", "GroupId"'
    )
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, r)) for r in cursor.fetchall()]


def fetch_group_permissions(cursor: Any) -> list[dict[str, Any]]:
    cursor.execute(
        'SELECT "GroupLink", "PermId", "Permission" FROM "TELCHI"."UGR1"'
    )
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, r)) for r in cursor.fetchall()]


def fetch_user_direct_permissions(cursor: Any) -> list[dict[str, Any]]:
    cursor.execute(
        'SELECT "UserLink", "PermId", "Permission" FROM "TELCHI"."USR3"'
    )
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, r)) for r in cursor.fetchall()]


def fetch_employee_roles(cursor: Any) -> list[dict[str, Any]]:
    cursor.execute(
        'SELECT "empID", "roleID" FROM "TELCHI"."HEM6"'
    )
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, r)) for r in cursor.fetchall()]


def build_permission_map(perm_tree: list[dict]) -> dict[int, dict]:
    return {p["AbsId"]: p for p in perm_tree}


def resolve_effective_permissions(
    user_id: int,
    is_superuser: bool,
    direct_perms: dict[int, list[dict]],
    group_assignments: dict[int, list[dict]],
    group_perms: dict[int, list[dict]],
) -> dict[str, Any]:
    if is_superuser:
        return {
            "source": "SUPERUSER",
            "permission_count": -1,
            "note": "Superusers have all permissions by definition",
        }

    perms: dict[int, str] = {}

    for p in direct_perms.get(user_id, []):
        perm_id = p["PermId"]
        if perm_id not in perms or p["Permission"] == "Y":
            perms[perm_id] = p["Permission"]

    for assignment in group_assignments.get(user_id, []):
        group_id = assignment["GroupId"]
        for p in group_perms.get(group_id, []):
            perm_id = p["PermId"]
            if perm_id not in perms or p["Permission"] == "Y":
                perms[perm_id] = p["Permission"]

    allowed = sum(1 for v in perms.values() if v == "Y")
    denied = sum(1 for v in perms.values() if v == "N")
    return {
        "source": "DIRECT+GROUP",
        "permission_count": len(perms),
        "allowed": allowed,
        "denied": denied,
        "permissions": perms,
    }


SENSITIVE_PERM_IDS: dict[int, str] = {}


def identify_sensitive_permissions(perm_map: dict[int, dict]) -> dict[int, str]:
    sensitive_keywords = {
        "cancel": "DOCUMENT_CANCEL",
        "anular": "DOCUMENT_CANCEL",
        "price": "PRICE_OVERRIDE",
        "precio": "PRICE_OVERRIDE",
        "discount": "DISCOUNT_OVERRIDE",
        "descuento": "DISCOUNT_OVERRIDE",
        "payment": "PAYMENT_OPERATION",
        "pago": "PAYMENT_OPERATION",
        "cobro": "PAYMENT_OPERATION",
        "credit note": "CREDIT_NOTE_OPERATION",
        "nota de": "CREDIT_NOTE_OPERATION",
        "stock": "STOCK_OPERATION",
        "inventar": "STOCK_OPERATION",
        "warehouse": "WAREHOUSE_OPERATION",
        "almac": "WAREHOUSE_OPERATION",
        "transfer": "TRANSFER_OPERATION",
        "transferencia": "TRANSFER_OPERATION",
        "purchase": "PURCHASE_OPERATION",
        "compra": "PURCHASE_OPERATION",
        "production": "PRODUCTION_OPERATION",
        "producci": "PRODUCTION_OPERATION",
        "journal": "JOURNAL_ENTRY",
        "asiento": "JOURNAL_ENTRY",
        "accounting": "ACCOUNTING_OPERATION",
        "contab": "ACCOUNTING_OPERATION",
        "user": "USER_ADMIN",
        "usuario": "USER_ADMIN",
        "authorization": "AUTH_ADMIN",
        "autorizaci": "AUTH_ADMIN",
        "master data": "MASTER_DATA",
        "maestro": "MASTER_DATA",
        "superuser": "SUPERUSER_CAP",
    }
    result = {}
    for abs_id, perm in perm_map.items():
        name_lower = (perm.get("Name") or "").lower()
        for keyword, capability in sensitive_keywords.items():
            if keyword in name_lower:
                result[abs_id] = capability
                break
    return result


def main() -> int:
    conn, cur = connect()
    try:
        perm_tree = fetch_permission_tree(cur)
        user_groups = fetch_user_groups(cur)
        user_group_assignments = fetch_user_group_assignments(cur)
        group_permissions = fetch_group_permissions(cur)
        user_direct_perms = fetch_user_direct_permissions(cur)
        employee_roles = fetch_employee_roles(cur)

        perm_map = build_permission_map(perm_tree)
        sensitive_perms = identify_sensitive_permissions(perm_map)

        group_assignments_by_user: dict[int, list[dict]] = defaultdict(list)
        for a in user_group_assignments:
            group_assignments_by_user[a["UserId"]].append(a)

        group_perms_by_group: dict[int, list[dict]] = defaultdict(list)
        for p in group_permissions:
            group_perms_by_group[p["GroupLink"]].append(p)

        direct_perms_by_user: dict[int, list[dict]] = defaultdict(list)
        for p in user_direct_perms:
            direct_perms_by_user[p["UserLink"]].append(p)

        users_with_groups = len(group_assignments_by_user)
        users_with_direct_perms = len(direct_perms_by_user)

        perm_values = Counter()
        for p in group_permissions:
            perm_values[p["Permission"]] += 1
        for p in user_direct_perms:
            perm_values[p["Permission"]] += 1

        group_perm_counts = {
            g["GroupId"]: len(group_perms_by_group[g["GroupId"]])
            for g in user_groups
        }

        result = {
            "phase": "AUTHORIZATION_MODEL",
            "permission_tree": {
                "total_permissions": len(perm_tree),
                "items": sum(1 for p in perm_tree if p["IsItem"] == "Y"),
                "categories": sum(1 for p in perm_tree if p["IsItem"] != "Y"),
                "max_levels": max((p["Levels"] for p in perm_tree), default=0),
            },
            "user_groups": {
                "total_groups": len(user_groups),
                "groups": [
                    {
                        "GroupId": g["GroupId"],
                        "GroupName": g["GroupName"],
                        "GroupType": g["GroupType"],
                        "permission_count": group_perm_counts.get(g["GroupId"], 0),
                    }
                    for g in user_groups
                ],
            },
            "user_group_assignments": {
                "total_assignments": len(user_group_assignments),
                "users_with_groups": users_with_groups,
            },
            "group_permissions": {
                "total_entries": len(group_permissions),
                "permission_value_distribution": dict(perm_values),
            },
            "user_direct_permissions": {
                "total_entries": len(user_direct_perms),
                "users_with_direct_perms": users_with_direct_perms,
            },
            "employee_roles": {
                "total_assignments": len(employee_roles),
                "distinct_roles": len(set(r["roleID"] for r in employee_roles)),
            },
            "sensitive_permissions_identified": {
                "count": len(sensitive_perms),
                "capabilities": sorted(set(sensitive_perms.values())),
                "sample": [
                    {
                        "AbsId": abs_id,
                        "Name": perm_map[abs_id]["Name"],
                        "Capability": cap,
                    }
                    for abs_id, cap in list(sensitive_perms.items())[:30]
                ],
            },
        }

        print(json.dumps(result, indent=2, default=str))

        print(f"\n{'='*60}")
        print("PHASE 4+5 — AUTHORIZATION MODEL SUMMARY")
        print(f"{'='*60}")
        print(f"  Permission tree nodes:       {len(perm_tree)}")
        print(f"  Permission items (leaves):   {sum(1 for p in perm_tree if p['IsItem'] == 'Y')}")
        print(f"  User groups:                 {len(user_groups)}")
        print(f"  User→Group assignments:      {len(user_group_assignments)}")
        print(f"  Users with group membership: {users_with_groups}")
        print(f"  Group permission entries:    {len(group_permissions)}")
        print(f"  User direct perm entries:    {len(user_direct_perms)}")
        print(f"  Users with direct perms:     {users_with_direct_perms}")
        print(f"  Employee role assignments:   {len(employee_roles)}")
        print(f"  Sensitive perm IDs found:    {len(sensitive_perms)}")
        print(f"  Sensitive capabilities:      {sorted(set(sensitive_perms.values()))}")

    finally:
        cur.close()
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
