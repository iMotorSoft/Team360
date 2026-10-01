# TELCHI — Gate physical lead time / logistics process investigation V1

**Continuación:** `TELCHI_REPLENISHMENT_LEVEL_B_100_L_PRODUCTS_V1_PASS`\
**Contexto:** `ENTITY=TELCHI` · `DOMAIN=REPOSICIÓN / STOCK_E_INVENTARIOS` · `STAGE=INVESTIGATION`\
**Branch:** `2A` · **universo:** `ItemCode LIKE 'L%'` · **ventana principal:** 2025-09-12 → 2026-09-11\
**Modo:** SAP/HANA read-only · `SAP_WRITE_COUNT=0` · `MAX_WORKERS=1` · `RESOURCE_GUARD=ENABLED`

## A. Veredicto

`TELCHI_PHYSICAL_LEAD_TIME_V1_NOT_OBSERVABLE`

La evidencia SAP permite medir algunos retardos documentales, pero no responde
cuánto tiempo transcurre físicamente desde la necesidad hasta la disponibilidad
en 2A. No se fuerza `PASS`, ni se sustituye `PHYSICAL_LEAD_TIME` por un valor
contable.

### Respuesta ejecutiva

**¿Cuánto tarda realmente Telchi en reponer 2A?** `UNKNOWN` con SAP actual.

En la ventana se observaron **1.624 documentos / 9.646 líneas positivas** de
transferencia L hacia `2A-SAL`/`2A-SMK`. En todas hay entrada `OINM TT67` en el
almacén destino, pero ese evento ocurre como parte de la contabilización de la
transferencia y no prueba salida física, llegada física ni disponibilidad
física.

Los únicos números medibles son auxiliares y deben permanecer separados:

- `REQUEST_TO_TRANSFER_DOCUMENT_DELAY`: solicitud `OWTQ/WTQ1` → creación del
  documento `OWTR`, solo 81 líneas enlazadas; mediana **0,0056 días** (~8 min),
  p90 **0,1071 días** (~2,6 h), máximo **1,9041 días**.
- `TRANSFER_DOCUMENT_DELAY_ACCOUNTING`: `OWTR.DocDate/DocTime` → `OINM`
  destino, mediana/p90 **0 días**, con 3 anomalías negativas y 252 casos
  positivos no cero. Esto es contabilidad, no tránsito físico.
- `FIRST_SALE_AFTER`: existe para 9.414/9.646 líneas (**97,6% dentro de la
  ventana**), pero es un límite superior/proxy de uso, no la fecha de llegada.

Por tanto, no existe un intervalo físico confiable que pueda reportarse sin
agregar dos hitos operativos: **`dispatch_timestamp`** y
**`receipt_timestamp`**.

## B. Mapa de proceso real

```text
OWTQ/WTQ1 (cuando la solicitud se usa)
        ↓ relación exacta BaseType/BaseEntry/BaseLine
OWTR/WTR1 (transferencia SAP)
        ↓ contabilización automática
OINM TT67: salida origen + entrada destino
        ↓ evidencia auxiliar, no fecha física
primera venta posterior (proxy censurado)
```

| Hito solicitado | Evidencia observada | Cobertura / semántica |
|---|---|---|
| `NECESIDAD` | no existe evento SAP de necesidad física | no observable |
| `SOLICITUD` | `OWTQ/WTQ1` | usada en 638 documentos L hacia 2A en la ventana; solo 35 documentos terminaron enlazados a `OWTR` |
| `PREPARACIÓN` | ningún timestamp/hito explícito | no observable |
| `DESPACHO` | `OWTR` y `CreateDate/CreateTS` | creación SAP, no salida física |
| `SALIDA FÍSICA` | ningún timestamp físico | no observable |
| `TRÁNSITO` | almacén clasificado `TRANSIT` y ruta documental | rol contable/logístico, no identidad de mercadería viajando |
| `RECEPCIÓN FÍSICA` | ningún timestamp físico | no observable |
| `DISPONIBILIDAD` | `OINM TT67` destino; primera venta posterior | posting contable; primera venta es proxy/upper bound |

`ODLN/DLN1` fueron inspeccionados y no se observó una cadena de entrega basada
en transferencia para esta ventana (`0` líneas L activas con `BaseType=67`).

## C. Inventory Transfer Request

### Cobertura de la fuente

- Universo total `OWTQ`: **91.850** documentos, 2022-04-01 → 2026-09-15.
- Universo total L `OWTQ/WTQ1`: **48.513** documentos, **182.586** líneas,
  2.271 productos L.
- 2A en la ventana: **638** documentos, **816** líneas, **320** productos,
  22.325 unidades solicitadas.
- `OWTR` positivo hacia 2A en la ventana: **1.624** documentos, **9.646**
  líneas, 690 productos, 631.145,27 unidades.
- Relación exacta por `WTR1.BaseType='1250000001'`, `BaseEntry` y `BaseLine`:
  **81/9.646 líneas (0,84%)** y **35/1.624 documentos (2,16%)**.
- Todas las 81 líneas enlazadas tienen solicitud previa al documento de
  transferencia; no se observa una solicitud previa en el resto.

Así, `OWTQ` **sí se utiliza**, pero no representa el flujo completo de
reposición de 2A. La mayoría de `OWTR` se crea directamente (`BaseType=-1`) o
no tiene solicitud enlazada.

## D. Source coverage

| Evidencia | Líneas | % de transferencias positivas |
|---|---:|---:|
| Solicitud exacta `OWTQ/WTQ1` | 81 | 0,84% |
| Documento `OWTR/WTR1` | 9.646 | 100,00% |
| Timestamp físico de despacho | 0 | 0,00% |
| Ruta con origen clasificado como tránsito | 9.379 | 97,23% |
| Entrada `OINM TT67` en destino | 9.646 | 100,00% contable |
| Timestamp físico de recepción | 0 | 0,00% |
| Fecha de disponibilidad física exacta | 0 | 0,00% |
| Primera venta posterior dentro de ventana | 9.414 | 97,59% proxy censurado |

### Confianza por episodio

Después de separar la confianza física de la evidencia contable:

- `EXACT`: **0**
- `STRONG`: **0**
- `BOUNDED`: **0** — no se pueden defender límites físicos con los campos
  actuales.
- `PROXY`: **9.414** — entrada contable más primera venta posterior.
- `UNKNOWN`: **232** — entrada contable sin primera venta posterior observada
  dentro de la ventana.

La clasificación `PROXY` no convierte una venta en disponibilidad exacta.

## E. Timestamps y retardos separados

Los campos existen en las tablas, pero su semántica operacional no es un hito
físico:

- `OWTR/OWTQ`: `DocDate`, `TaxDate`, `DocTime`, `CreateDate`, `CreateTS`,
  `UpdateDate`, `UpdateTS`, `ReqDate`, `StDlvDate`, `StDlvTime`, `EndDlvDate`,
  `EndDlvTime`.
- UDF logísticos candidatos revisados: `U_FECHEST_EMBR`, `U_FECHPRTO`,
  `U_FECHALM`, `U_FECHREAL_EMBR`, `U_FECHREAL_PRTO`, `U_FECHRECEPTR`.
- En las 36.341 líneas L relevantes de 2A, los campos de fecha/hito logístico
  candidatos y UDF anteriores están sin población útil (`0`).
- `OINM`: `DocDate`, `DocTime`, `CreateDate` y `TransType=67`; conserva el
  efecto contable del movimiento, no el momento físico.

Distribuciones observadas, etiquetadas correctamente:

| Medida | n | Mediana | p75 | p90 | p95 | Máximo |
|---|---:|---:|---:|---:|---:|---:|
| Solicitud → creación `OWTR` | 81 | 0,0056 d | 0,0147 d | 0,1071 d | 0,6514 d | 1,9041 d |
| `OWTR.DocDate/DocTime` → `OINM` destino | 9.646 | 0 d | 0 d | 0 d | 0 d | 0,1771 d |
| **PHYSICAL_LEAD_TIME** | **0** | **UNKNOWN** | **UNKNOWN** | **UNKNOWN** | **UNKNOWN** | **UNKNOWN** |

Los 3 casos contables negativos se conservan como anomalía, no se corrigen
silenciosamente. La simultaneidad contable no se interpreta como tránsito
físico cero.

## F. Rutas, cantidad y calendario

`SAP-R1 → 2A-SAL` domina la ventana: **8.634 líneas**, seguido por
`SAL-TRS → 2A-SAL` con **714**. También existen rutas desde `2A-AMD`, `2A-DEV`,
`2A-TRAN`, `2A-KIT`, `2A-MKT`, `CM-AMD`, `CM-SAL`, `LAB-*` y `01`.

La medición por ruta no produce lead time físico. En el equivalente contable
`OWTR.DocDate/DocTime → OINM`, las rutas principales tienen mediana y p90 de
0 días; por ello no se presentan como rutas rápidas o lentas físicamente.

La cobertura de solicitud es escasa por ruta. `2A-AMD → 2A-SAL` concentra
76 de las 81 líneas con solicitud; las rutas dominantes `SAP-R1 → 2A-SAL` y
`SAL-TRS → 2A-SAL` no tienen solicitud enlazada en esta ventana.

No se observa una conclusión física confiable por cantidad. En los tres grupos
`0–10`, `11–100` y `101+` la variable medida sigue siendo el retardo documental,
no el lead time físico.

Tampoco se concluye aceleración por día de semana. Las solicitudes enlazadas
son pocas y el tiempo medido es solicitud → creación SAP:

- lunes: 11 líneas, mediana 0,0142 d;
- martes: 8, mediana 0,0044 d;
- miércoles: 15, mediana 0,0010 d;
- jueves: 17, mediana 0,0147 d;
- viernes: 7, mediana 0,0056 d;
- sábado: 23, mediana 0,0050 d.

## G. Stockout y urgencia

Se cruzó la extracción de stockout del Level B únicamente como contexto de la
muestra L de 2A. El cruce no convierte una reposición posterior en una urgencia
operativa documentada:

- `AFTER_STOCKOUT`: 2.719 transferencias; 45 con solicitud; mediana de
  solicitud → `OWTR` 0,0050 d.
- `DURING_STOCKOUT`: 87 transferencias; 2 con solicitud; mediana 0,0128 d.
- `BEFORE_STOCKOUT`: 836 transferencias; 12 con solicitud; mediana 0,0056 d.

No es válido afirmar que urgencias aceleran, retrasan o no cambian el proceso:
la variable física faltante sigue siendo despacho/recepción y el volumen de
solicitudes enlazadas es bajo.

## H. Transit materiality

Con la clasificación de almacenes vigente se identifican siete almacenes
`TRANSIT`: `01`, `2A-DEV`, `2A-TRAN`, `LAB-A1`, `LAB-TRAN`, `SAL-TRS` y
`SAP-R1`.

En el snapshot actual de `OITW` hay **1.679 unidades L**, 25 filas y 24
productos con `OnHand <> 0` en esos almacenes. Este valor es el resultado
reproducible de este gate; el valor histórico de **4.119,98** citado en el gate
anterior no se reutiliza porque no coincide con este snapshot/universo de
clasificación y no se puede adjudicar sin reconstrucción adicional.

- Cantidad físicamente asignable con evidencia de identidad de envío: **0**.
- Solicitudes abiertas actuales desde tránsito hacia 2A con coincidencia de
  stock: **0 filas**.
- Porcentaje exacto asignable: **0,0%**.
- Duración histórica en tránsito: `UNKNOWN`; `OITW` no conserva edad de lote
  ni identidad de embarque.

El saldo se informa como stock técnico/contable en tránsito, no como stock de
2A. No se distribuye arbitrariamente entre sucursales.

## I. Casos reales trazables

Se generaron **20 episodios L de 2A** en
`real_cases.jsonl`, cada uno con `ItemCode`, `Qty`, origen, destino, request,
transferencia, timestamps de creación, posting `OINM`, evidencia de llegada,
primera venta proxy, usuario y confianza. La muestra cubre solicitudes
enlazadas, rutas desde `2A-AMD`/`2A-KIT`, lotes pequeños/medios/grandes y
contexto antes/durante/después de stockout.

El detalle completo, sin resumir ni colapsar líneas multi-item, está en:

- `episodes.jsonl`: 9.646 líneas atómicas.
- `real_cases.jsonl`: 20 casos reproducibles.
- `gate_result.json`: proceso, cobertura, distribución, rutas y limitaciones.

Ejemplos de episodios incluidos: `L00772` (request y durante/después de
stockout), `L00773`, `L01687`, `L01701`, `L01950`, `L02074`, `L02075`,
`L02077`, `L02079`, `L02081`, `L02122`, `L02123`, `L02128`, `L02205`,
`L02245`, `L02266` y `L02277`. La selección no interpreta la primera venta como
llegada exacta.

## J. Cancelaciones, reversas y conservación

- OWTR cancelados en ventana: **118**, excluidos del universo principal.
- OWTQ cancelados en ventana: **0**.
- Líneas negativas en OWTR activos hacia 2A: **5**, no se mezclaron con las
  9.646 reposiciones positivas.
- El matching de inventario conserva la semántica validada:
  `OWTR/WTR1 ↔ OINM TT67`, por `BASE_REF + ItemCode + DocLineNum/BaseLine +
  Warehouse`; cada una de las 9.646 líneas tiene 2 movimientos contables, una
  salida de origen y una entrada de destino.

## K. Datos faltantes

SAP no registra de forma utilizable en este flujo:

1. timestamp de necesidad de sucursal;
2. timestamp de solicitud cuando la solicitud se hace fuera de `OWTQ`;
3. timestamp de preparación/picking;
4. timestamp real de salida del vehículo;
5. identificador de carga/guía/remito asociado a la transferencia;
6. timestamp de llegada física;
7. confirmación de recepción por persona/sucursal;
8. timestamp de disponibilidad en el salón;
9. identidad de unidades que permanecen en tránsito y branch destino;
10. calendario de feriados/ruta/transportista aplicado al traslado.

Usuarios `soluone`, `manager` y usuarios personales aparecen como creadores SAP,
pero no bastan para inferir una acción física. `UserSign` se mantiene como
atributo de trazabilidad, no como evidencia de despacho o recepción.

## L. Minimum operational fix

No hace falta comenzar con un sistema logístico complejo. Para cerrar este gate
se recomienda registrar obligatoriamente, por transferencia/línea o por carga
con relación inequívoca:

```text
dispatch_timestamp
receipt_timestamp
```

Mínimos complementarios: `transfer_docentry`/`transfer_linenum`,
`source_whs`, `destination_whs`, usuario que confirma recepción y un
`shipment_id` si varias líneas viajan juntas. Con esos dos timestamps, el
lead time físico puede medirse; disponibilidad de venta puede registrarse como
tercer hito opcional cuando la recepción no implique disponibilidad inmediata.

## M. Impacto sobre Gate 5C

No se modifica el backtest actual ni sus escenarios `LT 0/1/2/3/5/7` durante
este gate.

Cuando Telchi capture hitos físicos suficientes:

1. medir distribución por ruta `source → destination` y, si aplica,
   `source → transit → branch`;
2. usar `median` como `LT_TYPICAL`, `p75` como escenario tensionado y `p90`
   como escenario conservador;
3. mantener por separado `PHYSICAL_LEAD_TIME`, `ACCOUNTING_LEAD_TIME`,
   `REQUEST_TO_TRANSFER_DOCUMENT_DELAY` y `STOCKOUT_TO_REPLENISHMENT_DELAY`;
4. no imponer un único lead time a todos los productos ni rutas;
5. repetir robustez de los 59 candidatos, especialmente los 32 con robustez
   LOW frente a lead time.

## N. Artefactos y validación

Runner:

`validation/branch_replenishment/physical_lead_time_gate_5c_v1.py`

Tests nuevos: `test_physical_lead_time_gate_5c_v1.py` (**7 PASS**).\
Regresión focalizada `validation/branch_replenishment`: **52 PASS**.\
Smoke HANA real del runner: completado con **9.646 líneas** y **20 casos**.\
Resource guard: **PASS**, `MAX_WORKERS=1`, `resource_abort_count=0`, RSS pico **148 MiB**, memoria disponible mínima **5.579,45 MiB**.

Evidencia externa:

`/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi/investigation-consolidation-v1/files/validation/branch_replenishment_physical_lead_time/v1/`

No se escribió SAP, no se modificó el backtest y no se cambió ninguna política
de reposición.
