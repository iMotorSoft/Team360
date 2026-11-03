# Familias de consultas históricas reutilizables

La agrupación posterior al inventario propone 26 familias. No genera código ni amplía TelchiAI; cada operación debe preservar su métrica, granularidad, permisos, fuente y cobertura.

Los IDs de preguntas y SQL están en `family_membership.csv`; las asociaciones SQL defendibles están separadas en `question_sql_links.csv`. Los mismos miembros pueden pertenecer a varias familias.

## F01 — Documentos y líneas comerciales

Agrupación conceptual respaldada por fuentes; las asociaciones completas están en `family_membership.csv`. La clasificación de familia no autoriza todos sus miembros.

- Variantes preservadas: ¿Qué contiene este documento?; ¿Qué líneas contiene un documento de múltiples líneas?; ¿Qué documentos, líneas, unidades y amount source-native tiene un cliente?; document contents
- Parámetros posibles: DocEntry; source_system; LineNum; límite.
- Semántica y dependencia: Hechos nativos por documento, sin excluir estados ni interpretar venta neta.
- Mapping CURRENT: sales_document + sales_line, snapshot 1408.
- Estado: **READY_FOUNDATION**; no significa capability aprobada.
- Fuentes: [query_catalog.md](../../../../SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/query_catalog.md); SQL: [sales_v1_linenum.sql](../../../../SrvRestAstroLS_v1/backend/modules/telchi/investigation/sql/current/sales/sales_v1_linenum.sql).
- Miembros candidatos: 12 ocurrencias de preguntas y 6 ocurrencias SQL, con IDs exactos en el CSV; no frecuencia de uso.

## F02 — Ventas por período y comparación

Agrupación conceptual respaldada por fuentes; las asociaciones completas están en `family_membership.csv`. La clasificación de familia no autoriza todos sus miembros.

- Variantes preservadas: ¿Cuánto de las ventas del mes se cobró?; ¿Cuánto vendimos hoy?; ¿Cuánto vendimos ayer?; ¿Cuánto vendimos este año?
- Parámetros posibles: desde/hasta; moneda; status; métrica; baseline.
- Semántica y dependencia: Separar importe documental, importe de línea y neto; comparación requiere misma cobertura.
- Mapping CURRENT: sales + credit_memo; DocTotal o LineTotal según métrica.
- Estado: **REQUIRES_METRIC_DEFINITION**; no significa capability aprobada.
- Fuentes: [FINANCIAL_REPORTING_CONTRACT.md](../../../../SrvRestAstroLS_v1/backend/modules/telchi/investigation/FINANCIAL_REPORTING_CONTRACT.md); SQL: [sales_monthly_v1.sql](../../../../SrvRestAstroLS_v1/backend/modules/telchi/investigation/sql/current/seasonality/sales_monthly_v1.sql).
- Miembros candidatos: 39 ocurrencias de preguntas y 7 ocurrencias SQL, con IDs exactos en el CSV; no frecuencia de uso.

## F03 — Ventas por cliente

Agrupación conceptual respaldada por fuentes; las asociaciones completas están en `family_membership.csv`. La clasificación de familia no autoriza todos sus miembros.

- Variantes preservadas: ¿Cuánto vendimos a Farmacia X este año?; De lo vendido a Farmacia X, ¿cuánto fue contado y cuánto crédito por sucursal?; ¿Cuánto vendimos ayer?; ¿Qué documentos, líneas, unidades y amount source-native tiene un cliente?
- Parámetros posibles: CardCode; período; métrica.
- Semántica y dependencia: No sumar cantidades de múltiples productos; resolver namespace y aliases.
- Mapping CURRENT: sales_document.card_code; Reference customers.code.
- Estado: **REQUIRES_MAPPING**; no significa capability aprobada.
- Fuentes: [TELCHI_DATALAKE_CEO_QUERY_SEMANTICS_AND_PERFORMANCE_CONTRACT_V1.md](../../../../SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/TELCHI_DATALAKE_CEO_QUERY_SEMANTICS_AND_PERFORMANCE_CONTRACT_V1.md); SQL: [sales_v1_linenum.sql](../../../../SrvRestAstroLS_v1/backend/modules/telchi/investigation/sql/current/sales/sales_v1_linenum.sql).
- Miembros candidatos: 19 ocurrencias de preguntas y 2 ocurrencias SQL, con IDs exactos en el CSV; no frecuencia de uso.

## F04 — Ventas por producto y presentación

Agrupación conceptual respaldada por fuentes; las asociaciones completas están en `family_membership.csv`. La clasificación de familia no autoriza todos sus miembros.

- Variantes preservadas: ¿Cuánto vendimos de Creolina?; ¿Cuántos litros de Creolina tengo en Saavedra?; ¿Qué stock tiene Creolina en todas las sucursales?; ¿Qué clientes compran Creolina?
- Parámetros posibles: SKU exacto; período; importe línea o cantidad nativa.
- Semántica y dependencia: Calenta es conjunto de candidatos de producto; cantidades por SKU, no suma kg/unidades.
- Mapping CURRENT: sales_line.item_code; products.item_code; namespaces diferentes.
- Estado: **READY_CONDITIONAL**; no significa capability aprobada.
- Fuentes: [product_seasonality_v1_report.md](../../../../SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/product_seasonality_v1_report.md); SQL: [sales_v1_linenum.sql](../../../../SrvRestAstroLS_v1/backend/modules/telchi/investigation/sql/current/sales/sales_v1_linenum.sql).
- Miembros candidatos: 198 ocurrencias de preguntas y 2 ocurrencias SQL, con IDs exactos en el CSV; no frecuencia de uso.

## F05 — Ventas por almacén y ubicación comercial

Agrupación conceptual respaldada por fuentes; las asociaciones completas están en `family_membership.csv`. La clasificación de familia no autoriza todos sus miembros.

- Variantes preservadas: ¿Cuánto vendió Segundo Anillo este mes?; ¿Cómo evolucionan las ventas por sucursal?; sales warehouse activity; ¿Qué unidades se registraron en un WhsCode?
- Parámetros posibles: WhsCode o ubicación validada; período; métrica.
- Semántica y dependencia: WhsCode no equivale a sucursal; warehouse planeado/documental/físico separados.
- Mapping CURRENT: sales_line.whs_code; Reference warehouses/business_locations.
- Estado: **REQUIRES_MAPPING**; no significa capability aprobada.
- Fuentes: [SALES_DIMENSIONS_FINAL_REPORT.md](../../../../SrvRestAstroLS_v1/backend/modules/telchi/investigation/validation/sales_dimensions/SALES_DIMENSIONS_FINAL_REPORT.md); SQL: [sales_v1_linenum.sql](../../../../SrvRestAstroLS_v1/backend/modules/telchi/investigation/sql/current/sales/sales_v1_linenum.sql).
- Miembros candidatos: 13 ocurrencias de preguntas y 2 ocurrencias SQL, con IDs exactos en el CSV; no frecuencia de uso.

## F06 — Vendedores, canales y venta corporativa

Agrupación conceptual respaldada por fuentes; las asociaciones completas están en `family_membership.csv`. La clasificación de familia no autoriza todos sus miembros.

- Variantes preservadas: ¿vendedor/reciente?; ¿Cuántas unidades vendimos por vendedor?; ¿Qué vendedor tiene peor venta contra su objetivo?; Ahora solamente venta horizontal.
- Parámetros posibles: año/mes; categoría vendedor validada.
- Semántica y dependencia: DocTotal BS activo menos NC BS por SlpCode; no generalizar al total ni canal por transacción.
- Mapping CURRENT: executive_sales.corporate_sales_by_salesperson; salespersons.
- Estado: **READY_CONDITIONAL**; no significa capability aprobada.
- Fuentes: [CORPORATE_SALES_FINAL_REPORT.md](../../../../SrvRestAstroLS_v1/backend/modules/telchi/investigation/validation/corporate_sales/CORPORATE_SALES_FINAL_REPORT.md); SQL: [05_salesperson_concentration.sql](../../../../SrvRestAstroLS_v1/backend/modules/telchi/investigation/sql/current/cancellation_audit/05_salesperson_concentration.sql).
- Miembros candidatos: 125 ocurrencias de preguntas y 7 ocurrencias SQL, con IDs exactos en el CSV; no frecuencia de uso.

## F07 — Rankings de productos y clientes

Agrupación conceptual respaldada por fuentes; las asociaciones completas están en `family_membership.csv`. La clasificación de familia no autoriza todos sus miembros.

- Variantes preservadas: ¿Cuáles son los 10 productos más vendidos?; cuales son los productos mas vendidos?; cuales son los productos mas vendidos?; Nueva consulta: top 10 productos por cantidad documental del 1 de enero al 15 de septiembre de 2026, sin filtros
- Parámetros posibles: métrica; UoM; período; top N; desempate.
- Semántica y dependencia: Top Quantity fuente no certifica comparación entre productos ni ventas netas.
- Mapping CURRENT: sales_line + product; Quantity, importe o net_qty diferenciados.
- Estado: **REQUIRES_METRIC_DEFINITION**; no significa capability aprobada.
- Fuentes: [query_catalog.md](../../../../SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/query_catalog.md); SQL: [sales_monthly_v1.sql](../../../../SrvRestAstroLS_v1/backend/modules/telchi/investigation/sql/current/seasonality/sales_monthly_v1.sql).
- Miembros candidatos: 80 ocurrencias de preguntas y 2 ocurrencias SQL, con IDs exactos en el CSV; no frecuencia de uso.

## F08 — Últimas operaciones comerciales

Agrupación conceptual respaldada por fuentes; las asociaciones completas están en `family_membership.csv`. La clasificación de familia no autoriza todos sus miembros.

- Variantes preservadas: dame las ultimas ventas de calenta; dame las ultimas ventas de calenta; dame las ultimas ventas de calenta; dame las ultimas ventas de calenta
- Parámetros posibles: fecha relevante; límite; entidad; status.
- Semántica y dependencia: DocDate no es instante de ingreso; no existe timestamp de registro demostrado.
- Mapping CURRENT: sales_document.doc_date; doc_entry orden determinista.
- Estado: **READY_CONDITIONAL**; no significa capability aprobada.
- Fuentes: [runner.py](../../../../SrvRestAstroLS_v1/backend/modules/telchi/investigation/validation/datalake_direct_business_query_validation_v1/runner.py); SQL: [sales_v1_linenum.sql](../../../../SrvRestAstroLS_v1/backend/modules/telchi/investigation/sql/current/sales/sales_v1_linenum.sql).
- Miembros candidatos: 40 ocurrencias de preguntas y 1 ocurrencias SQL, con IDs exactos en el CSV; no frecuencia de uso.

## F09 — Cobertura temporal y último mes

Agrupación conceptual respaldada por fuentes; las asociaciones completas están en `family_membership.csv`. La clasificación de familia no autoriza todos sus miembros.

- Variantes preservadas: ¿Qué mes y año querés consultar? No puedo determinar cuál fue el último mes registrado.; ¿Qué mes y año querés consultar? No puedo determinar cuál fue el último mes registrado.; ¿Qué mes y año querés consultar? No puedo determinar cuál fue el último mes registrado.; ¿Qué mes y año querés consultar? No puedo determinar cuál fue el último mes registrado.
- Parámetros posibles: entidad; métrica; publicación; completitud requerida.
- Semántica y dependencia: Máxima fecha 2026-09-24; septiembre tiene datos, no mes completo certificado.
- Mapping CURRENT: MIN/MAX doc_date por entidad/métrica; source_as_of separado.
- Estado: **READY_CONDITIONAL**; no significa capability aprobada.
- Fuentes: [runner.py](../../../../SrvRestAstroLS_v1/backend/modules/telchi/investigation/validation/datalake_2026_census_and_coverage_reconciliation_v1/runner.py); SQL: [sales_extract_v1.sql](../../../../SrvRestAstroLS_v1/backend/modules/telchi/investigation/sql/current/atomic_inventory_and_sales/sales_extract_v1.sql).
- Miembros candidatos: 17 ocurrencias de preguntas y 48 ocurrencias SQL, con IDs exactos en el CSV; no frecuencia de uso.

## F10 — Cancelaciones y notas de crédito

Agrupación conceptual respaldada por fuentes; las asociaciones completas están en `family_membership.csv`. La clasificación de familia no autoriza todos sus miembros.

- Variantes preservadas: ¿Cómo identificar pagos cancelados?; ¿Las notas de crédito están relacionadas?; ¿Cuánto vendimos neto de notas de crédito?; Which date describes the document and cancellation?
- Parámetros posibles: documento; tipo; período; evento.
- Semántica y dependencia: Original Y y reversa C preservados; NC positivas raw y signo según cálculo.
- Mapping CURRENT: sales y credit_memo; canceled; base_type/base_entry/base_line.
- Estado: **READY_CONDITIONAL**; no significa capability aprobada.
- Fuentes: [cancellation_findings.md](../../../../SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/cancellation_findings.md); SQL: [credit_notes_v1_linenum.sql](../../../../SrvRestAstroLS_v1/backend/modules/telchi/investigation/sql/current/credit_notes/credit_notes_v1_linenum.sql).
- Miembros candidatos: 243 ocurrencias de preguntas y 43 ocurrencias SQL, con IDs exactos en el CSV; no frecuencia de uso.

## F11 — Stock actual y disponibilidad

Agrupación conceptual respaldada por fuentes; las asociaciones completas están en `family_membership.csv`. La clasificación de familia no autoriza todos sus miembros.

- Variantes preservadas: ¿Cuánto stock disponible tengo?; ¿Cuál es el OnHand agregado de un scope pequeño?; ¿Cuál es el OnHand agregado de un scope pequeño?; ¿Qué OnHand/IsCommited/OnOrder tiene un caso no cero?
- Parámetros posibles: SKU; WhsCode; source_as_of; UoM.
- Semántica y dependencia: Detalle por SKU/almacén; disponible=on_hand-is_commited; on_order separado.
- Mapping CURRENT: inventory_balance + stock_availability; inventario UoM.
- Estado: **READY_FOUNDATION**; no significa capability aprobada.
- Fuentes: [material_stock_position_v1_report.md](../../../../SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/material_stock_position_v1_report.md); SQL: [item_stock_position_v1.sql](../../../../SrvRestAstroLS_v1/backend/modules/telchi/investigation/sql/current/stock/item_stock_position_v1.sql).
- Miembros candidatos: 218 ocurrencias de preguntas y 44 ocurrencias SQL, con IDs exactos en el CSV; no frecuencia de uso.

## F12 — Movimientos y trazabilidad de inventario

Agrupación conceptual respaldada por fuentes; las asociaciones completas están en `family_membership.csv`. La clasificación de familia no autoriza todos sus miembros.

- Variantes preservadas: MOVIMIENTOS_DE_INVENTARIO; MOVIMIENTOS_DE_INVENTARIO; MOVIMIENTOS_DE_INVENTARIO; MOVIMIENTOS_DE_INVENTARIO
- Parámetros posibles: clave fuente; SKU; warehouse; trans_type; período.
- Semántica y dependencia: InQty/OutQty separados; no inferir causalidad por item/fecha.
- Mapping CURRENT: inventory_movement, snapshot 1408; TransNum+TransSeq.
- Estado: **READY_CONDITIONAL**; no significa capability aprobada.
- Fuentes: [TRANSTYPE_MAP_FINAL_REPORT.md](../../../../SrvRestAstroLS_v1/backend/modules/telchi/investigation/validation/inventory_movements/TRANSTYPE_MAP_FINAL_REPORT.md); SQL: [source_inventory_movement.sql](../../../../SrvRestAstroLS_v1/backend/modules/telchi/investigation/sql/current/atomic/source_inventory_movement.sql).
- Miembros candidatos: 75 ocurrencias de preguntas y 158 ocurrencias SQL, con IDs exactos en el CSV; no frecuencia de uso.

## F13 — Rotación, cobertura y reposición

Agrupación conceptual respaldada por fuentes; las asociaciones completas están en `family_membership.csv`. La clasificación de familia no autoriza todos sus miembros.

- Variantes preservadas: Ver preguntas/objetivos en las fuentes citadas.
- Parámetros posibles: SKU; ventana; propósito comercial; demanda válida.
- Semántica y dependencia: Consumo interno no venta externa; stockout censura demanda; faltan unidades comparables.
- Mapping CURRENT: stock + sales + demanda/cobertura; sidecars comerciales no CURRENT.
- Estado: **REQUIRES_METRIC_DEFINITION**; no significa capability aprobada.
- Fuentes: [telchi_branch_replenishment_daily_stock_demand_v1_report.md](../../../../SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/telchi_branch_replenishment_daily_stock_demand_v1_report.md); SQL: [fg_usable_stock_v1.sql](../../../../SrvRestAstroLS_v1/backend/modules/telchi/investigation/sql/current/coverage/fg_usable_stock_v1.sql).
- Miembros candidatos: 3 ocurrencias de preguntas y 85 ocurrencias SQL, con IDs exactos en el CSV; no frecuencia de uso.

## F14 — Órdenes, recepciones y facturas de compra

Agrupación conceptual respaldada por fuentes; las asociaciones completas están en `family_membership.csv`. La clasificación de familia no autoriza todos sus miembros.

- Variantes preservadas: What is the canonical purchase chain?; Is ordered quantity in transit?; Contá órdenes de compra no canceladas de julio 2026 por proveedor; por fecha de PO.; Lo mismo en período, pero contá órdenes de compra no canceladas por proveedor.
- Parámetros posibles: proveedor; SKU; línea; período; path/cancelación.
- Semántica y dependencia: BaseType/BaseEntry/BaseLine; multi-recepción y out_of_coverage explícitos.
- Mapping CURRENT: purchasing manifest: 6 fuentes + lineage + receipt inventory.
- Estado: **READY_CONDITIONAL**; no significa capability aprobada.
- Fuentes: [telchi_purchase_to_warehouse_receipt_reconciliation_v1_report.md](../../../../SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/telchi_purchase_to_warehouse_receipt_reconciliation_v1_report.md); SQL: [purchase_document_chain_v1.sql](../../../../SrvRestAstroLS_v1/backend/modules/telchi/investigation/sql/current/purchases/purchase_document_chain_v1.sql).
- Miembros candidatos: 128 ocurrencias de preguntas y 9 ocurrencias SQL, con IDs exactos en el CSV; no frecuencia de uso.

## F15 — Abastecimiento, origen y lead time

Agrupación conceptual respaldada por fuentes; las asociaciones completas están en `family_membership.csv`. La clasificación de familia no autoriza todos sus miembros.

- Variantes preservadas: ¿Qué proveedores entregan parcialmente?; ¿Cuál es el lead time de los proveedores?; ¿Qué proveedores concentran las compras?; COMPRAS_Y_ABASTECIMIENTO
- Parámetros posibles: origen LF/LP/IMP/SAA; primera/última recepción; proveedor.
- Semántica y dependencia: DocDate lead time no prueba tiempo físico; Country no basta para importación.
- Mapping CURRENT: purchasing + material_supply.material_lead_time_profile.
- Estado: **READY_CONDITIONAL**; no significa capability aprobada.
- Fuentes: [purchase_lead_time_v1_report.md](../../../../SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/purchase_lead_time_v1_report.md); SQL: [purchase_lead_time_event_v1.sql](../../../../SrvRestAstroLS_v1/backend/modules/telchi/investigation/sql/current/lead_time/purchase_lead_time_event_v1.sql).
- Miembros candidatos: 42 ocurrencias de preguntas y 23 ocurrencias SQL, con IDs exactos en el CSV; no frecuencia de uso.

## F16 — Excepciones y diferencias de compras

Agrupación conceptual respaldada por fuentes; las asociaciones completas están en `family_membership.csv`. La clasificación de familia no autoriza todos sus miembros.

- Variantes preservadas: Ver preguntas/objetivos en las fuentes citadas.
- Parámetros posibles: línea AP; evidencia OC/GR/OINM; causa; límites cobertura.
- Semántica y dependencia: AP directa no equivale a ausencia física; separar evidencias de categorías causales.
- Mapping CURRENT: purchasing_document_lineage + purchase_inventory_receipt.
- Estado: **READY_CONDITIONAL**; no significa capability aprobada.
- Fuentes: [telchi_ap_invoiced_without_warehouse_receipt_v1_report.md](../../../../SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/telchi_ap_invoiced_without_warehouse_receipt_v1_report.md); SQL: [ap_invoice_v1.sql](../../../../SrvRestAstroLS_v1/backend/modules/telchi/investigation/sql/current/purchases/ap_invoice_v1.sql).
- Miembros candidatos: 5 ocurrencias de preguntas y 8 ocurrencias SQL, con IDs exactos en el CSV; no frecuencia de uso.

## F17 — Deuda actual, aging y riesgo abierto

Agrupación conceptual respaldada por fuentes; las asociaciones completas están en `family_membership.csv`. La clasificación de familia no autoriza todos sus miembros.

- Variantes preservadas: ¿existen facturas vencidas?; ¿Cuánto crédito vencido tenemos?; ¿Quiénes tienen mayor deuda vencida?; ¿Qué clientes aumentaron su deuda vencida?
- Parámetros posibles: cliente; as_of publicación; vencimiento; moneda.
- Semántica y dependencia: Saldo publicado no necesariamente reconstrucción histórica arbitrary as_of.
- Mapping CURRENT: receivable_settlement_status, snapshot base 1322.
- Estado: **READY_CONDITIONAL**; no significa capability aprobada.
- Fuentes: [credit_open_risk_aging_v1_report.md](../../../../SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/credit_open_risk_aging_v1_report.md); SQL: [current_ar_v1.sql](../../../../SrvRestAstroLS_v1/backend/modules/telchi/investigation/sql/current/financial/ar/current_ar_v1.sql).
- Miembros candidatos: 138 ocurrencias de preguntas y 84 ocurrencias SQL, con IDs exactos en el CSV; no frecuencia de uso.

## F18 — Crédito, excepciones y deuda histórica

Agrupación conceptual respaldada por fuentes; las asociaciones completas están en `family_membership.csv`. La clasificación de familia no autoriza todos sus miembros.

- Variantes preservadas: ¿Cómo identificar pagos cancelados?; ¿Se quedó como crédito a favor?; ¿Las notas de crédito están relacionadas?; De lo vendido a Farmacia X, ¿cuánto fue contado y cuánto crédito por sucursal?
- Parámetros posibles: cliente/grupo económico; instante; límite; reconciliación.
- Semántica y dependencia: Configuración de límite no prueba autorización; no hay historia suficiente de grants.
- Mapping CURRENT: receivables; clientes credit_limit; fuentes históricas settlement.
- Estado: **REQUIRES_MAPPING**; no significa capability aprobada.
- Fuentes: [credit_exception_cases_v1_report.md](../../../../SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/credit_exception_cases_v1_report.md); SQL: [settlement_aggregation_v1.sql](../../../../SrvRestAstroLS_v1/backend/modules/telchi/investigation/sql/current/financial/ar/settlement_aggregation_v1.sql).
- Miembros candidatos: 353 ocurrencias de preguntas y 1 ocurrencias SQL, con IDs exactos en el CSV; no frecuencia de uso.

## F19 — Cobranzas, pagos y aplicación

Agrupación conceptual respaldada por fuentes; las asociaciones completas están en `family_membership.csv`. La clasificación de familia no autoriza todos sus miembros.

- Variantes preservadas: ¿Cómo identificar pagos cancelados?
- Parámetros posibles: fecha pago; método; cliente; documento; moneda.
- Semántica y dependencia: Componente de medio de pago no pago único; RCT2 no autoridad settlement histórica Telchi.
- Mapping CURRENT: collection_method_fact + receivable_settlement_status.
- Estado: **READY_CONDITIONAL**; no significa capability aprobada.
- Fuentes: [traceability_cash_accounting_h4_v1_report.md](../../../../SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/traceability_cash_accounting_h4_v1_report.md); SQL: [payment_application_v1.sql](../../../../SrvRestAstroLS_v1/backend/modules/telchi/investigation/sql/current/financial/payment_application_v1.sql).
- Miembros candidatos: 41 ocurrencias de preguntas y 122 ocurrencias SQL, con IDs exactos en el CSV; no frecuencia de uso.

## F20 — Producción y consumo real

Agrupación conceptual respaldada por fuentes; las asociaciones completas están en `family_membership.csv`. La clasificación de familia no autoriza todos sus miembros.

- Variantes preservadas: ¿Cuántas producciones?; What is production reconciliation?; ¿Cuántas órdenes de producción están abiertas?; ¿Qué producción quedó parcial o en cero?
- Parámetros posibles: orden; componente; emisión/recibo real; período.
- Semántica y dependencia: BOM planificada no emisión real; no inferir producción desde venta.
- Mapping CURRENT: material_supply.material_actual_consumption; BOM/source production parcial.
- Estado: **REQUIRES_SOURCE**; no significa capability aprobada.
- Fuentes: [production_component_consumption_v1_report.md](../../../../SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/production_component_consumption_v1_report.md); SQL: [production_consumed_v1.sql](../../../../SrvRestAstroLS_v1/backend/modules/telchi/investigation/sql/current/equivalence/production_consumed_v1.sql).
- Miembros candidatos: 407 ocurrencias de preguntas y 94 ocurrencias SQL, con IDs exactos en el CSV; no frecuencia de uso.

## F21 — Recetas, equivalencia y capacidad

Agrupación conceptual respaldada por fuentes; las asociaciones completas están en `family_membership.csv`. La clasificación de familia no autoriza todos sus miembros.

- Variantes preservadas: ¿Tiene sentido generar recetas magistrales?; ¿Qué clientes terceros utilizan más capacidad?; What is historical BOM truth?; BOM_PRODUCCIÓN
- Parámetros posibles: producto terminado; componente; factor; UoM; capacidad.
- Semántica y dependencia: Equivalencia/densidad autorizada y dependencias multi-nivel; no suma kg/L.
- Mapping CURRENT: material_supply.material_equivalent_demand; stock; requisitos BOM.
- Estado: **REQUIRES_MAPPING**; no significa capability aprobada.
- Fuentes: [max_producible_by_component_v1_report.md](../../../../SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/max_producible_by_component_v1_report.md); SQL: [fg_component_requirement_v1.sql](../../../../SrvRestAstroLS_v1/backend/modules/telchi/investigation/sql/current/capacity/fg_component_requirement_v1.sql).
- Miembros candidatos: 76 ocurrencias de preguntas y 36 ocurrencias SQL, con IDs exactos en el CSV; no frecuencia de uso.

## F22 — Productos, clasificación y unidades

Agrupación conceptual respaldada por fuentes; las asociaciones completas están en `family_membership.csv`. La clasificación de familia no autoriza todos sus miembros.

- Variantes preservadas: ¿Cuántas unidades vendimos por vendedor?; ¿Cuántas unidades y amount source-native registró un ItemCode?; ¿Qué unidades se registraron en un WhsCode?; ¿Qué documentos, líneas, unidades y amount source-native tiene un cliente?
- Parámetros posibles: SKU; propósito; vigencia; producto propio/tercero.
- Semántica y dependencia: Brand UNKNOWN; SellItem no basta para uso externo; no inventar clase desde código.
- Mapping CURRENT: Reference products/UoM; semántica comercial candidata no CURRENT.
- Estado: **REQUIRES_MAPPING**; no significa capability aprobada.
- Fuentes: [TELCHI_DATALAKE_REFERENCE_AND_CROSSWALK_V1.md](../../../../SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/TELCHI_DATALAKE_REFERENCE_AND_CROSSWALK_V1.md); SQL: [item_master_v1.sql](../../../../SrvRestAstroLS_v1/backend/modules/telchi/investigation/sql/current/stock/item_master_v1.sql).
- Miembros candidatos: 151 ocurrencias de preguntas y 8 ocurrencias SQL, con IDs exactos en el CSV; no frecuencia de uso.

## F23 — Estacionalidad, forecast y demanda

Agrupación conceptual respaldada por fuentes; las asociaciones completas están en `family_membership.csv`. La clasificación de familia no autoriza todos sus miembros.

- Variantes preservadas: Are MRP/forecast facts V1 core?; What is forecast coverage?; FORECAST_Y_ESTACIONALIDAD; FORECAST_Y_ESTACIONALIDAD
- Parámetros posibles: SKU; mes; ventana homogénea; censura; forecast método.
- Semántica y dependencia: No equiparar saldo sin filas con cero fuera de cobertura; no comparar año parcial/completo.
- Mapping CURRENT: sales + credit_memo; historia documentada parcial.
- Estado: **REQUIRES_METRIC_DEFINITION**; no significa capability aprobada.
- Fuentes: [product_seasonality_v1_report.md](../../../../SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/product_seasonality_v1_report.md); SQL: [sales_monthly_v1.sql](../../../../SrvRestAstroLS_v1/backend/modules/telchi/investigation/sql/current/seasonality/sales_monthly_v1.sql).
- Miembros candidatos: 24 ocurrencias de preguntas y 55 ocurrencias SQL, con IDs exactos en el CSV; no frecuencia de uso.

## F24 — Usuarios, permisos y operaciones

Agrupación conceptual respaldada por fuentes; las asociaciones completas están en `family_membership.csv`. La clasificación de familia no autoriza todos sus miembros.

- Variantes preservadas: USUARIOS_ROLES_Y_PERMISOS; USUARIOS_ROLES_Y_PERMISOS; USUARIOS_ROLES_Y_PERMISOS; USUARIOS_ROLES_Y_PERMISOS
- Parámetros posibles: usuario; aplicación; operación; fecha.
- Semántica y dependencia: Superusuario/categoría no prueba acción realizada; no se reconstruyen permisos históricos.
- Mapping CURRENT: Reference users/salespersons/warehouses; permisos SAP completos no publicados.
- Estado: **REQUIRES_SOURCE**; no significa capability aprobada.
- Fuentes: [users_roles_authorizations_v1_report.md](../../../../SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/users_roles_authorizations_v1_report.md); SQL: [user_master_v1.sql](../../../../SrvRestAstroLS_v1/backend/modules/telchi/investigation/sql/current/users/user_master_v1.sql).
- Miembros candidatos: 88 ocurrencias de preguntas y 1 ocurrencias SQL, con IDs exactos en el CSV; no frecuencia de uso.

## F25 — Contabilidad, tesorería y administración

Agrupación conceptual respaldada por fuentes; las asociaciones completas están en `family_membership.csv`. La clasificación de familia no autoriza todos sus miembros.

- Variantes preservadas: ¿Los items están contabilizados?; Are payroll/WHT detail V1 core?; Does configured WHT prove actual withholding?; Does SAP contain detailed payroll?
- Parámetros posibles: cuenta; fecha; TransType; moneda; escenario.
- Semántica y dependencia: Reconstrucción/forecast histórico no saldo actual bancario ni nómina detallada.
- Mapping CURRENT: Fuentes históricas GL/treasury; Foundation no publica GL completo.
- Estado: **HISTORICAL_ONLY**; no significa capability aprobada.
- Fuentes: [telchi_financial_position_cash_flow_v1_1_report.md](../../../../SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/telchi_financial_position_cash_flow_v1_1_report.md); SQL: [source_cash_event_sap.sql](../../../../SrvRestAstroLS_v1/backend/modules/telchi/investigation/sql/current/atomic/source_cash_event_sap.sql).
- Miembros candidatos: 83 ocurrencias de preguntas y 236 ocurrencias SQL, con IDs exactos en el CSV; no frecuencia de uso.

## F26 — Proformas, precios y descuentos

Agrupación conceptual respaldada por fuentes; las asociaciones completas están en `family_membership.csv`. La clasificación de familia no autoriza todos sus miembros.

- Variantes preservadas: ¿Cuál fue el descuento promedio por línea?; How is a proforma linked to an invoice?; COTIZACIONES_PROFORMAS; COTIZACIONES_PROFORMAS
- Parámetros posibles: documento/línea; BaseType=23; precio; descuento.
- Semántica y dependencia: Preservar granos y cambio precio; no asumir política comercial desde configuración.
- Mapping CURRENT: sales líneas; QUT1/OQUT completos no acreditados CURRENT.
- Estado: **REQUIRES_SOURCE**; no significa capability aprobada.
- Fuentes: [proforma_pricing_inventory.md](../../../../SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/proforma_pricing_inventory.md); SQL: [sales_v1_linenum.sql](../../../../SrvRestAstroLS_v1/backend/modules/telchi/investigation/sql/current/sales/sales_v1_linenum.sql).
- Miembros candidatos: 27 ocurrencias de preguntas y 2 ocurrencias SQL, con IDs exactos en el CSV; no frecuencia de uso.
