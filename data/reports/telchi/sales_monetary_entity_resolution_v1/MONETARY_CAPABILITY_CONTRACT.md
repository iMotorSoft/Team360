# Monetary capability contract

La capability amplía el servicio existente [sales_query](../../../../SrvRestAstroLS_v1/backend/modules/telchi/datalake/sales_query.py); no crea otro servicio comercial ni State Engine.

| Campo | Contrato |
| --- | --- |
| Operación | sales.period_billed_amount.v1 |
| Parámetros exactos | date_from, date_to_exclusive, currency=BS; ISO canónico; rango positivo de hasta 366 días |
| Intent existente | sales.net_amount; SALES_NET histórico; devuelve también facturación válida y NC separadas |
| Permiso específico | telchi.sales.period_billed_amount.read.v1; no sustituido por latest_documents |
| Resultado | billed_amount, credit_amount, net_amount, invoice_count, credit_count, conteos de unicidad y montos presentes; moneda, período, definición, grano, publicación/snapshot, restricciones |
| Binding | publicación esperada y snapshot 1408; cambio de binding rechaza, nunca usa un snapshot reciente |
| Ejecución | worker bounded, conexión read-only, dos threads y 512MB; SQL registrado con parámetros, no SQL de Luna |
| Rechazos | parámetros extra, moneda distinta, entidad no acreditada, duplicados, montos ausentes, resultado inconsistente, falta de permiso o committed distinto de True |

[capabilities](../../../../SrvRestAstroLS_v1/backend/modules/telchi/assistant/capabilities.py) conecta el intent previo sin cambiar su significado a facturación bruta. Ambas magnitudes se muestran: «Ventas» es neto documental; «Facturación válida» es el total de facturas antes de NC. No hay entity_id aprobado aún.

Modelo y effort conservados: GPT-5.6 Luna Medium. Se actualizó sólo su catálogo declarado, sin fallback. El engine determinístico V2 no se modificó; la guardia committed=True permanece obligatoria.

Para ambas métricas se preservan requested_metrics y prioridad; sólo se entrega la parte monetaria del período cuando el ranking fijo es incompatible, explicando que unidades físicas no están habilitadas. No se presenta el conteo de documentos como cantidades de productos.

Se añadió un binding estrecho para la pregunta exacta de ranking genérico, después de reproducir fechas/ASK inconsistentes: fija la ventana registrada, conserva raw/propuesta y pasa por el mismo engine. No corrige paths inválidos, períodos explícitos ni decisiones rejected. El scope de neto por producto se rechaza sin consultar un total global.
