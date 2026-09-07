"""Structure discovery for the credit-exception cycle (READ ONLY).

Dumps physical columns (SELECT * LIMIT 0) for the P0 tables and related
document-chain tables. Evidence written to structure_probe.json.
"""
from __future__ import annotations

import json
from pathlib import Path

from modules.telchi.investigation.paths import EVIDENCE_ROOT

from modules.telchi.investigation.atomic.connection import connect

HERE = Path(__file__).parent
EVIDENCE = EVIDENCE_ROOT / "credit_exception" / "evidence"

TABLES = [
    "@SO1_01LOGAUTORIZA",   # Retail One authorization log (P0)
    "@SO1_01VENTA",         # Retail One sale header
    "@SO1_01VENTADETALLE",  # Retail One sale detail
    "ORDR", "RDR1",         # sales orders
    "ODLN", "DLN1",         # deliveries
    "ORIN", "RIN1",         # A/R credit notes
    "RCT2",                 # payment allocation lines
    "ITR1",                 # reconciliation lines
    "OITR",                 # reconciliation headers
    "INV6",                 # invoice installments (if exists)
    "OCTG",                 # payment terms
    "OQUT",                 # quotations
    "ODRF",                 # down payment invoices (if exists)
]


def main() -> int:
    conn, cur = connect()
    try:
        out: dict = {}
        for t in TABLES:
            try:
                cur.execute(f'SELECT * FROM "TELCHI"."{t}" LIMIT 0')
                cols = [d[0] for d in cur.description]
                out[t] = {"exists": True, "columns": cols, "n": len(cols)}
            except Exception as e:  # noqa: BLE001
                out[t] = {"exists": False, "error": str(e)[:200]}
        # row counts (cheap-ish for small tables only)
        for t in ["@SO1_01LOGAUTORIZA", "@SO1_01VENTA", "OCTG", "RCT2", "ITR1", "OITR", "INV6"]:
            if out.get(t, {}).get("exists"):
                try:
                    cur.execute(f'SELECT COUNT(*) FROM "TELCHI"."{t}"')
                    out[t]["rowcount"] = cur.fetchone()[0]
                except Exception as e:  # noqa: BLE001
                    out[t]["rowcount_error"] = str(e)[:120]
        EVIDENCE.mkdir(parents=True, exist_ok=True)
        (EVIDENCE / "structure_probe.json").write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
        for t, info in out.items():
            print(f"{t:28s} exists={info.get('exists')} cols={info.get('n')} rows={info.get('rowcount')}")
        return 0
    finally:
        conn.rollback()
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())