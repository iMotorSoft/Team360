# TELCHI — Current Policy Baseline + Operational Lead Time V1

**Gate:** `TELCHI_CURRENT_POLICY_BASELINE_V1`\
**Context:** `ENTITY=TELCHI` · `DOMAIN=REPOSICIÓN / STOCK_E_INVENTARIOS` · `STAGE=INVESTIGATION`\
**Scope:** `ItemCode LIKE 'L%'` · branches `2A` y `CM` · 365 días `2025-09-12..2026-09-11`\
**Estado:** `DEGRADED` · `READ ONLY` · `SAP_WRITE_COUNT=0` · `MAX_WORKERS=1`

## 1. Respuesta ejecutiva: ¿cómo repone hoy Telchi?

En el universo observado, Telchi repone principalmente mediante un flujo **push
contabilizado desde almacenes de tránsito hacia los salones**. Se observaron
`16.446 TRANSIT_TRANSFER`, `875.289,255` unidades y `208 CENTRAL_TRANSFER`,
`18.902` unidades. La producción directa al branch también aparece (`180`
eventos, `95.895` unidades), pero no se observa una solicitud física ni un
punto de pedido documentado.

La frecuencia no es única: la mediana entre eventos por `ItemCode × Branch` es
**6 días**, el p90 **16,4 días** y el máximo observado **329 días**. El tamaño
mediano es **24 unidades**, p90 **108** y máximo **100.000**; la media global
(**58,53**) está afectada por outliers. Antes de reponer, el stock conocido
tiene mediana **29** y p90 **135**; el DOS-30D conocido tiene mediana
**16,96 días**.

La operación no es puramente reactiva, pero sí tiene una fracción relevante
posterior al quiebre: **18,96%** de los eventos preceden un episodio de stockout,
**1,66%** ocurre durante él, **20,88%** después de él y **58,50%** no tiene un
contexto de stockout observable en la ventana. Esto describe evidencia; no
prueba una regla formal ni una política óptima.

## 2. Método reproducible

1. Se consumió el Level E previamente reconciliado: **639.480** filas diarias,
   **2A + CM**, 365 días, **876** productos activos y **1.353** combinaciones
   `ItemCode × Branch` con eventos observados.
2. El stock previo se tomó del día anterior al evento. El día del evento se
   conserva como fin de día y se ajusta con
   `CONCURRENT_NET_MOVEMENT = NET_MOVEMENT_DAY - REPLENISHMENT_QTY`.
3. La secuencia intradía se marca siempre `UNKNOWN`: la fecha/hora contable no
   demuestra el orden físico venta → preparación → despacho → recepción.
4. `AVG_DEMAND_7D/30D/60D/90D` y `DAYS_OF_SUPPLY_*` usan exclusivamente días
   anteriores al evento; ventanas incompletas quedan `INSUFFICIENT_HISTORY`.
5. Las clases de política usan CV de timing, cantidad y trigger. Sus umbrales
   son medianas y p75 de la distribución real de combinaciones, no umbrales
   comerciales prefijados. `LOW_STOCK` no se introduce.

No se imputan ventas perdidas: la demanda es `OBSERVED_DEMAND` y los episodios
se mantienen como `POSSIBLE_CENSORED_DEMAND` cuando corresponde.

El resource guard permaneció activo durante la corrida: `MAX_WORKERS=1`,
`RESOURCE_ABORT_COUNT=0`, peak RSS **309,05 MiB** y `MemAvailable` mínimo
**6.296,76 MiB**. La primera lectura en representación JSON completa fue
abortada correctamente por superar el límite de +1 GiB; el runner se corrigió a
una representación compacta y la corrida final pasó sin relajar la protección.

## 3. Métricas por sucursal

| Branch | Item×Branch activos | Eventos | Qty total | Frecuencia media de pares (días) | Pares reactivos | Sin política detectable |
|---|---:|---:|---:|---:|---:|---:|
| 2A | 876 | 9.774 | 710.580,270 | 43,90 | 18,26% | 332 |
| CM | 876 | 7.179 | 281.724,985 | 49,67 | 20,43% | 354 |

La frecuencia de sucursal es el promedio no ponderado de las frecuencias de sus
combinaciones con al menos dos eventos; no es una cadencia comercial global.

## 4. Fuentes logísticas observadas

| Categoría | Eventos | Qty |
|---|---:|---:|
| `TRANSIT_TRANSFER` | 16.446 | 875.289,255 |
| `CENTRAL_TRANSFER` | 208 | 18.902 |
| `BRANCH_TRANSFER` | 1 | 4 |
| `PRODUCTION_IN` | 180 | 95.895 |
| `PURCHASE_IN` | 0 | 0 |
| `OTHER_LOGISTIC_IN` | 118 | 2.215 |
| **Total** | **16.953** | **992.305,255** |

`INVENTORY_ADJUSTMENT` no se considera reposición y quedó excluido de los
eventos. Las devoluciones y entradas de ventas se auditaron como movimientos,
pero no se etiquetaron como reposición física.

## 5. Trigger observado y clasificación

Distribución de `ItemCode × Branch`:

| Clase | Combinaciones |
|---|---:|
| `MIN_MAX_LIKE` | 276 |
| `REACTIVE_TO_STOCKOUT` | 339 |
| `REORDER_POINT_LIKE` | 210 |
| `FIXED_QTY` | 93 |
| `PERIODIC` | 60 |
| `DEMAND_TRIGGERED` | 27 |
| `PUSH_FROM_CENTRAL` | 17 |
| `MANUAL_IRREGULAR` | 44 |
| `NO_CLEAR_POLICY` | 92 |
| `INSUFFICIENT_EVENTS` | 594 |
| **Total** | **1.353** |

Confianza de la clasificación: **682 HIGH**, **381 MEDIUM**, **689 LOW**. Las 399 combinaciones sin evento observado se retienen explícitamente como `INSUFFICIENT_EVENTS`.
`MIN_MAX_LIKE`, `REORDER_POINT_LIKE`, `PERIODIC`, `FIXED_QTY` y las demás
clases son similitudes observadas, no afirmaciones de que SAP tenga esa regla.

## 6. Stockout relativo a la reposición

| Contexto | Eventos | Porcentaje |
|---|---:|---:|
| `BEFORE_STOCKOUT` | 3.215 | 18,96% |
| `AT_STOCKOUT` | 282 | 1,66% |
| `AFTER_STOCKOUT` | 3.539 | 20,88% |
| `NO_STOCKOUT_CONTEXT` | 9.917 | 58,50% |
| **Total** | **16.953** | **100%** |

La proporción estrictamente `AT_OR_AFTER_STOCKOUT` es **22,54%**. Stock
`STOCK_BEFORE <= 0` se observó en **1.654** eventos; 67 eventos no tienen stock
previo disponible por el borde de la ventana o ausencia de serie.

## 7. Lead time

### 7.1 Lead time contable

Se cruzaron las líneas activas `OWTR/WTR1` contra `OINM` `TransType=67` por
`DocNum/BASE_REF`, `ItemCode`, almacén y línea. Resultado: **16.774/16.774**
líneas con ambos lados contables.

- **16.762** tienen exactamente el mismo `DocDate + DocTime` en origen y
  destino: `ACCOUNTING_LEAD_TIME_NOT_OBSERVABLE_SIMULTANEOUS`.
- **12** tienen una diferencia de **1 segundo**; son diferencias de registro
  (`p50=p90=0,0000116 días`), no evidencia de duración logística.
- No se convierte el cero contable en `PHYSICAL_LEAD_TIME`.

Por tanto, el estado es
`ACCOUNTING_LEAD_TIME_NOT_OBSERVABLE` para inferir una duración física. El
campo contable sí permite probar que SAP registra ambos lados en el mismo acto.

### 7.2 Lead time físico

La inspección de `OWTR` no encontró valores poblados en `ReqDate`,
`StDlvDate/StDlvTime`, `EndDlvDate/EndDlvTime` ni en los campos UDF
`U_FECHEST_EMBR`, `U_FECHPRTO`, `U_FECHALM`, `U_FECHREAL_EMBR` y
`U_FECHREAL_PRTO`. No existe una cadena demostrada
`solicitud → preparación → despacho → recepción`.

No se calcula `PHYSICAL_LEAD_TIME` ni se renombra el proxy
`STOCKOUT_TO_REPLENISHMENT_DELAY` como lead time logístico.

## 8. Transit e incidencias documentales

- `IN_TRANSIT_STOCK=UNRESOLVED`: **110** posiciones no cero, **109** productos,
  **4.119,98** unidades en almacenes clasificados como tránsito. No es posible
  asignarlas físicamente a un branch con la evidencia disponible.
- Cancelaciones `OINV/INV1` en la ventana: **11 documentos**, 28 líneas, 555
  unidades; 25 líneas y **224 unidades** no encontraron linkage OINM directo.
  `ORIN/RIN1`: 2 documentos, 6 líneas, sin impacto no resuelto. El impacto
  no resuelto equivale a **0,028%** de las 810.564 unidades de demanda observada,
  pero se conserva como degradación.
- Se mantienen separados los movimientos de devoluciones, cancelaciones,
  reversas y ajustes; no se usan para inventar una regla de reposición.

## 9. Casos reales trazados

El artefacto `real_cases.json` contiene 15 casos seleccionados
reproduciblemente. Incluye alta rotación (`L00003`), baja/intermitente
(`L02467`, `L03234`), eventos antes/durante/después de stockout, producción,
transferencia de tránsito, múltiples fuentes, cantidad extrema y casos sin
stockout observable. Cada caso conserva fecha, stock previo, ventas 7/30 días,
cantidad, fuente, stock ajustado posterior, contexto de stockout y siguiente
reposición.

## 10. Artefactos y código

Código fuente:

- `validation/branch_replenishment/current_policy_baseline_v1.py`
- `validation/branch_replenishment/run_current_policy_baseline_v1.py`
- `validation/branch_replenishment/test_current_policy_baseline_v1.py`

Evidencia externa:

- `branch_replenishment_current_policy_baseline/v1/gate_result.json`
- `item_branch_baseline.jsonl`
- `branch_baseline.jsonl`
- `replenishment_events_enriched.jsonl`
- `rankings.json`
- `real_cases.json`
- `lead_time_audit.json`

El siguiente paso puede comparar este baseline descriptivo contra MIN/MAX,
ROP, DAYS_OF_SUPPLY, PERIODIC, DYNAMIC e HYBRID. Este gate no selecciona ni
recomienda ninguna de esas políticas.
