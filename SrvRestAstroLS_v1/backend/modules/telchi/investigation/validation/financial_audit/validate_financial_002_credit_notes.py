#!/usr/bin/env python3
"""FINANCIAL-002: Credit Note Contract & Invoice Linkage Validation.

Validates the credit note contract SQL against SAP HANA.
Grain: ORIN.DocEntry (one row per credit note, header level).

Loop test:
1. Static validation (SQL syntax, file existence)
2. Header grain validation (DocEntry uniqueness)
3. Cancellation semantics (CANCELED distribution)
4. Line linkage coverage (BaseType/BaseEntry/BaseLine)
5. Direct invoice link (BaseType=13 → OINV)
6. Sign contract (DocTotal sign)
7. Currency profile
8. Seller attribution
9. Multi-window regression (Feb, Mar, Aug 2026)

Gate: TELCHI_FINANCIAL_CREDIT_NOTE_PASS
"""

from __future__ import annotations

import argparse
import json
import shlex
import sys
from datetime import date, timedelta
from pathlib import Path

from modules.telchi.investigation.paths import INVESTIGATION_ROOT, SECRET_ROOT
from typing import Any

import pandas
from hdbcli import dbapi

TELCHI_ROOT = INVESTIGATION_ROOT
HANA_ENV = SECRET_ROOT / "sap" / "hana.env"
SQL_CURRENT = TELCHI_ROOT / "sql" / "current" / "financial" / "credit_note_contract_v1.sql"
REPORT_DIR = TELCHI_ROOT / "validation" / "financial_audit"


def load_hana_config() -> dict[str, str]:
    """Load HANA connection config from env file."""
    values: dict[str, str] = {}
    for raw_line in HANA_ENV.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, raw_value = line.partition("=")
        if not separator:
            raise ValueError(f"invalid HANA env line: {raw_line}")
        parsed = shlex.split(raw_value, posix=True)
        if len(parsed) != 1:
            raise ValueError(f"invalid HANA env value: {raw_value}")
        values[key] = parsed[0]
    return values


def connect() -> tuple[dbapi.Connection, dbapi.Cursor]:
    """Create HANA connection."""
    config = load_hana_config()
    host = config.get("TELCHI_SAP_HANA_HOST", "127.0.0.1")
    port = int(config.get("TELCHI_SAP_HANA_PORT", "30015"))
    user = config.get("TELCHI_SAP_HANA_USER", "")
    password = config.get("TELCHI_SAP_HANA_PASSWORD", "")
    schema = config.get("TELCHI_SAP_HANA_SCHEMA", "TELCHI")

    conn = dbapi.connect(
        address=host,
        port=port,
        user=user,
        password=password,
        currentSchema=schema,
        encrypt="false",
    )
    cursor = conn.cursor()
    return conn, cursor


def query_frame(cursor: dbapi.Cursor, sql: str, params: tuple | None = None) -> pandas.DataFrame:
    """Execute query and return DataFrame."""
    if params:
        cursor.execute(sql, params)
    else:
        cursor.execute(sql)
    rows = cursor.fetchall()
    columns = [str(desc[0]) for desc in cursor.description or ()]
    return pandas.DataFrame(rows, columns=columns)


def static_validation() -> dict[str, Any]:
    """Step 1: Static validation."""
    result = {"step": "static_validation", "sql_file_exists": SQL_CURRENT.exists()}

    if not SQL_CURRENT.exists():
        result["status"] = "FAIL"
        result["error"] = "SQL file not found"
        return result

    sql_content = SQL_CURRENT.read_text(encoding="utf-8")
    checks = {
        "has_select": "SELECT" in sql_content.upper(),
        "has_from_orin": "FROM TELCHI.ORIN" in sql_content,
        "has_docentry": '"DocEntry"' in sql_content,
        "has_docnum": '"DocNum"' in sql_content,
        "has_cardcode": '"CardCode"' in sql_content,
        "has_slpcode": '"SlpCode"' in sql_content,
        "has_docdate": '"DocDate"' in sql_content,
        "has_docduedate": '"DocDueDate"' in sql_content,
        "has_doctotal": '"DocTotal"' in sql_content,
        "has_canceled": '"CANCELED"' in sql_content,
        "has_where_clause": "WHERE" in sql_content.upper(),
        "has_date_filter": ":start_date" in sql_content and ":end_date" in sql_content,
    }
    result["checks"] = checks
    result["all_pass"] = all(checks.values())
    result["status"] = "PASS" if result["all_pass"] else "FAIL"
    return result


def header_grain(cursor: dbapi.Cursor, window: tuple[str, str]) -> dict[str, Any]:
    """Step 2: Header grain validation."""
    sql = SQL_CURRENT.read_text(encoding="utf-8")
    sql_exec = sql.replace(":start_date", "?").replace(":end_date", "?")
    df = query_frame(cursor, sql_exec, window)

    result = {"step": "header_grain", "grain": "ORIN.DocEntry"}
    if df.empty:
        result["status"] = "EMPTY_WINDOW"
        return result

    docentry_distinct = int(df["DocEntry"].nunique())
    docentry_count = len(df)
    result["row_count"] = docentry_count
    result["docentry_distinct"] = docentry_distinct
    result["duplicates"] = docentry_count - docentry_distinct
    result["grain_unique"] = result["duplicates"] == 0
    result["status"] = "PASS" if result["grain_unique"] else "FAIL"
    return result


def cancellation_semantics(cursor: dbapi.Cursor, window: tuple[str, str]) -> dict[str, Any]:
    """Step 3: Cancellation semantics."""
    sql = SQL_CURRENT.read_text(encoding="utf-8")
    sql_exec = sql.replace(":start_date", "?").replace(":end_date", "?")
    df = query_frame(cursor, sql_exec, window)

    result = {"step": "cancellation_semantics"}
    if df.empty:
        result["status"] = "EMPTY_WINDOW"
        return result

    if "CANCELED" in df.columns:
        canceled_dist = df["CANCELED"].value_counts(dropna=False).to_dict()
        result["canceled_distribution"] = {str(k): int(v) for k, v in canceled_dist.items()}

        stats = {}
        for status in df["CANCELED"].unique():
            subset = df[df["CANCELED"] == status]
            stats[str(status)] = {
                "count": len(subset),
                "total_doc_total": float(subset["DocTotal"].sum()),
            }
        result["stats_by_canceled"] = stats
    result["status"] = "PASS"
    return result


def line_linkage_coverage(cursor: dbapi.Cursor, window: tuple[str, str]) -> dict[str, Any]:
    """Step 4: Line linkage coverage."""
    sql = f"""
        SELECT
            CASE WHEN RIN1."BaseEntry" IS NULL THEN 'NULL' ELSE 'NOT_NULL' END AS baseentry_coverage,
            RIN1."BaseType",
            COUNT(*) AS line_count,
            COUNT(DISTINCT RIN1."DocEntry") AS nc_count
        FROM TELCHI.ORIN AS ORIN
        INNER JOIN TELCHI.RIN1 AS RIN1 ON ORIN."DocEntry" = RIN1."DocEntry"
        WHERE ORIN."DocDate" >= ? AND ORIN."DocDate" < ?
        GROUP BY
            CASE WHEN RIN1."BaseEntry" IS NULL THEN 'NULL' ELSE 'NOT_NULL' END,
            RIN1."BaseType"
        ORDER BY RIN1."BaseType", baseentry_coverage
    """
    df = query_frame(cursor, sql, window)

    result = {"step": "line_linkage_coverage"}
    if df.empty:
        result["status"] = "EMPTY_WINDOW"
        return result

    coverage = {}
    total_lines = 0
    total_with_baseentry = 0
    # Normalize column names to uppercase (HANA returns uppercase)
    df.columns = [c.upper() for c in df.columns]
    for _, row in df.iterrows():
        bt = str(row["BASETYPE"])
        cov = str(row["BASEENTRY_COVERAGE"])
        lines = int(row["LINE_COUNT"])
        nc_count = int(row["NC_COUNT"])
        total_lines += lines
        if cov == "NOT_NULL":
            total_with_baseentry += lines
        if bt not in coverage:
            coverage[bt] = {}
        coverage[bt][cov] = {"lines": lines, "nc_documents": nc_count}

    result["coverage_by_basetype"] = coverage
    result["total_lines"] = total_lines
    result["total_with_baseentry"] = total_with_baseentry
    result["total_without_baseentry"] = total_lines - total_with_baseentry
    result["baseentry_coverage_pct"] = round(
        total_with_baseentry / total_lines * 100 if total_lines > 0 else 0, 2
    )
    result["status"] = "PASS"
    return result


def direct_invoice_link(cursor: dbapi.Cursor, window: tuple[str, str]) -> dict[str, Any]:
    """Step 5: Direct invoice linkage (BaseType=13)."""
    sql = f"""
        SELECT COUNT(*) AS linked_lines,
               COUNT(DISTINCT RIN1."DocEntry") AS nc_documents,
               COUNT(DISTINCT RIN1."BaseEntry") AS source_invoices
        FROM TELCHI.ORIN AS ORIN
        INNER JOIN TELCHI.RIN1 AS RIN1 ON ORIN."DocEntry" = RIN1."DocEntry"
        WHERE ORIN."DocDate" >= ? AND ORIN."DocDate" < ?
          AND RIN1."BaseType" = 13
    """
    df = query_frame(cursor, sql, window)

    result = {"step": "direct_invoice_link"}
    if df.empty:
        result["status"] = "NO_LINKED_LINES"
        return result

    df.columns = [c.upper() for c in df.columns]
    if len(df) == 1 and df.iloc[0]["LINKED_LINES"] == 0:
        result["status"] = "NO_LINKED_LINES"
        return result

    row = df.iloc[0]
    result["linked_lines"] = int(row["LINKED_LINES"])
    result["nc_documents"] = int(row["NC_DOCUMENTS"])
    result["source_invoices"] = int(row["SOURCE_INVOICES"])

    # Check if BaseEntry resolves to valid OINV
    validate_sql = f"""
        SELECT COUNT(*) AS valid_links
        FROM TELCHI.ORIN AS ORIN
        INNER JOIN TELCHI.RIN1 AS RIN1 ON ORIN."DocEntry" = RIN1."DocEntry"
        INNER JOIN TELCHI.OINV AS OINV ON RIN1."BaseEntry" = OINV."DocEntry"
        WHERE ORIN."DocDate" >= ? AND ORIN."DocDate" < ?
          AND RIN1."BaseType" = 13
    """
    df_validate = query_frame(cursor, validate_sql, window)
    if not df_validate.empty:
        df_validate.columns = [c.upper() for c in df_validate.columns]
        result["valid_links"] = int(df_validate.iloc[0]["VALID_LINKS"])
        result["invalid_links"] = result["linked_lines"] - result["valid_links"]
        result["link_validation"] = "PASS" if result["invalid_links"] == 0 else "PARTIAL"

    result["status"] = "PASS"
    return result


def sign_contract(cursor: dbapi.Cursor, window: tuple[str, str]) -> dict[str, Any]:
    """Step 6: Sign contract validation."""
    sql = SQL_CURRENT.read_text(encoding="utf-8")
    sql_exec = sql.replace(":start_date", "?").replace(":end_date", "?")
    df = query_frame(cursor, sql_exec, window)

    result = {"step": "sign_contract"}
    if df.empty:
        result["status"] = "EMPTY_WINDOW"
        return result

    df.columns = [c.upper() for c in df.columns]
    positive = int((df["DOCTOTAL"] > 0).sum())
    negative = int((df["DOCTOTAL"] < 0).sum())
    zero = int((df["DOCTOTAL"] == 0).sum())
    result["sign_distribution"] = {"POSITIVE": positive, "NEGATIVE": negative, "ZERO": zero}
    result["all_positive"] = negative == 0
    result["financial_effect"] = "DocTotal is POSITIVE in SAP; negate for net sales"
    result["status"] = "PASS"
    return result


def currency_profile(cursor: dbapi.Cursor, window: tuple[str, str]) -> dict[str, Any]:
    """Step 7: Currency profile."""
    sql = f"""
        SELECT ORIN."DocCur", COUNT(*) AS nc_count, SUM(ORIN."DocTotal") AS total_amount
        FROM TELCHI.ORIN AS ORIN
        WHERE ORIN."DocDate" >= ? AND ORIN."DocDate" < ?
        GROUP BY ORIN."DocCur"
    """
    df = query_frame(cursor, sql, window)

    result = {"step": "currency_profile"}
    if df.empty:
        result["status"] = "EMPTY_WINDOW"
        return result

    df.columns = [c.upper() for c in df.columns]
    result["currencies"] = {}
    for _, row in df.iterrows():
        result["currencies"][str(row["DOCCUR"])] = {
            "count": int(row["NC_COUNT"]),
            "total_amount": float(row["TOTAL_AMOUNT"]),
        }
    result["single_currency"] = len(result["currencies"]) == 1
    result["status"] = "PASS"
    return result


def seller_attribution(cursor: dbapi.Cursor, window: tuple[str, str]) -> dict[str, Any]:
    """Step 8: Seller attribution profile."""
    sql = f"""
        SELECT
            COUNT(*) AS total_nc_lines,
            SUM(CASE WHEN ORIN."SlpCode" = OINV."SlpCode" THEN 1 ELSE 0 END) AS same_seller,
            SUM(CASE WHEN ORIN."SlpCode" != OINV."SlpCode" THEN 1 ELSE 0 END) AS different_seller,
            COUNT(DISTINCT CASE WHEN ORIN."SlpCode" != OINV."SlpCode"
                  THEN ORIN."DocEntry" END) AS nc_with_seller_mismatch
        FROM TELCHI.ORIN AS ORIN
        INNER JOIN TELCHI.RIN1 AS RIN1 ON ORIN."DocEntry" = RIN1."DocEntry"
        INNER JOIN TELCHI.OINV AS OINV ON RIN1."BaseEntry" = OINV."DocEntry"
        WHERE ORIN."DocDate" >= ? AND ORIN."DocDate" < ?
          AND RIN1."BaseType" = 13
    """
    df = query_frame(cursor, sql, window)

    result = {"step": "seller_attribution"}
    if df.empty:
        result["status"] = "NO_LINKED_LINES"
        return result

    # Normalize column names to uppercase
    df.columns = [c.upper() for c in df.columns]
    row = df.iloc[0]
    result["total_nc_lines"] = int(row["TOTAL_NC_LINES"])
    result["same_seller"] = int(row["SAME_SELLER"])
    result["different_seller"] = int(row["DIFFERENT_SELLER"])
    result["nc_with_seller_mismatch"] = int(row["NC_WITH_SELLER_MISMATCH"])
    result["same_seller_pct"] = round(
        result["same_seller"] / result["total_nc_lines"] * 100
        if result["total_nc_lines"] > 0 else 0, 2
    )
    result["status"] = "PASS"
    return result


def multi_window_regression(cursor: dbapi.Cursor) -> dict[str, Any]:
    """Step 9: Multi-window regression."""
    windows = {"2023-02": ("2023-02-01", "2023-03-01"), "2023-03": ("2023-03-01", "2023-04-01"), "2026-08": ("2026-08-01", "2026-09-01")}
    sql = SQL_CURRENT.read_text(encoding="utf-8")
    sql_exec = sql.replace(":start_date", "?").replace(":end_date", "?")

    result = {"step": "multi_window_regression", "windows": {}}
    for month, window in windows.items():
        df = query_frame(cursor, sql_exec, window)
        if df.empty:
            result["windows"][month] = {"status": "EMPTY_WINDOW"}
            continue
        result["windows"][month] = {
            "row_count": len(df),
            "docentry_distinct": int(df["DocEntry"].nunique()),
            "grain_unique": len(df) == int(df["DocEntry"].nunique()),
            "total_doc_total": float(df["DocTotal"].sum()),
            "canceled_distribution": {str(k): int(v) for k, v in df["CANCELED"].value_counts().items()},
        }
    all_pass = all(
        w.get("grain_unique", False) for w in result["windows"].values() if w.get("status") != "EMPTY_WINDOW"
    )
    result["all_windows_pass"] = all_pass
    result["status"] = "PASS" if all_pass else "FAIL"
    return result


def run_validation(month: str = "2023-02") -> dict[str, Any]:
    """Run full FINANCIAL-002 validation."""
    results: dict[str, Any] = {
        "validation_id": "FINANCIAL-002",
        "gate": "TELCHI_FINANCIAL_CREDIT_NOTE_PASS",
        "month": month,
        "steps": {},
    }

    # Step 1: Static
    results["steps"]["static"] = static_validation()
    if results["steps"]["static"]["status"] != "PASS":
        results["overall_status"] = "FAIL"
        results["overall_gate"] = "TELCHI_FINANCIAL_CREDIT_NOTE_FAIL"
        return results

    try:
        conn, cursor = connect()
    except Exception as e:
        results["overall_status"] = "FAIL"
        results["overall_gate"] = "TELCHI_FINANCIAL_CREDIT_NOTE_BLOCKED"
        results["connection_error"] = str(e)
        return results

    try:
        # Determine window
        year, month_num = (int(p) for p in month.split("-"))
        if month_num == 12:
            next_month = date(year + 1, 1, 1)
        else:
            next_month = date(year, month_num + 1, 1)
        window = (f"{month}-01", next_month.isoformat())
        results["window"] = list(window)

        # Steps 2-8
        results["steps"]["header_grain"] = header_grain(cursor, window)
        results["steps"]["cancellation"] = cancellation_semantics(cursor, window)
        results["steps"]["line_linkage"] = line_linkage_coverage(cursor, window)
        results["steps"]["direct_invoice_link"] = direct_invoice_link(cursor, window)
        results["steps"]["sign_contract"] = sign_contract(cursor, window)
        results["steps"]["currency"] = currency_profile(cursor, window)
        results["steps"]["seller_attribution"] = seller_attribution(cursor, window)

        # Step 9: Multi-window
        results["steps"]["multi_window"] = multi_window_regression(cursor)

    finally:
        cursor.close()
        conn.close()

    # Overall status
    failed = [k for k, v in results["steps"].items() if v["status"] not in ("PASS", "EMPTY_WINDOW", "NO_LINKED_LINES")]
    if not failed:
        results["overall_status"] = "PASS"
        results["overall_gate"] = "TELCHI_FINANCIAL_CREDIT_NOTE_PASS"
    else:
        results["overall_status"] = "FAIL"
        results["overall_gate"] = "TELCHI_FINANCIAL_CREDIT_NOTE_FAIL"
        results["failed_steps"] = failed

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="FINANCIAL-002: Credit Note Validation")
    parser.add_argument("--month", default="2023-02")
    parser.add_argument("--output", "-o")
    args = parser.parse_args()

    results = run_validation(args.month)
    output = json.dumps(results, indent=2, default=str, sort_keys=False)

    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"Results written to {args.output}")
    else:
        print(output)

    print(f"\nGate: {results.get('overall_gate', 'UNKNOWN')}")
    return 0 if results.get("overall_status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
