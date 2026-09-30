"""Versioned, explicit and bounded SAP HANA SELECT statements for V1."""
from __future__ import annotations

import re


SALES_DISCOVERY_SQL = '''
SELECT MIN(H."DocEntry") AS "min_doc_entry", MAX(H."DocEntry") AS "max_doc_entry"
FROM "TELCHI"."OINV" H
WHERE H."DocDate" >= ? AND H."DocDate" < ?
'''

SALES_YTD_MAX_DATE_SQL = '''
SELECT MAX(H."DocDate") AS "max_doc_date"
FROM "TELCHI"."OINV" H
WHERE H."DocDate" >= ?
'''

CREDIT_MEMO_DISCOVERY_SQL = '''
SELECT MIN(H."DocEntry") AS "min_doc_entry", MAX(H."DocEntry") AS "max_doc_entry"
FROM "TELCHI"."ORIN" H
WHERE H."DocDate" >= ? AND H."DocDate" < ?
'''

CREDIT_MEMO_YTD_MAX_DATE_SQL = '''
SELECT MAX(H."DocDate") AS "max_doc_date"
FROM "TELCHI"."ORIN" H
WHERE H."DocDate" >= ?
'''

OINM_YTD_MAX_DATE_SQL = '''
SELECT MAX(M."DocDate") AS "max_doc_date"
FROM "TELCHI"."OINM" M
WHERE M."DocDate" >= ?
'''

OITW_SOURCE_AS_OF_SQL = '''
SELECT CURRENT_UTCTIMESTAMP AS "source_as_of", COUNT(*) AS "row_count"
FROM "TELCHI"."OITW"
'''

OINM_YTD_DUPLICATE_SQL_TEMPLATE = '''
SELECT COUNT(*) AS "duplicate_source_key_count", COALESCE(SUM("key_count" - 1), 0) AS "duplicate_source_rows"
FROM (
  SELECT M."TransNum", M."TransSeq", COUNT(*) AS "key_count"
  FROM "TELCHI"."OINM" M
  WHERE M."DocDate" >= ? AND M."DocDate" < ?
  GROUP BY M."TransNum", M."TransSeq"
  HAVING COUNT(*) > 1
) D
'''

SALES_EXTRACT_SQL = '''
SELECT
  H."DocEntry", H."DocNum", H."DocDate", H."DocDueDate", H."TaxDate",
  H."DocStatus", H."CANCELED", H."DocCur", H."DocTotal", H."DocTotalSy", H."DocTotalFC",
  H."CardCode", H."SlpCode" AS "HeaderSlpCode", H."Series", H."UserSign",
  13 AS "ObjType", L."LineNum", L."LineStatus", L."ItemCode", L."Dscription",
  L."Quantity", L."unitMsr", L."NumPerMsr", L."WhsCode", L."Price",
  L."PriceBefDi", L."Currency" AS "LineCurrency", L."Rate" AS "LineRate",
  L."DiscPrcnt" AS "LineDiscPrcnt", L."LineTotal", L."TotalFrgn",
  L."TotalSumSy", L."VatPrcnt", L."VatSum" AS "LineVatSum", L."SlpCode" AS "LineSlpCode"
FROM "TELCHI"."OINV" H
JOIN "TELCHI"."INV1" L ON L."DocEntry" = H."DocEntry"
WHERE H."DocDate" >= ? AND H."DocDate" < ?
  AND H."DocEntry" >= ? AND H."DocEntry" < ?
ORDER BY H."DocEntry", L."LineNum"
'''

CREDIT_MEMO_EXTRACT_SQL = '''
SELECT
  H."DocEntry", H."DocNum", H."DocDate", H."CreateDate", H."UpdateDate",
  H."DocStatus", H."CANCELED", H."CardCode", H."SlpCode" AS "HeaderSlpCode",
  H."DocCur", H."DocTotal", H."DocTotalSy", H."DocTotalFC", H."Series", H."UserSign",
  14 AS "ObjType", L."LineNum", L."LineStatus", L."ItemCode", L."WhsCode",
  L."Quantity", L."Currency" AS "LineCurrency", L."LineTotal", L."TotalSumSy",
  L."TotalFrgn", L."SlpCode" AS "LineSlpCode", L."BaseType", L."BaseEntry", L."BaseLine"
FROM "TELCHI"."ORIN" H
JOIN "TELCHI"."RIN1" L ON L."DocEntry" = H."DocEntry"
WHERE H."DocDate" >= ? AND H."DocDate" < ?
  AND H."DocEntry" >= ? AND H."DocEntry" < ?
ORDER BY H."DocEntry", L."LineNum"
'''

INVENTORY_DISCOVERY_SQL_TEMPLATE = '''
SELECT TOP {limit}
  W."ItemCode", W."WhsCode"
FROM "TELCHI"."OITW" W
WHERE (W."ItemCode" > ? OR (W."ItemCode" = ? AND W."WhsCode" > ?))
ORDER BY W."ItemCode", W."WhsCode"
'''

INVENTORY_EXTRACT_SQL = '''
SELECT
  W."ItemCode", W."WhsCode", W."OnHand", W."IsCommited", W."OnOrder"
FROM "TELCHI"."OITW" W
WHERE (W."ItemCode" > ? OR (W."ItemCode" = ? AND W."WhsCode" >= ?))
  AND (W."ItemCode" < ? OR (W."ItemCode" = ? AND W."WhsCode" <= ?))
ORDER BY W."ItemCode", W."WhsCode"
'''

# Candidate names are probed individually before this query is assembled.  In
# particular, SAP installations expose ``BASE_REF`` and ``TransSeq`` while
# some older/custom catalogs use different optional document columns.  The
# executor never sends a SELECT * and only selects fields confirmed present.
OINM_FIELD_CANDIDATES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("TransNum", ("TransNum",)),
    ("TransSeq", ("TransSeq", "Instance")),
    ("DocEntry", ("DocEntry",)),
    ("BaseRef", ("BASE_REF", "BaseRef")),
    ("TransType", ("TransType",)),
    ("DocDate", ("DocDate",)),
    ("ItemCode", ("ItemCode",)),
    ("Warehouse", ("Warehouse", "WhsCode")),
    ("InQty", ("InQty",)),
    ("OutQty", ("OutQty",)),
    ("Price", ("Price",)),
    ("CalcPrice", ("CalcPrice",)),
    ("TransValue", ("TransValue",)),
    ("CreatedBy", ("CreatedBy",)),
    ("AppObjAbs", ("AppObjAbs",)),
    ("AppObjType", ("AppObjType",)),
    ("Instance", ("Instance",)),
    ("DocLineNum", ("DocLineNum",)),
    ("Ref1", ("Ref1",)),
    ("Ref2", ("Ref2",)),
    ("Comments", ("Comments",)),
    ("JrnlMemo", ("JrnlMemo",)),
    ("DocDueDate", ("DocDueDate",)),
    ("DocTime", ("DocTime",)),
    ("CardCode", ("CardCode",)),
    ("CardName", ("CardName",)),
    ("Dscription", ("Dscription",)),
    ("Balance", ("Balance",)),
    ("SlpCode", ("SlpCode",)),
    ("UserSign", ("UserSign",)),
    ("ApplObj", ("ApplObj",)),
    ("AppObjLine", ("AppObjLine",)),
)

OINM_REQUIRED_FIELDS = {"TransNum", "TransType", "DocDate", "ItemCode", "Warehouse", "InQty", "OutQty"}


def oinm_extract_sql(available: dict[str, str]) -> str:
    """Build an explicit bounded OINM SELECT from discovered source columns."""
    required = OINM_REQUIRED_FIELDS - set(available)
    if required:
        raise ValueError(f"OINM schema is missing required fields: {sorted(required)}")
    fields = dict(available)
    # TransSeq is the preferred native sequence.  Instance is retained as a
    # source field when present, not silently substituted for TransSeq.
    aliases = [
        ("TransNum", "TransNum"), ("TransSeq", "TransSeq"),
        ("Instance", "Instance"), ("DocEntry", "DocEntry"),
        ("BaseRef", "BaseRef"), ("TransType", "TransType"),
        ("DocDate", "DocDate"), ("ItemCode", "ItemCode"),
        ("Warehouse", "Warehouse"), ("InQty", "InQty"), ("OutQty", "OutQty"),
        ("Price", "Price"), ("CalcPrice", "CalcPrice"), ("TransValue", "TransValue"),
        ("CreatedBy", "CreatedBy"), ("AppObjAbs", "AppObjAbs"),
        ("AppObjType", "AppObjType"), ("DocLineNum", "DocLineNum"),
        ("Ref1", "Ref1"), ("Ref2", "Ref2"), ("Comments", "Comments"),
        ("JrnlMemo", "JrnlMemo"), ("DocDueDate", "DocDueDate"),
        ("DocTime", "DocTime"), ("CardCode", "CardCode"), ("CardName", "CardName"),
        ("Dscription", "Dscription"), ("Balance", "Balance"),
        ("SlpCode", "SlpCode"), ("UserSign", "UserSign"), ("ApplObj", "ApplObj"),
        ("AppObjLine", "AppObjLine"),
    ]
    selected = [f'M."{fields[canonical]}" AS "{canonical}"' for canonical, _ in aliases if canonical in fields]
    order = [f'M."{fields["TransNum"]}"'] + ([f'M."{fields["TransSeq"]}"'] if "TransSeq" in fields else [])
    return (
        "SELECT " + ", ".join(selected) +
        ' FROM "TELCHI"."OINM" M WHERE M."' + fields["DocDate"] + '" >= ? AND M."' +
        fields["DocDate"] + '" < ? AND M."' + fields["TransNum"] + '" >= ? AND M."' +
        fields["TransNum"] + '" < ? ORDER BY ' + ", ".join(order)
    )


_FORBIDDEN = re.compile(r"\b(INSERT|UPDATE|DELETE|MERGE|UPSERT|CREATE|ALTER|DROP|TRUNCATE|CALL|GRANT|REVOKE)\b", re.I)


def assert_read_only_select(sql: str) -> str:
    executable = "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--")).strip()
    if not executable.upper().startswith("SELECT") or _FORBIDDEN.search(executable):
        raise ValueError("SAP query is not a read-only SELECT")
    if "SELECT *" in executable.upper():
        raise ValueError("SAP query must not use SELECT *")
    return executable


def inventory_discovery_sql(limit: int) -> str:
    if limit <= 0 or limit > 1_000_000:
        raise ValueError("inventory discovery limit is outside the safe bound")
    return INVENTORY_DISCOVERY_SQL_TEMPLATE.format(limit=limit)


for _query in (SALES_DISCOVERY_SQL, SALES_EXTRACT_SQL, CREDIT_MEMO_DISCOVERY_SQL, CREDIT_MEMO_EXTRACT_SQL, INVENTORY_EXTRACT_SQL):
    assert_read_only_select(_query)
