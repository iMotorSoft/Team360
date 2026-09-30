-- TELCHI real segment pilot V1. Bounded key discovery; SAP HANA READ ONLY.
SELECT TOP 1 H."DocEntry"
FROM "TELCHI"."OINV" H
JOIN "TELCHI"."INV1" L ON L."DocEntry" = H."DocEntry"
ORDER BY H."DocEntry"
