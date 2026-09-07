#!/usr/bin/env python3
"""SQL Baseline Validation Harness for Telchi HANA2 Legacy.

This harness:
- Loads SQL from files
- Binds parameters safely
- Executes read-only queries
- Reports row counts, columns, grain, duplicates, nulls
- Preserves SAP identifiers (DocEntry, etc.)

NO writes to HANA. NO Parquet output. NO infrastructure changes.
"""

from __future__ import annotations

import argparse
import json
import os
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
SQL_ROOT = TELCHI_ROOT / "sql"


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
    required = {
        "TELCHI_SAP_HANA_HOST",
        "TELCHI_SAP_HANA_PORT",
        "TELCHI_SAP_HANA_SCHEMA",
        "TELCHI_SAP_HANA_USER",
        "TELCHI_SAP_HANA_PASSWORD",
    }
    if set(values) != required:
        raise ValueError(f"unexpected HANA env keys: {set(values)}")
    return values


def connect() -> tuple[dbapi.Connection, dbapi.Cursor]:
    """Create HANA connection through the configured local endpoint.

    The harness deliberately has no Podman/VPN dependency and never invokes
    privileged host commands. HANA_HOST/HANA_PORT/HANA_USER/HANA_PASSWORD environment variables
    may override the local config for controlled validation.
    """
    config = load_hana_config()
    host = os.getenv("HANA_HOST", config["TELCHI_SAP_HANA_HOST"])
    port = int(os.getenv("HANA_PORT", config["TELCHI_SAP_HANA_PORT"]))
    schema = os.getenv("HANA_SCHEMA", config["TELCHI_SAP_HANA_SCHEMA"])
    user = os.getenv("HANA_USER", config["TELCHI_SAP_HANA_USER"])
    password = os.getenv("HANA_PASSWORD", config["TELCHI_SAP_HANA_PASSWORD"])
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
    """Find actual date window within a month."""
    start = f"{month}-01"
    year, month_num = (int(p) for p in month.split("-"))
    if month_num == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month_num + 1, 1)
    end = next_month.isoformat()

    cursor.execute(
        f'''SELECT MIN(TO_DATE("{column}")), MAX(TO_DATE("{column}"))
            FROM "TELCHI"."{table}"
            WHERE "{column}" >= ? AND "{column}" < ?''',
        (start, end),
    )
    row = cursor.fetchone()
    if row is None or row[0] is None:
        return start, end
    actual_start = str(row[0])[:10]
    actual_end = (date.fromisoformat(actual_start) + timedelta(days=2)).isoformat()
    return actual_start, actual_end


def validate_sales(cursor: dbapi.Cursor, window: tuple[str, str]) -> dict[str, Any]:
    """Validate sales SQL baseline."""
    sql_path = SQL_ROOT / "legacy_hana2/sales/sales_legacy.sql"
    sql = sql_path.read_text(encoding="utf-8")

    # Replace parameter placeholders with actual values for execution
    sql_exec = sql.replace(":start_date", "?").replace(":end_date", "?")

    df = query_frame(cursor, sql_exec, window)

    result: dict[str, Any] = {
        "domain": "sales",
        "sql_file": str(sql_path),
        "window": window,
        "row_count": len(df),
        "columns": list(df.columns),
        "column_count": len(df.columns),
    }

    if df.empty:
        return result | {"status": "EMPTY_WINDOW"}

    # SAP identifier checks
    result["docentry_present"] = "DocEntry" in df.columns
    result["docentry_null_count"] = int(df["DocEntry"].isna().sum()) if "DocEntry" in df.columns else -1
    result["docentry_unique"] = int(df["DocEntry"].nunique()) if "DocEntry" in df.columns else 0
    result["document_count"] = result["docentry_unique"]

    # Grain check
    if "DocEntry" in df.columns and "ItemCode" in df.columns:
        dup_count = int(df.duplicated(["DocEntry", "ItemCode"]).sum())
        result["docentry_itemcode_duplicates"] = dup_count

    # Key null checks
    for col in ["DocEntry", "DocNum", "CardCode", "ItemCode", "DocDate", "DocTotal"]:
        if col in df.columns:
            result[f"{col}_null_count"] = int(df[col].isna().sum())

    # Amount sanity
    if "DocTotal" in df.columns:
        result["doc_total_sum"] = float(df["DocTotal"].sum())
        result["doc_total_negative_count"] = int((df["DocTotal"] < 0).sum())

    # LineNum check (not in legacy, candidate for current)
    result["linenum_present"] = "LineNum" in df.columns

    # CANCELED check (not in legacy, candidate for current)
    result["canceled_present"] = "CANCELED" in df.columns

    result["status"] = "PASS"
    return result


def validate_credit_notes(cursor: dbapi.Cursor, window: tuple[str, str]) -> dict[str, Any]:
    """Validate credit notes SQL baseline."""
    sql_path = SQL_ROOT / "legacy_hana2/credit_notes/credit_notes_legacy.sql"
    if not sql_path.exists():
        return {"domain": "credit_notes", "status": "SQL_NOT_EXTRACTED"}

    sql = sql_path.read_text(encoding="utf-8")
    sql_exec = sql.replace(":start_date", "?").replace(":end_date", "?")
    df = query_frame(cursor, sql_exec, window)

    result: dict[str, Any] = {
        "domain": "credit_notes",
        "sql_file": str(sql_path),
        "window": window,
        "row_count": len(df),
        "columns": list(df.columns),
    }

    if df.empty:
        return result | {"status": "EMPTY_WINDOW"}

    result["docentry_present"] = "FDocEntry" in df.columns or "DocEntry" in df.columns
    result["baseref_present"] = "BaseRef" in df.columns
    if "BaseRef" in df.columns:
        result["baseref_null_count"] = int(df["BaseRef"].isna().sum())

    result["status"] = "PASS"
    return result


def validate_products(cursor: dbapi.Cursor) -> dict[str, Any]:
    """Validate products SQL baseline."""
    sql_path = SQL_ROOT / "legacy_hana2/products/products_base.sql"
    if not sql_path.exists():
        return {"domain": "products", "status": "SQL_NOT_EXTRACTED"}

    sql = sql_path.read_text(encoding="utf-8")
    df = query_frame(cursor, sql)

    result: dict[str, Any] = {
        "domain": "products",
        "sql_file": str(sql_path),
        "row_count": len(df),
        "columns": list(df.columns),
    }

    if df.empty:
        return result | {"status": "EMPTY"}

    result["itemcode_present"] = "ItemCode" in df.columns
    result["itemcode_unique"] = int(df["ItemCode"].nunique()) if "ItemCode" in df.columns else 0
    result["u_produce_present"] = "U_PRODUCE" in df.columns
    result["u_produce_lower_present"] = "u_produce" in df.columns

    result["status"] = "PASS"
    return result


def validate_customers(cursor: dbapi.Cursor) -> dict[str, Any]:
    """Validate customers SQL baseline."""
    sql_path = SQL_ROOT / "legacy_hana2/customers/customers_base.sql"
    if not sql_path.exists():
        return {"domain": "customers", "status": "SQL_NOT_EXTRACTED"}

    sql = sql_path.read_text(encoding="utf-8")
    df = query_frame(cursor, sql)

    result: dict[str, Any] = {
        "domain": "customers",
        "sql_file": str(sql_path),
        "row_count": len(df),
        "columns": list(df.columns),
    }

    if df.empty:
        return result | {"status": "EMPTY"}

    result["cardcode_present"] = "ClientCode" in df.columns or "CardCode" in df.columns
    result["cardcode_unique"] = int(df["ClientCode"].nunique() if "ClientCode" in df.columns else df["CardCode"].nunique())

    result["status"] = "PASS"
    return result


def validate_warehouses(cursor: dbapi.Cursor) -> dict[str, Any]:
    """Validate warehouses SQL baseline."""
    sql_path = SQL_ROOT / "legacy_hana2/warehouses/warehouses_base.sql"
    if not sql_path.exists():
        return {"domain": "warehouses", "status": "SQL_NOT_EXTRACTED"}

    sql = sql_path.read_text(encoding="utf-8")
    df = query_frame(cursor, sql)

    result: dict[str, Any] = {
        "domain": "warehouses",
        "sql_file": str(sql_path),
        "row_count": len(df),
        "columns": list(df.columns),
    }

    if df.empty:
        return result | {"status": "EMPTY"}

    if "ItemCode" in df.columns and "WhsCode" in df.columns:
        result["grain_unique"] = int(df.duplicated(["ItemCode", "WhsCode"]).sum()) == 0
        result["duplicate_keys"] = int(df.duplicated(["ItemCode", "WhsCode"]).sum())

    result["status"] = "PASS"
    return result


def validate_payments(cursor: dbapi.Cursor, window: tuple[str, str]) -> dict[str, Any]:
    """Validate payments SQL baseline."""
    sql_path = SQL_ROOT / "legacy_hana2/payments/payments_base.sql"
    if not sql_path.exists():
        return {"domain": "payments", "status": "SQL_NOT_EXTRACTED"}

    sql = sql_path.read_text(encoding="utf-8")
    sql_exec = sql.replace(":start_date", "?").replace(":end_date", "?")
    df = query_frame(cursor, sql_exec, window)

    result: dict[str, Any] = {
        "domain": "payments",
        "sql_file": str(sql_path),
        "window": window,
        "row_count": len(df),
        "columns": list(df.columns),
    }

    if df.empty:
        return result | {"status": "EMPTY_WINDOW"}

    result["docentry_present"] = "DocEntry" in df.columns
    result["canceled_present"] = "Canceled" in df.columns
    if "Canceled" in df.columns:
        result["canceled_distribution"] = df["Canceled"].value_counts(dropna=False).to_dict()

    result["status"] = "PASS"
    return result


def validate_reconciliation(cursor: dbapi.Cursor, window: tuple[str, str]) -> dict[str, Any]:
    """Validate reconciliation SQL baseline."""
    sql_path = SQL_ROOT / "legacy_hana2/reconciliation/reconciliation_base.sql"
    if not sql_path.exists():
        return {"domain": "reconciliation", "status": "SQL_NOT_EXTRACTED"}

    sql = sql_path.read_text(encoding="utf-8")
    sql_exec = sql.replace(":start_date", "?").replace(":end_date", "?")
    df = query_frame(cursor, sql_exec, window)

    result: dict[str, Any] = {
        "domain": "reconciliation",
        "sql_file": str(sql_path),
        "window": window,
        "row_count": len(df),
        "columns": list(df.columns),
    }

    if df.empty:
        return result | {"status": "EMPTY_WINDOW"}

    result["reconnumpresent"] = "ReconNum" in df.columns
    result["canceled_present"] = "Canceled" in df.columns

    result["status"] = "PASS"
    return result


def validate_inventory(cursor: dbapi.Cursor, window: tuple[str, str]) -> dict[str, Any]:
    """Validate inventory movements SQL baseline."""
    sql_path = SQL_ROOT / "legacy_hana2/inventory_movements/inventory_base.sql"
    if not sql_path.exists():
        return {"domain": "inventory_movements", "status": "SQL_NOT_EXTRACTED"}

    sql = sql_path.read_text(encoding="utf-8")
    sql_exec = sql.replace(":start_date", "?").replace(":end_date", "?")
    df = query_frame(cursor, sql_exec, window)

    result: dict[str, Any] = {
        "domain": "inventory_movements",
        "sql_file": str(sql_path),
        "window": window,
        "row_count": len(df),
        "columns": list(df.columns),
    }

    if df.empty:
        return result | {"status": "EMPTY_WINDOW"}

    result["transnum_present"] = "TransNum" in df.columns
    result["baseref_present"] = "BASE_REF" in df.columns
    result["trans_type_distribution"] = df["TransType"].value_counts(dropna=False).head(10).to_dict() if "TransType" in df.columns else {}

    result["status"] = "PASS"
    return result


def run_validation(month: str, domains: list[str] | None = None) -> dict[str, Any]:
    """Run validation for specified domains."""
    conn, cursor = connect()
    try:
        results: dict[str, Any] = {
            "month": month,
            "hana": {
                "host": load_hana_config()["TELCHI_SAP_HANA_HOST"],
                "port": load_hana_config()["TELCHI_SAP_HANA_PORT"],
                "schema": load_hana_config()["TELCHI_SAP_HANA_SCHEMA"],
            },
            "domains": {},
        }

        all_domains = domains or ["sales", "credit_notes", "inventory_movements",
                                   "products", "customers", "warehouses",
                                   "payments", "reconciliation"]

        for domain in all_domains:
            if domain == "sales":
                window = find_date_window(cursor, "OINV", "DocDate", month)
                results["domains"][domain] = validate_sales(cursor, window)
            elif domain == "credit_notes":
                window = find_date_window(cursor, "ORIN", "DocDate", month)
                results["domains"][domain] = validate_credit_notes(cursor, window)
            elif domain == "inventory_movements":
                window = find_date_window(cursor, "OINM", "DocDate", month)
                results["domains"][domain] = validate_inventory(cursor, window)
            elif domain == "products":
                results["domains"][domain] = validate_products(cursor)
            elif domain == "customers":
                results["domains"][domain] = validate_customers(cursor)
            elif domain == "warehouses":
                results["domains"][domain] = validate_warehouses(cursor)
            elif domain == "payments":
                window = find_date_window(cursor, "ORCT", "DocDate", month)
                results["domains"][domain] = validate_payments(cursor, window)
            elif domain == "reconciliation":
                window = find_date_window(cursor, "OITR", "ReconDate", month)
                results["domains"][domain] = validate_reconciliation(cursor, window)

        return results
    finally:
        cursor.close()
        conn.rollback()
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="SQL Baseline Validation Harness")
    parser.add_argument("--month", default="2023-02", help="Month to validate (YYYY-MM)")
    parser.add_argument("--domains", nargs="*", help="Domains to validate")
    parser.add_argument("--output", "-o", help="Output JSON file")
    args = parser.parse_args()

    results = run_validation(args.month, args.domains)

    output = json.dumps(results, indent=2, default=str, sort_keys=False)
    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"Results written to {args.output}")
    else:
        print(output)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
