-- TELCHI real segment pilot V2. Exact DocEntry scope; SAP HANA READ ONLY.
SELECT
  H."DocEntry", H."DocNum", H."DocDate", H."DocDueDate", H."TaxDate",
  H."DocStatus", H."CANCELED", H."DocCur", H."DocTotal", H."CardCode",
  L."LineNum", L."LineStatus", L."ItemCode", L."Dscription", L."Quantity",
  L."unitMsr", L."NumPerMsr", L."WhsCode", L."Price", L."PriceBefDi",
  L."Currency" AS "LineCurrency", L."Rate" AS "LineRate",
  L."DiscPrcnt" AS "LineDiscPrcnt", L."LineTotal", L."TotalFrgn",
  L."TotalSumSy", L."VatPrcnt", L."VatSum" AS "LineVatSum"
FROM "TELCHI"."OINV" H
JOIN "TELCHI"."INV1" L ON L."DocEntry" = H."DocEntry"
WHERE H."DocEntry" = ?
ORDER BY L."LineNum"
