# TELCHI — Purchasing Validated Knowledge Promotion V1

Este documento evalúa qué conocimiento validado por las investigaciones de compras puede convertirse en capacidad reusable. No modifica Foundation CURRENT ni publica componentes.

**Gate de diseño:** `TELCHI_PURCHASING_VALIDATED_KNOWLEDGE_PROMOTION_V1_PASS`\
**Entity:** `TELCHI` · **Domain:** `COMPRAS_Y_ABASTECIMIENTO` + `STOCK_E_INVENTARIOS` · **Stage:** `INVESTIGATION`\
**Foundation CURRENT sin cambios:** `foundation_d222a203801cc84e9a14164d26aa67a0`

## 1. Decisión ejecutiva

La evidencia es suficiente para definir una promoción formal, pero no para publicar todavía un componente productivo. La decisión es promover después de corregir y validar un resolver canónico de lineage y sus controles de cobertura.

- **Promover después de fix:** un componente lógico `purchasing` con seis relaciones atómicas y dos relaciones derivadas: `purchasing_document_lineage` y `purchase_inventory_receipt`.
- **Mantener como regla reusable:** resolución `BaseType/BaseEntry/BaseLine`, matching OINM y clasificación de cantidades, cancelaciones, UoM y multi-recepción.
- **Formalizar como contrato semántico:** `TELCHI_PURCHASING_ANALYTICAL_CONTRACT_V1`.
- **No promover como fact:** `TRUE_INVOICED_WITHOUT_RECEIPT`, `DIRECT_AP_INVOICE_NO_GRPO` y otras categorías causales; se derivan de hechos y reglas explícitas.
- **No tocar:** Foundation CURRENT, sus manifiestos y su snapshot productivo.

El gate es **PASS de promoción**, no PASS de publicación. La publicación futura queda condicionada a los gaps indicados en este documento y en el plan de implementación.

## 2. Evidencia revisada

La evaluación usa únicamente las dos investigaciones cerradas y sus artefactos reproducibles; no reabre compras ni Foundation V1.

| Fuente | Evidencia | Resultado relevante |
|---|---|---|
| Reconciliación | `validation/purchase_to_warehouse_receipt_reconciliation_v1/evidence/summary_20261001T002820.json` | 16.355 líneas; 15.471 completamente reconciliadas (94,59 %); 29 multi-recepción; 3 multi-almacén; 0 fanout; 100 % de 15.561 matches OINM con cantidad y almacén |
| AP sin recepción | `validation/ap_invoiced_without_warehouse_receipt_v1/evidence/summary_20261001T014033.json` | 25 líneas; 683.025 unidades; 10 categorías particionadas; 30 candidatos rechazados; 2 entradas OINM sin GRPO; 0 colisiones en el universo |
| Implementación | `validation/.../reconciliation.py` y `ap_invoice_no_grpo.py` | Resolver documental, conversión `Quantity × NumPerMsr`, controles y clasificadores puros |
| Foundation observada | `foundation_d222a203801cc84e9a14164d26aa67a0` | Existe `atomic.inventory_movement` y `reference`; no existe publicación atómica de compras |

La evidencia de negocio es reproducible y Data Lake-only: `SAP_ACCESSED=NO`, `SAP_QUERY_COUNT=0`, `SAP_WRITE_COUNT=0`.

## 3. Knowledge inventory

El inventario separa hechos source-native, relaciones derivadas, reglas de resolución y semántica de negocio para evitar promover interpretaciones como si fueran datos fuente.

### 3.1 Datasets

Estos datasets tienen grain y claves suficientemente claros para ser candidatos atómicos, con cobertura temporal declarada.

| Hallazgo | Grain y clave | Clasificación | Decisión |
|---|---|---|---|
| `purchase_order` | header; `DocEntry` | ATOMIC | PROMOTE_AFTER_FIX |
| `purchase_order_line` | línea; `DocEntry + LineNum` | ATOMIC | PROMOTE_AFTER_FIX |
| `purchase_receipt` | header; `DocEntry` | ATOMIC | PROMOTE_AFTER_FIX |
| `purchase_receipt_line` | línea; `DocEntry + LineNum` | ATOMIC | PROMOTE_AFTER_FIX |
| `ap_invoice` | header; `DocEntry` | ATOMIC | PROMOTE_AFTER_FIX |
| `ap_invoice_line` | línea; `DocEntry + LineNum` | ATOMIC | PROMOTE_AFTER_FIX |
| `inventory_movement` | movimiento source-native; `movement_id` o clave física estable | ATOMIC EXISTENTE | REUSE CURRENT |
| `reference/products` | producto; `code` | REFERENCE EXISTENTE | REUSE CURRENT |
| `reference/warehouses` | almacén; `code` | REFERENCE EXISTENTE | REUSE CURRENT |
| `reference/suppliers` | proveedor; `code` | REFERENCE EXISTENTE | REUSE CURRENT |

La publicación no debe asumir que un extracto parcial equivale a historia completa. Cada relación debe incluir `coverage_start`, `coverage_end`, `as_of` y estado de cobertura.

### 3.2 Relaciones documentales

Las relaciones fueron demostradas por claves nativas, no por coincidencia de fecha, proveedor o cantidad.

| Relación | Regla validada | Clasificación | Decisión |
|---|---|---|---|
| OC → recepción | recepción `BaseType=22`, `BaseEntry=PO.DocEntry`, `BaseLine=PO.LineNum` | REUSABLE_RULE | KEEP_AS_RULE |
| OC → factura | factura línea `BaseType=22`, `BaseEntry=PO.DocEntry`, `BaseLine=PO.LineNum` | REUSABLE_RULE | KEEP_AS_RULE |
| factura → recepción | recepción `BaseType=18` hacia factura; la factura puede apuntar a OC o GRPO | REUSABLE_RULE | KEEP_AS_RULE |
| recepción → recepción | `BaseType=20` recursivo, con límite, ciclo seguro y estado unresolved | REUSABLE_RULE | KEEP_AS_RULE |
| documento → inventory movement | crosswalk por tipo de transacción, `base_ref`, línea, ítem y proveedor cuando estén disponibles | REUSABLE_RULE | PROMOTE_AFTER_FIX |
| recepción → warehouse | `purchase_receipt_line.WhsCode` | SEMANTIC CONTRACT | PROMOTE_AFTER_FIX |

La relación canónica propuesta que expone estas reglas es `purchasing_document_lineage`; no se deben duplicar joins ad hoc en consumidores.

### 3.3 Reglas y claves

Estas reglas son conocimiento estable de resolución y deben convertirse en invariantes de contrato, no en columnas interpretadas dentro de los hechos atómicos.

| Regla | Estado de evidencia | Tratamiento |
|---|---|---|
| `BaseType`, `BaseEntry`, `BaseLine` son la evidencia primaria | Demostrada en 16.076 líneas enlazadas y en los 25 casos AP | Resolver reusable |
| `OINM.base_ref` no es identificador global | Demostrado: `DocNum=262000261` existe simultáneamente en PO `DocEntry=23757`, receipt `DocEntry=24669` e invoice `DocEntry=42615` | Invariante obligatoria |
| `trans_type` decide la familia documental | Necesario para separar PO, GRPO, AP y reversas | Resolver reusable |
| `doc_line_num` preserva la línea | 2 movimientos Flexo fueron atribuidos por línea; no se permite matching solo por documento | Invariante obligatoria |
| `ItemCode` debe ser consistente | 16.076/16.076 coincidencias en la reconciliación; 0 mismatch en los 25 objetivos | Test permanente |
| `card_code` corrobora proveedor | Preservado en evidencia OINM; si falta o contradice, el enlace es `UNRESOLVED` salvo unicidad demostrada por contrato | Test y failure behavior |
| `Quantity × NumPerMsr` es cantidad base | Coincidencia OINM en 15.561/15.561 líneas | Semántica reusable |
| `LineStatus` no prueba recepción | En AP el estado no discrimina; se usa lineage + `OpenQty` + hechos de recepción/movimiento | Regla reusable |

La colisión de `base_ref` debe bloquear cualquier promoción que exponga una relación OINM sin resolver la familia documental.

## 4. Hechos frente a interpretación

La separación siguiente evita materializar conclusiones de una investigación como hechos universales.

### 4.1 Hechos que sí se pueden publicar

Los hechos source-native son estables cuando conservan valor original, clave, snapshot y provenance.

- documentos, líneas y sus `DocEntry`, `DocNum`, `LineNum`;
- `BaseType`, `BaseEntry`, `BaseLine` y `trans_type`;
- `ItemCode`, `CardCode`, cantidades, `NumPerMsr`, `unitMsr`;
- `WhsCode` de la línea de recepción y almacén del movimiento;
- statuses, cancelaciones y fechas fuente;
- movimientos OINM, incluyendo entradas, salidas y reversas;
- relaciones resueltas junto con `resolution_status`, `resolution_path` y evidencia de origen.

### 4.2 Derivaciones permitidas

Estas métricas son deterministas si se calculan desde hechos válidos y no se presentan como campos SAP nativos.

- `total_received_qty`, por suma de recepciones válidas en cantidad base;
- `receipt_count`, por documentos de recepción distintos;
- `fully_received`, `partially_received`, `over_received`;
- `receipt_completion_date`, solo cuando la cobertura temporal permite afirmarlo;
- `invoiced_without_receipt`, solo como regla sobre ausencia de lineage y movimiento;
- `warehouse_received`, como conjunto de almacenes documentales;
- `net_received_after_returns`, únicamente donde exista crosswalk de devolución a línea.

`DIRECT_AP_INVOICE_NO_GRPO` y `TRUE_INVOICED_WITHOUT_RECEIPT` permanecen como resultados de una regla analítica. No son entidades, estados source-native ni componentes atómicos.

## 5. Promotion scorecard

El scorecard aplica evidencia, generalidad, estabilidad, cobertura, tests y reutilización; `PROMOTE_AFTER_FIX` significa que el diseño es válido pero falta una condición de publicación.

| Candidate | Evidence | Generality | Stability | Coverage | Tests | Reuse value | Decision |
|---|---|---|---|---|---|---|---|
| `purchase_order` + lines | Alta: 3.337 headers / 18.584 lines | Alta | Alta, source-native | 2026-01-01..09-23 | Focalizados existentes; faltan tests de contrato | Alta | PROMOTE_AFTER_FIX |
| `purchase_receipt` + lines | Alta: 3.471 / 16.921 | Alta | Alta con cancelaciones explícitas | 2026-01-05..09-23; 143 líneas unresolved | Focalizados existentes; falta coverage gate | Alta | PROMOTE_AFTER_FIX |
| `ap_invoice` + lines | Alta: 6.169 / 21.679 | Alta | Alta como fact documental | 2026-01-01..09-23 | 17 tests focalizados; falta resolver OINM genérico | Alta | PROMOTE_AFTER_FIX |
| `purchasing_document_lineage` | Alta en relaciones probadas | Alta para documentos soportados | Media-alta, depende de extractos y tipos | 16.076 receipt lines enlazadas; 143 unresolved | Resolver tests; falta cardinalidad publicada | Muy alta | PROMOTE_AFTER_FIX |
| `purchase_inventory_receipt` | Alta para TT20/TT18 observados | Media-alta | Media: crosswalk OINM y devoluciones incompletas | 15.561 matches exactos; 515 receipts sin movimiento, principalmente cargos | Faltan tests de collision y unresolved | Muy alta | PROMOTE_AFTER_FIX |
| `invoiced_without_receipt` | Evidencia alta, 25 casos | Media como regla, no fact | Media: comentarios y moneda son señales de caso | Cohorte puntual; no generalizar causa | 17 tests | Alta, pero derivada | KEEP_AS_RULE |
| `TRUE_INVOICED_WITHOUT_RECEIPT` | Alta en 2 casos | Media-baja como categoría | No debe ser source fact | Solo cohorte 25 | Tests de clasificación | Media | KEEP_AS_RULE |
| `reference/products` y warehouses | Ya existentes | Alta | Alta dentro del contrato reference | Snapshot vigente; no historia plena | Foundation CURRENT | Necesario | REUSE CURRENT |

La mínima estructura reusable es un solo componente lógico de compras con facts atómicos y dos relaciones derivadas, no cinco componentes físicos independientes.

## 6. Tests permanentes de Foundation

Los tests permanentes deben comprobar invariantes generales y no congelar los conteos de un snapshot.

| Control | Invariante reusable | Resultado de investigación |
|---|---|---|
| Clave documental | `DocEntry` y `DocEntry + LineNum` únicos dentro de cada dataset | 0 duplicados en los universos evaluados |
| No fanout | Una línea de recepción resuelve a cero o una línea PO | 0 violaciones |
| ItemCode | PO, invoice, receipt y movement enlazados conservan ítem compatible | 16.076/16.076; 0 mismatch objetivo |
| Base válido | `BaseEntry/BaseLine` apunta a una línea materializada o queda `UNRESOLVED` | 99 líneas AP previas al extracto declaradas |
| Lineage path | Solo paths permitidos; ciclos y depth excedido no se silencian | Resolver con `MAX_DEPTH` y tests puros |
| Collision guard | `base_ref` nunca se usa sin `trans_type` y `doc_line_num`; ítem/proveedor corroboran | Colisión `262000261` reproducible |
| Cancelación | Headers `Y/C` y líneas asociadas quedan excluidos de facts válidos, preservados como raw | 702 líneas de receipt excluidas; pares OINM neto cero observados |
| UoM | No sumar unidades incompatibles; convertir con `NumPerMsr` explícito | 16.355/16.355 comparables |
| Warehouse | Preservar warehouse por cada receipt line y movement; no sustituirlo por warehouse planeado | 15.561 cantidad/warehouse iguales |
| Multi-recepción | Sumar por PO line y mantener cada receipt document separado | 29 líneas multi-receipt preservadas |
| Cantidades | Exact/partial/over se derivan de cantidades base y no de status | 884 anomalías de línea visibles |
| OINM | Match TT20/TT18 exige tipo, referencia, línea, ítem y proveedor cuando disponible | 2 entradas TT18 atribuidas sin GRPO |
| Unknown behavior | Unresolved/out-of-window/no-crosswalk nunca se convierte en cero o ausencia | 143 unresolved y 515 sin movimiento declarados |

No son invariantes permanentes los porcentajes 94,59 %, las 25 líneas del caso AP ni los textos de comentarios; son gold/snapshot expectations.

## 7. Gold cases

Los gold cases fijan comportamiento y provenance, no un volumen permanente. El `gold_hash` futuro se calculará sobre JSON canónico ordenado por clave y versión de contrato.

| # | Fixture preservada | Expected result |
|---:|---|---|
| 1 | PO `262003319/0`, `M08929`; receipt `262003436/0` | `EXACT_RECEIPT`; 25 compradas = 25 recibidas; `2A-AMD` |
| 2 | PO `262000256/0`, `L00240`; receipts `262000546/0` + `262000548/0` | `MULTI_RECEIPT_COMPLETE`; 11.353 = 11.200 + 153 |
| 3 | PO `262000013/0`, `L03651`; receipt `262000022/0` | `PARTIAL_RECEIPT`; 1.000 compradas, 1 recibida |
| 4 | PO `262000248/0`, `L00172`; five receipts `262000454`, `490`, `491`, `504`, `557` | `OVER_RECEIPT`; 65.000 → 67.000; no dedup por documento |
| 5 | PO `262002089/0`, invoice `262003870/0`, no receipt | `DIRECT_AP_INVOICE_NO_GRPO` derivado; evidencia explícita `FACTURA ANTICIPADA` |
| 6 | PO `262000492/0-1`, invoice `262001093/0-1`, TT18 +3.000 por línea | `INVENTORY_ENTRY_WITHOUT_GRPO`; dos movimientos, ItemCode y línea preservados |
| 7 | Receipt `262000014` (`CANCELED=Y`) y par `262000019` (`C`) | Ambos excluidos de receipt válido; reversa preservada; no contar ingreso neto |
| 8 | PO `262002290/0`, invoice `262004306/0`, `L01491` | `NO_RECEIPT`; 45 compradas, 0 documentales, categoría derivada `TRUE_INVOICED_WITHOUT_RECEIPT` |
| 9 | `base_ref=262000261` | Resolver por `trans_type`: PO `DocEntry=23757`, receipt `24669`, invoice `42615`; nunca colapsar por `DocNum` |
| 10 | PO `262001421/2`, `L03475`; receipts `262001480/1` y `262001624/1` | `MULTI_RECEIPT_COMPLETE`; 2.000 = 700 en `LAB-M1` + 1.300 en `SAA-M1` |

Los identificadores anteriores deben quedar incluidos en la evidencia de una futura publicación. Si algún identificador desaparece de un snapshot posterior, el resultado debe ser `NOT_IN_SNAPSHOT`, no una sustitución heurística.

## 8. Data quality y límites

Una limitación conocida describe cobertura o semántica no materializada; un data quality failure viola un contrato dentro de la cobertura declarada.

| Tipo | Limitación conocida | No debe interpretarse como |
|---|---|---|
| Temporal | PO/invoice 2026-01-01..09-23; receipt 2026-01-05..09-23; OINM as-of 2026-09-24 | Fallo de join dentro de una ventana cubierta |
| Histórico | 99 receipt lines apuntan a AP lines previas al extracto y 38 a PO fuera del extracto | `NO_RECEIPT` |
| OINM | 515 receipt lines sin movimiento; cargos `I-*` no son inventariables y no generan OINM | Movimiento faltante universal |
| Devoluciones | TT21 existe, pero no hay crosswalk completo ORPD/RPD1 a PO line | `NET_RECEIVED_AFTER_RETURNS` por línea |
| Causas humanas | No hay historial de cambios, recepción borrada, aprobación o inspección física | Confirmación física de ausencia |
| Comentarios | Anticipo y embarque son evidencia documental secundaria para derivación | Campo nativo universal de proceso |
| UoM | Solo comparar cuando `unitMsr`/`NumPerMsr` lo permiten | Suma entre UoM incompatibles |
| `base_ref` | Es `DocNum` y colisiona entre familias documentales | Clave única |

La futura publicación debe reportar cobertura por entidad y un `resolution_status` por relación; nunca ocultar estas limitaciones con `NULL`, cero o fallback silencioso.

## 9. Reutilización

Con la capacidad publicada, estas preguntas podrían comenzar desde el contrato sin repetir discovery de datasets, claves o joins.

- compras todavía no recibidas;
- proveedores con entrega parcial o sobre-recepción;
- tiempo de compra a primera y última recepción;
- productos y cantidades por almacén receptor;
- facturas anteriores o posteriores a la recepción;
- compras en múltiples recepciones o almacenes;
- ingresos OINM sin GRPO documentado;
- diferencias de cantidades por proveedor y UoM compatible.

No se implementan estas consultas en esta fase. El valor de promoción es que todas parten de la misma granularidad, lineage y failure behavior.

### 9.1 Beneficio frente a investigation-only

La promoción elimina discovery repetido, pero no elimina la necesidad de interpretar una pregunta de negocio.

| Antes | Después |
|---|---|
| Localizar datasets y rutas físicas | Resolver `publication_id` y contrato |
| Descubrir claves y tipos | Usar claves y grain documentados |
| Rehacer OC → factura → receipt | Consumir `purchasing_document_lineage` |
| Revalidar fanout y candidatos | Confiar en tests de contrato y `resolution_status` |
| Adivinar warehouse y cantidades | Leer warehouse documental y cantidad base con UoM |
| Repetir colisión de `base_ref` | Aplicar resolver canónico |
| Tratar ausencia como cero | Propagar `UNKNOWN/UNRESOLVED/OUT_OF_COVERAGE` |

El flujo pasa de `pregunta → discovery → joins → validation → analysis` a `pregunta → Foundation contract → deterministic query → business interpretation`.

## 10. Versionado y provenance

La capacidad debe ser identificada por publicación inmutable, no por rutas físicas de Parquet.

Una publicación futura usará como mínimo:

- `publication_id`, por ejemplo `TELCHI_PURCHASING_FOUNDATION_V1_<fingerprint>`;
- `snapshot_id` y `as_of`;
- `schema_version` y `contract_version`;
- `source_publication_ids` y datasets de origen;
- `lineage_algorithm_version`;
- `gold_hash`;
- `coverage` por entidad y ventana;
- `provenance` del runner, commit y evidencia;
- `status`: `CANDIDATE`, `CURRENT`, `SUPERSEDED` o `REJECTED`.

Los consumidores deben solicitar un `publication_id` o alias lógico y no acoplarse a `DATA_ROOT`, nombres de archivo o layout físico.

## 11. Riesgos y gate

Los riesgos son conocidos y tienen salida explícita; ninguno autoriza promoción silenciosa.

- El resolver actual de investigación no es todavía un contrato Foundation: debe publicar crosswalk y `UNRESOLVED`.
- La cobertura no es histórica completa; la temporalidad debe acompañar cada resultado.
- `OINM` no permite afirmar devoluciones por línea sin crosswalk.
- La clasificación AP usa comentarios/moneda como evidencia de negocio y debe seguir siendo una regla derivada.
- La investigación no prueba existencia física cuando no hay documento o movimiento atribuible.

### 11.1 Gate emitido

Se emite `TELCHI_PURCHASING_VALIDATED_KNOWLEDGE_PROMOTION_V1_PASS` porque existe conocimiento reusable identificado, separación facts/derived, scorecard explícito, contrato defendible, tests, gold cases, provenance y failure behavior.

Este PASS no modifica Foundation CURRENT, no crea un candidato físico y no habilita consumidores productivos. La transición siguiente es el plan de implementación con parity checks y una ventana de promoción independiente.

## 12. Trazabilidad

La trazabilidad permite reproducir el razonamiento sin convertir los reportes de investigación en dependencias runtime.

- Investigación base: `telchi_purchase_to_warehouse_receipt_reconciliation_v1_report.md`.
- Excepción AP: `telchi_ap_invoiced_without_warehouse_receipt_v1_report.md`.
- Contrato propuesto: `TELCHI_PURCHASING_ANALYTICAL_CONTRACT_V1.md`.
- Plan: `TELCHI_PURCHASING_FOUNDATION_PROMOTION_IMPLEMENTATION_PLAN_V1.md`.
- Evidencia: los dos `summary_*.json` y sus JSONL asociados, con timestamps indicados arriba.
