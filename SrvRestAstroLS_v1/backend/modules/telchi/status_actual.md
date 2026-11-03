# Status actual - Telchi

Estado local reconciliado; observaciones operativas conjuntas publicadas en DEV, con métricas históricas y límites separados. [CONTEXT.md](CONTEXT.md) conserva la autoridad de arquitectura, roots y etapas.

## Observaciones operativas V1 — publicación conjunta acotada

`PARTIAL_PUBLISHED`: producción, compras, eventos de cobranza, prefijo OINM y consumo observado tienen datasets nuevos y readers canónicos. No es refresh integral de las métricas históricas.

- CURRENT: `foundation_42483d2e035e98e73e0a2d98ddc7d986`; anterior `foundation_d93234d13af15c1d5bef7f2f09b9335b` retenida. Reference `v2_sales_448ae93a960bf7342564a2d0` intacta. Los ocho componentes históricos, ventas, clasificación y stock permanecen exactos.
- Se publicaron conjuntamente 18 datasets fuente reutilizados y `observed_material_actual_consumption`, mediante la extensión explícita del envelope de sucesión independiente, sin noveno componente de métricas ni publicador paralelo. [Contrato y API de lectura](datalake/OPERATIONAL_OBSERVATIONS_V1.md); [informe de cierre](../../../../data/reports/telchi/operational-domains-completion-v1/report.json).
- Producción: 4.521 órdenes y 41.808 líneas de emisión. Las 31 líneas R0001 conservan clasificación desconocida por falta de identidad/tipo acreditado; 13.472 tienen evidencia BOM actual Type=290, sin atribuirle vigencia histórica. Detectadas 105 líneas que referencian 12 órdenes no capturadas: la auditoría anterior omitía BaseType `202.0` al compararlo como texto. No se inventaron órdenes ni recepciones terminadas.
- Compras: las 442 claves anteriores ausentes corresponden a 18 OC observadas ahora cerradas y no canceladas, con líneas presentes. Se acreditan dos revisiones documentales, no la causa ni fecha exacta del cambio SAP. Se preservó toda la historia; OC, recepciones y AP nuevas son observaciones separadas del lineage/métricas legacy, que siguen con su corte anterior. Sin solicitudes ni documentos de devolución nuevos.
- Cobranzas: publicados 50.687 pagos, 50.646 aplicaciones y las conciliaciones capturadas; 1.449 pagos sin aplicaciones permanecen disponibles. Facturas/cuotas son prefijo observado: no acreditan aging global actual ni reconstrucción histórica. No se convierten ausencias de cobertura en cero.
- OINM: 257.632 observaciones hasta la clave de prefijo 20.962.453; 39.619 filas de solape previo sin pérdida de claves ni cambios en fecha/producto/depósito/tipo/cantidades. El extremo de ventana sigue sin cerrar y no reemplaza el componente histórico de continuidad.
- Material Supply: 994 grupos de consumo por producto/unidad/factor, derivados de 19.984 emisiones activas con producto y orden acreditados, usando el kernel canónico y control decimal. Las demás líneas permanecen en la fuente, no se les inventa naturaleza. Los cinco datasets históricos siguen con su corte 24/09 y no se relabelan como nuevos: falta vigencia histórica BOM, cierre OINM y cobertura de todas sus dependencias.
- CAS/journal, activación, reader exacto por celda de los 19 datasets y NOOP vivo acreditados; recuperación/rollback aislados pasan, sin rollback vivo. Regresión Data Lake 761 PASS y focal final 68 PASS tras corregir el roundtrip de metadata del loader y conservar el dispatch en sucesoras. Un focal en disco venció el límite externo; su repetición tmpfs completó el gate, sin atribuirle PASS al aborto. Luna/capabilities/WhatsApp no implementados ni habilitados por esta publicación; permisos intactos. Cero SAP, recapturas, Atomic compartido, servicios, commits o push.

## Sucesión de facts V1 — publicación de stock anterior

`PARTIAL_PUBLISHED`: stock completo publicado y reader conciliado con capturas, sin sumar saldos ni refrescar movimientos. [Informe vigente](../../../../data/reports/telchi/full-foundation-facts-succession-v1/report.json).

- CURRENT: `foundation_d93234d13af15c1d5bef7f2f09b9335b`; anterior `foundation_9cd0d1a146308f555733d58fb3fda1ff` retenida. Reference efectiva `v2_sales_448ae93a960bf7342564a2d0` intacta, incluidos los 140 productos, 29 clientes y 59 proveedores incorporados.
- Stock: 1.385.179 posiciones, 17.118 productos y 82 depósitos; observación 01/11/2026 17:43:38–17:46:05 UTC. Incorporadas 13.554 posiciones, modificadas cantidades en 17.915; ninguna identidad anterior perdida. Replay exacto de cada campo contra capturas verificadas, unicidad, schema, cantidades y claves Reference. Hay 22.603 posiciones con UoM Reference desconocida: sin conversión ni agregación entre productos.
- Adapter explícito `OBSERVED_STOCK_FULL_REPLACEMENT_V1` en la cadena canónica existente. El reader conserva ventas selladas y snapshot independiente 1408; los siete componentes restantes permanecen exactos. Material Supply y CxC conservan derivación 1322 y sus cortes anteriores; no se presentan como actualizados.
- CAS, locks, activación y journal ejecutados. El primer comando venció su presupuesto externo después de activación; la reentrada sobre el mismo journal completó el reader real sin repetir commit. Comparación independiente de stock por todos los productos y depósitos, incluyendo cantidades y fecha de observación, exacta. Recuperación/rollback aislados y negativos pasan; no se realizó rollback vivo.
- El mecanismo implementado admite próximas observaciones completas de stock, no sucesiones arbitrarias de compras, producción o CxC. OINM conserva prefijo sin cierre de ventana; compras requiere resolver 442 líneas anteriores ausentes; producción conserva 31 líneas no clasificadas y no acredita recepciones terminadas; eventos de cobranza requieren su adapter separado de saldos históricos. Estas tareas y la rederivación Material Supply **no están implementadas por este cierre**.
- Cero SAP, recapturas, Atomic compartido, scheduler, permisos, servicios, commits o push. Luna no reacreditada; `DIRECT_UNAVAILABLE` previo no bloqueó la publicación de stock. Ventas y clasificación se preservaron y conciliaron mediante el reader real; no se declara FULL PASS ni readiness conversacional.

## Integración Foundation V1 — publicación parcial anterior de Reference

Cierre histórico anterior a la publicación de stock; no describe el CURRENT vigente.

`PARTIAL_PUBLISHED`: se publicó únicamente la fusión append-only de maestros. [Informe vigente](../../../../data/reports/telchi/full-foundation-integration-v1/report.json). No es un refresh integral de hechos ni un FULL PASS.

- CURRENT: `foundation_9cd0d1a146308f555733d58fb3fda1ff`; anterior `foundation_5a76699adba7eb2ab388167244e7869b` retenida. Reference: `v2_sales_448ae93a960bf7342564a2d0`, sucesora de `v2_sales_3b5cfb885a90e82fcf905d2b`.
- Incorporados 140 productos, 29 clientes y 59 proveedores desde capturas verificadas; todas las filas anteriores, sus atributos, clasificación física/comercial y crosswalks se preservan. Sin inferencias físicas ni consultas SAP.
- Ocho componentes conservados; siete componentes de hechos/derivaciones sin refresh. Snapshot independiente 1408 y derivación 1322 intactos. CAS, locks, journal, reader canónico y reentrada idempotente del publicador existente verificados.
- Sigue pendiente la sucesión multidominio de componentes independientes y la rederivación Material Supply. El adapter añadido acredita únicamente el append de Reference; no admite cambiar otros componentes por coincidencia de columnas. Compras tiene 442 claves de línea anteriores ausentes de la captura nueva: no se interpretaron como borrado ni se descartaron.
- Luna real, identidad/Console/PG: cuatro dominios sin adapter responden `DIRECT_UNAVAILABLE`. Ventas de octubre concilia con SQL independiente en diagnóstico con presupuesto explícito de 180 s; el turno default de 80 s falla y no se declara readiness conversacional del canal. No cambió ningún presupuesto runtime.
- La validación de ancestry repite proyecciones CPU-costosas. Se reutilizan proyecciones sólo dentro de cada validación y tras SHA de bytes en cada acceso; la serialización incremental conserva exactamente los fingerprints anteriores. Sin cache persistente ni atestaciones confiadas al worker.
- Las 23 capturas / 2.192.262 filas originales fueron verificadas nuevamente e intactas. Los demás dominios conservan sus cortes anteriores; no avanzaron watermarks de hechos, scheduler, permisos, Atomic compartido ni servicios. El informe detalla tests, límites y próxima transición.

## Refresh integral V1 — captura sin publicación

Cierre anterior, conservado como evidencia histórica previa a la publicación parcial de Reference; no describe el CURRENT vigente.

Dictamen `PARTIAL`: capturas multidominio reales y auditadas, sin nueva Foundation ni avance de watermarks publicados. [Evidencia del ciclo](../../../../data/reports/telchi/full-data-lake-refresh-v1/report.json).

- CURRENT vivo conserva `foundation_5a76699adba7eb2ab388167244e7869b` y Reference `v2_sales_3b5cfb885a90e82fcf905d2b`; ocho componentes lógicos, snapshot independiente 1408 y derivación 1322. El reader canónico fue verificado en este ciclo; no significa frescura integral.
- Captura iniciada con reloj SAP `2026-11-01T17:43:37.492000` UTC / `13:43:37.492000` fuente. Offset observado −04:00, sin acreditar zona IANA. Cada dataset conserva su propia ventana de observación, distinta de la fecha documental y de publicación.
- Stock: 1.385.179 filas conciliadas, 13.554 claves nuevas y 17.915 claves existentes con cantidades modificadas frente a la publicación. Cero claves anteriores desaparecidas. El maestro capturado incluye 140 productos aún ausentes de Reference publicada: requieren incorporación canónica antes de publicar sus dependencias.
- Producción, BOM, seis datasets de compras, siete familias de cobranzas y cuatro maestros capturados. OINM y documentos por cobrar detectaron avance concurrente de fuente; se revalidaron prefijos por clave nativa sin recapturar, conservando el fallo original y sin certificar cierre completo de sus ventanas. Los saldos anteriores al solape de cobranzas permanecen pendientes.
- Conciliación de producción: 13.472 líneas sin match OITM tienen evidencia BOM Type=290; otras 31 carecen de esa evidencia. No convertirlas automáticamente en consumo de materia prima ni ampliar acceso SAP a recursos por inferencia.
- El precheck canónico rechaza sustituir componentes independientes heredados de `SALES_FACTS_TRANSITION_V1` sin un adapter explícito compatible con readers. Falta implementar esa sucesión multidominio, fusionar Reference preservando clasificación, recomponer lineage/Material Supply y acreditar saldos históricos antes de promover. No se desactivó el control ni se creó un publicador paralelo.
- [Contrato operativo por dominio](datalake/full_refresh_contracts.json): presupuestos finitos, cursor único por statement, checkpoints con hashes, recuperación explícita y alertas. Scheduler deshabilitado; sin Atomic compartido, permisos, contabilidad, commits, push ni servicios ajenos modificados. Luna no fue reacreditada en este ciclo; las capacidades comerciales previas no habilitan los demás dominios.

## Sucesión incremental de ventas publicada

`INCREMENTAL_PUBLISHED_PASS`: candidata capturada reutilizada sin consultas SAP. [Evidencia del cierre](../../../../data/reports/telchi/incremental-foundation-succession-v1/report.json) y [cinco turnos reales de Luna](../../../../data/reports/telchi/incremental-foundation-succession-v1/luna-r2.json).

- CURRENT: `foundation_5a76699adba7eb2ab388167244e7869b`; anterior `foundation_881005a5a694a25dc806233dcb3838ac` retenida. Reference efectiva `v2_sales_3b5cfb885a90e82fcf905d2b`. Ocho componentes, snapshot de datos 1408 y derivación histórica 1322 conservados; Material Supply revalidado, clasificación física preservada.
- Admisión comercial por [sucesión canónica](datalake/SALES_FOUNDATION_PROMOTION_V1.md#sucesión-incremental-y-acreditación-comercial), no sustitución de IDs fijos. Schemas y metadata empresarial heredada estrictos; lineage, hashes, ledger y permisos conservan rechazo fail-closed.
- Octubre completo: facturación activa Bs 11.982.896,13; NC Bs 479.145,78; neto documental Bs 11.503.750,35. Días 30 y 31: netos Bs 502.530,33 y Bs 187.670,25. Noviembre parcial al corte 01/11/2026 13:55:47 UTC: Bs 1.643,16; no es cierre mensual ni ingreso contable.
- Cinco preguntas reales en un hilo, identidad DEV autorizada, permisos Console y auditoría PostgreSQL: PASS con tolerancia cero. Distribución física de octubre calculada desde las nuevas líneas, no del corte anterior. Sin listener, mensajes WhatsApp ni renovación automática de sus gates.
- Wrapper canónico con CAS/journal, reader real, NOOP vivo y recuperación durable PASS; rollback aislado PASS e inputs/base reales verificados, sin ejecutar rollback vivo. Watermark de cobertura publicado sólo después de reader y Luna; no es watermark global de modificaciones.
- Regresión Data Lake: 681 PASS; asistente segmentado: 297 PASS/2 skips y 425 PASS/2 skips; focal final 180 PASS. LAT y diff-check PASS. Dos comandos interrumpidos por su límite externo conservan estado `ENVIRONMENTAL_ABORT`, no PASS.
- Scheduler sigue `enabled=false`, `installed=false`; cero consultas HANA nuevas, recapturas, cambios de Atomic compartido, permisos, commits o push. Latencias conversacionales DEV 111–317 s con presupuesto diagnóstico explícito: no certifican readiness de latencia del canal ni una frecuencia de scheduler.

## Ventas por estado físico: baseline previo y conversación DEV

La integración física conserva las ventas publicadas y habilita la dimensión en el contrato comercial existente. [Evidencia de integración](../../../../data/reports/telchi/physical-sales-reference-integration-v1/report.json).

- CURRENT verificado en el cierre físico anterior: `foundation_881005a5a694a25dc806233dcb3838ac`; Reference sucesora `v2_04de6eed3805f591777012c7`, construida sobre `v2_sales_e02883116f4b4991c396010a`, no sobre la candidata física antigua. Ocho componentes, facts sellados, cobertura y snapshot 1408 conservados; derivación histórica 1322 intacta.
- 53.430 filas de productos preservadas, incluidos los 38 productos comerciales nuevos; 7.958 observaciones incorporadas sin altas inferidas. Clientes y crosswalks comerciales conservados exactamente.
- Octubre 1–29: Bs 10.189.413,12 de líneas comerciales; líquidos Bs 3.854.838,76, sólidos Bs 3.288.066,75 y semisólidos Bs 451.007,06. Cobertura física explícita: 74,53 % del importe y 51.186/83.651 líneas. Importes sin clasificación y códigos 4/5 visibles por separado; no se distribuye el total de cabeceras.
- Clasificación observada el 28–29/10/2026, no vigencia histórica de cada factura. Métrica antes de NC y ajustes de cabecera, sin IVA de línea; residuo documental no asignado ni interpretado íntegramente como impuesto.
- Publicación canónica y reader real verificados; NOOP y recuperación idempotente reales, rollback aislado y conservación de inputs reales acreditados. No se ejecutó rollback de CURRENT productivo.
- Pregunta prioritaria y nueve consultas con Luna real, identidad Console, autorización vigente y auditoría PostgreSQL PASS en DEV. Sin permisos nuevos, SAP, reextracción, scheduler, reinicios ni WhatsApp enviados. No equivale a WhatsApp E2E ni reacredita automáticamente los seis gates de arranque del canal.

## Conversación empresarial de Presidencia DEV

[Evidencia BIZ01](../../../../data/reports/telchi/biz01-conversation-v1/report.md) del 21/10/2026: diez turnos consecutivos en el pipeline HTTP autenticado y persistido, `BIZ01_CONVERSATION_PASS=YES`. Implementación DEV, no promoción ni entrega WhatsApp.

- Alcance empresarial explícito en el estado: slots aditivos (`/business_category`, `/product_target`, `/customer_target`, `/group_by`, `/periods`, `/period_mode`, `/breakdown_by`) y proyección de servicio `/focus` (producto y cliente en foco). Los estados persistidos que no los usan conservan su forma.
- El incidente del 21/10 no puede repetirse: una mención que no es código de categoría en una operación de producto o categoría se rechaza, y el producto tiene slot propio. La unión de dos meses es un conjunto contiguo que el motor convierte en ventana; nunca un mes.
- Primera familia analítica reutilizable: `sales.commercial_line_amount_by.v1` (importe de líneas comerciales BS por producto o por cliente facturado), con plan cerrado `dataset + filters + period + group_by + measure + ordering + limit` validado en backend. Permiso propio `telchi.sales.commercial_line_amount_by.read.v1` registrado en DEV por el mecanismo local idempotente, sin asignaciones, roles, perfiles ni cambio de FULL_ACCESS.
- L03281 julio+agosto 2026: Bs 586.227,06 (2.014 líneas, 2.012 facturas, 468 cuentas facturadas); cliente facturado líder FARMACORP S.A. (C000061) Bs 115.044,44 (julio Bs 72.383,99, agosto Bs 42.660,45); participación 19,62 %. Reconciliación de tolerancia cero en cada lectura.
- BUSINESS ANSWER FIRST transversal: la respuesta entrega el resultado acreditado, la excepción, el riesgo y el próximo paso. La taxonomía de cliente comercial sigue sin acreditar (0 clasificados): se advierte y no se bloquea, y las cuentas de control tributario de SAP se muestran y se cuantifican sin depurarlas.
- 1.082 tests focalizados PASS. `SIX_GATES=VALID` reacreditado para el fingerprint final con el procedimiento local vigente; runtime STOPPED, sin WhatsApp enviado. La validación WhatsApp real es manual y pertenece al owner.

## Respuesta empresarial y ranking histórico DEV

La ampliación local reutiliza el ranking monetario y conserva Foundation, clasificación y permisos. [Evidencia y estado de aceptación](../../../../data/reports/telchi/business-answer-historical-ranking-v1/report.md) separan cálculo, conversación autenticada y gates vigentes.

- Causa reproducida: guard monetario previo más amplio que la categoría solicitada; L01412 es RAW_MATERIAL acreditado y no participa en el ranking terminado. Su moneda de línea difiere de cabecera también en raw; esto no demuestra un error SAP ni autoriza denominar LineTotal en USD.
- `ANSWER_FIRST_WITH_EXCEPTIONS`: resultados por período independientes; exclusiones monetarias internas explícitas y parciales, anomalías externas separadas en auditoría. Sin desactivar claves, procedencia, clasificación, conciliación ni RBAC.
- Dos períodos usan `period`/`comparison`; producto objetivo separado de categoría. Ranking completo antes de localizarlo, sin depender del Top 5. [Contrato](assistant/PRODUCT_MONETARY_RANKING_V1.md#posición-histórica-compatible).
- Implementación DEV, no promoción ni prueba WhatsApp. El original permanece intacto; la aceptación manual pertenece al owner. No iniciar ni reiniciar automáticamente el runtime.

## Ranking monetario por producto DEV

[Product Monetary Ranking V1](../../../../data/reports/telchi/product-monetary-ranking-v1/report.md) validado en DEV el 20/10/2026; aceptación final pendiente de comprobación WhatsApp del owner.

- `sales.product_line_amount_ranking.v1` y permiso propio registrados idempotentemente por mecanismo local oficial; FULL_ACCESS scoped sin grants adicionales, aislamiento y revocación transaccional verificados. Sin cambios a resolver compartido, Foundation, SAP o clasificación.
- Top 5/10 terminado y Top 10 materia prima reales; desglose completo terminado: 278 productos / 18.541 líneas / Bs 2.679.208,66, diferencia cero con agregado. Cobertura 1–24/09/2026, sin IVA de línea, antes de NC y ajustes globales; no precio unitario ni neto documental.
- Estado/propuesta exactos del incidente persistido verificados en PG, copiados sólo a hilos nuevos; original intacto. Secuencia A–E, formulación original, ordinal y distinción de precio/cantidad con Luna Medium, HTTP/dispatcher/Console/PG/Foundation reales PASS. Formatter corregido; State Engine sólo amplía vocabulario de métrica, no algoritmo.
- 323 tests focalizados PASS; seis garantías DEV reejecutadas/reacreditadas para fingerprint final, `SIX_GATES=VALID`, `READY_FOR_MANUAL_WHATSAPP=YES`. Runtime STOPPED: carga/prueba manual necesaria; cero servicios iniciados/detenidos, WhatsApp enviados o entregas encoladas. Presidencia no implementada.

## Ventas monetarias por categoría DEV

Activación scoped DEV del 20/10/2026: [registro, verificaciones y límites](../../../../data/reports/telchi/category-scoped-registration-v1/report.json). No implica promoción productiva.

- `CATEGORY_CAPABILITY=READY`: capability y permiso vinculados únicamente en tenant Telchi / `telchi_dev` / módulo `telchi`. Registro idempotente y auditado con backup privado; FULL_ACCESS, resolver, roles, perfiles y asignaciones preexistentes intactos; cero grants individuales nuevos.
- Backend HTTP DEV autenticado sobre ASGI, identidad Console/teléfono y PostgreSQL reales: RAW_MATERIAL septiembre Bs 839.582,63 (34 productos / 526 líneas / 495 facturas); producto terminado Bs 2.679.208,66 y repregunta comparativa PASS con Luna Medium. Importes de líneas comerciales sin IVA de línea, antes de NC y ajustes globales, no neto/cobros; cobertura parcial 1–24/09/2026.
- Denegación no privilegiada, tenant/workspace/módulo, revocación de la capability con rollback, ausencia de cambios en permisos ajenos y operación documental previa verificadas. 34 tests focalizados PASS; evidencia anterior 256 PASS / 1 SKIP y PG opt-in 34 PASS retenida tras cotejo de hashes, no reejecutada.
- `SIX_GATES=VALID`, `READY_FOR_MANUAL_WHATSAPP=YES` para el fingerprint acreditado, política DEV change-based sin expiración artificial. Runtime STOPPED; sin listener, login humano, ingreso/entrega WhatsApp ni certificación de producción. Sin reinicios, infraestructura, Foundation, SAP o clasificaciones modificados.
- Presidencia no implementada: futura integración Console deberá permitir al dueño y Abraham idéntico alcance empresarial de lectura, sin administración técnica. Próximo paso: prueba WhatsApp manual del owner con el launcher existente.

## Estado vigente

Se distingue capacidad Foundation productiva de candidatos semánticos. Los IDs son los consignados por los cierres, no una inspección operacional nueva de CURRENT.

- Data Lake V1 cerrado; Receivables & Collections Extension V3 PASS productivo. V1/V2 fueron revertidos; QR continúa `UNRESOLVED_SOURCE_EVIDENCE`.
- Baseline anterior, consignado por la promoción de ventas del 30/10/2026: `foundation_38680850adc058b1bb11887632b7b681`, Reference `v2_sales_e02883116f4b4991c396010a`, ocho componentes, reader canónico verificado y conciliación documental de tolerancia cero (septiembre Bs 10.591.046,24; octubre 1–29 Bs 10.811.322,92). [Resultado](../../../data/reports/telchi/sales-foundation-nominal-promotion-20261030/postpublication.json) y [runbook](datalake/SALES_FOUNDATION_PROMOTION_V1.md). La transición de CURRENT ocurrió con el wrapper previo, que exigía autorización nominal; el mecanismo ya corregido revalidó la publicación de forma idempotente, sin exigir esa autorización y con auditoría automática del journal.
- CURRENT anterior `foundation_afd08d9eca6a725be53cdc3f9d5709c9` permanece inspeccionable; el ID V3 `foundation_d222a203801cc84e9a14164d26aa67a0` describe aquella promoción, no una lectura actual.
- Temporal Commercial Purpose V1 PASS semántico, sin promoción; candidate `foundation_15cfdba7ff7ff94011d26fa1b93bf266`. Se separan historia, propósito legacy y clasificación por período/cobertura.
- Source Gap Closure DEGRADED: 696 UNKNOWN residuales y 110 productos UoM no resueltos. La validación temporal sustituye el blocker temporal; no cierra los gaps restantes ni autoriza promoción.
- Product Commercial Semantics Closure DEGRADED: brand UNKNOWN e importe neto por producto no resuelto. Los ocho componentes originales, UoM y parity quedan preservados según evidencia.
- API Telchi formal, scheduler y resolver automático no declarados implementados. La foundation runtime es opt-in; frontend TelchiAI untracked es trabajo local sin gate/deploy declarado.
- SAP/HANA permanece read-only; esta normalización no consultó SAP, Data Root ni secretos y no cambió CURRENT.

## Frente Messaging ↔ Telchi

Se reconoce implementación DEV y profiling investigativo existentes del 08/10, sin promoción, cambios a CURRENT ni atribución de autoría. CONTEXT conserva la autoridad arquitectónica.

- Consulta fija de ventas vía [Messaging adapter](../messaging/telchi_sql.py) y [query Data Lake](datalake/messaging_sales_query.py); DuckDB sobre Parquet Foundation pinned/read-only, PostgreSQL para catálogo/persistencia. No constituye API Telchi formal ni routing general.
- Profiling `STAGE=INVESTIGATION`, source Data Lake: `TEAM360_TELCHI_DATALAKE_PRE_SQL_PROFILE_V1=PASS`, autónomo y validación WhatsApp real según [reporte canónico](../../../../data/reports/messaging/telchi-datalake-pre-sql-profile-v1/report.md). Sin LLM, SAP ni capacidad productiva inferida.
- Condición operativa documentada al cierre: callback Meta anterior no restaurado, suscripción temporal retirada y ninguna suscripción Meta Team360 activa. No corregido ni revalidado aquí; [navegación Messaging](../messaging/README.md).

## Asistente comercial DEV

Sales RBAC & Business Runtime V1 activa dos operaciones documentales para el piloto de `telchi_dev`; no promueve producción ni cambia Foundation CURRENT.

- `sales.latest_documents` y `sales.coverage`: DATA_PASS, SEMANTIC_PASS, AUTH_PASS y BUSINESS_RUNTIME_PASS acreditados; sólo OINV activas por DocDate, sin importe neto ni mes completo certificado.
- Permisos efectivos Console: los dos nuevos más `telchi.sales.source_quantity.read.v1`, sin grants globales al piloto ni cambios a otros clientes. Backup privado, auditoría e idempotencia verificados.
- HTTP real: B01–B06 y SQL independiente del snapshot 1408; controles negativos, guard committed=False y ranking original preservados. [Gates y límites observados](../../../../data/reports/telchi/sales_rbac_business_runtime_v1/GATES.md).
- Regla permanente IMPLEMENTED/ACTIVATED y provisioning acotado: [contrato del asistente](assistant/README.md#gates-permanentes-de-activación). Luna, State Engine, Messaging, Foundation y SAP sin modificaciones en este cierre.

## Facturación documental DEV

El incremento monetario reutiliza el contrato financiero histórico y activa importes por período; no promueve Foundation, producto neto ni resolución Calenta.

- `sales.period_billed_amount.v1`: DATA_PASS, SEMANTIC_PASS, AUTH_PASS y BUSINESS_RUNTIME_PASS para cabeceras activas BS, DocTotal y NC. Muestra facturación válida y neto documental por separado.
- Permiso específico efectivo para `devfull@telchiai.com` / `telchi_dev`; mayo, junio y continuidad obtenidos por HTTP, seis cotejos independientes con diferencia cero sobre CURRENT 1408.
- Ambas métricas permanecen en estado; cantidades mensuales no habilitadas se explican sin sumar unidades incompatibles. Calenta conserva productos/SKUs documentados y brecha de crosswalk; consulta empresarial BLOCKED.
- Cierre global del incremento PARTIAL: recuperación literal de algunas ejecuciones históricas/entrega externa pendiente e intermitencia de Luna en últimas facturas (`/pending` rechazado, cero ejecución). Modelo GPT-5.6 Luna Medium y engine V2 conservados; catálogo interpretativo actualizado.
- [Gates, contratos y evidencia canónica](../../../../data/reports/telchi/sales_monetary_entity_resolution_v1/GATES.md). Sin SAP, reingestión, cambio CURRENT, deploy ni cambios horizontales.

## Continuidad documental y líneas de factura DEV

Implementación V1 validada el 18/10, sin sustituir el runtime activo ni promover Foundation. [Contrato](assistant/README.md#continuidad-documental-y-productos-de-factura-v1) y [evidencia focalizada](../../../../data/reports/telchi/document-continuity-invoice-lines-v1/report.md) conservan los límites.

- Referencias independientes a factura y línea, persistidas en el namespace JSON existente; sin cambios al State Engine, Messaging ni memoria general nueva.
- `sales.invoice_lines.v1`: relación OINV/INV1 acreditada en Foundation 1408. Factura N.º 260192728: una línea L00003, cantidad documental 10; descripción de catálogo, UoM nativa de línea no publicada. Sin inferir litros/kg, conversiones ni importes.
- `telchi.sales.invoice_lines.read.v1` registrado y efectivo únicamente mediante rol local `telchi_dev` para el piloto autorizado; seis grants anteriores, identidades y habilitación WhatsApp preservados. Auditoría administrativa, backup privado e idempotencia verificados.
- Luna Medium real y Foundation real: secuencia completa de nueve turnos PASS en sonda con identidad/puerto de persistencia fixture explícitos. PostgreSQL temporal y negativos de permisos/aislamiento validados por separado; no equivalen a runtime autenticado WhatsApp.
- El cierre del 18/10 dejó código IMPLEMENTED y gates STALE. Esa condición documental queda sustituida por la reacreditación comercial DEV siguiente; no implica que se haya iniciado el runtime ni enviado WhatsApp.

## Cierre funcional comercial DEV

El [reporte verificable](../../../../data/reports/telchi/business-assistant-close-v1/report.md) acredita cinco respuestas y una limitación explícita con Luna, identidad, PostgreSQL y Foundation reales; no declara producto completo ni WhatsApp E2E.

- FULL_ACCESS dinámico implementado en el resolver compartido y asignado exclusivamente al piloto DEV existente, limitado a organización/workspace/módulo y registro habilitado. Migración 031 aplicada sólo en PostgreSQL local DEV; grants normales preservados, cero asignaciones individuales nuevas al piloto. Revocación/auditoría verificadas con rollback.
- Facturación registrada BS: septiembre 2026 Bs 8.891.439,79; agosto Bs 10.565.113,13. Datos actualizados al 28/09/2026: septiembre no es un cierre completo. Notas de crédito y neto documental se muestran por separado, sin confundirlos con cobros o saldos.
- `sales.invoice_amount.v1`: total documental de factura N.º 260192728 = BS 25,00; misma referencia tras consultar sus productos. Permiso comercial independiente; sin reconstrucción por líneas ni conversión.
- Continuidad real persistida en ese cierre: septiembre → agosto → limitación de comparación → cinco facturas → productos de la primera → importe de esa factura. La limitación de comparación quedó sustituida por la validación focalizada siguiente.
- 241 tests focalizados PASS (127 del recorrido/seguridad, 78 del handler/provisioning y 36 del evaluador de intercambio manual), incluidos PostgreSQL temporal y consumidores Console/Flow afectados; paridad SQL independiente con diferencia cero. Seis gates DEV reacreditados con política vigente change-based: `SIX_GATES=VALID`, `READY_FOR_MANUAL_WHATSAPP=YES` al cierre y para el fingerprint acreditado.
- Runtime permanece detenido; ningún servicio del operador iniciado/detenido ni WhatsApp enviado. Foundation CURRENT, SAP, transportes e infraestructura no modificados. El siguiente paso es prueba manual con el launcher existente; cambios posteriores relevantes invalidan el fingerprint, no la autorización permanente del piloto.

## Calidad conversacional DEV

La [sonda real focalizada](../../../../data/reports/telchi/conversational-quality-v1/live-final.json) acredita ocho turnos; no acredita entrega WhatsApp ni renueva su admisión operacional.

- Causa del rechazo sin signos del 19/10: Luna emitió `/product_context` en `unset`; el State Engine rechazó un campo del servicio. No fue una restricción demostrada por puntuación. Fix acotado a descarte en NEW_QUERY; escrituras/contextos inventados y `/pending` siguen rechazados.
- Ambas formulaciones de septiembre, agosto, diferencia, porcentaje y continuidad documental PASS con Luna Medium, identidad Console, PostgreSQL y Foundation reales. Diferencia septiembre respecto de agosto: BS −1.673.673,34 / −15,84 %, con septiembre parcial; no representa caída mensual definitiva.
- Comparaciones locales con Decimal, procedencia original y revalidación efectiva de permisos: cero llamadas a Foundation. 215 tests focalizados PASS, incluidos PG temporal, replay, incompatibilidades y aislamiento; sin cambios a Foundation, capacidades comerciales ni resolver compartido.
- [Seguridad y admisión](../../../../data/reports/telchi/conversational-quality-v1/security-and-admission.json): identidad real y permiso revocado con rollback PASS; grants ordinarios originales verificados tras restauración. Fuente cambiada: manifest previo rechazado por `gate_scope_mismatch`; `READY_FOR_MANUAL_WHATSAPP=NO` hasta reconciliar sólo garantías afectadas bajo política DEV change-based. No se inició/detuvo ningún servicio ni se envió WhatsApp.
- Un intento inicial de la sonda abortó en preflight de período faltante, sin propuesta raw conservada; no se atribuye una causa a esa variabilidad. Sonda final focalizada PASS no garantiza comprensión universal. [Contrato local](assistant/README.md#calidad-conversacional-y-comparación-local).

## Fiabilidad de entrega WhatsApp V1

La [corrección del 21/10/2026](../../../../data/reports/telchi/delivery-reliability-v1/report.md) parte de causas ya demostradas en la sesión `c716012d8a10876a1cd8e617b5076bd4` y no repite la auditoría general.

- Entrega: guarda determinística antes del proveedor (Meta acepta 4.096 caracteres). Nunca corta una línea, nunca altera una cifra, un nombre o una advertencia, y declara lo omitido. El texto acreditado completo queda en la auditoría; el entregado es el resumen.
- Fallo del proveedor: un rechazo explícito es fallo confirmado aunque Evolution responda 2xx; el estado incierto queda para resultados realmente inciertos y nunca se reenvían solos.
- Fallo del intérprete: código técnico redactado con tipo, status, duración y reintento; la respuesta explica la falla técnica y no se atribuye a la forma de preguntar. Ninguna capability se ejecuta tras un fallo de interpretación. Reintento acotado a un intento ante fallos transitorios, sin fallback, proxy ni cambio de modelo.
- Límite por familia analítica: un ranking de 50 no contamina una consulta posterior de productos o clientes; una cantidad pedida explícitamente se respeta.
- Presentación: resultado principal, períodos, participación acreditada (19,62 % para FARMACORP sobre L03281; **35,7 % es incorrecto** y no debe introducirse), advertencias materiales y paso siguiente. Ningún listado de 50 elementos.
- Sesión DEV: `idle_timeout` 900 s y `max_duration` 14.400 s en lugar de la duración fija de 600 s, con actividad verificable, turnos en curso protegidos y extensión por el control privado existente. Identidad, ownership, gates y restauración del webhook no cambian. El control privado todavía conservaba la clave legacy `duration: 600`, que hacía fallar el arranque con `idle_timeout_exceeds_max_duration`; quedó migrado a las dos claves nuevas (respaldo privado, bloque `env` de credenciales byte a byte idéntico).
- Validación: BIZ01 real 10/10 (`conversation_pass=true`), 633 tests del asistente PASS y sonda live del intérprete PASS con «me das la facturacion de septiembre 2026». `WHATSAPP_E2E=NOT_RUN`.
- Credenciales: cuatro potencialmente expuestas por el diagnóstico previo; **no se rotó ninguna** y no se imprimió ningún valor. La rotación coordina servicios compartidos y requiere autorización separada. [Inventario y procedimiento](../../../../data/reports/telchi/delivery-reliability-v1/report.md#5-credenciales-coordinación-requerida-no-se-rotaron).

## Reacreditación final de gates DEV

La [reacreditación del 22/10/2026](../../../../data/reports/telchi/six-gates-reaccreditation-20261021/report.md) reactiva las seis garantías sobre el código final de la V1 de fiabilidad, sin iniciar sesión ni enviar WhatsApp.

- `SIX_GATES=VALID` para el digest final `283418ac…`, con las seis garantías `PASS` y `kind=real`, artefacto privado y hash exacto por gate. Registro DEV v2 `change_based_v1` (sin `expires_at`): la validez depende del código, la aprobación y la configuración, no del reloj.
- Causas reales del `INVALID` previo, ambas corregidas: digest de fuente obsoleto por los cambios de la V1, y forma de registro DEV regresionada a la vigencia artificial de cuatro horas, ya expirada.
- Segundo bloqueo independiente: el control privado conservaba `duration: 600`, con lo que el arranque manual fallaba en `session_timing` aunque los gates fueran válidos. Migrado a `idle_timeout` 900 s y `max_duration` 14.400 s, con respaldo privado y credenciales intactas.
- Verificación: `gate_evidence` PASS, `preflight` en la vía normal con gates requeridos PASS, `telchiai-dev.sh status` con `gates: VALID` y `state: STOPPED`, 753 tests PASS y 322 ficheros del alcance del digest sin cambios concurrentes. El primer intento bloqueó por una fixture de permisos que heredaba el `umask 077` del runner, no por defecto del producto; ambos logs quedan preservados.
- Límites: `WHATSAPP_E2E=NOT_RUN`, sin mensajes, webhook, grants, bindings, credenciales ni Foundation modificados, y la rotación de credenciales sigue pendiente de ventana propia.

## Categorías empresariales y ventas V1

La [corrección e investigación separadas](../../../../data/reports/telchi/business-categories-sales-v1/report.md) preservan el State Engine, Foundation, RBAC y capabilities existentes; no habilitan importes por categoría.

- DEVELOPMENT: Luna distingue categoría, producto/código, búsqueda textual y consumo; seis turnos reales Medium PASS. RAW_MATERIAL y productos terminados conservan intención monetaria y septiembre de 2026 sin búsqueda sustituta. Catálogo bloquea ejecución incompatible y respuesta explica indisponibilidad sin cifras investigativas.
- INVESTIGATION READ ONLY: atribución PARTIAL; join de líneas/categorías verificable, conciliación DocTotal versus líneas no acreditada por impuestos/descuentos/ajustes faltantes, NC standalone/devolución y clasificación no historizada. Contrato monetario sólo propuesto, pendiente del owner.
- `SIX_GATES=STALE`, `READY_FOR_MANUAL_WHATSAPP=NO`; la sonda no renueva admisión operacional. Sin reinicio, WhatsApp, nuevos permisos, cambio de clasificación ni capability monetaria nueva.

## Distribución documental e importe por categoría

La [investigación READ ONLY](../../../../data/reports/telchi/category-line-amount-reconciliation-v1/report.md) confirma recurrencia, no concentración extrema; el owner autoriza desarrollar líneas comerciales sin exigir conciliación contable completa.

- 97,1222 % de 30.301 facturas activas con diferencia material; top 100 concentra 25,7079 % de diferencias absolutas. Patrón cercano al 13 % observado, sin causa fiscal acreditada.
- [Contrato DEVELOPMENT](datalake/CATEGORY_LINE_AMOUNT_V1.md) diseñado, no implementado: BLOCKED por acreditación independiente de denominación LineTotal/moneda local, no por el residuo global. Suma de campo de materia prima reproducida; no sustituye contrato monetario.
- Console DEV READ ONLY: Presidencia no representada por perfil/rol encontrado; requiere integración coordinada sin privilegios técnicos automáticos. FULL_ACCESS existente y aislamiento del resolver verificados, sin nuevos grants.
- 83 tests focalizados y un test PostgreSQL temporal PASS. Nueva sonda Luna Medium real: cinco turnos PASS / uno FAIL (EXECUTE con metric nula al buscar código), sin cambios de runtime ni atribución causal nueva. No reemplaza el PASS fechado anterior por una garantía universal.
- `SIX_GATES=STALE`, `READY_FOR_MANUAL_WHATSAPP=NO`; sin servicios iniciados/detenidos, WhatsApp, promoción o cambios de Foundation/permisos.

## Evidencia y navegación

Los contratos y reportes conservan matrices, conteos, candidates y límites completos. La investigación histórica permanece donde está, sin convertirse en autoridad arquitectónica.

- [Contrato temporal](datalake/TEMPORAL_COMMERCIAL_PURPOSE_V1.md) y [reporte](../../../../data/reports/telchi/temporal_commercial_purpose_v1/report.json).
- [Semántica comercial](datalake/PRODUCT_COMMERCIAL_SEMANTICS_V1.md) y [source-gap](../../../../data/reports/telchi/product_commercial_semantics_source_gap_v1/report.json).
- [README / etapas](README.md), [runtime foundation](RUNTIME_FOUNDATION.md), [investigation](investigation/README.md).
- [Histórico de cierres](../../../docs/status_historico_hasta_normalizacion_2026-10-06.md) y [estado GLOBAL](../../../docs/status_actual.md).

## Próximo paso

La promoción del candidate temporal requiere gate explícito separado. No inferir certeza comercial desde cobertura parcial ni resolver business unknown automáticamente con nueva ingestión.
