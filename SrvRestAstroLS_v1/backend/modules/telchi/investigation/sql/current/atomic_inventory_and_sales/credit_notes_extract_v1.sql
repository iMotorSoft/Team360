-- ATOMIC CREDIT NOTES source extraction V1. Native signs are preserved.
-- Watermark: UpdateDate + UpdateTS + DocEntry, with bounded DocDate reread.
SELECT
  H."DocEntry", H."ObjType", H."DocNum", H."Series", H."NumAtCard",
  H."CardCode", H."CardName", H."DocDate", H."DocDueDate", H."TaxDate",
  H."CreateDate", H."CreateTS", H."UpdateDate", H."UpdateTS",
  H."DocStatus", H."CANCELED", H."DocSubType", H."DocCur", H."DocRate", H."SysRate",
  H."DocTotal", H."DocTotalFC", H."DocTotalSy", H."DiscPrcnt", H."DiscSum",
  H."DiscSumFC", H."DiscSumSy", H."VatSum", H."VatSumFC", H."VatSumSy",
  H."PaidToDate", H."PaidFC", H."PaidSys", H."GroupNum", H."SlpCode", H."UserSign",
  H."BPLId", H."DataSource", H."U_ORIGIN", H."U_SO1_01RETAILONE",
  L."LineNum", L."LineStatus", L."ItemCode", L."Dscription", L."Quantity",
  L."unitMsr", L."NumPerMsr", L."WhsCode", L."Price", L."PriceBefDi",
  L."Currency" AS "LineCurrency", L."Rate" AS "LineRate", L."DiscPrcnt" AS "LineDiscPrcnt",
  L."LineTotal", L."TotalFrgn", L."TotalSumSy", L."VatPrcnt", L."VatSum" AS "LineVatSum",
  L."VatSumFrgn" AS "LineVatSumFC", L."VatSumSy" AS "LineVatSumSy",
  L."GTotal", L."GTotalFC", L."GTotalSC", L."StockPrice", L."StockValue",
  L."BaseType", L."BaseEntry", L."BaseLine", L."TargetType", L."TrgetEntry",
  L."U_DESCLINEA", L."U_TYPE"
FROM TELCHI."ORIN" H
JOIN TELCHI."RIN1" L ON L."DocEntry" = H."DocEntry"
WHERE H."DocDate" >= ? AND H."DocDate" < ?
ORDER BY H."DocEntry", L."LineNum"
