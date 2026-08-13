"""Reproducible, read-only audit probes for the historical Telchi SAP sync.

The probes validate bounded legacy SQL and proposed current equivalents against
the real HANA schema. They never write SAP data or historical Parquet files.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from typing import Any

from smoke_telchi_sap_hana import (
    HANA_HOST,
    HANA_PORT,
    HANA_SCHEMA,
    HANA_USER,
    PRIVATE_ENV_FILE,
    SmokeBlocked,
    load_private_config,
    tcp_preflight,
)


SAMPLE_FROM = "2026-08-01"
SAMPLE_TO = "2026-08-13 23:59:59"
ALLOWED_STATUSES = {"PASS", "CHANGE_REQUIRED", "DEPRECATED", "BLOCKED"}
WRITE_TOKEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|MERGE|CREATE|ALTER|DROP|TRUNCATE|UPSERT|REPLACE)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Probe:
    probe_id: str
    domain: str
    legacy_class: str
    legacy_source: str
    objects: tuple[str, ...]
    status: str
    current_sql: str
    legacy_sql: str | None = None
    dated: bool = False
    note: str = ""
    cursor: str = "NEEDS_RESEARCH"


PROBES = (
    Probe(
        "PRODUCTS",
        "PRODUCTS",
        "ACTIVE_LEGACY",
        "makeProduct + makeProductPropiety",
        ("OITM", "OITB", "OMRC", "OITG"),
        "PASS",
        '''SELECT TOP 5 I."ItemCode", I."ItemName", I."U_CODACTIVE",
                  I."LastPurPrc", I."LastPurCur", I."LastPurDat", I."OnHand",
                  I."ItmsGrpCod", G."ItmsGrpNam", I."InvntryUom", I."FirmCode",
                  M."FirmName", I."frozenFor", I."U_FormaFarmac", I."U_SUBGRUPO",
                  I."CreateDate", I."UpdateDate", I."UpdateTS"
             FROM "TELCHI"."OITM" I
             LEFT JOIN "TELCHI"."OITB" G ON G."ItmsGrpCod" = I."ItmsGrpCod"
             LEFT JOIN "TELCHI"."OMRC" M ON M."FirmCode" = I."FirmCode"''',
        '''SELECT TOP 5 OITM."ItemCode", OITM."ItemName", OITM."U_CODACTIVE",
                  OITM."LastPurPrc", OITM."LastPurCur", OITM."LastPurDat",
                  OITM."OnHand", OITM."ItmsGrpCod",
                  (SELECT OITB."ItmsGrpNam" FROM TELCHI.OITB OITB
                    WHERE OITB."ItmsGrpCod" = OITM."ItmsGrpCod"),
                  OITM."InvntryUom", OITM."FirmCode",
                  (SELECT OMRC."FirmName" FROM TELCHI.OMRC OMRC
                    WHERE OMRC."FirmCode" = OITM."FirmCode"),
                  OITM."frozenFor", OITM."U_FormaFarmac", OITM."U_SUBGRUPO"
             FROM TELCHI.OITM OITM''',
        note="The 64 QryGroup flags remain available; set-based extraction replaces 64 round trips.",
        cursor="SAFE_INCREMENTAL_CURSOR: UpdateDate+UpdateTS+ItemCode",
    ),
    Probe(
        "CUSTOMERS",
        "CUSTOMERS",
        "DORMANT_LEGACY",
        "makeClient + makeClientPropiety",
        ("OCRD", "OCQG"),
        "CHANGE_REQUIRED",
        '''SELECT TOP 5 C."CardCode", C."CardName", C."CardType", C."GroupCode",
                  C."City", C."CreateDate", C."UpdateDate", C."UpdateTS"
             FROM "TELCHI"."OCRD" C WHERE C."CardType" = 'C' ''',
        '''SELECT TOP 5 OCRD."CardCode", OCRD."CardName", OCRD."CardType",
                  OCRD."GroupCode", OCRD."City" FROM telchi.OCRD OCRD''',
        note="Legacy output named every business partner a client; current customer scope is CardType='C'.",
        cursor="SAFE_INCREMENTAL_CURSOR: UpdateDate+UpdateTS+CardCode",
    ),
    Probe(
        "WAREHOUSE_MASTER",
        "WAREHOUSES",
        "DORMANT_LEGACY",
        "makeOWHS",
        ("OWHS",),
        "PASS",
        '''SELECT TOP 5 "WhsCode", "WhsName", "BalInvntAc", "SaleCostAc",
                  "TransferAc", "Locked", "RevenuesAc" FROM "TELCHI"."OWHS"''',
        '''SELECT TOP 5 OWHS."WhsCode", OWHS."WhsName", OWHS."BalInvntAc",
                  OWHS."SaleCostAc", OWHS."TransferAc", OWHS."Locked",
                  OWHS."RevenuesAc" FROM TELCHI.OWHS OWHS''',
        cursor="FULL_REFRESH",
    ),
    Probe(
        "ITEM_WAREHOUSE",
        "WAREHOUSES",
        "ACTIVE_LEGACY",
        "makeWhareHouse",
        ("OITW",),
        "PASS",
        '''SELECT TOP 5 "ItemCode", "WhsCode", "OnHand", "IsCommited", "OnOrder",
                  "MinStock", "MaxStock", "AvgPrice", "createDate", "updateDate",
                  "userSign2", "RevenuesAc", "StockValue", "WipAcct"
             FROM "TELCHI"."OITW"''',
        '''SELECT TOP 5 OITW."ItemCode", OITW."WhsCode", OITW."OnHand",
                  OITW."IsCommited", OITW."OnOrder", OITW."MinStock",
                  OITW."MaxStock", OITW."AvgPrice", OITW."createDate",
                  OITW."updateDate", OITW."userSign2", OITW."RevenuesAc",
                  OITW."StockValue", OITW."WipAcct" FROM TELCHI.OITW OITW''',
        cursor="FULL_REFRESH",
    ),
    Probe(
        "SALES",
        "SALES",
        "ACTIVE_LEGACY",
        "makeSaleDFRange",
        ("OINV", "INV1", "OSLP", "OUSR"),
        "CHANGE_REQUIRED",
        '''SELECT TOP 5 H."DocEntry", H."DocNum", H."CardCode", H."CardName",
                  H."DocDate", H."TaxDate", H."DocDueDate", H."DocCur",
                  H."DocTotal", H."SlpCode", S."SlpName", L."LineNum",
                  L."ItemCode", L."Dscription", L."Quantity", L."LineTotal",
                  L."GTotal", L."Currency", L."WhsCode", H."UpdateDate", H."UpdateTS"
             FROM "TELCHI"."OINV" H
             JOIN "TELCHI"."INV1" L ON L."DocEntry" = H."DocEntry"
             LEFT JOIN "TELCHI"."OSLP" S ON S."SlpCode" = H."SlpCode"
            WHERE H."CANCELED" = 'N' AND H."DocDate" >= ? AND H."DocDate" <= ?''',
        '''SELECT TOP 5 H."DocEntry", H."NumAtCard", H."Series", H."DocNum",
                  H."CardCode", H."CardName", H."DocTotal", H."DiscSum",
                  H."PaidSum", H."SlpCode",
                  (SELECT S."SlpName" FROM TELCHI.OSLP S
                    WHERE S."SlpCode" = H."SlpCode"), H."UpdateDate", H."UpdateTS",
                  H."DocDate", H."DocTime", H."DocStatus", H."U_ESTADOFC",
                  H."DocSubType", L."ItemCode", L."Dscription", L."GPBefDisc",
                  L."Quantity", L."GTotal", L."U_DESCLINEA", L."WhsCode", L."U_TYPE"
             FROM TELCHI.OINV H
             JOIN TELCHI.INV1 L ON H."DocEntry" = L."DocEntry"
            WHERE H."DocDate" >= ? AND H."DocDate" <= ?''',
        dated=True,
        note="Legacy included canceled originals and cancellation documents and allocated header total across lines.",
        cursor="COMPOSITE_CURSOR_REQUIRED: UpdateDate+UpdateTS+DocEntry+LineNum",
    ),
    Probe(
        "CREDIT_NOTES",
        "CREDIT_NOTES",
        "ACTIVE_LEGACY",
        "makeNCDFRange",
        ("ORIN", "RIN1", "OSLP"),
        "CHANGE_REQUIRED",
        '''SELECT TOP 5 H."DocEntry", H."DocNum", H."CardCode", H."DocDate",
                  H."TaxDate", H."DocCur", H."DocTotal" * -1 AS "DocTotal",
                  H."SlpCode", S."SlpName", L."LineNum", L."ItemCode",
                  L."Quantity" * -1 AS "Quantity", L."LineTotal" * -1 AS "LineTotal",
                  L."GTotal" * -1 AS "GTotal", L."WhsCode", L."BaseEntry",
                  H."UpdateDate", H."UpdateTS"
             FROM "TELCHI"."ORIN" H
             JOIN "TELCHI"."RIN1" L ON L."DocEntry" = H."DocEntry"
             LEFT JOIN "TELCHI"."OSLP" S ON S."SlpCode" = H."SlpCode"
            WHERE H."CANCELED" = 'N' AND H."DocDate" >= ? AND H."DocDate" <= ?''',
        '''SELECT TOP 5 H."DocEntry", H."NumAtCard", H."Series", H."DocNum",
                  H."CardCode", H."CardName", H."DocTotal" * -1, H."DiscSum",
                  H."PaidSum", H."SlpCode",
                  (SELECT S."SlpName" FROM TELCHI.OSLP S
                    WHERE S."SlpCode" = H."SlpCode"), H."UpdateDate", H."UpdateTS",
                  H."DocDate", H."DocTime", H."DocStatus", H."U_ESTADOFC",
                  L."ItemCode", L."Dscription", L."GPBefDisc", L."Quantity" * -1,
                  L."GTotal" * -1, L."U_DESCLINEA", L."WhsCode", L."U_TYPE",
                  L."BaseRef"
             FROM TELCHI.ORIN H JOIN TELCHI.RIN1 L ON H."DocEntry" = L."DocEntry"
            WHERE H."DocDate" >= ? AND H."DocDate" <= ?''',
        dated=True,
        note="Negative sign is valid, but canceled pairs must not be counted as ordinary credit notes.",
        cursor="COMPOSITE_CURSOR_REQUIRED: UpdateDate+UpdateTS+DocEntry+LineNum",
    ),
    Probe(
        "INVENTORY_MOVEMENTS",
        "INVENTORY_MOVEMENTS",
        "ACTIVE_LEGACY",
        "makeMoveProductRange",
        ("OINM",),
        "CHANGE_REQUIRED",
        '''SELECT TOP 5 "TransNum", "TransSeq", "TransType", "BASE_REF",
                  "DocLineNum", "DocDate", "TaxDate", "CreateDate", "ItemCode",
                  "Warehouse", "InQty", "OutQty", "TransValue", "CalcPrice",
                  "Price", "Currency" FROM "TELCHI"."OINM"
            WHERE "DocDate" >= ? AND "DocDate" <= ?''',
        '''SELECT TOP 5 OINM."TransNum", OINM."TransType", OINM."BASE_REF",
                  OINM."DocLineNum", OINM."Ref1", OINM."Ref2", OINM."Comments",
                  OINM."JrnlMemo", OINM."DocDate", OINM."DocDueDate",
                  OINM."DocTime", OINM."CardCode", OINM."CardName",
                  OINM."ItemCode", OINM."Dscription", OINM."InQty", OINM."OutQty",
                  OINM."TransValue", OINM."CalcPrice", OINM."Price" / 0.87,
                  OINM."Balance", OINM."SlpCode", OINM."Warehouse", OINM."UserSign"
             FROM TELCHI.OINM OINM WHERE OINM."DocDate" >= ? AND OINM."DocDate" <= ?''',
        dated=True,
        note="OINM is now a view; fixed Price/0.87 is not a valid sale/cost measure for every TransType.",
        cursor="SAFE_INCREMENTAL_CURSOR: TransNum+TransSeq",
    ),
    Probe(
        "RECONCILIATIONS",
        "RECONCILIATIONS",
        "DORMANT_LEGACY",
        "makeReconRange",
        ("OITR", "ITR1", "OUSR"),
        "PASS",
        '''SELECT TOP 5 H."ReconNum", H."ReconDate", H."ReconType", H."Total",
                  H."ReconCurr", H."Canceled", H."CreateDate", H."CreateTS",
                  H."UpdateTS", L."LineSeq", L."ShortName", L."TransId",
                  L."TransRowId", L."SrcObjTyp", L."SrcObjAbs", L."ReconSum",
                  L."IsCredit", L."Account" FROM "TELCHI"."OITR" H
             JOIN "TELCHI"."ITR1" L ON L."ReconNum" = H."ReconNum"
            WHERE H."ReconDate" >= ? AND H."ReconDate" <= ?''',
        '''SELECT TOP 5 H."ReconNum", H."IsCard", H."ReconType", H."ReconDate",
                  H."Total", H."ReconCurr", H."Canceled", H."CancelAbs",
                  H."IsSystem", H."InitObjTyp", H."CreateDate", H."CreateTime",
                  H."UserSign", (SELECT U."USER_CODE" FROM TELCHI.OUSR U
                    WHERE U."USERID" = H."UserSign"), H."IsMultiBP", H."IsElectr",
                  H."CreateTS", H."UpdateTS", H."ObjType", L."ReconNum",
                  L."LineSeq", L."ShortName", L."TransId", L."TransRowId",
                  L."SrcObjTyp", L."SrcObjAbs", L."ReconSum", L."ReconSumFC",
                  L."ReconSumSC", L."SumMthCurr", L."IsCredit", L."Account",
                  L."CashDisSum", L."InstID"
             FROM TELCHI.OITR H JOIN TELCHI.ITR1 L ON L."ReconNum" = H."ReconNum"
            WHERE H."ReconDate" >= ? AND H."ReconDate" <= ?''',
        dated=True,
        cursor="COMPOSITE_CURSOR_REQUIRED: ReconNum+LineSeq",
    ),
    Probe(
        "INCOMING_PAYMENTS",
        "PAYMENTS",
        "DORMANT_LEGACY",
        "makePaymentRange",
        ("ORCT",),
        "PASS",
        '''SELECT TOP 5 "DocEntry", "DocNum", "TransId", "Canceled", "DocDate",
                  "TaxDate", "CardCode", "CardName", "DocCurr", "DocTotal",
                  "CashSum", "TrsfrSum", "CreditSum", "CheckSum", "UpdateDate",
                  "UpdateTS" FROM "TELCHI"."ORCT"
            WHERE "DocDate" >= ? AND "DocDate" <= ?''',
        '''SELECT TOP 5 "TransId", "CashSum", "TrsfrSum", "CreditSum", "CheckSum",
                  "DocTotal", "DocTotalFC", "DocEntry", "DocNum", "DocType",
                  "Canceled", "DocDate", "DocTime", "DocDueDate", "TaxDate",
                  "CardCode", "CardName", "Ref1", "Comments", "JrnlMemo"
             FROM TELCHI.ORCT WHERE "DocDate" >= ? AND "DocDate" <= ?''',
        dated=True,
        cursor="COMPOSITE_CURSOR_REQUIRED: UpdateDate+UpdateTS+DocEntry",
    ),
    Probe(
        "ITEM_GROUPS",
        "PRODUCTS",
        "DORMANT_LEGACY",
        "makeOITB",
        ("OITB",),
        "PASS",
        '''SELECT TOP 5 "ItmsGrpCod", "ItmsGrpNam", "Locked", "DataSource",
                  "UserSign", "BalInvntAc", "SaleCostAc", "TransferAc",
                  "RevenuesAc", "userSign2", "createDate", "updateDate"
             FROM "TELCHI"."OITB"''',
        '''SELECT TOP 5 "ItmsGrpCod", "ItmsGrpNam", "Locked", "DataSource",
                  "UserSign", "BalInvntAc", "SaleCostAc", "TransferAc",
                  "RevenuesAc", "userSign2", "createDate", "updateDate"
             FROM TELCHI.OITB''',
        cursor="FULL_REFRESH",
    ),
    Probe(
        "CHART_OF_ACCOUNTS",
        "ACCOUNTS",
        "DORMANT_LEGACY",
        "makeOACT",
        ("OACT",),
        "PASS",
        '''SELECT TOP 5 "AcctCode", "AcctName", "CurrTotal", "EndTotal",
                  "Finanse", "Groups", "Budget", "Frozen", "Postable",
                  "FatherNum", "CreateDate", "UpdateDate" FROM "TELCHI"."OACT"''',
        '''SELECT TOP 5 "AcctCode", "AcctName", "CurrTotal", "EndTotal", "Finanse",
                  "Groups", "Budget", "Frozen", "Postable", "Fixed", "Levels",
                  "PlngLevel", "ExportCode", "GrpLine", "FatherNum", "AccntntCod",
                  "CashBox", "RateTrans" FROM TELCHI.OACT''',
        cursor="SAFE_INCREMENTAL_CURSOR: UpdateDate+AcctCode",
    ),
    Probe(
        "BOM",
        "BOM_RECIPES",
        "MIGRATION_ONLY",
        "makeRecetasSap",
        ("OITT", "ITT1"),
        "DEPRECATED",
        '''SELECT TOP 5 H."Code", H."TreeType", H."Qauntity", H."CreateDate",
                  H."UpdateDate", L."ChildNum", L."Code" AS "ComponentCode",
                  L."Quantity" AS "ComponentQuantity", L."Warehouse"
             FROM "TELCHI"."OITT" H JOIN "TELCHI"."ITT1" L ON L."Father" = H."Code"''',
        note="Legacy routine created SAP-import CSV from old Arango/Excel data; it was not a HANA extractor.",
        cursor="COMPOSITE_CURSOR_REQUIRED: UpdateDate+UpdateTS+Code+ChildNum",
    ),
    Probe(
        "PURCHASES",
        "PURCHASES",
        "ACTIVE_LEGACY",
        "makePurchaseDFRange (pre-SAP SQL Server)",
        ("OPOR", "POR1", "OCRD", "OITM", "OWHS"),
        "CHANGE_REQUIRED",
        '''SELECT TOP 5 H."DocEntry", H."DocNum", H."DocStatus", H."DocDate",
                  H."DocDueDate", H."TaxDate", H."CardCode", H."CardName",
                  H."DocCur", H."DocRate", H."SlpCode", L."LineNum", L."ItemCode",
                  L."Dscription", L."Quantity", L."Price", L."LineTotal",
                  L."Currency", L."WhsCode", H."UpdateDate", H."UpdateTS"
             FROM "TELCHI"."OPOR" H JOIN "TELCHI"."POR1" L
               ON L."DocEntry" = H."DocEntry"
            WHERE H."CANCELED" = 'N' AND H."DocDate" >= ? AND H."DocDate" <= ?''',
        dated=True,
        note="Legacy purchase orders came from cohor/codor; SAP OPOR/POR1 is the structural successor.",
        cursor="COMPOSITE_CURSOR_REQUIRED: UpdateDate+UpdateTS+DocEntry+LineNum",
    ),
    Probe(
        "PURCHASE_EXPENSES",
        "PURCHASES_COSTS",
        "ACTIVE_LEGACY",
        "makePurchaseExpenseDFRange (pre-SAP SQL Server)",
        ("OIPF", "IPF1", "IPF2"),
        "CHANGE_REQUIRED",
        '''SELECT TOP 5 H."DocEntry", H."DocNum", H."DocDate", H."TaxDate",
                  H."DocCur", H."DocRate", H."DocTotal", H."CostSum",
                  H."UpdateDate", L."LineNum", L."BaseType", L."BaseEntry",
                  L."ItemCode", L."Quantity", L."PriceFOB", L."Cost",
                  L."PriceAtWH", L."LineTotal", L."WhsCode"
             FROM "TELCHI"."OIPF" H JOIN "TELCHI"."IPF1" L
               ON L."DocEntry" = H."DocEntry"
            WHERE H."Canceled" = 'N' AND H."DocDate" >= ? AND H."DocDate" <= ?''',
        dated=True,
        note="Landed costs are present, but old free-form expense categories need an explicit business mapping.",
        cursor="COMPOSITE_CURSOR_REQUIRED: UpdateDate+DocEntry+LineNum",
    ),
    Probe(
        "SALES_TARGETS",
        "SALES_TARGETS",
        "UNKNOWN_LEGACY",
        "No extractor found in repository history",
        ("@OBJ_VENTAS_C", "@OBJ_VENTAS_L"),
        "BLOCKED",
        '''SELECT TOP 5 H."Code", H."U_SUPERVISOR", H."U_SUPERVISOR_N",
                  H."UpdateDate", L."LineId", L."U_VENDEDOR", L."U_VENDEDOR_N",
                  L."U_ENERO", L."U_FEBRERO", L."U_MARZO", L."U_ABRIL",
                  L."U_MAYO", L."U_JUNIO", L."U_JULIO", L."U_AGOSTO",
                  L."U_SEPTIEMBRE", L."U_OCTUBRE", L."U_NOVIEMBRE", L."U_DICIEMBRE"
             FROM "TELCHI"."@OBJ_VENTAS_C" H LEFT JOIN "TELCHI"."@OBJ_VENTAS_L" L
               ON L."Code" = H."Code"''',
        note="Header has records but line table is empty; no legacy reader explains target semantics.",
        cursor="NEEDS_RESEARCH",
    ),
)


def validate_read_only_sql(sql: str) -> None:
    normalized = sql.lstrip()
    if not normalized.upper().startswith(("SELECT", "WITH")):
        raise ValueError("AUDIT_SQL_MUST_START_WITH_SELECT_OR_WITH")
    if WRITE_TOKEN.search(sql):
        raise ValueError("AUDIT_SQL_CONTAINS_WRITE_TOKEN")
    if ";" in sql:
        raise ValueError("AUDIT_SQL_MUST_BE_SINGLE_STATEMENT")


def catalog_names(cursor: Any, names: tuple[str, ...]) -> set[str]:
    placeholders = ",".join("?" for _ in names)
    cursor.execute(
        "SELECT TABLE_NAME FROM SYS.TABLES WHERE SCHEMA_NAME = ? "
        f"AND TABLE_NAME IN ({placeholders})",
        (HANA_SCHEMA, *names),
    )
    found = {str(row[0]) for row in cursor.fetchall()}
    cursor.execute(
        "SELECT VIEW_NAME FROM SYS.VIEWS WHERE SCHEMA_NAME = ? "
        f"AND VIEW_NAME IN ({placeholders})",
        (HANA_SCHEMA, *names),
    )
    found.update(str(row[0]) for row in cursor.fetchall())
    return found


def execute_bounded(cursor: Any, sql: str, dated: bool) -> tuple[int, int]:
    validate_read_only_sql(sql)
    parameters = (SAMPLE_FROM, SAMPLE_TO) if dated else ()
    cursor.execute(sql, parameters)
    rows = cursor.fetchall()
    return len(rows), len(cursor.description or ())


def run_audit() -> None:
    tcp_preflight()
    config = load_private_config(PRIVATE_ENV_FILE)
    password = config.pop("TELCHI_SAP_HANA_PASSWORD")
    connection = None
    cursor = None
    failures: list[str] = []
    try:
        from hdbcli import dbapi

        connection = dbapi.connect(
            address=HANA_HOST,
            port=HANA_PORT,
            user=HANA_USER,
            password=password,
        )
        password = ""
        config.clear()
        connection.setautocommit(False)
        cursor = connection.cursor()
        print(f"HANA AUDIT TARGET          {HANA_HOST}:{HANA_PORT}/{HANA_SCHEMA}")
        print(f"HANA AUDIT WINDOW          {SAMPLE_FROM}..{SAMPLE_TO}")

        for probe in PROBES:
            if probe.status not in ALLOWED_STATUSES:
                failures.append(f"{probe.probe_id}:INVALID_STATUS")
                continue
            present = catalog_names(cursor, probe.objects)
            missing = tuple(name for name in probe.objects if name not in present)
            if missing:
                failures.append(f"{probe.probe_id}:MISSING_OBJECTS={','.join(missing)}")
                print(f"{probe.probe_id:<28} FAIL missing_objects={','.join(missing)}")
                continue
            try:
                legacy_result = "N/A"
                if probe.legacy_sql:
                    rows, columns = execute_bounded(
                        cursor, probe.legacy_sql, probe.dated
                    )
                    legacy_result = f"PASS({rows}x{columns})"
                rows, columns = execute_bounded(cursor, probe.current_sql, probe.dated)
                print(
                    f"{probe.probe_id:<28} PASS legacy={legacy_result} "
                    f"current=PASS({rows}x{columns}) semantic={probe.status}"
                )
            except Exception as exc:
                code = f"{probe.probe_id}:{type(exc).__name__.upper()}"
                failures.append(code)
                print(f"{probe.probe_id:<28} FAIL {code}")
        if failures:
            raise SmokeBlocked(";".join(failures))
    finally:
        password = ""
        config.clear()
        if cursor is not None:
            cursor.close()
        if connection is not None:
            try:
                connection.rollback()
            finally:
                connection.close()


def main() -> int:
    try:
        run_audit()
    except SmokeBlocked as exc:
        print("TEAM360_TELCHI_SAP_HISTORICAL_SYNC_PROBES_BLOCKED")
        print(f"BLOCKER: {exc}")
        return 2
    print("TEAM360_TELCHI_SAP_HISTORICAL_SYNC_PROBES_PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
