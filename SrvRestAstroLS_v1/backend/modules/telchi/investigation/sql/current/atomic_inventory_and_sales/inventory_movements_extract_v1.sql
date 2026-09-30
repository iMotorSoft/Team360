-- ATOMIC INVENTORY MOVEMENTS source extraction V1. SAP HANA READ ONLY.
-- Identity proven unique on the current source: TransNum+Instance+DocLineNum+ItemCode+Warehouse.
-- OINM has no reliable update timestamp: bounded DocDate reread + deterministic merge is mandatory.
SELECT
  "TransNum", "Instance", "TransType", "CreatedBy", "BASE_REF" AS "BaseRef",
  "DocLineNum", "Ref1", "Ref2", "Comments", "JrnlMemo", "DocDate", "DocDueDate",
  "DocTime", "CardCode", "CardName", "ItemCode", "Dscription", "InQty", "OutQty",
  "TransValue", "CalcPrice", "Price", "Balance", "SlpCode", "Warehouse", "UserSign"
FROM TELCHI."OINM"
WHERE "DocDate" >= ? AND "DocDate" < ?
ORDER BY "TransNum", "Instance", "DocLineNum", "ItemCode", "Warehouse"
