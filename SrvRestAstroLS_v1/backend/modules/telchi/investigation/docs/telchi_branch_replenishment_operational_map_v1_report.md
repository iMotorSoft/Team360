# TELCHI — BRANCH STOCK REPLENISHMENT

## GATE 1 + BASELINE — MAPA OPERATIVO REAL

**Contexto:** `ENTITY=TELCHI` · `DOMAIN=REPOSICIÓN / STOCK_E_INVENTARIOS` · `STAGE=INVESTIGATION` · `SAP_HANA` + Data Lake · `READ ONLY` · `SAP_WRITE_COUNT=0` · universo operativo `ItemCode LIKE 'L%'`.

**Ventana observada:** SAP `2022-04-01` a `2026-09-10`.

**Evidencia reproducible:** `validation/branch_replenishment/v1/` en el Evidence Root externo:
`/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi/investigation-consolidation-v1/files/validation/branch_replenishment/v1/`.

## A. VEREDICTO

`DEGRADED`

Causas concretas:

1. El vínculo `WAREHOUSE → BRANCH` es exacto para los almacenes salón, pero los depósitos relacionados se resuelven en parte por código/nombre; `OWHS.U_SO1_01SUCURSAL` no aporta un mapping poblado.
2. El stock histórico diario no está cerrado. Las métricas que dependen de stock al momento de la transferencia quedan `PENDING_GATE_STOCK_HISTORY`.
3. No se puede afirmar stockout, urgencia física ni política formal a partir de `OWTR`/`OINM` solamente.
4. SAP registra la transferencia contable en un evento; no demuestra despacho físico, arribo o recepción física.
5. La sucursal `DV` tiene almacén salón, pero no presenta recepción L activa en la ventana observada.

No se ejecutaron escrituras SAP: `SAP_WRITE_COUNT=0`.

## B. MAPA DE ALMACENES Y SUCURSALES

Se clasificaron los 82 almacenes contra nombre, código, `U_TYPE`, `U_TIPO`, DMS y movimiento real. Conteo por rol:

| Role | Warehouses |
|---|---:|
| `MOBILE` | 19 |
| `FINISHED_GOODS` | 12 |
| `PRODUCTION` | 11 |
| `OTHER` | 11 |
| `UNKNOWN` | 11 |
| `TRANSIT` | 7 |
| `BRANCH_SALES` | 7 |
| `CENTRAL` | 4 |

La tabla completa con movimientos, ventas, entradas, salidas, transferencias recibidas/enviadas y evidencia de clasificación está en `warehouses.json`. Los `UNKNOWN` quedan explícitos; no se fuerzan a una categoría.

### Branch → warehouse

| Branch | Warehouse | Role | Confidence | Evidence |
|---|---|---|---|---|
| 2A | `2A-SAL` | `BRANCH_SALES` | `EXACT` | nombre/código salón; ventas y transferencias L |
| 2A | `2A-SMK` | `BRANCH_SALES` | `EXACT` | TelchiMarket salón; ventas y transferencias L |
| 2A | `2A-AMD`, `2A-AMK`, `2A-MAG` | `CENTRAL` | `STRONG` | prefijo 2A + medicamentos/matriz; movimientos reales |
| 2A | `2A-DEV`, `2A-TRAN` | `TRANSIT` | `STRONG` | devolución/transitorio + transferencias |
| 2A | `2A-DAN`, `2A-EXT`, `2A-MKT` | `OTHER` | `STRONG` | dañado/externo/marketing; no usados como salón |
| 2A | `2A-KIT`, `2A-MEI` | `UNKNOWN` | `STRONG` | vinculados por prefijo, rol funcional no cerrado |
| CM | `CM-SAL` | `BRANCH_SALES` | `EXACT` | nombre/código salón; ventas y transferencias L |
| CM | `CM-AMD` | `CENTRAL` | `STRONG` | medicamentos Casa Matriz; movimientos reales |
| CM | `CM-DAN` | `OTHER` | `STRONG` | dañado; no se usa como stock de salón |
| DV | `DV-SAL` | `BRANCH_SALES` | `EXACT` | nombre/código salón; sin recepción L activa observada |
| RC | `RC-SAL` | `BRANCH_SALES` | `EXACT` | nombre/código salón; ventas y transferencias L |
| UR | `UR-SAL` | `BRANCH_SALES` | `EXACT` | nombre/código salón; ventas y transferencias L |
| VI | `VI-SAL` | `BRANCH_SALES` | `EXACT` | nombre/código salón; ventas y transferencias L |
| LPZ* | `LPZ-T1`, `LPZ-D1`, `LPZ-D2` | `FINISHED_GOODS` / `MOBILE` | `HEURISTIC` | localidad/código La Paz + red móvil; no hay almacén salón explícito |

`LPZ` se conserva como nodo operativo provisional, no como sucursal salón confirmada.

## C. PRODUCTOS TELCHI

| Métrica | Resultado |
|---|---:|
| Códigos L totales | 3.759 |
| Activos | 3.471 |
| Inactivos | 288 |
| Con stock actual no cero | 2.216 |
| Con movimientos | 3.351 |
| Con ventas (`OINM` TT 13/15) | 1.501 |
| Con transferencias | 2.411 |
| Sin movimiento | 408 |

Las métricas de rutas y baseline no mezclan productos no L.

## D. RUTAS Y GRAFO LOGÍSTICO

`OWTR.CANCELED='N'` y `WTR1` son la fuente documental. Se conservaron 598 aristas L. El volumen informado es `SUM(ABS(WTR1.Quantity))`; las cantidades negativas activas se preservan como reversas/ajustes legítimos.

### Rutas dominantes directas

| Origin | Transit | Destination | Transfers | Volume | L Products | Role |
|---|---|---|---:|---:|---:|---|
| `SAP-R1` | — | `2A-SAL` | 3.916 | 2.305.147,876 | 770 | `TRANSIT → BRANCH_SALES` |
| `SAP-R1` | — | `CM-SAL` | 2.489 | 1.108.690,458 | 752 | `TRANSIT → BRANCH_SALES` |
| `SAL-TRS` | — | `2A-SAL` | 2.704 | 77.574 | 960 | `TRANSIT → BRANCH_SALES` |
| `SAL-TRS` | — | `CM-SAL` | 2.515 | 96.023 | 738 | `TRANSIT → BRANCH_SALES` |
| `SAP-R1` | — | `RC-SAL` | 1.637 | 407.715,189 | 661 | `TRANSIT → BRANCH_SALES` |
| `SAP-R1` | — | `VI-SAL` | 1.179 | 310.897,300 | 669 | `TRANSIT → BRANCH_SALES` |
| `SAL-TRS` | — | `VI-SAL` | 1.886 | 64.765,480 | 917 | `TRANSIT → BRANCH_SALES` |
| `SAL-TRS` | — | `UR-SAL` | 40 | 4.274 | 148 | `TRANSIT → BRANCH_SALES` |
| `UR-SAL` | — | `RC-SAL` | 1 | 840 | 1 | `BRANCH_SALES → BRANCH_SALES` |
| `2A-SAL` | — | `CM-SAL` | 1 | 350 | 1 | `BRANCH_SALES → BRANCH_SALES` |

### Composición de rutas con tránsito

La composición siguiente exige coincidencia de `ItemCode + DocDate` entre los dos segmentos. Es evidencia de grafo, no prueba de que una unidad física concreta haya recorrido ambos documentos.

| Origin | Transit | Destination | Matched item-days | Downstream transfers | Downstream volume | L Products | Role |
|---|---|---|---:|---:|---:|---:|---|
| `LAB-T2` | `SAP-R1` | `2A-SAL` | 6.727 | 6.788 | 713.790 | 235 | `FINISHED_GOODS → TRANSIT → BRANCH_SALES` |
| `LAB-T1` | `SAP-R1` | `CM-SAL` | 6.348 | 6.377 | 302.216 | 171 | `FINISHED_GOODS → TRANSIT → BRANCH_SALES` |
| `LAB-T1` | `SAP-R1` | `RC-SAL` | 4.053 | 4.070 | 122.824 | 166 | `FINISHED_GOODS → TRANSIT → BRANCH_SALES` |
| `2A-SAL` | `SAL-TRS` | `UR-SAL` | 130 | 130 | 3.070 | 100 | `BRANCH_SALES → TRANSIT → BRANCH_SALES` |
| `LAB-T1` | `SAP-R1` | `VI-SAL` | 3.418 | 3.423 | 91.582 | 167 | `FINISHED_GOODS → TRANSIT → BRANCH_SALES` |
| — | — | `DV-SAL` | 0 | 0 | 0 | 0 | `NO_DOMINANT_PATH` |

El grafo identifica `SAP-R1` y `SAL-TRS` como nodos de tránsito, `LAB-T*` como hubs de producto terminado y los almacenes `*-SAL` como receptores de salón. También existe movimiento entre sucursales: `UR-SAL → RC-SAL` y `2A-SAL → CM-SAL`.

## E. FUENTE PRINCIPAL POR SUCURSAL

| Branch | Primary source | Secondary source | Confidence |
|---|---|---|---|
| 2A (`2A-SAL`) | `SAP-R1` | `2A-MAG` | `STRONG` |
| CM (`CM-SAL`) | `SAP-R1` | `SAL-TRS` | `STRONG` |
| DV (`DV-SAL`) | `UNKNOWN` — sin recepción L activa | — | `UNKNOWN` |
| RC (`RC-SAL`) | `SAP-R1` | `SAL-TRS` | `STRONG` |
| UR (`UR-SAL`) | `SAL-TRS` | `2A-SAL` | `STRONG` |
| VI (`VI-SAL`) | `SAP-R1` | `SAL-TRS` | `STRONG` |
| LPZ operativo* | `ALM-IMP` vía `LPZ-T1` | `LAB-T1` | `HEURISTIC` |

La fuente primaria se ordena por volumen L recibido en el almacén salón; no significa que exista una política formal de asignación.

## F. BASELINE OBSERVADO

| Branch / warehouse | L vendidos | L recibidos/transferidos | Transfer docs | Volume received | Current L stock | Observed behaviour |
|---|---:|---:|---:|---:|---:|---|
| 2A / `2A-SAL` | 1.135 | 1.204 | 7.352 | 3.094.287,968 | 35.685,914 | push vía `SAP-R1`, con otras fuentes |
| 2A / `2A-SMK` | 4 | 4 | 4 | 10 | 0 | movimiento escaso; no política inferida |
| CM / `CM-SAL` | 1.088 | 962 | 5.179 | 1.264.259,458 | 51.246,695 | push vía `SAP-R1` + `SAL-TRS` |
| DV / `DV-SAL` | sin transferencia L | sin transferencia L | 0 | 0 | 0 | no baseline de reposición observable |
| RC / `RC-SAL` | 911 | 1.018 | 3.541 | 468.189,189 | 21.865,220 | push vía `SAP-R1` + `SAL-TRS` |
| UR / `UR-SAL` | 297 | 159 | 45 | 4.495 | 0 | push histórico vía `SAL-TRS`; luego inter-sucursal |
| VI / `VI-SAL` | 934 | 974 | 3.098 | 376.322,780 | 15.973,960 | push vía `SAP-R1` + `SAL-TRS` |

El histórico muestra transferencia posterior y anterior a ventas, pero sin stock diario no permite clasificar causalidad. Por eso no se afirma `MIN_MAX_LIKE`, `REORDER_POINT_LIKE`, `PERIODIC`, `DEMAND_TRIGGERED` ni `REACTIVE_TO_STOCKOUT`.

### Distribución de política implícita

| Patrón | Resultado |
|---|---|
| `PUSH_FROM_CENTRAL` | comportamiento de red observado en 2A/CM/RC/VI, no política formal |
| `PUSH_FROM_TRANSIT` | observado en UR y como ruta secundaria en otras sucursales |
| `MIN_MAX_LIKE` | no determinable |
| `REORDER_POINT_LIKE` | no determinable |
| `PERIODIC` | no determinable |
| `DEMAND_TRIGGERED` | no determinable |
| `MANUAL_IRREGULAR` | candidatos visibles, no confirmado sin causa/solicitud |
| `REACTIVE_TO_STOCKOUT` | no determinable |
| `NO_CLEAR_POLICY` | clasificación conservadora vigente para el baseline |

## G. CASOS REALES TRAZABLES

Los diez casos completos, con `TransNum`, `BASE_REF`, fecha, cantidades y ruta documental, están en `real_cases.json`.

| # | Caso | Evidencia real |
|---:|---|---|
| 1 | Alta rotación | `L00504 @ 2A-SAL`: ventas TT13 el 2022-04-08 (25+25); OWTR `DocNum=160`, 2022-04-11, `LAB-T2 → 2A-SAL`, qty 700. |
| 2 | Alta rotación | `L00505 @ CM-SAL`: ventas TT13 2022-04-13/14 (7, 10, 6, 15); OWTR `22010206`, 2022-04-14, `SAP-R1 → CM-SAL`, qty 1.000. |
| 3 | Rotación media | `L01990 @ VI-SAL`: venta 1 el 2022-04-20; OWTR `22050276`, 2022-05-19, `SAL-TRS → VI-SAL`, qty 10; ventas posteriores 2022-05-21 y 2022-05-28. |
| 4 | Producto lento | `L02432 @ RC-SAL`: OWTR `251804175`, 2025-12-12, `SAL-TRS → RC-SAL`, qty 1; no se inventa demanda o stockout. |
| 5 | Muchas transferencias | `L00505 @ UR-SAL`: ventas 2022-04-08/11/16/18; OWTR `22040016`, 2022-04-18, `SAL-TRS → UR-SAL`, qty 50; ventas continúan 2022-04-19/22. |
| 6 | Más de un origen | `L00505 @ VI-SAL`: movimientos recibidos desde `SAP-R1` y `SAL-TRS` en la población; OWTR `22050021`, 2022-04-12, `SAP-R1 → VI-SAL`, qty 1.000. |
| 7 | Transferencia entre sucursales | `L01584 @ RC-SAL`: OWTR `22050820`, 2022-08-12, `UR-SAL → RC-SAL`, qty 840; ventas RC 60 el 2022-09-01 y 300 el 2022-09-13. |
| 8 | Candidato posterior a quiebre | `L00505 @ CM-SAL`: secuencia ventas 2022-04-13/14 → OWTR `22010206` el 2022-04-14 → ventas posteriores; **no se etiqueta stockout** porque falta stock diario. |
| 9 | Urgencia | `L00504 @ 2A-SAL`: existe transferencia tras ventas; no hay campo/documento validado de urgencia física, por lo que el caso queda `URGENCY_UNOBSERVABLE`. |
| 10 | Irregularidad manual candidata | `L00505 @ VI-SAL`: ventas interdiarias y fuentes múltiples; la irregularidad es observacional, no se atribuye todavía a intervención manual. |

## H. UNKNOWN / DEGRADED

- 11 almacenes permanecen `UNKNOWN` por rol funcional: `2A-KIT`, `2A-MEI`, `BE-DT1`, `CBBA-DT1`, `CHQ-DT1`, `DMS-PROF`, `LAB-C1`, `OR-DT1`, `PO-DT1`, `SCZ-DT1`, `TJ-DT1`.
- 58/82 almacenes tienen mapping lógico de branch `UNKNOWN`; esto es esperado para plantas, tránsito, móviles y depósitos no sucursal, pero se conserva explícito.
- `DV-SAL` no tiene transferencia L activa observada.
- Cancelaciones de transferencia: 429 documentos; se excluyeron por `OWTR.CANCELED='Y'`.
- Reversas/ajustes: 5.866 líneas activas negativas; se preservaron, no se confundieron con cancelación.
- Same-warehouse: 0 líneas.
- Origen/destino desconocido en `WTR1`: 0.
- Productos L inexistentes en `OITM`: 0.
- La clave atómica documental es `OWTR.DocEntry + WTR1.LineNum`; el runner no colapsa documentos multi-origen/multi-destino.
- Duplicados completos sobre la extracción histórica masiva quedan como validación pendiente; no se afirma ausencia por una muestra parcial.
- `OINM.Balance` no se convierte aquí en stock histórico diario; el gate siguiente debe reconstruir snapshots por `ItemCode × Warehouse` y documentar el saldo inicial.

## I. LEAD TIME DISPONIBLE

- **Lead time contable:** candidato medible con `OWTR.DocDate/DocTime`, `OWTR.DocNum`, `WTR1.LineNum` y movimientos destino `OINM` TT67. Debe validarse el matching exacto de línea y el timestamp horario.
- **Lead time físico:** no medible con la evidencia actual. No existe una cadena confiable `solicitud → despacho → recepción`; la transferencia SAP es contable/instantánea para efectos de inventario.

## J. LOOP TEST

Se ejecutó `QUERY → RESULT → VALIDATE → COUNTEREXAMPLE → CORRECT → REPEAT` sobre datos SAP reales:

- central/transit → sucursal: `SAP-R1 → 2A/CM/RC/VI-SAL`;
- central → tránsito → sucursal: coincidencias de `ItemCode + DocDate`, separadas de prueba física;
- sucursal → sucursal: `UR-SAL → RC-SAL`, `2A-SAL → CM-SAL`;
- reversas: líneas activas negativas preservadas y cancelados excluidos;
- productos L: 3.759 perfilados; 2.411 con transferencias;
- control negativo no-L: no entra en métricas del modelo L.

Validaciones principales: 82 almacenes, 598 rutas L, 0 same-warehouse, 0 warehouses huérfanos, 0 productos L huérfanos.

## K. NEXT GATE

`GATE 2/3 — DEMANDA + STOCK HISTÓRICO DIARIO`

Debe resolver exactamente:

1. snapshot diario `ItemCode × Warehouse` desde el ledger OINM, incluyendo saldo inicial y reconciliación contra OITW;
2. demanda censurada por stockout, separando demanda observada de ventas perdidas/no observables;
3. secuencia `stock antes → venta/salida → transferencia → recepción` sin doble conteo de TT13/TT15;
4. clasificación reproducible de stockout y porcentaje de reposición posterior a stockout;
5. intervalos, tamaños y frecuencia de reposición por `ItemCode × Branch`;
6. duplicados, reversas, cancelaciones y matching horario/documental para lead time contable.

No implementar todavía safety stock, ROP, Min/Max, target stock, service level, optimización, compras ni producción sugerida.
