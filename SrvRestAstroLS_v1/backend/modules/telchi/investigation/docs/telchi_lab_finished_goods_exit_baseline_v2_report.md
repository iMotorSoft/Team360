# TELCHI — Baseline salida de producto terminado Laboratorio V2

## Gate

`TELCHI_LAB_FINISHED_GOODS_EXIT_BASELINE_V2 — DEGRADED`

El cálculo aplica Laboratorio como familia de almacenes de producto terminado,
conserva el snapshot histórico y no ejecuta causalidad ni discovery cuantitativo
de Saavedra.

## Definición Laboratorio

| Almacén | Subtipo regulatorio |
| --- | --- |
| `LAB-T1` | AGEMED |
| `LAB-T2` | SENASAG |
| `LAB-T3` | INDUSTRIAL |
| `LAB-T4` | MAGISTRAL |

`LAB-DES` y `LAB-D0` permanecen fuera de la familia; se conservan como
candidatos de despacho/picking sin evidencia de ser fuente comercial para esta
cohorte.

## Cohorte y cobertura

Se reutilizaron las 3.027 claves de Gates 1–3 y el snapshot
`2026-09-14 11:21:15`. No se recontó la cohorte con una consulta viva.

| Estado | N |
| --- | ---: |
| Pedidos L congelados | 3.027 |
| Activos canónicos del snapshot | 2.842 |
| Activos observables en SAP vivo | 2.840 |
| Cancelados observables | 187 |
| `LIVE_SAP_DRIFT` activo no resoluble por clave histórica | 2 |

La degradación se mantiene porque Gates 1–3 no persistieron la lista individual
as-of de los 2.842 activos. Las métricas y clasificaciones se calculan sobre
los 2.840 activos observables; los dos restantes no se reasignan con el estado
vivo.

## Clasificación por salida

Las categorías se reconcilian sin doble conteo sobre los 2.840 activos
observables:

| Clase | N | % |
| --- | ---: | ---: |
| `LAB_ONLY` | 71 | 2,50% |
| `LAB_MULTI_T` | 21 | 0,74% |
| `LAB_PLUS_OTHER` | 0 | 0,00% |
| `OTHER_ONLY` | 2.539 | 89,40% |
| `NO_EXIT` | 209 | 7,36% |
| **Total** | **2.840** | **100,00%** |

`LAB_ONLY` significa que toda la salida válida observada proviene de un único
`LAB-T*`; `LAB_MULTI_T` usa más de un `LAB-T*`. No se observó `LAB_PLUS_OTHER`
en esta cohorte. La cobertura por almacén no se suma como pedidos únicos:
puede haber pedidos `LAB_MULTI_T`.

## Primera salida LAB

`LabFirstExitDateTime` es el primer `CreateDate + CreateTS` del documento
generador con `OINM.OutQty > 0`, enlazado por
`TransType + CreatedBy + DocLineNum + ItemCode + Warehouse`.

| Métrica | Minutos |
| --- | ---: |
| N | 92 |
| mean | 571,902 |
| median | 48,100 |
| p25 | 9,133 |
| p75 | 99,383 |
| p90 | 1.329,550 |
| p95 | 2.767,395 |
| min | 1,717 |
| max | 24.833,333 |

Cobertura: `92/2.840` activos observables (3,24%) y `92/2.842` activos canónicos (3,24%).

## Salida completa LAB

Se calculó para `LAB_ONLY` y `LAB_MULTI_T`, donde toda la cantidad relevante
puede atribuirse a la familia LAB. No se fabrica una salida completa para
`LAB_PLUS_OTHER`.

| Métrica | Minutos |
| --- | ---: |
| N | 91 |
| mean | 567,700 |
| median | 46,017 |
| p25 | 9,050 |
| p75 | 97,667 |
| p90 | 1.340,833 |
| p95 | 2.767,900 |
| min | 1,717 |
| max | 24.833,333 |

Cobertura: `91/2.840` activos observables (3,20%) y `91/2.842` activos canónicos (3,20%).

## Métricas documentales adicionales

Sobre los 92 pedidos con salida LAB:

| Métrica | N | median | p90 | mean |
| --- | ---: | ---: | ---: | ---: |
| Pedido → factura | 92 | 136,350 | 2.876,550 | 1.084,449 |
| Factura → primera salida LAB válida | 9 | 27,233 | 320,013 | 167,889 |
| Factura → salida completa LAB válida | 9 | 27,233 | 320,013 | 167,889 |

Las 83 duraciones factura→salida no negativas no están disponibles porque en
la ruta `ENTREGA` la salida registrada precede documentalmente a la factura.
No se corrigieron ni mezclaron silenciosamente.

## Bandas temporales

| Banda | Primera salida N (%) | Salida completa N (%) |
| --- | ---: | ---: |
| <30m | 42 (45,65%) | 42 (46,15%) |
| 30–60m | 10 (10,87%) | 10 (10,99%) |
| 1–2h | 18 (19,57%) | 18 (19,78%) |
| 2–4h | 8 (8,70%) | 8 (8,79%) |
| 4–8h | 2 (2,17%) | 2 (2,20%) |
| 8–12h | 0 (0,00%) | 0 (0,00%) |
| 12–24h | 5 (5,43%) | 4 (4,40%) |
| 24–48h | 5 (5,43%) | 5 (5,49%) |
| 48–72h | 1 (1,09%) | 1 (1,10%) |
| 72–96h | 0 (0,00%) | 0 (0,00%) |
| >96h | 1 (1,09%) | 1 (1,10%) |

## Días transcurridos y umbrales

| Medida | Primera salida | Salida completa |
| --- | ---: | ---: |
| D+0 | 80 (86,96%) | 80 (87,91%) |
| D+1 | 6 (6,52%) | 5 (5,49%) |
| D+2 | 4 (4,35%) | 4 (4,40%) |
| D+3 | 1 (1,09%) | 1 (1,10%) |
| D+4+ | 1 (1,09%) | 1 (1,10%) |
| <=24h | 85 (92,39%) | 84 (92,31%) |
| >24h | 7 (7,61%) | 7 (7,69%) |
| >48h | 2 (2,17%) | 2 (2,20%) |
| >72h | 1 (1,09%) | 1 (1,10%) |

Las duraciones son minutos calendario; D+0 es día calendario y no equivale a
un SLA.

## Hora de ingreso

Las siguientes cifras corresponden a primera salida LAB; el artefacto JSON
contiene también el desglose de salida completa.

| Franja | N | median | p90 | D+0 % | >24h % |
| --- | ---: | ---: | ---: | ---: | ---: |
| 00–07 | 0 | — | — | — | — |
| 07–09 | 8 | 90,025 | 1.489,997 | 87,50% | 12,50% |
| 09–11 | 36 | 53,458 | 100,467 | 91,67% | 8,33% |
| 11–13 | 17 | 148,200 | 2.092,840 | 70,59% | 17,65% |
| 13–15 | 13 | 8,883 | 159,853 | 92,31% | 0,00% |
| 15–17 | 17 | 12,017 | 147,020 | 94,12% | 0,00% |
| 17–19 | 1 | 954,283 | 954,283 | 0,00% | 0,00% |
| 19–24 | 0 | — | — | — | — |

## Día de semana

Primera salida LAB:

| Día | N | median | p90 | D+0 % | >24h % | >48h % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| lunes | 5 | 13,867 | 193,593 | 100,00% | 0,00% | 0,00% |
| martes | 14 | 57,017 | 1.581,312 | 71,43% | 14,29% | 7,14% |
| miércoles | 20 | 9,683 | 146,490 | 95,00% | 0,00% | 0,00% |
| jueves | 16 | 117,942 | 2.767,900 | 75,00% | 18,75% | 0,00% |
| viernes | 13 | 18,867 | 166,177 | 92,31% | 0,00% | 0,00% |
| sábado | 24 | 65,483 | 101,333 | 91,67% | 8,33% | 4,17% |
| domingo | 0 | — | — | — | — | — |

Los cruces viernes→lunes y sábado→lunes no se interpretan causalmente con
estas muestras; el desglose conserva las fechas reales en el JSON.

## Por almacén

N es de pedidos únicos que utilizaron el almacén; por ello puede sumar más que
el consolidado.

| Almacén | Subtipo | N | median | p90 | same-day % | >24h % |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| LAB-T1 | AGEMED | 45 | 20,767 | 2.229,703 | 82,22% | 11,11% |
| LAB-T2 | SENASAG | 19 | 14,750 | 446,377 | 89,47% | 5,26% |
| LAB-T3 | INDUSTRIAL | 48 | 58,408 | 225,305 | 91,67% | 6,25% |
| LAB-T4 | MAGISTRAL | 6 | 124,325 | 2.000,475 | 66,67% | 16,67% |

`LAB-T4` tiene N=6 y debe interpretarse con cautela.

## Global vs LAB

| Medida | Global | LAB consolidado |
| --- | ---: | ---: |
| N primera salida | 2.631 | 92 |
| Mediana primera salida (min) | 1.470,333 | 48,100 |
| p90 primera salida (min) | 5.598,333 | 1.329,550 |
| N salida completa | 2.561 | 91 |
| Mediana salida completa (min) | 1.467,650 | 46,017 |
| p90 salida completa (min) | 5.580,133 | 1.340,833 |
| same-day primera salida | 15,36% | 86,96% |
| >24h primera salida | 53,63% | 7,61% |

La comparación es descriptiva y no atribuye la diferencia a una causa
operativa concreta.

## Sanity checks y cantidades

- `FirstExit <= CompleteExit`: `91/91` pares válidos, PASS.
- `FirstExit = CompleteExit`: `91/91`; `FirstExit < CompleteExit`: `0/91`.
- Cantidades: `2.840/2.840` pedidos observables reconcilian
  `salida total = salida LAB + salida otros`.
- No se detectaron duplicaciones de filas de salida después de agrupar por la
  clave canónica; no hubo `LAB_PLUS_OTHER`.
- Data quality: 0 movimientos sin documento, 0 documentos con movimiento
  faltante, 209 pedidos sin documento fuente y 0 timestamps negativos.
- Evento usado: `OINM.OutQty > 0`; el límite semántico sigue siendo salida
  registrada de inventario, no salida física del camión ni entrega al cliente.

## Casos reales

Se conservaron 5 casos rápidos, 5 cercanos a la mediana, 5 cercanos al p90 y 5
extremos en el JSON de evidencia. Muestra representativa:

| Grupo | Pedido | Key | Minutos | Almacén(es) | Ruta |
| --- | ---: | ---: | ---: | --- | --- |
| rápido | 261901495 | 212589 | 1,717 | LAB-T2 | ENTREGA |
| rápido | 261901469 | 212171 | 2,300 | LAB-T1/LAB-T4 | ENTREGA |
| mediana | 261901516 | 213100 | 43,017 | LAB-T1/LAB-T2/LAB-T3 | ENTREGA |
| mediana | 261901446 | 211519 | 46,017 | LAB-T2 | FACTURA_RESERVA_ENTREGA |
| p90 | 261901490 | 212431 | 954,283 | LAB-T2 | ENTREGA |
| p90 | 261901607 | 214747 | 1.340,833 | LAB-T3 | ENTREGA |
| extremo | 261901547 | 213585 | 2.772,950 | LAB-T1/LAB-T3/LAB-T4 | FACTURA_RESERVA_ENTREGA |
| extremo | 261901414 | 210920 | 24.833,333 | LAB-T2/LAB-T3 | ENTREGA |

La tabla no inventa causalidad; cada caso conserva documentos generadores,
cantidades y timestamps en la evidencia.

## Hallazgos

1. La salida LAB observada representa 92 pedidos únicos: 71 `LAB_ONLY` y 21
   `LAB_MULTI_T`; no hubo `LAB_PLUS_OTHER`.
2. La mediana consolidada Pedido→Primera salida LAB es 48,1 minutos y el p90
   es 1.329,55 minutos, muy por debajo del baseline global, cuyo p90 es
   5.598,333 minutos.
3. El 86,96% de primeras salidas LAB ocurre en D+0 y 92,39% en <=24h.
4. LAB-T1..T4 tienen perfiles distintos, pero LAB-T4 mantiene solo seis
   pedidos y no permite una conclusión robusta.
5. El gate permanece DEGRADED únicamente por los dos activos históricos no
   identificables individualmente frente al drift de SAP vivo; no se usó ese
   drift para redefinir la cohorte.

## Limitaciones

- El snapshot no contiene una lista individual persistida de activos Gate 2;
  por eso no se puede cerrar PASS histórico completo.
- `CreateDate + CreateTS` es timestamp de creación del documento generador en
  SAP, no timestamp físico.
- `Factura → salida` tiene excepciones semánticas en la ruta entrega.
- La ausencia de `LAB_PLUS_OTHER` es un resultado de esta ventana y no una
  regla permanente.
- No se hizo causalidad ni se correlacionó stock, producción o Saavedra.

## Recursos y evidencia

- SAP/HANA READ ONLY; `SAP_WRITE_COUNT=0`.
- Una consulta de preflight y una consulta de datos, secuenciales; filtros por
  3.027 documentos conocidos, tipos 13/15 y clave OINM exacta.
- Un proceso, `OMP_NUM_THREADS=1`, sin pandas ni multiprocessing.
- Tiempo: 1,982 s; RSS máxima: 63,0 MiB.
- Evidencia JSON externa:
  `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi/investigation-consolidation-v1/files/validation/order_delivery_efficiency/evidence/lab_finished_goods_exit_baseline_v2.json`
- Runner:
  `validation/order_delivery_efficiency/lab_finished_goods_exit_baseline_v2.py`
- Tests:
  `validation/order_delivery_efficiency/test_lab_finished_goods_exit_baseline_v2.py`

## Siguiente paso

No se ejecuta `TELCHI_SAAVEDRA_FRACTIONATION_FLOW_DISCOVERY_V1` porque el
criterio operativo indicado exige cerrar LAB V2 como PASS antes de continuar.
Primero debe persistirse o reconstruirse la lista histórica de activos para
resolver los dos `LIVE_SAP_DRIFT`; luego puede promoverse este gate a PASS sin
cambiar el snapshot.
