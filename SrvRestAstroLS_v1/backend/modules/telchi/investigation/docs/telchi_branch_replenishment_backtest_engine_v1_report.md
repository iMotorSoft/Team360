# TELCHI — Branch replenishment backtest engine V1

Este reporte documenta el primer backtest reproducible sobre evidencia histórica, sin escribir SAP ni convertir resultados en recomendaciones productivas.

## A. Gate

El gate queda `DEGRADED`: el motor y sus validaciones pasan en Level A, pero todavía no se evaluó el universo completo ni el modo con origen restringido.

`TELCHI_REPLENISHMENT_BACKTEST_ENGINE_V1_DEGRADED`

El resultado no debe interpretarse como selección de política. La comparación sigue limitada por demanda censurada y por el fill rate observable del baseline.

## B. Contexto y alcance

La ejecución corresponde a `ENTITY=TELCHI`, `DOMAIN=REPOSICIÓN / STOCK_E_INVENTARIOS`, `STAGE=INVESTIGATION`, fuentes SAP/HANA + Data Lake y operación read-only.

| Campo | Resultado |
|---|---:|
| Branch | `2A` |
| Productos | 10 productos L de mayor demanda observada |
| Combinaciones | 10 `ItemCode × Branch` |
| Ventana | `2025-09-12..2026-09-11` |
| Filas diarias leídas | 639.480 |
| Simulaciones alternativas | 1.140 |
| Configuraciones de política | 19 |
| Escenarios de lead time | `0 / 1 / 2 / 3 / 5 / 7` días |
| Workers | 1 |
| SAP write count | 0 |

La selección Level A es deliberada: permite validar semántica y recursos antes de ampliar productos, sucursales o configuraciones simultáneamente.

## C. Semántica del motor

La convención intradía única es `opening → arrivals → policy → observed demand → closing`; la secuencia física dentro del día continúa desconocida.

Un pedido emitido en T con `LT=N` se agenda en `T+N`. Con `LT=0`, llega después de la decisión y antes de la demanda de T. El inventario simulado nunca es negativo:

```text
ClosingStock = OpeningStock + Arrivals - FulfilledDemand
UnfulfilledDemand = ObservedDemand - FulfilledDemand
```

Las medias, desviaciones, tendencia, clasificación híbrida y triggers utilizan únicamente días anteriores a la fecha de decisión. Durante los primeros 30 días se registra `WARMUP` y no se emiten órdenes dependientes de historia insuficiente.

## D. Validación del engine

Las pruebas sintéticas y la ejecución real Level A cubren las invariantes críticas del gate.

| Validación | Estado |
|---|---|
| `NO_LOOKAHEAD_TEST` | PASS |
| `INVENTORY_CONSERVATION` | PASS |
| `DETERMINISTIC_SIMULATION_TEST` | PASS |
| `LEAD_TIME_SCHEDULING` | PASS |
| `POLICY_TRIGGER` | PASS |
| `CURRENT_POLICY_COMPARISON` | PASS |
| `ZERO_DEMAND` | PASS |
| `CONSTANT_DEMAND` | PASS |
| `INTERMITTENT_DEMAND` | PASS |
| `SINGLE_FUTURE_SPIKE` | PASS |
| `PARETO_CLASSIFICATION` | PASS |
| `RESOURCE_GUARD` | PASS |

El test de no look-ahead modifica demanda posterior a T y verifica que decisiones anteriores a T permanezcan idénticas.

## E. Políticas implementadas

Solo se consideran implementadas las políticas que ejecutaron simulación end-to-end y produjeron métricas.

- `CURRENT_POLICY`: baseline descriptivo observado; no se inventa una fórmula.
- `MIN_MAX`: dos configuraciones acotadas.
- `REORDER_POINT`: niveles de servicio 95%, 97%, 98% y 99%.
- `DAYS_OF_SUPPLY`: targets 7, 14, 21, 30, 45 y 60 días.
- `PERIODIC_REVIEW`: revisiones cada 1, 3, 7 y 14 días.
- `DYNAMIC_TARGET`: target DOS 21 y 30 con tendencia simple y variabilidad.
- `HYBRID`: clasificación walk-forward entre periódico, dinámico y ROP.

No se ejecutó `SOURCE_CONSTRAINED`: no existe todavía disponibilidad histórica reconstruida del origen que pueda usarse sin inventar capacidad central.

## F. Baseline CURRENT del piloto

El baseline usa stock histórico no negativo para métricas de inventario y conserva el stock negativo como evidencia separada. El fill rate es una cota observable, no una estimación de ventas perdidas.

| Métrica | CURRENT Level A |
|---|---:|
| Inventario promedio medio por combinación | 1.216,58 |
| Stockout days promedio | 34,3 |
| Reposiciones promedio | 60,2 |
| Demanda observada total | 349.659 |
| Fill rate | 1,0000 sobre demanda observada |

El `1,0000` no significa servicio perfecto: `OBSERVED_DEMAND` solo contiene ventas observadas y no convierte automáticamente días sin stock en demanda perdida.

## G. Comparación resumida

La siguiente tabla resume promedios de las combinaciones del piloto para tres escenarios de lead time; no es un score único ni una selección de negocio.

| Política | LT | Fill rate | Inventario promedio | Stockout days | Reposiciones |
|---|---:|---:|---:|---:|---:|
| `MIN_MAX` | 0 | 0,8421 | 10.231,1 | 28,4 | 9,8 |
| `MIN_MAX` | 3 | 0,8319 | 9.960,8 | 33,1 | 9,7 |
| `MIN_MAX` | 7 | 0,7849 | 9.559,9 | 45,7 | 9,4 |
| `REORDER_POINT` | 0 | 0,8062 | 4.366,7 | 34,9 | 32,9 |
| `REORDER_POINT` | 3 | 0,7993 | 6.846,9 | 42,0 | 30,8 |
| `REORDER_POINT` | 7 | 0,7934 | 9.949,1 | 41,5 | 29,2 |
| `DAYS_OF_SUPPLY` | 0 | 0,8332 | 8.242,9 | 29,6 | 23,8 |
| `DAYS_OF_SUPPLY` | 3 | 0,8053 | 8.773,4 | 40,1 | 16,8 |
| `DAYS_OF_SUPPLY` | 7 | 0,7565 | 9.475,7 | 54,4 | 12,0 |
| `PERIODIC_REVIEW` | 0 | 0,8296 | 8.505,7 | 32,7 | 54,0 |
| `PERIODIC_REVIEW` | 3 | 0,8262 | 9.101,5 | 36,0 | 52,1 |
| `PERIODIC_REVIEW` | 7 | 0,8111 | 9.885,8 | 40,3 | 49,9 |
| `HYBRID` | 0 | 0,8356 | 7.776,9 | 31,0 | 15,6 |
| `HYBRID` | 3 | 0,8276 | 8.478,2 | 34,6 | 14,9 |
| `HYBRID` | 7 | 0,8248 | 9.521,3 | 36,8 | 14,2 |

El comportamiento agregado confirma sensibilidad importante a lead time; no justifica buscar una política óptima bajo LT=0 solamente.

## H. Pareto y robustez

El frente se calculó por servicio observado, inventario promedio y cantidad de reposiciones, sin score arbitrario.

| Estado | Filas de simulación |
|---|---:|
| `PARETO_OPTIMAL` | 395 |
| `DOMINATED` | 745 |
| `INCONCLUSIVE` por clasificación contra CURRENT | 921 |

`ROBUST_POLICY` se marca cuando la misma configuración producto/sucursal permanece Pareto-optimal en al menos cuatro escenarios de lead time. En Level A hubo 774 filas escenario/configuración con esa marca; esto es una señal de robustez para continuar investigando, no una recomendación.

## I. Casos trazados

El caso real seleccionado es `L00003 × 2A`, con ventana `2025-09-09..2025-09-30` alrededor de su primera reposición observada en la ventana. El trace conserva stock inicial, demanda, trigger, pedido, fecha de llegada, llegada y stock final.

La evidencia muestra que las políticas alternativas pueden reducir inventario o movimientos en casos concretos, pero el costo de servicio observado debe permanecer explícito. No se observó una mejora positiva de fill rate contra el baseline observable `CURRENT_POLICY`; el mejor delta del piloto fue negativo. Por ejemplo, `L00505 × 2A` con `DAYS_OF_SUPPLY`, LT=1, reduce inventario promedio en 896,30 unidades, pero reduce el fill observado en 24,83 puntos porcentuales y agrega 35 días de stockout.

La reducción de stockout de `L02467 × 2A` bajo una configuración ROP LT=0 no es un win ejecutivo: exige aproximadamente 37.104 unidades adicionales de inventario promedio y el fill observado cae a cero por la historia altamente censurada.

## J. Resource safety

La corrida terminó sin abortos y mantuvo el límite de un worker.

| Métrica | Level A |
|---|---:|
| `PEAK_RSS_MB` | 189,12 |
| `MIN_MEM_AVAILABLE_MB` | 5.702,64 |
| `MAX_BATCH_ROWS` | 639.480 |
| `MAX_IOWAIT` | 2,50% |
| `RESOURCE_ABORT_COUNT` | 0 |
| Tiempo | 19,73 s |
| Filas simuladas | 416.100 |

La evidencia del backtest se guardó fuera de Git en `validation/branch_replenishment_backtest/v1_level_A/` con `gate_result.json`, `current_policy.jsonl`, `policy_metrics.jsonl`, `traces.json` y `resource_metrics.jsonl`.

## K. Limitaciones y veredicto

El resultado permanece degradado por limitaciones semánticas conocidas y por el alcance Level A.

- `PHYSICAL_LEAD_TIME_NOT_OBSERVABLE`.
- `TRANSIT_PARTIALLY_UNRESOLVED`.
- `CENSORED_DEMAND_NOT_DIRECTLY_OBSERVABLE`.
- `CANCELLED_SALES_RESIDUAL`.
- El fill rate de CURRENT es observado, no fill rate físico completo.
- No se reconstruyó disponibilidad del origen para `SOURCE_CONSTRAINED`.
- La secuencia intradía física permanece `UNKNOWN`.

Conclusión V1: el motor ya puede demostrar operacionalmente trade-offs por producto, sucursal y lead time sin look-ahead. El piloto no demuestra todavía que exista una política mejor que CURRENT para el negocio completo y no autoriza decisiones productivas.

## L. Archivos

El código puro, el runner y los tests quedan aislados dentro del scope de investigación de reposición.

- `validation/branch_replenishment/backtest_engine_v1.py`
- `validation/branch_replenishment/run_backtest_engine_v1.py`
- `validation/branch_replenishment/test_backtest_engine_v1.py`
- Evidencia externa: `validation/branch_replenishment_backtest/v1_level_A/`

## M. Next gate

El siguiente paso controlado es Level B: 100 productos de 2A, manteniendo una sola dimensión de escalamiento y el mismo grid acotado, antes de considerar Level C/D.
