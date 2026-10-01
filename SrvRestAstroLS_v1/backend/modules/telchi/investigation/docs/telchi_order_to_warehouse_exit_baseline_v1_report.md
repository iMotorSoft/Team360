# TELCHI — Baseline cuantitativo pedido → salida registrada de almacén V1

## Gate

`TELCHI_ORDER_TO_WAREHOUSE_EXIT_BASELINE_V1 — DEGRADED`

El cálculo cuantitativo se ejecutó en modo SAP/HANA `READ ONLY`, reutilizando el
snapshot `2026-09-14 11:21:15` y las definiciones cerradas en Gates 1–3.

El veredicto es `DEGRADED`, no `PASS`, porque el estado vivo de SAP ya no
reproduce la cardinalidad activa congelada: devuelve 2.840 activos y 187
cancelados, frente a los 2.842 y 185 del snapshot. Esto no cambia los conteos de
primera salida, salida completa ni parciales, pero impide afirmar una
reconciliación por pedido completamente as-of sin una lista persistida de claves
activas del Gate 2.

## Cohorte congelada

| Cohorte | N | Cobertura sobre activos |
| --- | ---: | ---: |
| Activos canónicos | 2.842 | 100,00% |
| Primera salida medible | 2.631 | 92,58% |
| Salida completa medible | 2.561 | 90,11% |
| Parciales | 70 | 2,46% |
| Sin salida | 211 | 7,42% |
| Cancelados | 185 | fuera de eficiencia |

El cálculo reproducido desde el estado consultado obtuvo 2.840 activos, 2.631
primeras salidas, 2.561 completas, 70 parciales y 209 sin salida. La
reconciliación viva es 2.840; la reconciliación canónica sigue siendo:

```text
2.561 + 70 + 211 = 2.842
```

## Pedido → primera salida registrada

Duración de calendario transcurrido, sobre `N=2.631` pedidos con primera salida:

| Métrica | Minutos |
| --- | ---: |
| median | 1.470,333 |
| p25 | 1.247,833 |
| p75 | 2.943,633 |
| p90 | 5.598,333 |
| p95 | 7.028,183 |
| mean | 2.337,986 |
| min | 1,717 |
| max | 24.833,333 |

La mediana equivale a 24,51 horas y el p90 a 93,31 horas. El máximo no fue
eliminado; queda identificado en las muestras de validación.

## Pedido → salida completa

Sobre `N=2.561` pedidos con cantidad L% completamente salida:

| Métrica | Minutos |
| --- | ---: |
| median | 1.467,650 |
| p25 | 1.246,133 |
| p75 | 2.926,950 |
| p90 | 5.580,133 |
| p95 | 6.935,133 |
| mean | 2.320,970 |
| min | 1,717 |
| max | 24.833,333 |

La mediana equivale a 24,46 horas y el p90 a 93,00 horas.

## Pedido → factura

`N=2.635` con timestamp de factura compatible:

| Métrica | Minutos |
| --- | ---: |
| median | 1.452,283 |
| p90 | 5.492,450 |
| mean | 2.249,743 |
| min | 1,333 |
| max | 25.042,633 |

## Factura → salida registrada

Las métricas solo incluyen duraciones no negativas y semánticamente compatibles.

| Métrica | N | median | p90 | mean |
| --- | ---: | ---: | ---: | ---: |
| Factura → primera salida | 2.545 | 0,000 | 0,000 | 115,051 |
| Factura → salida completa | 2.476 | 0,000 | 0,000 | 118,257 |

Se identificaron 86 excepciones semánticas en `Factura → primera salida` y 85
en `Factura → salida completa`: corresponden a la ruta `ENTREGA`, donde la
factura se crea después de que la entrega ya registró el movimiento de
inventario. No se corrigieron ni se mezclaron silenciosamente con duraciones
válidas.

## Bandas observadas

| Banda | Primera salida N (%) | Salida completa N (%) |
| --- | ---: | ---: |
| <30m | 51 (1,94%) | 49 (1,91%) |
| 30–60m | 16 (0,61%) | 15 (0,59%) |
| 1–2h | 41 (1,56%) | 40 (1,56%) |
| 2–4h | 79 (3,00%) | 78 (3,05%) |
| 4–8h | 167 (6,35%) | 163 (6,37%) |
| 8–12h | 50 (1,90%) | 48 (1,87%) |
| 12–24h | 816 (31,01%) | 801 (31,28%) |
| >24h | 1.411 (53,63%) | 1.367 (53,38%) |

Los porcentajes tienen como denominador 2.631 y 2.561 respectivamente. Estas
son bandas observadas; no constituyen SLA.

## Calendario

| Clasificación | Primera salida | Salida completa |
| --- | ---: | ---: |
| SAME_DAY | 404 (15,36%) | 398 (15,54%) |
| NEXT_CALENDAR_DAY | 1.374 (52,22%) | 1.343 (52,44%) |
| GREATER_THAN_1_CALENDAR_DAY | 853 (32,42%) | 820 (32,02%) |
| <=24h | 1.220 (46,37%) | 1.194 (46,62%) |
| >24h | 1.411 (53,63%) | 1.367 (53,38%) |

`NEXT_CALENDAR_DAY` es descriptivo: no equivale necesariamente a más de 24
horas. Las duraciones internas conservaron precisión de segundos.

## Hora de ingreso

Las franjas usan la hora de `OrderDateTime` (`ORDR.CreateDate + CreateTS`).
Las medianas y p90 están en minutos; los porcentajes same-day usan como
referencia los pedidos con primera salida de cada franja.

| Franja | N | First median | First p90 | Complete median | Complete p90 | Same-day |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 00–07 | 48 | 509,200 | 1.645,210 | 509,200 | 1.645,210 | 82,22% |
| 07–09 | 322 | 474,700 | 3.168,307 | 465,400 | 3.110,533 | 60,98% |
| 09–11 | 662 | 1.529,150 | 4.551,733 | 1.526,683 | 4.470,767 | 19,15% |
| 11–13 | 676 | 1.468,100 | 5.780,530 | 1.467,117 | 5.783,093 | 2,51% |
| 13–15 | 326 | 1.527,842 | 5.931,198 | 1.524,183 | 5.910,600 | 7,14% |
| 15–17 | 371 | 1.417,533 | 5.739,070 | 1.415,433 | 5.677,683 | 7,00% |
| 17–19 | 244 | 2.377,908 | 9.457,158 | 2.382,017 | 9.495,333 | 0,91% |
| 19–24 | 191 | 1.147,883 | 5.017,547 | 1.149,717 | 4.913,127 | 0,00% |

Estos resultados sugieren una diferencia descriptiva por hora, pero no
prueban causalidad laboral u operativa.

## Hora de salida registrada

| Franja | Primera salida N (%) | Salida completa N (%) |
| --- | ---: | ---: |
| 00–07 | 0 (0,00%) | 0 (0,00%) |
| 07–09 | 59 (2,24%) | 58 (2,26%) |
| 09–11 | 721 (27,40%) | 707 (27,61%) |
| 11–13 | 643 (24,44%) | 626 (24,44%) |
| 13–15 | 439 (16,69%) | 424 (16,56%) |
| 15–17 | 520 (19,76%) | 507 (19,80%) |
| 17–19 | 220 (8,36%) | 211 (8,24%) |
| 19–24 | 29 (1,10%) | 28 (1,09%) |

Esto muestra olas de registro en SAP; no demuestra hora de salida física de un
vehículo.

## Rutas documentales

| Ruta | N de pedidos con ruta | Primera salida median / p90 (N) | Completa median / p90 (N) |
| --- | ---: | ---: | ---: |
| FACTURA_DIRECTA | 2.438 | 1.477,808 / 5.599,738 (2.438) | 1.474,617 / 5.583,193 (2.369) |
| ENTREGA | 86 | 38,967 / 248,808 (86) | 36,750 / 180,310 (85) |
| FACTURA_RESERVA→ENTREGA | 111 | 2.858,800 / 5.994,453 (107) | 2.858,800 / 5.994,453 (107) |

La ruta de reserva conserva 111 facturas, pero solo 107 tienen salida al corte;
4 quedan sin movimiento. La comparación es un sanity check, no un ranking
causal.

## Parciales

| Grupo | N | OrderedQty | ExitedQty | RemainingQty |
| --- | ---: | ---: | ---: | ---: |
| Cerrados documentalmente | 69 | 6.758 | 5.429 | 1.329 |
| Abierto | 1 | 948 | 648 | 300 |
| **Total** | **70** | **7.706** | **6.077** | **1.629** |

Los 70 participan en primera salida cuando existe, pero no en salida completa.

## Sin salida / backlog

El baseline canónico mantiene **211 / 2.842 = 7,42%** sin salida disponible.
El lote actualmente observable contiene 209 porque dos pedidos del snapshot
cambiaron a cancelado en SAP vivo; la clasificación canónica no se reescribe.

Sobre los 209 observables sin salida, la edad al corte fue:

| Métrica | Días |
| --- | ---: |
| N | 209 |
| median | 2,662 |
| p90 | 5,797 |
| p95 | 8,416 |
| max | 23,824 |

La descomposición observable fue 205 sin documento posterior y 4 facturas de
reserva sin salida. La causa detallada del backlog queda fuera de este gate.

## Data Quality

| Clase | Resultado |
| --- | --- |
| VALID | Todas las duraciones de Pedido→Factura, Pedido→Primera salida y Pedido→Salida completa no negativas (N=2.635, 2.631 y 2.561) |
| SEMANTIC_EXCEPTION | 86 Factura→Primera salida y 85 Factura→Salida completa por factura posterior a entrega/salida |
| INVALID_TIMESTAMP | 0 duraciones negativas inexplicadas |
| UNKNOWN | Sin timestamp: 205 Pedido→Factura, 209 Pedido→Primera salida y 279 Pedido→Salida completa en el estado vivo observado |
| Snapshot drift | 2 pedidos activos del snapshot aparecen cancelados en SAP vivo |

## Casos de validación manual

Se seleccionaron automáticamente cinco casos rápidos, cinco alrededor de la
mediana, cinco alrededor del p90 y cinco extremos. El artefacto JSON conserva
`OrderKey`, `OrderNumber`, timestamps, ruta y duración de cada caso.

Ejemplos trazables:

- rápido: `OrderKey=212589`, 1,717 minutos, `ENTREGA`;
- mediana: `OrderKey=211253`, 1.470,333 minutos, `FACTURA_DIRECTA`;
- p90: `OrderKey=213756`, 5.598,333 minutos, `FACTURA_DIRECTA`;
- extremo: `OrderKey=210920`, 24.833,333 minutos, `ENTREGA`.

La validación confirma la consistencia aritmética de los timestamps usados por
el agregado. No se afirma causalidad para los extremos.

## Hallazgos cuantitativos

1. La mediana de primera salida es 1.470,333 minutos y la de salida completa
   1.467,650 minutos; el p90 es aproximadamente 93 horas para ambas.
2. El 15,36% comienza a registrar salida el mismo día y el 46,37% lo hace en
   24 horas o menos; para salida completa son 15,54% y 46,62%.
3. Más de 24 horas concentra 53,63% de primeras salidas y 53,38% de salidas
   completas.
4. La salida registrada se concentra entre 09:00 y 17:00: 2.323 de 2.631
   primeras salidas (88,29%). Esto no equivale a salida física.
5. La ruta `ENTREGA` registra tiempos menores que las otras rutas, mientras que
   la reserva→entrega conserva un tramo documental más largo; la diferencia no
   se interpreta todavía como causalidad de picking.

## Limitaciones

- `CreateDate + CreateTS` representa creación del documento generador en SAP,
  no salida física del camión ni entrega al cliente.
- El cálculo inicial es tiempo calendario transcurrido; no descuenta noches,
  fines de semana ni feriados.
- La cohorte activa exacta por clave no quedó persistida en Gates 1–3; por eso
  el drift de 2 cancelaciones obliga a `DEGRADED`.
- `Factura → salida` no es un proxy automático de picking; en la ruta entrega
  puede ser negativo por el orden documental.
- No se analizaron todavía sucursal, vendedor, stock, producción ni causas de
  outliers. Eso corresponde a Gates posteriores.
- No se mide entrega física, ruta de reparto, POD ni recepción del cliente.

## Recursos

- `SAP_WRITE_COUNT=0`.
- 2 consultas HANA acotadas, secuenciales, con columnas explícitas y join
  canónico `TransType + CreatedBy + DocLineNum + ItemCode + Warehouse`.
- Un proceso y un thread numérico; `OMP_NUM_THREADS=1`.
- Sin pandas, multiprocessing, contenedores ni servicios adicionales.
- Tiempo observado: aproximadamente 6,8 s; RSS máxima del runner: 40,5 MiB.
- No se reiniciaron ni detuvieron procesos ajenos.

## Archivos

- `validation/order_delivery_efficiency/order_to_warehouse_exit_baseline_v1.py`
- `validation/order_delivery_efficiency/test_order_to_warehouse_exit_baseline_v1.py`
- `docs/telchi_order_to_warehouse_exit_baseline_v1_report.md`
- Evidencia externa: `validation/order_delivery_efficiency/evidence/order_to_warehouse_exit_baseline_v1.json`

## Validaciones

- `py_compile`: PASS.
- Tests focalizados Gate 3 + Gate 4: **8 passed**.
- `SAP_WRITE_COUNT=0`: PASS.
- `git diff --check`: PASS.
- LAT `md`, `index`, `sections`, `code-refs` y `check`: PASS.

## Siguiente paso

No ejecutar Gate 5 todavía. Primero persistir la lista de claves activas del
snapshot o resolver explícitamente el drift de estado; después puede repetirse
este mismo cálculo para cerrar `PASS` sin reinterpretar SAP vivo.
