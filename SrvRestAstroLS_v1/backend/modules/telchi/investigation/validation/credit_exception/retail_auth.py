"""PHASE 10-13 — @SO1_01LOGAUTORIZA full inventory + Retail sale linkage.

READ ONLY. Emits evidence/auth_log_inventory.json and evidence/retail_linkage.json.

Linkage strategy (validated in discovery):
  * @SO1_01LOGAUTORIZA.U_SO1_FOLIO = '<sucursal><estacion><tipo><seq>'
    e.g. SRCR08CA163968 -> SRC / R08 / CA / 163968.
  * @SO1_01VENTADETALLE has U_SO1_FOLIO (sale lines carry the folio).
  * @SO1_01VENTA is the sale header (cliente, fecha, hora, estacion, tipo,
    usuario, total) but does NOT store the folio string.
  * For retail sales of the universe, VENTA rows are matched on
    (cliente, fecha, total) tolerance; folio is then recovered from
    VENTADETALLE rows (same Code) when available.
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path

from modules.telchi.investigation.paths import EVIDENCE_ROOT

from modules.telchi.investigation.atomic.connection import connect

HERE = Path(__file__).parent
EVIDENCE = EVIDENCE_ROOT / "credit_exception" / "evidence"

FOLIO_RE = re.compile(r"^([A-Z0-9]{3})([A-Z0-9]{3})([A-Z]{2})(\d+)$")


def parse_folio(folio: str):
    if not folio:
        return None
    m = FOLIO_RE.match(folio)
    if not m:
        return None
    return {"sucursal": m.group(1), "estacion": m.group(2), "tipo": m.group(3), "seq": int(m.group(4))}


def rows(cur, sql, params=()):
    cur.execute(sql, params)
    cols = [d[0].lower() for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def main() -> int:
    conn, cur = connect()
    try:
        log = rows(cur, '''SELECT "U_SO1_TIPO","U_SO1_IDENTIFICADOR","U_SO1_INSTANCIA",
            "U_SO1_USUARIO","U_SO1_FECHAACCESO","U_SO1_HORAACCESO","U_SO1_FECHASALIDA",
            "U_SO1_HORASALIDA","U_SO1_USUARIOAUTO","U_SO1_FOLIO"
            FROM "TELCHI"."@SO1_01LOGAUTORIZA" ORDER BY "U_SO1_FECHAACCESO"''')
        print("auth log rows:", len(log))
        months = Counter()
        idents = Counter()
        parsed = 0
        for r in log:
            r["folio_parsed"] = parse_folio(r["u_so1_folio"])
            parsed += int(r["folio_parsed"] is not None)
            d = r["u_so1_fechaacceso"]
            months[(d.year, d.month)] += 1
            idents[r["u_so1_identificador"]] += 1
        months_str = {f"{y:04d}-{m:02d}": n for (y, m), n in sorted(months.items())}
        print("months:", months_str)
        print("idents:", idents.most_common(12))
        print("folio parse rate:", parsed, "/", len(log))

        # window events (2026-01-01..2026-08-31)
        win = [r for r in log
               if r["u_so1_fechaacceso"] and date(2026, 1, 1) <= r["u_so1_fechaacceso"].date() <= date(2026, 8, 31)]
        win_idents = Counter(r["u_so1_identificador"] for r in win)
        win_users = Counter(r["u_so1_usuario"] for r in win)
        print("window events:", len(win), "| idents:", win_idents.most_common(12))
        print("window top users:", win_users.most_common(12))

        # VENTA window volume by tipo/status/factura
        venta = rows(cur, '''SELECT "U_SO1_TIPO","U_SO1_STATUS","U_SO1_FACTURA", COUNT(*) AS n
            FROM "TELCHI"."@SO1_01VENTA"
            WHERE "U_SO1_FECHA" >= '2026-01-01' AND "U_SO1_FECHA" <= '2026-08-31'
            GROUP BY "U_SO1_TIPO","U_SO1_STATUS","U_SO1_FACTURA"''')
        print("VENTA by tipo/status/factura:")
        for v in venta:
            print("  ", v)

        EVIDENCE.mkdir(parents=True, exist_ok=True)
        (EVIDENCE / "auth_log_inventory.json").write_text(json.dumps({
            "total_events": len(log),
            "total_parsed_folio": parsed,
            "events_by_month": months_str,
            "identifiers": dict(idents),
            "window": {
                "start": "2026-01-01", "end": "2026-08-31",
                "events": len(win),
                "identifiers": dict(win_idents),
                "top_users": dict(win_users.most_common(20)),
            },
            "tipos": dict(Counter(r["u_so1_tipo"] for r in log)),
            "instancias": dict(Counter(r["u_so1_instancia"] for r in log)),
            "auto_vs_self": {
                "usuario_equals_auto": sum(1 for r in log if r["u_so1_usuario"] == r["u_so1_usuarioauto"]),
                "usuario_diff": sum(1 for r in log if r["u_so1_usuario"] != r["u_so1_usuarioauto"]),
            },
        }, ensure_ascii=False, indent=1, default=str), encoding="utf-8")

        # ---- retail linkage feasibility: match revalidated RETAIL sales to VENTA ----
        cases = json.loads((EVIDENCE / "revalidated_cases.json").read_text(encoding="utf-8"))
        retail = [c for c in cases if c["origin"] == "SAP" and c["retailone"] == "Y"]
        print("retail cases:", len(retail))
        # pickup a sample of 30 spread across window
        sample = sorted(retail, key=lambda c: c["docdate"])[:: max(1, len(retail) // 30)][:30]
        venta_idx = {}
        pairs = rows(cur, '''SELECT "U_SO1_CLIENTE","U_SO1_FECHA","U_SO1_HORA","U_SO1_TOTALNETO",
            "U_SO1_SUCURSAL","U_SO1_ESTACION","U_SO1_TIPO","U_SO1_USUARIO","U_SO1_STATUS",
            "U_SO1_FACTURA","Code" FROM "TELCHI"."@SO1_01VENTA"
            WHERE "U_SO1_FECHA" >= '2026-01-01' AND "U_SO1_FECHA" <= '2026-08-31' AND "U_SO1_STATUS"='A' ''')
        detail = rows(cur, '''SELECT "Code","U_SO1_FOLIO" FROM "TELCHI"."@SO1_01VENTADETALLE"
            WHERE "U_SO1_FECHA" IS NULL''') if False else []
        # load detail folios keyed by Code (only needed keys; simpler: full map)
        folio_by_code = rows(cur, '''SELECT "Code", MIN("U_SO1_FOLIO") AS folio
            FROM "TELCHI"."@SO1_01VENTADETALLE" WHERE "U_SO1_FOLIO" IS NOT NULL
            GROUP BY "Code"''')
        folio_map = {r["code"]: r["folio"] for r in folio_by_code}
        print("detail codes with folio:", len(folio_map))
        for p in pairs:
            venta_idx.setdefault((p["u_so1_cliente"], str(p["u_so1_fecha"])[:10]), []).append(p)

        matched, unmatched = [], []
        for c in sample:
            key = (c["cardcode"], c["docdate"])
            cands = venta_idx.get(key, [])
            best = None
            tol = 1.0
            for v in cands:
                diff = abs(float(v["u_so1_totalneto"] or 0) - c["doctotal"])
                if diff <= tol:
                    best = v
                    tol = diff
            if best:
                folio = folio_map.get(best["code"])
                matched.append({
                    "case": c["docentry"], "docnum": c["docnum"], "date": c["docdate"],
                    "case_total": c["doctotal"], "venta_total": float(best["u_so1_totalneto"] or 0),
                    "venta_code": best["code"], "folio": folio,
                    "estacion": best["u_so1_estacion"], "tipo": best["u_so1_tipo"],
                    "usuario_pos": best["u_so1_usuario"], "hora": best["u_so1_hora"],
                })
            else:
                unmatched.append({"case": c["docentry"], "docnum": c["docnum"], "date": c["docdate"], "total": c["doctotal"]})
        print("retail sample matched-to-VENTA:", len(matched), "| unmatched:", len(unmatched))
        for m in matched:
            print("  ", m)
        (EVIDENCE / "retail_linkage.json").write_text(json.dumps(
            {"sample_matched": matched, "sample_unmatched": unmatched},
            ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        return 0
    finally:
        conn.rollback()
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())