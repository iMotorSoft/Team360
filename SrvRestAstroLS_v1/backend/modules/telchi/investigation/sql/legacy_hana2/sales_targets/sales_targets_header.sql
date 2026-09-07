-- =============================================================================
-- SALES TARGETS — Legacy exact query
-- =============================================================================
-- Source: /media/issajar/DEVELOP/Projects/telchi/tb1/i-MotorSoft/SrvRest/faTB1Srv02.py::getObjetiveSale
-- Historical endpoint/credentials removed; SQL semantics preserved.
-- Output is later melted in Python into Codigo_Vendedor/Month/ObjetivoM.
-- =============================================================================

SELECT
    T0."Code",
    T0."U_SUPERVISOR",
    T0."U_SUPERVISOR_N",
    T2."SlpCode" AS "Codigo_Vendedor",
    T1."U_VENDEDOR_N",
    (CASE
        WHEN T2."U_CATVENDEDOR" = 1 THEN 'Calle'
        WHEN T2."U_CATVENDEDOR" = 2 THEN 'Corporativo'
        WHEN T2."U_CATVENDEDOR" = 3 THEN 'Provincia'
        ELSE 'Sin Definir'
    END) AS "Categoria_Vendedor",
    T1."U_ENERO" AS "01",
    T1."U_FEBRERO" AS "02",
    T1."U_MARZO" AS "03",
    T1."U_ABRIL" AS "04",
    T1."U_MAYO" AS "05",
    T1."U_JUNIO" AS "06",
    T1."U_JULIO" AS "07",
    T1."U_AGOSTO" AS "08",
    T1."U_SEPTIEMBRE" AS "09",
    T1."U_OCTUBRE" AS "10",
    T1."U_NOVIEMBRE" AS "11",
    T1."U_DICIEMBRE" AS "12",
    T3."empID",
    T4."Name"
FROM "TELCHI"."@OBJ_VENTAS_C" T0
INNER JOIN "TELCHI"."@OBJ_VENTAS_L" T1
    ON T0."Code" = T1."Code"
INNER JOIN "TELCHI"."OSLP" T2
    ON T1."U_VENDEDOR" = T2."SlpCode"
LEFT JOIN "TELCHI"."OHEM" T3
    ON T2."SlpCode" = T3."salesPrson"
LEFT JOIN "TELCHI"."OUBR" T4
    ON T3."branch" = T4."Code";
