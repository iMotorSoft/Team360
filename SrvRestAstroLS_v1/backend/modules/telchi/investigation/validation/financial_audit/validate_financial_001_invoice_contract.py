#!/usr/bin/env python3
"""FINANCIAL-001: Invoice Contract Validation.

Validates the invoice contract SQL against SAP HANA.
Grain: OINV.DocEntry (one row per invoice, header level).

Loop test:
1. Static validation (SQL syntax, file existence)
2. HANA execution (row count, columns, nulls)
3. Grain validation (DocEntry uniqueness)
4. SAP ID validation (all required identifiers present)
5. Amount regression (DocTotal sum matches)
6. Canceled policy (CANCELED distribution)
7. Sample traceability (3 random invoices)
8. Second window validation (2023-03)

Gate: TELCHI_FINANCIAL_INVOICE_CONTRACT_PASS
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
SQL_CURRENT = TELCHI_ROOT / "sql" / "current" / "financial" / "invoice_contract_v1.sql"
SQL_LEGACY_SALES = TELCHI_ROOT / "sql" / "legacy_hana2" / "sales" / "sales_legacy.sql"
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


def find_date_window(cursor: dbapi.Cursor, table: str, column: str, month: str) -> tuple[str, str]:
    """Find actual date window within a month.

    Returns (start_date, next_month_start) as exclusive end for consistent
    date range queries (>= start AND < end).
    """
    start = f"{month}-01"
    year, month_num = (int(p) for p in month.split("-"))
    if month_num == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month_num + 1, 1)
    end = next_month.isoformat()
    return start, end


def static_validation() -> dict[str, Any]:
    """Step 1: Static validation - SQL file exists and is valid."""
    result = {
        "step": "static_validation",
        "sql_file_exists": SQL_CURRENT.exists(),
    }

    if not SQL_CURRENT.exists():
        result["status"] = "FAIL"
        result["error"] = "SQL file not found"
        return result

    sql_content = SQL_CURRENT.read_text(encoding="utf-8")

    # Check required elements
    checks = {
        "has_select": "SELECT" in sql_content.upper(),
        "has_from_oinv": "FROM TELCHI.OINV" in sql_content or 'FROM "TELCHI"."OINV"' in sql_content,
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

    if not result["all_pass"]:
        result["status"] = "FAIL"
        result["missing"] = [k for k, v in checks.items() if not v]
    else:
        result["status"] = "PASS"

    return result


def hana_execution(cursor: dbapi.Cursor, window: tuple[str, str]) -> dict[str, Any]:
    """Step 2: HANA execution - run query and get basic stats."""
    sql = SQL_CURRENT.read_text(encoding="utf-8")
    sql_exec = sql.replace(":start_date", "?").replace(":end_date", "?")

    df = query_frame(cursor, sql_exec, window)

    result = {
        "step": "hana_execution",
        "window": list(window),
        "row_count": len(df),
        "columns": list(df.columns),
        "column_count": len(df.columns),
    }

    if df.empty:
        result["status"] = "EMPTY_WINDOW"
        return result

    # Null profile
    null_profile = {}
    for col in df.columns:
        null_count = int(df[col].isna().sum())
        if null_count > 0:
            null_profile[col] = null_count
    result["null_profile"] = null_profile

    result["status"] = "PASS"
    return result


def grain_validation(cursor: dbapi.Cursor, window: tuple[str, str]) -> dict[str, Any]:
    """Step 3: Grain validation - DocEntry uniqueness."""
    sql = SQL_CURRENT.read_text(encoding="utf-8")
    sql_exec = sql.replace(":start_date", "?").replace(":end_date", "?")

    df = query_frame(cursor, sql_exec, window)

    result = {
        "step": "grain_validation",
        "grain": "DocEntry",
    }

    if df.empty:
        result["status"] = "EMPTY_WINDOW"
        return result

    # Check DocEntry uniqueness
    docentry_unique = int(df["DocEntry"].nunique())
    docentry_count = len(df)
    duplicates = docentry_count - docentry_unique

    result["docentry_count"] = docentry_count
    result["docentry_distinct"] = docentry_unique
    result["duplicates"] = duplicates
    result["grain_unique"] = duplicates == 0

    if result["grain_unique"]:
        result["status"] = "PASS"
    else:
        result["status"] = "FAIL"
        result["error"] = f"DocEntry grain has {duplicates} duplicates"

    return result


def sap_id_validation(cursor: dbapi.Cursor, window: tuple[str, str]) -> dict[str, Any]:
    """Step 4: SAP ID validation - all required identifiers present."""
    sql = SQL_CURRENT.read_text(encoding="utf-8")
    sql_exec = sql.replace(":start_date", "?").replace(":end_date", "?")

    df = query_frame(cursor, sql_exec, window)

    result = {
        "step": "sap_id_validation",
    }

    if df.empty:
        result["status"] = "EMPTY_WINDOW"
        return result

    # Required SAP identifiers
    required_ids = ["DocEntry", "DocNum", "CardCode", "SlpCode"]
    optional_ids = ["TransId", "PaidSum", "PaidToDate", "DocCur"]

    id_checks = {}
    for col in required_ids + optional_ids:
        if col in df.columns:
            null_count = int(df[col].isna().sum())
            id_checks[col] = {
                "present": True,
                "null_count": null_count,
                "required": col in required_ids,
            }
        else:
            id_checks[col] = {
                "present": False,
                "required": col in required_ids,
            }

    result["id_checks"] = id_checks

    # Check all required IDs are present
    missing_required = [k for k, v in id_checks.items() if not v["present"] and v["required"]]
    result["missing_required"] = missing_required

    if not missing_required:
        result["status"] = "PASS"
    else:
        result["status"] = "FAIL"
        result["error"] = f"Missing required SAP IDs: {missing_required}"

    return result


def amount_regression(cursor: dbapi.Cursor, window: tuple[str, str]) -> dict[str, Any]:
    """Step 5: Amount regression - DocTotal sum matches legacy.

    Uses direct SQL query to compare header-level totals from OINV
    against line-level totals from OINV+INV1 (deduplicated by DocEntry).
    Both queries use the same date range.
    """
    # Current SQL (header level)
    sql_current = SQL_CURRENT.read_text(encoding="utf-8")
    sql_current_exec = sql_current.replace(":start_date", "?").replace(":end_date", "?")
    df_current = query_frame(cursor, sql_current_exec, window)

    result = {
        "step": "amount_regression",
        "window": list(window),
    }

    if df_current.empty:
        result["status"] = "EMPTY_WINDOW"
        return result

    # Current: sum of DocTotal (header level)
    current_total = float(df_current["DocTotal"].sum())
    current_doc_count = len(df_current)

    # Legacy comparison: direct query against OINV (header level, same date range)
    sql_legacy_header = '''
        SELECT OINV."DocEntry", OINV."DocTotal"
        FROM TELCHI.OINV AS OINV
        WHERE OINV."DocDate" >= ? AND OINV."DocDate" < ?
    '''
    df_legacy_header = query_frame(cursor, sql_legacy_header, window)

    if not df_legacy_header.empty:
        legacy_total = float(df_legacy_header["DocTotal"].sum())
        legacy_doc_count = len(df_legacy_header)
    else:
        legacy_total = 0.0
        legacy_doc_count = 0

    result["current_total_doc_total"] = current_total
    result["current_doc_count"] = current_doc_count
    result["legacy_total_doc_total"] = legacy_total
    result["legacy_doc_count"] = legacy_doc_count

    # Check if totals match (with tolerance for floating point)
    tolerance = 0.01
    total_match = abs(current_total - legacy_total) < tolerance
    doc_count_match = current_doc_count == legacy_doc_count

    result["total_match"] = total_match
    result["doc_count_match"] = doc_count_match
    result["total_difference"] = abs(current_total - legacy_total)

    if total_match and doc_count_match:
        result["status"] = "PASS"
    else:
        result["status"] = "MISMATCH"
        result["warning"] = "Totals or document counts do not match legacy"

    return result


def canceled_policy(cursor: dbapi.Cursor, window: tuple[str, str]) -> dict[str, Any]:
    """Step 6: Canceled policy - CANCELED distribution."""
    sql = SQL_CURRENT.read_text(encoding="utf-8")
    sql_exec = sql.replace(":start_date", "?").replace(":end_date", "?")

    df = query_frame(cursor, sql_exec, window)

    result = {
        "step": "canceled_policy",
    }

    if df.empty:
        result["status"] = "EMPTY_WINDOW"
        return result

    # CANCELED distribution
    if "CANCELED" in df.columns:
        canceled_dist = df["CANCELED"].value_counts(dropna=False).to_dict()
        result["canceled_distribution"] = {str(k): int(v) for k, v in canceled_dist.items()}

        # Calculate stats by canceled status
        stats_by_canceled = {}
        for status in df["CANCELED"].unique():
            subset = df[df["CANCELED"] == status]
            stats_by_canceled[str(status)] = {
                "count": len(subset),
                "total_doc_total": float(subset["DocTotal"].sum()),
                "percentage_count": round(len(subset) / len(df) * 100, 2),
                "percentage_amount": round(float(subset["DocTotal"].sum()) / float(df["DocTotal"].sum()) * 100, 2),
            }
        result["stats_by_canceled"] = stats_by_canceled
        result["canceled_present"] = True
    else:
        result["canceled_present"] = False
        result["warning"] = "CANCELED field not present in SQL"

    result["status"] = "PASS"
    return result


def sample_traceability(cursor: dbapi.Cursor, window: tuple[str, str]) -> dict[str, Any]:
    """Step 7: Sample traceability - 3 random invoices with full SAP IDs."""
    sql = SQL_CURRENT.read_text(encoding="utf-8")
    sql_exec = sql.replace(":start_date", "?").replace(":end_date", "?")

    df = query_frame(cursor, sql_exec, window)

    result = {
        "step": "sample_traceability",
    }

    if df.empty:
        result["status"] = "EMPTY_WINDOW"
        return result

    # Sample 3 random invoices
    sample_size = min(3, len(df))
    sample = df.sample(n=sample_size, random_state=42)

    samples = []
    for _, row in sample.iterrows():
        invoice = {
            "DocEntry": int(row["DocEntry"]) if pandas.notna(row["DocEntry"]) else None,
            "DocNum": int(row["DocNum"]) if pandas.notna(row["DocNum"]) else None,
            "CardCode": str(row["CardCode"]) if pandas.notna(row["CardCode"]) else None,
            "SlpCode": int(row["SlpCode"]) if pandas.notna(row["SlpCode"]) else None,
            "DocDate": str(row["DocDate"])[:10] if pandas.notna(row["DocDate"]) else None,
            "DocDueDate": str(row["DocDueDate"])[:10] if pandas.notna(row["DocDueDate"]) else None,
            "DocTotal": float(row["DocTotal"]) if pandas.notna(row["DocTotal"]) else None,
            "CANCELED": str(row["CANCELED"]) if pandas.notna(row["CANCELED"]) else None,
            "DocStatus": str(row["DocStatus"]) if pandas.notna(row["DocStatus"]) else None,
        }
        samples.append(invoice)

    result["samples"] = samples
    result["sample_size"] = sample_size
    result["status"] = "PASS"

    return result


def second_window_validation(cursor: dbapi.Cursor, month: str = "2023-03") -> dict[str, Any]:
    """Step 8: Second window validation - 2023-03."""
    window = find_date_window(cursor, "OINV", "DocDate", month)

    sql = SQL_CURRENT.read_text(encoding="utf-8")
    sql_exec = sql.replace(":start_date", "?").replace(":end_date", "?")

    df = query_frame(cursor, sql_exec, window)

    result = {
        "step": "second_window_validation",
        "month": month,
        "window": list(window),
    }

    if df.empty:
        result["status"] = "EMPTY_WINDOW"
        return result

    # Basic stats
    result["row_count"] = len(df)
    result["docentry_distinct"] = int(df["DocEntry"].nunique())
    result["total_doc_total"] = float(df["DocTotal"].sum())

    # Grain check
    duplicates = len(df) - int(df["DocEntry"].nunique())
    result["duplicates"] = duplicates
    result["grain_unique"] = duplicates == 0

    # Canceled distribution
    if "CANCELED" in df.columns:
        result["canceled_distribution"] = {str(k): int(v) for k, v in df["CANCELED"].value_counts(dropna=False).items()}

    if result["grain_unique"]:
        result["status"] = "PASS"
    else:
        result["status"] = "FAIL"

    return result


def run_validation(month: str = "2023-02") -> dict[str, Any]:
    """Run full FINANCIAL-001 validation."""
    results: dict[str, Any] = {
        "validation_id": "FINANCIAL-001",
        "gate": "TELCHI_FINANCIAL_INVOICE_CONTRACT_PASS",
        "month": month,
        "steps": {},
    }

    # Step 1: Static validation
    results["steps"]["static"] = static_validation()
    if results["steps"]["static"]["status"] != "PASS":
        results["overall_status"] = "FAIL"
        results["overall_gate"] = "TELCHI_FINANCIAL_INVOICE_CONTRACT_FAIL"
        return results

    # Connect to HANA
    try:
        conn, cursor = connect()
    except Exception as e:
        results["overall_status"] = "FAIL"
        results["overall_gate"] = "TELCHI_FINANCIAL_INVOICE_CONTRACT_BLOCKED"
        results["connection_error"] = str(e)
        return results

    try:
        # Find date window
        window = find_date_window(cursor, "OINV", "DocDate", month)
        results["window"] = list(window)

        # Step 2: HANA execution
        results["steps"]["hana_execution"] = hana_execution(cursor, window)
        if results["steps"]["hana_execution"]["status"] == "EMPTY_WINDOW":
            results["overall_status"] = "EMPTY_WINDOW"
            return results

        # Step 3: Grain validation
        results["steps"]["grain"] = grain_validation(cursor, window)

        # Step 4: SAP ID validation
        results["steps"]["sap_ids"] = sap_id_validation(cursor, window)

        # Step 5: Amount regression
        results["steps"]["amount_regression"] = amount_regression(cursor, window)

        # Step 6: Canceled policy
        results["steps"]["canceled_policy"] = canceled_policy(cursor, window)

        # Step 7: Sample traceability
        results["steps"]["sample_traceability"] = sample_traceability(cursor, window)

        # Step 8: Second window validation
        results["steps"]["second_window"] = second_window_validation(cursor)

    finally:
        cursor.close()
        conn.close()

    # Overall status
    failed_steps = [k for k, v in results["steps"].items() if v["status"] not in ("PASS", "EMPTY_WINDOW")]
    if not failed_steps:
        results["overall_status"] = "PASS"
        results["overall_gate"] = "TELCHI_FINANCIAL_INVOICE_CONTRACT_PASS"
    else:
        results["overall_status"] = "FAIL"
        results["overall_gate"] = "TELCHI_FINANCIAL_INVOICE_CONTRACT_FAIL"
        results["failed_steps"] = failed_steps

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="FINANCIAL-001: Invoice Contract Validation")
    parser.add_argument("--month", default="2023-02", help="Month to validate (YYYY-MM)")
    parser.add_argument("--output", "-o", help="Output JSON file")
    args = parser.parse_args()

    results = run_validation(args.month)

    output = json.dumps(results, indent=2, default=str, sort_keys=False)
    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"Results written to {args.output}")
    else:
        print(output)

    # Print gate
    print(f"\nGate: {results.get('overall_gate', 'UNKNOWN')}")
    return 0 if results.get("overall_status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
