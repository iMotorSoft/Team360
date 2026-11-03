# Foundation Query Activation V1

Incremento DEVELOPMENT en Telchi. Selección y paridad técnica acreditadas; activación empresarial nueva bloqueada por permisos explícitamente limitados. No se declara BUSINESS_PASS ni RUNTIME_PASS nuevo.

## Resultado ejecutivo

La evidencia existente permite implementar hechos documentales sin inventar métricas. El permiso real no autoriza exponerlos al piloto; esa frontera se mantuvo cerrada.

- Rama `feature/console-backend-core`; HEAD inicial `09d2ec715a31bb88574d734eacb9f437f008624e` conservado.
- Foundation CURRENT `foundation_afd08d9eca6a725be53cdc3f9d5709c9`, snapshot `1408`; sin promoción, SAP, DDL/DML empresarial ni modificaciones de Parquet.
- Implementadas `sales.latest_documents` y `sales.coverage`: SQL parametrizado, Foundation pinned, worker acotado y State Engine existente. Véase [contratos](SALES_QUERY_CONTRACTS.md).
- Grant existente real: `telchi.sales.source_quantity.read.v1`. Descripción PostgreSQL: **Only** `telchi.sales_top_items.source_quantity.20260101_20260915.v1`; excluye **other capabilities**.
- No hay ninguna nueva candidata P0 autorizada al piloto. Habilitar coverage bajo ese grant sería una ampliación prohibida, aunque sólo entregue fechas. Véase [preflight read-only](preflight_and_trace.json).
- Dos paridades SQL independientes PASS; HTTP real nuevo muestra DENIED sin ejecución, no respuestas empresariales nuevas. Ranking previo devuelve datos reales.
- Regresión HTTP inicial: ocho CONTRACT_ERROR de continuidad. Se preservó la evidencia, se corrigió el contrato del prompt sin cambiar modelo/guard y se repitieron los 32 turnos: cero ERROR. No se usa HTTP 200 como criterio.

## Selección y bloqueos P0

Las referencias discovery/census no se presentan como nuevas operaciones EXACT del registro de treinta.

| Operación | Evidencia histórica | SQL Foundation | Semántica | Implementación | HTTP real |
| --- | --- | --- | --- | --- | --- |
| Últimas facturas activas | HS-e24b48c12f48051f9e; HQ-703df2860ba482327d / HS-604de2e2e229ed2525; sonda latest_sales_documents | PASS independiente | PASS documental DocDate; no timestamp de registro | PASS técnica | BLOCKED nuevo grant |
| Ventas por período | HQ-cf162105a169e5ec63 / HS-7b42e2b4867a054e81 | Histórico VALIDATED_SQL; mayo DocTotal sondeo, no nuevo total neto | GAP neto genérico; NC/impuestos/descuento por definir | BLOCKED métrica y grant | BLOCKED semántica |
| Cobertura temporal | HS-6e541cc586d91546bc; HQ-db9e682ef8aa01cdd1 | PASS independiente | PASS facturas activas; GAP mes completo | PASS técnica | BLOCKED nuevo grant |
| Calenta | HQ-fbdda4165b64b30810 / HS-56822a0ce444d328eb | PASS histórico SKU exacto; GAP join de namespaces | GAP familia/aliases/UoM | BLOCKED mapping y grant | BLOCKED mapping |
| Más vendidos | HQ-75ddaf55d0ace2fbab / HS-99232ce7f29843ba20 | V1 preservado | Sólo ranking Quantity documental fijo; no ranking físico | EXISTING V1 | PASS compatibilidad; no nueva operación |

## Matriz de treinta operaciones

Se conserva la clasificación original 9/8/13, preguntas, SQL y referencias. Cada fila del CSV agrega parámetros, grano del inventario, riesgo y aptitud; READY_FOUNDATION nunca se convirtió en autorización.

| Operación | Pregunta ID | SQL ID | Clase histórica | Definición fuente | Aptitud TelchiAI |
| --- | --- | --- | --- | --- | --- |
| sales_exact_document | HQ-703df2860ba482327d | HS-604de2e2e229ed2525 | READY_FOUNDATION | Header y líneas con los campos source-native preservados en Atomic; no se excluyen estados. | BLOCKED grant |
| sales_document_lines | HQ-50e9a6c21f62dcb2aa | HS-cd400889c3affbbb08 | READY_FOUNDATION | LineNum, ItemCode, WhsCode, Quantity y amount/status preservados. | BLOCKED grant |
| sales_by_item | HQ-fbdda4165b64b30810 | HS-56822a0ce444d328eb | READY_CONDITIONAL | Bounded item aggregation; amount es suma de LineTotal, no una métrica reinterpretada. | BLOCKED grant |
| sales_by_warehouse | HQ-84b2d39c0617baf9d4 | HS-dfa3f96f0991625598 | REQUIRES_METRIC_DEFINITION | Warehouse es WhsCode source-native; no se interpreta como branch. | BLOCKED grant |
| sales_by_customer | HQ-48f1c1306b08e22317 | HS-0abfbc6651edb4e957 | REQUIRES_METRIC_DEFINITION | CardCode exacto; no se cambia a nombre o segmento. | BLOCKED grant |
| sales_daily_aggregate | HQ-c001c5fe205bf070f0 | HS-e3ccaa468d109046f8 | REQUIRES_METRIC_DEFINITION | Daily complete-period source-native aggregate. | BLOCKED grant |
| sales_monthly_august | HQ-cf162105a169e5ec63 | HS-7b42e2b4867a054e81 | REQUIRES_METRIC_DEFINITION | Month closed before cutoff; quantity and LineTotal remain source-native. | BLOCKED grant |
| sales_ytd | HQ-e35670c9ccbdc0b6bd | HS-772e4b009f4d3a232d | REQUIRES_METRIC_DEFINITION | YTD inclusive through 2026-09-15; every line has DocEntry/LineNum lineage. | BLOCKED grant |
| sales_top_items | HQ-75ddaf55d0ace2fbab | HS-99232ce7f29843ba20 | REQUIRES_METRIC_DEFINITION | Deterministic ranking by source-native Quantity only; no interpretation as best products. | Fixed V1 only |
| sales_cancellation_status | HQ-ca842068aad64be663 | HS-d6f311ad8f755775b6 | READY_FOUNDATION | selected non-open/cancelled document | BLOCKED grant |
| oinm_exact_movement | HQ-4eee9271074818f2ad | HS-c7714b0d4ee41b3ea6 | READY_FOUNDATION | All relevant source-native fields available in the discovered OINM schema. | BLOCKED grant |
| oinm_item_history | HQ-398575353a0991fc91 | HS-8805104daa29a8158e | READY_CONDITIONAL | Rows, InQty, OutQty through cutoff. | BLOCKED grant |
| oinm_warehouse_history | HQ-acfbe087a9ffe9b1dc | HS-79a723bdce1d9e07a4 | REQUIRES_METRIC_DEFINITION | Rows and quantities by source-native Warehouse. | BLOCKED grant |
| oinm_item_warehouse | HQ-4feb9376f8484b36a8 | HS-8997d6db17fbc1c600 | READY_CONDITIONAL | Row count, InQty and OutQty without treating them as sales. | BLOCKED grant |
| oinm_trans_type | HQ-d2a176bff2b051907e | HS-149b93eb353c525301 | REQUIRES_METRIC_DEFINITION | Rows and InQty/OutQty by source-native TransType. | BLOCKED grant |
| oinm_daily_aggregate | HQ-97fd2a5c4f529ff1fb | HS-0df6ea9a5501b535b9 | REQUIRES_METRIC_DEFINITION | Rows, InQty and OutQty on an exact day. | BLOCKED grant |
| oinm_monthly_august | HQ-77433e8c9955cc7471 | HS-34d728708571a14716 | REQUIRES_METRIC_DEFINITION | Closed monthly movement aggregate. | BLOCKED grant |
| oinm_ytd | HQ-fc1d0e535c45eee260 | HS-667dcef5f6802ee4e1 | REQUIRES_METRIC_DEFINITION | Inclusive YTD row count and quantities. | BLOCKED grant |
| oinm_multi_trans_item | HQ-e1c975e1e470cea773 | HS-6d1c008d4c28fe41c7 | READY_CONDITIONAL | Rows and quantities grouped by TransType for one item. | BLOCKED grant |
| oinm_source_drilldown | HQ-b9e7ee69bcf0cd4c30 | HS-1495b9623c1e8d2b21 | READY_FOUNDATION | Bounded multi-row reread keyed by TransNum+TransSeq; no fuzzy linkage. | BLOCKED grant |
| cross_item_sales_movements | HQ-8330c3cf5288e34538 | HS-a685ccf8a9e41310da|HS-bbc2c22151050ae367 | READY_CONDITIONAL | Two independent source-native result sets in one multi-source question; no equivalence/causality claim. | BLOCKED grant |
| cross_item_warehouse_activity | HQ-933799a75b5cdb002b | HS-4a9ccbaaf74cbd571d|HS-c2a5fa946e0d3c3d35 | READY_CONDITIONAL | Sales and OINM are returned as separate source-native sets. | BLOCKED grant |
| cross_high_sales_item_movement_context | HQ-529664f7b37b7434d0 | HS-d94904e924ed157f3c|HS-e9d4cacc3bf18d18ef | READY_CONDITIONAL | A top-sales candidate is used only as a deterministic item selection; no causal inference. | BLOCKED grant |
| cross_warehouse_activity | HQ-8adb73dcd3b2f0ac4d | HS-c1313155522b7b2377|HS-d8c4c4209baa7b54e9 | REQUIRES_METRIC_DEFINITION | WhsCode and Warehouse are compared only as separately named source dimensions; no branch conversion. | BLOCKED grant |
| cross_item_warehouse_activity_control | HQ-98b5a506ec5896c3a5 | HS-f88d4b78711fd48fb1|HS-fff3a2ae241bb922a3 | READY_CONDITIONAL | Replacement for unavailable explicit document linkage; source-native dimensions only. | BLOCKED grant |
| oitw_exact_item_warehouse | HQ-9e2d8ca7260865aeb8 | HS-d3befb78af2c57fe56 | READY_FOUNDATION | Current state only; OnHand, IsCommited, OnOrder. | BLOCKED grant |
| oitw_same_item_multiple_warehouses | HQ-5632d0136d1bb2cec0 | HS-636c0f753fadaa6eb3 | READY_FOUNDATION | Current-state table across all available warehouses for one ItemCode. | BLOCKED grant |
| oitw_warehouse_sample | HQ-96248a28ec4c2ea054 | HS-79a9d7b4ca05e2d70f | READY_FOUNDATION | Bounded current-state sample; no historical-as-of claim. | BLOCKED grant |
| oitw_onhand_bounded_aggregate | HQ-41426dab6137056f02 | HS-af6151ebd7b74db663 | REQUIRES_METRIC_DEFINITION | Current-state OnHand sum over two bounded ItemCodes; no as-of cutoff. | BLOCKED grant |
| oitw_commitments_orders | HQ-2f5b9735fb1c88f28e | HS-fba43cf11d9b6eacf9 | READY_FOUNDATION | Current-state commitment/order evidence; zero is not conflated with NULL. | BLOCKED grant |

## Próxima tanda sin SAP

Se requiere una decisión humana de acceso antes de una nueva respuesta comercial, no una reingesta ni otro motor.

1. Autorizar y provisionar por el mecanismo existente los grants específicos de últimos documentos/cobertura para una identidad/workspace DEV aprobados; no se ejecutó ese cambio.
2. Repetir TQ01/TQ03 por el runner existente y comparar sus resultados HTTP completos con referencia SQL. Sólo entonces RUNTIME_PASS y BUSINESS_PASS.
3. SKU explícito: resolver crosswalk namespace y unidad documental, después reutilizar sales_by_item. Calenta libre permanece ambiguo.
4. Importe documental vs neto: adoptar contrato explícito por moneda, impuesto/descuento y NC. No sustituir importe por cantidad ni bloquear futuros hechos nativos por esa deuda.
