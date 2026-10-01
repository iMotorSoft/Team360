# TELCHI — Baseline pedido → salida de Laboratorio V1

Este gate reutiliza la cohorte congelada y detiene el cálculo si SAP no demuestra un único almacén de producto terminado para Laboratorio.

## Gate

El alcance del Laboratorio queda bloqueado por ambigüedad de código, sin mezclarlo con Saavedra.

`TELCHI_LAB_ORDER_TO_WAREHOUSE_EXIT_BASELINE_V1 — BLOCKED`

Causa: OWHS contiene cuatro almacenes activos de producto terminado bajo LAB y los movimientos de salida de la cohorte impactan más de uno. No es válido elegir uno por prefijo o por conveniencia.

## Snapshot y cohorte

La consulta no redefinió la población con SAP vivo.

| Elemento | Valor |
| --- | ---: |
| Snapshot | `2026-09-14 11:21:15` |
| Ventana | `2026-08-15` a `2026-09-14` |
| Pedidos activos congelados | 2.842 |
| Primera salida Gate 3 | 2.631 |
| Salida completa Gate 3 | 2.561 |
| Parciales Gate 3 | 70 |
| Sin salida Gate 3 | 211 |

La lista individual de activos del snapshot no quedó persistida en Gates 1–3. Por eso no se recalculó una subcohorte histórica con el estado mutable actual.

## Almacén Laboratorio

OWHS es concluyente respecto de la existencia de varios candidatos, pero no respecto de un único `LAB_WAREHOUSE_CODE`.

| Código | Nombre OWHS | Estado | Pedidos con salida L% en rutas cerradas |
| --- | --- | --- | ---: |
| `LAB-T1` | Almacén Producto Terminado AGEMED | activo | 45 |
| `LAB-T2` | Almacén Producto Terminado SENASAG | activo | 19 |
| `LAB-T3` | Almacén Producto Terminado INDUSTRIAL | activo | 48 |
| `LAB-T4` | Almacén Producto Terminado MAGISTRAL | activo | 6 |

Los conteos son por código y no deben sumarse como pedidos únicos: un pedido puede tener más de una línea o más de un almacén.

### Evidencia de almacenes de despacho

La descripción de `LAB-DES` es `Almacén Despacho Laboratorio.` y la de `LAB-D0` es `Almacen Picking (Despacho)`. Sin embargo, ambos tienen cero pedidos con salida en las rutas documentales congeladas consultadas. No se promovieron a almacén canónico.

`LAB-M1` aparece en OWHS como `Almacén Materia Prima` y queda explícitamente fuera del circuito de producto terminado.

## Filtro de movimiento

La evidencia se obtuvo únicamente con `OINM.OutQty > 0`, vinculado por la clave cerrada.

```text
TransType + CreatedBy + DocLineNum + ItemCode + Warehouse
```

El resumen se limitó a los documentos generadores de la cohorte y a las rutas documentales ya auditadas. No hubo scan abierto de OINM ni join suficiente por `BASE_REF`.

## Métricas de Laboratorio

No se calcularon `OrderToLabFirstExitMinutes`, `OrderToLabCompleteExitMinutes`, percentiles, bandas, días, franjas horarias, multi-warehouse ni casos reales. Hacerlo antes de resolver el código produciría una métrica potencialmente mal adjudicada.

Por la misma razón, este gate no clasifica `LAB_ONLY`, `LAB_PLUS_OTHER` u `OTHER_ONLY` de forma canónica: primero debe definirse si Laboratorio significa `LAB-T1`, uno de `LAB-T1..LAB-T4`, o un circuito agrupado explícito.

## Saavedra discovery

El discovery fue mínimo y acotado a la misma ventana. No se calcularon tiempos de eficiencia de Saavedra.

| Candidato OWHS | Nombre | Observación |
| --- | --- | --- |
| `SAA-M1` | Almacén Prod. a Granel Procesadora Saavedra | candidato de origen de materia prima; no promovido todavía |
| `SAA-P1` | Almacén de Proceso Saavedra | proceso |
| `SAA-T1` | Almacén Producto Terminado Proc. Saavedra | producto terminado |
| `SAA-T2` | Almacén de Reacondicionado Saavedra | reacondicionado |
| `SAA-T3` | Almacén de Reacondicionado Saavedra | reacondicionado |
| `SAA-DAN` | Almacén Productos Dañados Saavedra | dañados |

### Rutas observadas

La consulta agrupó `OWTR/WTR1` activos por origen, destino, `ObjType` y `DocType`.

| Origen | Destino | ObjType | Docs | Líneas | Cantidad |
| --- | --- | ---: | ---: | ---: | ---: |
| `SAA-M1` | `SAA-P1` | 67 | 88 | 313 | 294.293,5947 |
| `SAA-P1` | `SAA-T1` | 67 | 36 | 187 | 258.578,9943 |
| `SAA-T1` | `LAB-T3` | 67 | 22 | 76 | 96.404 |
| `SAA-M1` | `LAB-T3` | 67 | 21 | 34 | 37.688 |
| `SAA-M1` | `LAB-M1` | 67 | 12 | 36 | 87.775,705 |
| `SAA-T1` | `LAB-T2` | 67 | 11 | 24 | 74.783 |
| `LAB-M1` | `SAA-M1` | 67 | 9 | 23 | 102.417,866 |

La evidencia muestra que `SAA-M1` abastece `SAA-P1` y también tiene transferencias hacia `LAB-M1`, pero no demuestra todavía el circuito completo necesidad → salida → ingreso → consumo. Las rutas hacia `LAB-T*` no se interpretan automáticamente como materia prima.

En el período hubo 126 documentos, 389 líneas y cantidad 427.987,2997 con origen `SAA-M1`. Los documentos activos observados fueron de tipo `ObjType=67`.

## Calidad y límites

Se mantuvo `LIVE_SAP_DRIFT` como condición del baseline histórico: SAP vivo no se utilizó para cambiar los 2.842 activos congelados. El timestamp autorizado para el futuro cálculo será `CreateDate + CreateTS` del documento generador.

No se puede afirmar todavía:

- que un único almacén LAB represente todo el producto terminado del Laboratorio;
- que `LAB-DES` sea el origen contable de la salida de pedidos;
- que una demora del pedido se deba a materia prima;
- que Saavedra → Laboratorio sea siempre directo;
- que una transferencia SAP equivalga a movimiento físico.

## Recursos

La ejecución fue secuencial y de bajo impacto.

| Recurso | Resultado |
| --- | --- |
| SAP/HANA | READ ONLY |
| `SAP_WRITE_COUNT` | 0 |
| Consultas | 4, acotadas |
| Procesos | 1 |
| Threads numéricos | `OMP_NUM_THREADS=1` |
| pandas / multiprocessing | no usados |
| RSS máxima del runner | 38,1 MiB |
| Tiempo observado | 7,760 s |
| Servicios reiniciados | ninguno |

## Evidencia y código

El runner y la evidencia quedan separados de los reportes previos.

- `validation/order_delivery_efficiency/lab_order_to_warehouse_exit_baseline_v1.py`
- `validation/order_delivery_efficiency/test_lab_order_to_warehouse_exit_baseline_v1.py`
- Evidencia externa: `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi/investigation-consolidation-v1/files/validation/order_delivery_efficiency/evidence/lab_order_to_warehouse_exit_baseline_v1.json`
- Semántica previa: `telchi_warehouse_exit_semantics_v1_report.md`
- Baseline global previo: `telchi_order_to_warehouse_exit_baseline_v1_report.md`

## Siguiente paso

Solicitar la decisión operativa que fije el universo exacto: un código (`LAB-T1`, `LAB-T2`, `LAB-T3` o `LAB-T4`) o un conjunto explícito de almacenes de producto terminado. Con esa autorización se puede congelar `LAB_WAREHOUSE_CODE` o un contrato de grupo y ejecutar el baseline cuantitativo sin mezclar circuitos.
