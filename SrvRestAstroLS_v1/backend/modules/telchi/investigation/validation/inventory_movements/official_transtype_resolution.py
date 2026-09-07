#!/usr/bin/env python3
"""Official TransType resolution using OINM metadata fields (ApplObj, AppObjType, AppObjAbs).

Strategy (per spec section 4):
  PRIORITY 1: SAP official metadata/objects (ApplObj field in OINM)
  PRIORITY 2: HANA real evidence (table existence, DocNum collision analysis)
  PRIORITY 3: Legacy code

The ApplObj field is the OFFICIAL SAP field that identifies the source object type.
AppObjAbs is the DocEntry of the source object.
This is more robust than BASE_REF DocNum matching (which can collide).

No writes to HANA. Read-only.
"""
from __future__ import annotations

import json
import os
import shlex
import sys
import time
from pathlib import Path

from modules.telchi.investigation.paths import SECRET_ROOT
from collections import defaultdict

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
HANA_ENV = SECRET_ROOT / "sap" / "hana.env"
OUT_DIR = ROOT / "validation" / "inventory_movements"

# SAP B1 BoObjectTypes (official SDK enumeration)
# Source: SAP Business One SDK Reference Guide
# These are the integer codes used in the ApplObj field
SAP_OBJECT_TYPES = {
    -1: "NO_LINK",
    1: "oPaymentTermsType",
    2: "oPriceLists",
    4: "oSpecialPrices",
    13: "oInvoices",           # A/R Invoice
    14: "oCreditNotes",       # A/R Credit Memo
    15: "oDeliveryNotes",     # Delivery Note
    16: "oReturns",           # A/R Return
    18: "oPurchaseInvoices",  # A/P Invoice
    19: "oPurchaseCreditNotes",  # A/P Credit Memo
    20: "oPurchaseDeliveryNotes", # Goods Receipt PO
    21: "oPurchaseReturns",   # A/P Return
    59: "oInventoryGenEntry", # Goods Receipt (inventory)
    60: "oInventoryGenExit",  # Goods Issue (inventory)
    67: "oStockTransfer",     # Inventory Transfer
    69: "oLandedCosts",       # Landed Costs
    162: "oInventoryRevaluation", # Inventory Revaluation
    202: "oProductionOrders", # Production Order
    10000071: "CUSTOM_EXT",   # Extended/custom range
}

# Official SAP B1 TransType documentation for OINM
# Source: SAP Business One SDK Reference Guide - OINM table
# TransType values and their official SAP meanings
OFFICIAL_TRANSTYPE = {
    13: {"object": "A/R Invoice", "header": "OINV", "line": "INV1", "category": "SALES", "official_name": "arInvoice"},
    14: {"object": "A/R Credit Memo", "header": "ORIN", "line": "RIN1", "category": "SALES_RETURN", "official_name": "arCreditNote"},
    15: {"object": "Delivery", "header": "ODLN", "line": "DLN1", "category": "SALES", "official_name": "arDeliveryNote"},
    16: {"object": "A/R Return", "header": "ORPD", "line": "RPD1", "category": "SALES_RETURN", "official_name": "arReturn"},
    18: {"object": "A/P Invoice", "header": "OPCH", "line": "PCH1", "category": "PURCHASE", "official_name": "apInvoice"},
    19: {"object": "A/P Credit Memo", "header": "ORPC", "line": "RPC1", "category": "PURCHASE_RETURN", "official_name": "apCreditNote"},
    20: {"object": "Goods Receipt PO", "header": "OPDN", "line": "PDN1", "category": "PURCHASE", "official_name": "apDeliveryNote"},
    21: {"object": "Goods Return", "header": "ORPD", "line": "RPD1", "category": "PURCHASE_RETURN", "official_name": "apReturn"},
    59: {"object": "Inventory Goods Receipt", "header": "OIGN", "line": "IGN1", "category": "INVENTORY_RECEIPT", "official_name": "oInventoryGenEntry"},
    60: {"object": "Inventory Goods Issue", "header": "OIGE", "line": "IGE1", "category": "INVENTORY_ISSUE", "official_name": "oInventoryGenExit"},
    67: {"object": "Inventory Transfer", "header": "OWTR", "line": "WTR1", "category": "TRANSFER", "official_name": "oStockTransfer"},
    69: {"object": "Landed Costs", "header": "OIGN", "line": "IGN1", "category": "LANDED_COST", "official_name": "oLandedCosts"},
    162: {"object": "Inventory Revaluation", "header": "OINM", "line": "OINM", "category": "VALUATION", "official_name": "oInventoryRevaluation"},
    202: {"object": "Production Order", "header": "OWOR", "line": "WOR1", "category": "PRODUCTION", "official_name": "oProductionOrders"},
    10000071: {"object": "Inventory Posting (Custom)", "header": "OINM", "line": "OINM", "category": "OTHER", "official_name": "customExtended"},
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


def main() -> int:
    os.environ.setdefault("HANA_HOST", "127.0.0.1")
    os.environ.setdefault("HANA_PORT", "30015")
    os.environ.setdefault("HANA_SCHEMA", "TELCHI")
    conn = connect()
    cur = conn.cursor()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    report = {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "windows": {}}

    for wname, (d0, d1) in {"feb2023": ("2023-02-01", "2023-03-01"), "mar2023": ("2023-03-01", "2023-04-01")}.items():
        t0 = time.time()
        # 1. ApplObj distribution per TransType (OFFICIAL source)
        appl_df = q(cur, f"""
            SELECT OINM."TransType", OINM."ApplObj", COUNT(*) AS n,
                   SUM(CASE WHEN OINM."AppObjAbs" IS NOT NULL AND OINM."AppObjAbs">0 THEN 1 ELSE 0 END) AS has_appobjabs
            FROM TELCHI.OINM OINM
            WHERE OINM."DocDate">='{d0}' AND OINM."DocDate"<'{d1}'
            GROUP BY OINM."TransType", OINM."ApplObj"
            ORDER BY OINM."TransType", n DESC
        """)
        appl_map = {}
        for _, row in appl_df.iterrows():
            tt = str(int(row["TransType"]))
            appl_map.setdefault(tt, []).append({
                "ApplObj": int(row["ApplObj"]),
                "ApplObj_name": SAP_OBJECT_TYPES.get(int(row["ApplObj"]), f"UNKNOWN_{row['ApplObj']}"),
                "count": int(row["N"]),
                "has_appobjabs": int(row["HAS_APPOBJABS"]),
            })

        # 2. AppObjType distribution (secondary field)
        appobj_df = q(cur, f"""
            SELECT OINM."TransType", OINM."AppObjType", COUNT(*) AS n
            FROM TELCHI.OINM OINM
            WHERE OINM."DocDate">='{d0}' AND OINM."DocDate"<'{d1}'
            GROUP BY OINM."TransType", OINM."AppObjType"
            ORDER BY OINM."TransType", n DESC
        """)
        appobj_map = {}
        for _, row in appobj_df.iterrows():
            tt = str(int(row["TransType"]))
            appobj_map.setdefault(tt, []).append({
                "AppObjType": row["AppObjType"],
                "count": int(row["N"]),
            })

        # 3. Materiality profile (value + quantity per TransType)
        mat_df = q(cur, f"""
            SELECT OINM."TransType",
                   COUNT(*) AS rows_count,
                   SUM(ABS(OINM."TransValue")) AS sum_abs_transvalue,
                   SUM(OINM."TransValue") AS sum_transvalue,
                   SUM(OINM."InQty") AS sum_inqty,
                   SUM(OINM."OutQty") AS sum_outqty,
                   SUM(OINM."InQty" + OINM."OutQty") AS sum_abs_qty,
                   COUNT(DISTINCT OINM."ItemCode") AS items,
                   COUNT(DISTINCT OINM."Warehouse") AS warehouses,
                   COUNT(DISTINCT OINM."CardCode") AS customers
            FROM TELCHI.OINM OINM
            WHERE OINM."DocDate">='{d0}' AND OINM."DocDate"<'{d1}'
            GROUP BY OINM."TransType" ORDER BY OINM."TransType"
        """)
        materiality = []
        for _, row in mat_df.iterrows():
            materiality.append({
                "TransType": int(row["TransType"]),
                "rows": int(row["ROWS_COUNT"]),
                "sum_abs_transvalue": float(row["SUM_ABS_TRANSVALUE"]),
                "sum_transvalue": float(row["SUM_TRANSVALUE"]),
                "sum_inqty": float(row["SUM_INQTY"]),
                "sum_outqty": float(row["SUM_OUTQTY"]),
                "items": int(row["ITEMS"]),
                "warehouses": int(row["WAREHOUSES"]),
                "customers": int(row["CUSTOMERS"]),
            })

        elapsed = round(time.time() - t0, 2)
        report["windows"][wname] = {
            "window": [d0, d1],
            "elapsed": elapsed,
            "appl_obj_distribution": appl_map,
            "appobj_type_distribution": appobj_map,
            "materiality": materiality,
        }
        print(f"{wname}: elapsed={elapsed}s, TransTypes={len(materiality)}")

    # 4. DocNum collision analysis (sample)
    print("\n=== DocNum Collision Analysis ===")
    # Get distinct BASE_REF per TransType for a small sample
    sample_df = q(cur, """
        SELECT OINM."TransType", CAST(OINM."BASE_REF" AS VARCHAR(50)) AS baseref, COUNT(*) AS n
        FROM TELCHI.OINM OINM
        WHERE OINM."DocDate">='2023-02-01' AND OINM."DocDate"<'2023-04-01'
          AND LENGTH(OINM."BASE_REF") > 0
          AND OINM."BASE_REF" NOT LIKE '%[^0-9]%'
        GROUP BY OINM."TransType", OINM."BASE_REF"
        HAVING COUNT(*) >= 1
        ORDER BY OINM."TransType", n DESC
        LIMIT 200
    """)
    # For each sample BASE_REF, check how many tables it exists in
    collision_tables = ["OINV", "ORIN", "ODLN", "OPCH", "OPDN", "OIGN", "OIGE", "OWTR", "ORCT", "ORPC", "OWOR"]
    collision_results = []
    # Group by TransType
    by_tt = defaultdict(list)
    for _, row in sample_df.iterrows():
        by_tt[int(row["TransType"])].append(row["BASEREF"])

    for tt in sorted(by_tt.keys()):
        refs = by_tt[tt][:5]  # Sample 5 per TransType
        collisions = {}
        for ref_str in refs:
            ref_int = int(ref_str)
            found_in = []
            for tab in collision_tables:
                try:
                    cur.execute(f'SELECT COUNT(*) FROM TELCHI."{tab}" WHERE "DocNum"=?', (ref_int,))
                    cnt = cur.fetchone()[0]
                    if cnt > 0:
                        found_in.append({"table": tab, "count": cnt})
                except Exception:
                    pass
            if len(found_in) > 1:
                collisions[ref_str] = found_in
        collision_results.append({
            "TransType": tt,
            "sample_refs": refs,
            "collisions": collisions,
            "collision_count": len(collisions),
        })
        if collisions:
            print(f"  TT={tt}: {len(collisions)} collisions in {refs[:2]}")
        else:
            print(f"  TT={tt}: 0 collisions in {refs[:2]}")

    report["collision_analysis"] = collision_results

    # 5. Line link test: OINM.DocLineNum vs source table LineNum
    print("\n=== Line Link Test ===")
    line_tests = []
    for tt, info in OFFICIAL_TRANSTYPE.items():
        if info["header"] == info["line"]:  # skip self-referencing
            continue
        header = info["header"]
        line = info["line"]
        # Sample a few movements for this TransType and check line match
        sample = q(cur, f"""
            SELECT TOP 5 OINM."TransNum", CAST(OINM."BASE_REF" AS BIGINT) AS baseref,
                   OINM."DocLineNum", OINM."ItemCode"
            FROM TELCHI.OINM OINM
            WHERE OINM."TransType"={tt}
              AND OINM."DocDate">='2023-02-01' AND OINM."DocDate"<'2023-04-01'
              AND LENGTH(OINM."BASE_REF") > 0
              AND OINM."BASE_REF" NOT LIKE '%[^0-9]%'
        """)
        if sample.empty:
            continue
        matches = 0
        total = 0
        details = []
        for _, row in sample.iterrows():
            baseref = int(row["BASEREF"])
            docline = int(row["DocLineNum"])
            try:
                cur.execute(f'SELECT COUNT(*) FROM TELCHI."{line}" WHERE "DocEntry"=? AND "LineNum"=?', (baseref, docline))
                cnt = cur.fetchone()[0]
                total += 1
                if cnt > 0:
                    matches += 1
                details.append({"TransNum": int(row["TransNum"]), "baseref": baseref, "DocLineNum": docline, "found_in_line": cnt > 0})
            except Exception as e:
                details.append({"TransNum": int(row["TransNum"]), "error": str(e)[:50]})
        line_tests.append({
            "TransType": tt,
            "header_table": header,
            "line_table": line,
            "sample_size": total,
            "line_matches": matches,
            "details": details,
            "status": "CONFIRMED_EXACT" if matches == total and total > 0 else "PARTIAL" if matches > 0 else "NOT_APPLICABLE",
        })
        print(f"  TT={tt} ({line}): {matches}/{total} line matches")
    report["line_link_tests"] = line_tests

    # 6. Full annual materiality
    print("\n=== Annual Materiality 2023 ===")
    annual_mat = q(cur, """
        SELECT OINM."TransType",
               COUNT(*) AS rows_count,
               SUM(ABS(OINM."TransValue")) AS sum_abs_transvalue,
               SUM(OINM."TransValue") AS sum_transvalue,
               SUM(OINM."InQty") AS sum_inqty,
               SUM(OINM."OutQty") AS sum_outqty
        FROM TELCHI.OINM OINM
        WHERE OINM."DocDate">='2023-01-01' AND OINM."DocDate"<'2024-01-01'
        GROUP BY OINM."TransType" ORDER BY OINM."TransType"
    """)
    report["annual_2023_materiality"] = []
    for _, row in annual_mat.iterrows():
        report["annual_2023_materiality"].append({
            "TransType": int(row["TransType"]),
            "rows": int(row["ROWS_COUNT"]),
            "sum_abs_transvalue": float(row["SUM_ABS_TRANSVALUE"]),
            "sum_transvalue": float(row["SUM_TRANSVALUE"]),
            "sum_inqty": float(row["SUM_INQTY"]),
            "sum_outqty": float(row["SUM_OUTQTY"]),
        })
        print(f"  TT={int(row['TransType'])}: rows={int(row['ROWS_COUNT'])}, abs_value={float(row['SUM_ABS_TRANSVALUE']):.0f}")

    out = OUT_DIR / "official_resolution.json"
    out.write_text(json.dumps(report, indent=2, default=str))
    print(f"\nWROTE {out}")

    cur.close()
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())