# Telchi — Semántica de salida registrada de almacén V1

Este informe cierra la semántica del movimiento de inventario para la cohorte congelada de pedidos `L%`, sin interpretar el evento como salida física del camión ni medir aún tiempos globales.

## Gate

El gate `TELCHI_WAREHOUSE_EXIT_SEMANTICS_V1` queda en **PASS** para salida registrada de inventario, con la frontera física declarada.

- Período de pedidos: 2026-08-15 a 2026-09-14.
- Cohorte Gate 1: 3.027 pedidos `L%`.
- Cohorte activa Gate 2: 2.842 pedidos.
- Snapshot documental reutilizado: 2026-09-14 11:21:15, hora HANA.
- SAP/HANA READ ONLY; `SAP_WRITE_COUNT=0`.

## Evidencia

La evidencia demuestra tres rutas que generan el movimiento saliente, usando cantidades de inventario (`InvQty`) y no solo cantidades comerciales.

| Ruta generadora de stock | Pedidos al snapshot | Líneas L con `OutQty` | Error de cantidad | Error de almacén |
| --- | ---: | ---: | ---: | ---: |
| Pedido → factura normal → movimiento | 2.438 | 11.179 | 0 | 0 |
| Pedido → entrega → movimiento → factura | 86 | 188 | 0 | 0 |
| Pedido → factura de reserva → entrega → movimiento | 107 | 330 | 0 | 0 |
| Total con primera salida registrada | 2.631 | 11.697 | 0 | 0 |

Cada línea se enlazó mediante tipo documental, `CreatedBy=DocEntry`, línea documental, `ItemCode` y almacén. `BASE_REF=DocNum` se conservó como control, no como clave suficiente.

## Hallazgo

La factura directa tiene dos semánticas distintas: la factura normal genera salida (`TransType=13`), mientras la factura de reserva no mueve stock; su entrega posterior genera la salida (`TransType=15`).

La ruta dominante sigue siendo factura directa normal. ODLN no es universal, pero sí es indispensable tanto para los 86 pedidos basados directamente en entrega como para las facturas de reserva.

## Semántica

El evento confiable es `OINM.OutQty > 0` enlazado inequívocamente con la línea fuente. El timestamp apto para tiempos internos es `CreateDate + CreateTS` del documento que generó ese movimiento.

| Campo/evento | Semántica demostrada | Uso autorizado |
| --- | --- | --- |
| `OINM.TransType=13` | Salida generada por factura normal | Sí |
| `OINM.TransType=15` | Salida generada por entrega | Sí |
| `OINM.CreatedBy` | `DocEntry` del documento generador dentro de su `TransType` | Clave principal |
| `OINM.BASE_REF` | Número visible del documento | Solo control; no usar solo |
| `OINM.DocLineNum` + `ItemCode` | Línea e ítem del movimiento | Clave de línea |
| `OINM.Warehouse` | Almacén afectado | Debe igualar `WhsCode` fuente |
| `OINM.OutQty` | Cantidad de inventario saliente | Comparar con `InvQty` |
| `OINM.InQty` | Entrada o compensación | No sumar como salida |
| `OINM.AppObjAbs` | `-1` en las 11.697 líneas salientes; enlazó la entrega original en la reversa observada | Control de reversa |
| `OINM.DocDate` | Fecha de contabilización copiada del documento fuente | No usar como fecha de creación |
| `OINM.DocTime` | Minuto de registro del movimiento; sin segundos | No usar solo para elapsed time |
| Documento `CreateDate + CreateTS` | Creación del documento generador, con segundos | Timestamp de salida registrada |

`OINM.DocDate + DocTime` no es un timestamp cronológico universal. En factura normal, 36 documentos tenían fecha de contabilización distinta de la fecha de creación, con desfase de hasta 2 días; en 5 documentos el minuto OINM también difirió del minuto de creación.

La clasificación adoptada es `WAREHOUSE_EXIT_CONFIRMED` para **salida registrada de inventario** cuando existen `OutQty>0`, relación exacta y timestamp de creación del documento generador. No demuestra hora física de salida del camión.

## Primera salida y salida completa

Las definiciones quedan habilitadas para Gate 4, manteniendo separado el flujo bruto de las compensaciones posteriores.

- `FirstWarehouseExitDateTime`: mínimo `CreateDate + CreateTS` entre movimientos `OutQty>0` válidos del pedido.
- `CompleteWarehouseExitDateTime`: primer `CreateDate + CreateTS` donde la suma acumulada de `OutQty` válido alcanza `OrderedInvQty` de líneas `L%`.
- No se usa tolerancia decimal silenciosa: la comparación es exacta en la unidad de inventario SAP.
- `InQty` de devolución, nota de crédito o reversa se registra aparte y no se convierte en otra salida.
- Para análisis neto futuro se debe calcular un estado separado; no se debe reescribir la primera salida histórica.

## Cobertura

La cobertura canónica reconcilia el baseline Gate 2 sin repetir Gate 1 ni Gate 2 y corrige únicamente las excepciones semánticas investigadas.

| Estado al snapshot Gate 2 | Pedidos | % activos | Uso temporal |
| --- | ---: | ---: | --- |
| Salida completa confirmada | 2.561 | 90,11% | Primera y completa |
| Salida parcial confirmada | 70 | 2,46% | Primera; no completa |
| Sin salida disponible | 211 | 7,42% | No medible |
| Total activo | 2.842 | 100,00% | — |

La primera salida está disponible para **2.631/2.842 pedidos activos (92,58%)**. La salida completa está disponible para **2.561/2.842 (90,11%)**.

La reconciliación es: 2.448 completos Gate 2 + 6 falsos `OVER_EXIT` corregidos + 107 salidas por entrega de factura de reserva = 2.561 completos. Los 70 parciales elevan la cobertura de primera salida a 2.631.

## Excepciones

Las tres excepciones prioritarias quedaron explicadas con claves y cantidades, sin inferir causas no almacenadas.

### Los 111 documentos sin OINM enlazado

Los 111 eran facturas de reserva (`isIns=Y`), documentos comerciales que no generan `OutQty` por sí mismos. El join Gate 2 se detenía una etapa antes.

- 107 ya tenían entrega activa dentro del snapshot; sus entregas generaron `TransType=15`, con cantidad y almacén exactos.
- 4 no tenían movimiento saliente al snapshot y quedan `NOT_AVAILABLE`; son documentos no inventariables hasta que exista entrega.
- La inspección posterior observó progresión documental en SAP, pero no se incorporó al snapshot cerrado.
- Clasificación: 107 `ALTERNATIVE_ROUTE`; 4 `NON_INVENTORY_DOCUMENT` al corte; 0 `UNKNOWN`.

### Los 70 parciales

Los movimientos parciales son reales y no son una diferencia de UoM: para la cantidad efectivamente documentada, `OutQty=InvQty` y el almacén coincide.

| Estado del pedido | Pedidos | Pedido L | Salió | Restante |
| --- | ---: | ---: | ---: | ---: |
| Cerrado | 69 | 6.758 | 5.429 | 1.329 |
| Abierto | 1 | 948 | 648 | 300 |

Los 69 cerrados no conservan saldo abierto aunque nunca alcanzaron la cantidad original; SAP no expone en estos campos la causa operativa del cierre del remanente. El caso abierto conserva 300 unidades pendientes. No se los marca como error ni como salida completa.

### Los 6 `OVER_EXIT`

Los seis excesos eran falsos positivos causados por usar `BASE_REF=DocNum` sin exigir `CreatedBy`. Números visibles repetidos permitían sumar movimientos de otro documento.

| `Order DocEntry` | Pedido | Gate 2 | Salida exacta | Fanout ajeno |
| ---: | ---: | ---: | ---: | ---: |
| 211940 | 1 | 2 | 1 | 1 |
| 212556 | 5 | 6 | 5 | 1 |
| 213753 | 3 | 4 | 3 | 1 |
| 213867 | 70 | 74 | 70 | 4 |
| 213988 | 9 | 10 | 9 | 1 |
| 214698 | 32 | 33 | 32 | 1 |

Los seis quedan `EXACT`. No hubo exceso real, diferencia de UoM ni salida adicional legítima.

### Reversas

Se observó un pedido con salida completa y compensación completa posterior, que demuestra por qué salida original y neto no pueden mezclarse.

El pedido `213594` salió mediante entrega `352763` por 1.023 unidades L. Una nota de crédito (`TransType=14`, documento `21212`) registró después `InQty=1.023` en 20 líneas y `AppObjAbs=352763`.

La primera salida registrada permanece como hecho histórico. El pedido debe llevar además `REVERSAL_FULL` y no considerarse completo en una futura métrica neta al corte sin una regla explícita.

## Muestras

Se conservaron muestras pequeñas y trazables en el JSON externo, sin descargar el detalle completo de la cohorte.

- 15 casos de factura normal.
- 15 casos de pedido con entrega.
- 15 casos de factura de reserva con entrega.
- Los 70 parciales se agregaron en HANA; el detalle analizado se limitó a muestras y estados.
- Los 6 falsos `OVER_EXIT` se revisaron completos.
- La única reversa detectada se revisó completa, con 20 líneas.

## Data quality

Los controles relevantes para la semántica cerraron sin diferencias de línea, cantidad o almacén.

- 11.697/11.697 líneas salientes tuvieron movimiento exacto.
- 0 almacenes diferentes entre movimiento y línea fuente.
- 0 cantidades diferentes entre `OutQty` e `InvQty` documentada.
- 0 salidas con `InQty` positiva mezclada.
- 6 fanouts por referencia visible fueron eliminados mediante `CreatedBy`.
- 36 facturas normales prueban que fecha de contabilización y fecha de creación pueden diferir.

## Limitaciones

El gate no prueba logística física ni causas humanas no registradas en SAP.

1. `CreateDate + CreateTS` representa creación/registro SAP, no salida física del camión.
2. Los 69 remanentes cerrados no tienen una causa causal demostrada en los campos inspeccionados.
3. El estado de SAP es mutable: durante Gate 3 dos pedidos cambiaron su flag activo y aparecieron documentos posteriores. La cobertura canónica conserva el snapshot Gate 2 y reporta el drift sin recontarlo.
4. No se calcularon medianas, percentiles, rankings ni bandas globales.
5. La métrica neta después de reversas queda separada de primera salida y salida completa bruta.

## Recursos

La ejecución convivió con otros agentes y mantuvo el impacto acotado.

- `SAP_WRITE_COUNT=0`.
- Un proceso y un thread numérico.
- Consultas secuenciales, filtradas por cohorte y snapshot.
- Agregaciones en HANA y muestras de máximo 15 casos por ruta.
- Sin pandas, multiprocessing, contenedores, servicios adicionales ni suites generales.
- Memoria disponible observada antes de consultar: aproximadamente 4,2 GiB.
- No se detuvieron ni reiniciaron procesos ajenos.

## Archivos

Los artefactos son locales al módulo de investigación y la evidencia de datos queda fuera del repositorio.

- `validation/order_delivery_efficiency/warehouse_exit_semantics_v1.py`.
- `validation/order_delivery_efficiency/test_warehouse_exit_semantics_v1.py`.
- `docs/telchi_warehouse_exit_semantics_v1_report.md`.
- Evidencia externa: `validation/order_delivery_efficiency/evidence/warehouse_exit_semantics_v1.json` bajo el Evidence Root Telchi.
- `STATUS_ACTUAL.md` no fue modificado porque contiene cambios concurrentes ajenos.

## Validaciones

La validación focalizada cubre clasificación exacta, evidencia, freeze y reconciliación de cardinalidad.

Los comandos y resultados finales se registran en el cierre de ejecución. No se ejecutaron suites generales.

## Siguiente paso

Avanzar a `TELCHI_ORDER_TO_WAREHOUSE_EXIT_BASELINE_V1` usando solo los 2.631 pedidos con primera salida confirmada y reportando por separado 2.561 completos, 70 parciales y 211 no medibles.
