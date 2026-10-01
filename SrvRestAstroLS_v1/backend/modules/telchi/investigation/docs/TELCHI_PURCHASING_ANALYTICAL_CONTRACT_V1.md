# TELCHI — Purchasing Analytical Contract V1

Este contrato es una propuesta semántica para publicar compras y su ingreso a almacén sin mezclar hechos fuente con derivaciones. Está diseñado, no materializado.

**Status:** `PROPOSED_CONTRACT` · **Publication target:** `TELCHI_PURCHASING_FOUNDATION_V1`\
**Contract version:** `1.0.0` · **Foundation CURRENT:** sin cambios\
**Gate de publicación:** pendiente de `PROMOTE_AFTER_FIX`; este documento no autoriza publicación.

## 1. Alcance y no alcance

El contrato cubre documentos de compra, relaciones documentales, movimientos de inventario atribuibles y cantidades/almacenes con cobertura explícita.

Incluye:

- `purchase_order` y `purchase_order_line`;
- `purchase_receipt` y `purchase_receipt_line`;
- `ap_invoice` y `ap_invoice_line`;
- `purchasing_document_lineage`;
- `purchase_inventory_receipt`;
- referencia de productos, proveedores y almacenes.

No incluye causal humana, estado físico no materializado, pagos, devoluciones por línea sin crosswalk, ni categorías de negocio como facts atómicos.

## 2. Publication envelope

Cada resultado consumible debe indicar qué publicación y snapshot lo produjo.

| Campo | Semántica |
|---|---|
| `publication_id` | Identidad inmutable de la publicación, nunca una ruta física |
| `snapshot_id` | Snapshot lógico de fuente |
| `as_of` | Fecha/hora máxima efectiva de la evidencia |
| `schema_version` | Versión del schema atómico/derivado |
| `contract_version` | Versión de este contrato |
| `lineage_algorithm_version` | Versión del resolver documental y OINM |
| `gold_hash` | Hash de resultados gold canónicos |
| `coverage` | Ventana y completitud por entidad |
| `provenance` | IDs de fuentes, runner, commit y evidencia |
| `status` | `CANDIDATE`, `CURRENT`, `SUPERSEDED` o `REJECTED` |

Un consumidor debe seleccionar `publication_id`; no debe conocer `DATA_ROOT`, carpetas o nombres de Parquet.

## 3. Entidades y grain

La granularidad es parte del contrato y no puede inferirse de una consulta consumidora.

| Entidad | Grain | Clave canónica |
|---|---|---|
| `purchase_order` | una cabecera OC | `source_system + doc_entry` |
| `purchase_order_line` | una línea OC | `source_system + doc_entry + line_num` |
| `purchase_receipt` | una cabecera GRPO | `source_system + doc_entry` |
| `purchase_receipt_line` | una línea GRPO | `source_system + doc_entry + line_num` |
| `ap_invoice` | una cabecera AP | `source_system + doc_entry` |
| `ap_invoice_line` | una línea AP | `source_system + doc_entry + line_num` |
| `purchasing_document_lineage` | una relación documental dirigida por línea | `lineage_id`; además `from_key + to_key + path_rank` |
| `purchase_inventory_receipt` | una atribución de movimiento a línea documental | `movement_key + target_line_key` |
| `reference/product` | un producto | `source_system + code` |
| `reference/warehouse` | un almacén | `source_system + code` |
| `reference/supplier` | un proveedor | `source_system + code` |

`DocNum` es un atributo de negocio, no una clave. `DocEntry + LineNum` es la identidad documental dentro del sistema fuente.

## 4. Atomic schema

Las relaciones atómicas conservan valores source-native y no contienen estados interpretados por conveniencia.

### 4.1 `purchase_order`

La cabecera OC conserva identidad, fecha, proveedor, cancelación y estado fuente.

Campos mínimos:

- `source_system`, `doc_entry`, `doc_num`;
- `doc_date`, `card_code`, `doc_status`, `canceled`;
- `tipo_compra`, `comments` si están materializados;
- `snapshot_id`, `source_row_hash`, `coverage_status`.

### 4.2 `purchase_order_line`

La línea OC conserva cantidades, UoM, almacén planeado y status sin afirmar recepción.

Campos mínimos:

- `source_system`, `doc_entry`, `line_num`, `item_code`;
- `quantity`, `unit_msr`, `num_per_msr`, `open_qty`;
- `whs_code`, `line_status`, `ship_date`, `description`;
- `base_quantity` solo como conversión técnica auditable: `quantity × num_per_msr`;
- `snapshot_id`, `source_row_hash`, `coverage_status`.

### 4.3 `purchase_receipt` y `purchase_receipt_line`

La recepción conserva el documento, su cancelación y la relación source-native declarada en cada línea.

Campos mínimos de header: `doc_entry`, `doc_num`, `doc_date`, `card_code`, `doc_status`, `canceled`.\
Campos mínimos de línea: `doc_entry`, `line_num`, `base_type`, `base_entry`, `base_line`, `item_code`, `quantity`, `unit_msr`, `num_per_msr`, `whs_code`.

`whs_code` es el almacén documental de ingreso. No se reemplaza por el almacén planeado de la OC.

### 4.4 `ap_invoice` y `ap_invoice_line`

La factura AP conserva su base documental, moneda y status fuente; una factura directa no se convierte por sí sola en receipt.

Campos mínimos de header: `doc_entry`, `doc_num`, `doc_date`, `card_code`, `doc_status`, `canceled`, `doc_cur`, `comments`, `num_at_card`.\
Campos mínimos de línea: `doc_entry`, `line_num`, `base_type`, `base_entry`, `base_line`, `item_code`, `quantity`, `unit_msr`, `num_per_msr`, `open_qty`, `line_status`.

Los comentarios, moneda y referencias de embarque son evidencia documental secundaria y deben conservar su provenance.

## 5. Canonical document lineage

`purchasing_document_lineage` contiene solo relaciones deterministas o marca explícitamente la relación como unresolved.

### 5.1 Paths permitidos

El resolver debe conservar el path que produjo cada relación.

| `resolution_path` | Regla |
|---|---|
| `DIRECT_PO` | receipt line `BaseType=22` → PO line |
| `VIA_AP_INVOICE` | receipt `BaseType=18` → AP line `BaseType=22` → PO line |
| `VIA_RECEIPT_CHAIN` | receipt `BaseType=20` → receipt line, recursivo y limitado |
| `AP_INVOICE_NO_PO` | AP directa sin OC; no inventa una PO |
| `AP_LINE_NOT_MATERIALIZED` | la línea base está fuera del snapshot |
| `NO_BASE_DOCUMENT` | no existe documento base |
| `MAX_DEPTH` / `CYCLE` | cadena no resoluble |
| `PO_LINE_OUT_OF_COVERAGE` | la PO destino no está materializada |

### 5.2 Reglas de join

La resolución usa únicamente claves source-native y valida que la línea destino exista.

1. Normalizar `BaseType`, `BaseEntry` y `BaseLine` sin convertir `NULL` en cero.
2. Resolver `BaseEntry` contra `DocEntry` de la familia definida por `BaseType`.
3. Validar `ItemCode` cuando ambos lados lo exponen.
4. Mantener todos los paths; no colapsar dos documentos distintos en un único hecho.
5. Marcar `resolution_status=RESOLVED`, `UNRESOLVED`, `OUT_OF_COVERAGE` o `NOT_APPLICABLE`.
6. Rechazar fanout: una línea receipt no puede resolver a múltiples líneas PO.

## 6. OINM lineage resolver

OINM se integra como hecho atómico y como relación derivada solamente cuando la identidad documental es defendible.

### 6.1 Clave de matching

`base_ref` es normalmente `DocNum` y colisiona entre PO, receipt e invoice. Por eso la clave mínima de resolución es:

```text
(trans_type, base_ref, doc_line_num, ItemCode, CardCode)
```

`CardCode` debe coincidir cuando ambos lados están presentes. Si está ausente, el resolver puede aceptar el vínculo solo si el crosswalk restante es único y el contrato registra `card_code_status=ABSENT_BUT_UNIQUE`; si hay más de un candidato, devuelve `UNRESOLVED`.

`trans_type` debe mapear primero la familia documental. Para los casos validados: TT20 corresponde a ingreso por recepción y TT18 a entrada por factura AP; TT21 representa devolución y no se resta a una línea PO sin crosswalk de devolución.

### 6.2 Resultado de resolución

Cada vínculo OINM publica la evidencia utilizada y no solo una boolean.

- `movement_key` estable de la publicación;
- `target_line_key` documental;
- `trans_type`, `base_ref`, `doc_line_num`, `item_code`, `card_code`;
- `warehouse`, `doc_date`, `in_qty`, `out_qty`;
- `resolution_status`;
- `match_fields` y `rejected_candidate_count`;
- `resolution_reason`;
- `source_snapshot_id` y `algorithm_version`.

Una coincidencia por cantidad, fecha, proveedor o almacén sin enlace documental es un candidato rechazado, nunca un vínculo.

## 7. Quantity and UoM semantics

Las cantidades se comparan en una UoM base solo cuando la conversión está demostrada.

- `quantity` conserva la magnitud source-native de la línea.
- `unit_msr` conserva la UoM declarada.
- `num_per_msr` conserva el factor fuente.
- `base_quantity = quantity × num_per_msr` cuando ambos valores son válidos.
- `received_base_quantity` suma solo receipts válidos y comparables.
- UoM incompatible produce `UOM_UNRESOLVED`; no produce cero.
- No se suman UoM incompatibles en agregados.

La clasificación de una línea usa `received_base_quantity` frente a `ordered_base_quantity`: `EXACT`, `PARTIAL`, `OVER`, `NO_RECEIPT` o `NOT_DETERMINABLE`.

## 8. Warehouse semantics

El contrato distingue almacén planeado, almacén documental y almacén físico corroborado.

- `planned_warehouse`: `purchase_order_line.WhsCode`.
- `receipt_warehouse`: `purchase_receipt_line.WhsCode`.
- `movement_warehouse`: `inventory_movement.warehouse`.
- `warehouse_match_status`: `MATCH`, `MISMATCH`, `UNKNOWN`.

Una línea puede tener múltiples receipts y múltiples warehouses. Se conserva una fila por receipt line y se derivan conjuntos/agregados sin perder esa granularidad.

## 9. Cancellation, reversal and temporal semantics

La cancelación se preserva como hecho fuente; los estados derivados deben explicar qué excluyeron.

- Se aplica la semántica de cancelación propia de cada entidad: receipt usa `Y/C`; PO y AP conservan y aplican los valores observados en su fuente. Todo cancelado queda fuera de facts válidos y permanece en raw/atomic con su status.
- Un par original/reversa se excluye del agregado válido cuando la evidencia documental y OINM lo respaldan.
- TT21 no se resta automáticamente de compras: falta crosswalk completo a línea PO.
- Toda ausencia se interpreta solo dentro de `coverage_start..coverage_end` y `as_of`.
- Una PO anterior a la ventana o una línea base fuera del snapshot produce `OUT_OF_COVERAGE`, no `NO_RECEIPT`.
- `receipt_completion_date` es `UNKNOWN` si no existe evidencia de que el snapshot contiene el final de la cadena.

## 10. Derived contract

Las relaciones derivadas exponen resultados deterministas junto con sus inputs y estado de resolución.

### 10.1 `purchasing_document_lineage`

Grain: una arista documental dirigida por línea.

Campos mínimos:

- `lineage_id`, `from_entity`, `from_key`, `to_entity`, `to_key`;
- `resolution_path`, `resolution_status`, `path_depth`;
- `base_type`, `base_entry`, `base_line`;
- `item_match_status`, `uom_match_status`, `card_code_status`;
- `coverage_status`, `evidence_refs`, `algorithm_version`.

### 10.2 `purchase_inventory_receipt`

Grain: una atribución de movimiento a una línea documental; no un agregado por proveedor.

Campos mínimos:

- `movement_key`, `target_line_key`, `target_entity`;
- `trans_type`, `base_ref`, `doc_line_num`, `item_code`, `card_code`;
- `warehouse`, `in_qty`, `out_qty`, `movement_date`;
- `resolution_status`, `resolution_reason`, `match_fields`;
- `quantity_match_status`, `warehouse_match_status`;
- `coverage_status`, `evidence_refs`, `algorithm_version`.

## 11. Unknown and failure behavior

El contrato hace visibles las fronteras de conocimiento y prohíbe inferencias silenciosas.

| Situación | Resultado requerido |
|---|---|
| Línea fuente ausente del snapshot | `OUT_OF_COVERAGE` |
| BaseEntry/BaseLine inválido | `UNRESOLVED` |
| `base_ref` con más de una familia/candidato | `AMBIGUOUS_LINEAGE` |
| Cycle o profundidad excedida | `UNRESOLVED` con razón `CYCLE`/`MAX_DEPTH` |
| ItemCode inconsistente | `ITEM_MISMATCH`, no join analítico |
| UoM incompatible | `UOM_UNRESOLVED` |
| Warehouse ausente | `WAREHOUSE_UNKNOWN` |
| OINM sin crosswalk | `MOVEMENT_UNRESOLVED` |
| Devolución sin crosswalk PO | `RETURN_UNRESOLVED` |
| Falta de evidencia causal | `NOT_DETERMINABLE` |

Un consumer puede filtrar estados, pero no puede reinterpretar `UNKNOWN` como `0`, `NO_RECEIPT` o `FALSE`.

## 12. Deterministic business rules

Las reglas de negocio consumen hechos y lineage; no alteran los datasets atómicos.

- `total_received_qty`: suma de receipt lines `RESOLVED`, no canceladas y UoM compatibles.
- `receipt_count`: `COUNT(DISTINCT receipt_doc_entry)` en la línea PO.
- `fully_received`: ordered y received comparables, delta cero.
- `partially_received`: received menor que ordered y mayor que cero.
- `over_received`: received mayor que ordered.
- `invoiced_without_receipt`: AP válida basada en PO, sin receipt lineage y sin movement lineage dentro de cobertura.
- `true_invoiced_without_receipt`: regla anterior más ausencia de evidencia documental secundaria; no es una columna atómica.

Las señales de anticipo, importación y comentario deben exponerse como evidencia (`evidence_type`, `evidence_ref`), no como causal universal.

## 13. Contract acceptance criteria

El contrato solo puede pasar a candidato Foundation cuando todos estos criterios tengan evidencia versionada.

- claves y grain únicos por entidad;
- resolver collision-safe con fixture `262000261`;
- fanout cero o estado unresolved explícito;
- cobertura publicada por dataset;
- tests de ItemCode, UoM, warehouse, cancelaciones y multi-receipt;
- crosswalk OINM TT20/TT18 reproducible;
- gold cases 1–10 iguales al expected;
- `UNKNOWN`/`OUT_OF_COVERAGE` no convertido a cero;
- parity contra la investigación dentro de la misma snapshot;
- manifiesto y `gold_hash` reproducibles;
- ningún consumidor depende de rutas físicas;
- sin cambio a Foundation CURRENT antes del gate de promoción.
