-- TELCHI real segment pilot V1. Exact ItemCode+WhsCode scope; SAP HANA READ ONLY.
SELECT
  W."ItemCode", W."WhsCode", W."OnHand", W."IsCommited", W."OnOrder",
  W."Consig", W."Counted", W."MinStock", W."MaxStock", W."MinOrder",
  W."AvgPrice", W."StockValue", W."Locked", W."Freezed",
  I."ItemName", I."InvntryUom", H."WhsName", H."Inactive"
FROM "TELCHI"."OITW" W
LEFT JOIN "TELCHI"."OITM" I ON I."ItemCode" = W."ItemCode"
LEFT JOIN "TELCHI"."OWHS" H ON H."WhsCode" = W."WhsCode"
WHERE W."ItemCode" = ? AND W."WhsCode" = ?
