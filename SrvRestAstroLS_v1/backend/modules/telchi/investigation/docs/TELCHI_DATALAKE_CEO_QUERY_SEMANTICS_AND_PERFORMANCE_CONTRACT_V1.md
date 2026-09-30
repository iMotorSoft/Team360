# TELCHI — CEO Query Semantics & Performance Contract V1

## Gate y alcance

`TELCHI_DATALAKE_CEO_QUERY_SEMANTICS_AND_PERFORMANCE_CONTRACT_V1` cierra el
contrato investigativo que relaciona preguntas ejecutivas, semántica de negocio,
read models futuros, frescura, autorización, drill-down y presupuesto de
latencia.

Este gate **no construye** `atomic`, `business`, `current`, chat runtime,
semantic planner productivo ni scheduler de ingesta. No accede SAP/HANA y no
modifica DuckLake foundation. Todos los outputs son catálogos CSV/JSON locales
bajo `validation/datalake_ceo_query_semantics_and_performance_contract_v1/`.

La evidencia de entrada se toma de los gates históricos ya aprobados:

- inventario histórico y mirror legacy de 696 archivos;
- modelo canónico, diseño físico, reference/crosswalk;
- DuckLake PostgreSQL 18 foundation;
- baseline de entity resolution `7.959 ms` y DuckLake warm query
  `P95=10.0535 ms`.

La fuente legacy informa casos y fórmulas históricas, pero no es autoridad
semántica automática.

## Resultado ejecutivo

El contrato queda listo para revisión con estado **DEGRADED**, no FAIL. La
cobertura estructural de P0 está completa, pero el siguiente gate debe resolver
las ambigüedades financieras y operativas antes de materializar hechos.

```text
GATE=TELCHI_DATALAKE_CEO_QUERY_SEMANTICS_AND_PERFORMANCE_CONTRACT_V1
CEO_QUERY_FAMILIES=10
CEO_QUERIES_TOTAL=74
CEO_QUERIES_P0=15
CEO_QUERIES_P1=40
CEO_QUERIES_P2=19
METRICS_TOTAL=32
METRICS_CONFIRMED=3
METRICS_PROVISIONAL=19
METRICS_SEMANTIC_GAP=10
DIMENSIONS_TOTAL=15
AMBIGUITIES_TOTAL=15
AMBIGUITIES_WITH_DEFAULT=9
AMBIGUITIES_REQUIRING_CLARIFICATION=9
P0_WITH_SEMANTIC_PLAN=15/15
P0_WITH_DATA_PRODUCT=15/15
P0_WITH_LATENCY_CLASS=15/15
P0_WITH_FRESHNESS_CLASS=15/15
P0_WITH_DRILLDOWN=15/15
ENTITY_RESOLUTION_P95_MS=7.959
DUCKLAKE_WARM_QUERY_P95_MS=10.0535
SEMANTIC_CATALOG_LOOKUP_P95_MS=0.000106
PERFORMANCE_CLASS_A_TARGET_P95_MS=100
PERFORMANCE_CLASS_B_TARGET_P95_MS=300
PERFORMANCE_CLASS_C_TARGET_P95_MS=750
CASH_VS_CREDIT_SEMANTICS=SEMANTIC_GAP
NET_SALES_SEMANTICS=SEMANTIC_GAP
CURRENT_RECEIVABLE_SEMANTICS=PROVISIONAL
OVERDUE_RECEIVABLE_SEMANTICS=PROVISIONAL
STOCK_DEFAULT_SEMANTICS=PROVISIONAL
PRODUCTION_COUNT_DEFAULT_SEMANTICS=SEMANTIC_GAP
UOM_CONTRACT_READY=YES
CURRENCY_CONTRACT_READY=YES
DATE_SEMANTICS_READY=YES
SECURITY_SCOPE_CONTRACT_READY=YES
DRILLDOWN_CONTRACT_READY=YES
DEV_PROD_LOGICAL_NAMES_IDENTICAL=YES
POSTGRES_CATALOG_DATABASE=team360_telchi_ducklake
POSTGRES_RUNTIME_ROLE=team360_telchi_ducklake
SAP_ACCESSED=NO
SAP_WRITE_COUNT=0
ATOMIC_TABLES_CREATED=0
BUSINESS_TABLES_CREATED=0
CURRENT_TABLES_CREATED=0
CEO_QUERY_CONTRACT_READY=YES
ATOMIC_REQUIREMENTS_DERIVED=YES
ATOMIC_BUILD_PRIORITY_DEFINED=YES
TELCHI_DATALAKE_CEO_QUERY_SEMANTICS_AND_PERFORMANCE_CONTRACT_V1_DEGRADED
```

La degradación es explícita por `CASH_VS_CREDIT_SEMANTIC_GAP`, definición de
`NET_SALES`, default de conteo de producción y políticas de costo/FX todavía no
confirmadas.

## Contrato semántico

El semantic plan es un contrato reutilizable, no SQL ni un conjunto cerrado de
intents. Sus campos son:

```text
domain
metrics[]
entities[]
dimensions[]
filters[]
time_range
comparison
scope
requested_unit
currency
grain
ranking
limit
drilldown_level
freshness_requirement
ambiguities[]
```

La ejecución futura preserva este orden:

```text
identity
  -> authorization context
  -> entity resolution within scope
  -> semantic plan
  -> authorized query
  -> current/business read model
  -> DuckDB
  -> answer
```

La autorización se aplica antes de retrieval. Un CEO y un warehouse manager
pueden compartir el plan semántico, pero no necesariamente el mismo scope. No
se debe generar una respuesta completa y ocultarla después.

Los términos sin período usan `ASK_OR_CONTEXT`; nunca se asume silenciosamente
“hoy”. `hoy`, `ayer`, MTD, YTD y períodos equivalentes se interpretan con el
timezone empresarial Telchi configurado, nunca con el timezone implícito del
servidor. El contexto conversacional futuro podrá heredar entidad, métricas,
filtros y período, pero su implementación queda fuera de este gate.

## Cobertura CEO

El catálogo contiene 74 preguntas business-realistic en diez familias:

- SALES: ventas por período, sucursal, cliente, producto, vendedor, familia,
  descuentos, notas de crédito, rankings y comparaciones;
- STOCK: `ON_HAND`, `AVAILABLE`, `COMMITTED`, `ON_ORDER`, mínimos, exceso,
  productos L, falta de ventas y stock por warehouse/sucursal;
- CREDIT: total, corriente, vencido, aging, días, límites, sobre-límite,
  evolución y saldos históricos as-of;
- CASH: cobros, cliente, caja, sucursal, último cobro y medios de pago;
- PRODUCTION: órdenes, cierres, recibos de terminados, consumos y desviaciones;
- PURCHASES: abiertas, pendientes, proveedor, recepciones y lead time;
- PROFITABILITY: margen por producto, línea y sucursal, pendiente de política
  de costo;
- CUSTOMER: recencia, nuevos clientes, ticket y afinidad producto-cliente;
- PRODUCT: universo `is_telchi_l_product`, rotación, UoM y costo;
- BRANCH: ventas, stock, mappings y deuda por sucursal cuando sea válido.

Las 15 preguntas P0 tienen semantic plan, data product, clase de latencia,
clase de frescura, scope requerido y cadena de drill-down. Ninguna requiere
aritmética del LLM, lectura directa de legacy ni query SAP live.

## Métricas y gaps semánticos

El metric catalog contiene 32 métricas, cada una con definición, fórmula lógica,
grain requerido, dimensiones permitidas, moneda/unidad, semántica temporal,
null/sign semantics, reglas de inclusión/exclusión, autoridad de reconciliación,
estado y versión (`METRIC_ID@1`). Entre otras, distingue explícitamente:

- `GROSS_SALES`, `NET_SALES` y `NET_SALES_AFTER_CREDIT_NOTES`;
- `QUANTITY_SOLD` de `DOCUMENT_COUNT`;
- `SALE_PAYMENT_TERM` conceptual de `PAYMENT_RECEIVED`;
- `ON_HAND`, `COMMITTED`, `ON_ORDER` y `AVAILABLE`;
- `TOTAL_RECEIVABLE`, `CURRENT_RECEIVABLE`, `OVERDUE_RECEIVABLE`,
  `DAYS_OVERDUE`, `CREDIT_LIMIT` y `OVER_LIMIT`;
- órdenes, recibos y consumos de producción como hechos distintos.

### Cash versus credit

Queda `SEMANTIC_GAP`. No se copió la fórmula legacy. La clasificación futura debe
separar venta con condición de pago de dinero recibido y de saldo abierto. Antes
de confirmarla se debe reconciliar documento, condición de pago, receipt,
reconciliation, nota de crédito y saldo abierto con la autoridad SAP moderna.

### Venta neta

Queda `SEMANTIC_GAP` hasta fijar con SAP si el default ejecutivo es con o sin
IVA, cómo entran descuentos de línea/documento, cancelaciones, devoluciones,
notas de crédito, monedas y tipos de documento.

### Crédito

`CURRENT_RECEIVABLE` y `OVERDUE_RECEIVABLE` quedan `PROVISIONAL`: la
reconstrucción SAP moderna validada es la autoridad conceptual, pero el read
model aún no existe. “Deuda hoy” no se sustituye por `OCRD` para responder una
fecha histórica. Para as-of se exige snapshot de negocio o reconstrucción que
incluya invoice, credit note, payment, reconciliation, open balance y due date.

### Stock y unidades

El default propuesto `stock -> ON_HAND` queda `PROVISIONAL`; cuando sea útil la
respuesta puede mostrar también `AVAILABLE`, pero no se deben tratar como
sinónimos. La pregunta de Creolina en Saavedra exige resolver producto,
warehouse/branch, stock, autorización, agregación y conversión UoM.

El UoM contract distingue document, inventory, sales y purchase unit, tipo y
unidad canónica, factor, fuente, confianza y vigencia. El LLM no puede inventar
conversiones; `1 unidad de 500 mL` no equivale automáticamente a `1 litro`.

### Producción, costo, moneda y tax

“¿Cuántas producciones?” exige aclarar si son órdenes creadas, cerradas,
receipts, unidades terminadas o runs. El default queda `SEMANTIC_GAP`.

Margen y rentabilidad quedan sujetos a una política de costo: actual,
historical, document, moving average, production o last purchase cost. No se
elige una base por conveniencia.

La currency contract conserva document/local/system/analytical currency y no
contiene FX hardcoded. La tasa histórica requiere fuente aprobada. Cada métrica
financiera debe declarar tax included/excluded/not applicable y signos
canónicos para invoice, credit note, payment, return, inventory y producción.

## Data products y performance

El routing contract define diez destinos futuros, priorizando current/business
read models sobre reconstrucción atomic:

- `current.stock_current`, grain `product × warehouse`;
- `business.sales_flow`, grain línea comercial canónica;
- `business.production_flow`, hechos separados de orden/receipt/consumo;
- `business.inventory_flow`;
- `current.customer_credit_current`, grain customer y detalle customer ×
  document;
- `business.customer_credit_history`, customer × as-of;
- `business.cash_flow`;
- `current.purchase_open`, purchase document line;
- `business.purchase_flow`;
- `reference.* / crosswalk.*`.

Clases de data-query latency, sin LLM, UI, red ni streaming:

| Clase | Objetivo warm P95 | Ejemplos |
|---|---:|---|
| A | <= 100 ms | stock actual, deuda, top deudores, abiertas |
| B | <= 300 ms | ventas por período/dimensión, producción |
| C | <= 750 ms | comparaciones, multi-dimensión, margen |
| D | no sub-second | as-of complejo, evidencia y análisis profundo |

La fundación aporta `DuckLake ATTACH cold P95≈170 ms`, por lo que ATTACH no puede
ocurrir por pregunta. Las conexiones deben reutilizarse con seguridad.
El warm query heredado es `P95=10.0535 ms`; entity resolution aprobado es
`P95=7.959 ms` y lookup del catálogo semántico medido en memoria es
`P95=0.000116 ms`.

La validación también conserva probes readonly directos sobre Parquet. El probe
raw de alias tiene outliers de lectura de archivo y **no reemplaza** el baseline
del resolver optimizado; esta diferencia queda registrada para no presentar un
scan de archivo como la performance del futuro resolver.

Frescura: `NEAR_REALTIME` para stock/ventas/producción actuales, `INTRADAY` para
crédito/cash/compras abiertas, `DAILY` para historia/margen y `HISTORICAL` para
snapshots as-of. Toda respuesta future current debe mostrar `data_as_of` y
marcarse stale si excede su SLA.

## Explainability, trace y response shape

Las respuestas futuras se expresan como `EXECUTIVE_SHORT`, `EXECUTIVE_TABLE`,
`EXECUTIVE_COMPARISON`, `DRILLDOWN` o `EVIDENCE`. Primero va la respuesta
 directa, luego desglose y observación breve; SQL y detalles técnicos sólo bajo
pedido.

El trace interno requerido contiene `query_id`, `semantic_plan_hash`, versiones
de métricas/datasets, DuckLake snapshot, `data_as_of`, authorization scope,
`execution_ms` y `row_count`. Las métricas se versionan; cambiar una definición
no puede cambiar silenciosamente la historia.

La cadena de evidencia baja de resumen a dimensión, documento, línea,
payment/reconciliation y fuente SAP. Cada drill-down revalida autorización y
as-of.

## Legacy baseline

`legacy_semantic_comparison.csv` revisa especialmente `saleProduct`,
`saleSB1Product`, `ncB1Product`, `movProduct`, `movProductSB1`, `cash`,
`cuentasxCobrar`, `productTransform`, `purchase` y `ProductSaleCostDay`.
Registra fields/grain, fórmula/patrones, problemas conocidos y data product
futuro. El patrón Dask/per-request y los joins legacy no se trasladan al
runtime nuevo.

## Atomic requirements derivados — no construir

El análisis deriva 13 verdades potenciales, ordenadas por cobertura,
dependencias, certeza semántica y valor de performance:

1. `atomic.sales_document`
2. `atomic.sales_line`
3. `atomic.credit_note`
4. `atomic.inventory_movement`
5. `atomic.inventory_snapshot`
6. `atomic.payment`
7. `atomic.reconciliation`
8. `atomic.production_order`
9. `atomic.production_component`
10. `atomic.production_receipt`
11. `atomic.purchase_order`
12. `atomic.purchase_line`
13. `atomic.cost_observation`

Son requisitos de diseño para el siguiente gate, no tablas creadas. El orden
privilegia primero ventas/crédito/inventario y deja costo después de resolver su
semántica. La existencia de una entrada en esta lista no autoriza comenzar
`Atomic Build`.

## Artefactos y validación reproducible

Código y tests:

- `validation/datalake_ceo_query_semantics_and_performance_contract_v1/build_outputs.py`
- `validation/datalake_ceo_query_semantics_and_performance_contract_v1/test_contract.py`

Outputs:

- `ceo_query_catalog.csv`
- `metric_catalog.csv`
- `dimension_catalog.csv`
- `semantic_ambiguity_catalog.csv`
- `query_data_product_routing.csv`
- `performance_classes.csv`
- `freshness_contract.csv`
- `uom_contract.csv`
- `currency_contract.csv`
- `drilldown_contract.csv`
- `legacy_semantic_comparison.csv`
- `atomic_requirements.csv`
- `business_read_model_requirements.csv`
- `benchmark_baseline.csv`
- `semantic_plan_contract.json`
- `summary.json`

Validación ejecutada:

```text
uv run pytest modules/telchi/investigation/validation/datalake_ceo_query_semantics_and_performance_contract_v1/test_contract.py -q
7 passed
```

El builder sólo genera CSV/JSON de investigación. No crea Parquet ni tablas
`atomic`, `business` o `current`; `SAP_WRITE_COUNT=0` y `SAP_ACCESSED=NO`.

## STOP AND REVIEW

`CEO_QUERY_CONTRACT_READY=YES`, pero el resultado es
`TELCHI_DATALAKE_CEO_QUERY_SEMANTICS_AND_PERFORMANCE_CONTRACT_V1_DEGRADED`.
Debe revisarse con negocio/SAP la clasificación contado-crédito, net sales,
producción, FX, tax y cost basis. Hasta esa revisión:

- no comenzar atomic;
- no integrar chat;
- no crear read models productivos;
- no acceder SAP salvo una ambigüedad autorizada y read-only;
- conservar esta lista como contrato de decisión para el siguiente gate.
