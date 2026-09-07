"""Export name maps used by the economic grouping (READ ONLY).

OSLP (salespersons) and OHEM (POS operators) referenced by the 268 explained
cases. Single source for display names so downstream grouping/metrics stay
deterministic without another HANA round-trip.

Evidence emitted: evidence/name_maps.json
"""
from __future__ import annotations

import json
from pathlib import Path

from modules.telchi.investigation.paths import EVIDENCE_ROOT

from modules.telchi.investigation.atomic.connection import connect
from modules.telchi.investigation.validation.credit_control.readonly import ReadOnlyConnection

HERE = Path(__file__).parent
EVIDENCE = EVIDENCE_ROOT / "credit_exception_economic" / "evidence"

TECHNICAL = {"soluone", "dms", "b1i", "manager", "workflow"}


def load_268() -> list[dict]:
    import json as _j
    classified = _j.loads((EVIDENCE_ROOT / "credit_exception" / "evidence" / "classified_cases.json")
                          .read_text(encoding="utf-8"))
    prior = _j.loads((EVIDENCE_ROOT / "credit_control" / "evidence" / "phase78_sale_credit_state.json")
                     .read_text(encoding="utf-8"))["all_overdue_sales"]
    prior_keys = {(s["cardcode"], s["docentry"]) for s in prior}
    return [x for x in classified
            if (x["cardcode"], x["doc_entry"]) in prior_keys and x["classification"] != "UNRESOLVED"]


def main() -> int:
    ex = load_268()
    slps = sorted({x["slpcode"] for x in ex})
    pos_ids = sorted({x.get("retail", {}).get("usuario_pos")
                      for x in ex if x.get("retail", {}).get("matched")
                      and x.get("retail", {}).get("usuario_pos")})

    conn, cur = connect()
    ro = ReadOnlyConnection(conn)
    c = ro.cursor()
    try:
        slp_map: dict[str, str] = {}
        if slps:
            ph = ",".join(["?"] * len(slps))
            c.execute(f'SELECT "SlpCode","SlpName" FROM "TELCHI"."OSLP" WHERE "SlpCode" IN ({ph})', slps)
            slp_map = {str(r[0]): r[1] for r in c.fetchall()}
        ohem_map: dict[str, dict] = {}
        if pos_ids:
            ph2 = ",".join(["?"] * len(pos_ids))
            c.execute(f'SELECT "empID","lastName","firstName","branch" FROM "TELCHI"."OHEM" WHERE "empID" IN ({ph2})', pos_ids)
            for emp_id, last, first, branch in c.fetchall():
                ohem_map[str(emp_id)] = {"last": last, "first": first, "branch": branch}
    finally:
        conn.rollback()
        conn.close()

    out = {
        "generated_from": "export_names.py (READ ONLY HANA)",
        "salespersons": slp_map,
        "pos_operators": ohem_map,
        "technical_users": sorted(TECHNICAL),
    }
    (EVIDENCE / "name_maps.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"salespersons": len(slp_map), "pos_operators": len(ohem_map)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())