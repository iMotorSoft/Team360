-- ATOMIC INVENTORY BALANCE SNAPSHOT source extraction V1. SAP HANA READ ONLY.
-- One observed state per ItemCode+WhsCode at extraction time; no historical state is fabricated.
SELECT
  W."ItemCode", W."WhsCode", W."OnHand", W."IsCommited", W."OnOrder", W."Consig",
  W."Counted", W."WasCounted", W."MinStock", W."MaxStock", W."MinOrder",
  W."AvgPrice", W."StockValue", W."Locked", W."Freezed", W."createDate", W."updateDate",
  I."ItemName", I."InvntryUom", H."WhsName", H."Inactive"
FROM TELCHI."OITW" W
LEFT JOIN TELCHI."OITM" I ON I."ItemCode" = W."ItemCode"
LEFT JOIN TELCHI."OWHS" H ON H."WhsCode" = W."WhsCode"
ORDER BY W."ItemCode", W."WhsCode"
