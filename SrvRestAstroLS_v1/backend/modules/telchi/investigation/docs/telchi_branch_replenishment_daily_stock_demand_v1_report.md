# TELCHI — Branch Stock Replenishment
## Gate 2/3 — Demanda + stock histórico diario V1

**Contexto:** `ENTITY=TELCHI` · `DOMAIN=REPOSICIÓN / STOCK_E_INVENTARIOS` · `STAGE=INVESTIGATION` · `SAP_HANA + DATA_LAKE` · `READ ONLY` · `SAP_WRITE_COUNT=0` · `ItemCode LIKE 'L%'`.

## Implementación

- `validation/branch_replenishment/stock_demand_domain.py`: contrato puro y testeable para reconstrucción inversa, continuidad, reconciliación, disponibilidad, demanda observada, episodios y métricas.
- `validation/branch_replenishment/daily_stock_demand_v1.py`: extracción HANA set-based, clasificación de movimientos y generación de evidencia externa.
- Los datasets se escriben fuera de Git bajo `EVIDENCE_ROOT` cuando se ejecuta el runner.

## Semántica

`NET_MOVEMENT = InQty - OutQty`. La serie histórica se reconstruye desde `OITW.OnHand` actual:

```text
StockEndOfDay(d) = CurrentOnHand - SUM(NetMovement(k) for k > d)
```

No se asume stock inicial cero. Los días sin movimiento se materializan por continuidad. La reconciliación del último día se compara por `ItemCode × Warehouse` con OITW.

Categorías preservadas: `SALES`, `RETURNS`, `TRANSFER`, `PRODUCTION_IN`, `PRODUCTION_CONSUMPTION`, `PURCHASE_IN`, `PURCHASE_RETURN`, `INVENTORY_ADJUSTMENT`, `OTHER`.

Ventas observadas usan movimientos SAP validados `TransType 13/15`; devoluciones `14/16`; transferencias `67` no se mezclan con ventas. La cancelación se audita por documento y no se infiere solamente por `TransType`.

## Demanda censurada y stockout

- `ZERO_STOCK` y `NEGATIVE_STOCK` son estados de disponibilidad, no ventas perdidas.
- `LOW_STOCK` queda `PENDING_POLICY_THRESHOLD` hasta que Telchi valide un umbral.
- `POSSIBLE_CENSORED_DEMAND` requiere patrón pre/post y reposición; en caso contrario se conserva `UNPROVEN_CENSORED_DEMAND`.
- No se calcula `LOST_SALES`.

Los episodios conservan stock previo, última venta anterior, reposición posterior, primera venta posterior, demanda 30 días antes/después y confianza `STRONG`, `WEAK` o `UNKNOWN`.

## Reposición

Se extraen transferencias activas OWTR/WTR1 con cantidad positiva hacia almacenes `BRANCH_SALES`. El origen conserva rol y tipo (`TRANSFER_FROM_CENTRAL`, `TRANSFER_FROM_TRANSIT`, `TRANSFER_FROM_BRANCH`, `PRODUCTION_DIRECT`, etc.). Los ajustes y reversas no se etiquetan automáticamente como reposición logística. `IN_TRANSIT_STOCK` se mantiene separado de `AVAILABLE_BRANCH_STOCK`.

## Look-ahead

Las métricas de cobertura usan únicamente el intervalo `[t-30, t)`. El día `t` y fechas futuras no entran en la media. El test unitario cambia datos futuros y demuestra que una métrica pasada no cambia.

## Artefactos del runner

- `daily_item_warehouse_stock.jsonl.gz` (almacenes `BRANCH_SALES`, ventana comparable)
- `daily_item_branch_stock.jsonl.gz`
- `daily_branch_demand.jsonl.gz`
- `replenishment_events.jsonl.gz`
- `stockout_episodes.json`
- `reconciliation.json`
- `gate_result.json`

## Controlled Scale-Up V2

Runner: `validation/branch_replenishment/scale_up_v2.py`. Evidencia externa:
`.../validation/branch_replenishment_daily_stock_demand/v2_scale_up/`.

Todos los niveles se ejecutaron secuencialmente con `MAX_WORKERS=1`, batches de productos, liberación explícita de memoria y checkpoints append-only:

| Nivel | Branches | Productos | Días | OINM rows | Output rows | Tiempo s | Rows/s | Peak RSS MiB | Min MemAvailable MiB | Checkpoint MiB | iowait máximo | Abort | Reconciliación |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| A | 2A | 10 | 90 | 11.014 | 3.776 | 3,99 | 2.763 | 37,11 | 7.215,78 | 0,049 | 3,80% | 0 | 20/20 |
| B | 2A | 675 | 90 | 42.096 | 245.465 | 109,99 | 383 | 36,98 | 7.057,24 | 1,495 | 41,56% | 0 | 1.350/1.350 |
| C | 2A | 819 | 365 | 172.172 | 1.206.192 | 153,81 | 1.119 | 41,25 | 5.348,45 | 5,743 | 32,05% | 0 | 1.638/1.638 |
| D | CM | 642 | 90 | 39.716 | 175.069 | 186,11 | 213 | 37,47 | 4.535,39 | 1,307 | 20,99% | 0 | 642/642 |
| E | 2A+CM | 876 | 365 | 331.816 | 2.256.577 | 341,08 | 973 | 40,91 | 5.301,07 | 10,891 | 16,88% | 0 | 2.628/2.628 |

En todos los niveles: `mismatch=0`, `unknown=0`, `continuity_gaps=0`, `continuity_movement_violations=0`, `RESOURCE_ABORT_COUNT=0` y `SAP_WRITE_COUNT=0`. La reconciliación usa `ItemCode × Warehouse` y tolerancia `1e-6`, no una suma agregada por sucursal.

### Validación semántica V2

- La transferencia activa se reconcilia por `OWTR/WTR1` neto contra `OINM TT67` enlazado por `BASE_REF + ItemCode + Warehouse`, excluyendo headers cancelados y sin confundir transferencias salientes con entradas de sucursal.
- La validación cerró con `transfer_delta=0` en A–E y separación ventas/transferencias `PASS`.
- El smoke B inicial mostró una diferencia aparente de 112 unidades; el contraejemplo fue un documento cancelado y su reversa activa. Se corrigió el criterio para comparar únicamente documentos activos emparejados. La regresión quedó protegida por la ejecución A–E.
- Episodios stockout: B 168, C 808, D 132, E 1.623. Se mantienen como estado de stock confirmado; la demanda perdida no se imputa. En E: 1.097 `POSSIBLE_CENSORED_DEMAND` y 526 `UNPROVEN_CENSORED_DEMAND`.

### Semántica aún pendiente

El escalamiento no convierte el gate funcional en `PASS`: permanecen `IN_TRANSIT_STOCK` sin asignación física por sucursal, umbral `LOW_STOCK` pendiente de política, linkage exhaustivo por documento de ventas/devoluciones canceladas y demanda censurada no observable. Por ello el estado correcto continúa `FUNCTIONAL_STATUS=DEGRADED`, aunque `RESOURCE_SAFETY=PASS` y la reconstrucción/reconciliación de A–E pasan.

## Resource Safety Gate

`TELCHI_RESOURCE_SAFETY_GATE_V1` quedó habilitado en el runner:

- `MAX_WORKERS=1`; no hay multiprocessing ni ejecución paralela.
- La ejecución por defecto es una muestra real: una sucursal, 1–10 productos L y 60–90 días.
- OINM se filtra y agrega en HANA por sucursal, productos y rango temporal; no se carga OINM completo en RAM.
- El batch se checkpointa antes de reconstruir y cada etapa registra `rows_read`, `rows_written`, `elapsed_seconds`, `peak_rss_mb`, `mem_available_min_mb`, `batch_size`, `partition` y `result`.
- Si `MemAvailable < 2 GiB`, RSS crece más de 1 GiB o se observan dos ventanas consecutivas de iowait alto, termina con `RESOURCE_GUARD_ABORT`; no continúa automáticamente.
- El tamaño de muestra se reduce automáticamente con menor memoria disponible.

### Smoke real 2026-09-11

Salida externa: `.../validation/branch_replenishment_daily_stock_demand/v1/smoke_20260911_r2/`.

- `TELCHI_DAILY_STOCK_RESOURCE_SMOKE_TEST_V1_PASS`.
- Branch `2A`; almacenes `2A-SAL`, `2A-SMK`; 5 productos L; 60 días (`2026-07-14..2026-09-11`).
- 4.976 filas OINM leídas en la muestra, 426 proyecciones agregadas; 600 filas `ItemCode×Warehouse×Date`, 300 filas branch/día y 57 eventos de reposición.
- Reconciliación actual: **10/10 exactas**, diferencias 0, máxima 0,0.
- `RESOURCE_SAFETY=PASS`; `PEAK_RSS=37,49 MiB`; `MIN_MEM_AVAILABLE=5.947,30 MiB`; `MAX_BATCH_ROWS=5.033`; `RESOURCE_ABORT_COUNT=0`; ventanas de iowait alto consecutivas `0`; `SAP_WRITE_COUNT=0`.
- El smoke no habilita todavía una corrida branch/multi-branch/universe; queda como gate previo al escalamiento.

## Tests

`17 passed` en el contrato focalizado. Incluyen reconciliación, continuidad, días sin movimiento, semántica de movimientos, episodios, clasificación conservadora, reposición, ausencia de look-ahead, niveles de escala y controles del resource gate.

## Veredicto

El runner no debe declarar `PASS` por pytest solamente. El cierre real requiere ejecutar BUILD → RUN → RECONCILE → TRACE REAL CASE → FIND COUNTEREXAMPLE → FIX → REPEAT contra HANA. El resultado actual permanece `DEGRADED`: el smoke de recurso y la reconciliación de la muestra pasan, pero la expansión por niveles (`sample → branch → multi-branch → universe`) y la validación documental/cancelaciones por universo aún no están autorizadas.

## Next gate

`GATE 4 — BASELINE CUANTITATIVO + LEAD TIME OPERATIVO`: descubrir nivel de stock previo, tamaño/frecuencia de reposición y lead time contable, sin inferir todavía una política óptima.
