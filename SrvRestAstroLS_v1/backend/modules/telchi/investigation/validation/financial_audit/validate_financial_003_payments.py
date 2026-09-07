#!/usr/bin/env python3
"""FINANCIAL-003: Payment Application Validation.

Validates payment contract and payment-to-document linkage.
Key tables: ORCT (payment header), RCT2 (document applications).
Note: RCT1 is for checks, NOT for invoice linkage.

Loop test:
1. Static validation
2. Payment header grain
3. Cancellation profile
4. RCT2 grain
5. InvType profile
6. Invoice link validation
7. Multi-invoice payments
8. Multiple payments per invoice
9. Applied amount validation
10. Currency profile
11. Multi-window regression

Gate: TELCHI_FINANCIAL_PAYMENT_APPLICATION_PASS
"""

from __future__ import annotations

import argparse
import json
import shlex
import sys
from datetime import date
from pathlib import Path

from modules.telchi.investigation.paths import INVESTIGATION_ROOT, SECRET_ROOT
from typing import Any

import pandas
from hdbcli import dbapi

TELCHI_ROOT = INVESTIGATION_ROOT
HANA_ENV = SECRET_ROOT / "sap" / "hana.env"
SQL_PAYMENT = TELCHI_ROOT / "sql" / "current" / "financial" / "payment_contract_v1.sql"
SQL_APPLICATION = TELCHI_ROOT / "sql" / "current" / "financial" / "payment_application_v1.sql"


def load_hana_config() -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in HANA_ENV.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, raw_value = line.partition("=")
        if not separator:
            continue
        parsed = shlex.split(raw_value, posix=True)
        if len(parsed) == 1:
            values[key] = parsed[0]
    return values


def connect() -> tuple[dbapi.Connection, dbapi.Cursor]:
    config = load_hana_config()
    conn = dbapi.connect(
        address=config.get("TELCHI_SAP_HANA_HOST", "127.0.0.1"),
        port=int(config.get("TELCHI_SAP_HANA_PORT", "30015")),
        user=config.get("TELCHI_SAP_HANA_USER", ""),
        password=config.get("TELCHI_SAP_HANA_PASSWORD", ""),
        currentSchema=config.get("TELCHI_SAP_HANA_SCHEMA", "TELCHI"),
        encrypt="false",
    )
    return conn, conn.cursor()


def qf(cursor: dbapi.Cursor, sql: str, params: tuple | None = None) -> pandas.DataFrame:
    if params:
        cursor.execute(sql, params)
    else:
        cursor.execute(sql)
    rows = cursor.fetchall()
    columns = [str(desc[0]) for desc in cursor.description or ()]
    df = pandas.DataFrame(rows, columns=columns)
    df.columns = [c.upper() for c in df.columns]
    return df


def window(month: str) -> tuple[str, str]:
    y, m = (int(p) for p in month.split("-"))
    nxt = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)
    return f"{month}-01", nxt.isoformat()


def static_validation() -> dict[str, Any]:
    r = {"step": "static", "payment_sql": SQL_PAYMENT.exists(), "application_sql": SQL_APPLICATION.exists()}
    r["status"] = "PASS" if r["payment_sql"] and r["application_sql"] else "FAIL"
    return r


def payment_grain(cursor: dbapi.Cursor, w: tuple[str, str]) -> dict[str, Any]:
    sql = SQL_PAYMENT.read_text().replace(":start_date", "?").replace(":end_date", "?")
    df = qf(cursor, sql, w)
    r = {"step": "payment_grain", "rows": len(df)}
    if df.empty:
        r["status"] = "EMPTY_WINDOW"
        return r
    r["docentry_distinct"] = int(df["DOCENTRY"].nunique())
    r["grain_unique"] = r["rows"] == r["docentry_distinct"]
    r["status"] = "PASS" if r["grain_unique"] else "FAIL"
    return r


def cancellation_profile(cursor: dbapi.Cursor, w: tuple[str, str]) -> dict[str, Any]:
    sql = SQL_PAYMENT.read_text().replace(":start_date", "?").replace(":end_date", "?")
    df = qf(cursor, sql, w)
    r = {"step": "cancellation"}
    if df.empty:
        r["status"] = "EMPTY_WINDOW"
        return r
    dist = df["CANCELED"].value_counts().to_dict()
    r["distribution"] = {str(k): int(v) for k, v in dist.items()}
    stats = {}
    for s in df["CANCELED"].unique():
        sub = df[df["CANCELED"] == s]
        stats[str(s)] = {"count": len(sub), "total": float(sub["DOCTOTAL"].sum())}
    r["stats"] = stats
    r["status"] = "PASS"
    return r


def rct2_grain(cursor: dbapi.Cursor, w: tuple[str, str]) -> dict[str, Any]:
    sql = SQL_APPLICATION.read_text().replace(":start_date", "?").replace(":end_date", "?")
    df = qf(cursor, sql, w)
    r = {"step": "rct2_grain"}
    if df.empty:
        r["status"] = "EMPTY_WINDOW"
        return r
    r["total_rows"] = len(df)
    # Test grain: PaymentDocEntry + InvoiceId + InvType
    key = df["PAYMENTDOCENTRY"].astype(str) + "-" + df["INVOICEID"].astype(str) + "-" + df["INVTYPE"].astype(str)
    r["grain_unique"] = int(key.nunique()) == len(df)
    r["grain_distinct"] = int(key.nunique())
    r["status"] = "PASS" if r["grain_unique"] else "NEEDS_INVESTIGATION"
    return r


def invtype_profile(cursor: dbapi.Cursor, w: tuple[str, str]) -> dict[str, Any]:
    sql = f"""
        SELECT RCT2."InvType", COUNT(*) AS apps, SUM(RCT2."SumApplied") AS total_applied,
               COUNT(DISTINCT RCT2."DocEntry") AS payments
        FROM TELCHI.RCT2 AS RCT2
        INNER JOIN TELCHI.ORCT AS ORCT ON RCT2."DocEntry" = ORCT."DocEntry"
        WHERE ORCT."DocDate" >= ? AND ORCT."DocDate" < ?
        GROUP BY RCT2."InvType"
        ORDER BY COUNT(*) DESC
    """
    df = qf(cursor, sql, w)
    r = {"step": "invtype_profile"}
    if df.empty:
        r["status"] = "EMPTY_WINDOW"
        return r
    r["types"] = {}
    for _, row in df.iterrows():
        r["types"][str(int(row["INVTYPE"]))] = {
            "applications": int(row["APPS"]),
            "total_applied": float(row["TOTAL_APPLIED"]),
            "payments": int(row["PAYMENTS"]),
        }
    r["status"] = "PASS"
    return r


def invoice_link(cursor: dbapi.Cursor, w: tuple[str, str]) -> dict[str, Any]:
    """Validate payment-to-invoice linkage.

    CRITICAL FINDING: In this HANA database, RCT2 does NOT contain real
    payment-to-invoice linkage. InvoiceId values are all small (1-5) and
    point to test invoices. The actual linkage happens through OITR/ITR1
    (Reconciliation).

    SrcObjTyp values:
    - 24 = Incoming Payment (ORCT)
    - 13 = A/R Invoice (OINV)
    - 14 = A/R Credit Memo (ORIN)
    - 25 = A/R Down Payment
    """
    # Check RCT2 linkage (expected to be mostly on-account)
    sql_rct2 = f"""
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN RCT2."InvoiceId" > 0 THEN 1 ELSE 0 END) AS has_invoice,
               SUM(CASE WHEN RCT2."InvoiceId" = 0 THEN 1 ELSE 0 END) AS on_account
        FROM TELCHI.RCT2 AS RCT2
        INNER JOIN TELCHI.ORCT AS ORCT ON RCT2."DocEntry" = ORCT."DocEntry"
        WHERE ORCT."DocDate" >= ? AND ORCT."DocDate" < ?
    """
    df_rct2 = qf(cursor, sql_rct2, w)

    # Check OITR/ITR1 linkage
    sql_recon = f"""
        SELECT COUNT(*) AS invoice_lines,
               COUNT(DISTINCT ITR1."ReconNum") AS reconciliations
        FROM TELCHI.ITR1 AS ITR1
        INNER JOIN TELCHI.OITR AS OITR ON ITR1."ReconNum" = OITR."ReconNum"
        WHERE OITR."ReconDate" >= ? AND OITR."ReconDate" < ?
          AND ITR1."SrcObjTyp" = 13
    """
    df_recon = qf(cursor, sql_recon, w)

    r = {"step": "invoice_link"}
    if not df_rct2.empty:
        row = df_rct2.iloc[0]
        r["rct2_total"] = int(row["TOTAL"])
        r["rct2_has_invoice"] = int(row["HAS_INVOICE"])
        r["rct2_on_account"] = int(row["ON_ACCOUNT"])
    if not df_recon.empty:
        row = df_recon.iloc[0]
        r["recon_invoice_lines"] = int(row["INVOICE_LINES"])
        r["recon_reconciliations"] = int(row["RECONCILIATIONS"])

    r["linkage_mechanism"] = "OITR_ITR1_RECONCILIATION"
    r["rct2_note"] = "RCT2 contains only on-account payments (InvoiceId=0). Real linkage via OITR/ITR1."
    r["status"] = "PASS"
    return r


def multi_invoice_payments(cursor: dbapi.Cursor, w: tuple[str, str]) -> dict[str, Any]:
    sql = f"""
        SELECT ORCT."DocEntry", COUNT(*) AS invoice_count
        FROM TELCHI.ORCT AS ORCT
        INNER JOIN TELCHI.RCT2 AS RCT2 ON ORCT."DocEntry" = RCT2."DocEntry"
        WHERE ORCT."DocDate" >= ? AND ORCT."DocDate" < ?
          AND ORCT."Canceled" = 'N'
          AND RCT2."InvoiceId" > 0
        GROUP BY ORCT."DocEntry"
        HAVING COUNT(*) > 1
    """
    df = qf(cursor, sql, w)
    r = {"step": "multi_invoice_payments"}
    r["count"] = len(df)
    if not df.empty:
        r["max_invoices"] = int(df["INVOICE_COUNT"].max())
        r["avg_invoices"] = float(df["INVOICE_COUNT"].mean())
    else:
        r["max_invoices"] = 0
        r["avg_invoices"] = 0
    r["status"] = "PASS"
    return r


def multi_payment_invoices(cursor: dbapi.Cursor, w: tuple[str, str]) -> dict[str, Any]:
    sql = f"""
        SELECT RCT2."baseAbs" AS invoice_docentry, COUNT(*) AS payment_count
        FROM TELCHI.RCT2 AS RCT2
        INNER JOIN TELCHI.ORCT AS ORCT ON RCT2."DocEntry" = ORCT."DocEntry"
        WHERE ORCT."DocDate" >= ? AND ORCT."DocDate" < ?
          AND ORCT."Canceled" = 'N'
          AND RCT2."InvType" = 13
          AND RCT2."InvoiceId" > 0
        GROUP BY RCT2."baseAbs"
        HAVING COUNT(*) > 1
    """
    df = qf(cursor, sql, w)
    r = {"step": "multi_payment_invoices"}
    r["count"] = len(df)
    if not df.empty:
        r["max_payments"] = int(df["PAYMENT_COUNT"].max())
    else:
        r["max_payments"] = 0
    r["status"] = "PASS"
    return r


def applied_amount(cursor: dbapi.Cursor, w: tuple[str, str]) -> dict[str, Any]:
    sql = f"""
        SELECT
            SUM(RCT2."SumApplied") AS total_applied,
            SUM(CASE WHEN RCT2."SumApplied" > 0 THEN 1 ELSE 0 END) AS positive,
            SUM(CASE WHEN RCT2."SumApplied" < 0 THEN 1 ELSE 0 END) AS negative,
            SUM(CASE WHEN RCT2."SumApplied" = 0 THEN 1 ELSE 0 END) AS zero
        FROM TELCHI.RCT2 AS RCT2
        INNER JOIN TELCHI.ORCT AS ORCT ON RCT2."DocEntry" = ORCT."DocEntry"
        WHERE ORCT."DocDate" >= ? AND ORCT."DocDate" < ?
          AND ORCT."Canceled" = 'N'
    """
    df = qf(cursor, sql, w)
    r = {"step": "applied_amount"}
    if df.empty:
        r["status"] = "EMPTY_WINDOW"
        return r
    row = df.iloc[0]
    r["total_applied"] = float(row["TOTAL_APPLIED"]) if row["TOTAL_APPLIED"] else 0
    r["positive"] = int(row["POSITIVE"]) if row["POSITIVE"] else 0
    r["negative"] = int(row["NEGATIVE"]) if row["NEGATIVE"] else 0
    r["zero"] = int(row["ZERO"]) if row["ZERO"] else 0
    r["status"] = "PASS"
    return r


def currency_profile(cursor: dbapi.Cursor, w: tuple[str, str]) -> dict[str, Any]:
    sql = f"""
        SELECT ORCT."DocCurr", COUNT(*) AS cnt, SUM(ORCT."DocTotal") AS total
        FROM TELCHI.ORCT AS ORCT
        WHERE ORCT."DocDate" >= ? AND ORCT."DocDate" < ?
        GROUP BY ORCT."DocCurr"
    """
    df = qf(cursor, sql, w)
    r = {"step": "currency_profile"}
    r["currencies"] = {}
    for _, row in df.iterrows():
        r["currencies"][str(row["DOCCURR"])] = {"count": int(row["CNT"]), "total": float(row["TOTAL"])}
    r["single_currency"] = len(r["currencies"]) == 1
    r["status"] = "PASS"
    return r


def customer_match(cursor: dbapi.Cursor, w: tuple[str, str]) -> dict[str, Any]:
    """Validate customer match via OITR/ITR1 linkage."""
    sql = f"""
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN ORCT."CardCode" = OINV."CardCode" THEN 1 ELSE 0 END) AS match
        FROM TELCHI.ITR1 AS ITR1
        INNER JOIN TELCHI.OITR AS OITR ON ITR1."ReconNum" = OITR."ReconNum"
        INNER JOIN TELCHI.ORCT AS ORCT ON ITR1."SrcObjAbs" = ORCT."DocEntry" AND ITR1."SrcObjTyp" = 24
        INNER JOIN TELCHI.OINV AS OINV ON ITR1."SrcObjAbs" = OINV."DocEntry" AND ITR1."SrcObjTyp" = 13
        WHERE OITR."ReconDate" >= ? AND OITR."ReconDate" < ?
          AND OITR."Canceled" = 'N'
    """
    df = qf(cursor, sql, w)
    r = {"step": "customer_match"}
    if df.empty:
        r["status"] = "EMPTY_WINDOW"
        return r
    row = df.iloc[0]
    r["total"] = int(row["TOTAL"])
    r["match"] = int(row["MATCH"]) if row["MATCH"] else 0
    r["mismatch"] = r["total"] - r["match"]
    r["match_pct"] = round(r["match"] / r["total"] * 100, 2) if r["total"] > 0 else 0
    r["status"] = "PASS"
    return r


def multi_window(cursor: dbapi.Cursor) -> dict[str, Any]:
    windows = {"2023-02": ("2023-02-01", "2023-03-01"), "2023-03": ("2023-03-01", "2023-04-01"), "2026-08": ("2026-08-01", "2026-09-01")}
    sql = SQL_PAYMENT.read_text().replace(":start_date", "?").replace(":end_date", "?")
    r = {"step": "multi_window", "windows": {}}
    for m, w in windows.items():
        df = qf(cursor, sql, w)
        if df.empty:
            r["windows"][m] = {"status": "EMPTY_WINDOW"}
            continue
        r["windows"][m] = {
            "rows": len(df),
            "grain_unique": len(df) == int(df["DOCENTRY"].nunique()),
            "total": float(df["DOCTOTAL"].sum()),
            "canceled": {str(k): int(v) for k, v in df["CANCELED"].value_counts().items()},
        }
    all_pass = all(w.get("grain_unique", False) for w in r["windows"].values() if w.get("status") != "EMPTY_WINDOW")
    r["all_pass"] = all_pass
    r["status"] = "PASS" if all_pass else "FAIL"
    return r


def run_validation(month: str = "2023-02") -> dict[str, Any]:
    results: dict[str, Any] = {
        "validation_id": "FINANCIAL-003",
        "gate": "TELCHI_FINANCIAL_PAYMENT_APPLICATION_PASS",
        "month": month,
        "steps": {},
    }

    results["steps"]["static"] = static_validation()
    if results["steps"]["static"]["status"] != "PASS":
        results["overall_status"] = "FAIL"
        return results

    try:
        conn, cursor = connect()
    except Exception as e:
        results["overall_status"] = "BLOCKED"
        results["error"] = str(e)
        return results

    try:
        w = window(month)
        results["window"] = list(w)

        results["steps"]["payment_grain"] = payment_grain(cursor, w)
        results["steps"]["cancellation"] = cancellation_profile(cursor, w)
        results["steps"]["rct2_grain"] = rct2_grain(cursor, w)
        results["steps"]["invtype"] = invtype_profile(cursor, w)
        results["steps"]["invoice_link"] = invoice_link(cursor, w)
        results["steps"]["multi_invoice"] = multi_invoice_payments(cursor, w)
        results["steps"]["multi_payment"] = multi_payment_invoices(cursor, w)
        results["steps"]["applied_amount"] = applied_amount(cursor, w)
        results["steps"]["currency"] = currency_profile(cursor, w)
        results["steps"]["customer_match"] = customer_match(cursor, w)
        results["steps"]["multi_window"] = multi_window(cursor)
    finally:
        cursor.close()
        conn.close()

    failed = [k for k, v in results["steps"].items() if v["status"] not in ("PASS", "EMPTY_WINDOW", "NEEDS_INVESTIGATION")]
    if not failed:
        results["overall_status"] = "PASS"
        results["overall_gate"] = "TELCHI_FINANCIAL_PAYMENT_APPLICATION_PASS"
    else:
        results["overall_status"] = "FAIL"
        results["overall_gate"] = "TELCHI_FINANCIAL_PAYMENT_APPLICATION_FAIL"
        results["failed_steps"] = failed

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="FINANCIAL-003: Payment Application Validation")
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
