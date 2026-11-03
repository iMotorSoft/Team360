# Reutilización de las seis preguntas de TelchiAI

Las cifras de las sondas corresponden exclusivamente a Foundation CURRENT 1408 observada en esta auditoría. No representan SAP actual ni una nueva validación comercial general.

## A — Últimas ventas registradas

Existe ordenación histórica por DocDate descendente en el discovery del runner directo; aún no es una capability de últimas ventas aprobada.

- Pregunta original: «Dame las últimas ventas registradas»; fixture WhatsApp 20261011 y batería runtime_http.
- SQL histórico: validation/datalake_direct_business_query_validation_v1/runner.py, _discover / validation_closed_day_sample, ORDER BY H.DocDate DESC. Es discovery de fecha de muestra, no respuesta histórica a listado de últimas ventas.
- Prueba CURRENT: foundation_business_cases.json / latest_sales_documents; 10 headers, orden DocDate DESC + DocEntry DESC; última fecha 2026-09-24.
- Semántica: grano documental; puede incluir estados N/Y/C; «registradas» como fecha de ingreso no está demostrado con DocDate.
- Brecha: fijar fecha/estatus/alcance; devolver documento vs línea; filtro por cliente/producto y permisos; no reutilizar silenciosamente el top Quantity.
- Esfuerzo mínimo: adaptación de consulta existente, parámetros acotados y contrato de orden/grano; resolver timestamp si se exige registro cronológico real.
- Recomendación: **READY_CONDITIONAL** para «últimos documentos por fecha documental», no para afirmar últimas ventas en SAP vivo.

## B — Ventas de mayo 2026

Hay SQL mensual ejecutado para agosto, SQL de estacionalidad por producto y un cálculo monetario existente de ventas corporativas. Sus definiciones son distintas.

- Histórico: registry sales_monthly_august, EXACT; cutoff 15/09/2026. Grain DocEntry+LineNum, suma Quantity y LineTotal sin excluir estados; no es neto general.
- Semántica histórica alternativa: sql/current/seasonality/sales_monthly_v1.sql = unidades OINV activas menos ORIN activas por producto/mes; no importe.
- CURRENT: la sonda may_document_amounts agrupa DocTotal por moneda y cancelación. Mayo tiene 36.242 headers BS activos y suma DocTotal **8.761.459,22**; además 2 originales Y y 2 reversas C, cada grupo 740,22.
- La cifra es **importe de facturas activas BS del snapshot**, no neto tras NC, ventas por producto ni cobranza. No se presentó como respuesta empresarial actual.
- Brecha: acordar DocTotal vs LineTotal; moneda/impuestos/descuentos; NC y cancelaciones; completitud requerida. El SQL parametrizable y los datos ya existen.
- Esfuerzo mínimo: escoger contrato monetario respaldado, trasladar filtros/período y conectar un reader limitado; no repetir SAP.
- Recomendación: **REQUIRES_METRIC_DEFINITION** para «ventas» genéricas; **READY_CONDITIONAL** para importe documental con definición explícita.

## C — Calenta

Reference y resultados previos identifican productos; no prueban una única marca, cliente o familia comercial resuelta.

- Evidencia histórica: data/reports/telchi/high_stock_low_sales_commercial_products_v1/commercial_universe.csv y excluded.csv; CALENTA 250 g, 30 g, FORTE y KG interno.
- SQL histórico reutilizable: registry sales_by_item (EXACT); ventas por ItemCode fuente. No se localizó una consulta histórica validada llamada «últimas ventas Calenta».
- CURRENT: productos SAP L02822, L02823, L02877, L03035, L03648, L03649, L03650, L03658; L02877/L03648 SellItem=N, KG. Customers no tuvo matches en esta publicación.
- LIKE %CALENTA% también devuelve INCUBADORA...CALENTADOR y Horno de CALENTAMIENTO. Varios aliases están AMBIGUOUS; no tomar la búsqueda como resolver.
- Mapping material: Atomic source_system=SAP_B1_HANA; Reference=SAP_HANA. Igualdad literal devuelve cero filas; es una brecha real de namespace, no falta de ventas.
- Prueba por SKU exacto de mayo: L02822 1.568 / LineTotal 63.287,96; L02823 3.472 / 24.889,65; L03649 2.125 / 18.487,39; L03658 785 / 43.082,52. Todos BS y N. Las cantidades son nativas y permanecen por SKU; no se suman ni se convierten a peso.
- Brecha: conjunto comercial autorizado, Calenta vs Calenta Forte, excluir internos, namespace canónico; definición de importe neto por producto no resuelta.
- Esfuerzo mínimo: mapping/alias con provenance y filtro de SKUs exactos; reutilizar sales_by_item. No nuevo discovery SAP.
- Recomendación: **REQUIRES_MAPPING** para mención libre; **READY_CONDITIONAL** para SKU explícito y métrica fuente.

## D — Último mes disponible

El census histórico ya consulta MIN/MAX; la fecha máxima observada en CURRENT es reproducible, pero no acredita mes completo.

- SQL histórico: datalake_2026_census_and_coverage_reconciliation_v1/runner.py:529, MIN/MAX doc_date; resultados de census preservados en evidencia externa.
- CURRENT: first_date 2022-03-31, last_date 2026-09-24, 330.443 headers. Mes con datos más reciente: septiembre 2026; agosto alcanza 31/08.
- No afirmar historia completa desde 2022, ni último mes completo por encontrar el día 31. Publication data_as_of, component source_as_of, max DocDate y fecha de commit son diferentes.
- Brecha: metadata autorizada por entidad/métrica y certificación de completitud. TelchiAI sólo guarda latest_available_month, sin resolverlo.
- Esfuerzo mínimo: exponer metadata de cobertura existente con entidad/métrica y estado de completitud; reader pinned, sin cambiar CURRENT.
- Recomendación: **READY_CONDITIONAL** para último mes con registros; **UNRESOLVED** para último mes empresarial completo.

## E — Importes y cantidades

El registro directo ya devuelve ambas columnas; la limitación es semántica y contractual, además del catálogo del asistente.

- SQL/evidencia: sales_by_item, sales_by_customer, sales_daily_aggregate, sales_monthly_august, sales_ytd y sales_top_items; hashes EXACT históricos y reproducción CURRENT.
- Source-native LineTotal no es DocTotal ni neto comercial. Los agrupados de cliente/período pueden mezclar unidades; un SUM Quantity global es inadmisible como magnitud física.
- Foundation conserva importes y cantidades fuente, pero sales_line no incluye un factor documental/UoM completo. Reference sales_uom_id no sustituye esa evidencia.
- Esfuerzo mínimo: dos métricas con contratos separados, cantidad por SKU/UoM validada y moneda; no agregar métricas desde el LLM. Neto por producto necesita definición adicional.
- Recomendación: **READY_CONDITIONAL** para ambas medidas fuente por SKU; **REQUIRES_METRIC_DEFINITION** para agregados generales.

## F — Productos más vendidos

Hay varias definiciones históricas que no deben convertirse en un único ranking sin elegir qué significa «más».

- Variante source-native: registry sales_top_items, EXACT histórico, 2026-01-01..2026-09-15; Quantity por ItemCode, sin excluir cancelaciones/NC. Reproducida en CURRENT con mismo scope SQL.
- Capability actual: messaging_sales_query.SQL_TEMPLATE y assistant sales.source_top_items, top 10 fijo 01/01..16/09 exclusivo. No permite filtros generales, importe neto ni período parametrizable.
- Variante net units mensual: seasonality/sales_monthly_v1.sql y product_seasonality_v1_report; facturas activas menos NC activas; cantidades por producto y período.
- Variante comercial vs uso interno: high_stock_low_sales_commercial_products_v1 y semántica comercial de producto; no usar candidate sidecar como CURRENT.
- Variante por importe: SQL histórico tiene LineTotal; requiere distinguir importe de línea de neto producto y encabezado.
- Brecha: criterio de ranking, unidades, universo comercial, cancelaciones/NC, período, desempate y mappings.
- Esfuerzo mínimo: parametrizar familia existente después de fijar métrica/universo; validar resultados, no diseñar motor paralelo.
- Recomendación: **REQUIRES_METRIC_DEFINITION** para «más vendidos» genérico. El ranking documental fijo ya existe, con sus límites.
