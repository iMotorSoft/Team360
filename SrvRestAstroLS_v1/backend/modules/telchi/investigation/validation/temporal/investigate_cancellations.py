"""
TELCHI — FASE 0: Investigación de Anulaciones en SAP HANA
Investiga cómo SAP Telchi maneja anulaciones de facturas, pagos y reconciliaciones.
"""

import os
import sys
import json
from pathlib import Path

from modules.telchi.investigation.paths import SECRET_ROOT

# Add parent to path for imports

try:
    import hdbcli.dbapi
    HAS_HDBCLI = True
except ImportError:
    HAS_HDBCLI = False
    print("WARNING: hdbcli not installed")

# Load credentials
env_path = SECRET_ROOT / "sap" / "hana.env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            os.environ[key.strip().strip("'\"")] = value.strip().strip("'\"")

HOST = os.environ.get('TELCHI_SAP_HANA_HOST', '127.0.0.1')
PORT = int(os.environ.get('TELCHI_SAP_HANA_PORT', '30015'))
SCHEMA = os.environ.get('TELCHI_SAP_HANA_SCHEMA', 'TELCHI')
USER = os.environ.get('TELCHI_SAP_HANA_USER', 'insiding_hana')
PASS = os.environ.get('TELCHI_SAP_HANA_PASSWORD', '')


def get_connection():
    """Get HANA connection."""
    if not HAS_HDBCLI:
        raise RuntimeError("hdbcli not installed")
    return hdbcli.dbapi.connect(
        address=HOST,
        port=PORT,
        user=USER,
        password=PASS,
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


def investigate_cancellation_patterns():
    """Investigate how SAP Telchi handles cancellations."""
    conn = get_connection()

    print("=" * 80)
    print("TELCHI — INVESTIGACIÓN DE ANULACIONES")
    print("=" * 80)

    # 1. Invoice cancellation patterns
    print("\n1. PATRONES DE ANULACIÓN DE FACTURAS (OINV)")
    print("-" * 60)
    cols, rows = run_query(conn, """
        SELECT
            "CANCELED",
            COUNT(*) AS "Count",
            SUM("DocTotal") AS "TotalDocTotal",
            SUM("PaidToDate") AS "TotalPaidToDate"
        FROM TELCHI."OINV"
        GROUP BY "CANCELED"
        ORDER BY "CANCELED"
    """)
    print(f"  {'CANCELED':<10} {'Count':<10} {'DocTotal':>15} {'PaidToDate':>15}")
    for row in rows:
        print(f"  {str(row[0]):<10} {row[1]:<10} {row[2]:>15,.2f} {row[3]:>15,.2f}")

    # 2. Check for cancellation date fields
    print("\n2. CAMPOS DE FECHA EN OINV")
    print("-" * 60)
    cols, rows = run_query(conn, """
        SELECT COLUMN_NAME, DATA_TYPE_NAME
        FROM SYS.TABLE_COLUMNS
        WHERE SCHEMA_NAME = 'TELCHI'
          AND TABLE_NAME = 'OINV'
          AND UPPER(COLUMN_NAME) LIKE '%DATE%'
           OR UPPER(COLUMN_NAME) LIKE '%CANCEL%'
           OR UPPER(COLUMN_NAME) LIKE '%UPDATE%'
        ORDER BY ORDINAL_POSITION
    """)
    print(f"  {'Column':<30} {'Type':<20}")
    for row in rows:
        print(f"  {row[0]:<30} {row[1]:<20}")

    # 3. Look for reversal documents
    print("\n3. DOCUMENTOS DE REVERSIÓN (CANCELED='C')")
    print("-" * 60)
    cols, rows = run_query(conn, """
        SELECT
            OINV."DocEntry",
            OINV."DocNum",
            OINV."CardCode",
            OINV."DocDate",
            OINV."UpdateDate",
            OINV."DocTotal",
            OINV."CANCELED",
            OINV."TransId",
            OINV."DocSubType"
        FROM TELCHI."OINV" AS OINV
        WHERE OINV."CANCELED" = 'C'
        ORDER BY OINV."UpdateDate" DESC
        LIMIT 20
    """)
    if rows:
        print(f"  {'DocEntry':<10} {'DocNum':<10} {'CardCode':<15} {'DocDate':<12} {'UpdateDate':<12} {'DocTotal':>15} {'TransId':<10}")
        for row in rows:
            print(f"  {row[0]:<10} {row[1]:<10} {row[2]:<15} {str(row[3]):<12} {str(row[4]):<12} {row[5]:>15,.2f} {row[6]:<10}")
    else:
        print("  No reversal documents found")

    # 4. Look for canceled invoices (Y)
    print("\n4. FACTURAS ANULADAS (CANCELED='Y') - Recientes")
    print("-" * 60)
    cols, rows = run_query(conn, """
        SELECT
            OINV."DocEntry",
            OINV."DocNum",
            OINV."CardCode",
            OINV."DocDate",
            OINV."UpdateDate",
            OINV."DocTotal",
            OINV."PaidToDate",
            OINV."CANCELED",
            OINV."TransId"
        FROM TELCHI."OINV" AS OINV
        WHERE OINV."CANCELED" = 'Y'
        ORDER BY OINV."UpdateDate" DESC
        LIMIT 20
    """)
    if rows:
        print(f"  {'DocEntry':<10} {'DocNum':<10} {'CardCode':<15} {'DocDate':<12} {'UpdateDate':<12} {'DocTotal':>15} {'PaidToDate':>15}")
        for row in rows:
            print(f"  {row[0]:<10} {row[1]:<10} {row[2]:<15} {str(row[3]):<12} {str(row[4]):<12} {row[5]:>15,.2f} {row[6]:>15,.2f}")
    else:
        print("  No canceled invoices found")

    # 5. Check if DocDate vs UpdateDate can identify cancellation timing
    print("\n5. ANÁLISIS DE TIMING: DocDate vs UpdateDate para anuladas")
    print("-" * 60)
    cols, rows = run_query(conn, """
        SELECT
            COUNT(*) AS "TotalCanceled",
            AVG(DAYS_BETWEEN(OINV."DocDate", OINV."UpdateDate")) AS "AvgDaysBetween",
            MIN(DAYS_BETWEEN(OINV."DocDate", OINV."UpdateDate")) AS "MinDaysBetween",
            MAX(DAYS_BETWEEN(OINV."DocDate", OINV."UpdateDate")) AS "MaxDaysBetween"
        FROM TELCHI."OINV" AS OINV
        WHERE OINV."CANCELED" IN ('Y', 'C')
    """)
    if rows and rows[0][0] > 0:
        print(f"  Total anuladas: {rows[0][0]}")
        print(f"  Días promedio entre DocDate y UpdateDate: {rows[0][1]:.1f}")
        print(f"  Mínimo: {rows[0][2]} días")
        print(f"  Máximo: {rows[0][3]} días")

    # 6. Payment cancellation patterns
    print("\n6. PATRONES DE ANULACIÓN DE PAGOS (ORCT)")
    print("-" * 60)
    cols, rows = run_query(conn, """
        SELECT
            "Canceled",
            COUNT(*) AS "Count",
            SUM("DocTotal") AS "TotalDocTotal"
        FROM TELCHI."ORCT"
        GROUP BY "Canceled"
        ORDER BY "Canceled"
    """)
    print(f"  {'Canceled':<10} {'Count':<10} {'DocTotal':>15}")
    for row in rows:
        print(f"  {str(row[0]):<10} {row[1]:<10} {row[2]:>15,.2f}")

    # 7. Reconciliation cancellation patterns
    print("\n7. PATRONES DE ANULACIÓN DE RECONCILIACIONES (OITR)")
    print("-" * 60)
    cols, rows = run_query(conn, """
        SELECT
            "Canceled",
            COUNT(*) AS "Count",
            SUM("Total") AS "TotalAmount"
        FROM TELCHI."OITR"
        GROUP BY "Canceled"
        ORDER BY "Canceled"
    """)
    print(f"  {'Canceled':<10} {'Count':<10} {'TotalAmount':>15}")
    for row in rows:
        print(f"  {str(row[0]):<10} {row[1]:<10} {row[2]:>15,.2f}")

    # 8. Check for UpdateTS (timestamp) availability
    print("\n8. DISPONIBILIDAD DE UpdateTS (timestamp)")
    print("-" * 60)
    cols, rows = run_query(conn, """
        SELECT
            COUNT(*) AS "TotalInvoices",
            SUM(CASE WHEN "UpdateTS" IS NOT NULL AND "UpdateTS" != '' THEN 1 ELSE 0 END) AS "WithUpdateTS"
        FROM TELCHI."OINV"
        WHERE "DocDate" >= '2024-01-01'
    """)
    if rows:
        print(f"  Facturas desde 2024: {rows[0][0]}")
        print(f"  Con UpdateTS: {rows[0][1]}")
        print(f"  Cobertura: {rows[0][1]/rows[0][0]*100:.1f}%")

    # 9. Check for any cancellation-specific columns
    print("\n9. COLUMNAS QUE PUEDEN INDICAR ANULACIÓN")
    print("-" * 60)
    cols, rows = run_query(conn, """
        SELECT COLUMN_NAME, DATA_TYPE_NAME
        FROM SYS.TABLE_COLUMNS
        WHERE SCHEMA_NAME = 'TELCHI'
          AND TABLE_NAME = 'OINV'
          AND (
            UPPER(COLUMN_NAME) LIKE '%CANCEL%'
            OR UPPER(COLUMN_NAME) LIKE '%REVERS%'
            OR UPPER(COLUMN_NAME) LIKE '%VOID%'
            OR UPPER(COLUMN_NAME) LIKE '%DELETED%'
            OR UPPER(COLUMN_NAME) LIKE '%STATUS%'
            OR UPPER(COLUMN_NAME) LIKE '%U_ESTADO%'
          )
        ORDER BY ORDINAL_POSITION
    """)
    if rows:
        for row in rows:
            print(f"  {row[0]:<30} {row[1]:<20}")
    else:
        print("  No additional cancellation columns found")

    conn.close()
    print("\n" + "=" * 80)
    print("FIN DE INVESTIGACIÓN")
    print("=" * 80)


if __name__ == "__main__":
    investigate_cancellation_patterns()
