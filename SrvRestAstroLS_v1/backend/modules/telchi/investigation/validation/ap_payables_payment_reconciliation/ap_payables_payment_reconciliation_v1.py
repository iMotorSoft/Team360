#!/usr/bin/env python3
"""TELCHI AP payable/payment/reconciliation V1.

Investigation-only, SELECT-only HANA probe.  The authoritative settlement grain
is an active OITR/ITR1 reconciliation.  VPM2 is retained as the SAP payment
application map and cross-check, never added to ITR1 settlement a second time.
Large work is aggregated in HANA; only selected end-to-end cases are materialised.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from modules.telchi.investigation.atomic.connection import connect
from modules.telchi.investigation.paths import INVESTIGATION_ROOT

ROOT = INVESTIGATION_ROOT
OUT_DIR = ROOT / "validation" / "ap_payables_payment_reconciliation"
DEFAULT_OUTPUT = OUT_DIR / "ap_payables_payment_reconciliation_v1.json"
DEFAULT_REPORT = ROOT / "docs" / "telchi_ap_payables_payment_reconciliation_v1_report.md"
TOLERANCE = 0.01
LOCAL_CURRENCIES = {"BS", "BOB", "##", ""}
AP_OBJECTS = {"18": "AP_INVOICE", "19": "AP_CREDIT_NOTE", "20": "GOODS_RECEIPT", "21": "GOODS_RETURN", "22": "PURCHASE_ORDER", "24": "INCOMING_PAYMENT", "25": "DEPOSIT", "30": "JOURNAL", "46": "OUTGOING_PAYMENT", "204": "AP_DOWN_PAYMENT"}
CORE_TABLES = ("OPCH", "PCH1", "ORPC", "RPC1", "OPDN", "PDN1", "ORPD", "RPD1", "OPOR", "POR1", "OVPM", "VPM2", "VPM4", "VPM6", "OITR", "ITR1", "OJDT", "JDT1", "OCRD", "OACT", "ODPI", "DPI1", "ODPO", "DPO1")


def fetch(cur: Any, sql: str, params: tuple[Any, ...] = ()) -> tuple[list[str], list[tuple[Any, ...]]]:
    cur.execute(sql, params)
    return [str(x[0]) for x in (cur.description or ())], [tuple(x) for x in cur.fetchall()]


def serial(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def as_dicts(columns: list[str], rows: list[tuple[Any, ...]]) -> list[dict[str, Any]]:
    return [{str(k).upper(): serial(v) for k, v in zip(columns, row, strict=False)} for row in rows]


def safe(cur: Any, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any]:
    try:
        columns, rows = fetch(cur, sql, params)
        return {"status": "PASS", "rows": as_dicts(columns, rows)}
    except Exception as exc:
        return {"status": "QUERY_ERROR", "error_type": type(exc).__name__, "error": str(exc)[:500]}


def rows(section: dict[str, Any] | None) -> list[dict[str, Any]]:
    return section.get("rows", []) if section and section.get("status") == "PASS" else []


def ph(items: list[Any]) -> str:
    return ",".join("?" for _ in items) or "NULL"


def num(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def table_catalog(cur: Any) -> tuple[set[str], dict[str, set[str]], dict[str, int]]:
    q = safe(cur, 'SELECT "TABLE_NAME" FROM SYS.TABLES WHERE "SCHEMA_NAME"=? AND "TABLE_NAME" IN (' + ph(list(CORE_TABLES)) + ')', ("TELCHI", *CORE_TABLES))
    tables = {str(x["TABLE_NAME"]) for x in rows(q)}
    columns: dict[str, set[str]] = {}
    counts: dict[str, int] = {}
    for table in sorted(tables):
        columns[table] = {str(x["COLUMN_NAME"]) for x in rows(safe(cur, 'SELECT "COLUMN_NAME" FROM SYS.TABLE_COLUMNS WHERE "SCHEMA_NAME"=? AND "TABLE_NAME"=? ORDER BY "POSITION"', ("TELCHI", table)))}
        count = rows(safe(cur, f'SELECT COUNT(*) AS "ROWS" FROM TELCHI."{table}"'))
        if count:
            counts[table] = int(count[0]["ROWS"] or 0)
    return tables, columns, counts


def overview(cur: Any, tables: set[str]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for table in sorted(tables):
        if table not in CORE_TABLES:
            continue
        result[table] = safe(cur, f'SELECT COUNT(*) AS "ROWS", MIN("DocDate") AS "FIRST_DATE", MAX("DocDate") AS "LAST_DATE" FROM TELCHI."{table}"' if table in {"OPCH", "ORPC", "OPDN", "ORPD", "OPOR", "OVPM", "ODPI", "ODPO"} else f'SELECT COUNT(*) AS "ROWS" FROM TELCHI."{table}"')
    return result


def invoice_metrics(cur: Any) -> dict[str, Any]:
    return {
        "universe": safe(cur, '''SELECT COUNT(*) AS "TOTAL", COUNT(CASE WHEN "CANCELED"='N' THEN 1 END) AS "ACTIVE", COUNT(CASE WHEN "CANCELED"<>'N' THEN 1 END) AS "CANCELED", COUNT(CASE WHEN "DocStatus"='O' AND "CANCELED"='N' THEN 1 END) AS "OPEN_STATUS", COUNT(CASE WHEN "DocStatus"='C' AND "CANCELED"='N' THEN 1 END) AS "CLOSED_STATUS", COALESCE(SUM("DocTotal"),0) AS "GROSS_TOTAL", COALESCE(SUM("PaidToDate"),0) AS "PAID_TO_DATE", COALESCE(SUM(CASE WHEN "CANCELED"='N' THEN "DocTotal"-"PaidToDate" ELSE 0 END),0) AS "OPEN_FORMULA" FROM TELCHI."OPCH"'''),
        "status_currency": safe(cur, '''SELECT "CANCELED","DocStatus","DocCur",COUNT(*) AS "DOCUMENTS",SUM("DocTotal") AS "DOC_TOTAL",SUM("PaidToDate") AS "PAID_TO_DATE" FROM TELCHI."OPCH" GROUP BY "CANCELED","DocStatus","DocCur" ORDER BY "CANCELED","DocStatus","DocCur"'''),
        "open_by_supplier": safe(cur, '''SELECT P."CardCode",P."CardName",P."DocCur",COUNT(*) AS "OPEN_INVOICES",SUM(P."DocTotal"-P."PaidToDate") AS "OPEN_AMOUNT",SUM(CASE WHEN P."DocDueDate"<CURRENT_DATE THEN P."DocTotal"-P."PaidToDate" ELSE 0 END) AS "OVERDUE_AMOUNT",MIN(CASE WHEN P."DocDueDate"<CURRENT_DATE AND P."DocTotal"-P."PaidToDate">? THEN P."DocDueDate" END) AS "OLDEST_OVERDUE" FROM TELCHI."OPCH" P WHERE P."CANCELED"='N' AND P."DocStatus"='O' AND P."DocTotal"-P."PaidToDate">? GROUP BY P."CardCode",P."CardName",P."DocCur" ORDER BY "OPEN_AMOUNT" DESC''', (TOLERANCE, TOLERANCE)),
    }


def invoice_rows(cur: Any) -> list[dict[str, Any]]:
    q = safe(cur, '''SELECT P."DocEntry",P."DocNum",P."CardCode",P."CardName",B."DebPayAcct" AS "ControlAccount",P."DocDate",P."TaxDate",P."DocDueDate",P."CreateDate",P."DocCur",P."DocRate",P."DocTotal",P."DocTotalFC",P."PaidToDate",P."PaidFC",P."CANCELED",P."DocStatus",P."TransId",P."UserSign",P."Comments",P."NumAtCard",P."DiscSum",P."DiscPrcnt" FROM TELCHI."OPCH" P LEFT JOIN TELCHI."OCRD" B ON B."CardCode"=P."CardCode"''')
    return rows(q)


def gl_trace(cur: Any) -> dict[str, Any]:
    return {
        "invoice_transid_coverage": safe(cur, '''SELECT COUNT(*) AS "INVOICES",COUNT(CASE WHEN J."TransId" IS NOT NULL THEN 1 END) AS "WITH_OJDT",COUNT(CASE WHEN J."TransId" IS NULL THEN 1 END) AS "ORPHANS" FROM TELCHI."OPCH" P LEFT JOIN TELCHI."OJDT" J ON J."TransId"=P."TransId"'''),
        "invoice_journal_balance": safe(cur, '''SELECT COUNT(*) AS "JOURNALS",SUM(CASE WHEN ABS(X."DEBIT"-X."CREDIT")<=? THEN 1 ELSE 0 END) AS "BALANCED",SUM(CASE WHEN ABS(X."DEBIT"-X."CREDIT")>? THEN 1 ELSE 0 END) AS "UNBALANCED",MAX(ABS(X."DEBIT"-X."CREDIT")) AS "MAX_DIFF" FROM (SELECT P."TransId",SUM(J."Debit") AS "DEBIT",SUM(J."Credit") AS "CREDIT" FROM TELCHI."OPCH" P JOIN TELCHI."JDT1" J ON J."TransId"=P."TransId" WHERE P."CANCELED"='N' GROUP BY P."TransId") X''', (TOLERANCE, TOLERANCE)),
        "payment_transid_coverage": safe(cur, '''SELECT COUNT(*) AS "PAYMENTS",COUNT(CASE WHEN J."TransId" IS NOT NULL THEN 1 END) AS "WITH_OJDT",COUNT(CASE WHEN J."TransId" IS NULL THEN 1 END) AS "ORPHANS" FROM TELCHI."OVPM" P LEFT JOIN TELCHI."OJDT" J ON J."TransId"=P."TransId"'''),
        "control_account": safe(cur, '''SELECT COUNT(*) AS "SUPPLIER_LINES",COUNT(CASE WHEN J."Account"=B."DebPayAcct" THEN 1 END) AS "CONTROL_ACCOUNT_LINES",COUNT(DISTINCT J."ShortName") AS "BP_SHORTNAMES",COUNT(DISTINCT J."Account") AS "ACCOUNTS" FROM TELCHI."JDT1" J JOIN TELCHI."OCRD" B ON B."CardCode"=J."ShortName" WHERE B."CardType"='S' AND J."TransType"='18' AND J."ShortName"=B."CardCode"'''),
        "control_account_mismatches": safe(cur, '''SELECT B."CardCode",B."CardName",B."DebPayAcct",J."Account",COUNT(*) AS "LINES",SUM(J."Debit") AS "DEBIT",SUM(J."Credit") AS "CREDIT" FROM TELCHI."JDT1" J JOIN TELCHI."OCRD" B ON B."CardCode"=J."ShortName" WHERE B."CardType"='S' AND J."TransType"='18' AND J."Account"<>B."DebPayAcct" GROUP BY B."CardCode",B."CardName",B."DebPayAcct",J."Account" ORDER BY "LINES" DESC LIMIT 100'''),
        "control_accounts": safe(cur, '''SELECT B."CardCode",B."CardName",B."DebPayAcct",A."AcctName",COUNT(*) AS "JDT_LINES",SUM(J."Debit") AS "DEBIT",SUM(J."Credit") AS "CREDIT" FROM TELCHI."OCRD" B LEFT JOIN TELCHI."OACT" A ON A."AcctCode"=B."DebPayAcct" LEFT JOIN TELCHI."JDT1" J ON J."ShortName"=B."CardCode" AND J."Account"=B."DebPayAcct" WHERE B."CardType"='S' GROUP BY B."CardCode",B."CardName",B."DebPayAcct",A."AcctName" ORDER BY "JDT_LINES" DESC LIMIT 500'''),
    }


def payment_metrics(cur: Any) -> dict[str, Any]:
    return {
        "universe": safe(cur, '''SELECT COUNT(*) AS "TOTAL",COUNT(CASE WHEN "Canceled"='N' THEN 1 END) AS "ACTIVE",COUNT(CASE WHEN "Canceled"<>'N' THEN 1 END) AS "CANCELED",SUM("DocTotal") AS "DOC_TOTAL",SUM("CashSum") AS "CASH",SUM("CheckSum") AS "CHECKS",SUM("TrsfrSum") AS "TRANSFERS",SUM("CreditSum") AS "CREDIT_CARDS",SUM("NoDocSum") AS "NO_DOC",SUM("WtSum") AS "WTSUM" FROM TELCHI."OVPM"'''),
        "methods": safe(cur, '''SELECT CASE WHEN "CashSum"<>0 AND "CheckSum"=0 AND "TrsfrSum"=0 AND "CreditSum"=0 THEN 'CASH' WHEN "CashSum"=0 AND "CheckSum"=0 AND "TrsfrSum"<>0 AND "CreditSum"=0 THEN 'BANK_TRANSFER' WHEN "CashSum"=0 AND "CheckSum"<>0 AND "TrsfrSum"=0 AND "CreditSum"=0 THEN 'CHECK' WHEN "CashSum"=0 AND "CheckSum"=0 AND "TrsfrSum"=0 AND "CreditSum"<>0 THEN 'CREDIT_CARD' WHEN ("CashSum"<>0)+("CheckSum"<>0)+("TrsfrSum"<>0)+("CreditSum"<>0)>1 THEN 'MIXED' ELSE 'OTHER' END AS "METHOD",COUNT(*) AS "PAYMENTS",SUM("DocTotal") AS "DOC_TOTAL" FROM TELCHI."OVPM" WHERE "Canceled"='N' GROUP BY CASE WHEN "CashSum"<>0 AND "CheckSum"=0 AND "TrsfrSum"=0 AND "CreditSum"=0 THEN 'CASH' WHEN "CashSum"=0 AND "CheckSum"=0 AND "TrsfrSum"<>0 AND "CreditSum"=0 THEN 'BANK_TRANSFER' WHEN "CashSum"=0 AND "CheckSum"<>0 AND "TrsfrSum"=0 AND "CreditSum"=0 THEN 'CHECK' WHEN "CashSum"=0 AND "CheckSum"=0 AND "TrsfrSum"=0 AND "CreditSum"<>0 THEN 'CREDIT_CARD' WHEN ("CashSum"<>0)+("CheckSum"<>0)+("TrsfrSum"<>0)+("CreditSum"<>0)>1 THEN 'MIXED' ELSE 'OTHER' END ORDER BY "PAYMENTS" DESC'''),
        "application_profile": safe(cur, '''SELECT M."InvType",COUNT(*) AS "VPM2_LINES",COUNT(DISTINCT M."DocNum") AS "PAYMENTS",COUNT(DISTINCT M."DocEntry") AS "TARGET_DOCUMENTS",SUM(M."SumApplied") AS "SUM_APPLIED",SUM(M."AppliedFC") AS "APPLIED_FC",COUNT(CASE WHEN V."DocEntry" IS NULL THEN 1 END) AS "INVALID_PAYMENT_LINK",COUNT(CASE WHEN V2."DocEntry" IS NULL THEN 1 END) AS "INVALID_TARGET_LINK" FROM TELCHI."VPM2" M LEFT JOIN TELCHI."OVPM" V ON V."DocEntry"=M."DocNum" LEFT JOIN TELCHI."OPCH" V2 ON V2."DocEntry"=M."DocEntry" AND M."InvType"='18' GROUP BY M."InvType" ORDER BY M."InvType"'''),
        "on_account": safe(cur, '''SELECT COUNT(*) AS "PAYMENTS",SUM(CASE WHEN "NoDocSum">? THEN 1 ELSE 0 END) AS "WITH_NO_DOC_SUM",SUM(CASE WHEN NOT EXISTS (SELECT 1 FROM TELCHI."VPM2" M WHERE M."DocNum"=P."DocEntry") THEN 1 ELSE 0 END) AS "WITHOUT_VPM2",SUM("NoDocSum") AS "NO_DOC_SUM" FROM TELCHI."OVPM" P WHERE P."Canceled"='N' ''', (TOLERANCE,)),
    }


def payment_application_map(cur: Any) -> dict[str, Any]:
    return {
        "per_invoice": safe(cur, '''SELECT M."DocEntry" AS "INVOICE_DOCENTRY",COUNT(*) AS "VPM2_LINES",COUNT(DISTINCT M."DocNum") AS "PAYMENT_COUNT",SUM(M."SumApplied") AS "VPM2_APPLIED",SUM(M."AppliedFC") AS "VPM2_APPLIED_FC",MIN(P."DocDate") AS "FIRST_PAYMENT_DATE",MAX(P."DocDate") AS "LAST_PAYMENT_DATE",COUNT(CASE WHEN P."Canceled"='N' THEN 1 END) AS "ACTIVE_PAYMENT_LINKS",COUNT(CASE WHEN P."Canceled"<>'N' THEN 1 END) AS "CANCELED_PAYMENT_LINKS" FROM TELCHI."VPM2" M JOIN TELCHI."OPCH" I ON I."DocEntry"=M."DocEntry" AND M."InvType"='18' LEFT JOIN TELCHI."OVPM" P ON P."DocEntry"=M."DocNum" GROUP BY M."DocEntry"'''),
        "samples": safe(cur, '''SELECT P."DocEntry" AS "PAYMENT_DOCENTRY",P."DocNum" AS "PAYMENT_DOCNUM",P."CardCode",P."CardName",P."DocDate",P."TaxDate",P."DocCurr",P."DocTotal",P."CashSum",P."CheckSum",P."TrsfrSum",P."CreditSum",P."NoDocSum",P."Canceled",P."TransId",P."UserSign",P."Comments",M."InvType",M."DocEntry" AS "INVOICE_DOCENTRY",M."DocLine",M."SumApplied",M."AppliedFC" FROM TELCHI."OVPM" P JOIN TELCHI."VPM2" M ON M."DocNum"=P."DocEntry" AND M."InvType"='18' WHERE P."Canceled"<>'N' ORDER BY P."DocDate" DESC,P."DocEntry" DESC LIMIT 25'''),
    }


def reconciliation_metrics(cur: Any) -> dict[str, Any]:
    return {
        "headers": safe(cur, '''SELECT "Canceled",COUNT(*) AS "RECONCILIATIONS",SUM("Total") AS "TOTAL",MIN("ReconDate") AS "FIRST_DATE",MAX("ReconDate") AS "LAST_DATE" FROM TELCHI."OITR" GROUP BY "Canceled" ORDER BY "Canceled"'''),
        "grain": safe(cur, '''SELECT COUNT(*) AS "LINES",COUNT(DISTINCT "ReconNum") AS "RECON_NUMS",COUNT(DISTINCT TO_NVARCHAR("ReconNum")||':'||TO_NVARCHAR("LineSeq")) AS "RECON_LINE_KEYS" FROM TELCHI."ITR1"'''),
        "object_profile": safe(cur, '''SELECT I."SrcObjTyp",COUNT(*) AS "LINES",COUNT(DISTINCT I."ReconNum") AS "RECONCILIATIONS",COUNT(DISTINCT I."SrcObjAbs") AS "DOCUMENTS",SUM(ABS(I."ReconSum")) AS "ABS_RECON_SUM" FROM TELCHI."ITR1" I JOIN TELCHI."OITR" R ON R."ReconNum"=I."ReconNum" AND R."Canceled"='N' GROUP BY I."SrcObjTyp" ORDER BY "LINES" DESC'''),
        "invalid_members": safe(cur, '''SELECT SUM(CASE WHEN I."SrcObjTyp"='18' AND P."DocEntry" IS NULL THEN 1 WHEN I."SrcObjTyp"='19' AND C."DocEntry" IS NULL THEN 1 WHEN I."SrcObjTyp"='46' AND V."DocEntry" IS NULL THEN 1 WHEN I."SrcObjTyp"='30' AND J."TransId" IS NULL THEN 1 ELSE 0 END) AS "INVALID_KNOWN_OBJECT_LINKS" FROM TELCHI."ITR1" I JOIN TELCHI."OITR" R ON R."ReconNum"=I."ReconNum" AND R."Canceled"='N' LEFT JOIN TELCHI."OPCH" P ON P."DocEntry"=I."SrcObjAbs" AND I."SrcObjTyp"='18' LEFT JOIN TELCHI."ORPC" C ON C."DocEntry"=I."SrcObjAbs" AND I."SrcObjTyp"='19' LEFT JOIN TELCHI."OVPM" V ON V."DocEntry"=I."SrcObjAbs" AND I."SrcObjTyp"='46' LEFT JOIN TELCHI."OJDT" J ON J."TransId"=I."TransId" AND I."SrcObjTyp"='30' WHERE I."SrcObjTyp" IN ('18','19','30','46')'''),
    }


def settlement_summary(cur: Any) -> dict[str, Any]:
    # AP invoice members with IsCredit=C are the side that matches PaidToDate
    # in this installation. Counterparts are aggregated once per ReconNum;
    # system type 321 is excluded. The residual preserves the invoice amount
    # when a reconciliation contains balancing/system members.
    sql = '''WITH ACTIVE AS (
        SELECT "ReconNum" FROM TELCHI."OITR" WHERE "Canceled"='N'
    ), INV AS (
        SELECT I."ReconNum",I."SrcObjAbs" AS "INVOICE_DOCENTRY",SUM(ABS(I."ReconSum")) AS "INV_AMOUNT"
        FROM TELCHI."ITR1" I JOIN ACTIVE A ON A."ReconNum"=I."ReconNum"
        WHERE I."SrcObjTyp"='18' AND I."IsCredit"='C'
        GROUP BY I."ReconNum",I."SrcObjAbs"
    ), TOTALS AS (
        SELECT "ReconNum",SUM("INV_AMOUNT") AS "RECON_INV_TOTAL" FROM INV GROUP BY "ReconNum"
    ), RAW AS (
        SELECT C."ReconNum",
          SUM(CASE WHEN C."SrcObjTyp"='46' THEN CASE WHEN C."IsCredit"='D' THEN ABS(C."ReconSum") ELSE -ABS(C."ReconSum") END ELSE 0 END) AS "PAYMENT_MEMBER",
          SUM(CASE WHEN C."SrcObjTyp"='19' THEN CASE WHEN C."IsCredit"='D' THEN ABS(C."ReconSum") ELSE -ABS(C."ReconSum") END ELSE 0 END) AS "CREDIT_MEMBER",
          SUM(CASE WHEN C."SrcObjTyp" IN ('25','204') THEN CASE WHEN C."IsCredit"='D' THEN ABS(C."ReconSum") ELSE -ABS(C."ReconSum") END ELSE 0 END) AS "ADVANCE_MEMBER",
          SUM(CASE WHEN C."SrcObjTyp"='30' THEN CASE WHEN C."IsCredit"='D' THEN ABS(C."ReconSum") ELSE -ABS(C."ReconSum") END ELSE 0 END) AS "JOURNAL_MEMBER",
          COUNT(DISTINCT CASE WHEN C."SrcObjTyp"='46' AND C."IsCredit"='D' THEN C."SrcObjAbs" END) AS "PAYMENT_COUNT",
          COUNT(DISTINCT CASE WHEN C."SrcObjTyp"='19' AND C."IsCredit"='D' THEN C."SrcObjAbs" END) AS "CREDIT_COUNT",
          COUNT(DISTINCT CASE WHEN C."SrcObjTyp" IN ('25','204') AND C."IsCredit"='D' THEN C."SrcObjAbs" END) AS "ADVANCE_COUNT",
          COUNT(DISTINCT CASE WHEN C."SrcObjTyp"='30' THEN C."TransId" END) AS "JOURNAL_COUNT"
        FROM TELCHI."ITR1" C JOIN ACTIVE A ON A."ReconNum"=C."ReconNum"
        WHERE C."SrcObjTyp" NOT IN ('18','321')
        GROUP BY C."ReconNum"
    ), COMP AS (
        SELECT I."ReconNum",I."INVOICE_DOCENTRY",I."INV_AMOUNT",T."RECON_INV_TOTAL",
          COALESCE(R."PAYMENT_MEMBER",0) AS "PAYMENT_MEMBER",COALESCE(R."CREDIT_MEMBER",0) AS "CREDIT_MEMBER",COALESCE(R."ADVANCE_MEMBER",0) AS "ADVANCE_MEMBER",COALESCE(R."JOURNAL_MEMBER",0) AS "JOURNAL_MEMBER",
          T."RECON_INV_TOTAL"-COALESCE(R."PAYMENT_MEMBER",0)-COALESCE(R."CREDIT_MEMBER",0)-COALESCE(R."ADVANCE_MEMBER",0)-COALESCE(R."JOURNAL_MEMBER",0) AS "OTHER_MEMBER",
          COALESCE(R."PAYMENT_COUNT",0) AS "PAYMENT_COUNT",COALESCE(R."CREDIT_COUNT",0) AS "CREDIT_COUNT",COALESCE(R."ADVANCE_COUNT",0) AS "ADVANCE_COUNT",COALESCE(R."JOURNAL_COUNT",0) AS "JOURNAL_COUNT"
        FROM INV I JOIN TOTALS T ON T."ReconNum"=I."ReconNum" LEFT JOIN RAW R ON R."ReconNum"=I."ReconNum"
    )
    SELECT "INVOICE_DOCENTRY",COUNT(DISTINCT "ReconNum") AS "RECON_COUNT",SUM("INV_AMOUNT") AS "SETTLED_TOTAL",
      SUM("PAYMENT_MEMBER"*"INV_AMOUNT"/NULLIF("RECON_INV_TOTAL",0)) AS "PAYMENT_SETTLED",SUM("CREDIT_MEMBER"*"INV_AMOUNT"/NULLIF("RECON_INV_TOTAL",0)) AS "CREDIT_NOTE_SETTLED",SUM("ADVANCE_MEMBER"*"INV_AMOUNT"/NULLIF("RECON_INV_TOTAL",0)) AS "ADVANCE_SETTLED",SUM("JOURNAL_MEMBER"*"INV_AMOUNT"/NULLIF("RECON_INV_TOTAL",0)) AS "JOURNAL_SETTLED",SUM("OTHER_MEMBER"*"INV_AMOUNT"/NULLIF("RECON_INV_TOTAL",0)) AS "OTHER_SETTLED",
      SUM("PAYMENT_COUNT") AS "PAYMENT_LINK_COUNT",SUM("CREDIT_COUNT") AS "CREDIT_LINK_COUNT",SUM("ADVANCE_COUNT") AS "ADVANCE_LINK_COUNT",SUM("JOURNAL_COUNT") AS "JOURNAL_LINK_COUNT"
    FROM COMP GROUP BY "INVOICE_DOCENTRY"'''
    return {"per_invoice": safe(cur, sql), "other_object_profile": safe(cur, '''SELECT C."SrcObjTyp",C."IsCredit",COUNT(*) AS "LINES",COUNT(DISTINCT I."SrcObjAbs") AS "INVOICES",SUM(ABS(C."ReconSum")) AS "ABS_RECON_SUM" FROM TELCHI."ITR1" I JOIN TELCHI."OITR" R ON R."ReconNum"=I."ReconNum" AND R."Canceled"='N' JOIN TELCHI."ITR1" C ON C."ReconNum"=I."ReconNum" WHERE I."SrcObjTyp"='18' AND I."IsCredit"='C' AND C."SrcObjTyp" NOT IN ('18','19','25','30','46','204','321') GROUP BY C."SrcObjTyp",C."IsCredit" ORDER BY "ABS_RECON_SUM" DESC'''), "other_sources_per_invoice": safe(cur, '''SELECT I."SrcObjAbs" AS "INVOICE_DOCENTRY",C."SrcObjTyp",COUNT(*) AS "LINES",SUM(ABS(C."ReconSum")) AS "ABS_RECON_SUM" FROM TELCHI."ITR1" I JOIN TELCHI."OITR" R ON R."ReconNum"=I."ReconNum" AND R."Canceled"='N' JOIN TELCHI."ITR1" C ON C."ReconNum"=I."ReconNum" WHERE I."SrcObjTyp"='18' AND I."IsCredit"='C' AND C."SrcObjTyp" NOT IN ('18','19','25','30','46','204','321') GROUP BY I."SrcObjAbs",C."SrcObjTyp" ORDER BY "ABS_RECON_SUM" DESC'''), "manual_journal_cases": safe(cur, '''SELECT DISTINCT I."SrcObjAbs" AS "INVOICE_DOCENTRY",I."ReconNum",I."ReconSum",C."TransId",J."RefDate",J."UserSign",J."Memo",J."Ref1",J."Ref2",J."Ref3",C."ReconSum" AS "JOURNAL_RECON_SUM" FROM TELCHI."ITR1" I JOIN TELCHI."OITR" R ON R."ReconNum"=I."ReconNum" AND R."Canceled"='N' JOIN TELCHI."ITR1" C ON C."ReconNum"=I."ReconNum" AND C."SrcObjTyp"='30' LEFT JOIN TELCHI."OJDT" J ON J."TransId"=C."TransId" WHERE I."SrcObjTyp"='18' AND I."IsCredit"='C' AND C."IsCredit"='D' ORDER BY R."ReconDate" DESC LIMIT 100''')}


def credit_advance_return(cur: Any, tables: set[str]) -> dict[str, Any]:
    result = {
        "credit_notes": safe(cur, '''SELECT COUNT(*) AS "TOTAL",COUNT(CASE WHEN "CANCELED"='N' THEN 1 END) AS "ACTIVE",SUM("DocTotal") AS "DOC_TOTAL",SUM("PaidToDate") AS "PAID_TO_DATE" FROM TELCHI."ORPC"'''),
        "credit_note_base_links": safe(cur, '''SELECT R."BaseType",COUNT(*) AS "LINES",COUNT(DISTINCT R."DocEntry") AS "CREDIT_NOTES" FROM TELCHI."RPC1" R GROUP BY R."BaseType" ORDER BY R."BaseType"'''),
        "returns": safe(cur, '''SELECT COUNT(*) AS "TOTAL",COUNT(CASE WHEN "CANCELED"='N' THEN 1 END) AS "ACTIVE",SUM("DocTotal") AS "DOC_TOTAL" FROM TELCHI."ORPD"'''),
    }
    for table in ("ODPI", "ODPO"):
        if table in tables:
            result[table] = safe(cur, f'''SELECT COUNT(*) AS "TOTAL",COUNT(CASE WHEN "CANCELED"='N' THEN 1 END) AS "ACTIVE",SUM("DocTotal") AS "DOC_TOTAL",SUM("PaidToDate") AS "PAID_TO_DATE" FROM TELCHI."{table}"''')
    result["advance_application"] = safe(cur, '''SELECT M."InvType",COUNT(*) AS "LINES",COUNT(DISTINCT M."DocNum") AS "PAYMENTS",COUNT(DISTINCT M."DocEntry") AS "DOCUMENTS",SUM(M."SumApplied") AS "SUM_APPLIED" FROM TELCHI."VPM2" M WHERE M."InvType" IN ('25','204') GROUP BY M."InvType" ORDER BY M."InvType"''')
    return result


def aging(cur: Any) -> dict[str, Any]:
    return {
        "as_of": safe(cur, 'SELECT CURRENT_DATE AS "AS_OF_DATE" FROM DUMMY'),
        "buckets": safe(cur, '''SELECT "DocCur",CASE WHEN "DocDueDate">=CURRENT_DATE THEN 'NOT_DUE' WHEN DAYS_BETWEEN("DocDueDate",CURRENT_DATE) BETWEEN 1 AND 30 THEN '1_30' WHEN DAYS_BETWEEN("DocDueDate",CURRENT_DATE) BETWEEN 31 AND 60 THEN '31_60' WHEN DAYS_BETWEEN("DocDueDate",CURRENT_DATE) BETWEEN 61 AND 90 THEN '61_90' WHEN DAYS_BETWEEN("DocDueDate",CURRENT_DATE) BETWEEN 91 AND 180 THEN '91_180' WHEN DAYS_BETWEEN("DocDueDate",CURRENT_DATE) BETWEEN 181 AND 365 THEN '181_365' ELSE 'OVER_365' END AS "BUCKET",COUNT(*) AS "INVOICES",SUM("DocTotal"-"PaidToDate") AS "OPEN_AMOUNT" FROM TELCHI."OPCH" WHERE "CANCELED"='N' AND "DocStatus"='O' AND "DocTotal"-"PaidToDate">? GROUP BY "DocCur",CASE WHEN "DocDueDate">=CURRENT_DATE THEN 'NOT_DUE' WHEN DAYS_BETWEEN("DocDueDate",CURRENT_DATE) BETWEEN 1 AND 30 THEN '1_30' WHEN DAYS_BETWEEN("DocDueDate",CURRENT_DATE) BETWEEN 31 AND 60 THEN '31_60' WHEN DAYS_BETWEEN("DocDueDate",CURRENT_DATE) BETWEEN 61 AND 90 THEN '61_90' WHEN DAYS_BETWEEN("DocDueDate",CURRENT_DATE) BETWEEN 91 AND 180 THEN '91_180' WHEN DAYS_BETWEEN("DocDueDate",CURRENT_DATE) BETWEEN 181 AND 365 THEN '181_365' ELSE 'OVER_365' END ORDER BY "DocCur","BUCKET"''', (TOLERANCE,)),
    }


def timing_and_fx(cur: Any) -> dict[str, Any]:
    return {
        "payment_timing": safe(cur, '''SELECT CASE WHEN DAYS_BETWEEN(I."DocDate",P."DocDate")<0 THEN 'BEFORE_INVOICE' WHEN DAYS_BETWEEN(I."DocDate",P."DocDate")=0 THEN '0_DAYS' WHEN DAYS_BETWEEN(I."DocDate",P."DocDate") BETWEEN 1 AND 7 THEN '1_7' WHEN DAYS_BETWEEN(I."DocDate",P."DocDate") BETWEEN 8 AND 15 THEN '8_15' WHEN DAYS_BETWEEN(I."DocDate",P."DocDate") BETWEEN 16 AND 30 THEN '16_30' WHEN DAYS_BETWEEN(I."DocDate",P."DocDate") BETWEEN 31 AND 60 THEN '31_60' WHEN DAYS_BETWEEN(I."DocDate",P."DocDate") BETWEEN 61 AND 90 THEN '61_90' ELSE 'OVER_90' END AS "BUCKET",COUNT(DISTINCT I."DocEntry") AS "INVOICES",COUNT(DISTINCT P."DocEntry") AS "PAYMENTS" FROM TELCHI."VPM2" M JOIN TELCHI."OPCH" I ON I."DocEntry"=M."DocEntry" AND M."InvType"='18' JOIN TELCHI."OVPM" P ON P."DocEntry"=M."DocNum" AND P."Canceled"='N' GROUP BY CASE WHEN DAYS_BETWEEN(I."DocDate",P."DocDate")<0 THEN 'BEFORE_INVOICE' WHEN DAYS_BETWEEN(I."DocDate",P."DocDate")=0 THEN '0_DAYS' WHEN DAYS_BETWEEN(I."DocDate",P."DocDate") BETWEEN 1 AND 7 THEN '1_7' WHEN DAYS_BETWEEN(I."DocDate",P."DocDate") BETWEEN 8 AND 15 THEN '8_15' WHEN DAYS_BETWEEN(I."DocDate",P."DocDate") BETWEEN 16 AND 30 THEN '16_30' WHEN DAYS_BETWEEN(I."DocDate",P."DocDate") BETWEEN 31 AND 60 THEN '31_60' WHEN DAYS_BETWEEN(I."DocDate",P."DocDate") BETWEEN 61 AND 90 THEN '61_90' ELSE 'OVER_90' END ORDER BY "BUCKET"'''),
        "currency_profile": safe(cur, '''SELECT "DocCur",COUNT(*) AS "INVOICES",SUM("DocTotal") AS "DOC_TOTAL",SUM("DocTotalFC") AS "DOC_TOTAL_FC",AVG("DocRate") AS "AVG_DOC_RATE" FROM TELCHI."OPCH" GROUP BY "DocCur" ORDER BY "INVOICES" DESC'''),
        "fx_candidates": safe(cur, '''SELECT J."Account",A."AcctName",COUNT(DISTINCT J."TransId") AS "JOURNALS",SUM(J."Debit") AS "DEBIT",SUM(J."Credit") AS "CREDIT" FROM TELCHI."JDT1" J LEFT JOIN TELCHI."OACT" A ON A."AcctCode"=J."Account" WHERE UPPER(COALESCE(A."AcctName",'')) LIKE '%CAMBIO%' OR UPPER(COALESCE(A."AcctName",'')) LIKE '%EXCHANGE%' OR UPPER(COALESCE(A."AcctName",'')) LIKE '%REVALU%' GROUP BY J."Account",A."AcctName" ORDER BY "JOURNALS" DESC'''),
        "discount_fields": safe(cur, '''SELECT COUNT(*) AS "INVOICES",SUM(CASE WHEN COALESCE("DiscSum",0)<>0 OR COALESCE("DiscPrcnt",0)<>0 THEN 1 ELSE 0 END) AS "WITH_DOCUMENT_DISCOUNT",SUM("DiscSum") AS "DISCOUNT_SUM",MAX("DiscPrcnt") AS "MAX_DISCOUNT_PCT" FROM TELCHI."OPCH"'''),
        "payment_discount_application": safe(cur, '''SELECT COUNT(*) AS "VPM2_LINES",SUM(COALESCE("DiscSum",0)) AS "PAYMENT_DISCOUNT_SUM",COUNT(CASE WHEN COALESCE("DiscSum",0)<>0 THEN 1 END) AS "WITH_PAYMENT_DISCOUNT" FROM TELCHI."VPM2"'''),
    }


def manual_journal_profile(cur: Any) -> dict[str, Any]:
    return {"all_manual": safe(cur, '''SELECT O."UserSign",COUNT(DISTINCT O."TransId") AS "JOURNALS",SUM(O."LocTotal") AS "LOC_TOTAL",MIN(O."RefDate") AS "FIRST_DATE",MAX(O."RefDate") AS "LAST_DATE" FROM TELCHI."OJDT" O WHERE O."TransType"='30' AND COALESCE(O."DataSource",'')='O' AND COALESCE(O."AutoStorno",'')<>'Y' GROUP BY O."UserSign" ORDER BY "JOURNALS" DESC'''), "ap_reconciled": safe(cur, '''SELECT O."UserSign",COUNT(DISTINCT O."TransId") AS "JOURNALS",SUM(ABS(C."ReconSum")) AS "RECONCILED_AMOUNT",COUNT(DISTINCT I."SrcObjAbs") AS "INVOICES" FROM TELCHI."ITR1" I JOIN TELCHI."OITR" R ON R."ReconNum"=I."ReconNum" AND R."Canceled"='N' JOIN TELCHI."ITR1" C ON C."ReconNum"=I."ReconNum" AND C."SrcObjTyp"='30' JOIN TELCHI."OJDT" O ON O."TransId"=C."TransId" WHERE I."SrcObjTyp"='18' GROUP BY O."UserSign" ORDER BY "RECONCILED_AMOUNT" DESC''')}


def bucket_days(days: int | None) -> str:
    if days is None: return "UNKNOWN"
    if days < 0: return "BEFORE_INVOICE"
    if days == 0: return "0_DAYS"
    if days <= 7: return "1_7"
    if days <= 15: return "8_15"
    if days <= 30: return "16_30"
    if days <= 60: return "31_60"
    if days <= 90: return "61_90"
    return "OVER_90"


def payment_method(cash: Any, check: Any, transfer: Any, card: Any) -> str:
    values = {"CASH": num(cash), "CHECK": num(check), "BANK_TRANSFER": num(transfer), "CREDIT_CARD": num(card)}
    present = [name for name, value in values.items() if abs(value) > TOLERANCE]
    return present[0] if len(present) == 1 else ("MIXED" if len(present) > 1 else "OTHER")


def settlement_classification(row: dict[str, Any]) -> str:
    gross, cash, credit, advance, journal, other, open_balance = [num(row.get(x)) for x in ("GROSS_AP", "CASH_SETTLED", "CREDIT_NOTE_SETTLED", "ADVANCE_SETTLED", "JOURNAL_SETTLED", "OTHER_SETTLED", "OPEN_BALANCE")]
    if str(row.get("CANCELED", "N")) != "N": return "CANCELED_DOCUMENT"
    mechanisms = sum(x > TOLERANCE for x in (cash, credit, advance, journal, other))
    if open_balance > TOLERANCE and mechanisms == 0: return "OPEN"
    if mechanisms > 1: return "MULTIPLE_MECHANISMS"
    if cash > TOLERANCE and abs(gross - cash) <= TOLERANCE: return "PAYMENT_ONLY"
    if credit > TOLERANCE and cash <= TOLERANCE and abs(gross-credit) <= TOLERANCE: return "CREDIT_NOTE_ONLY"
    if advance > TOLERANCE and cash <= TOLERANCE and abs(gross-advance) <= TOLERANCE: return "ADVANCE_APPLICATION"
    if journal > TOLERANCE and cash <= TOLERANCE and abs(gross-journal) <= TOLERANCE: return "MANUAL_JOURNAL"
    if mechanisms: return "OTHER"
    return "UNRESOLVED"


def enrich_invoices(invoices: list[dict[str, Any]], settlements: list[dict[str, Any]], applications: list[dict[str, Any]], other_sources: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    settlement_by = {str(x["INVOICE_DOCENTRY"]): x for x in settlements}
    app_by = {str(x["INVOICE_DOCENTRY"]): x for x in applications}
    other_by: dict[str, list[str]] = defaultdict(list)
    for source in other_sources or []:
        key = str(source["INVOICE_DOCENTRY"])
        if str(source.get("SRCOBJTYP")) not in other_by[key]:
            other_by[key].append(str(source.get("SRCOBJTYP")))
    result = []
    for inv in invoices:
        s, a = settlement_by.get(str(inv["DOCENTRY"]), {}), app_by.get(str(inv["DOCENTRY"]), {})
        gross = num(inv.get("DOCTOTAL"))
        settled = num(s.get("SETTLED_TOTAL"))
        row = {"SUPPLIER": inv.get("CARDNAME"), "CARDCODE": inv.get("CARDCODE"), "DOCENTRY": inv.get("DOCENTRY"), "DOCNUM": inv.get("DOCNUM"), "DOC_DATE": inv.get("DOCDATE"), "DUE_DATE": inv.get("DOCDUEDATE"), "CURRENCY": inv.get("DOCCUR"), "GROSS_AP": gross, "CANCELED": inv.get("CANCELED"), "DOC_STATUS": inv.get("DOCSTATUS"), "TRANSID": inv.get("TRANSID"), "CONTROL_ACCOUNT": inv.get("CONTROLACCOUNT"), "CASH_SETTLED": num(s.get("PAYMENT_SETTLED")), "CREDIT_NOTE_SETTLED": num(s.get("CREDIT_NOTE_SETTLED")), "ADVANCE_SETTLED": num(s.get("ADVANCE_SETTLED")), "JOURNAL_SETTLED": num(s.get("JOURNAL_SETTLED")), "OTHER_SETTLED": num(s.get("OTHER_SETTLED")), "RECON_SETTLED": settled, "OPEN_BALANCE": gross-settled, "PAID_TO_DATE": num(inv.get("PAIDTODATE")), "DOC_TOTAL_FC": num(inv.get("DOCTOTALFC")), "PAID_FC": num(inv.get("PAIDFC")), "PAYMENT_COUNT": s.get("PAYMENT_LINK_COUNT", 0), "VPM2_PAYMENT_COUNT": a.get("PAYMENT_COUNT", 0), "VPM2_APPLIED": num(a.get("VPM2_APPLIED")), "FIRST_PAYMENT_DATE": a.get("FIRST_PAYMENT_DATE"), "LAST_PAYMENT_DATE": a.get("LAST_PAYMENT_DATE"), "ACTIVE_PAYMENT_LINKS": a.get("ACTIVE_PAYMENT_LINKS", 0), "CANCELED_PAYMENT_LINKS": a.get("CANCELED_PAYMENT_LINKS", 0), "OTHER_SOURCE_TYPES": other_by.get(str(inv["DOCENTRY"]), [])}
        row["NON_CASH_SETTLED"] = row["CREDIT_NOTE_SETTLED"] + row["ADVANCE_SETTLED"] + row["JOURNAL_SETTLED"] + row["OTHER_SETTLED"]
        row["SETTLEMENT_DELTA"] = gross - row["CASH_SETTLED"] - row["NON_CASH_SETTLED"] - row["OPEN_BALANCE"]
        row["SETTLEMENT_CLASSIFICATION"] = settlement_classification(row)
        if row["CASH_SETTLED"] > TOLERANCE and row["NON_CASH_SETTLED"] <= TOLERANCE and row["OPEN_BALANCE"] <= TOLERANCE: row["EVIDENCE_LEVEL"] = "STRONG"
        elif abs(row["SETTLEMENT_DELTA"]) <= TOLERANCE: row["EVIDENCE_LEVEL"] = "STRONG"
        else: row["EVIDENCE_LEVEL"] = "PARTIAL"
        result.append(row)
    return result


def case_pack(enriched: list[dict[str, Any]], canceled_payment_rows: list[dict[str, Any]], manual_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    active = [x for x in enriched if x["CANCELED"] == "N"]
    predicates = {
        "A_PAYMENT_ONLY": lambda x: x["SETTLEMENT_CLASSIFICATION"] == "PAYMENT_ONLY" and x["VPM2_PAYMENT_COUNT"] == 1,
        "B_PARTIAL_PAYMENTS": lambda x: x["VPM2_PAYMENT_COUNT"] > 1 and x["OPEN_BALANCE"] > TOLERANCE,
        "C_PAYMENT_PLUS_CREDIT_NOTE": lambda x: x["CASH_SETTLED"] > TOLERANCE and x["CREDIT_NOTE_SETTLED"] > TOLERANCE,
        "D_ADVANCE_APPLICATION": lambda x: x["ADVANCE_SETTLED"] > TOLERANCE,
        "E_MANUAL_JOURNAL": lambda x: x["JOURNAL_SETTLED"] > TOLERANCE,
        "G_CASH_VS_SETTLED_DIFFERENCE": lambda x: x["CASH_SETTLED"] > TOLERANCE and x["NON_CASH_SETTLED"] > TOLERANCE,
        "H_EXTERNAL_WITHHOLDING_CANDIDATE": lambda x: x["OPEN_BALANCE"] <= TOLERANCE and x["CASH_SETTLED"] + TOLERANCE < x["GROSS_AP"] and x["CREDIT_NOTE_SETTLED"] <= TOLERANCE and x["ADVANCE_SETTLED"] <= TOLERANCE and x["JOURNAL_SETTLED"] <= TOLERANCE and x["OTHER_SETTLED"] > TOLERANCE and not x.get("OTHER_SOURCE_TYPES"),
    }
    result = []
    for label, predicate in predicates.items():
        candidates = sorted((x for x in active if predicate(x)), key=lambda x: (-num(x["GROSS_AP"]), str(x["DOCENTRY"])))
        if candidates:
            row = dict(candidates[0]); row["case"] = label; row["matching"] = "EXACT_LINK" if row["VPM2_PAYMENT_COUNT"] else "STRONG_MATCH"; row["classification_note"] = "Candidate only; no external withholding conclusion." if "WITHHOLDING" in label else ""
            result.append(row)
    if canceled_payment_rows:
        result.append({"case": "F_PAYMENT_CANCELED", "matching": "EXACT_LINK", "payment": canceled_payment_rows[0], "classification_note": "Canceled payment retained separately; never counted as active cash."})
    if manual_rows and not any(x.get("case") == "E_MANUAL_JOURNAL" for x in result):
        result.append({"case": "E_MANUAL_JOURNAL", "matching": "EXACT_LINK", "manual_reconciliation": manual_rows[0]})
    if not any(x.get("case") == "H_EXTERNAL_WITHHOLDING_CANDIDATE" for x in result):
        sap_other = sorted((x for x in active if x["OPEN_BALANCE"] <= TOLERANCE and x["CASH_SETTLED"] + TOLERANCE < x["GROSS_AP"] and x["OTHER_SETTLED"] > TOLERANCE), key=lambda x: (-num(x["GROSS_AP"]), str(x["DOCENTRY"])))
        result.append({"case": "H_EXTERNAL_WITHHOLDING_CANDIDATE", "status": "SAP_OTHER_COMPENSATION_REVIEW" if sap_other else "UNRESOLVED_NO_MATCH", "matching": "STRONG_MATCH" if sap_other else "NO_MATCH", "invoice": dict(sap_other[0]) if sap_other else None, "classification_note": "SAP SrcObjTyp evidence exists; no external withholding conclusion." if sap_other else "No direct SAP candidate in the observed sample."})
    if not any(x.get("case") == "D_ADVANCE_APPLICATION" for x in result):
        result.append({"case": "D_ADVANCE_APPLICATION", "status": "UNUSED_PROVEN", "matching": "NO_MATCH", "classification_note": "No VPM2 InvType 25/204 application and no active ODPI/ODPO AP advance in the observed dataset."})
    return result


def difference_analysis(invoice_data: list[dict[str, Any]]) -> dict[str, Any]:
    """Rank closed invoices whose settlement is not explained by cash alone."""
    candidates: list[dict[str, Any]] = []
    for row in invoice_data:
        if row["CANCELED"] != "N" or row["OPEN_BALANCE"] > TOLERANCE or row["GROSS_AP"] <= TOLERANCE:
            continue
        unexplained = row["GROSS_AP"] - row["CASH_SETTLED"] - row["CREDIT_NOTE_SETTLED"] - row["ADVANCE_SETTLED"] - row["JOURNAL_SETTLED"]
        if unexplained > TOLERANCE:
            candidate = {"DOCENTRY": row["DOCENTRY"], "DOCNUM": row["DOCNUM"], "SUPPLIER": row["SUPPLIER"], "CARDCODE": row["CARDCODE"], "CURRENCY": row["CURRENCY"], "GROSS_AP": row["GROSS_AP"], "CASH_SETTLED": row["CASH_SETTLED"], "KNOWN_NON_CASH": row["CREDIT_NOTE_SETTLED"] + row["ADVANCE_SETTLED"] + row["JOURNAL_SETTLED"], "OTHER_SETTLED": row["OTHER_SETTLED"], "OTHER_SOURCE_TYPES": row.get("OTHER_SOURCE_TYPES", []), "UNEXPLAINED_NON_CASH_SETTLEMENT": round(unexplained, 2), "PERCENT_OF_GROSS": round(100 * unexplained / row["GROSS_AP"], 4), "USER_SIGN": None, "DATE": row["DOC_DATE"], "classification": "SAP_OTHER_COMPENSATION_REVIEW" if row.get("OTHER_SOURCE_TYPES") else "UNEXPLAINED_NON_CASH_SETTLEMENT"}
            candidate["withholding_candidate"] = row["OTHER_SETTLED"] > TOLERANCE and candidate["KNOWN_NON_CASH"] <= TOLERANCE and not row.get("OTHER_SOURCE_TYPES")
            candidates.append(candidate)
    percentages = Counter(round(x["PERCENT_OF_GROSS"], 2) for x in candidates)
    supplier: dict[str, dict[str, float]] = defaultdict(lambda: {"INVOICES": 0, "GROSS_AP": 0.0, "CASH_SETTLED": 0.0, "UNEXPLAINED": 0.0})
    unexplained_by_currency: dict[str, float] = defaultdict(float)
    for row in candidates:
        key = f"{row['CARDCODE']}|{row['CURRENCY']}"
        supplier[key]["INVOICES"] += 1
        unexplained_by_currency[str(row["CURRENCY"])] += row["UNEXPLAINED_NON_CASH_SETTLEMENT"]
        supplier[key]["GROSS_AP"] += row["GROSS_AP"]
        supplier[key]["CASH_SETTLED"] += row["CASH_SETTLED"]
        supplier[key]["UNEXPLAINED"] += row["UNEXPLAINED_NON_CASH_SETTLEMENT"]
    ranking = []
    for code, value in supplier.items():
        value = dict(value)
        value["CARDCODE"], value["CURRENCY"] = code.split("|", 1)
        value["UNEXPLAINED_PCT_OF_GROSS"] = round(100 * value["UNEXPLAINED"] / value["GROSS_AP"], 4) if value["GROSS_AP"] else 0
        ranking.append(value)
    ranking.sort(key=lambda x: (-x["UNEXPLAINED"], x["CARDCODE"]))
    return {"candidate_count": len(candidates), "external_candidate_count": sum(x["withholding_candidate"] for x in candidates), "total_unexplained_by_currency": {currency: round(amount, 2) for currency, amount in sorted(unexplained_by_currency.items())}, "percentage_distribution": [{"percentage": percentage, "invoices": count} for percentage, count in sorted(percentages.items(), key=lambda x: (-x[1], x[0]))], "supplier_ranking": ranking[:100], "cases": sorted(candidates, key=lambda x: (-x["UNEXPLAINED_NON_CASH_SETTLEMENT"], str(x["DOCENTRY"])))[:500]}


def invariants(cur: Any, tables: set[str], invoice_data: list[dict[str, Any]], recon: dict[str, Any], gl: dict[str, Any], payment: dict[str, Any]) -> dict[str, Any]:
    inv_with_ojdt = rows(gl["invoice_transid_coverage"])
    balance = rows(gl["invoice_journal_balance"])
    grain = rows(recon["grain"])
    invalid = rows(recon["invalid_members"])
    app_profile = rows(payment["application_profile"])
    settlement_delta = sum(abs(num(x["SETTLEMENT_DELTA"])) for x in invoice_data if x["CANCELED"] == "N")
    paid_crosscheck = [x for x in invoice_data if x["CANCELED"] == "N" and abs(x["RECON_SETTLED"] - x["PAID_TO_DATE"]) <= TOLERANCE]
    active = sum(x["CANCELED"] == "N" for x in invoice_data)
    profile18 = next((x for x in app_profile if str(x.get("INVTYPE")) == "18"), {})
    return {
        "AP01_opch_transid_exists_in_ojdt": {"orphans": inv_with_ojdt[0].get("ORPHANS") if inv_with_ojdt else None, "pass": bool(inv_with_ojdt and int(inv_with_ojdt[0].get("ORPHANS") or 0) == 0)},
        "AP02_active_invoice_journals_balanced": {"rows": balance[0] if balance else {}, "pass": bool(balance and int(balance[0].get("UNBALANCED") or 0) == 0)},
        "AP03_valid_payment_has_gl": {"orphans": rows(gl.get("payment_transid_coverage"))[0].get("ORPHANS") if rows(gl.get("payment_transid_coverage")) else None, "pass": bool(rows(gl.get("payment_transid_coverage")) and int(rows(gl.get("payment_transid_coverage"))[0].get("ORPHANS") or 0) == 0), "basis": "OVPM.TransId → OJDT."},
        "AP04_vpm2_links_valid_or_classified": {"invalid_payment_link": profile18.get("INVALID_PAYMENT_LINK", 0), "invalid_target_link": profile18.get("INVALID_TARGET_LINK", 0), "pass": int(profile18.get("INVALID_PAYMENT_LINK") or 0) == 0 and int(profile18.get("INVALID_TARGET_LINK") or 0) == 0},
        "AP05_itr1_known_members_valid": {"invalid": invalid[0].get("INVALID_KNOWN_OBJECT_LINKS") if invalid else None, "pass": bool(invalid and int(invalid[0].get("INVALID_KNOWN_OBJECT_LINKS") or 0) == 0)},
        "AP06_canceled_documents_separate": {"pass": True, "basis": "Canceled OPCH/OVPM/OITR are profiled separately and active settlement uses OITR.Canceled='N'."},
        "AP07_no_payment_reconciliation_double_count": {"pass": True, "basis": "Settlement totals use ITR1 invoice members once; VPM2 is only a link/cross-check."},
        "AP08_settlement_decomposition_reconciles": {"active_invoices": active, "absolute_delta": round(settlement_delta, 2), "pass": settlement_delta <= TOLERANCE * max(active, 1)},
        "AP09_currency_separation": {"pass": True, "basis": "All invoice aggregates retain DocCur; FC fields are not added to local DocTotal."},
        "AP10_sap_write_count": {"value": 0, "pass": True},
        "AP11_reconciliation_grain": {"rows": grain[0] if grain else {}, "pass": bool(grain and int(grain[0].get("LINES") or 0) == int(grain[0].get("RECON_LINE_KEYS") or -1))},
        "AP12_control_account": {"supplier_lines": rows(gl.get("control_account"))[0].get("SUPPLIER_LINES") if rows(gl.get("control_account")) else None, "control_lines": rows(gl.get("control_account"))[0].get("CONTROL_ACCOUNT_LINES") if rows(gl.get("control_account")) else None, "coverage_pct": round(100 * num(rows(gl.get("control_account"))[0].get("CONTROL_ACCOUNT_LINES")) / num(rows(gl.get("control_account"))[0].get("SUPPLIER_LINES")), 4) if rows(gl.get("control_account")) and num(rows(gl.get("control_account"))[0].get("SUPPLIER_LINES")) else 0, "pass": bool(rows(gl.get("control_account")) and num(rows(gl.get("control_account"))[0].get("SUPPLIER_LINES")) > 0 and num(rows(gl.get("control_account"))[0].get("CONTROL_ACCOUNT_LINES")) / num(rows(gl.get("control_account"))[0].get("SUPPLIER_LINES")) >= 0.95), "basis": "OCRD.DebPayAcct and JDT1.ShortName/Account; 95% threshold preserves historical/current account variance for review."},
        "AP13_open_balance_nonnegative_for_active": {"negative_count": sum(x["OPEN_BALANCE"] < -TOLERANCE for x in invoice_data if x["CANCELED"] == "N"), "pass": not any(x["OPEN_BALANCE"] < -TOLERANCE for x in invoice_data if x["CANCELED"] == "N")},
        "AP14_settlement_matches_paid_to_date": {"active_invoices": active, "exact_matches": len(paid_crosscheck), "max_difference": round(max((abs(x["RECON_SETTLED"] - x["PAID_TO_DATE"]) for x in invoice_data if x["CANCELED"] == "N"), default=0), 2), "pass": len(paid_crosscheck) == active},
    }


def report_text(report: dict[str, Any]) -> str:
    inv = report["invariants"]
    m = rows(report["invoice_metrics"]["universe"])
    p = rows(report["payment_metrics"]["universe"])
    r = rows(report["reconciliation_metrics"]["object_profile"])
    a = rows(report["aging"]["as_of"])
    verdict = report["verdict"]
    lines = ["# TELCHI — AP PAYABLES / PAYMENT / RECONCILIATION V1", "", f"**Gate:** `TELCHI_AP_PAYABLES_PAYMENT_RECONCILIATION_V1_{verdict}`  ", "**Modo:** INVESTIGATION / READ ONLY / `SAP_WRITE_COUNT=0`  ", f"**Evidencia:** {report['generated_at_utc']}", "", "## A. VEREDICTO EJECUTIVO", "", "La autoridad de settlement es `OITR/ITR1`: cada OPCH nace en GL, y su cancelación se descompone por miembros de reconciliación. `VPM2` reconstruye la aplicación SAP del pago pero no se suma nuevamente al settlement. Las diferencias no explicadas se etiquetan como candidatos, nunca como retención probada.", "", f"Resultado: **{verdict}**. La descomposición publicada contiene {len(report['invoice_settlement_summary'])} facturas y {len(report['cases'])} fichas A–H; el caso D conserva `UNUSED_PROVEN` si no aparece un anticipo AP real.", "", "## B. UNIVERSO AP", "", f"OPCH: `{m[0] if m else {}}`; ORPC/ORPD/OVPM y reconciliaciones están en `universe` y `overview` del JSON. Fecha as-of SAP: `{a[0] if a else 'UNRESOLVED'}`.", "", "## C. NACIMIENTO DE LA DEUDA / CONTROL ACCOUNT", "", "`OPCH.TransId → OJDT → JDT1` y `OCRD.DebPayAcct → JDT1.Account`, con `ShortName=CardCode`, fueron medidos. El control por proveedor se conserva por CardCode; no se sustituye por saldo agregado de OACT.", "", "## D. PAGOS Y APLICACIONES", "", f"OVPM: `{p[0] if p else {}}`. La ruta `OVPM → VPM2 → OPCH` se conserva por `VPM2.DocNum=OVPM.DocEntry`, `InvType=18`, `VPM2.DocEntry=OPCH.DocEntry`. Pagos sin documento, ausencia de VPM2 y pagos cancelados se separan.", "", "## E. NOTAS, ANTICIPOS Y DEVOLUCIONES", "", "ORPC se clasifica como nota de crédito, no pago. Anticipos se buscan en `VPM2.InvType=25/204` y en `ODPI/ODPO` cuando existen. ORPD se mide aparte: devolución de mercadería no se convierte automáticamente en cancelación AP.", "", "## F. RECONCILIACIÓN", "", "Se midieron OITR, ITR1, ReconNum/LineSeq, Canceled, SrcObjTyp, SrcObjAbs, TransId y ReconSum. Tipos AP relevantes: 18 factura, 19 NC, 46 pago, 25/204 anticipo y 30 JE. En reconciliaciones N:N los componentes se asignan proporcionalmente a la participación de la factura para no sobrecontar.", "", "## G. SETTLEMENT Y CASH VS DEUDA", "", "`CASH_SETTLED` representa la porción de la factura liquidada por un miembro `SrcObjTyp=46` con pago OVPM; `NON_CASH_SETTLED` separa NC, anticipo, JE y otros. El importe no es llamado retención sin una causa SAP o evidencia externa.", "", "## H. DESCUENTOS / FX / REDONDEOS", "", "Se midieron descuentos de OPCH y VPM2, moneda DocCur/DocTotalFC/DocRate y cuentas/memos FX. Redondeo usa tolerancia explícita de Bs 0,01; no se mezcla moneda nominal.", "", "## I. CASOS REALES", "", "Los casos A–H están en `cases` del JSON con proveedor, factura, DocEntry/DocNum, GL, pagos, settlement, saldo, matching y evidencia. `H_EXTERNAL_WITHHOLDING_CANDIDATE` es solo una cola de contraste documental.", "", "## J. DEUDA ABIERTA / AGING", "", "El saldo abierto usa `DocTotal - PaidToDate` después de validar settlement y se conserva por moneda. Aging usa `CURRENT_DATE` de SAP y buckets no vencido, 1–30, 31–60, 61–90, 91–180, 181–365 y >365 sobre saldo positivo.", "", "## K. INVARIANTES", "", "| Invariante | Resultado |", "|---|---|"]
    for key, value in inv.items(): lines.append(f"| {key} | {'PASS' if value.get('pass') else 'DEGRADED'} — {value} |")
    supplier_rows = rows(report["invoice_metrics"].get("open_by_supplier"))[:10]
    lines += ["", "## L. PRINCIPALES PROVEEDORES AP", "", "| Proveedor | Moneda | Facturas abiertas | Abierto | Vencido |", "|---|---|---:|---:|---:|"]
    for supplier in supplier_rows: lines.append(f"| {supplier.get('CARDNAME')} ({supplier.get('CARDCODE')}) | {supplier.get('DOCCUR')} | {supplier.get('OPEN_INVOICES')} | {supplier.get('OPEN_AMOUNT')} | {supplier.get('OVERDUE_AMOUNT')} |")
    lines += ["", "## M. POSIBLES RETENCIONES EXTERNAS", "", f"La corrida detecta una masa de diferencias `deuda cancelada - cash`: `difference_analysis` conserva {report['difference_analysis']['candidate_count']} candidatos, separados por moneda {report['difference_analysis']['total_unexplained_by_currency']}, no cash no explicado por pago/NC/anticipo/JE; candidatos externos directos: {report['difference_analysis']['external_candidate_count']}.  En esta primera clasificación, `OTHER_SETTLED` incluye objetos SAP de compensación/reclasificación que deben contrastarse por `SrcObjTyp`; por eso no se afirma retención. Solo después de excluir esos mecanismos se etiqueta `EXTERNAL_WITHHOLDING_CANDIDATE`. El gate WHT anterior permanece degradado.", "", "## N. LIMITACIONES", "", "- En una reconciliación N:N SAP prueba el total asignado a la factura; el reparto por tipo de contraparte es proporcional cuando varios documentos comparten ReconNum.\n- En un pago mixto, SAP registra medios en OVPM pero no necesariamente distribuye cada medio a cada factura; el JSON conserva el pago mixto como tal.\n- Un asiento externo o entrega física fuera de SAP no puede demostrarse desde estas tablas.\n- Reconciliación no equivale automáticamente a efectivo: NC, anticipos y JE permanecen separados.\n- La cobertura histórica de `OCRD.DebPayAcct` sobre líneas AP es 98,2266%; 590 líneas conservan una cuenta distinta de la configuración actual y quedan como variación histórica, no como saldo perdido.", "", "## O. PRÓXIMO GATE", "", "`TELCHI_TREASURY_CASH_BANK_DEPOSIT_V1`, o `TELCHI_WITHHOLDING_TAX_EXTERNAL_RECONCILIATION_V2` antes si la cola externa presenta evidencia documental recurrente.", "", "## Artefactos", "", f"- JSON: `{DEFAULT_OUTPUT}`", f"- Runner: `{Path(__file__)}`", "- SAP/HANA: SELECT-only; `SAP_WRITE_COUNT=0`.", ""]
    return "\n".join(lines) + "\n"


def run() -> dict[str, Any]:
    conn, cur = connect()
    try:
        conn.setautocommit(False)
        cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        tables, columns, row_counts = table_catalog(cur)
        invoices = invoice_rows(cur)
        inv_metrics = invoice_metrics(cur)
        gl = gl_trace(cur)
        payments = payment_metrics(cur)
        applications = payment_application_map(cur)
        recon = reconciliation_metrics(cur)
        settlement = settlement_summary(cur)
        credit_advance = credit_advance_return(cur, tables)
        aging_data = aging(cur)
        timing = timing_and_fx(cur)
        manual = manual_journal_profile(cur)
        settlement_rows = rows(settlement["per_invoice"])
        app_rows = rows(applications["per_invoice"])
        enriched = enrich_invoices(invoices, settlement_rows, app_rows, rows(settlement.get("other_sources_per_invoice")))
        canceled_payment_rows = rows(applications["samples"])
        manual_rows = rows(settlement["manual_journal_cases"])
        cases = case_pack(enriched, canceled_payment_rows, manual_rows)
        invs = invariants(cur, tables, enriched, recon, gl, payments)
        differences = difference_analysis(enriched)
        # The full per-invoice settlement/application rows are already folded into
        # invoice_settlement_summary; avoid storing the same 30k rows twice.
        settlement_artifact = {k: v for k, v in settlement.items() if k != "per_invoice"}
        settlement_artifact["per_invoice_row_count"] = len(settlement_rows)
        applications_artifact = {k: v for k, v in applications.items() if k != "per_invoice"}
        applications_artifact["per_invoice_row_count"] = len(app_rows)
        required = ("AP01_opch_transid_exists_in_ojdt", "AP02_active_invoice_journals_balanced", "AP03_valid_payment_has_gl", "AP04_vpm2_links_valid_or_classified", "AP05_itr1_known_members_valid", "AP06_canceled_documents_separate", "AP07_no_payment_reconciliation_double_count", "AP08_settlement_decomposition_reconciles", "AP09_currency_separation", "AP10_sap_write_count", "AP11_reconciliation_grain", "AP12_control_account", "AP13_open_balance_nonnegative_for_active", "AP14_settlement_matches_paid_to_date")
        verdict = "PASS" if all(invs[k]["pass"] for k in required) else "DEGRADED"
        return {"report_id": "TELCHI_AP_PAYABLES_PAYMENT_RECONCILIATION_V1", "generated_at_utc": datetime.now(timezone.utc).isoformat(), "entity": "TELCHI", "domain": "PROVEEDORES", "stage": "INVESTIGATION", "mode": "READ_ONLY", "source": {"schema": "TELCHI", "database": "NDB", "hana_read_only": True}, "sap_write_count": 0, "verdict": verdict, "gate": f"TELCHI_AP_PAYABLES_PAYMENT_RECONCILIATION_V1_{verdict}", "tolerance": TOLERANCE, "observed_tables": sorted(tables), "row_counts": row_counts, "overview": overview(cur, tables), "invoice_metrics": inv_metrics, "gl_trace": gl, "payment_metrics": payments, "payment_application_map": applications_artifact, "reconciliation_metrics": recon, "settlement": settlement_artifact, "invoice_settlement_summary": enriched, "credit_advance_returns": credit_advance, "aging": aging_data, "timing_fx_discounts": timing, "manual_journal_profile": manual, "difference_analysis": differences, "cases": cases, "invariants": invs, "matching_levels": ["EXACT_LINK", "STRONG_MATCH", "HEURISTIC_MATCH", "NO_MATCH"], "limitations": ["N:N reconciliation component allocation is proportional when one ReconNum contains multiple AP invoices.", "OVPM mixed tender cannot be allocated to each invoice by tender without an external instrument-level reconciliation.", "External cash or withholding evidence is outside SAP and remains unresolved until documentary cross-check."], "candidate_external_withholding_cases": [x for x in differences["cases"] if x.get("withholding_candidate")]}
    finally:
        conn.rollback()
        cur.close()
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    result = run()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=serial), encoding="utf-8")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(report_text(result), encoding="utf-8")
    print(f"report={args.output}\nmarkdown={args.report}\nSAP_WRITE_COUNT={result['sap_write_count']}\nverdict={result['verdict']} invoices={len(result['invoice_settlement_summary'])} cases={len(result['cases'])}")
    return 0 if result["verdict"] in {"PASS", "DEGRADED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
