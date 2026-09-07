"""PHASE 1 — CATALOG DISCOVERY for Telchi SAP users/roles/authorizations.

READ ONLY. Never writes to HANA. Inspects SYS.TABLES, SYS.VIEWS and
SYS.TABLE_COLUMNS to inventory every candidate table related to:
  - users (OUSR, USR*)
  - employees (OHEM, HEM*)
  - salespersons (OSLP, SLP*)
  - branches (OUBR, UBR*)
  - roles / groups (OUGR, UGR*, UPT*)
  - authorizations / permissions
  - licenses
  - any other SAP B1 administration table

Output: structured report of discovered tables, columns and row counts.
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field
from typing import Any

from modules.telchi.investigation.atomic.connection import connect, table_columns


@dataclass(frozen=True)
class CatalogEntry:
    schema: str
    object_name: str
    object_type: str
    row_count: int | None
    column_count: int
    columns: list[str]
    meaning_inferred: str = ""
    meaning_validated: str = ""
    join_keys: list[str] = field(default_factory=list)
    evidence: str = ""


USER_ROLE_PATTERNS = (
    "OUSR", "OHEM", "OSLP", "OUBR", "OUGR",
    "USR", "UGR", "UPT", "HEM", "SLP", "UBR",
    "USER", "ROLE", "PERM", "AUTH", "GRNT",
    "MENU", "FORM", "MODULE", "LICENSE",
    "OADM", "ADP", "AIB",
    "RDSP", "RDBG",
    "CSP",
)

EXCLUDE_PREFIXES = ("@",)


def discover_tables(cursor: Any, schema: str) -> list[tuple[str, str, str]]:
    cursor.execute(
        "SELECT TABLE_NAME, 'TABLE' FROM SYS.TABLES WHERE SCHEMA_NAME = ? "
        "UNION ALL "
        "SELECT VIEW_NAME, 'VIEW' FROM SYS.VIEWS WHERE SCHEMA_NAME = ?",
        (schema, schema),
    )
    return [(r[0], r[1]) for r in cursor.fetchall()]


def is_candidate(name: str) -> bool:
    if any(name.startswith(p) for p in EXCLUDE_PREFIXES):
        return False
    upper = name.upper()
    for pat in USER_ROLE_PATTERNS:
        if upper == pat or upper.startswith(pat) and len(upper) > len(pat) and upper[len(pat):].isdigit():
            return True
        if upper.startswith(pat) and len(upper) > len(pat) and upper[len(pat):len(pat)+1] in ("_", ""):
            if pat in ("OUSR", "OHEM", "OSLP", "OUBR", "OUGR", "OADM"):
                return upper == pat
    for pat in USER_ROLE_PATTERNS:
        if pat in upper:
            return True
    return False


def count_rows(cursor: Any, schema: str, table: str, obj_type: str) -> int | None:
    try:
        q = f'SELECT COUNT(*) FROM "{schema}"."{table}"'
        cursor.execute(q)
        row = cursor.fetchone()
        return row[0] if row else None
    except Exception:
        return None


def get_columns(cursor: Any, schema: str, table: str) -> list[str]:
    try:
        return table_columns(schema, table)
    except Exception:
        return []


def infer_meaning(name: str, columns: list[str]) -> str:
    upper = name.upper()
    cols_upper = [c.upper() for c in columns]
    if upper == "OUSR":
        return "SAP B1 users master table"
    if upper == "OHEM":
        return "SAP B1 employees master table"
    if upper == "OSLP":
        return "SAP B1 sales persons master table"
    if upper == "OUBR":
        return "SAP B1 branches master table"
    if upper == "OUGR":
        return "SAP B1 user groups"
    if upper == "OADM":
        return "SAP B1 administration configuration"
    if "USER" in upper and "SIGN" in " ".join(cols_upper):
        return "User-related table with UserSign references"
    if upper.startswith("USR"):
        return f"SAP B1 user sub-table ({name})"
    if upper.startswith("HEM"):
        return f"SAP B1 employee sub-table ({name})"
    if upper.startswith("SLP"):
        return f"SAP B1 salesperson sub-table ({name})"
    if upper.startswith("UBR"):
        return f"SAP B1 branch sub-table ({name})"
    if upper.startswith("UGR"):
        return f"SAP B1 user group sub-table ({name})"
    if upper.startswith("UPT"):
        return f"SAP B1 authorization/permission sub-table ({name})"
    if "AUTH" in upper or "PERM" in upper:
        return "Authorization/permissions related"
    if "ROLE" in upper:
        return "Role related"
    if "MENU" in upper:
        return "Menu permissions related"
    if "LICENSE" in upper or "LIC" in upper:
        return "License related"
    return "Candidate — needs manual validation"


def run_discovery(schema: str = "TELCHI") -> dict[str, Any]:
    conn, cur = connect()
    try:
        all_tables = discover_tables(cur, schema)
        candidates = [(n, t) for n, t in all_tables if is_candidate(n)]
        candidates.sort(key=lambda x: x[0])

        entries: list[dict[str, Any]] = []
        for name, obj_type in candidates:
            cols = get_columns(cur, schema, name)
            rc = count_rows(cur, schema, name, obj_type)
            meaning = infer_meaning(name, cols)
            entry = {
                "schema": schema,
                "object_name": name,
                "object_type": obj_type,
                "row_count": rc,
                "column_count": len(cols),
                "columns": cols,
                "meaning_inferred": meaning,
            }
            entries.append(entry)

        total_tables = sum(1 for _, t in all_tables if t == "TABLE")
        total_views = sum(1 for _, t in all_tables if t == "VIEW")

        return {
            "phase": "CATALOG_DISCOVERY",
            "schema": schema,
            "total_tables_in_schema": total_tables,
            "total_views_in_schema": total_views,
            "total_objects": len(all_tables),
            "candidates_found": len(entries),
            "entries": entries,
        }
    finally:
        cur.close()
        conn.close()


def main() -> int:
    try:
        result = run_discovery()
    except Exception as exc:
        print(f"CATALOG_DISCOVERY_BLOCKED: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(result, indent=2, default=str))
    print(f"\nSUMMARY: {result['candidates_found']} candidates "
          f"from {result['total_objects']} total objects "
          f"in schema {result['schema']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
