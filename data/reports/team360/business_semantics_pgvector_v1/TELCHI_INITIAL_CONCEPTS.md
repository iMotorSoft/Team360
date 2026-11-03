# Conceptos iniciales y agregado Telchi

Nueve significados publicados DEV, con operaciones relacionadas todavía pendientes. Dos candidatos documentales adicionales siguen propuestos; no se publicaron automáticamente.

## Seed confirmado

Las definiciones y aliases canónicos están en [telchi_seed.py](../../../../SrvRestAstroLS_v1/backend/modules/business_semantics/telchi_seed.py), no dentro de un prompt fijo.

| Código | Dimensión y límite esencial |
| --- | --- |
| telchi.sales.pharmacy_branches | Sucursales clasificadas farmacia; no productos farmacéuticos ni clientes farmacias. IDs de sucursal pendientes. |
| telchi.sales.menona_customers | Segmento comercial autorizado de clientes; no producto ni inferencia sensible. |
| telchi.procurement.import_recommendations | Intención analítica de abastecimiento; factores potenciales, ninguna fórmula u orden aprobada. |
| telchi.receivables.outstanding | Saldos abiertos vencidos + corrientes al mismo corte/alcance; no sólo morosidad ni cuentas por pagar. |
| telchi.sales.lost_opportunities | Oportunidades no concretadas; cotización abierta/no convertida/parcial/perdida son estados distintos. |
| telchi.sales.horizontal_channel | En general vendedores DMS/calle; origen DMS no clasifica automáticamente cada documento. |
| telchi.sales.corporate_channel | Modalidad corporativa; canal cliente y categoría vendedor son independientes. |
| telchi.sales.online_channel | Puede identificarse comercialmente mediante vendedor; vigencia y documentos requieren evidencia. |
| telchi.sales.seller_classification | Consulta/clasificación de vendedores; categoría no equivale a canal de cada venta. |

La comparación horizontal/corporativa recupera ambos conceptos mediante aliases versionados y permanece no ejecutable. La versión 2 de corporativo preserva versión 1, actor, razón y embeddings separados.

## Relaciones comprobadas y no resueltas

La investigación fue focalizada sobre reportes existentes y CURRENT read-only. Los ejemplos son datos estructurados, no una lista fija de vendedores en el system prompt.

- Selva Rojas Jaimes: SAP OSLP clave 11, ID Foundation `salesperson_63670834455a669575a65f5d`, categoría corporativa 2 en snapshot de referencia.
- Luz Guzman: SAP OSLP clave 13, ID Foundation `salesperson_570cdbc532c60880c82015f7`, categoría corporativa 2 en ese snapshot.
- “Dra. Luz” online: referencia empresarial registrada con clave NULL/identidad pendiente. No se equipara automáticamente con Luz Guzman ni se reclasifican sus operaciones.
- `sales_document.slp_code`/`card_code` localizan relaciones documento-vendedor-cliente; campos y muestra están en [evidencia Foundation](channel_foundation_evidence.json).
- Customers CURRENT no publica `U_CANAL_VENTAS` ni relación maestro-vendedor; dataset channels no existe en esa referencia sellada.
- Namespace Reference SAP_HANA versus Atomic SAP_B1_HANA: no join literal sin crosswalk explícito.
- Source system/document source table son lineage; no prueba suficiente de origen DMS/Retail One o canal empresarial.

Fuentes históricas preservadas: [corporativo](../../../../SrvRestAstroLS_v1/backend/modules/telchi/investigation/validation/corporate_sales/CORPORATE_SALES_FINAL_REPORT.md), [canal cliente](../../../../SrvRestAstroLS_v1/backend/modules/telchi/investigation/validation/corporate_sales/CHANNEL_RULE_FINAL_REPORT.md), [corrección temporal](../../../../SrvRestAstroLS_v1/backend/modules/telchi/investigation/validation/corporate_sales/CHANNEL_HISTORY_FINAL_REPORT.md). El último contradice la supuesta estabilidad 2022–2026: bulk-load en 2026, sin historia individual demostrada. No agrupar automáticamente canales 2 y 3.

## Propuestas históricas

Sólo se extrajeron candidatos defendibles del inventario existente; las propuestas no generan embeddings publicados ni aparecen como conocimiento utilizable.

`telchi.stock.available` y `telchi.stock.coverage` conservan fuente, límites, relaciones propuestas con importaciones y necesidad de revisión. [Fuente documental](../../telchi/historical_business_query_inventory_v1/business_semantics.md). No se definieron por inferencia nuevas pertenencias comerciales, unidades, fórmulas de cobertura o reglas de fraccionamiento.
