"""TELCHI branch replenishment Gate 1 + baseline (SAP/HANA READ ONLY).

This runner deliberately stops at observed behaviour. It does not calculate or
recommend ROP, safety stock, min/max, service levels, purchasing or production.
All SQL is aggregate/read-only and every output preserves the distinction
between an SAP warehouse and a logical branch.
"""
from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from modules.telchi.investigation.atomic.connection import connect
from modules.telchi.investigation.paths import EVIDENCE_ROOT

GATE = "TELCHI_BRANCH_REPLENISHMENT_OPERATIONAL_MAP_V1"
OUT = EVIDENCE_ROOT / "branch_replenishment" / "v1"


def jsonable(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    return value


def rows(cur: Any, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    cur.execute(sql, params)
    # HDBCLI uppercases unquoted aliases; the runner uses a stable lowercase DTO.
    names = [d[0].lower() for d in cur.description]
    return [dict(zip(names, row)) for row in cur.fetchall()]


def role(code: str, name: str, u_type: str | None, dms: Any) -> tuple[str, str]:
    """Return requested operational role and the evidence rule used."""
    c, n = (code or "").upper(), (name or "").upper()
    if "TRANSITO" in n or "TRANSIT" in n or "-TRAN" in c or "TRS" in c:
        return "TRANSIT", "code/name transit marker"
    if dms == 3 or "MOVIL" in n or "MÓVIL" in n or "RUTA" in n or "-D" in c and c.startswith(("LAB-", "LPZ-")):
        return "MOBILE", "DMS/mobile/ruta marker"
    if "DAÑAD" in n or "VENCID" in n or c.endswith("-DAN"):
        return "OTHER", "damaged/expired warehouse marker"
    if "SALON" in n or "SALÓN" in n or c.endswith("-SAL") or c.endswith("-SMK"):
        return "BRANCH_SALES", "salon/sales warehouse marker"
    if "PRODUCTO TERMINADO" in n or "TERMINADO" in n or "-T" in c and c[:3] in {"LAB", "SAA", "MAG", "LPZ", "NTG"}:
        return "FINISHED_GOODS", "finished-goods marker"
    if "PROCESO" in n or "ETIQUET" in n or "REACOND" in n or "RETEN" in n or c.endswith(("-P1", "-P2", "-P3", "-P4", "-P5")):
        return "PRODUCTION", "process/production marker"
    if "MATERIA PRIMA" in n or "A GRANEL" in n or c.endswith("-M1"):
        return "PRODUCTION", "raw-material/production marker"
    if "MEDICAMENTOS" in n or "MATRIZ" in n or c.endswith("-AMD") or c in {"2A-MAG", "2A-AMK"}:
        return "CENTRAL", "central/medicines marker"
    if "TECNIC" in n or "TALLER" in n:
        return "TECHNICAL", "technical marker"
    if "IMPORT" in n or "CONTINGENCIA" in n or "DEVOLUC" in n or "DAÑAD" in n or "DAN" in c or "EXTERN" in n or "MARKETING" in n:
        return "OTHER", "non-replenishment warehouse marker"
    return "UNKNOWN", "no validated role marker"


def branch_for(code: str) -> tuple[str | None, str | None, str]:
    """Conservative logical branch mapping; no branch is inferred from city alone."""
    c = (code or "").upper()
    prefixes = {
        "2A": "2A", "CM": "CM", "DV": "DV", "RC": "RC", "UR": "UR", "VI": "VI",
    }
    for prefix, branch in prefixes.items():
        if c == f"{prefix}-SAL" or c == f"{prefix}-SMK" or c.startswith(f"{prefix}-"):
            confidence = "EXACT" if c.endswith(("-SAL", "-SMK")) else "STRONG"
            return branch, branch, confidence
    if c.startswith("LPZ-"):
        return "LPZ", "La Paz", "HEURISTIC"
    return None, None, "UNKNOWN"


def classify_warehouses(cur: Any) -> list[dict[str, Any]]:
    master = rows(cur, '''SELECT "WhsCode" AS code,"WhsName" AS name,"Inactive" AS inactive,
        "U_TYPE" AS u_type,"U_TIPO" AS u_tipo,"U_WAREHOUSE_DMS" AS dms,
        "U_SO1_01SUCURSAL" AS branch_field,"City" AS city,"BPLid" AS bplid
        FROM "TELCHI"."OWHS" ORDER BY "WhsCode"''')
    movement = rows(cur, '''SELECT "Warehouse" AS code,COUNT(*) AS movement_rows,
        COUNT(DISTINCT "ItemCode") AS movement_items,SUM("InQty") AS in_qty,SUM("OutQty") AS out_qty
        FROM "TELCHI"."OINM" GROUP BY "Warehouse"''')
    transfer = rows(cur, '''SELECT code, SUM(received_docs) AS transfer_received_docs,
        SUM(received_lines) AS transfer_received_lines,SUM(received_qty) AS transfer_received_qty,
        SUM(sent_docs) AS transfer_sent_docs,SUM(sent_lines) AS transfer_sent_lines,
        SUM(sent_qty) AS transfer_sent_qty FROM (
          SELECT W."WhsCode" AS code,COUNT(DISTINCT W."DocEntry") AS received_docs,COUNT(*) AS received_lines,
            SUM(ABS("Quantity")) AS received_qty,0 AS sent_docs,0 AS sent_lines,0 AS sent_qty
          FROM "TELCHI"."OWTR" O JOIN "TELCHI"."WTR1" W ON W."DocEntry"=O."DocEntry"
          WHERE O."CANCELED"='N' GROUP BY "WhsCode"
          UNION ALL
          SELECT W."FromWhsCod" AS code,0,0,0,COUNT(DISTINCT W."DocEntry"),COUNT(*),SUM(ABS(W."Quantity"))
          FROM "TELCHI"."OWTR" O JOIN "TELCHI"."WTR1" W ON W."DocEntry"=O."DocEntry"
          WHERE O."CANCELED"='N' GROUP BY "FromWhsCod"
        ) X GROUP BY code''')
    sales = rows(cur, '''SELECT "Warehouse" AS code,COUNT(*) AS sales_movement_rows,
        COUNT(DISTINCT "ItemCode") AS sales_items,SUM("OutQty") AS sales_out_qty,
        SUM("InQty") AS sales_in_qty FROM "TELCHI"."OINM"
        WHERE "ItemCode" LIKE 'L%' AND "TransType" IN (13,15)
        GROUP BY "Warehouse"''')
    by = {r["code"]: r for r in movement}
    for r in transfer: by.setdefault(r["code"], {}).update(r)
    for r in sales: by.setdefault(r["code"], {}).update(r)
    result = []
    for r in master:
        m = by.get(r["code"], {})
        op_role, rule = role(r["code"], r["name"], r["u_type"], r["dms"])
        branch_id, branch_name, confidence = branch_for(r["code"])
        result.append({
            **r, "role": op_role, "role_evidence": rule,
            "branch_id": branch_id, "branch_name": branch_name,
            "branch_confidence": confidence,
            "movement_rows": m.get("movement_rows", 0), "movement_items": m.get("movement_items", 0),
            "movement_in_qty": m.get("in_qty", 0), "movement_out_qty": m.get("out_qty", 0),
            "sales_movement_rows": m.get("sales_movement_rows", 0), "sales_items": m.get("sales_items", 0),
            "sales_out_qty": m.get("sales_out_qty", 0), "sales_in_qty": m.get("sales_in_qty", 0),
            "transfer_received_docs": m.get("transfer_received_docs", 0),
            "transfer_received_lines": m.get("transfer_received_lines", 0),
            "transfer_received_qty": m.get("transfer_received_qty", 0),
            "transfer_sent_docs": m.get("transfer_sent_docs", 0),
            "transfer_sent_lines": m.get("transfer_sent_lines", 0),
            "transfer_sent_qty": m.get("transfer_sent_qty", 0),
        })
    return result


def product_profile(cur: Any) -> dict[str, Any]:
    counts = rows(cur, '''SELECT
      COUNT(*) AS total_l,
      SUM(CASE WHEN COALESCE("validFor",'N')='Y' THEN 1 ELSE 0 END) AS active_l,
      SUM(CASE WHEN COALESCE("validFor",'N')<>'Y' THEN 1 ELSE 0 END) AS inactive_l,
      SUM(CASE WHEN COALESCE("OnHand",0)<>0 THEN 1 ELSE 0 END) AS with_current_stock,
      SUM(CASE WHEN COALESCE("ItemCode",'') IN (SELECT DISTINCT "ItemCode" FROM "TELCHI"."OINM" WHERE "ItemCode" LIKE 'L%' AND ("InQty"<>0 OR "OutQty"<>0)) THEN 1 ELSE 0 END) AS with_movements
      FROM "TELCHI"."OITM" WHERE "ItemCode" LIKE ?''', ("L%",))[0]
    sales = rows(cur, '''SELECT COUNT(DISTINCT "ItemCode") AS n FROM "TELCHI"."OINM"
        WHERE "ItemCode" LIKE 'L%' AND "TransType" IN (13,15) AND COALESCE("OutQty",0)>0''')[0]["n"]
    transfers = rows(cur, '''SELECT COUNT(DISTINCT W."ItemCode") AS n FROM "TELCHI"."OWTR" O
        JOIN "TELCHI"."WTR1" W ON W."DocEntry"=O."DocEntry"
        WHERE O."CANCELED"='N' AND W."ItemCode" LIKE 'L%' AND W."Quantity"<>0''')[0]["n"]
    no_move = int(counts["total_l"] or 0) - int(counts["with_movements"] or 0)
    return {**counts, "with_sales": sales, "with_transfers": transfers, "without_movement": no_move}


def routes(cur: Any) -> list[dict[str, Any]]:
    result = rows(cur, '''SELECT W."FromWhsCod" AS origin,W."WhsCode" AS destination,
      COUNT(DISTINCT O."DocEntry") AS transfers,COUNT(*) AS lines,COUNT(DISTINCT W."ItemCode") AS l_products,
      SUM(ABS(W."Quantity")) AS volume,MIN(O."DocDate") AS first_date,MAX(O."DocDate") AS last_date,
      SUM(CASE WHEN W."Quantity"<0 THEN 1 ELSE 0 END) AS negative_lines
      FROM "TELCHI"."OWTR" O JOIN "TELCHI"."WTR1" W ON W."DocEntry"=O."DocEntry"
      WHERE O."CANCELED"='N' AND W."ItemCode" LIKE 'L%' GROUP BY W."FromWhsCod",W."WhsCode"
      ORDER BY volume DESC''')
    names = rows(cur, 'SELECT "WhsCode" AS code,"WhsName" AS name,"U_WAREHOUSE_DMS" AS dms FROM "TELCHI"."OWHS"')
    info = {r["code"]: r for r in names}
    for r in result:
        a, b = info.get(r["origin"], {}), info.get(r["destination"], {})
        r["origin_role"] = role(r["origin"], a.get("name", ""), a.get("u_type"), a.get("dms"))[0]
        r["destination_role"] = role(r["destination"], b.get("name", ""), b.get("u_type"), b.get("dms"))[0]
        r["route_role"] = f'{r["origin_role"]}->{r["destination_role"]}'
    return result


def branch_sources(cur: Any, warehouses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # Only customer-facing branch sales warehouses are used for this table.
    data = rows(cur, '''SELECT W."WhsCode" AS destination,W."FromWhsCod" AS origin,
      COUNT(DISTINCT O."DocEntry") AS transfers,SUM(ABS(W."Quantity")) AS volume,
      COUNT(DISTINCT W."ItemCode") AS l_products,MIN(O."DocDate") AS first_date,MAX(O."DocDate") AS last_date
      FROM "TELCHI"."OWTR" O JOIN "TELCHI"."WTR1" W ON W."DocEntry"=O."DocEntry"
      WHERE O."CANCELED"='N' AND W."ItemCode" LIKE 'L%'
        AND (W."WhsCode" LIKE '%-SAL' OR W."WhsCode" LIKE '%-SMK')
      GROUP BY W."WhsCode",W."FromWhsCod" ORDER BY W."WhsCode",volume DESC''')
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in data:
        branch, _, conf = branch_for(r["destination"])
        if branch:
            r["branch_id"], r["branch_confidence"] = branch, conf
            grouped[branch].append(r)
    out = []
    # Include every customer-facing branch warehouse, including branches with
    # no L-product receipt in the observed period; absence is evidence, not a
    # reason to silently drop the branch.
    for w in warehouses:
        if w["role"] == "BRANCH_SALES" and w["branch_id"]:
            grouped.setdefault(w["branch_id"], [])
    for branch, candidates in sorted(grouped.items()):
        candidates.sort(key=lambda x: float(x["volume"] or 0), reverse=True)
        primary = candidates[0] if candidates else None
        secondary = candidates[1] if len(candidates) > 1 else None
        out.append({
            "branch_id": branch,
            "primary_source": primary["origin"] if primary else None,
            "secondary_source": secondary["origin"] if secondary else None,
            "confidence": "STRONG" if primary else "UNKNOWN",
            "evidence": "direct active OWTR/WTR1 L-product volume into branch sales warehouse",
            "destination_warehouse": primary["destination"] if primary else None,
            "candidate_sources": candidates[:5],
        })
    return out


def route_paths(cur: Any, source_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Expose dominant observed two-hop paths without inventing a shipment leg.

    The source/destination transfer rows remain the atomic evidence. A path is
    a graph composition (same network, not a physical shipment assertion).
    """
    out = []
    for src in source_rows:
        transit, destination = src.get("primary_source"), src.get("destination_warehouse")
        if not transit or not destination:
            out.append({"branch_id": src["branch_id"], "origin": None, "transit": transit,
                        "destination": destination, "status": "NO_DOMINANT_PATH"})
            continue
        upstream = rows(cur, '''WITH U AS (
          SELECT W."FromWhsCod" AS origin,W."ItemCode" AS item,O."DocDate" AS event_date,
            COUNT(DISTINCT O."DocEntry") AS upstream_transfers,SUM(ABS(W."Quantity")) AS upstream_volume
          FROM "TELCHI"."OWTR" O JOIN "TELCHI"."WTR1" W ON W."DocEntry"=O."DocEntry"
          WHERE O."CANCELED"='N' AND W."ItemCode" LIKE 'L%' AND W."WhsCode"=?
          GROUP BY W."FromWhsCod",W."ItemCode",O."DocDate"), D AS (
          SELECT W."ItemCode" AS item,O."DocDate" AS event_date,
            COUNT(DISTINCT O."DocEntry") AS downstream_transfers,SUM(ABS(W."Quantity")) AS downstream_volume
          FROM "TELCHI"."OWTR" O JOIN "TELCHI"."WTR1" W ON W."DocEntry"=O."DocEntry"
          WHERE O."CANCELED"='N' AND W."ItemCode" LIKE 'L%' AND W."FromWhsCod"=? AND W."WhsCode"=?
          GROUP BY W."ItemCode",O."DocDate")
          SELECT U.origin,COUNT(*) AS matched_item_days,SUM(U.upstream_transfers) AS upstream_transfers,
            SUM(D.downstream_transfers) AS downstream_transfers,SUM(U.upstream_volume) AS upstream_volume,
            SUM(D.downstream_volume) AS downstream_volume,COUNT(DISTINCT U.item) AS l_products
          FROM U JOIN D ON D.item=U.item AND D.event_date=U.event_date
          GROUP BY U.origin ORDER BY downstream_volume DESC LIMIT 1''', (transit, transit, destination))
        if upstream:
            x = upstream[0]
            out.append({"branch_id": src["branch_id"], "origin": x["origin"], "transit": transit,
                        "destination": destination, "matched_item_days": x["matched_item_days"],
                        "upstream_transfers": x["upstream_transfers"], "downstream_transfers": x["downstream_transfers"],
                        "upstream_volume": x["upstream_volume"], "downstream_volume": x["downstream_volume"],
                        "l_products": x["l_products"],
                        "status": "SAME_ITEM_DATE_GRAPH_MATCH; not physical dispatch proof"})
        else:
            out.append({"branch_id": src["branch_id"], "origin": None, "transit": transit,
                        "destination": destination, "status": "NO_UPSTREAM_EVIDENCE"})
    return out


def baseline(cur: Any, warehouses: list[dict[str, Any]], source_rows: list[dict[str, Any]]) -> dict[str, Any]:
    branch_whs = [r["code"] for r in warehouses if r["branch_id"] and r["role"] == "BRANCH_SALES"]
    if not branch_whs:
        return {"branches": [], "stock_history_status": "PENDING_GATE_STOCK_HISTORY"}
    placeholders = ",".join("?" for _ in branch_whs)
    q = f'''SELECT W."WhsCode" AS warehouse,COUNT(DISTINCT W."ItemCode") AS products_received,
      COUNT(DISTINCT O."DocEntry") AS transfer_docs_received,COUNT(*) AS transfer_lines_received,
      SUM(ABS(W."Quantity")) AS transfer_volume,MIN(O."DocDate") AS first_replenishment,
      MAX(O."DocDate") AS last_replenishment
      FROM "TELCHI"."OWTR" O JOIN "TELCHI"."WTR1" W ON W."DocEntry"=O."DocEntry"
      WHERE O."CANCELED"='N' AND W."ItemCode" LIKE 'L%' AND W."WhsCode" IN ({placeholders})
      GROUP BY W."WhsCode"'''
    replenishment = {r["warehouse"]: r for r in rows(cur, q, tuple(branch_whs))}
    sales = {r["warehouse"]: r for r in rows(cur, f'''SELECT "Warehouse" AS warehouse,
      COUNT(DISTINCT "ItemCode") AS products_sold,COUNT(*) AS sales_rows,SUM("OutQty") AS sales_qty
      FROM "TELCHI"."OINM" WHERE "ItemCode" LIKE 'L%' AND "TransType" IN (13,15)
      AND "Warehouse" IN ({placeholders}) GROUP BY "Warehouse"''', tuple(branch_whs))}
    stock = {r["warehouse"]: r for r in rows(cur, f'''SELECT "WhsCode" AS warehouse,
      COUNT(DISTINCT "ItemCode") AS products_with_stock,SUM(CASE WHEN COALESCE("OnHand",0)<>0 THEN 1 ELSE 0 END) AS stock_rows,
      SUM("OnHand") AS on_hand FROM "TELCHI"."OITW" WHERE "ItemCode" LIKE 'L%' AND "WhsCode" IN ({placeholders})
      GROUP BY "WhsCode"''', tuple(branch_whs))}
    out = []
    for w in branch_whs:
        b = next(r["branch_id"] for r in warehouses if r["code"] == w)
        r = {"branch_id": b, "warehouse": w, **replenishment.get(w, {}), **sales.get(w, {}), **stock.get(w, {})}
        r["replenishment_frequency"] = "PENDING_GATE_STOCK_HISTORY"  # no daily stock/stockout event
        r["mean_median_size"] = "PENDING_GATE_STOCK_HISTORY"
        r["post_stockout_pct"] = "PENDING_GATE_STOCK_HISTORY"
        r["positive_stock_replenishment_pct"] = "PENDING_GATE_STOCK_HISTORY"
        r["observed_behaviour"] = "TRANSFER_OBSERVED; stock-trigger classification not asserted"
        out.append(r)
    return {"branches": out, "stock_history_status": "PENDING_GATE_STOCK_HISTORY"}


def real_cases(cur: Any, source_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # Select traceable, materially different observations without pretending
    # that urgency or stockout can be observed without historical stock.
    targets = [("2A-SAL", "high_rotation"), ("CM-SAL", "high_rotation"),
               ("VI-SAL", "medium_rotation"), ("RC-SAL", "slow_rotation"),
               ("UR-SAL", "many_transfer_candidates"), ("VI-SAL", "multiple_sources"),
               ("RC-SAL", "branch_to_branch_candidate"), ("CM-SAL", "post_stockout_candidate"),
               ("2A-SAL", "transfer_urgency_not_observable"), ("VI-SAL", "manual_irregular_candidate")]
    cases: list[dict[str, Any]] = []
    for warehouse, kind in targets:
        if kind == "branch_to_branch_candidate":
            q = '''SELECT W."ItemCode" AS item_code,COUNT(*) AS transfer_lines,SUM(ABS(W."Quantity")) AS volume
              FROM "TELCHI"."OWTR" O JOIN "TELCHI"."WTR1" W ON W."DocEntry"=O."DocEntry"
              WHERE O."CANCELED"='N' AND W."ItemCode" LIKE 'L%' AND W."WhsCode"=? AND W."FromWhsCod" LIKE '%-SAL'
              GROUP BY W."ItemCode" ORDER BY volume DESC'''
        elif kind == "multiple_sources":
            q = '''SELECT W."ItemCode" AS item_code,COUNT(*) AS transfer_lines,SUM(ABS(W."Quantity")) AS volume
              FROM "TELCHI"."OWTR" O JOIN "TELCHI"."WTR1" W ON W."DocEntry"=O."DocEntry"
              WHERE O."CANCELED"='N' AND W."ItemCode" LIKE 'L%' AND W."WhsCode"=?
              GROUP BY W."ItemCode" HAVING COUNT(DISTINCT W."FromWhsCod")>1 ORDER BY volume DESC'''
        else:
            q = '''SELECT W."ItemCode" AS item_code,COUNT(*) AS transfer_lines,SUM(ABS(W."Quantity")) AS volume
              FROM "TELCHI"."OWTR" O JOIN "TELCHI"."WTR1" W ON W."DocEntry"=O."DocEntry"
              WHERE O."CANCELED"='N' AND W."ItemCode" LIKE 'L%' AND W."WhsCode"=? GROUP BY W."ItemCode"
              ORDER BY volume DESC'''
        candidates = rows(cur, q, (warehouse,))
        if not candidates:
            continue
        if kind == "slow_rotation": chosen = candidates[-1]
        elif kind == "medium_rotation": chosen = candidates[len(candidates)//2]
        else: chosen = candidates[0]
        item = chosen["item_code"]
        events = rows(cur, '''SELECT "DocDate" AS event_date,CAST("TransType" AS NVARCHAR(20)) AS trans_type,
          "BASE_REF" AS base_ref,"ItemCode" AS item_code,"Warehouse" AS warehouse,
          "InQty" AS in_qty,"OutQty" AS out_qty,"TransNum" AS trans_num
          FROM "TELCHI"."OINM" WHERE "ItemCode"=? AND "Warehouse"=?
            AND "TransType" IN (13,14,15,16,67) ORDER BY "DocDate","TransNum" LIMIT 5000''', (item, warehouse))
        transfer_details = rows(cur, '''SELECT O."DocNum" AS doc_num,W."FromWhsCod" AS origin,W."WhsCode" AS destination,
          W."Quantity" AS quantity,O."DocDate" AS event_date,W."LineNum" AS line_num
          FROM "TELCHI"."OWTR" O JOIN "TELCHI"."WTR1" W ON W."DocEntry"=O."DocEntry"
          WHERE O."CANCELED"='N' AND W."ItemCode"=? AND W."WhsCode"=? ORDER BY O."DocDate",O."DocNum"''', (item, warehouse))
        route_by_doc = {str(x["doc_num"]): x for x in transfer_details}
        for event in events:
            if event["trans_type"] == "67" and str(event["base_ref"]) in route_by_doc:
                route = route_by_doc[str(event["base_ref"])]
                event.update({"origin": route["origin"], "destination": route["destination"], "transfer_quantity": route["quantity"]})
        transfer_indexes = [i for i, e in enumerate(events) if e["trans_type"] == "67"]
        if transfer_indexes:
            pivot = transfer_indexes[0]
            events = events[max(0, pivot - 4):pivot + 6]
        else:
            events = events[:10]
        cases.append({"case": kind, "branch_warehouse": warehouse, "item_code": item,
                      "selection": "real active L-product transfer population", "events": events,
                      "stock_resulting": "PENDING_GATE_STOCK_HISTORY",
                      "interpretation": "event trace only; no formal policy inferred"})
    return cases


def validations(cur: Any, warehouses: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "canceled_transfer_docs": rows(cur, 'SELECT COUNT(*) AS n FROM "TELCHI"."OWTR" WHERE "CANCELED"=\'Y\'')[0]["n"],
        "active_negative_transfer_lines": rows(cur, '''SELECT COUNT(*) AS n FROM "TELCHI"."WTR1" W JOIN "TELCHI"."OWTR" O ON O."DocEntry"=W."DocEntry" WHERE O."CANCELED"='N' AND W."Quantity"<0''')[0]["n"],
        "same_warehouse_lines": rows(cur, '''SELECT COUNT(*) AS n FROM "TELCHI"."WTR1" WHERE "FromWhsCod"="WhsCode"''')[0]["n"],
        "unknown_origin_or_destination": rows(cur, '''SELECT COUNT(*) AS n FROM "TELCHI"."WTR1" W LEFT JOIN "TELCHI"."OWHS" A ON A."WhsCode"=W."FromWhsCod" LEFT JOIN "TELCHI"."OWHS" B ON B."WhsCode"=W."WhsCode" WHERE A."WhsCode" IS NULL OR B."WhsCode" IS NULL''')[0]["n"],
        "unknown_role_warehouses": [r["code"] for r in warehouses if r["role"] == "UNKNOWN"],
        "invalid_l_items_in_oitm": rows(cur, '''SELECT COUNT(*) AS n FROM "TELCHI"."WTR1" W LEFT JOIN "TELCHI"."OITM" I ON I."ItemCode"=W."ItemCode" WHERE W."ItemCode" LIKE 'L%' AND I."ItemCode" IS NULL''')[0]["n"],
        "route_impossibility_same_wh": "same-warehouse checked; no semantic route emitted for same-warehouse",
        "duplicates": "OWTR.DocEntry + WTR1.LineNum is the atomic transfer key; duplicate test is pending full extraction, source grain contract preserved",
        "reversals": "active negative quantities preserved as legitimate reverse/adjustment lines; canceled headers excluded",
        "missing_branch_association": "non-branch operational warehouses are intentionally not forced into a BRANCH; see UNKNOWN/DEGRADED",
    }


def main() -> int:
    conn, cur = connect()
    try:
        whs = classify_warehouses(cur)
        rt = routes(cur)
        src = branch_sources(cur, whs)
        paths = route_paths(cur, src)
        result = {
            "gate": GATE, "context": {"entity": "TELCHI", "domain": "REPOSICIÓN / STOCK_E_INVENTARIOS", "stage": "INVESTIGATION", "source": "SAP_HANA", "read_only": True, "SAP_WRITE_COUNT": 0, "product_filter": "ItemCode LIKE 'L%'"},
            "warehouse_count": len(whs), "warehouses": whs, "routes": rt, "route_paths": paths,
            "branch_sources": src, "products": product_profile(cur),
            "baseline": baseline(cur, whs, src), "real_cases": real_cases(cur, src),
            "validations": validations(cur, whs),
            "lead_time": {"accounting": "MEASURABLE_CANDIDATE: OWTR.DocDate/DocTime -> destination OINM.DocDate/DocTime; exact line matching requires final event grain validation", "physical": "NOT_MEASURABLE_FROM_CURRENT_EVIDENCE: no reliable request/dispatch/receipt chain; SAP transfer is accounting-only"},
            "verdict": "DEGRADED",
            "degraded_causes": ["BRANCH_MAPPING_PARTLY_HEURISTIC", "HISTORICAL_DAILY_STOCK_NOT_CLOSED", "STOCKOUT_CLASSIFICATION_NOT_ASSERTED", "PHYSICAL_LEAD_TIME_NOT_AVAILABLE", "TRANSFER_URGENCY_NOT_IDENTIFIED_AS_A_DOCUMENTED_FIELD"],
        }
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "gate_result.json").write_text(json.dumps(jsonable(result), ensure_ascii=False, indent=2))
        for key in ("warehouses", "routes", "route_paths", "branch_sources", "real_cases"):
            (OUT / f"{key}.json").write_text(json.dumps(jsonable(result[key]), ensure_ascii=False, indent=2))
        print(json.dumps(jsonable({"gate": GATE, "verdict": result["verdict"], "warehouse_count": len(whs), "branches": len(src), "routes": len(rt), "products": result["products"], "output": str(OUT)}), ensure_ascii=False, indent=2))
    finally:
        cur.close(); conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
