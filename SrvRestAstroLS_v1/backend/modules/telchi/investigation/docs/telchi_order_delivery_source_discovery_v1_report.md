# Telchi — Source Discovery de pedidos y reparto V1

**Gate:** `TELCHI_ORDER_DELIVERY_SOURCE_DISCOVERY_V1`

**Estado:** PASS de discovery; no habilita todavía métricas de eficiencia

**Corte:** 30 días, 2026-08-15 a 2026-09-14

**Política:** SAP/HANA READ ONLY; `SAP_WRITE_COUNT=0`

## Gate

**PASS** para identificar fuentes, canales, documentos iniciales y timestamps candidatos. La semántica operativa de los timestamps y la cadena documental siguen pendientes; por eso no se avanzó a baseline ni se calculó ninguna duración.

## Evidencia

### Universo documental reciente

| Fuente SAP | Documentos 30d | Cancelados | Qué prueba hoy |
| --- | ---: | ---: | --- |
| Pedidos | 3.151 | 186 | Documentos de pedido creados en SAP |
| Entregas | 2.158 | 12 | Documentos de entrega SAP, no recepción física |
| Facturas | 37.684 | 1 | Documentos de facturación SAP |

El universo inicial de pedidos con al menos una línea cuyo SKU comienza exactamente con `L` contiene **3.027 pedidos**: **2.997 100% L**, **30 mixtos** y **185 cancelados**.

### Origen de los pedidos L observados en SAP

| Canal marcado en SAP | Pedidos L | Participación |
| --- | ---: | ---: |
| DMS | 2.965 | 97,95% |
| SAP directo | 62 | 2,05% |
| Retail One | 0 | 0,00% |

Para DMS, **2.923 de 2.965 pedidos (98,58%)** fueron creados con la cuenta SAP técnica `dms`. Esto demuestra que la hora de creación SAP es, como mínimo, una **hora de recepción/sincronización documental**; todavía no demuestra la hora original en que el cliente hizo el pedido.

Los 62 pedidos SAP directo se distribuyen entre usuarios nombrados. Su `CreateDate + CreateTS` es candidato a hora de carga humana en SAP, pero aún no prueba la hora de solicitud del cliente.

### Retail One

La fuente `@SO1_01VENTA` conserva `fecha`, `hora`, sucursal, estación, operador, vendedor y folio. En 30 días hubo **38.046 transacciones**. De ellas, **21.995** contenían al menos un producto `L%` y **19.395 (88,18%)** enlazaron a una factura SAP mediante el folio Retail One.

No se observó ninguna transacción L con `pedido=Y`; **18.903** tenían `factura=Y`. Por tanto, Retail One aparece en esta ventana principalmente como **venta POS/facturación**, no como la fuente del universo ORDR de pedidos de reparto. No debe sumarse automáticamente a los 3.027 pedidos.

Los campos de aparente entrega en Retail One no permiten afirmar entrega física:

- fecha de entrega informada: 10/38.046;
- hora de entrega no nula: 32.688/38.046, pero las muestras muestran `0` o cadena vacía como default;
- fecha y hora positiva simultáneas: 0/38.046;
- repartidor informado: 1/38.046;
- zona informada: 0/38.046.

Para las 21.995 transacciones L, fecha y hora positiva de entrega simultáneas también fueron **0**.

### Timestamps candidatos

| Etapa | Fuente/campo candidato | Clasificación provisional | Confianza actual |
| --- | --- | --- | --- |
| Origen Retail One | fecha + hora de `@SO1_01VENTA` | Evento POS previo a la factura SAP | Media/alta para POS; no es pedido de reparto demostrado |
| Ingreso DMS a SAP | pedido SAP `CreateDate + CreateTS` | Recepción/sincronización en SAP | Alta para creación SAP; baja para pedido original cliente |
| Ingreso SAP directo | pedido SAP `CreateDate + CreateTS` | Carga del documento en SAP | Alta para creación SAP; semántica cliente pendiente |
| Fecha comercial pedido | pedido SAP `DocDate + DocTime` | Timestamp documental | Media; comparar con `CreateTS` |
| Facturación | factura SAP `CreateDate + CreateTS` | Creación documental | Alta para creación SAP; no prueba contabilización efectiva |
| Despacho | entrega SAP `CreateDate + CreateTS` | Creación de entrega | Solo proxy documental |
| Entrega cliente | campos Retail One de entrega | Sin cobertura útil observada | `NOT_AVAILABLE` para universo L reciente |

Los samples Retail One enlazados muestran facturas SAP creadas normalmente segundos o pocos minutos después del evento POS, lo que confirma que ambos timestamps son distintos y deben conservarse.

## Hallazgo

El flujo de **pedidos L de reparto** observado durante 30 días nace casi por completo en DMS y llega a SAP como pedido. SAP conserva con precisión la creación del documento, pero no se demostró todavía que conserve la hora original de captura en DMS.

Retail One representa otro flujo: ventas POS que suelen enlazar directamente a facturas y no muestran `pedido=Y` para productos L en la ventana. Mezclarlo con pedidos DMS produciría una métrica conceptualmente incorrecta.

No existe evidencia útil de hora física de entrega al cliente en las fuentes locales ni en los campos SAP/Retail One inspeccionados. Las entregas SAP deben tratarse por ahora como `DOCUMENT_TIMESTAMP_ONLY`, no como prueba de recepción física.

## Limitaciones

1. No hay dataset Parquet local reutilizable: el Data Root solo contiene actualmente su manifest de aislamiento.
2. No se encontró conector o dataset DMS externo en el módulo, Data Root, Private Root o legacy inspeccionado. Solo están disponibles sus marcas sincronizadas en SAP.
3. `CreateTS`, `DocTime` y campos Retail One son candidatos; su semántica definitiva requiere comparación documental en Gate 3.
4. La relación pedido → entrega → factura, las rutas sin pedido, parciales y huérfanos pertenecen a Gate 2 y no se cuantificaron aquí.
5. No se infiere despacho físico ni entrega cliente desde la creación de ODLN.
6. La relación header/detail de Retail One se usó estructuralmente por `Code`; deberá recibir un gate explícito de cardinalidad antes de un baseline.

## Recursos

- Ejecución secuencial, sin multiprocessing y con threads numéricos limitados a 1.
- Ventana única de 30 días.
- Proyecciones de columnas explícitas; sin `SELECT *` de datos.
- Solo agregados y muestras de máximo 20 filas.
- Sin carga masiva en RAM, contenedores, servicios, reinicios ni suites completas.
- Evidencia externa: `validation/order_delivery_efficiency/evidence/source_discovery_v1.json` bajo el Evidence Root Telchi.
- `SAP_WRITE_COUNT=0`.

## Siguiente paso

Ejecutar **Gate 2 — `TELCHI_ORDER_DOCUMENT_CHAIN_V1`** solo sobre los 3.027 pedidos L recientes, excluyendo cancelados del flujo principal pero reportándolos aparte. Validar primero cardinalidades de `RDR1 → DLN1 → INV1`, rutas reales, parciales y documentos sin relación; no calcular tiempos de reparto todavía.
