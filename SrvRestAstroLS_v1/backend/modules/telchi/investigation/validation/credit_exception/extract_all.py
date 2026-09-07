"""EXTRACT — consolidate all per-case evidence into case_bundle.json.

READ ONLY. Consumes the already-produced evidence files:
  revalidated_cases.json (PHASE 1/2, EXACT as-of reconstruction)
  doc_chain.json        (PHASE 19/20)
  payment_outcome.json  (PHASE 24-26)
and adds:
  SAP actor: OUSR user code, superuser flag, technical classification
  EXCEL auth: CONFIRM_CREDIT_LINE_DEVIATION effective (FULL/NONE/unknown)
  CUSTOMER: VENCREVENC/U_ClienteExcepcional/Block/PaymBlock
  RETAIL (for retail cases): VENTA match (estacion/tipo/usuario/hora/credito)
    + auth-log events on same date/station/tipo/user with timing class.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path

from modules.telchi.investigation.paths import EVIDENCE_ROOT

from modules.telchi.investigation.atomic.connection import connect

HERE = Path(__file__).parent
EVIDENCE = EVIDENCE_ROOT / "credit_exception" / "evidence"
TOLERANCE = 0.01
TECH_USERS = {"soluone": 156, "dms": 145, "manager": 1, "B1i": None, "Workflow": None,
              "EDsUser": None, "AlertSvc": None, "alianza": 176}
# ObjType -> meaning (validated in this installation)
BT_MEANING = {-1: "direct", 15: "delivery", 17: "order", 23: "quotation", 13: "invoice"}


def rows(cur, sql, params=()):
    cur.execute(sql, params)
    cols = [d[0].lower() for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def to_date(v):
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    return datetime.strptime(str(v)[:10], "%Y-%m-%d").date()


def main() -> int:
    conn, cur = connect()
    try:
        cases = json.loads((EVIDENCE / "revalidated_cases.json").read_text(encoding="utf-8"))
        docchain = {r["docentry"]: r for r in json.loads((EVIDENCE / "doc_chain.json").read_text(encoding="utf-8"))}
        payments = {r["docentry"]: r for r in json.loads((EVIDENCE / "payment_outcome.json").read_text(encoding="utf-8"))}
        cardcodes = sorted({c["cardcode"] for c in cases})
        usersigns = sorted({c["usersign"] for c in cases})
        phcc = ",".join(["?"] * len(cardcodes))
        phu = ",".join(["?"] * len(usersigns))

        # SAP actors
        ousr = rows(cur, f'''SELECT "USERID","USER_CODE","U_NAME","SUPERUSER","Locked" FROM "TELCHI"."OUSR"
            WHERE "USERID" IN ({phu})''', usersigns)
        user_map = {r["userid"]: r for r in ousr}

        # EXCEL authorization model (previous gate evidence)
        excel = json.loads((EVIDENCE.parent.parent / "credit_control" / "evidence" / "excel_authorization_model.json").read_text(encoding="utf-8"))
        excel_by_login = {u["login"].strip().lower(): u for u in excel["users_by_login"]}

        # OCRD flags
        ocrd = rows(cur, f'''SELECT "CardCode","CardName","CreditLine","Balance","GroupNum",
            "U_SO1_01VENCREVENC","U_ClienteExcepcional","Block","PaymBlock","U_CANAL_VENTAS"
            FROM "TELCHI"."OCRD" WHERE "CardCode" IN ({phcc})''', cardcodes)
        ocrd_map = {r["cardcode"]: r for r in ocrd}

        # ---- RETAIL: VENTA rows in window + auth log ----
        auth_rows = rows(cur, '''SELECT "U_SO1_IDENTIFICADOR","U_SO1_USUARIO","U_SO1_FECHAACCESO",
            "U_SO1_HORAACCESO","U_SO1_USUARIOAUTO","U_SO1_FOLIO","U_SO1_INSTANCIA"
            FROM "TELCHI"."@SO1_01LOGAUTORIZA" ORDER BY "U_SO1_FECHAACCESO"''')
        auth_by_day: dict[date, list] = defaultdict(list)
        for a in auth_rows:
            d = to_date(a["u_so1_fechaacceso"])
            if d:
                auth_by_day[d].append(a)

        venta_rows = rows(cur, '''SELECT "U_SO1_CLIENTE","U_SO1_FECHA","U_SO1_HORA","U_SO1_TOTALNETO",
            "U_SO1_SUCURSAL","U_SO1_ESTACION","U_SO1_TIPO","U_SO1_USUARIO","U_SO1_STATUS",
            "U_SO1_FACTURA","U_SO1_CREDITO","Code" FROM "TELCHI"."@SO1_01VENTA"
            WHERE "U_SO1_FECHA" >= '2026-01-01' AND "U_SO1_FECHA" <= '2026-08-31' AND "U_SO1_STATUS"='A' ''')
        venta_by_key: dict[tuple, list] = defaultdict(list)
        for v in venta_rows:
            key = (v["u_so1_cliente"], str(v["u_so1_fecha"])[:10])
            venta_by_key[key].append(v)

        folio_by_code = {}
        # fetch detail folios only for VENTA codes that will be used
        venta_codes = {v["code"] for c in cases for v in venta_by_key.get((c["cardcode"], c["docdate"]), [])}
        if venta_codes:
            vc = sorted(venta_codes)
            for i in range(0, len(vc), 500):
                chunk = vc[i:i + 500]
                folio_by_code.update({r["code"]: r["folio"] for r in rows(cur,
                    f'''SELECT "Code", MIN("U_SO1_FOLIO") AS folio FROM "TELCHI"."@SO1_01VENTADETALLE"
                    WHERE "Code" IN ({",".join(["?"] * len(chunk))}) AND "U_SO1_FOLIO" IS NOT NULL
                    GROUP BY "Code"''', chunk)})

        def hora_to_min(h):
            if h is None:
                return None
            h = int(h)
            return (h // 100) * 60 + (h % 100)

        def retail_lookup(c):
            """Match the sale to a VENTA row and collect auth evidence."""
            key = (c["cardcode"], c["docdate"])
            cands = [v for v in venta_by_key.get(key, [])
                     if abs(float(v["u_so1_totalneto"] or 0) - c["doctotal"]) <= 1.0]
            if not cands:
                # fallback: same day, any amount
                cands = venta_by_key.get(key, [])
            if not cands:
                return {"matched": False}
            best = min(cands, key=lambda v: abs(float(v["u_so1_totalneto"] or 0) - c["doctotal"]))
            folio = folio_by_code.get(best["code"])
            sale_min = hora_to_min(best["u_so1_hora"])
            day = to_date(best["u_so1_fecha"])
            # auth events: same station user, same date, applicable window around sale
            events = []
            for a in auth_by_day.get(day, []):
                am = hora_to_min(a["u_so1_horaacceso"])
                if am is None:
                    continue
                if int(a["u_so1_usuario"]) != int(best["u_so1_usuario"]):
                    continue
                f = a["u_so1_folio"] or ""
                same_station = (f[:3] == (best["u_so1_sucursal"] or ""[:3])
                                and f[3:6] == (best["u_so1_estacion"] or ""))
                if not same_station:
                    continue
                if sale_min is not None and abs(am - sale_min) <= 60:
                    events.append({
                        "identificador": a["u_so1_identificador"],
                        "hora": a["u_so1_horaacceso"],
                        "auto": a["u_so1_usuarioauto"],
                        "folio": f,
                        "mins_diff": am - sale_min if sale_min is not None else None,
                        "timing": ("BEFORE_SALE" if (sale_min is not None and am < sale_min)
                                   else "AFTER_SALE" if (sale_min is not None and am > sale_min)
                                   else "SAME_TIME_WINDOW"),
                    })
            return {
                "matched": True,
                "venta_code": best["code"],
                "sucursal": best["u_so1_sucursal"],
                "estacion": best["u_so1_estacion"],
                "tipo": best["u_so1_tipo"],
                "usuario_pos": best["u_so1_usuario"],
                "hora": best["u_so1_hora"],
                "total_neto": float(best["u_so1_totalneto"] or 0),
                "credito": best["u_so1_credito"],
                "factura_flag": best["u_so1_factura"],
                "folio": folio,
                "auth_events_window": events,
                "auth_found": any("auth_events_window" and True for _ in events) or len(events) > 0,
            }

        bundle = []
        for c in cases:
            de = c["docentry"]
            usr = user_map.get(c["usersign"], {})
            login = (usr.get("user_code") or "").strip().lower()
            excel_u = excel_by_login.get(login, {})
            eff = (excel_u.get("effective_credit_auth") or {}).get("CONFIRM_CREDIT_LINE_DEVIATION", "NO_GROUP_OR_UNMAPPED")
            ocr = ocrd_map.get(c["cardcode"], {})
            retail = retail_lookup(c) if (c["origin"] == "SAP" and c["retailone"] == "Y") else {"matched": False}
            dc = docchain.get(de, {})
            pm = payments.get(de, {})
            bundle.append({
                **c,
                "sap_user": usr.get("user_code"),
                "user_name": usr.get("u_name"),
                "superuser": usr.get("superuser"),
                "user_locked": usr.get("locked"),
                "excel_credit_auth": eff,
                "technical_user": login in (TECH_USERS.keys()),
                "vencrevenc_y": ocr.get("u_so1_01vencrevenc") == "Y",
                "cliente_excepcional": ocr.get("u_so1_01clientexceptional") or ocr.get("u_clienteexcepcional"),
                "block": ocr.get("block"),
                "paymblock": ocr.get("paymblock"),
                "cardname": ocr.get("cardname"),
                "customer_channel": ocr.get("u_canal_ventas"),
                **dc,
                **pm,
                "retail": retail,
            })
        # persist
        (EVIDENCE / "case_bundle.json").write_text(json.dumps(bundle, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        # quick aggregates
        cnt_retail = sum(1 for b in bundle if b["retail"]["matched"])
        cnt_retail_auth = sum(1 for b in bundle if b["retail"].get("auth_found"))
        cnt_retail_cash = sum(1 for b in bundle if b["retail"].get("credito") == "N")
        cnt_super = sum(1 for b in bundle if b["superuser"] == "Y")
        cnt_full = sum(1 for b in bundle if b["excel_credit_auth"] == "FULL")
        print(json.dumps({
            "cases": len(bundle),
            "retail_matched_venta": cnt_retail,
            "retail_with_auth_evidence": cnt_retail_auth,
            "retail_credito_N": cnt_retail_cash,
            "superuser_executor": cnt_super,
            "excel_FULL_executor": cnt_full,
        }, indent=1))
        return 0
    finally:
        conn.rollback()
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())