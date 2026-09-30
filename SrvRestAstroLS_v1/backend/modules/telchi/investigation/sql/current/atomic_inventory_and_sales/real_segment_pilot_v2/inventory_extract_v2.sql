-- TELCHI real segment pilot V2. Exact ItemCode × WhsCode scope; SAP HANA READ ONLY.
SELECT
  W."ItemCode", W."WhsCode", W."OnHand", W."IsCommited", W."OnOrder"
FROM "TELCHI"."OITW" W
WHERE W."ItemCode" = ? AND W."WhsCode" = ?
