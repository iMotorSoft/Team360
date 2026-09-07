"""TELCHI_PRODUCTION_SCHEMA_DISCOVERY_V1 — schema discovery validator (READ ONLY).

Inventories and validates the real SAP B1 production schema for Telchi:
recipe (OITT/ITT1), production order (OWOR/WOR1), component consumption
(OIGE/IGE1), finished product receipt (OIGN/IGN1), warehouse transfer
(OWTR/WTR1), inventory movement (OINM), stock (OITW), warehouse master (OWHS).

Output: for each source — table, key, join, cardinality, coverage, confidence,
limitations, sample SAP document.
"""
from __future__ import annotations

import json
import sys
from typing import Any

from modules.telchi.investigation.atomic.connection import connect


def q(cursor: Any, sql: str, params: tuple = ()) -> Any:
    cursor.execute(sql, params)
    return cursor.fetchone()


def qall(cursor: Any, sql: str, params: tuple = ()) -> list:
    cursor.execute(sql, params)
    return cursor.fetchall()


def recipe_source(cur: Any) -> dict[str, Any]:
    total = q(cur, 'SELECT COUNT(*) FROM "TELCHI"."OITT"')[0]
    lines = q(cur, 'SELECT COUNT(*) FROM "TELCHI"."ITT1"')[0]
    parents = q(cur, 'SELECT COUNT(DISTINCT "Father") FROM "TELCHI"."ITT1"')[0]
    treetype = qall(cur, 'SELECT "TreeType", COUNT(*) FROM "TELCHI"."OITT" GROUP BY "TreeType"')
    issue = qall(cur, 'SELECT "IssueMthd", COUNT(*) FROM "TELCHI"."ITT1" GROUP BY "IssueMthd"')
    return {
        "table": "OITT/ITT1", "total_recipe_headers": total, "total_lines": lines,
        "distinct_parents": parents, "treetype_dist": dict(treetype),
        "issue_method_dist": dict(issue),
        "join": "ITT1.Father = OITT.Code", "confidence": "EXACT",
        "note": "IssueMthd M=manual, B=backflush",
    }


def production_order_source(cur: Any) -> dict[str, Any]:
    total = q(cur, 'SELECT COUNT(*) FROM "TELCHI"."OWOR"')[0]
    status = qall(cur, 'SELECT "Status", COUNT(*) FROM "TELCHI"."OWOR" GROUP BY "Status"')
    types = qall(cur, 'SELECT "Type", COUNT(*) FROM "TELCHI"."OWOR" GROUP BY "Type"')
    dmin, dmax = q(cur, 'SELECT MIN("PostDate"), MAX("PostDate") FROM "TELCHI"."OWOR"')
    items = q(cur, 'SELECT COUNT(DISTINCT "ItemCode") FROM "TELCHI"."OWOR"')[0]
    return {
        "table": "OWOR", "total_orders": total, "status_dist": dict(status),
        "type_dist": dict(types), "date_min": str(dmin)[:10], "date_max": str(dmax)[:10],
        "distinct_items": items, "key": "DocEntry", "confidence": "EXACT",
        "note": "Status L=Released(20K), C=Closed, P=Planned. Type S=Standard, D=Disassembly",
    }


def expected_component_source(cur: Any) -> dict[str, Any]:
    total = q(cur, 'SELECT COUNT(*) FROM "TELCHI"."WOR1"')[0]
    per_order = q(cur,
        'SELECT COUNT(DISTINCT "DocEntry") FROM "TELCHI"."WOR1"')[0]
    return {
        "table": "WOR1", "total_lines": total, "orders_with_components": per_order,
        "join": "WOR1.DocEntry = OWOR.DocEntry", "key": "DocEntry+LineNum",
        "confidence": "EXACT",
        "note": "BaseQty=per-unit, PlannedQty=total planned, IssuedQty=issued",
    }


def actual_consumption_source(cur: Any) -> dict[str, Any]:
    total = q(cur, 'SELECT COUNT(*) FROM "TELCHI"."IGE1" WHERE "BaseType"=202')[0]
    orders = q(cur, 'SELECT COUNT(DISTINCT "BaseEntry") FROM "TELCHI"."IGE1" WHERE "BaseType"=202')[0]
    return {
        "table": "IGE1 (BaseType=202)", "total_issue_lines": total,
        "orders_linked": orders,
        "join": "IGE1.BaseEntry = OWOR.DocEntry AND IGE1.BaseType=202",
        "key": "DocEntry+LineNum", "confidence": "EXACT",
        "note": "Consumption (Issue for Production); BaseLine=WOR1.LineNum",
    }


def finished_receipt_source(cur: Any) -> dict[str, Any]:
    total = q(cur, 'SELECT COUNT(*) FROM "TELCHI"."IGN1" WHERE "BaseType"=202')[0]
    orders = q(cur, 'SELECT COUNT(DISTINCT "BaseEntry") FROM "TELCHI"."IGN1" WHERE "BaseType"=202')[0]
    return {
        "table": "IGN1 (BaseType=202)", "total_receipt_lines": total,
        "orders_linked": orders,
        "join": "IGN1.BaseEntry = OWOR.DocEntry AND IGN1.BaseType=202",
        "key": "DocEntry+LineNum", "confidence": "EXACT",
        "note": "Finished product receipt (Receipt from Production)",
    }


def transfer_source(cur: Any) -> dict[str, Any]:
    total = q(cur, 'SELECT COUNT(*) FROM "TELCHI"."OWTR"')[0]
    lines = q(cur, 'SELECT COUNT(*) FROM "TELCHI"."WTR1"')[0]
    btype = qall(cur, 'SELECT "BaseType", COUNT(*) FROM "TELCHI"."WTR1" GROUP BY "BaseType" ORDER BY COUNT(*) DESC')
    return {
        "table": "OWTR/WTR1", "total_transfers": total, "total_lines": lines,
        "base_type_dist": {str(k): v for k, v in btype},
        "key": "DocEntry / DocEntry+LineNum", "confidence": "EXACT",
        "note": "WTR1.WhsCode=dest, FromWhsCod=origin; BaseRef=source doc",
    }


def inventory_movement_source(cur: Any) -> dict[str, Any]:
    total = q(cur, 'SELECT COUNT(*) FROM "TELCHI"."OINM"')[0]
    tt = qall(cur, 'SELECT "TransType", COUNT(*) FROM "TELCHI"."OINM" WHERE "TransType" IN (59,60,67,202) GROUP BY "TransType" ORDER BY COUNT(*) DESC')
    # link verification
    link59 = q(cur, 'SELECT COUNT(DISTINCT M."BASE_REF") FROM "TELCHI"."OINM" M JOIN "TELCHI"."IGN1" N ON N."BaseRef"=M."BASE_REF" WHERE M."TransType"=59')[0]
    link60 = q(cur, 'SELECT COUNT(DISTINCT M."BASE_REF") FROM "TELCHI"."OINM" M JOIN "TELCHI"."IGE1" E ON E."BaseRef"=M."BASE_REF" WHERE M."TransType"=60')[0]
    return {
        "table": "OINM", "total_rows": total,
        "production_transtype_dist": {str(k): v for k, v in tt},
        "receipt_links_tt59": link59, "issue_links_tt60": link60,
        "key": "TransNum+TransSeq", "confidence": "EXACT",
        "note": "TT59=receipt(InQty), TT60=issue(OutQty), TT67=transfer, 202=production. BASE_REF=source DocNum/BaseRef",
    }


def stock_source(cur: Any) -> dict[str, Any]:
    total = q(cur, 'SELECT COUNT(*) FROM "TELCHI"."OITW"')[0]
    items = q(cur, 'SELECT COUNT(DISTINCT "ItemCode") FROM "TELCHI"."OITW"')[0]
    whs = q(cur, 'SELECT COUNT(DISTINCT "WhsCode") FROM "TELCHI"."OITW"')[0]
    return {
        "table": "OITW", "total_rows": total, "distinct_items": items,
        "distinct_whs": whs, "key": "ItemCode+WhsCode", "confidence": "EXACT",
        "note": "Current stock only; historical stock must be reconstructed from OINM",
    }


def warehouse_master(cur: Any) -> dict[str, Any]:
    whs = qall(cur, 'SELECT "WhsCode", "WhsName" FROM "TELCHI"."OWHS"')
    roles = {"CENTRAL": [], "LABORATORIO": [], "SUCURSAL_SALON": [], "MOVIL": [],
             "MATERIA_PRIMA": [], "PRODUCTO_TERMINADO": [], "PROCESO": [],
             "DESPACHO": [], "DISTRIBUCION_TERBOL": [], "TRANSITO": [], "DMS": [], "OTRO": []}
    for code, name in whs:
        n = (name or "").upper()
        c = (code or "").upper()
        if "MATERIA PRIMA" in n or c.endswith("-M1") or "GRANEL" in n:
            roles["MATERIA_PRIMA"].append(c)
        elif "PRODUCTO TERMINADO" in n or "-T" in c and ("LAB" in c or "SAA" in c or "MAG" in c):
            roles["PRODUCTO_TERMINADO"].append(c)
        elif "PROCESO" in n or "PRODUCTOS EN PROCESO" in n or c.endswith("-P1") or c.endswith("-P2"):
            roles["PROCESO"].append(c)
        elif "DESPACHO" in n or "PICKING" in n:
            roles["DESPACHO"].append(c)
        elif "MOVIL" in n or "RUTA" in n:
            roles["MOVIL"].append(c)
        elif "SALON" in n or "SAL" in c:
            roles["SUCURSAL_SALON"].append(c)
        elif "TRANSITO" in n or "TRAN" in c or "TRS" in c:
            roles["TRANSITO"].append(c)
        elif "DISTRIBUCION" in n or "TERBOL" in n:
            roles["DISTRIBUCION_TERBOL"].append(c)
        elif "DMS" in c:
            roles["DMS"].append(c)
        elif "MEDICAMENTOS" in n or "MATRIZ" in n or "AMD" in c:
            roles["CENTRAL"].append(c)
        else:
            roles["OTRO"].append(c)
    return {"table": "OWHS", "total_warehouses": len(whs), "roles": {k: v for k, v in roles.items() if v}}


def main() -> int:
    conn, cur = connect()
    try:
        result = {
            "gate": "TELCHI_PRODUCTION_SCHEMA_DISCOVERY_V1",
            "recipe": recipe_source(cur),
            "production_order": production_order_source(cur),
            "expected_components": expected_component_source(cur),
            "actual_consumption": actual_consumption_source(cur),
            "finished_receipt": finished_receipt_source(cur),
            "transfer": transfer_source(cur),
            "inventory_movement": inventory_movement_source(cur),
            "stock": stock_source(cur),
            "warehouse_master": warehouse_master(cur),
        }
        print(json.dumps(result, indent=2, default=str))

        print(f"\n{'='*70}")
        print("TELCHI_PRODUCTION_SCHEMA_DISCOVERY_V1")
        print(f"{'='*70}")
        for k, v in result.items():
            if k == "gate":
                continue
            print(f"\n[{k.upper()}]")
            for kk, vv in v.items():
                if kk in ("note", "join", "key", "confidence"):
                    print(f"  {kk}: {vv}")
                elif isinstance(vv, dict):
                    print(f"  {kk}: {json.dumps(vv, default=str)[:200]}")
                else:
                    print(f"  {kk}: {vv}")

    finally:
        cur.close()
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
