-- =============================================================================
-- SALES TARGETS — Current HANA line-table diagnostic
-- =============================================================================
-- The legacy function has one joined SQL (sales_targets_header.sql); it does
-- not execute a separate line query. This read-only diagnostic preserves the
-- line-table contract needed to classify current external data availability.
-- =============================================================================

SELECT
    T0."Code",
    T0."LineId",
    T0."U_VENDEDOR",
    T0."U_VENDEDOR_N",
    T0."U_ENERO",
    T0."U_FEBRERO",
    T0."U_MARZO",
    T0."U_ABRIL",
    T0."U_MAYO",
    T0."U_JUNIO",
    T0."U_JULIO",
    T0."U_AGOSTO",
    T0."U_SEPTIEMBRE",
    T0."U_OCTUBRE",
    T0."U_NOVIEMBRE",
    T0."U_DICIEMBRE"
FROM "TELCHI"."@OBJ_VENTAS_L" T0;
