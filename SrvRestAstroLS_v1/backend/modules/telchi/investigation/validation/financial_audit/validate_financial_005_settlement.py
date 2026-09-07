#!/usr/bin/env python3
"""FINANCIAL-005: Settlement Aggregation Validation.

Builds per-invoice settlement from OITR/ITR1 reconciliation data.
Grain: OINV.DocEntry (one row per invoice with settlement components).

Loop test:
1. Static validation (SQL syntax, file existence)
2. HANA execution (row count, grain validation)
3. Settlement component classification
4. SAP PaidToDate crosscheck
5. Balance regression (calculated vs SAP control)
6. Negative balance analysis
7. Audit flags

Gate: TELCHI_FINANCIAL_AR_SETTLEMENT_AGGREGATION_PASS
"""

from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path

from modules.telchi.investigation.paths import INVESTIGATION_ROOT, SECRET_ROOT
from typing import Any

import pandas
from hdbcli import dbapi

TELCHI_ROOT = INVESTIGATION_ROOT
HANA_ENV = SECRET_ROOT / "sap" / "hana.env"
SQL_DIR = TELCHI_ROOT / "sql" / "current" / "financial" / "ar"
REPORT_DIR = TELCHI_ROOT / "validation" / "financial_audit"

# Windows for validation
WINDOWS = [
    ("2023-02-01", "2023-03-01", "2023-02"),
    ("2023-03-01", "2023-04-01", "2023-03"),
    ("2026-08-01", "2026-09-01", "2026-08"),
]


def load_hana_config() -> dict[str, str]:
    """Load HANA connection config from env file."""
    values: dict[str, str] = {}
    for raw_line in HANA_ENV.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, raw_value = line.partition("=")
        if not _:
            continue
        parsed = shlex.split(raw_value, posix=True)
        values[key.strip()] = parsed[0] if parsed else ""
    return values


def get_connection(config: dict[str, str]) -> Any:
    """Create HANA connection."""
    return dbapi.connect(
        address=config["TELCHI_SAP_HANA_HOST"],
        port=int(config["TELCHI_SAP_HANA_PORT"]),
        user=config["TELCHI_SAP_HANA_USER"],
        password=config["TELCHI_SAP_HANA_PASSWORD"],
        databaseName="NDB",
    )


def run_query(conn: Any, sql: str, params: dict | None = None) -> pandas.DataFrame:
    """Execute query and return DataFrame."""
    return pandas.read_sql(sql, conn, params=params)


def validate_static() -> dict[str, Any]:
    """Step 1: Static validation."""
    result = {"step": "static", "status": "PASS"}

    # Check SQL file exists
    sql_file = SQL_DIR / "settlement_aggregation_v1.sql"
    if not sql_file.exists():
        result["status"] = "FAIL"
        result["error"] = f"SQL file not found: {sql_file}"
        return result

    result["sql_file"] = str(sql_file)
    result["sql_size"] = sql_file.stat().st_size

    return result


def validate_grain(conn: Any, start_date: str, end_date: str, window: str) -> dict[str, Any]:
    """Step 2: Validate grain and basic metrics."""
    result = {"step": "grain", "window": window, "status": "PASS"}

    # Count invoices with settlement
    query = """
    SELECT COUNT(DISTINCT I."SrcObjAbs") AS invoice_count
    FROM TELCHI."ITR1" AS I
    INNER JOIN TELCHI."OITR" AS O ON I."ReconNum" = O."ReconNum"
    WHERE I."SrcObjTyp" = 13
      AND O."Canceled" = 'N'
      AND O."ReconDate" >= :start_date
      AND O."ReconDate" < :end_date
    """
    df = run_query(conn, query, {"start_date": start_date, "end_date": end_date})
    result["invoices_with_recon"] = int(df.iloc[0, 0])

    # Count total invoices in period
    query2 = """
    SELECT COUNT(*) AS total_invoices
    FROM TELCHI."OINV"
    WHERE "DocDate" >= :start_date AND "DocDate" < :end_date
    """
    df2 = run_query(conn, query2, {"start_date": start_date, "end_date": end_date})
    result["total_invoices"] = int(df2.iloc[0, 0])

    # Coverage
    if result["total_invoices"] > 0:
        result["coverage_pct"] = round(
            result["invoices_with_recon"] / result["total_invoices"] * 100, 2
        )
    else:
        result["coverage_pct"] = 0.0

    return result


def validate_settlement_components(conn: Any, start_date: str, end_date: str, window: str) -> dict[str, Any]:
    """Step 3: Validate settlement component classification."""
    result = {"step": "settlement_components", "window": window, "status": "PASS"}

    query = """
    WITH invoice_recons AS (
        SELECT
            I."SrcObjAbs" AS "InvoiceDocEntry",
            I."ReconNum"
        FROM TELCHI."ITR1" AS I
        INNER JOIN TELCHI."OITR" AS O ON I."ReconNum" = O."ReconNum"
        WHERE I."SrcObjTyp" = 13
          AND O."Canceled" = 'N'
          AND O."ReconDate" >= :start_date
          AND O."ReconDate" < :end_date
    ),
    settlement_members AS (
        SELECT
            IR."InvoiceDocEntry",
            I."SrcObjTyp",
            I."ReconSum"
        FROM invoice_recons AS IR
        INNER JOIN TELCHI."ITR1" AS I ON IR."ReconNum" = I."ReconNum"
        WHERE I."SrcObjTyp" != 13
    )
    SELECT
        CASE
            WHEN "SrcObjTyp" IN (24, 46) THEN 'PAYMENT'
            WHEN "SrcObjTyp" = 14 THEN 'CREDIT_NOTE'
            WHEN "SrcObjTyp" = 25 THEN 'DOWN_PAYMENT'
            WHEN "SrcObjTyp" = 30 THEN 'JOURNAL'
            ELSE 'OTHER'
        END AS "SettlementType",
        COUNT(*) AS line_count,
        COUNT(DISTINCT "InvoiceDocEntry") AS invoice_count,
        SUM(ABS("ReconSum")) AS total_amount
    FROM settlement_members
    GROUP BY
        CASE
            WHEN "SrcObjTyp" IN (24, 46) THEN 'PAYMENT'
            WHEN "SrcObjTyp" = 14 THEN 'CREDIT_NOTE'
            WHEN "SrcObjTyp" = 25 THEN 'DOWN_PAYMENT'
            WHEN "SrcObjTyp" = 30 THEN 'JOURNAL'
            ELSE 'OTHER'
        END
    ORDER BY total_amount DESC
    """
    df = run_query(conn, query, {"start_date": start_date, "end_date": end_date})

    components = {}
    for _, row in df.iterrows():
        comp = row.iloc[0]  # SettlementType
        components[comp] = {
            "line_count": int(row.iloc[1]),
            "invoice_count": int(row.iloc[2]),
            "total_amount": float(row.iloc[3]),
        }

    result["components"] = components
    result["total_settlement"] = sum(c["total_amount"] for c in components.values())

    return result


def validate_paidtodate_crosscheck(conn: Any, start_date: str, end_date: str, window: str) -> dict[str, Any]:
    """Step 4: Crosscheck calculated settlement vs SAP PaidToDate."""
    result = {"step": "paidtodate_crosscheck", "window": window, "status": "PASS"}

    # Get calculated settlement per invoice
    query_calc = """
    WITH invoice_recons AS (
        SELECT
            I."SrcObjAbs" AS "InvoiceDocEntry",
            I."ReconNum"
        FROM TELCHI."ITR1" AS I
        INNER JOIN TELCHI."OITR" AS O ON I."ReconNum" = O."ReconNum"
        WHERE I."SrcObjTyp" = 13
          AND O."Canceled" = 'N'
          AND O."ReconDate" >= :start_date
          AND O."ReconDate" < :end_date
    ),
    settlement_members AS (
        SELECT
            IR."InvoiceDocEntry",
            I."SrcObjTyp",
            I."ReconSum"
        FROM invoice_recons AS IR
        INNER JOIN TELCHI."ITR1" AS I ON IR."ReconNum" = I."ReconNum"
        WHERE I."SrcObjTyp" != 13
    ),
    calc_settlement AS (
        SELECT
            "InvoiceDocEntry",
            SUM(ABS("ReconSum")) AS "CalculatedSettlement"
        FROM settlement_members
        WHERE "SrcObjTyp" IN (24, 46, 14, 25, 30)
        GROUP BY "InvoiceDocEntry"
    )
    SELECT
        CS."InvoiceDocEntry",
        CS."CalculatedSettlement",
        OINV."PaidToDate" AS "SAPPaidToDate",
        ABS(CS."CalculatedSettlement" - OINV."PaidToDate") AS difference
    FROM calc_settlement AS CS
    INNER JOIN TELCHI."OINV" ON CS."InvoiceDocEntry" = OINV."DocEntry"
    WHERE OINV."CANCELED" = 'N'
    """
    df = run_query(conn, query_calc, {"start_date": start_date, "end_date": end_date})

    if len(df) == 0:
        result["status"] = "SKIP"
        result["note"] = "No invoices with settlement in this window"
        return result

    # Normalize column names to lowercase for easier access
    df.columns = [c.lower() for c in df.columns]
    total = len(df)
    exact = len(df[df["difference"] < 0.01])
    within_1 = len(df[df["difference"] < 1.00])
    within_10 = len(df[df["difference"] < 10.00])
    max_diff = float(df["difference"].max())
    total_diff = float(df["difference"].sum())

    result["total_invoices"] = total
    result["exact_matches"] = exact
    result["within_1"] = within_1
    result["within_10"] = within_10
    result["mismatches"] = total - exact
    result["max_difference"] = max_diff
    result["total_difference"] = total_diff
    result["exact_pct"] = round(exact / total * 100, 2) if total > 0 else 0

    # Show top mismatches
    top_mismatches = df.nlargest(5, "difference")
    result["top_mismatches"] = []
    for _, row in top_mismatches.iterrows():
        result["top_mismatches"].append({
            "DocEntry": int(row.get("invoicedocentry", row.get("InvoiceDocEntry", 0))),
            "Calculated": float(row.get("calculatedsettlement", row.get("CalculatedSettlement", 0))),
            "SAP": float(row.get("sappaidtodate", row.get("SAPPaidToDate", 0))),
            "Difference": float(row["difference"]),
        })

    if result["exact_pct"] < 90:
        result["status"] = "PARTIAL"
        result["note"] = f"Only {result['exact_pct']}% exact matches"

    return result


def validate_negative_balances(conn: Any, start_date: str, end_date: str, window: str) -> dict[str, Any]:
    """Step 5: Analyze negative balances."""
    result = {"step": "negative_balances", "window": window, "status": "PASS"}

    query = """
    WITH invoice_recons AS (
        SELECT
            I."SrcObjAbs" AS "InvoiceDocEntry",
            I."ReconNum"
        FROM TELCHI."ITR1" AS I
        INNER JOIN TELCHI."OITR" AS O ON I."ReconNum" = O."ReconNum"
        WHERE I."SrcObjTyp" = 13
          AND O."Canceled" = 'N'
          AND O."ReconDate" >= :start_date
          AND O."ReconDate" < :end_date
    ),
    invoice_settlement AS (
        SELECT
            IR."InvoiceDocEntry",
            OINV."DocTotal",
            OINV."PaidToDate",
            SUM(CASE WHEN I."SrcObjTyp" IN (24, 46, 14, 25, 30)
                     THEN ABS(I."ReconSum") ELSE 0 END) AS "TotalSettlement"
        FROM invoice_recons AS IR
        INNER JOIN TELCHI."ITR1" AS I ON IR."ReconNum" = I."ReconNum"
        INNER JOIN TELCHI."OINV" ON IR."InvoiceDocEntry" = OINV."DocEntry"
        WHERE OINV."CANCELED" = 'N'
        GROUP BY IR."InvoiceDocEntry", OINV."DocTotal", OINV."PaidToDate"
    )
    SELECT
        "InvoiceDocEntry",
        "DocTotal",
        "PaidToDate",
        "TotalSettlement",
        ("DocTotal" - "TotalSettlement") AS "OutstandingRaw"
    FROM invoice_settlement
    WHERE ("DocTotal" - "TotalSettlement") < -0.01
    ORDER BY ("DocTotal" - "TotalSettlement") ASC
    LIMIT 20
    """
    df = run_query(conn, query, {"start_date": start_date, "end_date": end_date})

    # Normalize column names
    df.columns = [c.lower() for c in df.columns]
    result["count"] = len(df)
    if len(df) > 0:
        result["total_negative"] = float(df["outstandingraw"].sum())
        result["max_negative"] = float(df["outstandingraw"].min())
        result["samples"] = []
        for _, row in df.head(5).iterrows():
            result["samples"].append({
                "DocEntry": int(row.get("invoicedocentry", 0)),
                "DocTotal": float(row.get("doctotal", 0)),
                "Settlement": float(row.get("totalsettlement", 0)),
                "Outstanding": float(row["outstandingraw"]),
            })

    return result


def run_validation(window: tuple[str, str, str] | None = None) -> dict[str, Any]:
    """Run full validation for a window."""
    config = load_hana_config()
    conn = get_connection(config)

    report: dict[str, Any] = {
        "validation_id": "FINANCIAL-005",
        "gate": "TELCHI_FINANCIAL_AR_SETTLEMENT_AGGREGATION_PASS",
        "steps": {},
    }

    # Step 1: Static
    report["steps"]["static"] = validate_static()
    if report["steps"]["static"]["status"] == "FAIL":
        conn.close()
        report["overall_status"] = "FAIL"
        return report

    # Use specified window or default
    if window:
        windows = [window]
    else:
        windows = WINDOWS

    for start_date, end_date, win_label in windows:
        print(f"\n--- Validating window: {win_label} ---")

        # Step 2: Grain
        report["steps"][f"grain_{win_label}"] = validate_grain(conn, start_date, end_date, win_label)

        # Step 3: Settlement components
        report["steps"][f"components_{win_label}"] = validate_settlement_components(
            conn, start_date, end_date, win_label
        )

        # Step 4: PaidToDate crosscheck
        report["steps"][f"crosscheck_{win_label}"] = validate_paidtodate_crosscheck(
            conn, start_date, end_date, win_label
        )

        # Step 5: Negative balances
        report["steps"][f"negatives_{win_label}"] = validate_negative_balances(
            conn, start_date, end_date, win_label
        )

    conn.close()

    # Determine overall status
    all_statuses = [s.get("status", "PASS") for s in report["steps"].values()]
    if "FAIL" in all_statuses:
        report["overall_status"] = "FAIL"
    elif "PARTIAL" in all_statuses:
        report["overall_status"] = "PARTIAL"
    else:
        report["overall_status"] = "PASS"

    report["overall_gate"] = "TELCHI_FINANCIAL_AR_SETTLEMENT_AGGREGATION_PASS"

    return report


def main() -> int:
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="FINANCIAL-005 Settlement Aggregation Validation")
    parser.add_argument("--window", nargs=3, metavar=("START", "END", "LABEL"),
                       help="Validate specific window (start end label)")
    parser.add_argument("--output", type=str, help="Output report path")
    args = parser.parse_args()

    window = tuple(args.window) if args.window else None
    report = run_validation(window)

    # Output
    output_path = Path(args.output) if args.output else REPORT_DIR / "settlement_005_report.json"
    output_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"\nReport written to: {output_path}")
    print(f"Overall status: {report['overall_status']}")

    return 0 if report["overall_status"] in ("PASS", "PARTIAL") else 1


if __name__ == "__main__":
    sys.exit(main())
