# Semántica empresarial recuperada

Los estados se aplican a cada definición y su alcance, no a todo el dominio. Historicidad, paridad de valores y aptitud productiva son garantías distintas.

## Ventas, documentos, importes y fechas

El conocimiento monetario existente distingue cabecera, línea y notas de crédito; no debe reinterpretarse para ampliar el catálogo.

| Definición | Estado | Evidencia / restricción |
| --- | --- | --- |
| DocEntry es grano financiero de factura; LineNum es grano de detalle | VALIDATED histórico; CURRENT campos verificados | DECISIONS TELCHI-DEC-007; FINANCIAL_REPORTING_CONTRACT; registry sales_exact_document/lines |
| DocTotal de cabecera no equivale a suma LineTotal | VALIDATED como distinción | DECISIONS; executive_sales.py:20 y 42; impuestos, descuentos y redondeos requieren base explícita |
| Neto documental = facturas válidas − NC válidas bajo reglas del contrato | CONDITIONAL | FINANCIAL_REPORTING_CONTRACT; corporate_sales_by_salesperson sólo BS, categoría corporativa y SlpCode |
| Neto comercial general por producto | UNRESOLVED | PRODUCT_COMMERCIAL_SEMANTICS_V1.md:66: NET_PRODUCT_AMOUNT_UNRESOLVED; no asignación de descuento cabecera demostrada |
| CANCELED N / Y / C = activo / original cancelado / reversa | VALIDATED histórico | query_catalog.md §11; cancelaciones y NC preservadas en CURRENT |
| NC DocTotal raw positivo; signo negativo para cálculo comercial | VALIDATED histórico | DECISIONS TELCHI-DEC-008; no negar indiscriminadamente todos los importes fuente |
| DocDate es fecha documental | VALIDATED | fecha de venta documental; no timestamp de ingreso ni ingestión |
| UpdateDate demuestra exactamente cuándo se anuló | REJECTED como equivalencia general | query_catalog dice última actualización; lifecycle temporal exige reconstrucción/estado; una actualización puede tener otros motivos |
| Último mes disponible = mes de MAX(doc_date) | CONDITIONAL | prueba sales_coverage/sales_months da septiembre 2026 hasta 24/09; no garantiza mes completo |
| Último mes completo | UNRESOLVED | agosto tiene fechas hasta 31/08; presencia de esas filas no acredita ausencia de faltantes ni cierre empresarial |
| Canal vendedor equivale a canal de cada venta | REJECTED como regla universal | CORPORATE_SALES_FINAL_REPORT y CHANNEL_RULE_FINAL_REPORT separan categoría de vendedor y clasificación transaccional |

## Cantidades y productos

La fidelidad source-native no basta para convertir cantidades documentales en unidades físicas comparables ni para comparar productos.

| Definición | Estado | Evidencia / restricción |
| --- | --- | --- |
| SUM Quantity por SKU conserva cantidad fuente | CONDITIONAL | direct registry sales_by_item; CURRENT reproducción; no acredita factor/UoM documental |
| SUM Quantity por almacén, cliente o período multi-SKU como una magnitud | REJECTED | metric/uom contracts; kg, litros, unidades y paquetes no se suman |
| Ranking cross-SKU por Quantity documental | CONDITIONAL sólo como orden documental explícito; REJECTED como ranking físico/comercial universal | messaging_sales_query y assistant README no certifican UoM comparables ni venta neta |
| Conversión comercial requiere factor de línea verificado hacia inventario del mismo SKU | VALIDATED como invariante | PRODUCT_COMMERCIAL_SEMANTICS_V1.md:38–50; master o BaseEntry no sustituyen prueba de factor |
| Conversión kg/L sin densidad | REJECTED | MASS/VOLUME incompatible; no densidad inferida |
| Calenta es un único cliente o marca confirmada | UNRESOLVED / sin evidencia suficiente | productos SAP identificados, customers sin matches; brand UNKNOWN según contrato, alias AMBIGUOUS en varias presentaciones |
| Calenta tiene candidatos de producto SAP | VALIDATED como localización | L02822, L02823, L02877, L03035, L03648, L03649, L03650, L03658; dos variantes KG no vendibles |
| LIKE %CALENTA% resuelve familia comercial | REJECTED | también devuelve CALENTADOR y CALENTAMIENTO; no es resolver semántico |
| Namespace fuente es igual en Atomic y Reference | REJECTED | Atomic SAP_B1_HANA vs Reference SAP_HANA; join literal no recupera ventas Calenta. Consulta SKU exacto sí devuelve cuatro productos en mayo |
| Clasificación comercial temporal y sidecars UoM están en CURRENT | UNRESOLVED / no acreditado | manifest CURRENT tiene 8 componentes lógicos y no publica product_commercial_semantics/temporal; no usar candidate como CURRENT |

## Stock, compras y abastecimiento

Las magnitudes y las fechas mantienen su origen; equivalencias entre hechos comerciales y físicos requieren lineage probado.

- **VALIDATED / alcance actual:** OnHand, IsCommited y OnOrder son posiciones distintas. Disponible = OnHand − IsCommited conserva negativos; OnOrder no se agrega como existencia. OITW es as_of, no stock histórico.
- **CONDITIONAL:** stock agregado sólo entre unidades compatibles; snapshot y source_as_of obligatorios. Stock histórico derivado requiere OINM y baseline coherente.
- **VALIDATED histórico:** ordenado, recibido y facturado se unen por BaseType/BaseEntry/BaseLine. NumPerMsr debe ser explícito, finito y positivo. Multi-recepción y multi-almacén conservan grain de línea.
- **REJECTED:** base_ref solo identifica un documento globalmente; caso 262000261 colisiona entre OC/GR/AP. Requiere trans_type, doc_line_num, ItemCode y corroboración proveedor.
- **CONDITIONAL:** AP directa no demuestra no recepción física; TRUE_INVOICED_WITHOUT_RECEIPT es clasificación derivada con alcance/cobertura, no fact universal.
- **CONDITIONAL:** lead time documental es diferencia de fechas; no tiempo físico certificado ni estado de importación/aduana. U_TIPOCOMPRA clasifica origen; Country solo no basta.

## Crédito, cobranzas, producción y operaciones

Los reportes anteriores conservan respuestas defendibles en su universo; la publicación actual no demuestra toda la historia ni una integración de esas operaciones en el asistente.

- **VALIDATED histórico:** OITR/ITR1 es autoridad settlement Telchi; RCT2 no fue autoridad suficiente en aquel baseline. Reconciliado no equivale a cobrado en efectivo. No extrapolar esto a cualquier SAP.
- **CONDITIONAL:** receivable_settlement_status publica saldo/estado; collection_method_fact tiene componentes por medio de pago, no un pago único por fila. Pago, aplicación, reducción económica y deuda son métricas distintas.
- **UNRESOLVED:** reproducir cualquier deuda histórica al día de venta desde solo saldo publicado actual; necesita eventos, cancelaciones y fechas efectivos.
- **REJECTED:** límite configurado / vendedor / superusuario prueba aprobación o acción operacional. Falta historia de autorización.
- **VALIDATED histórico:** BOM es receta/plan; OWOR/IGE1/IGN1 y OINM soportan orden, consumo y salida reales. BOM vigente no demuestra consumo real histórico.
- **CONDITIONAL:** demanda equivalente, cobertura y capacidad necesitan factores y unidades verificados, dependencias entre componentes y validez temporal; consumo interno no se transforma en venta externa.
- **HISTORICAL:** cifras de tesorería, contabilidad, nómina, forecasting y backtests; no saldos bancarios actuales ni resultados nuevos de modelos.

Fuentes canónicas: [DECISIONS](../../../../SrvRestAstroLS_v1/backend/modules/telchi/investigation/DECISIONS.md), [contrato financiero](../../../../SrvRestAstroLS_v1/backend/modules/telchi/investigation/FINANCIAL_REPORTING_CONTRACT.md), [reglas SAP](../../../../SrvRestAstroLS_v1/backend/modules/telchi/investigation/validation/sap_knowledge_inventory_v1/sap_business_rules_inventory.csv), [contrato compras](../../../../SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/TELCHI_PURCHASING_ANALYTICAL_CONTRACT_V1.md), [semántica productos](../../../../SrvRestAstroLS_v1/backend/modules/telchi/datalake/PRODUCT_COMMERCIAL_SEMANTICS_V1.md).
