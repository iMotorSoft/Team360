# Telchi — Cadena documental de pedidos L V1

**Gate:** `TELCHI_ORDER_DOCUMENT_CHAIN_V1`

**Estado:** PASS de cadena documental; no habilita aún métricas temporales

**Cohorte congelada:** pedidos de Gate 1, 2026-08-15 a 2026-09-14, `DocEntry <= 215152`

**Política:** SAP/HANA READ ONLY; `SAP_WRITE_COUNT=0`

## Gate

**PASS.** Se reconstruyeron las rutas posteriores de los 3.027 pedidos con productos `L%`, con relaciones exactas por documento, línea e ítem. Se separaron cancelados, parciales y pedidos sin documento posterior. La interpretación del timestamp del movimiento de inventario queda deliberadamente para Gate 3.

## Evidencia

### Universo

| Estado | Pedidos | Porcentaje del total |
| --- | ---: | ---: |
| Activos | 2.842 | 93,89% |
| Cancelados | 185 | 6,11% |
| Total | 3.027 | 100,00% |

Los 185 cancelados no tienen documento posterior activo y quedan fuera de las métricas futuras de eficiencia.

### Rutas reales sobre pedidos activos

| Ruta observada | Pedidos | Porcentaje activo |
| --- | ---: | ---: |
| Pedido → factura directa | 2.549 | 89,69% |
| Pedido → entrega SAP → factura | 86 | 3,03% |
| Pedido sin documento posterior activo | 207 | 7,28% |
| Total activo | 2.842 | 100,00% |

No se observaron en esta cohorte:

- pedidos con más de una entrega activa: **0**;
- pedidos con más de una factura activa: **0**;
- rutas simultáneas entrega + factura directa: **0**;
- pedidos activos con entrega sin factura posterior: **0**.

### Calidad de las relaciones

| Relación | Líneas L enlazadas | Coincidencia exacta documento/línea/ítem | Documentos |
| --- | ---: | ---: | ---: |
| Pedido → entrega | 188 | 188 (100%) | 86 entregas |
| Pedido → factura directa | 11.515 | 11.515 (100%) | 2.549 facturas |
| Entrega → factura | 188 | 188 (100%) | 86 facturas |

La relación usa `BaseType`, `BaseEntry`, `BaseLine` e igualdad de `ItemCode`. No se enlazó por número de documento aislado.

Para el candidato de inventario se exigió además:

- familia documental de movimiento: factura o entrega;
- `OINM.BASE_REF = DocNum` dentro de esa familia;
- misma línea documental;
- mismo `ItemCode`;
- `OutQty` como cantidad saliente candidata.

### Cantidad documentada para pedidos activos

| Estado provisional | Pedidos | Porcentaje activo |
| --- | ---: | ---: |
| Cantidad completa en documento posterior | 2.565 | 90,25% |
| Cantidad parcial en documento posterior | 70 | 2,46% |
| Sin documento posterior | 207 | 7,28% |

Esta clasificación prueba cumplimiento documental de las líneas L. Todavía no equivale a salida física confirmada.

### Movimiento OINM candidato

| Estado provisional según `OutQty` | Pedidos | Porcentaje activo |
| --- | ---: | ---: |
| Cantidad completa | 2.448 | 86,14% |
| Cantidad parcial | 70 | 2,46% |
| Sin movimiento saliente enlazado | 318 | 11,19% |
| Cantidad superior a la pedida | 6 | 0,21% |

Los **111 casos adicionales sin movimiento** respecto de los 207 sin documento posterior, y los **6 OVER_EXIT**, son evidencia de que no debe declararse todavía `WAREHOUSE_EXIT_CONFIRMED`. Gate 3 deberá determinar si son diferencias temporales de contabilización, documentos sin efecto de stock, reversas, duplicación aparente de OINM u otra semántica.

### Casos trazables

| Pedido | Canal | Ruta | Cantidad L pedida | Cantidad documento | `OutQty` candidato |
| --- | --- | --- | ---: | ---: | ---: |
| 262121971 (`210600`) | DMS | Factura directa | 270 | 270 | 270 |
| 262121972 (`210602`) | DMS | Factura directa | 4 | 4 | 4 |
| 261901406 (`210627`) | DMS | Entrega → factura | 550 | 550 | 550 |
| 261901407 (`210628`) | SAP directo | Entrega → factura | 3 | 3 | 3 |
| 262122027 (`210698`) | DMS | Cancelado, sin posterior activo | 39 | 0 | 0 |

El JSON de evidencia conserva para las muestras los `DocEntry`, `DocNum`, línea, ítem, almacén, cantidad y `TransNum` de movimiento relacionados.

## Hallazgo

La cadena predominante no usa un documento separado de entrega: **89,69% de los pedidos activos pasa directamente de pedido a factura**. En esos casos, la factura es también el documento candidato que genera la salida de inventario.

Solo **3,03%** sigue `pedido → entrega SAP → factura`; para esta ruta, el movimiento candidato pertenece a la entrega, no debe duplicarse con la factura posterior.

El armado analítico debe soportar ambas rutas. Usar únicamente ODLN excluiría casi nueve de cada diez pedidos activos; usar únicamente OINV perdería la ruta cuyo stock sale mediante entrega.

## Limitaciones

1. Este gate demuestra relaciones documentales y presencia/cantidad de movimientos, no el significado físico de la fecha/hora OINM.
2. Los 207 pedidos activos sin documento posterior incluyen pedidos posiblemente abiertos; todavía no se asigna causa.
3. Los 70 parciales requieren validar si el saldo estaba pendiente al corte o fue completado posteriormente.
4. Los 111 pedidos con documento posterior pero sin `OutQty` enlazado requieren inspección focalizada.
5. Los 6 `OVER_EXIT` permanecen `UNKNOWN` hasta descartar fanout, reversas o unidades de medida.
6. No se calcularon tiempos, percentiles ni bandas.

## Recursos

- Cohorte congelada de 3.027 pedidos; no se amplió a 90 o 365 días.
- Consultas secuenciales, agregadas en HANA y con columnas explícitas.
- Muestras documentales limitadas a 12 pedidos.
- Sin pandas, multiprocessing, servicios, contenedores o suites completas.
- Threads numéricos limitados a 1.
- `SAP_WRITE_COUNT=0`.
- Evidencia externa: `validation/order_delivery_efficiency/evidence/document_chain_v1.json` bajo el Evidence Root Telchi.

## Siguiente paso

Ejecutar **Gate 3 — `TELCHI_WAREHOUSE_EXIT_SEMANTICS_V1`** sobre muestras estratificadas y pequeñas:

1. facturas directas con `OutQty` completo;
2. entregas con `OutQty` completo;
3. 111 documentos sin movimiento enlazado;
4. 70 parciales;
5. 6 `OVER_EXIT`.

Validar `OINM.DocDate`, `DocTime`, `TransNum`, almacén, cantidades, reversas y relación con los timestamps de creación del documento antes de definir primera salida o salida completa.
