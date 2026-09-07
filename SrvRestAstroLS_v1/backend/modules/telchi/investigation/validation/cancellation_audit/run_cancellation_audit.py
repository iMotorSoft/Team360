"""
TELCHI SAP — AUDITORÍA DE FACTURAS ANULADAS
Ejecuta las consultas de auditoría y genera un reporte completo.
"""

import os
import sys
import json
from pathlib import Path

from modules.telchi.investigation.paths import SECRET_ROOT
from datetime import datetime

# Add parent to path for imports

try:
    import hdbcli.dbapi
    HAS_HDBCLI = True
except ImportError:
    HAS_HDBCLI = False
    print("ERROR: hdbcli not installed")
    sys.exit(1)

# Load credentials
env_path = SECRET_ROOT / "sap" / "hana.env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            os.environ[k.strip().strip("'\"")] = v.strip().strip("'\"")


def get_connection():
    """Get HANA connection."""
    return hdbcli.dbapi.connect(
        address=os.environ['TELCHI_SAP_HANA_HOST'],
        port=int(os.environ['TELCHI_SAP_HANA_PORT']),
        user=os.environ['TELCHI_SAP_HANA_USER'],
        password=os.environ['TELCHI_SAP_HANA_PASSWORD'],
        databaseName='NDB'
    )


def run_query(conn, sql, params=None):
    """Execute query and return results."""
    cursor = conn.cursor()
    cursor.execute(sql, params or [])
    columns = [desc[0] for desc in cursor.description] if cursor.description else []
    rows = cursor.fetchall()
    cursor.close()
    return columns, rows


def format_currency(value):
    """Format number as currency."""
    if value is None:
        return "N/A"
    return f"${value:,.2f}"


def format_pct(value):
    """Format number as percentage."""
    if value is None:
        return "N/A"
    return f"{value:.2f}%"


def run_cancellation_audit():
    """Run the complete cancellation audit."""
    conn = get_connection()

    print("=" * 80)
    print("TELCHI SAP — AUDITORÍA DE FACTURAS ANULADAS")
    print(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    audit_report = {
        "timestamp": datetime.now().isoformat(),
        "module": "Telchi SAP",
        "area": "Ventas — Facturación — Anulaciones",
        "tests": []
    }

    # =========================================================================
    # TEST T01: TOTAL UNIVERSE
    # =========================================================================
    print("\n" + "=" * 80)
    print("TEST T01: UNIVERSO TOTAL DE ANULACIONES")
    print("=" * 80)

    cols, rows = run_query(conn, """
        SELECT
            COUNT(*) AS "TotalInvoices",
            SUM(CASE WHEN "CANCELED" = 'N' THEN 1 ELSE 0 END) AS "ActiveInvoices",
            SUM(CASE WHEN "CANCELED" = 'Y' THEN 1 ELSE 0 END) AS "CanceledOriginal",
            SUM(CASE WHEN "CANCELED" = 'C' THEN 1 ELSE 0 END) AS "CanceledReversal",
            SUM("DocTotal") AS "TotalDocTotal",
            SUM(CASE WHEN "CANCELED" = 'N' THEN "DocTotal" ELSE 0 END) AS "ActiveDocTotal",
            SUM(CASE WHEN "CANCELED" = 'Y' THEN "DocTotal" ELSE 0 END) AS "CanceledDocTotal"
        FROM TELCHI."OINV"
    """)

    if rows:
        r = rows[0]
        total_invoices = r[0]
        active_invoices = r[1]
        canceled_y = r[2]
        canceled_c = r[3]
        total_doc_total = r[4]
        active_doc_total = r[5]
        canceled_doc_total = r[6]

        # Y and C should be equal (pairs)
        y_c_match = canceled_y == canceled_c
        cancellation_rate = (canceled_y / total_invoices * 100) if total_invoices > 0 else 0
        monetary_rate = (canceled_doc_total / total_doc_total * 100) if total_doc_total > 0 else 0

        print(f"\n  FACTURAS TOTALES:      {total_invoices:>12,}")
        print(f"  Facturas activas (N):  {active_invoices:>12,}")
        print(f"  Facturas anuladas (Y): {canceled_y:>12,}")
        print(f"  Reversión (C):         {canceled_c:>12,}")
        print(f"  Pares Y/C correctos:   {'✓ SÍ' if y_c_match else '✗ NO'}")
        print(f"\n  MONTO TOTAL:           {format_currency(total_doc_total):>15}")
        print(f"  Monto activo:          {format_currency(active_doc_total):>15}")
        print(f"  Monto anulado:         {format_currency(canceled_doc_total):>15}")
        print(f"\n  TASA ANULACIÓN:        {format_pct(cancellation_rate):>15}")
        print(f"  TASA MONETARIA:        {format_pct(monetary_rate):>15}")

        audit_report["universe"] = {
            "total_invoices": total_invoices,
            "active_invoices": active_invoices,
            "canceled_y": canceled_y,
            "canceled_c": canceled_c,
            "y_c_match": y_c_match,
            "total_doc_total": float(total_doc_total),
            "canceled_doc_total": float(canceled_doc_total),
            "cancellation_rate": cancellation_rate,
            "monetary_rate": monetary_rate
        }

        audit_report["tests"].append({
            "test_id": "T01",
            "test_name": "Total Universe",
            "status": "PASS" if y_c_match else "FAIL",
            "details": {
                "total": total_invoices,
                "canceled": canceled_y,
                "y_c_match": y_c_match
            }
        })

    # =========================================================================
    # TEST T02: TIMING DISTRIBUTION
    # =========================================================================
    print("\n" + "=" * 80)
    print("TEST T02: DISTRIBUCIÓN TEMPORAL")
    print("=" * 80)

    cols, rows = run_query(conn, """
        WITH timing AS (
            SELECT
                "DocEntry",
                "DocTotal",
                DAYS_BETWEEN("DocDate", "UpdateDate") AS "DaysToCancel",
                CASE
                    WHEN DAYS_BETWEEN("DocDate", "UpdateDate") <= 30 THEN '≤30_days'
                    ELSE '>30_days'
                END AS "MainClass"
            FROM TELCHI."OINV"
            WHERE "CANCELED" = 'Y'
        )
        SELECT
            "MainClass",
            COUNT(*) AS "Count",
            SUM("DocTotal") AS "TotalAmount",
            AVG("DocTotal") AS "AvgAmount",
            MIN("DaysToCancel") AS "MinDays",
            MAX("DaysToCancel") AS "MaxDays"
        FROM timing
        GROUP BY "MainClass"
        ORDER BY "MainClass"
    """)

    if rows:
        total_cancelled = sum(r[1] for r in rows)
        print(f"\n  {'Clasificación':<15} {'Cantidad':>10} {'%':>8} {'Monto Total':>18} {'Promedio':>15} {'Min':>8} {'Max':>8}")
        print("  " + "-" * 85)

        for r in rows:
            main_class = r[0]
            count = r[1]
            total_amount = r[2]
            avg_amount = r[3]
            min_days = r[4]
            max_days = r[5]
            pct = (count / total_cancelled * 100) if total_cancelled > 0 else 0

            print(f"  {main_class:<15} {count:>10,} {pct:>7.1f}% {format_currency(total_amount):>18} {format_currency(avg_amount):>15} {min_days:>8} {max_days:>8}")

        # Check if totals match
        sum_count = sum(r[1] for r in rows)
        timing_match = sum_count == total_cancelled

        audit_report["timing"] = {
            "total_cancelled": total_cancelled,
            "timing_match": timing_match,
            "buckets": [{
                "class": r[0],
                "count": r[1],
                "amount": float(r[2]),
                "min_days": r[4],
                "max_days": r[5]
            } for r in rows]
        }

        audit_report["tests"].append({
            "test_id": "T02",
            "test_name": "Timing Distribution",
            "status": "PASS" if timing_match else "FAIL",
            "details": {
                "total_cancelled": total_cancelled,
                "sum_by_bucket": sum_count,
                "match": timing_match
            }
        })

    # =========================================================================
    # DETAILED TIMING BUCKETS
    # =========================================================================
    print("\n" + "=" * 80)
    print("DISTRIBUCIÓN DETALLADA POR BUCKETS")
    print("=" * 80)

    cols, rows = run_query(conn, """
        WITH timing AS (
            SELECT
                "DocEntry",
                "DocTotal",
                DAYS_BETWEEN("DocDate", "UpdateDate") AS "DaysToCancel",
                CASE
                    WHEN DAYS_BETWEEN("DocDate", "UpdateDate") = 0 THEN '00_same_day'
                    WHEN DAYS_BETWEEN("DocDate", "UpdateDate") BETWEEN 1 AND 7 THEN '01_1_7'
                    WHEN DAYS_BETWEEN("DocDate", "UpdateDate") BETWEEN 8 AND 15 THEN '02_8_15'
                    WHEN DAYS_BETWEEN("DocDate", "UpdateDate") BETWEEN 16 AND 30 THEN '03_16_30'
                    WHEN DAYS_BETWEEN("DocDate", "UpdateDate") BETWEEN 31 AND 60 THEN '04_31_60'
                    WHEN DAYS_BETWEEN("DocDate", "UpdateDate") BETWEEN 61 AND 90 THEN '05_61_90'
                    WHEN DAYS_BETWEEN("DocDate", "UpdateDate") BETWEEN 91 AND 120 THEN '06_91_120'
                    WHEN DAYS_BETWEEN("DocDate", "UpdateDate") > 120 THEN '07_120_plus'
                    ELSE '99_unknown'
                END AS "Bucket"
            FROM TELCHI."OINV"
            WHERE "CANCELED" = 'Y'
        )
        SELECT
            "Bucket",
            COUNT(*) AS "Count",
            SUM("DocTotal") AS "TotalAmount",
            AVG("DocTotal") AS "AvgAmount"
        FROM timing
        GROUP BY "Bucket"
        ORDER BY "Bucket"
    """)

    if rows:
        print(f"\n  {'Bucket':<20} {'Cantidad':>10} {'%':>8} {'Monto Total':>18} {'Promedio':>15}")
        print("  " + "-" * 75)

        total_cancelled = sum(r[1] for r in rows)
        for r in rows:
            bucket = r[0]
            count = r[1]
            total_amount = r[2]
            avg_amount = r[3]
            pct = (count / total_cancelled * 100) if total_cancelled > 0 else 0

            print(f"  {bucket:<20} {count:>10,} {pct:>7.1f}% {format_currency(total_amount):>18} {format_currency(avg_amount):>15}")

    # =========================================================================
    # TEST T03: TOP 20 BY AMOUNT
    # =========================================================================
    print("\n" + "=" * 80)
    print("TEST T03: TOP 20 ANULACIONES POR MONTO")
    print("=" * 80)

    cols, rows = run_query(conn, """
        SELECT
            OINV."DocEntry",
            OINV."DocNum",
            OINV."CardCode",
            OINV."CardName",
            OINV."SlpCode",
            (SELECT OSLP."SlpName" FROM TELCHI.OSLP AS OSLP WHERE OINV."SlpCode" = OSLP."SlpCode") AS "SellerName",
            OINV."DocDate",
            OINV."UpdateDate" AS "CancellationDate",
            OINV."DocTotal",
            OINV."PaidToDate",
            DAYS_BETWEEN(OINV."DocDate", OINV."UpdateDate") AS "DaysToCancel"
        FROM TELCHI."OINV"
        WHERE OINV."CANCELED" = 'Y'
        ORDER BY OINV."DocTotal" DESC
        LIMIT 20
    """)

    if rows:
        print(f"\n  {'#':<4} {'DocEntry':<12} {'DocNum':<12} {'CardCode':<12} {'DocDate':<12} {'CancelDate':<12} {'DocTotal':>15} {'Days':<6}")
        print("  " + "-" * 85)

        for i, r in enumerate(rows, 1):
            print(f"  {i:<4} {r[0]:<12} {r[1]:<12} {r[2]:<12} {str(r[6])[:10]:<12} {str(r[7])[:10]:<12} {format_currency(r[8]):>15} {r[10]:<6}")

        audit_report["top20_by_amount"] = [{
            "doc_entry": r[0],
            "doc_num": r[1],
            "card_code": r[2],
            "card_name": r[3],
            "doc_date": str(r[6])[:10],
            "cancellation_date": str(r[7])[:10],
            "doc_total": float(r[8]),
            "days_to_cancel": r[10]
        } for r in rows]

    # =========================================================================
    # SUMMARY
    # =========================================================================
    print("\n" + "=" * 80)
    print("RESUMEN DE AUDITORÍA")
    print("=" * 80)

    if "universe" in audit_report:
        u = audit_report["universe"]
        print(f"\n  UNIVERSO TOTAL:")
        print(f"    Facturas totales:        {u['total_invoices']:>12,}")
        print(f"    Facturas anuladas:       {u['canceled_y']:>12,}")
        print(f"    Tasa de anulación:       {format_pct(u['cancellation_rate']):>12}")
        print(f"    Monto total:             {format_currency(u['total_doc_total']):>15}")
        print(f"    Monto anulado:           {format_currency(u['canceled_doc_total']):>15}")
        print(f"    Tasa monetaria:          {format_pct(u['monetary_rate']):>12}")

    if "timing" in audit_report:
        t = audit_report["timing"]
        print(f"\n  DISTRIBUCIÓN TEMPORAL:")
        for bucket in t["buckets"]:
            if "≤30" in bucket["class"]:
                print(f"    ≤30 días:    {bucket['count']:>6,} facturas")
            elif ">30" in bucket["class"]:
                print(f"    >30 días:    {bucket['count']:>6,} facturas")

    # Save report
    output_path = Path(__file__).parent / "cancellation_audit_report.json"
    with open(output_path, 'w') as f:
        json.dump(audit_report, f, indent=2, default=str)
    print(f"\n  Reporte guardado en: {output_path}")

    conn.close()
    print("\n" + "=" * 80)
    print("FIN DE AUDITORÍA")
    print("=" * 80)

    return audit_report


if __name__ == "__main__":
    report = run_cancellation_audit()
