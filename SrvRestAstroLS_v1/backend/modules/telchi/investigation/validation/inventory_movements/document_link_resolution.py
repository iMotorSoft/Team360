#!/usr/bin/env python3
"""Document-link resolution: test which SAP header table each OINM TransType's BASE_REF resolves to."""
from __future__ import annotations

import json
import os
import shlex
import sys
from pathlib import Path

from modules.telchi.investigation.paths import SECRET_ROOT

from hdbcli import dbapi

ROOT = Path(__file__).resolve().parents[2]
HANA_ENV = SECRET_ROOT / "sap" / "hana.env"


def main() -> int:
    env = {}
    for line in HANA_ENV.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        k, _, v = line.partition("=")
        env[k] = shlex.split(v, posix=True)[0]

    conn = dbapi.connect(
        address=os.environ.get("HANA_HOST", "127.0.0.1"),
        port=int(os.environ.get("HANA_PORT", "30015")),
        user=os.environ.get("HANA_USER", env["TELCHI_SAP_HANA_USER"]),
        password=os.environ.get("HANA_PASSWORD", env["TELCHI_SAP_HANA_PASSWORD"]),
        currentSchema="TELCHI",
        encrypt="false",
    )
    cur = conn.cursor()

    # candidate header tables per transtype (hypotheses to test, not conclusions)
    tests = {
        13: ["OINV"],
        14: ["ORIN"],
        15: ["ODLN", "OINV"],
        16: ["ORPD", "OPQT", "OPCH"],
        19: ["OQUT", "ORDR", "OINV"],
        20: ["OPCH", "OPDN", "OIGE", "ORPD"],
        21: ["OQUT", "ORDR", "OIGN", "OPCH"],
        59: ["ORPC", "OMTC", "OWTR"],
        60: ["ORCT", "OMTC", "OWTR"],
        67: ["OWTR", "OWOR", "OIGN", "OIGE"],
        69: ["OWTR", "OMTC", "ODLN"],
        162: ["OWTR", "OMTC"],
        202: ["OWTR", "OMTC", "OIGN"],
        10000071: ["OINV", "OWTR"],
    }

    results = {}
    for tt, tables in tests.items():
        entry = {"transtype": tt, "refs": 0, "tables": {}}
        base_sql = f"""
        SELECT DISTINCT CAST(OINM."BASE_REF" AS BIGINT) AS bref
        FROM TELCHI.OINM OINM
        WHERE OINM."TransType" = {tt}
          AND OINM."DocDate" >= '2023-02-01' AND OINM."DocDate" < '2023-04-01'
        """
        try:
            cur.execute(base_sql)
            refs = [r[0] for r in cur.fetchall()]
        except Exception as e:
            entry["error"] = str(e)[:120]
            results[str(tt)] = entry
            continue
        entry["refs"] = len(refs)
        non_numeric = sum(1 for r in refs if r is None)
        entry["refs_nonnumeric"] = non_numeric
        for tab in tables:
            for keycol in ("DocNum", "DocEntry"):
                sql = (
                    f"SELECT COUNT(*) FROM TELCHI.\"{tab}\" H "
                    f"WHERE H.\"{keycol}\" IN ({','.join('?' * len(refs))})"
                )
                try:
                    cur.execute(sql, refs)
                    matched = int(cur.fetchone()[0])
                    entry["tables"].setdefault(tab, {})[keycol] = matched
                except Exception as e:
                    entry["tables"].setdefault(tab, {})[keycol] = f"ERR {str(e)[:50]}"
        results[str(tt)] = entry
        print(f"tt={tt} refs={entry['refs']} tables={json.dumps(entry['tables'])}")

    out = ROOT / "validation/inventory_movements/document_link_resolution.json"
    out.write_text(json.dumps(results, indent=2, default=str))
    print("WROTE", out)
    cur.close()
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())