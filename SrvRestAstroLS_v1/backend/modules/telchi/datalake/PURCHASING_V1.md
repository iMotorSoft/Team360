# Purchasing Foundation Component V1

Compras está implementado como componente candidato de Foundation. Publica hechos source-native y relaciones auditables; CURRENT permanece intacto y la promoción requiere un gate independiente.

## Resultado vigente

El gate de implementación cerró sobre el candidato indicado, con paridad por línea y lectura verificada de los Parquet materializados.

- Gate: `TELCHI_PURCHASING_FOUNDATION_COMPONENT_V1_PASS`.
- Foundation candidate: `foundation_afd08d9eca6a725be53cdc3f9d5709c9`.
- Purchasing publication: `purchasing_4ab178d62c5f5ba27d7180a8`.
- Estado candidato: `READY_TO_COMMIT`; interpretación operacional: `CANDIDATE_READY_FOR_PROMOTION`.
- CURRENT preservado: `foundation_d222a203801cc84e9a14164d26aa67a0`.
- Evidencia canónica: `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi/TELCHI_PURCHASING_FOUNDATION_COMPONENT_V1/purchasing-v1-20261001T121125360640Z/`.
- Gold hash: `3b1095a308855e93a684d79d892c0ca620e693518916676a621979e20de459de`.

## Contrato efectivo

La implementación reutiliza el writer inmutable `write_raw`, sus hashes/manifests y el catálogo `FoundationPublicationStore`. No agrega publicaciones, punteros ni mecanismos de promoción paralelos.

| Dataset | Filas | Identidad |
| --- | ---: | --- |
| `purchase_order` | 3.337 | source_system + object_type + DocEntry |
| `purchase_order_line` | 18.584 | identidad documental + LineNum |
| `purchase_receipt` | 3.471 | source_system + object_type + DocEntry |
| `purchase_receipt_line` | 16.921 | identidad documental + LineNum |
| `ap_invoice` | 6.169 | source_system + object_type + DocEntry |
| `ap_invoice_line` | 21.679 | identidad documental + LineNum |
| `purchasing_document_lineage` | 38.600 | arista dirigida por línea |
| `purchase_inventory_receipt` | 17.196 | movement_key único |

`source_native_json` conserva todos los campos extraídos, incluso los que no tienen columna normalizada. Las claves, cancelación, moneda, cantidades, UoM, factor, almacén y BaseType/BaseEntry/BaseLine quedan también accesibles en columnas. `source_row_hash` y `snapshot_id` identifican la evidencia fuente.

La identidad del componente incluye hashes lógicos de cada dataset, manifests fuente, cobertura y versiones de dependencias. El lector verifica hashes físicos, conteos y hashes lógicos; no selecciona archivos por glob ni usa latest. Los datos físicos permanecen en `DATA_ROOT`, separados del source.

## Resolución documental e inventario

Las relaciones exponen la arista inmediata y el path hasta la OC. Una relación inmediata puede estar demostrada aunque su raíz esté fuera de cobertura; ambos estados se conservan.

El resolver documental usa BaseType/BaseEntry/BaseLine, verifica ItemCode/proveedor y limita profundidad y ciclos. Publica `RESOLVED_EXACT`, `UNRESOLVED`, `OUT_OF_COVERAGE` y `NOT_APPLICABLE`. `edge_resolution_status` distingue la arista inmediata de `resolution_status`, que describe el path raíz.

El resolver OINM restringe primero la familia por `trans_type` y después exige `base_ref`, `doc_line_num` e ItemCode. CardCode corrobora cuando está presente; su ausencia permite `RESOLVED_SUPPORTED` solamente con unicidad demostrada. Un DocEntry OINM no se interpreta automáticamente como DocEntry de compras. Un crosswalk explícito puede aportar esa identidad.

El caso real `262000261` conserva OC `23757`, recepción `24669` y factura `42615`: `base_ref` solo es ambiguo, TT20 selecciona la recepción. Una colisión dentro de la misma familia que conserva varios candidatos queda `UNRESOLVED`; el test permanente impide selección arbitraria.

| Métrica OINM | Resultado |
| --- | ---: |
| RESOLVED_EXACT | 16.414 |
| RESOLVED_SUPPORTED | 0 |
| UNRESOLVED | 0 |
| OUT_OF_COVERAGE | 43 |
| NOT_APPLICABLE | 739 |
| Colisiones entre familias detectadas | 17.153 |
| Colisiones resueltas con evidencia | 16.414 |
| Colisiones ambiguas conservadas unresolved en este snapshot | 0 |
| Fanout / ItemCode mismatch / warehouse mismatch | 0 / 0 / 0 |

Las 739 devoluciones TT21 se preservan como `NOT_APPLICABLE` para atribución a PO: falta el crosswalk de devolución. No se restan a compras por heurística. El inventario existente se consume por el reader canónico, pinneado al snapshot CURRENT `1328`; el snapshot base de manifiesto `1322` se preserva como concepto distinto.

El lineage completo de receipt y AP contiene 33.944 paths `RESOLVED_EXACT`, 556 `UNRESOLVED`, 259 `OUT_OF_COVERAGE` y 3.841 `NOT_APPLICABLE`. Estos conteos incluyen líneas no inventariables y canceladas, además de la cohorte principal; no equivalen a fallos de reconciliación en las 16.355 líneas inventariables.

## Cantidades, almacenes y cancelación

Toda cantidad conserva su UoM fuente; la cantidad base usa exclusivamente `Quantity × NumPerMsr` con factor finito y positivo. No hay conversión desde descripciones.

- `ordered_qty`: Quantity de la línea PO; `ordered_base_quantity`: su conversión fuente.
- `received_qty`: Quantity por receipt line; total comparable desde `base_quantity`, manteniendo cada línea y receipt DocEntry.
- `invoiced_qty`: Quantity por AP line; agregación por identidad de línea y UoM compatible, sin convertir AP directa en GRPO.
- `inventory_in_qty` / `inventory_out_qty`: InQty/OutQty base por movement_key, preservados separadamente.
- `base_qty`: cantidad documental convertida que acompaña la atribución OINM; no implica igualdad de una línea con cada movimiento individual.
- `purchase_summary` expone cantidades base, receipt_count, primera/última fecha, warehouses y fully_received; un valor indeterminado permanece `None`.

Los almacenes planeado, documental y físico permanecen separados. El crosswalk Reference pinneado aporta ubicación de negocio y estado/provenance; si falta, queda `UNKNOWN`. Multi-recepción y multi-warehouse mantienen grain de línea.

Los documentos `Y/C` se conservan en atomic y se excluyen de cantidades efectivas. El path comprueba también cancelaciones intermedias. OINM conserva dirección y status efectivo; el gold real `262000014`/`262000019` prueba original, reversa y neto cero. No se eliminan movimientos ni se supone crosswalk completo de devoluciones.

## Cobertura y límites

La publicación cubre los captures documentales 2026 usados en las investigaciones; no afirma historia completa. Fechas, ventanas de extracción y manifests fuente acompañan cada dataset.

- PO/AP: primeras fechas disponibles `2026-01-01`, últimas `2026-09-23`.
- Receipt: primera fecha disponible `2026-01-05`, última `2026-09-23`; extracción desde `2026-01-01`.
- OINM: componente existente con evidencia hasta `2026-09-24`; el scope de compras incluye TT18/20/21 y algunos movimientos históricos sin documentos en el capture.
- La cobertura nominal mensual de los manifests no se interpreta como evidencia posterior a la última fecha disponible.
- Referencias a líneas ausentes quedan `OUT_OF_COVERAGE`; claves inválidas, ciclos, ItemCode contradictorio o UoM incompatible conservan estados explícitos.
- La semántica causal humana, recepción física sin registro y net_received_after_returns completo permanecen fuera del contrato.
- `TRUE_INVOICED_WITHOUT_RECEIPT`, `DIRECT_AP_INVOICE_NO_GRPO` e `INVENTORY_ENTRY_WITHOUT_GRPO` son reglas derivadas, nunca facts atómicos.

## Gold y paridad

Los diez casos reales quedan en el fixture permanente `tests/fixtures/purchasing_gold_v1.json`, seleccionado de las fuentes selladas con sus claves y familias en colisión; no se sustituyen por ejemplos sin ambigüedad.

La paridad compara las 16.355 líneas contra el JSONL cerrado, incluyendo claves de receipts, ItemCode, proveedor, cantidades, clasificación y almacenes. Reproduce 15.460 exactas, 11 multi-exactas, 31 parciales, 8 over-receipt, 845 sin recepción y 0 NOT_DETERMINABLE. Las 3.219 OC válidas se preservan en el componente.

La investigación focalizada reproduce 25 líneas, 683.025 unidades base y la partición 21 AP directas / 2 entradas OINM sin GRPO / 2 verdaderas sin recepción. La validación se repite después de materializar y leer los Parquet exactos. No hubo diferencias sin explicar.

Los siete componentes previos mantienen manifiesto, publication identity y datos: se comparan fingerprints de nueve tablas pinneadas y hashes de Reference y Material Supply. El primer candidato de prueba `foundation_58bee7346ae4c1b5d6cf77367ab3cbc8` quedó `FAILED` antes de promoción por la regresión del reader; su evidencia y corrección se preservan. Solo el candidato vigente es elegible.

Validación final: 41 tests propios de purchasing, incluidos los diez casos gold reales, y 287 tests de regresión Data Lake PASS. Los gates LAT y `git diff --check` pasaron. Las validaciones usan Data Lake y fixtures; no acceden a SAP ni invocan modelos de IA.

## Uso y reproducción

Los consumidores candidatos entran por un Foundation candidate ID explícito y reciben datasets verificados; no necesitan conocer DATA_ROOT ni reconstruir discovery o joins de investigación.

```python
from modules.telchi.datalake.purchasing_foundation import pinned_component, read_component

component = pinned_component(store, candidate_id)
datasets = read_component(component)
```

El componente permite partir de lineage estable para recepción por proveedor, entregas parciales/excesos, primera/última recepción, almacenes, AP directa y entradas inventario sin GRPO. La selección CURRENT productiva se habilitará en el gate posterior; esta implementación no cambia su puntero.

```bash
uv run pytest modules/telchi/datalake/tests
uv run python -m modules.telchi.datalake.purchasing_gate --base-id foundation_d222a203801cc84e9a14164d26aa67a0
```

El runner exige tests de regresión antes de construir el candidato, verifica fuentes y gold/parity, materializa mediante el writer existente y usa el run lock para el catálogo. Una falla preserva CURRENT y evita marcar un candidato listo.

## Estado y próximo gate

La implementación conserva su candidato aprobado, pero el precheck de promoción del 2026-10-01 bloqueó su publicación por incompatibilidad con el lector productivo de Receivables & Collections. CURRENT no fue modificado.

El gate `TELCHI_PURCHASING_FOUNDATION_PROMOTION_AND_CLOSURE_V1_BLOCKED` verificó el candidato exacto en `READY_TO_COMMIT`, su manifiesto aprobado y gold/parity sin diferencias. El CURRENT vigente sigue siendo `foundation_d222a203801cc84e9a14164d26aa67a0`, con siete componentes; purchasing todavía no está productivo.

`receivables_collections_foundation.resolve_current` delega en `_resolve`, que exige `candidate_kind=RECEIVABLES_COLLECTIONS_FOUNDATION_EXTENSION_V1` y exactamente los siete componentes de ese contrato. El candidato aprobado declara `PURCHASING_FOUNDATION_V1` y ocho componentes. Aplicar ese lector al candidato produce `ReceivablesComponentError: Receivables Foundation manifest kind is missing or wrong`; aun superado ese primer control, el conjunto de componentes incumple su contrato.

La promoción no se intentó y no requirió rollback. No se modificaron lógica, schemas, datasets, gold cases ni el candidato. Resolver la compatibilidad requiere volver al gate de implementación y validar los consumidores antes de autorizar otra promoción. No hay evidencia post-promoción ni smoke de purchasing productivo.

Evidencia del bloqueo: `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi/TELCHI_PURCHASING_FOUNDATION_PROMOTION_AND_CLOSURE_V1/`. Las restricciones de coverage, UNKNOWN, UNRESOLVED, OUT_OF_COVERAGE y devoluciones sin crosswalk del candidato permanecen intactas.

```text
FOUNDATION_CURRENT_MODIFIED=NO
PURCHASING_COMPONENT_IMPLEMENTED=YES
COLLISION_SAFE_RESOLVER=PASS
GOLD_CASES=PASS
PARITY=PASS
CANDIDATE_CREATED=YES
READY_FOR_PROMOTION=YES
SAP_ACCESSED=NO
SAP_QUERY_COUNT=0
SAP_WRITE_COUNT=0
```
