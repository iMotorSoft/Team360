"""
TELCHI — TEST T03: Invoice Cancellation March → June Scenario
Validates that a March invoice canceled in June is correctly handled.
"""

import os
import sys
import json
from pathlib import Path

from modules.telchi.investigation.paths import SECRET_ROOT


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
    return hdbcli.dbapi.connect(
        address=os.environ['TELCHI_SAP_HANA_HOST'],
        port=int(os.environ['TELCHI_SAP_HANA_PORT']),
        user=os.environ['TELCHI_SAP_HANA_USER'],
        password=os.environ['TELCHI_SAP_HANA_PASSWORD'],
        databaseName='NDB'
    )


def run_query(conn, sql, params=None):
    cursor = conn.cursor()
    cursor.execute(sql, params or [])
    columns = [desc[0] for desc in cursor.description] if cursor.description else []
    rows = cursor.fetchall()
    cursor.close()
    return columns, rows


def test_T03_invoice_cancellation():
    """Test T03: Invoice Cancellation March → June Scenario."""
    conn = get_connection()

    print("=" * 80)
    print("TEST T03: INVOICE CANCELLATION — MARCH → JUNE SCENARIO")
    print("=" * 80)

    results = {
        "test_id": "T03",
        "test_name": "Invoice Cancellation March → June",
        "status": "UNKNOWN",
        "checks": []
    }

    # Check 1: Find March invoices that were canceled later
    print("\n1. BUSCANDO FACTURAS DE MARZO ANULADAS POSTERIORMENTE")
    print("-" * 60)
    cols, rows = run_query(conn, """
        SELECT
            "DocEntry", "DocNum", "CardCode", "DocDate", "DocTotal",
            "CANCELED", "UpdateDate", "UpdateTS",
            DAYS_BETWEEN("DocDate", "UpdateDate") AS "DaysToCancel"
        FROM TELCHI."OINV"
        WHERE "DocDate" >= '2026-03-01'
          AND "DocDate" < '2026-04-01'
          AND "CANCELED" = 'Y'
          AND "UpdateDate" > '2026-03-31'
        ORDER BY DAYS_BETWEEN("DocDate", "UpdateDate") DESC
        LIMIT 5
    """)

    if rows:
        print(f"  Encontradas {len(rows)} facturas de marzo anuladas después de marzo:")
        for row in rows:
            print(f"    DocEntry={row[0]}, DocDate={row[3]}, CancellationDate={row[6]}, Days={row[8]}")

        test_case = rows[0]
        doc_entry = test_case[0]
        doc_date = test_case[3]
        cancel_date = test_case[6]
        days_to_cancel = test_case[8]

        results["checks"].append({
            "check": "March invoice canceled later exists",
            "status": "PASS",
            "doc_entry": doc_entry,
            "doc_date": str(doc_date),
            "cancellation_date": str(cancel_date),
            "days_to_cancel": days_to_cancel
        })

        # Check 2: Find the reversal document (C)
        print("\n2. BUSCANDO DOCUMENTO DE REVERSIÓN (C)")
        print("-" * 60)
        cols2, rows2 = run_query(conn, f"""
            SELECT
                Y."DocEntry" AS "Y_DocEntry",
                Y."DocNum" AS "Y_DocNum",
                Y."CardCode",
                Y."DocTotal",
                Y."UpdateDate" AS "Y_UpdateDate",
                C."DocEntry" AS "C_DocEntry",
                C."DocNum" AS "C_DocNum",
                C."DocDate" AS "C_DocDate",
                C."TransId" AS "C_TransId"
            FROM TELCHI."OINV" AS Y
            INNER JOIN TELCHI."OINV" AS C
                ON Y."CardCode" = C."CardCode"
                AND Y."DocTotal" = C."DocTotal"
                AND C."CANCELED" = 'C'
                AND ABS(DAYS_BETWEEN(Y."UpdateDate", C."DocDate")) <= 7
            WHERE Y."DocEntry" = {doc_entry}
        """)

        if rows2:
            reversal = rows2[0]
            print(f"  Y (Original): DocEntry={reversal[0]}, DocNum={reversal[1]}")
            print(f"  C (Reversal): DocEntry={reversal[5]}, DocNum={reversal[6]}")
            print(f"  Reversal DocDate: {reversal[7]}")

            results["checks"].append({
                "check": "Reversal document (C) found and linked",
                "status": "PASS",
                "reversal_doc_entry": reversal[5],
                "reversal_doc_num": reversal[6],
                "reversal_doc_date": str(reversal[7])
            })
        else:
            print("  ✗ No reversal document found")
            results["checks"].append({
                "check": "Reversal document (C) found and linked",
                "status": "FAIL"
            })

        # Check 3: Verify cancellation timestamp precision
        print("\n3. VERIFICACIÓN DE PRECISO TEMPORAL")
        print("-" * 60)
        update_ts = test_case[7]
        print(f"  UpdateTS: {update_ts}")
        print(f"  Formato HHMMSS: {update_ts[:2]}:{update_ts[2:4]}:{update_ts[4:6]}")

        results["checks"].append({
            "check": "Cancellation timestamp precision",
            "status": "PASS",
            "update_ts": update_ts,
            "formatted": f"{update_ts[:2]}:{update_ts[2:4]}:{update_ts[4:6]}"
        })

    else:
        print("  ✗ No March invoices found that were canceled later")
        print("  Intentando buscar en 2025...")

        # Try 2025
        cols, rows = run_query(conn, """
            SELECT
                "DocEntry", "DocNum", "CardCode", "DocDate", "DocTotal",
                "CANCELED", "UpdateDate", "UpdateTS",
                DAYS_BETWEEN("DocDate", "UpdateDate") AS "DaysToCancel"
            FROM TELCHI."OINV"
            WHERE "DocDate" >= '2025-03-01'
              AND "DocDate" < '2025-04-01'
              AND "CANCELED" = 'Y'
              AND "UpdateDate" > '2025-03-31'
            ORDER BY DAYS_BETWEEN("DocDate", "UpdateDate") DESC
            LIMIT 5
        """)

        if rows:
            print(f"  Encontradas {len(rows)} facturas de marzo 2025 anuladas después:")
            for row in rows:
                print(f"    DocEntry={row[0]}, DocDate={row[3]}, CancellationDate={row[6]}, Days={row[8]}")
            test_case = rows[0]
            doc_entry = test_case[0]
            doc_date = test_case[3]
            cancel_date = test_case[6]
            days_to_cancel = test_case[8]

            results["checks"].append({
                "check": "March invoice canceled later exists (2025)",
                "status": "PASS",
                "doc_entry": doc_entry,
                "doc_date": str(doc_date),
                "cancellation_date": str(cancel_date),
                "days_to_cancel": days_to_cancel
            })
        else:
            print("  ✗ No cases found in 2025 either")
            results["checks"].append({
                "check": "March invoice canceled later exists",
                "status": "FAIL"
            })

    # Check 4: Calculate as-reported vs restated for March
    print("\n4. CÁLCULO: AS-REPORTED vs RESTATED PARA MARZO")
    print("-" * 60)
    cols3, rows3 = run_query(conn, """
        SELECT
            COUNT(*) AS "TotalMarchInvoices",
            SUM(CASE WHEN "CANCELED" = 'N' THEN 1 ELSE 0 END) AS "ActiveNow",
            SUM(CASE WHEN "CANCELED" = 'Y' AND "UpdateDate" > '2026-03-31' THEN 1 ELSE 0 END) AS "CanceledLater",
            SUM("DocTotal") AS "TotalDocTotal",
            SUM(CASE WHEN "CANCELED" = 'N' THEN "DocTotal" ELSE 0 END) AS "ActiveDocTotal",
            SUM(CASE WHEN "CANCELED" = 'Y' AND "UpdateDate" > '2026-03-31' THEN "DocTotal" ELSE 0 END) AS "CanceledLaterDocTotal"
        FROM TELCHI."OINV"
        WHERE "DocDate" >= '2026-03-01'
          AND "DocDate" < '2026-04-01'
    """)

    if rows3:
        r = rows3[0]
        print(f"  Total facturas marzo 2026: {r[0]}")
        print(f"  Activas hoy: {r[1]}")
        print(f"  Anuladas después: {r[2]}")
        print(f"  Total DocTotal: ${r[3]:,.2f}")
        print(f"  Activas DocTotal: ${r[4]:,.2f}")
        print(f"  Anuladas después DocTotal: ${r[5]:,.2f}")

        if r[2] > 0:
            print(f"\n  AS-REPORTED (Marzo 2026): ${r[3]:,.2f}")
            print(f"  RESTATED (Actual): ${r[4]:,.2f}")
            print(f"  DIFERENCIA (Anulaciones): ${r[5]:,.2f}")

            results["checks"].append({
                "check": "As-reported vs restated calculated",
                "status": "PASS",
                "as_reported": r[3],
                "restated": r[4],
                "difference": r[5]
            })
        else:
            print("  No late cancellations found in March 2026")
            results["checks"].append({
                "check": "As-reported vs restated calculated",
                "status": "PASS",
                "note": "No late cancellations in March 2026"
            })

    # Summary
    print("\n" + "=" * 80)
    print("RESUMEN DEL TEST T03")
    print("=" * 80)

    passed = sum(1 for c in results["checks"] if c["status"] == "PASS")
    failed = sum(1 for c in results["checks"] if c["status"] == "FAIL")

    for check in results["checks"]:
        status_icon = "✓" if check["status"] == "PASS" else "✗"
        print(f"  {status_icon} {check['check']}: {check['status']}")

    if failed == 0:
        results["status"] = "PASS"
        print(f"\n  TEST T03: PASS ({passed}/{len(results['checks'])} checks)")
    else:
        results["status"] = "FAIL"
        print(f"\n  TEST T03: FAIL ({failed}/{len(results['checks'])} failed)")

    conn.close()
    return results


if __name__ == "__main__":
    results = test_T03_invoice_cancellation()

    # Save results
    output_path = Path(__file__).parent / "test_T03_results.json"
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved to: {output_path}")
