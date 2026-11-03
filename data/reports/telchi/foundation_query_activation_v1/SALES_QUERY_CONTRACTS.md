# Sales Query Contracts

Contrato cerrado de dos lecturas documentales candidatas. No incluye importe ni suma física; cada operación nueva exige un grant propio además del acceso base y del scope workspace aprobado.

## Parámetros y permisos

La allowlist se valida antes de crear el worker. No se interpolan valores, entidades ni columnas del modelo en SQL.

| Operación interna | Capability | Parámetros | Grant específico |
| --- | --- | --- | --- |
| sales.latest_documents | sales.latest_documents.v1 | limit entero estricto 1..50, default 10 | telchi.sales.latest_documents.read.v1 |
| sales.coverage | sales.coverage.v1 | ninguno; referencia latest_available_month permitida | telchi.sales.coverage.read.v1 |

`date_from`, `date_to_exclusive`, `entity_type`, `entity_id`, `metrics`, `group_by`, `sort` no se aceptan por este servicio: no son parámetros autorizados de estas dos operaciones. No hay query genérica ni SQL del modelo.

`limit` es opcional compatible con estados anteriores; NEW_QUERY no lo hereda. Períodos del State Engine conservan ISO y máximo 366 días para otras métricas. No se exige período a latest/coverage. Entidad, sucursal, canal, comparación, período concreto y solicitudes multimétrica bloquean esta primera versión.

## Hechos y resultados

Las dos consultas leen sales_document, fuente SAP_B1_HANA, CANCELED=N. Son facturas OINV activas por fecha documental, no movimientos de producción, registro cronológico ni ventas netas.

Latest: grano cabecera; source_system + doc_entry es identidad fuente. Orden DocDate DESC, DocEntry numérico DESC y desempate textual; se excluyen fechas nulas. Devuelve DocEntry, DocNum, DocDate y N. No expone cliente, líneas, productos, Quantity, moneda ni DocTotal en esta versión. Esos campos existen históricamente, pero no se aprobó su exposición/semántica adicional.

Coverage: primera/última DocDate y número de cabeceras activas con fecha; último mes se toma de la última fecha real. `complete_month_certified=False` siempre. No certifica historia completa, cobertura monetaria, ventas netas ni último mes cerrado. Sin filas devuelve cobertura desconocida, nunca ventas cero.

Cancelaciones Y/C excluidas expresamente; notas de crédito excluidas de ambas relaciones. No se computan impuestos, descuentos ni importes. No hay agregación de unidades incompatibles ni atribución comercial por descripción.

## Fronteras de ejecución

No se cambió identidad, Messaging, Srv05, modelo ni State Engine por otro sistema. El registro SalesCapabilities es la implementación existente extendida, no un motor paralelo.

TelchiHandler sólo entra tras `committed is True`, acción EXECUTE y availability. Revalida el permiso base y el grant específico con PermissionConsoleRepository; el permiso en identidad no sustituye la revalidación PostgreSQL. Nuevo acceso exige tenant Telchi, entorno DEV y workspace coincidente. Rechazos ejecutan cero capabilities y cero lecturas Foundation.

El worker verifica attachment read-only y CURRENT exacto 1408/publicación aprobada; si CURRENT cambia falla cerrado. Usa dos threads, 512 MB, sin temp spill; timeout 30 s y reap del hijo propio. No escribe datos Foundation, snapshots ni configuración global. La persistencia conversacional existente del runner HTTP sí escribe auditoría PG, como requiere su contrato; no se confundió con DML empresarial.

El grant real del piloto sólo autoriza V1 fijo. Los nuevos códigos no fueron insertados, concedidos ni usados como permisos implícitos. Toda activación queda pendiente de autorización y provisioning explícitos.
