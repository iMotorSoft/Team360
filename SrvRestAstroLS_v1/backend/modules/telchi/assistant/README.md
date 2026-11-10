# Telchi conversational assistant V1

Handler DEV opt-in sobre Messaging horizontal. [CONTEXT](../CONTEXT.md) conserva la autoridad Telchi; el [reporte verificable](../../../../../data/reports/telchi/whatsapp-assistant-v1/report.md) distingue integración local de operación WhatsApp.

## Composición y acceso

El módulo utiliza la inyección existente de Srv05, sin cambiar su bootstrap ni Messaging. No hay registro automático ni configuración productiva nueva.

`composition.create_telchi_app(policy=..., pool=...)` registra `TelchiHandler` mediante `create_app(messaging_handlers={'telchi': ...})`. Requiere una `BusinessPolicy` aprobada. Si se omite pool, usa `get_pool` existente de forma lazy, después del startup; no crea otro pool o lifecycle.

No existe un permiso comercial por defecto. Los permisos generales Console no se convierten en permisos de ventas. `module_enabled=False` y `whole_workspace_scope_verified=False` deniegan por defecto. El segundo flag es una atestación de composición, NO un grant RBAC ni un resolver de scope.

El owner debe acreditar que el permiso elegido concede lectura de TODO el workspace a sus titulares antes de habilitar ese flag. Los permisos limitados por sucursal/cliente/datos no son suficientes para la consulta global V1: se bloquean, nunca se amplían. La selección operacional está aprobada sólo para Telchi DEV en el cierre [Sales RBAC & Business Runtime V1](../../../../../data/reports/telchi/sales_rbac_business_runtime_v1/ACTIVATION_REPORT.md); no implica habilitación productiva.

## Contexto empresarial autenticado

El handler entrega a Luna `enterprise_context` después de autorizar el turno. Identidad, canal y política deben coincidir en tenant/workspace; el módulo identifica Telchi como empresa propia, nunca desde el texto del usuario.

La empresa titular no es un filtro comercial. Clientes, proveedores, marcas, productos y empresas externas conservan su significado; no se borran menciones para ejecutar consultas globales. El contexto no otorga permisos ni agrega aliases inferidos. La [evidencia V1](../../../../../data/reports/telchi/enterprise_context_v1/report.md) distingue la única prueba real del intérprete, negativos offline y permisos efectivos registrados, sin renovar gates ni certificar WhatsApp.

## Contrato del turno

El intérprete propone cambios; el motor confirma solicitudes; la capability produce resultados. Son responsabilidades distintas, con una barrera explícita antes de ejecutar.

- Entrada: `InboundMessage` y `MessageContext` confiable. Telchi no identifica usuarios desde el texto ni usa allowlists telefónicas.
- Modelo: OpenAI Responses directo, `gpt-5.6-luna`, `medium`, `OpenAI_Key_JAI_query`, `store=false`; verifica modelo y esfuerzo devueltos. Sin proxy, redirects, fallback, herramientas o segundo verificador.
- Propuesta: `intent`, `action`, `state_delta={set,unset}`, `clarification`. Paths: metric, period, branches, sales_channel, comparison, reference. Prefijos de paths se normalizan sin resolver conflictos.
- Estado: métrica, período objetivo, sucursales, canal, baseline de comparación, referencia a solicitud anterior y aclaración pendiente. Las listas extendidas son conjuntos finales; remove restaura defaults explícitos.
- ASK: confirma sólo pending con propuesta conocida y hash del estado activo; no ejecuta. ANSWER_CLARIFICATION aplica la propuesta y respuesta; pending obsoleto se rechaza.
- `committed is not True`: `EXECUTION_FORBIDDEN`. No se ejecuta el raw, el estado rechazado ni la consulta anterior retenida.
- EXECUTE: exige estado listo, capability/params aprobados y permisos efectivos Console revalidados. EXPLAIN no autoriza ejecución.
- Mapping/métrica/cobertura no disponibles: guarda la solicitud validada para continuidad, marcada `not_executed`; nunca la presenta como un resultado.
- Fallo de capability: conserva estado anterior y audita el fallo, sin inventar cifras. Rechazo: ERROR seguro, sin entregar una aclaración raw rechazada.

El motor sólo certifica contrato, no comprensión semántica perfecta. No infiere años, mappings, autorización, conversiones ni cifras. `REFERENCE` restaura solicitudes anteriores retenidas (hasta 20); `RESULT_REFERENCE` selecciona resultados mediante el contrato independiente descrito más abajo.

## Extensión conversacional V2

La extensión separa intención y ejecutabilidad sin crear capabilities. El [diagnóstico real](../../../../../data/reports/telchi/whatsapp-assistant-dev-live-v1/real_conversation_diagnosis.md) conserva evidencia y límites.

Los estados V1 persistidos siguen siendo válidos y el namespace PG no cambia. Al usar paths nuevos, el motor materializa `schema_version=2`, `requested_metrics` (orden de prioridad; su primera métrica coincide con `metric`), `entity_mention={text,type:null}` y `temporal_reference=latest_available_month|null`.

No se inventa tipo comercial ni mapping. La referencia al último mes queda sin período concreto. La operación documental `sales.coverage` puede resolverlo para facturas activas, pero exige su grant específico; no sustituye cobertura monetaria ni por entidad. Un mes explícito usa intervalo semiabierto y limpia la referencia relativa.

`NEW_QUERY` V2 construye la propuesta desde defaults, no desde una consulta anterior. `ASK` mantiene protegido el estado activo; la intención conocida está en `pending.proposed`. Un segundo ASK como respuesta conserva esa propuesta y verifica el hash. El motor rechaza aclaraciones sobre métricas V2 ya seleccionadas o períodos V2 ya expresados.

El handler no pregunta fechas para desbloquear importes/filtros/metadata que el catálogo declara ausentes: responde desde la propuesta pendiente validada, sin ejecutarla ni reemplazar el estado activo. `DIRECT_UNAVAILABLE` consulta el catálogo sólo para clasificar; nunca ejecuta. Ambas métricas permanecen representadas aunque ninguna consulta conjunta esté habilitada.

El catálogo distingue `METRIC_MISSING`, `MAPPING_MISSING`, `TEMPORAL_METADATA_MISSING`, `PERIOD_PARAMETER_UNSUPPORTED` y ventana fija excedida (`COVERAGE_GAP`). Ninguna categoría certifica ausencia de filas o cobertura histórica empresarial.

## Catálogo disponible

La primera lectura aprobada reutiliza la consulta fija Foundation existente. Las extensiones documentales candidatas no amplían ese permiso; su [activación y bloqueos](../../../../../data/reports/telchi/foundation_query_activation_v1/ACTIVATION_PLAN.md) se acreditan por separado.

`sales.latest_documents` y `sales.coverage` leen cabeceras OINV activas N de CURRENT 1408 por DocDate. Últimos documentos admite límite 1..50 (default 10), sin período obligatorio; cobertura determina fechas y mes con filas sin certificar completitud. No exponen importe, cantidad física ni filtros de entidades.

Requieren respectivamente `telchi.sales.latest_documents.read.v1` y `telchi.sales.coverage.read.v1`, además de identidad, acceso base y scope aprobado. El handler revalida esos grants efectivos antes de la capability; el grant V1 fijo no los concede. Ambos quedaron registrados y resueltos para el piloto de `telchi_dev`, con paridad HTTP/SQL acreditada en [el cierre de activación DEV](../../../../../data/reports/telchi/sales_rbac_business_runtime_v1/GATES.md). El grant original permanece independiente.

La métrica documental de V1 y sus limitaciones se muestran al usuario; no se etiqueta como venta neta o importe.

`sales.source_top_items` admite exclusivamente 2026-01-01 a 2026-09-16 exclusivo, sin sucursal/canal/comparación. Devuelve top 10 cantidades documentales por producto. No descuenta créditos o cancelaciones, no certifica UoM comparables ni completitud histórica y no expone `line_total` como facturación.

`sales.net_amount` reutiliza `sales.period_billed_amount.v1`: facturación de cabeceras activas BS, notas de crédito y neto documental separados, por período explícito. No acredita cobros, saldo pendiente ni importe neto por producto o sucursal. Saavedra y canal horizontal quedan bloqueados sólo para consultas que necesiten esas dimensiones; quitarlos permite la lectura fija.

La fuente es `query_fixed_sales` o `query_sales → FoundationReader → CURRENT coherente/pinned`, nunca SAP, HANA, latest implícito o SQL del LLM. Resultado estructurado con publicación, snapshot, actualización, período, unidades y limitaciones; redacción simple determinística.

## Ranking monetario de productos

El [contrato Product Monetary Ranking V1](PRODUCT_MONETARY_RANKING_V1.md) distingue el ranking por importe comercial acumulado del total de categoría, cantidades, búsqueda textual y precio unitario.

`sales.product_line_amount_ranking.v1` exige categoría acreditada, período semiabierto BS, límite 1–50 y su permiso comercial propio. Concilia el desglose completo antes de Top N y reutiliza referencias ordinales a resultados autorizados. El registro DEV idempotente se realiza con `modules.telchi.provisioning.ranking_cli --apply`; no crea grants individuales ni cambia FULL_ACCESS. La aceptación WhatsApp permanece manual.

## Alcance comercial conversacional V1

El [informe de evidencia BIZ01](../../../../../data/reports/telchi/biz01-conversation-v1/report.md) acredita una conversación completa de Presidencia sobre el pipeline autenticado y persistido.

El estado conversacional dejó de ser una plantilla de consulta y pasó a tener un **alcance empresarial explícito**. Los slots son aditivos: un estado persistido que no los usa conserva su forma y sigue siendo válido.

- `/business_category`: la categoría acreditada, con su propio slot. `entity_mention` queda para una entidad comercial todavía no resuelta y nunca admite un código de producto: una operación de producto o categoría rechaza una mención que no sea código de categoría, de modo que el producto ya no puede sobrescribir la categoría.
- `/product_target`: el código SAP del producto en foco, transferible entre métricas y dimensiones. El ranking histórico lo publica en `/focus.product`.
- `/customer_target`: el código SAP (CardCode) del cliente facturado en foco.
- `/group_by`: la dimensión de agrupación, `sap_product` o `card_code`.
- `/periods` y `/period_mode`: el conjunto de períodos y cómo se leen. `union` es una unión contigua y la ventana la calcula el motor; `compare` sigue siendo un período contra su base. Una unión nunca se colapsa en un mes ni un mes en una unión.
- `/focus`: la proyección de servicio (producto y cliente en foco con sus nombres publicados). Lo escribe el servicio después de cada ejecución, nunca el modelo, y es lo que permite que «ese producto», «ese cliente» o «nos compró» se resuelvan sin que el usuario repita nada.

El [plan de negocio](business_plan.py) es el único contrato que Team360 compila: `dataset + filters + period + group_by + measure + ordering + limit`, con vocabulario cerrado y validación en backend. El modelo nunca nombra tabla, columna, dataset ni expresión SQL. La primera familia acreditada es `sales.commercial_line_amount_by.v1`: importe de líneas comerciales en BS agrupado por producto o por cliente facturado, con filtros cerrados de categoría, producto y cliente, desglose por mes opcional y reconciliación de tolerancia cero contra el total del alcance.

El permiso `telchi.sales.commercial_line_amount_by.read.v1` se registró en DEV con el mecanismo local idempotente (`modules.telchi.provisioning.commercial_by_cli --apply`): capability y permiso nuevos en el catálogo, **sin** asignaciones, roles, perfiles ni cambio de FULL_ACCESS; el piloto conserva su scope y suma el permiso nuevo.

«Cliente» significa la cuenta facturada en SAP (CardCode) que recibe las líneas. No es el comprador final ni un cliente comercial validado: la taxonomía `customer_business_type` no está acreditada (0 clientes clasificados como comerciales) y la respuesta lo advierte, sin bloquear el resultado ya acreditado. Las cuentas de control tributario de SAP se muestran y se cuantifican; no se depuran, porque no hay una taxonomía acreditada que las distinga.

El contrato **BUSINESS ANSWER FIRST** es transversal: la respuesta entrega primero el resultado empresarial verificable, luego la excepción, el riesgo concreto, su efecto sobre la conclusión y el próximo paso útil. Ninguna indisponibilidad desnuda oculta un importe acreditado, y ninguna respuesta pierde un período del texto.

## Aprovisionamiento comercial DEV

El procedimiento existente añade sólo dos grants documentales. Reutiliza Console RBAC, roles exclusivos del workspace y `core_events` como ledger administrativo; no instala otro sistema de entitlements.

`provisioning.live_cli --sales-activation` extiende el bootstrap explícito de propietario local DEV: verifica las tres identidades persistidas, actor global, organización/admin delegado, destino local, backup privado recuperable y hashes de fuentes revisadas. No emite tokens ni representa un login Console.

Team360 registra catálogo/roles y aprueba límites para el administrador Telchi en `telchi.admin.sales-authorize`. Telchi asigna mediante `telchi.admin.sales-grant`; una segunda ejecución es no-op sin eventos extra. El comando autenticado `admin_cli manage-client` admite `grant-sales` con los dos permisos exactos y `modules=['telchi']`, pero exige la aprobación global persistida.

La reversión `live_cli --sales-activation --rollback-sales-run <run_id>` con manifest privado, `--apply --local-owner-bootstrap`, elimina únicamente las relaciones `core_user_roles` creadas por esa ejecución y sin cambios. Conserva catálogo, usuarios, grants preexistentes y auditoría. El [reporte](../../../../../data/reports/telchi/sales_rbac_business_runtime_v1/RBAC_CHANGES.md) acredita rehearsal transaccional.

## Ventas por estado físico

La dimensión física integra el maestro acreditado con las líneas comerciales publicadas mediante la capability existente, sin otro motor ni cambios de permisos.

- `sales.commercial_line_amount_by.v1`, `group_by=physical_state`, mismo permiso `telchi.sales.commercial_line_amount_by.read.v1`. Identidad de producto resuelta por crosswalk canónico, sin inferencias por nombre o unidad.
- `physical_focus` es foco de presentación cerrado, no filtro monetario. `breakdown_by=products|day` expone ranking o serie diaria del mismo universo; las listas resumidas declaran lo omitido y conservan el detalle completo auditado.
- `/period` y `/comparison` permiten ventanas exactas para comparar hasta el mismo día; no se suma el hueco entre ellas. La fecha de captura física no se presenta como vigencia histórica de cada factura.
- Respuesta: importes BS de líquidos/sólidos/semisólidos, no clasificados y códigos 4/5 separados; porcentajes del total y del importe explícito, cobertura por líneas/productos/importes, corte, observación, métrica, hashes y publicación/snapshot.
- No se prorratean cabeceras. Descuentos de línea ya reflejados, sin IVA de línea y antes de NC/ajustes globales; cabeceras, NC documentales y residuo no asignable se muestran aparte. Los importes desconocidos no desaparecen.
- Presupuesto de lectura por defecto: 60 s, calibrado con el reader canónico real en HDD (aproximadamente 33–41 s). Un límite explícito del caller se respeta; no cambia el presupuesto de persistencia, reintentos ni la admisión del canal.
- [Contrato de clasificación](../datalake/PHYSICAL_PRODUCT_CLASSIFICATION_V1.md), [estado local](../status_actual.md) y [evidencia real](../../../../../data/reports/telchi/physical-sales-reference-integration-v1/report.json). La sonda autenticada/persistida no equivale a entrega WhatsApp ni reactiva automáticamente sus gates de arranque.

## Gates permanentes de activación

IMPLEMENTED significa código disponible; ACTIVATED exige los cuatro gates siguientes para una identidad, workspace y runtime explícitos. Ningún PASS aislado sustituye los demás ni implica promoción PROD.

- `DATA_PASS`: lectura Foundation real ejecutable y lineage acreditado.
- `SEMANTIC_PASS`: métrica, universo documental y límites definidos.
- `AUTH_PASS`: permiso registrado, asignado y efectivo mediante Console para la identidad autorizada.
- `BUSINESS_RUNTIME_PASS`: pregunta natural por el pipeline real, respuesta empresarial y paridad SQL independiente.

El handler audita la propuesta raw y, cuando corresponde, el contrato documental corregido: una pregunta acotada por última fecha utiliza cobertura, nunca lista/venta neta. Las propuestas de consulta pasan por el mismo State Engine y permiso específico; las selecciones de resultados usan el resolvedor independiente sin alterar la consulta. «¿Y las anteriores?» tras últimas facturas conserva el contexto y explica que no hay paginación, sin otra consulta. Auditoría cuenta invocaciones de capability y permiso requerido; no cuenta statements internos de conexión.

## Referencias a resultados V1

Las selecciones operan sobre filas auditadas en su orden presentado, sin convertir ordinales en límites ni filtros comerciales. No constituyen memoria documental general.

Luna recibe `result_context`: ID de lista, cantidad, campos referenciables y ordinal previamente seleccionado, sin valores de filas. Propone `intent=RESULT_REFERENCE`, `action=SELECT_RESULT`, `result_reference={result_id,ordinal,field}` y `clarification=null`; no envía `state_delta`. Ordinal empieza en 1; null reutiliza la selección previa. Campo null solicita los datos disponibles de esa fila. La ambigüedad usa `action=ASK`, referencia null y aclaración breve.

`result_references.py` valida ese contrato fuera del motor de consultas. El handler revalida el permiso comercial actual antes de suministrar descriptores y antes de responder. No invoca capabilities ni Foundation para una selección. La consulta activa queda intacta; el puntero de lista y selección se persiste aparte. La auditoría conserva fuente, documento seleccionado y campo solicitado.

El repositorio recupera un solo evento acotado a conversación, canal, workspace, entorno y owner completo. Para auditorías anteriores sin puntero utiliza los IDs ordenados de las últimas 20 solicitudes retenidas. Máximo 64 KiB por auditoría recuperada y 50 filas; no añade vencimientos. Sólo acepta ejecuciones exitosas con RBAC acreditado, estado válido y procedencia conservada. Los adaptadores admiten listas de facturas, catálogo de productos y ranking documental; no amplían capabilities ni permisos. Los reportes con varias listas, como productos más resumen más líneas, quedan fuera de V1 para no confundir sus ordinales.

La respuesta advierte que reutiliza la publicación anterior y su fecha, sin afirmar actualidad. Una factura seleccionada muestra sólo los datos de cabecera disponibles. La respuesta preparada prueba el orden del contenido, no su recepción por WhatsApp: la entrega continúa bajo Messaging y no queda certificada por estos tests.

Pruebas: `test_result_references.py` cubre continuidad 5 → 3 → segunda → número, negativos y cero invocaciones nuevas. `test_result_references_postgres.py` usa PostgreSQL real con tablas temporales de sesión, sin modificar filas operacionales; requiere `TEAM360_RESULT_REFERENCE_POSTGRES_TEST=1`. `tests.live_result_reference --output <path-nuevo>` prueba Luna Medium real con descriptores y datos sintéticos, sin Foundation ni WhatsApp. La [evidencia focalizada](../../../../../data/reports/telchi/conversational-result-reference-v1/luna-medium.json) no acredita activación del canal ni RBAC de una identidad real.

## Continuidad documental y productos de factura V1

La selección documental y la selección de producto son punteros distintos vinculados a auditorías autorizadas. [Evidencia focalizada y límites](../../../../../data/reports/telchi/document-continuity-invoice-lines-v1/report.md) no certifica el runtime WhatsApp activo.

`document_context` contiene sólo descriptores de la lista de facturas y su ordinal seleccionado. El contrato independiente `DOCUMENT_REFERENCE` usa `result_reference={result_id,ordinal,field}` y `clarification=null`, sin `state_delta`. `READ_LINES` exige `field=null`; `SELECT_DOCUMENT` permite null, doc_num, doc_date, client o amount. El cliente explica el campo ausente; amount ejecuta la lectura monetaria individual descrita abajo, con permiso independiente. Los IDs documentales provienen de una fila autorizada, nunca de Luna. La lista de facturas y las selecciones genéricas muestran número y fecha, no DocEntry ni tablas; el ID interno retenido sólo se devuelve cuando se pide explícitamente ese campo.

El repositorio conserva `document_reference` junto al `result_reference` existente y `reference_focus`; no instala otra memoria ni cambia el State Engine. Seleccionar una factura fija su foco; leer líneas activa el foco de productos; volver a la factura no destruye la selección de línea. `NEW_QUERY` o una nueva ejecución independiente abandona el documento anterior. Un singleton permite una referencia inequívoca sin inventar un ordinal. Los campos documentales no se convierten en filtros comerciales.

`sales.invoice_lines.v1` exige dinámicamente `telchi.sales.invoice_lines.read.v1`, además del acceso base y el permiso del resultado documental original. No reutiliza permisos de búsqueda o ventas por producto. El worker valida publicación/snapshot originales, fuente SAP_B1_HANA, tipo OINV, DocEntry, número y fecha. Sólo admite cabecera activa N única y líneas INV1 con la misma extracción y fecha fuente; excluye colisiones de otros tipos/fuentes, duplicados y linaje incompatible. El orden es LineNum ascendente, sin agrupar cantidades ni truncar la factura.

La descripción procede del catálogo SAP_HANA de la misma publicación, no del texto histórico de INV1. Foundation no publica UoM nativa de línea: `unit=null` se explica, sin deducir litros/kg desde nombres o UoM de catálogo. No devuelve importes ni hace conversiones. Una factura sin líneas se informa como tal. Un fallo de lectura conserva la identificación y no repite últimas facturas. Las líneas se presentan al contrato ordinal V1 existente con sus límites originales de tamaño/filas; no se agregan vencimientos.

`provisioning.live_cli --invoice-activation` extiende el procedimiento local-owner DEV existente con backup privado, manifest y hashes revisados; registra un permiso, un rol exclusivo del workspace y una asignación al piloto, auditados por `invoice-authorize`/`invoice-grant`. No altera permisos por operación en la habilitación WhatsApp, identidades ni grants anteriores. Código disponible y permiso efectivo no significan proceso activo actualizado: los seis gates previos quedan STALE hasta reacreditación focalizada y carga controlada, sin reinicio automático.

Pruebas específicas: `test_invoice_continuity.py`, `test_invoice_continuity_postgres.py`, `datalake/tests/test_invoice_lines_query.py` y `provisioning/tests/test_invoice_admin.py`. La sonda `tests.live_invoice_continuity --output <path-nuevo>` usa Luna Medium y Foundation reales, con identidad y puerto de persistencia fixture declarados; `--full-conversation` recorre 5 → 3 → segunda → primera → productos y sus seguimientos. No envía WhatsApp. PostgreSQL temporal se valida por separado con `TEAM360_RESULT_REFERENCE_POSTGRES_TEST=1`.

## Cierre comercial DEV y FULL_ACCESS acotado

El [cierre verificable](../../../../../data/reports/telchi/business-assistant-close-v1/report.md) prioriza cifras reales y continuidad; no certifica WhatsApp E2E ni modifica Foundation.

El resolver compartido Console expande sólo registros habilitados de `core_workspace_capabilities` para una asignación activa en `core_module_full_access_grants`. Requiere usuario/workspace/organización vigentes, tenant de la asignación igual al del workspace y namespace de permiso igual al módulo. No interpreta `*`, roles globales ni el texto FULL_ACCESS como autorización. Conserva grants normales, autenticación y límites de cada operación. Requiere migración `031_team360_scoped_full_access.sql` antes de cargar el resolver actualizado.

Sólo el piloto existente de `telchi_dev` recibe esta asignación; su relación de roles individuales no cambia. Una capability futura necesita registrarse y habilitarse en el ámbito, pero no otro grant al piloto. Deshabilitar un registro o revocar la asignación elimina esa expansión en la siguiente resolución. Los permisos ordinarios preexistentes permanecen. `provisioning.business_close_cli --apply --revoke` conserva la fila revocada y registra `telchi.admin.full-access-revoke`; la activación registra el grant y el catálogo en el mismo ledger. Ambos usan el procedimiento local-owner DEV con backup privado, no un login ni emisión de tokens.

`sales.invoice_amount.v1` exige `telchi.sales.invoice_amount.read.v1`, además de acceso base y autorización del resultado documental padre. Usa la referencia documental validada existente y lee exclusivamente el total de cabecera publicado de una factura activa, con su moneda nativa. No suma líneas, infiere impuestos, convierte monedas ni amplía permisos de listados o productos. El rol monetario normal queda registrado sin asignarlo individualmente al piloto FULL_ACCESS.

Las respuestas monetarias muestran primero la cifra, período, moneda y fecha de actualización; distinguen facturado, neto documental, cobrado y saldo pendiente. Un mes que termina después de la actualización se declara parcial. No hay cobertura completa certificada ni conversión implícita de ausencia de filas a ventas cero.

## Calidad conversacional y comparación local

Las comparaciones reutilizan resultados auditados y autorizados; no agregan consultas comerciales ni habilitan comparación en Foundation.

`monetary_comparison.py` acredita facturación documental registrada de períodos explícitos mediante el contrato monetario existente. Recupera hasta 20 eventos de la historia de la misma conversación, canal, workspace, entorno y owner, con máximo 64 KiB por auditoría. Sólo admite ejecuciones exitosas, procedencia verificable y documentos presentes; selecciona la última ejecución por período. No se añaden vencimientos.

Luna recibe `monetary_context` sin importes. Propone el contrato independiente `MONETARY_COMPARISON / CALCULATE`, `comparison={target_id,baseline_id,mode:difference|absolute_difference|percent}`, `clarification=null`, sin delta. El modo se elige por la pregunta: `difference` es resta con signo, `absolute_difference` es la magnitud `abs(target-base)` y `percent` es variación porcentual. Una pregunta por «diferencia absoluta» nunca se responde con un importe negativo. Ante referencia ambigua usa ASK. Con exactamente dos períodos y sin orden explícito, el posterior es objetivo y el anterior base; el orden explícito se conserva. `previous` conserva los IDs de la última comparación para «¿Y en porcentaje?».

Team360 valida IDs, moneda, métrica, definición, publicación, snapshot y cobertura de ambos resultados, períodos distintos no superpuestos y permisos efectivos antes de interpretar y antes de responder, incluido replay cacheado. Calcula con `Decimal`: objetivo menos base, la magnitud absoluta cuando se pide `absolute_difference`, y porcentaje sobre base positiva. Conserva en auditoría la diferencia con signo (`difference`), la magnitud (`absolute_difference`), la `direction` (`target_higher`/`baseline_higher`/`equal`), el modo entregado (`reported`) y el valor presentado (`value`), de modo que magnitud y dirección nunca se confunden. `capability_calls=0`, sin Foundation. Una base cero/no positiva no produce porcentaje; incompatibilidad o ausencia de resultados pide aclaración sin ejecutar sustitutos. Cobertura parcial se identifica por período y nunca se interpreta como caída mensual definitiva. La misma separación aplica a la aritmética de componentes de un resultado (`ratio_percent` participación, `difference` con signo, `absolute_difference` magnitud).

La auditoría WhatsApp del 19/10 mostró que el primer rechazo de septiembre procedía de `/product_context` en `unset`, no de evidencia de una restricción por puntuación. Sólo `NEW_QUERY` acepta ese descarte explícito ya realizado por el servicio; escribir contexto/IDs, modificarlo en REFINE o alterar `/pending` continúa prohibido. El rechazo conserva el estado anterior y registra `contract_error`.

Regresión: `tests/test_conversational_quality.py` y fixture anonimizada de los cuatro turnos reales; PostgreSQL temporal opt-in con `TEAM360_RESULT_REFERENCE_POSTGRES_TEST=1`. La sonda `tests.live_conversational_quality --output <path-nuevo>` recorre ambas formulaciones, agosto, diferencia, porcentaje y continuidad documental con Luna Medium/Console/PostgreSQL/Foundation reales, sin listener ni envío WhatsApp. [Evidencia focalizada](../../../../../data/reports/telchi/conversational-quality-v1/live-r1.json). Implementación validada no equivale a admisión del runtime: el fingerprint cambió y el manifest DEV previo requiere reconciliación change-based antes de otra sesión manual.

## Categorías empresariales y ventas V1

La [implementación monetaria DEV](../../../../../data/reports/telchi/category-sales-monetary-v1/report.md) materializa el [contrato de líneas](../datalake/CATEGORY_LINE_AMOUNT_V1.md), sin alterar clasificación, Foundation ni permisos persistidos. Registro scoped pendiente: IMPLEMENTED, no ACTIVATED.

Luna recibe el vocabulario acreditado de `product_business_type`. El slot V2 `entity_mention={text:código_canónico,type:null}` distingue categoría de búsqueda textual. `sales.net_amount` con categoría ejecuta exclusivamente `sales.category_line_amount.v1`, no el neto documental global; requiere `telchi.sales.category_line_amount.read.v1` revalidado en cada turno. Se conserva el contrato previo para consultas sin categoría.

La operación devuelve importe registrado en líneas comerciales activas BS, descuentos propios incluidos, sin IVA de línea, notas de crédito ni ajustes globales. Clasificación actual no histórica; SUPPORTED se advierte y PROVISIONAL/UNKNOWN se bloquean. Sin resultados no acredita cero comercial. Monedas incompatibles, claves/linaje inválidos o publicación distinta se rechazan sin sustitución. El importe y límites son calculados desde Foundation, nunca cifras fijas investigativas.

Comparación local entre categorías: resultados anteriores autorizados, mismo período, moneda, cobertura documental, publicación/snapshot, definición y versión de clasificación. No consulta datos adicionales; filas sin ejecución no participan. La búsqueda textual, códigos y consumo productivo conservan sus fronteras. EXPLAIN distingue cabeceras y líneas sin atribuir todo residuo a IVA ni hacer conversiones fiscales.

Luna Medium real y Foundation PASS en alcance focalizado; agosto bloqueado por una moneda no acreditada sin perder intención. FULL_ACCESS existente no incorpora la nueva capability hasta registrarla/habilitarla en el workspace. `SIX_GATES=STALE`, `READY_FOR_MANUAL_WHATSAPP=NO`; sin reinicios, grants, Presidencia, WhatsApp ni promoción.

## Persistencia y recuperación

Se extienden únicamente namespaces JSON de las filas Messaging existentes. No se crean tablas, migraciones ni otro sistema de conversación.

`ConversationRepository` conserva `telchi_assistant_v1` en `message_threads.metadata_jsonb` y `message_events.payload_jsonb`. Owner: entorno, tenant, workspace, canal y usuario; IDs: thread y evento inbound suministrados por Messaging. Cambiar identidad del thread falla cerrado.

La transacción bloquea thread antes de evento, revalida permisos, procesa y guarda estado, auditoría, resultado y respuesta preparada juntos. Mantiene orden explícito de historia para no depender del orden de claves JSONB. Auditoría distingue anterior, propuesta, validado, confirmado, decisión, execution_status, resultado y respuesta.

El commit ocurre antes de devolver `MessageResult`. El intent outbound se persiste después por Messaging: NO es la misma transacción. Si hay crash en esa brecha, el fence inbound horizontal impide volver a ejecutar, pero el duplicado puede quedar `execution_uncertain`; no se añadió recuperación automática de esa brecha.

Evento ya completado leído directamente retorna su respuesta cacheada con acceso revalidado. Duplicados normales y retries de entrega usan el mecanismo horizontal sin reinvocar Telchi. No se garantiza exactly-once universal fuera de Messaging ni ante llamadas directas que ignoren su fence tras rollback.

Límites configurables en constructores: interpretación 45 s, worker Foundation 30 s, turno 80 s; SQL PG local: lock 3 s y statement 5 s. La transacción ocupa una conexión y mantiene el lock durante LLM/lectura: validar presupuesto operacional antes de activar el canal. No se promueve concurrencia ilimitada.

## WhatsApp durable y controles conversacionales

El rollout DEV opt-in reutiliza Messaging y su inbox PostgreSQL. La [evidencia local](../../../../../data/reports/telchi/whatsapp-conversational-e2e-v1/backend-live.json) no acredita WhatsApp externo.

- `TEAM360_TELCHI_DURABLE=1`, desde la composición Telchi existente: Srv05 Evolution ON, handler transaccional replay-safe y configuración explícita; OFF conserva el camino anterior. El flag pertenece al allowlist privado y al fingerprint; no se modificó la configuración privada ni se renovaron gates automáticamente.
- El webhook persiste el inbound con `durable_job=QUEUED` antes del ACK. Duplicados retornan sin ejecutar ni enviar. El ingreso durable no actualiza la conversación bloqueada por Luna; el lock del handler permite insertar nuevos turnos mientras procesa el anterior.
- `modules.messaging.durable.DurableWorker` recupera trabajo de `message_events`, con un supervisor local y polling de dos segundos. Un advisory lock transaccional por conversación serializa workers; PostgreSQL lo libera al caer la conexión. No hay broker, tabla, scheduler general ni cola en memoria nuevos.
- El resultado, contexto y respuesta Telchi siguen confirmándose juntos. Tras un crash en la brecha resultado/intent, el worker reutiliza ese resultado con RBAC actual y completa el único intent outbound. Un cálculo sin commit puede repetirse después de una caída; se garantiza una respuesta lógica persistida, no una única invocación física universal del modelo.
- Los estados y transiciones viven en `durable_job`; un ERROR sin audit confirmado admite hasta tres intentos, separados por 30 s y sin adelantar turnos posteriores. Autorización y resultado acreditado permanecen en el audit Telchi. La aceptación se distingue de los callbacks delivered/read existentes. Una aceptación incierta queda detenida para reconciliación, sin reenvío automático. `recover_delivery(..., retry=True)` permite revisar un fallo confirmado mediante el worker y revalida permisos; no convierte incertidumbre en permiso de reenvío.
- El worker aplica el presupuesto explícito DEV de turno 300 s / lectura 180 s, separado del transporte Evolution y del webhook; no cambia los timeouts del camino legacy ni exige Luna en menos de 60 s. El shutdown cierra solamente su supervisor, conservando trabajo y locks recuperables en PostgreSQL.
- Las respuestas empresariales completas ofrecen texto `Continuar — Nueva consulta`, sin asumir soporte de botones. `Continuar` conserva el contexto sin llamar al modelo. `Nueva consulta` crea otro `analysis_context_id`, limpia estado, punteros e historia activa, y conserva eventos auditables. Cada turno registra conversación, turno, contexto y padre; las preguntas libres siguen usando Luna/State Engine existentes.
- El catálogo actual no ofrece ranking de proveedores. La [regresión real corregida](../../../../../data/reports/telchi/whatsapp-conversational-e2e-v1/supplier-fix-live.json) conserva compras/octubre y explica esa limitación sin recalcular el total como sustituto ni inventar proveedores. No se añadió una operación empresarial.

La [sonda reanudable](tests/live_durable_conversation.py) usa identidad, RBAC, Luna, Foundation y PostgreSQL reales, receiver sintético aislado y outbound simulado. Los tests `test_messaging_durable_inbox_postgres.py` usan un schema desechable para duplicados concurrentes, ingreso no bloqueante, recuperación resultado/intent, retry confirmado y revocación previa al envío. Ninguno certifica entrega externa.

Límite externo observado: contenedor Evolution detenido, admisión V1 cerrada y candidato marcado `deployment-authorized=false`; su ID no coincide con el registro privado de runtime poseído. La instancia DB coincide con binding/receiver, pero `ownerJid` está vacío y no acredita ownership. No se tomó control ni se activó el candidato. El registro firmado existente identifica al owner administrativo `mario`; la activación externa necesita reconciliar ese runtime concreto y reacreditar los gates afectados con el owner, sin alterar instancias ajenas.

## Fiabilidad de entrega WhatsApp V1

Corrección del 21/10/2026 sobre la sesión `c716012d8a10876a1cd8e617b5076bd4`: la respuesta empresarial era correcta y el usuario nunca la recibió. Las causas están demostradas y las correcciones son deterministas; la evidencia vive en [delivery-reliability-v1](../../../../../data/reports/telchi/delivery-reliability-v1/report.md).

- **Límite del canal**: Meta acepta como máximo 4.096 caracteres en `text.body`. `modules/messaging/delivery_guard.py` aplica una guarda determinística antes del proveedor: nunca corta una línea, nunca altera una cifra, un nombre o una advertencia y declara en el mensaje y en la auditoría lo que omite. El texto acreditado completo queda en `audit.accredited_response_text`; el entregado es `audit.response_prepared.text`.
- **Fallo explícito del proveedor**: un rechazo explícito (por ejemplo, texto demasiado largo) es un **fallo confirmado** aunque Evolution responda 2xx. `uncertain` queda reservado para resultados realmente inciertos (timeout, respuesta inválida). Un rechazo nunca se reenvía solo.
- **Fallo técnico del intérprete**: `luna.LunaError` conserva código redactado, tipo, HTTP status, duración y si hubo reintento. El handler responde con una explicación técnica comprensible y **nunca** como «no pude interpretar la consulta». El audit registra `luna_failure` y `decision=LUNA_TECHNICAL_FAILURE`; ninguna capability se ejecuta después de un fallo de interpretación.
- **Reintento acotado**: como máximo un reintento, y sólo ante fallos transitorios claramente seguros (timeout, error de conexión, 429, 5xx, respuesta truncada). Sin fallback, sin proxy, sin cambio de modelo; `gpt-5.6-luna` con esfuerzo `medium` y `store=false` se conservan.
- **Objetivo de longitud**: las respuestas se componen para caber en 1.500 caracteres. La familia comercial presenta el resultado principal, sus períodos, su participación, las advertencias materiales y el paso siguiente; no vuelca listados de 50 elementos.
- **Límite por familia analítica**: un límite de filas pertenece a la operación que lo pidió. Un ranking de 50 no contamina una consulta posterior de productos o clientes; una cantidad pedida explícitamente por el usuario siempre se respeta (`state_engine.scope_limit`).

## Continuidad de sesión DEV

La sesión DEV ya no cierra por una duración fija de 600 s. `whatsapp_dev.session_timing` resuelve `idle_timeout` (por defecto 900 s) y `max_duration` (por defecto 14.400 s); el valor legacy `--duration` se conserva como alias de la duración máxima.

- La actividad real del canal se registra en `activity.json` (marca de tiempo, turnos y turnos en curso), sin mensaje, teléfono, credencial ni valor de negocio.
- Un turno en curso nunca se interrumpe: el cierre por inactividad espera a que termine.
- El motivo del cierre (`idle_timeout_reached`, `max_duration_reached`, `gate_evidence_expired`, `operator_stop`) queda en `closure.json` y en el estado de sesión.
- La sesión activa puede extenderse desde el control privado existente (`idle_timeout` / `max_duration` en `whatsapp-dev-control.json`); el controlador lo relee sin tocar el entorno.
- Identidad, ownership, allowlist, gates, integridad y restauración segura del webhook no cambian. No hay expiraciones nuevas para Presidencia ni cambios de autorización.

## Producto y validación

ACG básico y BMD mínimo son parte de este desarrollo. APD y análisis extensos siguen siendo futuros; no se crean jobs, emails ni tickets ni se prometen entregas.

BMD registra sólo categoría de necesidad en la auditoría existente: capability, métrica, mapping, cobertura o análisis. No guarda texto/identidad adicional innecesarios. Las métricas por etapa cubren el procesamiento interno; no incluyen espera del lock, commit PG ni transporte WhatsApp.

Desde backend, tests focalizados sin servicios reales:

```bash
uv run pytest modules/telchi/assistant/tests tests/test_telchi_assistant_srv05.py -q
```

Sondas reales opt-in, sin activar canal ni escribir datos empresariales; necesitan preflight de host/servicios. Identidad, permisos y PG siguen simulados en estas sondas. El output debe ser un path nuevo:

```bash
uv run python -m modules.telchi.assistant.tests.live_probe --luna --preflight --output /tmp/telchi-luna-preflight-new.json
uv run python -m modules.telchi.assistant.tests.live_probe --luna --foundation --output /tmp/telchi-live-handler-new.json
```

No enviar datos sensibles al modelo. Estas sondas envían sólo preguntas controladas y estados de consulta, nunca filas empresariales. El reporte reduce resultados Foundation a fuente, conteo y hash.

## Validación HTTP runtime (DEV)

`dev_runtime_http.py` monta un endpoint DEV deshabilitado por defecto, loopback y con token (`TEAM360_TELCHI_ASSISTANT_DEV_HTTP=1`) que alimenta el **mismo** `MessageDispatcher` → `TelchiHandler` → State Engine → capabilities usado por WhatsApp, sin transporte de salida. La identidad se resuelve desde el binding telefónico aprobado en PostgreSQL, nunca desde el cuerpo. No crea otro motor ni otro catálogo.

La batería `curl` reutilizable vive en `tests/runtime_http/` (`run_battery.py`, `security_probes.py`, `restart_continuity.py`); su [README](tests/runtime_http/README.md) documenta alcance y límites. Es el gate previo a la validación manual por WhatsApp.

El [runbook WhatsApp DEV](WHATSAPP_DEV.md) documenta el launcher manual Srv05 + TelchiAI + Evolution, preflight read-only, aprobación explícita, backup/restauración y revisión de un intercambio real. No activa el webhook durante la preparación ni declara E2E_PASS con tests HTTP o dobles.
