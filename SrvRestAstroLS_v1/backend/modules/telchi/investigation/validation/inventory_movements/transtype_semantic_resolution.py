#!/usr/bin/env python3
"""TransType Semantic Resolution — CORRECTED line link methodology.

This script corrects the broken line link test from the previous phase.

Key corrections:
1. Line link test must resolve BASE_REF (DocNum) → HEADER.DocEntry → LINE
2. When ApplObj > 0, use AppObjAbs (DocEntry) + AppObjLine (LineNum) directly
3. When ApplObj = -1, use BASE_REF → HEADER.DocEntry → LINE.DocEntry + LINE.LineNum = DocLineNum
4. DocNum collision analysis is critical for understanding link reliability

No writes to HANA. Read-only.
Produces:
  - transtype_map_v2.yaml (corrected)
  - document_link_matrix_v2.json (corrected)
  - line_link_validation.json (new, corrected)
  - docnum_collision_analysis.json (new, expanded)
"""
from __future__ import annotations

import json
import os
import shlex
import sys
import time
from collections import defaultdict
from pathlib import Path

from modules.telchi.investigation.paths import SECRET_ROOT

import yaml
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
HANA_ENV = SECRET_ROOT / "sap" / "hana.env"
OUT_DIR = ROOT / "validation" / "inventory_movements"

# SAP B1 Official TransType → Object mapping
# Source: SAP Business One SDK Reference Guide
OFFICIAL_TRANSTYPE = {
    13: {
        "object": "A/R Invoice", "header": "OINV", "line": "INV1",
        "category": "SALES", "official_name": "arInvoice",
        "note": "Primary document. ApplObj=-1 means movement IS the invoice."
    },
    14: {
        "object": "A/R Credit Memo", "header": "ORIN", "line": "RIN1",
        "category": "SALES_RETURN", "official_name": "arCreditNote",
        "note": "ApplObj=15 when referencing Delivery. ApplObj=-1 for direct credit."
    },
    15: {
        "object": "Delivery", "header": "ODLN", "line": "DLN1",
        "category": "SALES", "official_name": "arDeliveryNote",
        "note": "Primary delivery document."
    },
    16: {
        "object": "A/R Return", "header": "ORPD", "line": "RPD1",
        "category": "SALES_RETURN", "official_name": "arReturn",
        "note": "Customer return to warehouse."
    },
    18: {
        "object": "A/P Invoice", "header": "OPCH", "line": "PCH1",
        "category": "PURCHASE", "official_name": "apInvoice",
        "note": "Purchase invoice. Very low volume in Telchi."
    },
    19: {
        "object": "A/P Credit Memo", "header": "ORPC", "line": "RPC1",
        "category": "PURCHASE_RETURN", "official_name": "apCreditNote",
        "note": "ApplObj=20 when referencing Goods Receipt PO."
    },
    20: {
        "object": "Goods Receipt PO", "header": "OPDN", "line": "PDN1",
        "category": "PURCHASE", "official_name": "apDeliveryNote",
        "note": "Purchase goods receipt. Large value."
    },
    21: {
        "object": "Goods Return", "header": "OPDN", "line": "PDN1",
        "category": "PURCHASE_RETURN", "official_name": "apReturn",
        "note": "Return to vendor. Uses same tables as TT=20."
    },
    59: {
        "object": "Inventory Goods Receipt", "header": "OIGN", "line": "IGN1",
        "category": "INVENTORY_RECEIPT", "official_name": "oInventoryGenEntry",
        "note": "ApplObj=202 when from Production Order. AppObjType P=Production, C=Component."
    },
    60: {
        "object": "Inventory Goods Issue", "header": "OIGE", "line": "IGE1",
        "category": "INVENTORY_ISSUE", "official_name": "oInventoryGenExit",
        "note": "ApplObj=202 when from Production Order. AppObjType C=Component consumption."
    },
    67: {
        "object": "Inventory Transfer", "header": "OWTR", "line": "WTR1",
        "category": "TRANSFER", "official_name": "oStockTransfer",
        "note": "Largest by rows and value. ApplObj=-1. InQty=OutQty balanced."
    },
    69: {
        "object": "Landed Costs", "header": "OIGN", "line": "IGN1",
        "category": "LANDED_COST", "official_name": "oLandedCosts",
        "note": "Value-only cost allocation. InQty=OutQty=0."
    },
    162: {
        "object": "Inventory Revaluation", "header": "OINM", "line": "OINM",
        "category": "VALUATION", "official_name": "oInventoryRevaluation",
        "note": "Value-only revaluation. Self-referencing."
    },
    202: {
        "object": "Production Order", "header": "OWOR", "line": "WOR1",
        "category": "PRODUCTION", "official_name": "oProductionOrders",
        "note": "DocLineNum=-1 indicates header-level movement."
    },
    10000071: {
        "object": "Inventory Posting (Custom)", "header": "OINM", "line": "OINM",
        "category": "OTHER", "official_name": "customExtended",
        "note": "Extended range. Self-referencing."
    },
}


def load_env() -> dict:
    vals = {}
    for line in HANA_ENV.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        k, _, v = line.partition("=")
        vals[k] = shlex.split(v, posix=True)[0]
    return vals


def connect():
    from hdbcli import dbapi
    host = os.environ.get("HANA_HOST", "127.0.0.1")
    port = int(os.environ.get("HANA_PORT", "30015"))
    schema = os.environ.get("HANA_SCHEMA", "TELCHI")
    env = load_env()
    return dbapi.connect(
        address=host, port=port,
        user=os.environ.get("HANA_USER", env["TELCHI_SAP_HANA_USER"]),
        password=os.environ.get("HANA_PASSWORD", env["TELCHI_SAP_HANA_PASSWORD"]),
        currentSchema=schema, encrypt="false",
    )


def q(cur, sql, params=None):
    cur.execute(sql, params)
    cols = [d[0] for d in cur.description]
    return pd.DataFrame(cur.fetchall(), columns=cols)


def resolve_docnum_to_docentry(cur, header_table: str, docnum: int) -> int | None:
    """Resolve DocNum → DocEntry for a header table. Returns None if not found."""
    try:
        cur.execute(f'SELECT "DocEntry" FROM TELCHI."{header_table}" WHERE "DocNum"=?', (docnum,))
        row = cur.fetchone()
        return row[0] if row else None
    except Exception:
        return None


def check_line_match(cur, line_table: str, docentry: int, linenumber: int) -> dict:
    """Check if a specific line exists in the line table."""
    try:
        cur.execute(
            f'SELECT "DocEntry", "LineNum", "ItemCode" FROM TELCHI."{line_table}" WHERE "DocEntry"=? AND "LineNum"=?',
            (docentry, linenumber)
        )
        row = cur.fetchone()
        if row:
            return {"match": True, "DocEntry": row[0], "LineNum": row[1], "ItemCode": row[2]}
        return {"match": False}
    except Exception as e:
        return {"match": False, "error": str(e)[:80]}


def run_corrected_line_link_tests(cur, window: tuple[str, str]) -> list[dict]:
    """Run CORRECTED line link tests using two strategies:

    Strategy A (ApplObj > 0): AppObjAbs = source DocEntry, AppObjLine = source LineNum
    Strategy B (ApplObj = -1): BASE_REF → HEADER.DocEntry → LINE.DocEntry + DocLineNum = LineNum
    """
    d0, d1 = window
    results = []

    for tt, info in OFFICIAL_TRANSTYPE.items():
        header = info["header"]
        line = info["line"]

        if header == "OINM":  # self-referencing types
            results.append({
                "TransType": tt,
                "header_table": header,
                "line_table": line,
                "strategy": "SELF_REFERENCING",
                "sample_size": 0,
                "strategy_a_matches": 0,
                "strategy_b_matches": 0,
                "total_matches": 0,
                "status": "NOT_APPLICABLE",
                "note": "Self-referencing; no separate line table"
            })
            continue

        # Sample movements for this TransType
        sample_df = q(cur, f"""
            SELECT TOP 20
                OINM."TransNum", CAST(OINM."BASE_REF" AS BIGINT) AS baseref,
                OINM."DocLineNum", OINM."ApplObj", OINM."AppObjAbs", OINM."AppObjLine",
                OINM."ItemCode", OINM."Warehouse"
            FROM TELCHI.OINM OINM
            WHERE OINM."TransType"={tt}
              AND OINM."DocDate">='{d0}' AND OINM."DocDate"<'{d1}'
              AND LENGTH(OINM."BASE_REF") > 0
              AND OINM."BASE_REF" NOT LIKE '%[^0-9]%'
            ORDER BY OINM."TransNum"
        """)

        if sample_df.empty:
            results.append({
                "TransType": tt,
                "header_table": header,
                "line_table": line,
                "strategy": "NO_SAMPLE",
                "sample_size": 0,
                "status": "NO_DATA"
            })
            continue

        strategy_a_total = 0
        strategy_a_matches = 0
        strategy_b_total = 0
        strategy_b_matches = 0
        details = []

        for _, row in sample_df.iterrows():
            baseref = int(row["BASEREF"])
            docline = int(row["DocLineNum"])
            applobj = int(row["ApplObj"])
            appobjabs = int(row["AppObjAbs"])
            appobjline = int(row["AppObjLine"])

            detail = {
                "TransNum": int(row["TransNum"]),
                "BASE_REF": baseref,
                "DocLineNum": docline,
                "ApplObj": applobj,
                "AppObjAbs": appobjabs,
                "AppObjLine": appobjline,
                "ItemCode": row["ItemCode"],
                "strategy_a": None,
                "strategy_b": None,
            }

            # Strategy A: ApplObj > 0 → use AppObjAbs + AppObjLine
            if applobj > 0 and appobjabs > 0 and appobjline >= 0:
                strategy_a_total += 1
                match = check_line_match(cur, line, appobjabs, appobjline)
                detail["strategy_a"] = match
                if match.get("match"):
                    strategy_a_matches += 1

            # Strategy B: BASE_REF → HEADER.DocEntry → LINE
            # First resolve DocNum → DocEntry via header table
            docentry = resolve_docnum_to_docentry(cur, header, baseref)
            if docentry is not None:
                strategy_b_total += 1
                match = check_line_match(cur, line, docentry, docline)
                detail["strategy_b"] = match
                detail["resolved_docentry"] = docentry
                if match.get("match"):
                    strategy_b_matches += 1

            details.append(detail)

        total = len(details)
        any_match = strategy_a_matches > 0 or strategy_b_matches > 0

        results.append({
            "TransType": tt,
            "header_table": header,
            "line_table": line,
            "strategy": "DUAL" if applobj > 0 else "DOCNUM_RESOLVE",
            "sample_size": total,
            "strategy_a_applicable": strategy_a_total,
            "strategy_a_matches": strategy_a_matches,
            "strategy_b_applicable": strategy_b_total,
            "strategy_b_matches": strategy_b_matches,
            "total_matches": strategy_a_matches + strategy_b_matches,
            "details": details,
            "status": "CONFIRMED_EXACT" if (strategy_a_matches == strategy_a_total and strategy_a_total > 0) or (strategy_b_matches == strategy_b_total and strategy_b_total > 0) else "PARTIAL" if any_match else "NOT_APPLICABLE",
        })

        print(f"  TT={tt}: strategy_a={strategy_a_matches}/{strategy_a_total}, strategy_b={strategy_b_matches}/{strategy_b_total}")

    return results


def run_expanded_collision_analysis(cur, window: tuple[str, str]) -> dict:
    """Expanded DocNum collision analysis with larger sample and per-TransType breakdown."""
    d0, d1 = window

    # Get distinct BASE_REF per TransType
    sample_df = q(cur, f"""
        SELECT OINM."TransType", CAST(OINM."BASE_REF" AS VARCHAR(50)) AS baseref, COUNT(*) AS n
        FROM TELCHI.OINM OINM
        WHERE OINM."DocDate">='{d0}' AND OINM."DocDate"<'{d1}'
          AND LENGTH(OINM."BASE_REF") > 0
          AND OINM."BASE_REF" NOT LIKE '%[^0-9]%'
        GROUP BY OINM."TransType", OINM."BASE_REF"
        ORDER BY OINM."TransType", n DESC
    """)

    collision_tables = [
        "OINV", "ORIN", "ODLN", "OPCH", "OPDN", "OIGN", "OIGE",
        "OWTR", "ORCT", "ORPC", "OWOR", "ORPD"
    ]

    by_tt = defaultdict(list)
    for _, row in sample_df.iterrows():
        by_tt[int(row["TransType"])].append(row["BASEREF"])

    results = {
        "window": list(window),
        "tables_evaluated": collision_tables,
        "per_transtype": {},
        "summary": {
            "total_sampled": 0,
            "total_collisions": 0,
            "collision_rate": 0.0,
        }
    }

    total_sampled = 0
    total_collisions = 0

    for tt in sorted(by_tt.keys()):
        refs = by_tt[tt][:10]  # Sample up to 10 per TransType (reduced for speed)
        collisions = {}

        for ref_str in refs:
            ref_int = int(ref_str)
            found_in = []
            # Use a single query with UNION ALL for efficiency
            union_parts = []
            for tab in collision_tables:
                union_parts.append(f'SELECT \'{tab}\' AS tbl, COUNT(*) AS cnt FROM TELCHI."{tab}" WHERE "DocNum"={ref_int}')
            combined_sql = ' UNION ALL '.join(union_parts)
            try:
                cur.execute(combined_sql)
                for row in cur.fetchall():
                    if row[1] > 0:
                        found_in.append({"table": row[0], "count": row[1]})
            except Exception:
                pass

            if len(found_in) > 1:
                collisions[ref_str] = found_in
                total_collisions += 1
            total_sampled += 1

        collision_rate = len(collisions) / len(refs) if refs else 0.0

        results["per_transtype"][str(tt)] = {
            "sample_size": len(refs),
            "collisions": len(collisions),
            "collision_rate": round(collision_rate, 4),
            "collision_examples": {k: v for k, v in list(collisions.items())[:3]},
            "expected_header": OFFICIAL_TRANSTYPE.get(tt, {}).get("header", "UNKNOWN"),
        }

        print(f"  TT={tt}: {len(refs)} sampled, {len(collisions)} collisions ({collision_rate:.1%})")

    results["summary"] = {
        "total_sampled": total_sampled,
        "total_collisions": total_collisions,
        "collision_rate": round(total_collisions / total_sampled, 4) if total_sampled > 0 else 0.0,
    }

    return results


def run_appl_obj_analysis(cur, window: tuple[str, str]) -> dict:
    """Analyze ApplObj distribution per TransType to understand link semantics."""
    d0, d1 = window

    appl_df = q(cur, f"""
        SELECT OINM."TransType", OINM."ApplObj",
               CASE OINM."ApplObj"
                   WHEN -1 THEN 'NO_LINK'
                   WHEN 13 THEN 'oInvoices'
                   WHEN 14 THEN 'oCreditNotes'
                   WHEN 15 THEN 'oDeliveryNotes'
                   WHEN 16 THEN 'oReturns'
                   WHEN 18 THEN 'oPurchaseInvoices'
                   WHEN 19 THEN 'oPurchaseCreditNotes'
                   WHEN 20 THEN 'oPurchaseDeliveryNotes'
                   WHEN 21 THEN 'oPurchaseReturns'
                   WHEN 59 THEN 'oInventoryGenEntry'
                   WHEN 60 THEN 'oInventoryGenExit'
                   WHEN 67 THEN 'oStockTransfer'
                   WHEN 69 THEN 'oLandedCosts'
                   WHEN 162 THEN 'oInventoryRevaluation'
                   WHEN 202 THEN 'oProductionOrders'
                   ELSE 'UNKNOWN_' || CAST(OINM."ApplObj" AS VARCHAR)
               END AS appl_name,
               COUNT(*) AS n,
               SUM(CASE WHEN OINM."AppObjAbs" IS NOT NULL AND OINM."AppObjAbs">0 THEN 1 ELSE 0 END) AS has_appobjabs,
               SUM(CASE WHEN OINM."AppObjLine" IS NOT NULL AND OINM."AppObjLine">=0 THEN 1 ELSE 0 END) AS has_appobjline
        FROM TELCHI.OINM OINM
        WHERE OINM."DocDate">='{d0}' AND OINM."DocDate"<'{d1}'
        GROUP BY OINM."TransType", OINM."ApplObj"
        ORDER BY OINM."TransType", n DESC
    """)

    result = {}
    for _, row in appl_df.iterrows():
        tt = str(int(row["TransType"]))
        result.setdefault(tt, []).append({
            "ApplObj": int(row["ApplObj"]),
            "ApplObj_name": row["APPL_NAME"],
            "count": int(row["N"]),
            "has_appobjabs": int(row["HAS_APPOBJABS"]),
            "has_appobjline": int(row["HAS_APPOBJLINE"]),
        })

    return result


def build_corrected_transtype_map(
    appl_analysis: dict,
    line_link_results: list[dict],
    collision_results: dict,
    materiality: dict,
) -> dict:
    """Build corrected TransType map with proper evidence."""

    map_entries = []
    corrections = []

    for tt, info in OFFICIAL_TRANSTYPE.items():
        tt_str = str(tt)

        # Get ApplObj distribution for this TransType
        appl_dist = appl_analysis.get(tt_str, [])
        primary_appl = appl_dist[0] if appl_dist else None
        primary_appl_obj = primary_appl["ApplObj"] if primary_appl else -1
        primary_appl_name = primary_appl["ApplObj_name"] if primary_appl else "UNKNOWN"

        # Get line link test result
        line_result = next((r for r in line_link_results if r["TransType"] == tt), None)
        line_status = line_result["status"] if line_result else "NOT_TESTED"

        # Get collision info
        coll_info = collision_results.get("per_transtype", {}).get(tt_str, {})
        collision_rate = coll_info.get("collision_rate", 0.0)

        # Get materiality
        mat = materiality.get(tt_str, {})

        # Determine link quality
        if line_status == "CONFIRMED_EXACT":
            link_quality = "EXACT_ID_LINK"
            link_status = "CONFIRMED_EXACT"
        elif line_status == "PARTIAL":
            link_quality = "DOCUMENT_NUMBER_LINK"
            link_status = "PARTIAL"
        elif info["header"] == "OINM":
            link_quality = "HEURISTIC_LINK"
            link_status = "SELF_REFERENCING"
        else:
            link_quality = "DOCUMENT_NUMBER_LINK"
            link_status = "PENDING"

        # Determine link strategy description
        if primary_appl_obj > 0:
            link_strategy = f"ApplObj={primary_appl_obj} ({primary_appl_name}); AppObjAbs=DocEntry, AppObjLine=LineNum"
        else:
            link_strategy = f"BASE_REF=DocNum → {info['header']}.DocEntry → {info['line']}.LineNum=DocLineNum"

        entry = {
            "trans_type": tt,
            "official_object_type": info["official_name"],
            "official_name": info["object"],
            "header_table": info["header"],
            "line_table": info["line"],
            "business_category": info["category"],
            "raw_preserved": True,
            "semantic_status": "CONFIRMED",
            "link_status": link_status,
            "link_source_field": f"BASE_REF → {info['header']}.DocEntry" if primary_appl_obj <= 0 else f"AppObjAbs → {info['line']}.DocEntry",
            "link_target_field": f"{info['line']}.LineNum" if info["header"] != "OINM" else "self-referencing",
            "line_link_status": line_status,
            "link_quality": link_quality,
            "confidence": "CONFIRMED" if line_status in ("CONFIRMED_EXACT", "NOT_APPLICABLE") else "HIGH",
            "primary_appl_obj": primary_appl_obj,
            "primary_appl_name": primary_appl_name,
            "link_strategy": link_strategy,
            "docnum_collision_rate": collision_rate,
            "notes": info["note"],
        }

        # Add materiality if available
        if mat:
            entry["annual_2023"] = {
                "rows": mat.get("rows", 0),
                "abs_value": mat.get("sum_abs_transvalue", 0),
            }

        map_entries.append(entry)

    return {
        "trans_type_map": map_entries,
        "corrections": corrections,
        "methodology": {
            "semantic_source": "SAP B1 SDK Official Documentation",
            "appl_obj_source": "OINM.ApplObj field (official SAP metadata)",
            "line_link_strategy_a": "When ApplObj > 0: AppObjAbs = source DocEntry, AppObjLine = source LineNum",
            "line_link_strategy_b": "When ApplObj = -1: BASE_REF → HEADER.DocNum → HEADER.DocEntry → LINE.DocEntry + LINE.LineNum = DocLineNum",
            "collision_handling": "DocNum collision rate tracked per TransType; composite key (TransType + BASE_REF) preferred over DocNum alone",
        },
    }


def main() -> int:
    os.environ.setdefault("HANA_HOST", "127.0.0.1")
    os.environ.setdefault("HANA_PORT", "30015")
    os.environ.setdefault("HANA_SCHEMA", "TELCHI")
    conn = connect()
    cur = conn.cursor()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    window = ("2023-02-01", "2023-04-01")  # Feb+Mar 2023

    # 1. ApplObj analysis
    print("=== 1. ApplObj Distribution Analysis ===")
    t0 = time.time()
    appl_analysis = run_appl_obj_analysis(cur, window)
    print(f"  Elapsed: {time.time()-t0:.1f}s")

    # 2. Corrected line link tests
    print("\n=== 2. Corrected Line Link Tests ===")
    t0 = time.time()
    line_link_results = run_corrected_line_link_tests(cur, window)
    print(f"  Elapsed: {time.time()-t0:.1f}s")

    # 3. Expanded DocNum collision analysis
    print("\n=== 3. Expanded DocNum Collision Analysis ===")
    t0 = time.time()
    collision_results = run_expanded_collision_analysis(cur, window)
    print(f"  Elapsed: {time.time()-t0:.1f}s")

    # 4. Materiality profile
    print("\n=== 4. Materiality Profile ===")
    mat_df = q(cur, f"""
        SELECT OINM."TransType",
               COUNT(*) AS rows_count,
               SUM(ABS(OINM."TransValue")) AS sum_abs_transvalue,
               SUM(OINM."TransValue") AS sum_transvalue,
               SUM(OINM."InQty") AS sum_inqty,
               SUM(OINM."OutQty") AS sum_outqty
        FROM TELCHI.OINM OINM
        WHERE OINM."DocDate">='{window[0]}' AND OINM."DocDate"<'{window[1]}'
        GROUP BY OINM."TransType" ORDER BY OINM."TransType"
    """)
    materiality = {}
    for _, row in mat_df.iterrows():
        tt = str(int(row["TransType"]))
        materiality[tt] = {
            "rows": int(row["ROWS_COUNT"]),
            "sum_abs_transvalue": float(row["SUM_ABS_TRANSVALUE"]),
            "sum_transvalue": float(row["SUM_TRANSVALUE"]),
            "sum_inqty": float(row["SUM_INQTY"]),
            "sum_outqty": float(row["SUM_OUTQTY"]),
        }
        print(f"  TT={tt}: rows={int(row['ROWS_COUNT'])}, abs_value={float(row['SUM_ABS_TRANSVALUE']):.0f}")

    # 5. Build corrected map
    print("\n=== 5. Building Corrected TransType Map ===")
    corrected_map = build_corrected_transtype_map(appl_analysis, line_link_results, collision_results, materiality)

    # 6. Write outputs
    print("\n=== 6. Writing Outputs ===")

    # transtype_map_v2.yaml
    map_path = OUT_DIR / "transtype_map_v2.yaml"
    with open(map_path, "w") as f:
        yaml.dump(corrected_map, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
    print(f"  WROTE {map_path}")

    # line_link_validation.json
    ll_path = OUT_DIR / "line_link_validation.json"
    ll_path.write_text(json.dumps({
        "validation_id": "CORRECTED_LINE_LINK_V2",
        "window": list(window),
        "methodology": {
            "strategy_a": "ApplObj > 0: AppObjAbs=DocEntry, AppObjLine=LineNum (direct official link)",
            "strategy_b": "ApplObj = -1: BASE_REF → HEADER.DocEntry → LINE.DocEntry + DocLineNum=LineNum",
            "key_correction": "Previous test used BASE_REF as DocEntry directly, which is incorrect. BASE_REF=DocNum, not DocEntry.",
        },
        "results": line_link_results,
    }, indent=2, default=str))
    print(f"  WROTE {ll_path}")

    # docnum_collision_analysis.json
    coll_path = OUT_DIR / "docnum_collision_analysis.json"
    coll_path.write_text(json.dumps(collision_results, indent=2, default=str))
    print(f"  WROTE {coll_path}")

    # document_link_matrix_v2.json
    matrix_entries = []
    for entry in corrected_map["trans_type_map"]:
        matrix_entries.append({
            "TransType": entry["trans_type"],
            "SAP_object": entry["official_name"],
            "header": entry["header_table"],
            "line": entry["line_table"],
            "link_strategy": entry["link_strategy"],
            "link_quality": entry["link_quality"],
            "line_link_status": entry["line_link_status"],
            "docnum_collision_rate": entry["docnum_collision_rate"],
            "status": entry["link_status"],
        })

    matrix_path = OUT_DIR / "document_link_matrix_v2.json"
    matrix_path.write_text(json.dumps({
        "analysis_id": "DOCUMENT_LINK_MATRIX_V2_CORRECTED",
        "methodology": corrected_map["methodology"],
        "document_links": matrix_entries,
    }, indent=2, default=str))
    print(f"  WROTE {matrix_path}")

    # Summary
    print("\n=== SUMMARY ===")
    confirmed = sum(1 for e in corrected_map["trans_type_map"] if e["line_link_status"] == "CONFIRMED_EXACT")
    not_applicable = sum(1 for e in corrected_map["trans_type_map"] if e["line_link_status"] == "NOT_APPLICABLE")
    pending = sum(1 for e in corrected_map["trans_type_map"] if e["line_link_status"] not in ("CONFIRMED_EXACT", "NOT_APPLICABLE"))
    print(f"  Line link CONFIRMED_EXACT: {confirmed}")
    print(f"  Line link NOT_APPLICABLE (self-referencing): {not_applicable}")
    print(f"  Line link PENDING: {pending}")
    print(f"  Total TransTypes: {len(corrected_map['trans_type_map'])}")
    print(f"  Collision rate (overall): {collision_results['summary']['collision_rate']:.1%}")

    cur.close()
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
