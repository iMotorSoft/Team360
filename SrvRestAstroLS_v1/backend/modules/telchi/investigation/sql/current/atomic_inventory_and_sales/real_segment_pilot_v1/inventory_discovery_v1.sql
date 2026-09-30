-- TELCHI real segment pilot V1. One bounded key lookup; SAP HANA READ ONLY.
SELECT TOP 1 W."ItemCode", W."WhsCode"
FROM "TELCHI"."OITW" W
ORDER BY W."ItemCode", W."WhsCode"
