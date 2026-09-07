"""Locate the SAP PermId(s) matching the Excel group pattern for credit
permissions, using the UGR1 group→PermId matrix (READ ONLY)."""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from modules.telchi.investigation.paths import EVIDENCE_ROOT

from modules.telchi.investigation.atomic.connection import connect

EVIDENCE = EVIDENCE_ROOT / "credit_control" / "evidence"

# Excel (documental) pattern per group for 'Confirmar desviación de línea de
# crédito': FULL in every mapped group except Almacenes(37) and Produccion(43).
FULL_GROUPS = {30, 38, 39, 40, 41, 42, 44, 46, 54}
RESTRICTED_GROUPS = {37, 43}


def load_matrix(cur) -> dict[int, dict[str, str]]:
    cur.execute('SELECT "GroupLink","PermId","Permission" FROM "TELCHI"."UGR1"')
    m: dict[int, dict[str, str]] = defaultdict(dict)
    for g, p, perm in cur.fetchall():
        if perm in ("F", "R", "V", "N"):
            m[g][p] = perm
    return m


def pattern_candidates(m):
    all_permids = sorted({p for g in m for p in m[g]})
    cands = []
    for permid in all_permids:
        if all(m.get(g, {}).get(permid) == "F" for g in FULL_GROUPS) and all(
            m.get(g, {}).get(permid) in ("N", None) for g in RESTRICTED_GROUPS
        ):
            cands.append(permid)
    return cands


def main() -> int:
    conn, cur = connect()
    try:
        m = load_matrix(cur)
        cands = pattern_candidates(m)
        detail = {str(p): {str(g): m.get(g, {}).get(p) for g in sorted(set(FULL_GROUPS) | set(RESTRICTED_GROUPS))} for p in cands}
        out = {
            "excel_pattern": {
                "permission": "Confirmar desviación de línea de crédito / Confirm Credit Line Deviation",
                "full_groups": sorted(FULL_GROUPS),
                "restricted_groups": sorted(RESTRICTED_GROUPS),
            },
            "candidate_perm_ids": [str(p) for p in cands],
            "candidate_count": len(cands),
            "detail": detail,
            "limitation": (
                "TELCHI.schema has no permission-description dictionary (OUPT holds only the "
                "Retail One addon tree). Exact PermId↔subject mapping is UNRESOLVED; the "
                "pattern identifies a family of credit-sensitive permissions whose group "
                "distribution matches the Excel documental matrix exactly."
            ),
        }
        (EVIDENCE / "perm_id_credit_pattern.json").write_text(
            json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        print("candidate PermIds (F in all groups except Almacenes/Produccion):", len(cands))
        print(sorted(cands))
        return 0
    finally:
        conn.rollback()
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
