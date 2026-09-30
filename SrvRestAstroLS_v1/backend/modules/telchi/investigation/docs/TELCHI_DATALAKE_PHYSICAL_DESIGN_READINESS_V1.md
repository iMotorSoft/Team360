# TELCHI DATA LAKE — PHYSICAL DESIGN READINESS REVIEW V1

Este gate revisa sólo los ocho gaps bloqueantes del modelo canónico y decide si existe definición suficiente para iniciar, en un gate posterior, el diseño físico de Parquet.

## A. Gate

El gate termina en PASS porque los ocho gaps tienen cierre o contrato seguro y ninguno exige resolver el layout mediante una suposición.

**PASS — `TELCHI_DATALAKE_PHYSICAL_DESIGN_READINESS_V1_PASS`**

```text
PHYSICAL_DESIGN_READY=YES
STILL_BLOCKING=0
```

Este PASS autoriza únicamente el siguiente gate. No define nombres, schemas físicos, particiones, compresión, orden, incrementalidad, vistas DuckDB, ingesta, serving ni Parquet productivos.

## B. Resumen ejecutivo

Se usaron como autoridad los tres gates requeridos, sin reconstruir inventarios ni reabrir análisis funcionales.

- Los ocho gaps originales fueron revisados exactamente una vez.
- Dos quedaron `RESOLVED` por contratos ya explícitos: política de snapshots y seguridad futura.
- Seis quedaron `DEFERRED_WITH_SAFE_CONTRACT`: el conocimiento pendiente queda encapsulado sin cambiar grain, identidad, conteos, lineage, temporalidad ni autorización futura.
- No fue necesaria una consulta SAP/HANA: la evidencia existente responde la pregunta de readiness.
- Los ocho ejes de readiness están `READY`.
- No se diseñó ni creó layout físico.

La conclusión es limitada: el diseño físico puede comenzar sin inventar semántica. No significa que todo el conocimiento Telchi esté completo ni que los mappings históricos estén materializados.

## C. Los 8 gaps originales

La fuente exacta es `datalake_canonical_model_and_lineage_v1/blocking_gaps.csv`; esta tabla no agrega gaps nuevos.

| Gap | Descripción original | Motivo de bloqueo físico |
|---|---|---|
| GAP-001 | Falta metadata formal de origen en Parquet legacy. | Las filas físicas necesitan lineage estable aun cuando el origen histórico sea parcial. |
| GAP-002 | La fecha del filename difiere de las fechas de negocio. | Concatenar snapshots solapados puede duplicar eventos o estados. |
| GAP-003 | `movProductSB1` tiene claves candidatas duplicadas y join OINM no universal. | La clave corta no puede definir el movimiento atómico. |
| GAP-004 | Falta vigencia histórica de maestros y warehouse→branch. | Proyectar el mapping actual al pasado fabricaría verdad temporal. |
| GAP-010 | El vínculo producción→despacho es heurístico. | No debe prometerse trazabilidad completa mediante una FK falsa. |
| GAP-012 | No hay autorización histórica ni RBAC futuro implementado. | El layout no debe impedir seguridad por dominio, fila, columna, métrica y scope. |
| GAP-017 | Mappings SAP de `purchaseExpense`, `productTransform` y `cash` incompletos. | Una fusión silenciosa cambiaría grain y podría duplicar hechos. |
| GAP-018 | Cancelaciones y pagos históricos tienen watermarks distintos. | Un cutover implícito corrompería deuda y estado as-of. |

La evidencia detallada, las preguntas de cierre y las decisiones físicas afectadas están en `blocking_gaps_review.csv`.

## D. Resolución individual

Cada gap termina en una de las cuatro categorías obligatorias, sin estados intermedios.

| Gap | Estado final | Evidencia decisiva | Resolución |
|---|---|---|---|
| GAP-001 | `DEFERRED_WITH_SAFE_CONTRACT` | Ocho perfiles de lineage y archivos históricos inventariados. | El lineage desconocido se representa como parcial/aggregate y no se fabrica. |
| GAP-002 | `RESOLVED` | 16 políticas de snapshot y DEC-011. | Un corte declarado, identidad fuerte y prohibición de concatenación implícita cierran el riesgo físico. |
| GAP-003 | `DEFERRED_WITH_SAFE_CONTRACT` | 181.384 colisiones candidatas; DEC-001; OINM `TransNum+TransSeq`. | `movProductSB1` queda business-denormalized, nunca verdad atómica por inferencia. |
| GAP-004 | `DEFERRED_WITH_SAFE_CONTRACT` | 51 almacenes→7 oficinas actuales; crosswalks versionados. | Warehouse es autoritativo; branch histórico puede ser null/UNKNOWN. |
| GAP-010 | `DEFERRED_WITH_SAFE_CONTRACT` | Grains productivos independientes y ausencia explícita de FK. | El link heurístico es derivado opcional, con método/confianza, no constraint. |
| GAP-012 | `RESOLVED` | Nueve dominios con scope, sensibilidad y agregación. | El layout puede preservar las dimensiones para `SECURITY BEFORE RETRIEVAL`; RBAC no se implementa aquí. |
| GAP-017 | `DEFERRED_WITH_SAFE_CONTRACT` | Entidades specialized y mappings incompletos explícitos. | Las familias legacy quedan source-scoped y no se fusionan con hechos SAP. |
| GAP-018 | `DEFERRED_WITH_SAFE_CONTRACT` | Crédito as-of, fuentes por rol y prohibición de cutover silencioso. | Cada fuente conserva tiempo efectivo, snapshot, extracción y versión; no se exige watermark global. |

Resultado cuantitativo: `RESOLVED=2`, `RESOLVED_BY_TARGETED_VALIDATION=0`, `DEFERRED_WITH_SAFE_CONTRACT=6`, `STILL_BLOCKING=0`.

### Granularidad CORE V1 relevante

La revisión confirma el modelo aprobado; no cambia entidades ni crea otras por conveniencia.

| Entidad | Una fila representa | Key nativa candidata | Clase | Tiempo |
|---|---|---|---|---|
| `SALE_DOCUMENT` | un documento de venta | source system + native id + type | EVENT | document/posting/due/system |
| `SALE_LINE` | una línea de venta | source document + line | EVENT | document/posting/extraction |
| `INVENTORY_MOVEMENT` | una línea/evento de movimiento | transaction + line o fallback declarado | EVENT | event/document/posting |
| `STOCK_SNAPSHOT` | producto × almacén × corte | product + warehouse + snapshot_at | STATE | snapshot obligatorio |
| `TRANSFER` | un documento de transferencia | source native id + type | EVENT | document/posting/system |
| `TRANSFER_LINE` | una línea de transferencia | source document + line | EVENT | event/document/posting |
| `PURCHASE_ORDER` | una línea de orden | source document + line | EVENT | document/due/close |
| `GOODS_RECEIPT` | una línea de recepción | source document + line | EVENT | event/document/posting |
| `PRODUCTION_ORDER` | una orden de producción | source native id | EVENT | order/due/release/close |
| `COMPONENT_CONSUMPTION` | una línea real de issue | source document + line | EVENT | event/document/posting |
| `PRODUCTION_OUTPUT` | una línea real de receipt | source document + line | EVENT | event/document/posting |
| `PAYMENT` | un documento de pago + dirección | native id + direction | EVENT | event/document/posting |
| `RECONCILIATION` | reconciliación × miembro | reconciliation + native id + line | EVENT | reconciliation/as-of |
| `CUSTOMER_CREDIT_STATE` | cliente × fecha as-of | customer + as_of + semantic version | DERIVED | as-of/system/extraction |

La denominación solicitada `PRODUCTION_COMPONENT` corresponde en el modelo canónico al hecho real `COMPONENT_CONSUMPTION`; `BOM_COMPONENT` conserva el requerimiento de fórmula. No se renombra el modelo en este gate.

### Snapshots y doble conteo

Las familias requeridas tienen política inequívoca suficiente para el diseño posterior.

| Familia | Clasificación | Regla segura |
|---|---|---|
| `movProduct` | `PERIOD_SNAPSHOT` de stock/agregado | No es movimiento atómico ni stock current. |
| `movProductSB1` | `PERIOD_SNAPSHOT` de observación business | No concatenar; atomicidad sólo con identidad fuerte. |
| `saleProduct` | `PERIOD_SNAPSHOT` | Seleccionar corte declarado; no sumar archivos. |
| `saleSB1Product` | `PERIOD_SNAPSHOT` | Misma venta observada en distintos cortes no es evento nuevo. |
| `purchase` | `PERIOD_SNAPSHOT` | Seleccionar última observación válida por línea/corte. |
| `purchaseExpense` | `PERIOD_SNAPSHOT` specialized | No convertir en segunda factura proveedor. |
| `cash` | `PERIOD_SNAPSHOT` specialized | No sumar meses sin identidad transaccional y corte. |
| `cuentasxCobrar` | `PERIOD_SNAPSHOT` de estado | No convertir en pago; conservar as-of. |
| `productTracking` | `PERIOD_SNAPSHOT` specialized | No convertir en movimiento sin equivalencia probada. |

OINM permanece `APPEND_ONLY_EVENT`; OITW es `CURRENT_STATE`; maestros legacy son `FULL_SNAPSHOT`; estados calculados son `DERIVED_SNAPSHOT`. Así se separan evento, estado, referencia y restatement.

### Identidad y continuidad Legacy ↔ SAP

La continuidad está lista como contrato, no como crosswalk materializado al 100%.

Los crosswalks de producto, cliente, proveedor, almacén, sucursal, vendedor y usuario exigen `canonical_id`, `source_system`, `source_native_id`, `valid_from`, `valid_to`, `mapping_source`, `confidence` y estado. Un mapping ambiguo queda `UNMAPPED/UNKNOWN` sin colisionar.

La selección de autoridad se conserva por concepto y ventana mediante `PRIMARY_SOURCE`, `HISTORICAL_SOURCE`, `SECONDARY_SOURCE` y `VALIDATION_SOURCE`. No existe cutover global implícito.

## E. Validaciones SAP realizadas

No se accedió a SAP/HANA porque ningún gap requirió evidencia adicional tras revisar contratos y artefactos existentes.

```text
SAP_ACCESSED=NO
SAP_ACCESS_PURPOSE=NONE
SAP_TARGETED_VALIDATIONS=0
SAP_WRITE_COUNT=0
```

`sap_targeted_validations.csv` contiene sólo el header contractual. No hay SQL ni hashes que registrar.

## F. Readiness matrix

La matriz es binaria por área y deriva de los ocho gaps revisados.

| Área | Estado | Evidencia | Impacto físico |
|---|---|---|---|
| Canonical grain | READY | 25 grains CORE V1; ambigüedad legacy en cuarentena. | Una entidad atómica conserva un grain declarado. |
| Identity | READY | 7 crosswalks versionados con UNKNOWN/UNMAPPED. | ID canónico y nativo no se confunden. |
| Temporal model | READY | event/document/posting/due/as-of/snapshot/extraction/validity separados. | Soporta estado actual, conocido en T y restatement. |
| Snapshot policy | READY | 16 políticas; no concatenación implícita. | Evita double counting y duplicación de eventos. |
| Legacy ↔ SAP | READY | Roles de autoridad y mappings parciales explícitos. | No hay cutover ni equivalencia fabricados. |
| Lineage | READY | 8 perfiles con REQUIRED/OPTIONAL/NOT_APPLICABLE. | Cada fila futura puede preservar origen y calidad. |
| Security scope | READY | 9 dominios, scopes y campos/métricas sensibles. | Seguridad futura antes de retrieval sigue siendo posible. |
| Atomic vs Business | READY | `movProductSB1` business; `movProduct` snapshot/agregado. | La denormalización no sustituye verdad atómica. |

La versión estructurada está en `readiness_matrix.csv`.

## G. Contratos de diferimiento seguro

Los seis diferimientos especifican qué debe preservar el futuro diseño sin anticipar su layout.

1. **GAP-001 — lineage legacy:** reservar el envelope canónico; conservar file/snapshot/extraction; usar calidad `PARTIAL`/`AGGREGATE_ONLY`; cuarentena si la identidad no permite suma.
2. **GAP-003 — `movProductSB1`:** no deduplicar por clave corta ni usarlo como atomic; conservar transacción/documento/línea cuando existan y toda la traza del snapshot.
3. **GAP-004 — warehouse→branch:** `warehouse_id` autoritativo, `branch_id` nullable, vigencia nullable si se desconoce, source/confidence/status obligatorios; no inventar fechas.
4. **GAP-010 — producción→despacho:** ninguna FK; un vínculo futuro será heurístico, versionado, con confianza y excluido de conteos autoritativos.
5. **GAP-017 — familias legacy especializadas:** identidades source-scoped, estado UNKNOWN/UNMAPPED y sin unión SAP hasta crosswalk confirmado y test anti-double-count.
6. **GAP-018 — crédito temporal:** conservar tiempo efectivo, snapshot, extracción, ingesta y versión; seleccionar autoridad por concepto/ventana y no sobrescribir hechos con restatements.

El texto íntegro y machine-readable está en `gap_resolution_contracts.csv` y `decision_log.csv`.

## H. Riesgos residuales

Los riesgos son conocimiento pendiente encapsulado y no bloquean la definición física del siguiente gate.

- Lineage histórico no recuperable puede limitar trazabilidad, pero no alterar grain ni identidad aceptada.
- Algunos mappings Legacy↔SAP permanecerán `UNMAPPED` y no participarán en métricas cross-source.
- Branch histórico puede ser null; el mapping actual 51→7 no se proyectará hacia atrás.
- `movProductSB1` puede conservar observaciones ambiguas, pero no generará eventos atómicos.
- Producción→despacho seguirá siendo heurístico hasta evidencia futura.
- Watermarks distintos limitan comparaciones as-of, no la capacidad de representarlas honestamente.

MRP/forecast permanece `CORE_LATER` con `CONFIGURED`, `OBSERVED`, `INFERRED` y `UNKNOWN` separados. Nómina detallada y WHT transaccional son `OUT_OF_INITIAL_SCOPE` y `NON_BLOCKING` para V1.

## I. Physical Design Readiness

La decisión binaria es positiva porque no queda ningún gap en `STILL_BLOCKING`.

```text
PHYSICAL_DESIGN_READY=YES
```

Las reglas vigentes evitan cambiar grain, colisionar identidades, duplicar hechos, perder lineage, fabricar temporalidad o impedir seguridad futura. Por tanto, el diseño físico puede comenzar sin inventar semántica.

## J. Recomendación siguiente

Entregar este resultado para revisión y no iniciar automáticamente el diseño físico.

El siguiente gate recomendado es `TELCHI_DATALAKE_PHYSICAL_PARQUET_DESIGN_V1`. Allí, y no aquí, podrán definirse datasets físicos, schemas, columnas, particionado, nombres, formatos, compresión, incrementalidad, snapshots materializados, read models y estrategia DuckDB.

## Evidencia reproducible

Los artefactos se generan desde decisiones declarativas y validan contra los ocho IDs bloqueantes de la autoridad canónica.

- `validation/datalake_physical_design_readiness_v1/build_outputs.py`
- `validation/datalake_physical_design_readiness_v1/test_validation.py`
- `validation/datalake_physical_design_readiness_v1/blocking_gaps_review.csv`
- `validation/datalake_physical_design_readiness_v1/readiness_matrix.csv`
- `validation/datalake_physical_design_readiness_v1/gap_resolution_contracts.csv`
- `validation/datalake_physical_design_readiness_v1/sap_targeted_validations.csv`
- `validation/datalake_physical_design_readiness_v1/decision_log.csv`
- `validation/datalake_physical_design_readiness_v1/summary.json`

## Cierre obligatorio

El cierre conserva los contadores y garantías solicitados.

```text
CANONICAL_MODEL_USED=YES
HISTORICAL_INVENTORY_USED=YES
SAP_KNOWLEDGE_INVENTORY_USED=YES

BLOCKING_GAPS_INITIAL=8

RESOLVED=2
RESOLVED_BY_TARGETED_VALIDATION=0
DEFERRED_WITH_SAFE_CONTRACT=6
STILL_BLOCKING=0

SAP_ACCESSED=NO
SAP_ACCESS_PURPOSE=NONE
SAP_TARGETED_VALIDATIONS=0
SAP_WRITE_COUNT=0

CANONICAL_GRAIN_READY=YES
IDENTITY_MODEL_READY=YES
TEMPORAL_MODEL_READY=YES
SNAPSHOT_POLICY_READY=YES
LEGACY_SAP_CONTINUITY_READY=YES
LINEAGE_READY=YES
SECURITY_SCOPE_READY=YES
ATOMIC_BUSINESS_BOUNDARY_READY=YES

PHYSICAL_DESIGN_READY=YES

PRODUCTION_PARQUETS_CREATED=0
DATALAKE_PHYSICAL_LAYOUT_CREATED=0
SOURCE_FILES_MODIFIED=0
SOURCE_FILES_MOVED=0
SOURCE_FILES_DELETED=0

TELCHI_DATALAKE_PHYSICAL_DESIGN_READINESS_V1_PASS
```
