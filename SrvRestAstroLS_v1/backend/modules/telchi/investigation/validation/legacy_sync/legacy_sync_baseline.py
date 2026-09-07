"""Read-only baseline checks for the legacy Telchi SAP sync behavior.

This harness deliberately does not import or execute legacy jobs. The legacy
modules import optional packages at module load time and their public wrappers
write Parquet files. Queries and transformations are reproduced in memory so
the current HANA state can be inspected without mutating legacy evidence.
"""

from __future__ import annotations

import argparse
import json
import shlex
import zipfile
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

from modules.telchi.investigation.paths import (
    INVESTIGATION_ROOT,
    LEGACY_DATA_ROOT,
    SECRET_ROOT,
)
from typing import Any
from xml.etree import ElementTree

import pandas
from hdbcli import dbapi


TELCHI_ROOT = INVESTIGATION_ROOT
LEGACY_ROOT = LEGACY_DATA_ROOT
HANA_ENV = SECRET_ROOT / "sap" / "hana.env"
WAREHOUSE_MAPPING = LEGACY_ROOT / "DS/sapWhsOfficeName.xlsx"
LEGACY_HANA_SYNC = LEGACY_ROOT / "SrvRest/srvSyncTelchiSB101.py"


def load_hana_config() -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in HANA_ENV.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, raw_value = line.partition("=")
        if not separator:
            raise ValueError("invalid HANA env line")
        parsed = shlex.split(raw_value, posix=True)
        if len(parsed) != 1:
            raise ValueError("invalid HANA env value")
        values[key] = parsed[0]
    required = {
        "TELCHI_SAP_HANA_HOST",
        "TELCHI_SAP_HANA_PORT",
        "TELCHI_SAP_HANA_SCHEMA",
        "TELCHI_SAP_HANA_USER",
        "TELCHI_SAP_HANA_PASSWORD",
    }
    if set(values) != required:
        raise ValueError("unexpected HANA env keys")
    return values


def query_frame(cursor: Any, sql: str, parameters: tuple[Any, ...] = ()) -> pandas.DataFrame:
    cursor.execute(sql, parameters)
    rows = cursor.fetchall()
    columns = [str(description[0]) for description in cursor.description or ()]
    return pandas.DataFrame(rows, columns=columns)


def scalar(cursor: Any, sql: str, parameters: tuple[Any, ...] = ()) -> Any:
    cursor.execute(sql, parameters)
    row = cursor.fetchone()
    return None if row is None else row[0]


def date_window(cursor: Any, table: str, column: str, month: str) -> tuple[str, str]:
    start = f"{month}-01"
    year, month_number = (int(part) for part in month.split("-"))
    next_month = date(year + (month_number == 12), 1 if month_number == 12 else month_number + 1, 1)
    end = next_month.isoformat()
    day = scalar(
        cursor,
        f'''SELECT TOP 1 TO_DATE("{column}") FROM "TELCHI"."{table}"
            WHERE "{column}" >= ? AND "{column}" < ?
            GROUP BY TO_DATE("{column}") ORDER BY TO_DATE("{column}")''',
        (start, end),
    )
    if day is None:
        return start, end
    day_text = str(day)[:10]
    day_end = (date.fromisoformat(day_text) + timedelta(days=1)).isoformat()
    return day_text, day_end


def cancellation_counts(cursor: Any, table: str, column: str, window: tuple[str, str]) -> dict[str, int]:
    frame = query_frame(
        cursor,
        f'''SELECT COALESCE("{column}", '<NULL>') AS "status", COUNT(*) AS "rows"
            FROM "TELCHI"."{table}"
            WHERE "DocDate" >= ? AND "DocDate" < ?
            GROUP BY "{column}" ORDER BY "status"''',
        window,
    )
    return {str(row.status): int(row.rows) for row in frame.itertuples(index=False)}


def xlsx_first_sheet_rows(path: Path) -> list[list[str]]:
    namespace = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    with zipfile.ZipFile(path) as archive:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in root.findall(f"{namespace}si"):
                shared.append("".join(text.text or "" for text in item.iter(f"{namespace}t")))
        sheet = ElementTree.fromstring(archive.read("xl/worksheets/sheet1.xml"))
        rows: list[list[str]] = []
        for row in sheet.findall(f".//{namespace}row"):
            values: dict[int, str] = {}
            for cell in row.findall(f"{namespace}c"):
                reference = cell.attrib.get("r", "A1")
                index = 0
                for character in reference:
                    if character.isalpha():
                        index = index * 26 + ord(character.upper()) - ord("A") + 1
                    else:
                        break
                value = cell.find(f"{namespace}v")
                text = "" if value is None else (value.text or "")
                if cell.attrib.get("t") == "s" and text:
                    text = shared[int(text)]
                values[index] = text
            if values:
                rows.append([values.get(index, "") for index in range(1, max(values) + 1)])
        return rows


def confirm_except_e_failure() -> bool:
    namespace: dict[str, Any] = {}
    exec(
        "def trigger():\n"
        "    try:\n"
        "        raise ValueError('probe')\n"
        "    except e:\n"
        "        return None\n",
        namespace,
    )
    try:
        namespace["trigger"]()
    except NameError:
        return True
    return False


def mapping_summary() -> dict[str, Any]:
    if not WAREHOUSE_MAPPING.is_file():
        return {"file": str(WAREHOUSE_MAPPING), "status": "MISSING"}
    rows = xlsx_first_sheet_rows(WAREHOUSE_MAPPING)
    if not rows:
        return {"file": str(WAREHOUSE_MAPPING), "status": "EMPTY"}
    header = rows[0]
    expected = {"WhsCode", "OfficeName"}
    if not expected.issubset(header):
        return {"file": str(WAREHOUSE_MAPPING), "status": "SCHEMA_MISMATCH", "columns": header}
    positions = {name: header.index(name) for name in expected}
    records = [
        (row[positions["WhsCode"]], row[positions["OfficeName"]])
        for row in rows[1:]
        if len(row) > max(positions.values())
    ]
    codes = [code for code, _ in records if code]
    return {
        "file": str(WAREHOUSE_MAPPING),
        "status": "PASS",
        "columns": header,
        "rows": len(records),
        "unique_whs_codes": len(set(codes)),
        "duplicate_whs_codes": sum(count - 1 for count in Counter(codes).values() if count > 1),
    }


def sales_check(cursor: Any, window: tuple[str, str]) -> dict[str, Any]:
    frame = query_frame(
        cursor,
        '''SELECT H."DocEntry", H."NumAtCard", H."Series", H."DocNum", H."CardCode",
                  H."CardName", H."DocTotal", H."DiscSum", H."PaidSum", H."SlpCode",
                  S."SlpName" AS "SellerNameSB1", H."UpdateDate", H."UpdateTS",
                  H."DocDate", H."DocTime", H."DocStatus", H."U_ESTADOFC",
                  H."DocSubType", L."LineNum", L."ItemCode", L."Dscription",
                  L."GPBefDisc", L."Quantity", L."GTotal", L."U_DESCLINEA",
                  L."WhsCode", L."U_TYPE"
             FROM "TELCHI"."OINV" H
             JOIN "TELCHI"."INV1" L ON L."DocEntry" = H."DocEntry"
             LEFT JOIN "TELCHI"."OSLP" S ON S."SlpCode" = H."SlpCode"
            WHERE H."DocDate" >= ? AND H."DocDate" < ?''',
        window,
    )
    result: dict[str, Any] = {
        "window": window,
        "source_rows": len(frame),
        "documents": int(frame["DocEntry"].nunique()) if not frame.empty else 0,
        "line_num_present": "LineNum" in frame,
        "docentry_itemcode_duplicate_rows": 0,
        "zero_sum_documents": 0,
        "max_document_total_delta": None,
        "canceled_documents": cancellation_counts(cursor, "OINV", "CANCELED", window),
        "mapping": mapping_summary(),
        "status": "VALIDATED_BASELINE",
    }
    if frame.empty:
        return result | {"status": "UNKNOWN"}
    grouped = frame.groupby("DocEntry", dropna=False)["GTotal"].sum().rename("SumGTotal")
    frame = frame.join(grouped, on="DocEntry")
    zero_sum = frame["SumGTotal"].eq(0)
    result["zero_sum_documents"] = int(frame.loc[zero_sum, "DocEntry"].nunique())
    frame["CoefGTotal"] = frame["GTotal"] / frame["SumGTotal"]
    frame["DescLineR"] = (frame["SumGTotal"] - frame["DocTotal"]) * frame["CoefGTotal"]
    frame["ItemSale"] = frame["GTotal"] - frame["DescLineR"]
    deltas = frame.groupby("DocEntry")["ItemSale"].sum() - frame.groupby("DocEntry")["DocTotal"].first()
    result["max_document_total_delta"] = float(deltas.abs().max())
    result["docentry_itemcode_duplicate_rows"] = int(frame.duplicated(["DocEntry", "ItemCode"]).sum())
    return result


def credit_note_check(cursor: Any, window: tuple[str, str]) -> dict[str, Any]:
    frame = query_frame(
        cursor,
        '''SELECT H."DocEntry", H."NumAtCard", H."Series", H."DocNum", H."CardCode",
                  H."CardName", H."DocTotal" * -1 AS "DocTotal", H."DiscSum",
                  H."PaidSum", H."SlpCode", H."UpdateDate", H."UpdateTS", H."DocDate",
                  H."DocTime", H."DocStatus", H."U_ESTADOFC", L."LineNum",
                  L."ItemCode", L."Dscription", L."GPBefDisc", L."Quantity" * -1 AS "Quantity",
                  L."GTotal" * -1 AS "GTotal", L."U_DESCLINEA", L."WhsCode",
                  L."U_TYPE", L."BaseRef"
             FROM "TELCHI"."ORIN" H
             JOIN "TELCHI"."RIN1" L ON L."DocEntry" = H."DocEntry"
            WHERE H."DocDate" >= ? AND H."DocDate" < ?''',
        window,
    )
    result: dict[str, Any] = {
        "window": window,
        "source_rows": len(frame),
        "documents": int(frame["DocEntry"].nunique()) if not frame.empty else 0,
        "line_num_present": "LineNum" in frame,
        "base_ref_null_rows": int(frame["BaseRef"].isna().sum()) if not frame.empty else 0,
        "canceled_documents": cancellation_counts(cursor, "ORIN", "CANCELED", window),
        "status": "VALIDATED_BASELINE" if not frame.empty else "UNKNOWN",
    }
    if frame.empty:
        return result
    grouped = frame.groupby("DocEntry", dropna=False)["GTotal"].sum().rename("SumGTotal")
    frame = frame.join(grouped, on="DocEntry")
    frame["CoefGTotal"] = frame["GTotal"] / frame["SumGTotal"]
    frame["DescLineR"] = (frame["SumGTotal"].abs() - frame["DocTotal"].abs()) * frame["CoefGTotal"]
    frame["ItemSale"] = (frame["GTotal"].abs() - frame["DescLineR"].abs()) * -1
    deltas = frame.groupby("DocEntry")["ItemSale"].sum() - frame.groupby("DocEntry")["DocTotal"].first()
    result["max_document_total_delta"] = float(deltas.abs().max())
    return result


def inventory_check(cursor: Any, window: tuple[str, str]) -> dict[str, Any]:
    frame = query_frame(
        cursor,
        '''SELECT "TransNum", "TransType", "BASE_REF", "DocLineNum", "Ref1", "Ref2",
                  "Comments", "JrnlMemo", "DocDate", "DocDueDate", "DocTime",
                  "CardCode", "CardName", "ItemCode", "Dscription", "InQty", "OutQty",
                  "TransValue" AS "CostTotal", "CalcPrice" AS "CostU",
                  ("Price" / 0.87) AS "ItemSaleU", "Price", "Balance", "SlpCode",
                  "Warehouse", "UserSign"
             FROM "TELCHI"."OINM"
            WHERE "DocDate" >= ? AND "DocDate" < ?''',
        window,
    )
    dynamic = pandas.DataFrame({"value": [None]})
    dynamic_before = bool(dynamic["value"].isna().any())
    dynamic["value"].fillna(0)
    dynamic_fillna_ineffective = bool(dynamic["value"].isna().any())
    df13 = query_frame(
        cursor,
        '''SELECT 13 AS "TransType", OINV."DocNum" AS "base_ref",
                  OINV."DocNum" AS "OINV_DocNum", OINV."CardCode" AS "OINV_CardCode",
                  OINV."DocDate" AS "SaleDocDate", OINV."DocDueDate" AS "SaleDocDueDate",
                  OINV."SlpCode" AS "SellerCodeSB1", OINV."DocTotal" AS "OfficeSale"
             FROM "TELCHI"."OINV" OINV
            WHERE OINV."DocNum" IN (
                    SELECT DISTINCT "BASE_REF" FROM "TELCHI"."OINM"
                     WHERE "DocDate" >= ? AND "DocDate" < ? AND "TransType"=13
                  )''',
        window,
    )
    df15 = query_frame(
        cursor,
        '''SELECT 15 AS "TransType", T0."DocNum" AS "base_ref",
                  T2."DocNum" AS "OINV_DocNum", T2."CardCode" AS "OINV_CardCode",
                  T2."DocDate" AS "SaleDocDate", T2."DocDueDate" AS "SaleDocDueDate",
                  T2."SlpCode" AS "SellerCodeSB1", T2."DocTotal" AS "DeliverySale"
             FROM "TELCHI"."ODLN" T0
             LEFT JOIN "TELCHI"."DLN1" T1 ON T0."DocEntry"=T1."DocEntry"
             LEFT JOIN "TELCHI"."OINV" T2
               ON T1."BaseEntry"=T2."DocEntry"
              AND T1."BaseRef"=CAST(T2."DocNum" AS varchar)
            WHERE T0."CANCELED"='N' AND T2."isIns"='Y'
              AND T0."DocNum" IN (
                    SELECT DISTINCT "BASE_REF" FROM "TELCHI"."OINM"
                     WHERE "DocDate" >= ? AND "DocDate" < ? AND "TransType"=15
                  )''',
        window,
    )
    result: dict[str, Any] = {
        "window": window,
        "source_rows": len(frame),
        "columns": list(frame.columns),
        "base_ref_column_present": "BASE_REF" in frame.columns,
        "base_ref_lower_column_present": "base_ref" in frame.columns,
        "trans_type_counts": {str(k): int(v) for k, v in frame["TransType"].value_counts(dropna=False).items()},
        "item_sale_u_null_rows": int(frame["ItemSaleU"].isna().sum()) if not frame.empty else 0,
        "item_sale_u_negative_rows": int((frame["ItemSaleU"] < 0).sum()) if not frame.empty else 0,
        "fillna_before_null": dynamic_before,
        "fillna_ineffective": dynamic_fillna_ineffective,
        "secondary_merge": {
            "df13_rows": len(df13),
            "df13_distinct_base_ref": int(df13["base_ref"].nunique()) if not df13.empty else 0,
            "df13_after_drop_duplicates": len(df13.drop_duplicates()),
            "df15_rows": len(df15),
            "df15_distinct_base_ref": int(df15["base_ref"].nunique()) if not df15.empty else 0,
            "df15_duplicate_full_rows": int(df15.duplicated().sum()),
            "df15_after_drop_duplicates": len(df15.drop_duplicates()),
        },
        "status": "VALIDATED_WITH_KNOWN_BUGS" if not frame.empty else "UNKNOWN",
    }
    return result


def products_check(cursor: Any) -> dict[str, Any]:
    row = cursor.execute('SELECT COUNT(*) FROM "TELCHI"."OITM"')
    total = int(cursor.fetchone()[0])
    sample = query_frame(
        cursor,
        '''SELECT TOP 5000 "ItemCode", "U_PRODUCE", "LastPurPrc", "LastPurCur", "LastPurDat",
                         "OnHand", "frozenFor" FROM "TELCHI"."OITM"''',
    )
    avg_count = scalar(
        cursor,
        '''SELECT COUNT(*) FROM (
                 SELECT "ItemCode" FROM "TELCHI"."OINM"
                  WHERE "DocDate" >= ADD_DAYS(CURRENT_DATE, -60)
                  GROUP BY "ItemCode"
             )''',
    )
    property_columns = scalar(
        cursor,
        '''SELECT COUNT(*) FROM SYS.TABLE_COLUMNS
            WHERE SCHEMA_NAME=? AND TABLE_NAME='OITM' AND COLUMN_NAME LIKE 'QryGroup%' ''',
        ("TELCHI",),
    )
    to_wh_rows = scalar(
        cursor,
        '''SELECT COUNT(*) FROM (
                 SELECT "Code", ROW_NUMBER() OVER (PARTITION BY "Code" ORDER BY "UpdateDate" DESC) AS rn
                   FROM "TELCHI"."OITT"
             ) WHERE rn=1''',
    )
    return {
        "rows": total,
        "sample_rows": len(sample),
        "itemun_distribution": {str(k): int(v) for k, v in sample["ItemCode"].astype(str).str[:1].map(lambda x: "Litel" if x == "L" else "Medi" if x == "M" else "Otros").value_counts().items()},
        "last_purchase_nulls": int(sample["LastPurPrc"].isna().sum()),
        "u_produce_upper_present": "U_PRODUCE" in sample.columns,
        "u_produce_lower_present": "u_produce" in sample.columns,
        "avg_calcprice_60d_item_count": int(avg_count or 0),
        "qrygroup_columns": int(property_columns or 0),
        "latest_towh_rows": int(to_wh_rows or 0),
        "status": "VALIDATED_BASELINE",
    }


def customers_check(cursor: Any) -> dict[str, Any]:
    total = int(scalar(cursor, 'SELECT COUNT(*) FROM "TELCHI"."OCRD"'))
    sample = query_frame(
        cursor,
        '''SELECT TOP 5000 "CardCode", "CardName", "CardType", "GroupCode", "City", "ListNum"
             FROM "TELCHI"."OCRD"''',
    )
    property_columns = scalar(
        cursor,
        '''SELECT COUNT(*) FROM SYS.TABLE_COLUMNS
            WHERE SCHEMA_NAME=? AND TABLE_NAME='OCRD' AND COLUMN_NAME LIKE 'QryGroup%' ''',
        ("TELCHI",),
    )
    return {
        "rows": total,
        "sample_rows": len(sample),
        "cardtype_counts": {str(k): int(v) for k, v in sample["CardType"].value_counts(dropna=False).items()},
        "qrygroup_columns": int(property_columns or 0),
        "except_e_static": True,
        "except_e_dynamic_failure": confirm_except_e_failure(),
        "status": "VALIDATED_WITH_KNOWN_BUGS",
    }


def warehouses_check(cursor: Any) -> dict[str, Any]:
    total = int(scalar(cursor, 'SELECT COUNT(*) FROM "TELCHI"."OITW"'))
    distinct_keys = int(
        scalar(
            cursor,
            '''SELECT COUNT(*) FROM (
                     SELECT "ItemCode", "WhsCode" FROM "TELCHI"."OITW"
                     GROUP BY "ItemCode", "WhsCode"
                 )''',
        )
    )
    null_dates = query_frame(
        cursor,
        '''SELECT SUM(CASE WHEN "createDate" IS NULL THEN 1 ELSE 0 END),
                  SUM(CASE WHEN "updateDate" IS NULL THEN 1 ELSE 0 END)
             FROM "TELCHI"."OITW"''',
    ).iloc[0].tolist()
    dynamic = pandas.DataFrame({"value": [None]})
    dynamic["value"].fillna(0)
    return {
        "rows": total,
        "distinct_item_whs_keys": distinct_keys,
        "duplicate_composite_keys": total - distinct_keys,
        "create_date_nulls": int(null_dates[0] or 0),
        "update_date_nulls": int(null_dates[1] or 0),
        "fillna_ineffective": bool(dynamic["value"].isna().any()),
        "status": "VALIDATED_WITH_KNOWN_BUGS",
    }


def payments_reconciliation_check(cursor: Any, month: str) -> dict[str, Any]:
    payment_window = date_window(cursor, "ORCT", "DocDate", month)
    recon_window = date_window(cursor, "OITR", "ReconDate", month)
    payments = query_frame(
        cursor,
        '''SELECT "DocEntry", "DocNum", "TransId", "Canceled", "DocDate", "DocDueDate",
                  "TaxDate", "DocTotal", "DocTotalFC", "CashSum", "TrsfrSum",
                  "CreditSum", "CheckSum" FROM "TELCHI"."ORCT"
            WHERE "DocDate" >= ? AND "DocDate" < ?''',
        payment_window,
    )
    recons = query_frame(
        cursor,
        '''SELECT H."ReconNum", H."CancelAbs", H."Canceled", L."SrcObjAbs", L."TransId",
                  L."ReconSum" FROM "TELCHI"."OITR" H
            JOIN "TELCHI"."ITR1" L ON L."ReconNum"=H."ReconNum"
            WHERE H."ReconDate" >= ? AND H."ReconDate" < ?''',
        recon_window,
    )
    return {
        "payments_window": payment_window,
        "payments_rows": len(payments),
        "payments_docentry_unique": int(payments["DocEntry"].nunique()) if not payments.empty else 0,
        "payments_canceled": {str(k): int(v) for k, v in payments["Canceled"].value_counts(dropna=False).items()} if not payments.empty else {},
        "reconciliation_window": recon_window,
        "reconciliation_rows": len(recons),
        "reconciliation_unique": int(recons["ReconNum"].nunique()) if not recons.empty else 0,
        "reconciliation_canceled": {str(k): int(v) for k, v in recons["Canceled"].value_counts(dropna=False).items()} if not recons.empty else {},
        "status": "VALIDATED_BASELINE",
    }


def static_source_check() -> dict[str, Any]:
    source = LEGACY_HANA_SYNC.read_text(encoding="utf-8")
    return {
        "file": str(LEGACY_HANA_SYNC),
        "functions_present": all(
            name in source
            for name in (
                "syncDSSale",
                "makeSaleDFRange",
                "syncDSNC",
                "makeNCDFRange",
                "syncDSMoveProduct",
                "makeMoveProductRange",
                "makeProduct",
                "makeProductPropiety",
                "makeClient",
                "makeClientPropiety",
                "makeWhareHouse",
                "def job",
            )
        ),
        "legacy_endpoint_risk": "192.168.21.4" in source,
        "legacy_parquet_write_targets": sorted(set(line.split("__DS__ + ", 1)[1].split("'")[1] for line in source.splitlines() if "__DS__ + '" in line and "parq" in line)),
        "fillna_without_assignment_count": sum(
            1
            for line in source.splitlines()
            if ".fillna(" in line and "=" not in line.split(".fillna(", 1)[0]
        ),
        "except_e_present": "except e:" in source,
        "price_factor_present": "0.87" in source,
        "product_case_mismatch_present": 'DF["u_produce"]' in source or "DF['u_produce']" in source,
    }


def run(month: str) -> dict[str, Any]:
    config = load_hana_config()
    password = config.pop("TELCHI_SAP_HANA_PASSWORD")
    connection = dbapi.connect(
        address=config["TELCHI_SAP_HANA_HOST"],
        port=int(config["TELCHI_SAP_HANA_PORT"]),
        user=config["TELCHI_SAP_HANA_USER"],
        password=password,
    )
    cursor = connection.cursor()
    try:
        sales_window = date_window(cursor, "OINV", "DocDate", month)
        credit_window = date_window(cursor, "ORIN", "DocDate", month)
        movement_window = date_window(cursor, "OINM", "DocDate", month)
        result = {
            "month": month,
            "static_source": static_source_check(),
            "sales": sales_check(cursor, sales_window),
            "credit_notes": credit_note_check(cursor, credit_window),
            "inventory_movements": inventory_check(cursor, movement_window),
            "products": products_check(cursor),
            "customers": customers_check(cursor),
            "warehouses": warehouses_check(cursor),
            "payments_reconciliation": payments_reconciliation_check(cursor, month),
            "parquet": {
                "read_engine": "UNAVAILABLE" if not __import__("importlib.util").util.find_spec("pyarrow") else "AVAILABLE",
                "legacy_files_present": len(list((LEGACY_ROOT / "DS").glob("*.parq"))) > 0,
                "parity": "UNKNOWN",
            },
        }
        return result
    finally:
        cursor.close()
        connection.rollback()
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--month", default="2023-02")
    args = parser.parse_args()
    print(json.dumps(run(args.month), indent=2, default=str, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
