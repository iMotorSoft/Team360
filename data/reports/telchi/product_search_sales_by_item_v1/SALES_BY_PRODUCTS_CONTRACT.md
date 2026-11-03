# Sales by products contract

Foundation `foundation_afd08d9eca6a725be53cdc3f9d5709c9`, snapshot **1408**, CURRENT efectivo confirmado; solo DEV y lectura. Sin SAP, modificaciones canónicas, reingestión, deploy ni cambio de modelo.

Operación `sales.by_products`, permiso `telchi.sales.by_products.read.v1`; el handler exige además el permiso de búsqueda. Entrada: conjunto único de 1..20 ItemCodes verificados, namespace SAP_HANA, período opcional completo (inicio/fin exclusivo, hasta 366 días), límite 1..50.

No recibe texto de nombre para filtrar ventas. JOIN línea/cabecera por source_system y DocEntry; filtro comercial por IDs exactos. Política de últimas ventas: OINV activas CANCELED=N, sin NC; no es venta neta. Orden DocDate, DocEntry y LineNum descendentes. No impone último mes.

Resultado: fecha, tipo OINV, DocEntry/DocNum, número de línea, ItemCode, descripción original, Quantity documental y UoM de catálogo como metadata separada. Grano invoice_line, nunca factura completa. Varias líneas del mismo producto siguen siendo líneas distintas, no documentos duplicados.

Resumen por ItemCode: conteo de líneas activas y primera/última fecha para todo el período consultado, independiente del límite temporal. No agrega cantidades físicas ni importes. Un vínculo huérfano/duplicado se rechaza; un vacío correctamente unido no certifica ausencia fuera de cobertura.
