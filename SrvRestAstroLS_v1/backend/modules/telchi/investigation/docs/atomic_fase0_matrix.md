# TELCHI — FASE 0 MATRIZ DE DOMINIOS (ATOMIC)

**Fecha:** 2026-08-25
**Método:** Inventario real de workspace nuevo + legacy + validación HANA read-only (§8).

| Dominio | Legacy | Nuevo (SQL+contract) | HANA validado | Estado |
|---|---|---|---|---|
| ventas | saleProduct, saleSB1Product (2018-2024) | `source_sale_header/line` + `SALE_HEADER/LINE` | ✅ grain DocEntry / DocEntry+LineNum (2023-02) | ✅ CONFIRMED |
| cobros | payout, cuentasxCobrar (2019-2022) | `source_payment_header` + `PAYMENT_HEADER` | ✅ grain DocEntry; perfil medio de pago real | ✅ CONFIRMED |
| stock | movProduct, movProductSB1 (2017-2024) | `source_inventory_movement` + `INVENTORY_MOVEMENT` + `relation_stock_document.sql` | ✅ DOCNUM_RESOLVE 94.9% (2023-02) | ✅ CONFIRMED |
| clientes | clientSB1.parq | — (maestro OCRD pendiente atomic) | (gates previos) | ✅ base previa |
| productos | product, productSB1, productTKB | — (OITM pendiente atomic) | (gates previos) | ✅ base previa |
| warehouses | wareHouseSB1, sapWhsOfficeName (60 filas WhsCode↔sucursal) | — (OWHS previo) | (gates previos) | ✅ CONFIRMED |
| reconciliaciones | reconB1 (2022-2023) | `relation_settlement.sql` (ITR1/OITR) | ✅ SrcObjTyp 13/24/14... ventana real | ✅ CONFIRMED |
| producción | recetasNiveles01, productTransform | `source_production_bom.sql` + BOM contracts | ✅ tablas OITT/ITT1/OWOR/WOR1 existen | 🟡 columnas confirmadas; capacity pendiente |
| BOM | recetasNiveles01.parq | ITT1 contract | ✅ 7.753 líneas | 🟡 validación cruzada legacy pendiente |
| precios | ProductSaleCostDay | — (pricing contract pendiente) | — | ⏳ PENDIENTE |
| proformas | — | OQUT/QUT1 (catalogado) | ✅ 158.931 QUT | ⏳ PROFORMA_SOURCE_UNRESOLVED |
| caja (cash event) | cash-*.parq (2019-2022): cjtrn/cjcja/cjdpc/vttrn (43 cajas, Efectivo 89.2%) | `source_cash_event_sap.sql` + `CASH_EVENT` contracts | ✅ SAP: ORCT CashSum>0 validado; legacy: grain parquet | ✅ CONFIRMED (SAP era) + baseline legacy |
| canales Retail One/DMS | — | UDFs OINV confirmados | ✅ U_ORIGIN, U_SO1_01* | 🟡 PARTIAL_TRACEABILITY |

**Tamaños reales (HANA, 2026-08-25):** OINV 1,816,736 · INV1 3,975,966 · ODLN 92,428 · DLN1 260,968 · OINM 8,304,256 · ORCT 1,794,866 · RCT2 1,797,957 · OITR 2,070,496 · ITR1 4,429,470 · OITT 1,043 · ITT1 7,753 · OWOR 20,745 · WOR1 141,366 · OQUT 158,931 · OCRD 13,987 · OWHS 82 · OSLP 251.

**Nota pyarrow (§42):** no se escribieron Parquet en este ciclo (DEC-004 vigente). Versiones legacy: 1.0.0 / 9.0.0 / 11.0.0 vs 25.0.1 actual — contrato de compatibilidad aún no definido.