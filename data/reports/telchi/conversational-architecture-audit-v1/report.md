# Auditoría arquitectónica del asistente conversacional TelchiAI — V1

- Fecha: 2026-10-21
- Rama: `feature/console-backend-core`
- Alcance: auditoría READ ONLY. Sin modificación de código, catálogo, gates, runtime ni datos.
- Modo: `ENTITY=TELCHI`, `DOMAIN=VENTAS`, `STAGE=INVESTIGATION`, `SOURCE=DATA_LAKE/FOUNDATION + PostgreSQL (DEV)`.

## 0. Resumen ejecutivo

La conversación no se interrumpe por falta de datos. Se interrumpe porque el **estado conversacional es una plantilla de consulta** (`metric` + `period` + `comparison` + un `entity_mention` genérico), no un **contexto de negocio** con entidades y dimensiones propias.

Consecuencia medida en el incidente real del 21/10/2026:

1. El turno del 20/10 17:33 (misma pregunta, mismo hilo) **sobrescribió el slot de categoría** (`entity_mention`: `LAB_FINISHED_PRODUCT` → `L03281`) para representar el producto, porque la versión V2 del contrato no tiene slot propio para producto dentro de un ranking. El State Engine aceptó y **persistió** ese estado dañado.
2. El turno A del 21/10 12:07 heredó el estado sin categoría y **preguntó de nuevo la categoría** (aclaración innecesaria). La causa no fue Luna ni el prompt (que ya contenía el ejemplo L03281, mtime 20/10 21:34): fue la pérdida de contexto en el turno previo.
3. El turno C del 21/10 12:09 no tiene **slots representables** para «cliente» ni para «unión de dos meses». Luna hizo lo que el contrato le ordenaba (`DIRECT_UNAVAILABLE`), anuló la métrica y conservó sólo agosto; el formatter (`business_categories.unavailable_text`)也只有 conoce categoría + métrica + `period`, por lo que **julio desapareció del texto**.

El dato existe y es verificable: `sales_document.card_code` está publicado, la relación producto→cliente facturado es exacta y la unión julio+agosto reconcilia **exactamente** con el ranking ya acreditado (Bs 586.227,06 = 271.255,49 + 314.971,57).

## 1. Fase A — Auditoría exacta de los turnos reales

### 1.1 Identificación de la evidencia

Hilo: `baea2cb9-a8fa-478d-84e0-808994beac11` (WhatsApp/Evolution, `dev`, `telchi`/`telchi_dev`).
Eventos en `message_events.payload_jsonb->'telchi_assistant_v1'` (turno) y `message_threads.metadata_jsonb->'telchi_assistant_v1'` (estado e historial persistidos).

| # | Hora ART | Evento | Decisión | Exec | Clasificación |
|---|---|---|---|---|---|
| P0 | 20/10 14:32 | `d3c820ef` | EXECUTE | executed | DIRECT_AVAILABLE (ranking LAB_FINISHED_PRODUCT, sept-2026, L03281 #1) |
| P1 | 20/10 14:33 | `6b7b2b39` | DIRECT_UNAVAILABLE | not_executed | `RANKING_UNAVAILABLE` |
| A | 21/10 09:07 | `e2d4061d` | ASK | not_executed | NEEDS_CLARIFICATION |
| B | 21/10 09:08 | `8bc2b3b4` | EXECUTE | executed | DIRECT_AVAILABLE (posición histórica 2 meses) |
| C | 21/10 09:09 | `4e86b77f` | DIRECT_UNAVAILABLE | not_executed | `RANKING_UNAVAILABLE` |

Entregas: `outbound` `message` + `status` (`sent`/`delivered`/`read`) presentes para los tres turnos.

### 1.2 Divergencias

**P1 (precursor, 20/10 14:33) — primera divergencia de toda la cadena.**

- Estado previo: `entity_mention={text:"LAB_FINISHED_PRODUCT"}` (categoría acreditada, de P0).
- Propuesta de Luna: `REFINE / DIRECT_UNAVAILABLE`, `set /entity_mention={text:"L03281"}`, `set /period=agosto-2026`, `set /comparison=julio-2026`, **sin** `/ranking_target_item_code`.
- State Engine: `committed=true`, `contract_error=null`. El estado corrupto quedó **persistido** como `confirmed_state`.
- Catálogo: `availability()` → `category_code(state) is None` → `RANKING_UNAVAILABLE` («El ranking monetario no está disponible para ese universo o esos filtros»).
- **El motor no detectó nada**: `entity_mention` sólo se valida como texto libre de 1..120 caracteres.

**Turno A (21/10 09:07) — aclaración innecesaria.**

- Estado previo (heredado, ya sin categoría): `entity_mention={text:"L03281"}`, sin `ranking_target_item_code`.
- Propuesta: `REFINE / ASK`, `set /ranking_target_item_code="L03281"`, `set /entity_mention={text:"L03281"}` (idéntico al previo), `clarification={slot:"reference", question:"¿A qué categoría acreditada pertenece L03281…"}`.
- El motor la aceptó y creó `pending` con `proposed` (que ya incluía `/ranking_target_item_code:"L03281"`).
- Causa: la categoría **no estaba en el estado** y no era recuperable desde el contexto provisto. `result_references.interpreter_context()` expone `result_id, row_count, fields, selected_ordinal, entity_label, historical` — **no expone el ámbito del resultado** (categoría, período, métrica, medida). Luna no tenía forma de re-derivar `LAB_FINISHED_PRODUCT` ni aunque el ranking previo siguiera visible en `result_context`.
- Nota: el prompt (`luna.py`, mtime 20/10 21:34, posterior a P1) ya contenía el ejemplo L03281. La aclaración no fue un fallo de prompt: fue un fallo de **memoria**.

**Turno B (21/10 09:08) — correcto, y la prueba de que el dato existe.**

- `ANSWER_CLARIFICATION / EXECUTE`; `entity_mention` → `LAB_FINISHED_PRODUCT`; conserva `period`=agosto, `comparison`=julio, `ranking_target_item_code=L03281`.
- Ejecutó `sales.product_line_amount_ranking.v1` vía `historical_ranking.execute` sobre el **ranking completo** (no el Top N).
- Resultado: Agosto puesto 1 entre 289 (Bs 314.971,57); Julio puesto 2 entre 283 (Bs 271.255,49); diferencia Bs 43.716,08. `accreditation=verified`, `exceptions=[]`.
- `entity_mention` volvió a ser el portador de la categoría. **El mismo slot cumple dos papeles** (categoría y entidad), y su valor depende de qué capability esté activa.

**Turno C (21/10 09:09) — fallo principal.**

- Estado previo: categoría, producto (`ranking_target_item_code`), `period`=agosto, `comparison`=julio, `metric=sales.product_line_amount_ranking`.
- Propuesta: `REFINE / DIRECT_UNAVAILABLE`, `set /metric=null`, `set /requested_metrics=[]`, resto intacto.
- `bmd.category = RANKING_UNAVAILABLE` — etiqueta **incorrecta**: la causa real es que no existe dimensión cliente. La causa real se perdió porque `availability()` corta en
  `if state.get('ranking_target_item_code'): return Availability(False, 'El producto objetivo corresponde únicamente al ranking monetario.', 'RANKING_UNAVAILABLE')`,
  es decir: **el alcance de producto no es transferible a ninguna otra operación**.
- Texto al usuario: `business_categories.unavailable_text()` (rama `metric is None`): «Entiendo la consulta sobre producto terminado de laboratorio del 1 de agosto de 2026 al 31 de agosto de 2026. Todavía no tengo disponible esa operación; no la sustituyo por ventas ni por una búsqueda de productos.»
  - `unavailable_text` sólo conoce `category_code`, `metric` y `state['period']` → **julio no aparece**. La comparación no se representa en el texto.
  - No hay cifra parcial, ni explicación del faltante real, ni siguiente paso. **No cumple BUSINESS ANSWER FIRST.**

### 1.3 Respuestas a A–G

| Pregunta | Respuesta |
|---|---|
| A. ¿Por qué se pidió la categoría? | Porque el turno P1 (20/10) sobrescribió `entity_mention` con el código de producto y el motor lo persistió. El turno A no tuvo acceso al ámbito del ranking previo (`result_context` no lo expone). Causalidad: **memoria**, no Luna. |
| B. ¿Cómo se representaron julio y agosto? | `period = [2026-08-01, 2026-09-01)` y `comparison = [2026-07-01, 2026-08-01)`. Semántica de **comparación**, no de **unión**. No existe slot para conjunto de períodos. |
| C. ¿Por qué la siguiente consulta conservó sólo agosto? | `unavailable_text()`/`unavailable_response()` sólo renderizan `state['period']`. `comparison` no se renderiza nunca en la ruta de indisponibilidad. Además el modelo eligió `period`=agosto. |
| D. ¿Se perdió L03281? | **No se perdió el producto** (quedó en `ranking_target_item_code`), pero quedó **mal representado**: es un slot atado exclusivamente al ranking, y el mismo estado ya no puede sostener otra operación. |
| E. ¿Luna interpretó la dimensión cliente? | **Sí** (no la mapeó a ventas ni a búsqueda de productos; `DIRECT_UNAVAILABLE` conservando la entidad, tal como ordena el prompt). Pero la intención **no quedó representable**: no hay slot de cliente ni de dimensión, y el prompt afirma explícitamente «No hay capability de ventas por empresa/cliente». |
| F. ¿Existe parcialmente la operación en el catálogo? | **No en el catálogo del asistente**; **sí en Foundation** (verificado, §3.2). |
| G. ¿Por qué indisponibilidad genérica? | Porque la única ruta de "no disponible" (`unavailable_response` / `unavailable_text`) no tiene forma de expresar *qué falta*, y el catálogo no tiene una categoría de error para «dimensión no acreditada». |

## 2. Fase B — Inventario de la arquitectura conversacional

### 2.1 Capas reales

| Capa | Archivo | Rol |
|---|---|---|
| Intérprete | `assistant/luna.py` (SYSTEM ≈ 200 líneas, 28 KB) | `gpt-5.6-luna`, medium, OpenAI directo. Emite `{intent, action, state_delta, clarification}`. El prompt **es** el catálogo de reglas por capability. |
| Motor de estado | `assistant/state_engine.py` | Valida forma (`patch`/`validate`/`process`), atómica, fail-closed. No valida significado. |
| Estado persistido | `assistant/repository.py` → `message_threads.metadata_jsonb['telchi_assistant_v1']` | `state`, `history` (20 turnos), punteros de referencia, `monetary_comparison`. |
| Catálogo | `assistant/capabilities.py` | `SalesCapabilities.availability()` + `execute()` + `format_result()`. 5 métricas. |
| Despachador | `assistant/handler.py` | Autorización → interpretación → motor → catálogo → formato → auditoría. |
| Composición | `assistant/composition.py` | Sólo DI (Srv05). No hay compositor analítico. |
| Lectores | `datalake/{sales_query, product_sales_query, category_line_amount_query, product_line_amount_ranking_query, invoice_lines_query, invoice_amount_query, messaging_sales_query}.py` | Foundation DuckLake read-only, snapshot pineado 1408. |
| Formato | `capabilities.format_result` + `business_categories.unavailable_text` | Determinista, sin LLM. |
| Errores | `availability().category` ∈ {CAPABILITY_MISSING, METRIC_MISSING, MAPPING_MISSING, TEMPORAL_METADATA_MISSING, PERIOD_PARAMETER_UNSUPPORTED, COVERAGE_GAP, PERIOD_UNRESOLVED, RANKING_UNAVAILABLE, CATEGORY_CAPABILITY_UNAVAILABLE, COMPARISON_UNSUPPORTED} | No hay categoría para «dimensión no acreditada». |
| Autorización | `handler.BusinessAuthorization` + `modules/console/repositories.py` (FULL_ACCESS scoped, migración 031) | Re-validación por capability antes y después de ejecutar. |

### 2.2 B1 — Memoria empresarial: qué se conserva y qué no

Slots del estado (`state_engine.py`): `metric`, `period`, `branches`, `sales_channel`, `comparison`, `reference`, `pending`, `limit`, `ranking_target_item_code`, `ranking_detail`, `schema_version`, `requested_metrics`, `entity_mention`, `temporal_reference`, `product_search_text`, `selected_item_codes`, `product_context`, `semantic_references`.

| Information | ¿Se conserva? | Observación |
|---|---|---|
| Producto principal | **Sí, pero con slot condicional** | `ranking_target_item_code` sólo es válido con la métrica de ranking (`availability()` lo rechaza en cualquier otro caso). `product_search_text`/`selected_item_codes` cubren el otro camino (búsqueda textual). |
| Categoría | **Sí, sobre un slot compartido** | Vive en `entity_mention.text`. Colisiona con cualquier otra entidad comercial. |
| Cliente | **No** | No existe slot. `entity_mention` está ocupado por la categoría; y ninguna capability acepta filtro de entidad. |
| Métrica | **Sí** | Enumeración cerrada de 7 valores. |
| Período individual | **Sí** | `period`, intervalo semiabierto. |
| Conjunto / unión de períodos | **No** | Sólo `period` + `comparison`, y `comparison` significa comparación. El prompt prohíbe explícitamente «fusionar meses». |
| Intervalo acumulado | **Sí** (como período) | `[2026-07-01, 2026-09-01)` es un `period` válido — la unión **es** representable, pero el prompt no la contempla. |
| Ranking / posición | **Parcial** | `ranking_target_item_code` + `ranking_detail`; la posición se calcula re-ejecutando el ranking completo. |
| Resultados anteriores | **Sí, y con precedente de composición** | `RESULT_REFERENCE` (selección por ordinal) y `MONETARY_COMPARISON` (aritmética local entre dos resultados acreditados). `monetary_comparison.py` es el **único precedent de composición** del sistema. |
| Referencias ordinales | **Sí** | `result_context` + contrato `RESULT_REFERENCE`. |
| Relaciones entre entidades | **No** | No hay modelo de relations en el estado. |
| Excepciones relevantes | **Sí, en el resultado** | `exceptions` / `external_currency_anomalies`; `answer_policy=ANSWER_FIRST_WITH_EXCEPTIONS`. |

**Distinción crítica (estado almacenado ≠ contexto correctamente interpretado):** en el turno C el estado contenía producto, categoría, dos períodos y métrica. Lo que faltaba no era información: era **una forma de decir «agrupar por cliente» y «unir los dos meses»**. El sistema conservó el contexto y aun así no pudo responder.

### 2.3 B2 — Limitaciones del esquema (concretas, con archivo y línea)

| # | Limitación | Ubicación | Efecto observado |
|---|---|---|---|
| L1 | Categoría y entidad comercial comparten `entity_mention` | `state_engine.SalesState`, `business_categories.category_code()` | Turno P1: la categoría se perdió al representar el producto. |
| L2 | `entity_mention` se valida como texto libre, no como código de categoría | `state_engine.validate()` (`unresolved_entity_required`) | El motor aceptó `entity_mention="L03281"` sin observación. |
| L3 | Dos períodos ⇒ `period` + `comparison` (comparación), nunca unión | `luna.py` («comparison aquí es un SEGUNDO período independiente: no fusionar meses») | «de estos dos meses» no es expresable. |
| L4 | El alcance de producto está atado a la métrica de ranking | `capabilities.availability()` (`if state.get('ranking_target_item_code')`) | Ninguna otra operación puede conservar el producto en foco. |
| L5 | No hay dimensión (`group_by`) ni slot de cliente | `state_engine` (slots) | No se puede cambiar de dimensión comercial. |
| L6 | El contexto de resultado no expone el ámbito del resultado | `result_references.interpreter_context()` | Luna no puede re-derivar categoría/período desde un ranking previo. |
| L7 | La ruta de indisponibilidad sólo conoce `category_code` + `metric` + `period` | `business_categories.unavailable_text()`, `handler.unavailable_response()` | Julio desaparece; no hay diagnóstico del faltante. |
| L8 | El ranking se representa indirectamente por `limit` (+ `ranking_target_item_code`) | `capabilities.execute()` | `limit` significa dos cosas según la métrica. |
| L9 | Sin vocabulario de error para dimensión/período-no-acreditado | `availability().category` | `RANKING_UNAVAILABLE` usado para un caso de cliente; auditoría engañosa. |
| L10 | Resultado previo disponible pero no reutilizable como insumo de agregación | `monetary_comparison` sólo cubre dos importes escalares | No hay `BREAKDOWN`/`PERCENT_OF` sobre resultados previos. |

## 3. Fase C — Inventario de capacidades analíticas

### 3.1 Catálogo registrado (capa 3)

| Métrica | Capability | Permiso | Grano | Dimensiones | Filtros | Agrupación | Orden | Período | Moneda | Composición posible |
|---|---|---|---|---|---|---|---|---|---|---|
| `sales.net_amount` | `sales.period_billed_amount.v1` | `telchi.sales.period_billed_amount.read.v1` | Cabecera OINV/NC | ninguna | sólo período | total | — | 1 intervalo | BS | con `MONETARY_COMPARISON` (2 resultados) |
| `sales.source_top_items` | `telchi.sales_top_items.source_quantity.20260101_20260915.v1` | `telchi.sales.source_quantity.read.v1` | Línea | producto (top 10) | ventana fija | producto | cantidad | fijo 01/01–15/09/2026 | — | ninguna |
| `sales.latest_documents` | `sales.latest_documents.v1` | `telchi.sales.latest_documents.read.v1` | Cabecera | — | límite | — | DocDate desc | no | — | `RESULT_REFERENCE` |
| `sales.coverage` | `sales.coverage.v1` | `telchi.sales.coverage.read.v1` | Cabecera | — | — | — | — | no | — | ninguna |
| `sales.by_products` | `sales.by_products.v1` | `telchi.sales.by_products.read.v1` | Línea | producto (selección) | `selected_item_codes` | producto | fecha, DocEntry, línea | opcional | — | `RESULT_REFERENCE` |
| `products.search` | `products.search.v1` | `telchi.sales.products_search.read.v1` | Catálogo | producto | texto | — | match_rank | no | — | ninguna |
| `sales.product_line_amount_ranking` | `sales.product_line_amount_ranking.v1` | `telchi.sales.product_line_amount_ranking.read.v1` | Línea | **producto** (obligatoria: categoría) | categoría, período | `sap_product` | `amount desc, item_code asc` | 1 intervalo + `comparison` | BS (línea y cabecera) | histórico por `ranking_target_item_code` |
| `sales.category_line_amount` (implícita) | `sales.category_line_amount.v1` | `telchi.sales.category_line_amount.read.v1` | Línea | **categoría** | categoría, período | categoría | — | 1 intervalo | BS | `MONETARY_COMPARISON` (categorías) |
| `sales.invoice_lines` / `sales.invoice_amount` | V1 | propios | Línea / cabecera | factura | doc | — | — | — | BS | `DOCUMENT_REFERENCE` |

Las cinco capas del enunciado **no** coinciden:

1. **Datos en Foundation**: incluyen `card_code` (cliente facturado), `slp_code`, `sales_channel_code`, `whs_code`, `party` (nombre del cliente), `customer_business_type`.
2. **Lectores existentes**: ninguno publica `card_code` (`sales.latest_documents` selecciona `source_system, doc_entry, doc_num, doc_date, canceled`).
3. **Capabilities registradas**: ninguna agrupa por cliente.
4. **Operaciones expresables por Luna**: no hay dimensión; `entity_mention` no es filtro.
5. **Operaciones que llegan al usuario**: 7 métricas, ninguna de cliente.

### 3.2 C1 — Caso producto → cliente: verificación READ ONLY

Ejecutado sobre `CURRENT 1408` / `foundation_afd08d9eca6a725be53cdc3f9d5709c9` / reference `v2_reference_closure_2088d5885204313a`, DuckLake `READ_ONLY`, sin SAP.

Relación: `atomic.sales_document.card_code` (CardCode SAP B1) ⋈ `atomic.sales_line.doc_entry`. Medida idéntica a la acreditada: `line_total` de líneas INV1, cabecera y línea en BS, `canceled='N'`, `source_system='SAP_B1_HANA'`, `source_table='OINV'/'INV1'`.

L03281, `[2026-07-01, 2026-09-01)` (unión julio+agosto):

| CardCode | Nombre (party) | Importe línea BS | Líneas | Docs | Jul | Ago |
|---|---|---|---|---|---|---|
| C000061 | FARMACORP S.A. | **115.044,44** | 4 | 4 | 72.383,99 | 42.660,45 |
| CG2A | CONTROL TRIBUTARIO | 70.430,77 | 448 | 447 | — | — |
| CGCM | CONTROL TRIBUTARIO | 67.772,87 | 472 | 471 | — | — |
| CGRC | CONTROL TRIBUTARIO | 34.488,69 | 246 | 246 | — | — |
| C010264 | L&S S.R.L. | 26.825,57 | 3 | 3 | — | — |
| C007066 | SUPER FARMACIA VIRGEN DE COPACABANA | 26.816,86 | 29 | 29 | — | — |
| CGV1 | CONTROL TRIBUTARIO | 19.885,63 | 150 | 150 | — | — |

Total del item en la ventana: **Bs 586.227,06**, 2.014 líneas, 2.012 documentos, 468 clientes distintos, 0 líneas no-BS.

**Reconciliación cruzada con el ranking ya acreditado** (misma medida, mismo snapshot):

```
Bs 271.255,49 (julio, ranking turno B) + Bs 314.971,57 (agosto, ranking turno B) = Bs 586.227,06 = total por cliente del intervalo [07-01, 09-01)
```

La unión de los dos meses es **exactamente** un `period` del contrato vigente. La operación «cliente que más compró en julio y agosto, con desglose mensual» es aritméticamente verificable con los lectores actuales, cambiando sólo el `group_by` de `sap_product` a `card_code`.

**Salvedad de semántica comercial (obligatoria, y es el gap real de dato):**

- `crosswalk/_versions/v2_reference_closure_2088d5885204313a/customer_business_type` existe (sha256 `88fa1fa8…`) con taxonomía `COMMERCIAL_CUSTOMER | GENERIC_CUSTOMER | INTERNAL_ACCOUNT | FISCAL_TECHNICAL_ACCOUNT | OTHER_NON_COMMERCIAL | UNKNOWN`, pero su distribución es **UNKNOWN 12.977 / GENERIC_CUSTOMER 1 / INTERNAL_ACCOUNT 1 / COMMERCIAL_CUSTOMER 0**.
- `customer_business_identity.py` es explícito: *«Unknown CardCodes therefore stay out of commercial-customer rankings»*.
- Consecuencia: un ranking de **cliente facturado en SAP** es acreditable hoy (y el líder, FARMACORP S.A., no es una cuenta fiscal). Un ranking de **cliente comercial** (excluyendo `CONTROL TRIBUTARIO`, cuentas internas y genéricas) **no** es acreditable hasta acreditar la taxonomía.
- Esto coincide con la advertencia del owner: no confundir cliente facturado en SAP con comprador final de DMS. `party` no trae identidad DMS; sólo `CardCode` + nombre maestro SAP.

### 3.3 Gap ya visible en otro turno del mismo hilo

- 19/10 17:06, «me das el monto de la factura» → `READ_AMOUNT` OK.
- 18/10 13:20, «quién es el cliente» sobre la factura seleccionada → el handler responde «El cliente no está disponible en la cabecera conservada; no hay una operación habilitada para recuperarlo». **El `card_code` sí está publicado**; el lector `sales.latest_documents` simplemente no lo proyecta. Es `NEW_CAPABILITY` (proyección), no `NEW_DATA_CONTRACT`.

## 4. Fase D — Evaluación de composición analítica

### 4.1 Qué es componible hoy

| Primitiva | Estado | Nota |
|---|---|---|
| SELECT de universo acreditado | **Sí** | `access.sales('sales_document'/'sales_line')` + crosswalk de clasificación, todo pineado a snapshot. |
| FILTER por período | **Sí** | `date_from`/`date_to_exclusive`. |
| FILTER por categoría | **Sí** | Crosswalk `product_business_type` con `sha256` y versión. |
| FILTER por producto | **Sí** | `item_code` (usado internamente por el ranking). |
| FILTER por cliente | **No** (dato sí) | `card_code` existe; ninguna lectura/capability lo usa. |
| GROUP BY producto | **Sí** | `PLAN.group_by='sap_product'`. |
| GROUP BY cliente | **No** (dato sí) | Requiere parametrizar `group_by`. |
| AGGREGATE importe de línea | **Sí** | `DEFINITION = commercial_active_invoice_line_amount_excluding_line_tax_v1`. |
| AGGREGATE cabecera neta | **Sí** | `sales.period_billed_amount`. |
| SORT / LIMIT | **Sí** | `order_by` + `limit` 1..50. |
| COMPARE entre períodos | **Parcial** | Sólo para la métrica de cabecera y entre dos resultados (`MONETARY_COMPARISON`); para categoría sí; para ranking no (`comparison` = vista histórica). |
| BREAKDOWN por dimensión | **No** | No hay lector que devuelva el desglose completo por cliente/mes. |
| DOCUMENT TRACE | **Sí** | `DOCUMENT_REFERENCE` / `READ_LINES`. |

### 4.2 El hueco real

El catálogo no es un conjunto de primitivas composables: es una **lista de plantillas `pregunta → consulta`**. La composición sólo existe en dos islas: `RESULT_REFERENCE` (elegir un elemento de una lista) y `MONETARY_COMPARISON` (restar dos importes acreditados). Ambas están construidas con el mismo patrón correcto y reutilizable:

> **el LLM propone una referencia a *resultados acreditados*; Team360 resuelve la referencia contra datos autorizados, valida compatibilidad (moneda, período, medida, cobertura) y calcula localmente con aritmética Decimal.**

Ese patrón (`monetary_comparison.py`) es exactamente la semántica de `COMPARE`/`BREAKDOWN` que el enunciado propone, y ya está en producción DEV con gate, permiso, re-autorización y prueba. Es la mejor evidencia de que la **Alternativa B/C es viable sobre la arquitectura existente** y no unareescritura.

### 4.3 Riesgo que la composición debe conservar

- Nada de SQL libre: el LLM nunca debe emitir tablas, columnas ni SQL. Hoy eso se garantiza porque el LLM elige entre métricas cerradas y el código construye las consultas.
- La composición no puede inventar medidas: sólo puede reusar medidas ya acreditadas (`DEFINITION` + `sha256` + `coverage` + `limitations`).
- La reconciliación es la defensa real: el ranking reconcilia su desglose contra el total de categoría con tolerancia 0. Un `group_by=cliente` debe reconciliar contra el total del producto (o de la categoría si no hay filtro de producto) con la misma tolerancia.
- Moneda: `d.currency='BS' AND l.currency='BS'` con exclusión explícita y auditable, nunca conversión.
- Procedencia: cada resultado debe conservar `publication_id`, `snapshot_id`, `updated_at`, `definition`, `classification`, `coverage` y `exceptions`.
- Fail-closed: la taxonomía de cliente (hoy 0 `COMMERCIAL_CUSTOMER`) implica que un ranking de «clientes comerciales» debe quedar bloqueado con diagnóstico, no relajar el filtro.

## 5. Fase E — Tres alternativas

### Alternativa A — Seguir agregando capabilities específicas

- **Resuelve**: la pregunta concreta de hoy, con el menor riesgo por capability.
- **Deja pendiente**: toda clase de consultas que cambie de dimensión. Cada nueva dimensión (cliente, sucursal, vendedor, canal, mes) ⇒ nueva capability + permiso + registro + slots + prompt + formatter + gate + evidencia. El prompt ya es una lista de reglas por capability; su costo crece con el producto capabilities × dims.
- **Archivos**: `datalake/*_query.py` (nuevo), `capabilities.py`, `state_engine.py`, `luna.py`, `handler.py`, `business_categories.py`, `provisioning/`, `modules/console` (permiso).
- **Seguridad**: neutra (cada capability conserva su permiso y guardas).
- **Rendimiento**: cada reader es un worker DuckDB con timeout y `_LOCK`; multiplicar readers multiplica procesos.
- **Regresión**: media; cada capability nueva toca el catálogo cerrado y puede desplazar reglas del prompt.
- **Esfuerzo**: ~1 capability por familia; el incidente actual sería `top_customer_by_product.v1` + `client_line_amount.v1` + `client_product_ranking.v1` + `period_comparison_by_client.v1`… la familia «cliente» sola son 4.
- **Compatibilidad Foundation**: total.
- **Gradualidad**: sí, pero cada paso es una capability, no una clase.

### Alternativa B — Capabilities reutilizables con composición limitada

- **Resuelve**: la familia «producto × cliente × período × medida» reutilizando los readers y contratos acreditados, parametrizando `group_by` y `filters` dentro de un conjunto cerrado de combinaciones permitidas.
- **Deja pendiente**: consultas que requieren dimensiones no previstas (combinaciones arbitrarias, joins, subagregaciones anidadas) — seguirían necesitando capabilities específicas; y la semántica de cliente comercial (taxonomía).
- **Archivos**: `state_engine.py` (slots de dimensión/cliente/período-conjunto/producto), `luna.py` (prompt: de reglas por capability a reglas por dimensión), `capabilities.py` (catálogo), `datalake/product_line_amount_ranking_query.py` → reader genérico `commercial_line_amount_by`, `handler.py` (formatters por dimensión), `result_references.py` (exponer ámbito del resultado).
- **Seguridad**: mejora si el plan es una lista cerrada y compilada server-side; el LLM no toca SQL. Hay que preservar el `group_by` permitido por capability (no dejar que el LLM elija).
- **Rendimiento**: un reader parametrizado en lugar de N; misma cantidad de lectures.
- **Regresión**: media-alta (toca prompt y esquema); mitigable con las pruebas existentes + batería de conversaciones.
- **Esfuerzo**: medio; ~6–8 archivos.
- **Compatibilidad Foundation**: total (reutiliza `DEFINITION`, guardas, reconciliación).
- **Gradualidad**: alta — se puede empezar por un solo `group_by` nuevo.

### Alternativa C — Planificador empresarial determinístico

- **Resuelve**: expresividad maximal dentro de un lenguaje cerrado: Luna emite `{dataset, filters, group_by, measure, order, limit, breakdown, compare}`; un planner de Team360 valida contra una whitelist `dataset × group_by × measure × período` y compila a los readers; los breakers siguen siendo成分 cerrados.
- **Deja pendiente**: nada conceptual, pero es el mayor costo de construcción y el mayor riesgo de sobre-expresión (un plan demasiado expresivo es un SQL libre convester).
- **Archivos**: los de B + un `planner.py` nuevo (hoy `datalake/planner.py` es de segmentación de ingestión, otro propósito) + un DSL + validador + compilador + formatters.
- **Seguridad**: depende criticamente de la whitelist; es el punto de mayor riesgo. Mitigable (fail-closed, sin SQL libre, permisos por capability, reconciliación obligatoria), pero exige más gates.
- **Rendimiento**: igual o mejor (un plan se compila a una consulta).
- **Regresión**: alta; el prompt cambia de forma radical.
- **Esfuerzo**: alto.
- **Compatibilidad Foundation**: total.
- **Gradualidad**: posible en垂直, pero el верificador de planes es trabajo nuevo y no trivially correcto.

### Recomendación

**HYBRID B+C acotado**: la *estructura* de B (capacidades reutilizables y parametricidad) con el *núcleo* de C (un plan explícito y validado), limitado a un **vocabulario cerrado de una sola dimensión de agrupación a la vez** (`sap_product` | `customer_card_code`), **una** medida por familia y **un** período (o un conjunto de períodos contiguos como unión).

Motivo: la alternativa A no escala; la C completa sobredimensiona el problema y aumenta el riesgo de seguridad; la B sola puede quedarse sin generalidad si el plan no es explícito. El híbrido entrega un `plan` explícito y validado (auditable, determinista) sobre primitivas ya acreditadas, y es **incremental**: cada dimensión nueva se añade a la whitelist, no una capability nueva.

## 6. Fase F — Batería conversacional de negocio

### 6.1 Diseño

- **Vehículo existente reutilizable**: `assistant/tests/runtime_http/run_battery.py` (batería HTTP contra el pipeline real `MessageDispatcher → TelchiHandler → State Engine → capabilities → Foundation`, persistida en PostgreSQL, **sin enviar WhatsApp**). 40+ escenarios actuales, todos **monotónicos**: no hay ninguna conversación que cambie de dimensión o encadene producto→cliente→ranking→comparación.
- **Escenario nuevo**: `BIZ01` (10 turnos, §6.2), un único `conversation_key` para los 10 turnos → una sola conversación persistida.
- **Evaluador**: un evaluador estático de continuidad, que para cada turno extrae del audit persistido (`interpretation_proposed`, `confirmed_state`, `previous_state`, `execution_result`, `bmd`, `response_prepared`) las tuplas **(producto, categoría, cliente, conjunto de períodos, métrica, dimensión, capability, clasificación, necesita_aclaración)** y las compara con las del turno anterior.
- **Reglas de calidad** (por turno): `Heredó producto` / `Heredó categoría` / `Heredó período(s)` / `Heredó métrica` / `Heredó cliente`; `Aclaración innecesaria`; `Indisponibilidad injustificada`; `Pérdida de período`; `Resultado parcial útil`; `Clasificación` ∈ {READY_EXISTING, COMPOSABLE, NEW_DATA_CONTRACT, NEW_CAPABILITY, CONTEXT_DEFECT, BLOCKED_BY_EVIDENCE}.
- **Regla de no-falso-PASS**: un turno no puede marcarse PASS por una respuesta simulada; sólo por `execution_status='executed'` con resultado acreditado, o por una indisponibilidad **correctamente clasificada y explicada**. Toda indisponibilidad que omita un resultado parcial acreditado cuenta como `UNJUSTIFIED_UNAVAILABILITY`.
- **Replay del incidente**: fixture con los cuatro turnos reales (P0, P1, A, B, C) como caso de regresión, ejecutado offline contra el motor de estado (sin Luna, sin WhatsApp), para verificar que una corrección de memoria no reintroduce el defecto.

### 6.2 Clasificación estática de los 10 turnos (con la arquitectura actual)

| # | Turno | Clasificación | Evidencia / gap |
|---|---|---|---|
| 1 | ¿Cuánto facturamos en septiembre? | **READY_EXISTING** | Ejecutado 19/10 y 20/10 en el mismo hilo. |
| 2 | ¿Cuánto vendimos de productos terminados? | **READY_EXISTING** | Ejecutado 20/10 16:54 (`category_line_amount`). |
| 3 | ¿Cuáles fueron los cinco más vendidos? | **READY_EXISTING** | Ejecutado 20/10 17:32 (ranking, Top 5). |
| 4 | ¿En qué puesto estuvo L03281 en julio y agosto? | **CONTEXT_DEFECT** | La capability existe (probada 21/10 12:08), pero el turno previo la dejó irrealizable. |
| 5 | ¿A qué cliente le vendimos más ese producto en esos dos meses? | **COMPOSABLE** | Dato verificado (§3.2). Falta dimension + slot cliente + lector por `card_code`. |
| 6 | ¿Cuánto compró ese cliente en julio y cuánto en agosto? | **COMPOSABLE** | Misma lectura, filtro `card_code` + desglose mensual. |
| 7 | ¿Qué otros productos compró? | **COMPOSABLE** | Misma lectura, `group_by=sap_product` restringido a `card_code`. |
| 8 | ¿Qué % representa ese cliente sobre las ventas del producto? | **COMPOSABLE** | Aritmética local entre dos resultados acreditados (patrón `MONETARY_COMPARISON`). |
| 9 | ¿Qué clientes dejaron de comprar ese producto? | **NEW_CAPABILITY** | Diferencia de conjuntos de clientes entre dos períodos; requiere lector de presencia por período. |
| 10 | ¿Qué cambió entre julio y agosto? | **COMPOSABLE** | `COMPARE` ya existe para cabecera y categoría; falta para producto/cliente. |

### 6.3 Métricas (línea base medida en el incidente real)

| Métrica | Valor |
|---|---|
| Turnos analizados (diseño) | 10 |
| Turnos reales auditados | 5 (P0, P1, A, B, C) |
| Respondibles hoy (READY_EXISTING) | 3 de 10 (+1 si se corrige el defecto de contexto del turno 4) |
| COMPOSABLE | 5 |
| NEW_CAPABILITY | 1 (turno 9) |
| NEW_DATA_CONTRACT | 1 (taxonomía de cliente comercial, si se exige «cliente comercial») |
| Aclaraciones innecesarias | 1 (turno A) |
| Indisponibilidades injustificadas | 1 (turno C) |
| Pérdidas de período en la respuesta | 1 (turno C: julio) |
| Capacities nuevas requeridas (estrategia A) | ≥ 4 para la familia cliente |

## 7. Fase G — Propuesta arquitectónica

### 7.1 Diagnóstico

1. **Problema principal**: el estado conversacional modela *consultas*, no *negocio*. No existe el concepto de **dimensión comercial** (producto, categoría, cliente) ni de **conjunto de períodos**; cada concept tiene un slot ad-hoc, y un slot (`entity_mention`) hace de dos cosas a la vez. Cuando el empresario cambia de dimensión, no hay dónde escribirlo.
2. **Cuánto es de Luna**: ~20 %. Luna cumple el contrato (incluido el acierto de no inventar). Su aporte al defecto fue la disciplina de slot en P1 (escribió un código de producto en el slot de categoría porque el contrato no le daba otro sitio) y el `DIRECT_UNAVAILABLE` del turno C, que era lo único expresable. El prompt, al ser un catálogo de reglas por capability, **codifica el supuesto de catálogo cerrado** y lo amplifica.
3. **Cuánto es del State Engine**: ~30 %. Valida forma, no significado: acepta `entity_mention="L03281"` en un slot cuyo único consumidor espera un código de categoría; no impide la sobrescritura; y **persiste el estado dañado** que se convierte en la entrada del turno siguiente. Además no tiene forma de representar unión de períodos ni dimensión.
4. **Cuánto es del contrato de capabilities**: ~50 %. El catálogo expone «métricas», no «dimensiones»; no existe operación de cliente; `availability()` ata el alcance de producto a una sola métrica; y el vocabulario de errores no tiene «dimensión no acreditada», por lo que el turno C quedó etiquetado `RANKING_UNAVAILABLE`.
5. **Qué falla al cambiar de dimensión comercial**: la transición requiere escribir «agrupar por cliente» y «unir julio y agosto»; no hay slot para ninguna de las dos; el modelo se ve obligado a (a) reutilizar un slot ocupado — y destruir contexto — o (b) anular la métrica y emitir indisponibilidad.
6. **Cambio mínimo de mayor impacto**: **preservar el ámbito del resultado previo en `result_context` + dedicated slots para categoría y producto**. Con sólo (i) exponer el ámbito del resultado en el contexto que ve Luna y (ii) impedir la colisión categoría/producto, el turno A de hoy no habría pedido la categoría, y la cadena del 20/10 no se habría roto. Es un cambio de bajo riesgo y alto rendimiento, y **no requiere tocar el catálogo ni Foundation**.
7. **Cómo evitar una capability por pregunta**: parametrizar el *reader* acreditado por dimensión de agrupación y por conjunto de filtros, dentro de una whitelist cerrada (`dataset × group_by × measure × filtros`). El plan lo propone Luna; Team360 lo valida y compila. La lista de capabilities deja de crecer por pregunta y crece por dimensión.
8. **Cómo garantizar BUSINESS ANSWER FIRST**: contrato de respuesta en dos partes, obligatorio — (a) **resultado acreditado disponible** (aunque sea parcial: total del producto en la unión de los dos meses, ranking del producto, desglose mensual del producto), (b) **faltante exacto y sunature accredited** («no tengo acreditada la taxonomía de cliente comercial: 0 clientes clasificados como comerciales en la publicación vigente») y (c) **siguiente paso verificable**. Un gate rechaza la indisponibilidad «desnuda» cuando existe un sub-plan acreditado compatible. Regla dura: **nunca perder un período del texto**.
9. **Cómo no degradar la seguridad**: el LLM nunca emite SQL, tablas, columnas ni datasets; emite un plan de un vocabulario cerrado; el planner valida y compila contra readers pre-registrados; cada reader conserva sus guardas (moneda, clasificación, lineage, snapshot pineado), su reconciliación con tolerancia 0 y su procedencia; RBAC se re-valida por capability antes y después; el plan se audita completo. Fail-closed por defecto: dimensión o taxonomía no acreditada ⇒ diagnóstico, no respuesta.
10. **Cómo validamos conversaciones completas antes de PASS**: (a) batería `BIZ01` de 10 turnos sobre el pipeline real, persistida, con evaluador de continuidad; (b) replay offline del incidente real (P0/P1/A/B/C) como regresión; (c) para cada fase, criterio verificable de no-regresión sobre las pruebas existentes (`323 tests focalizados PASS` y las seis garantías DEV vigentes) y `lat check` + `git diff --check`.

### 7.2 Fases propuestas (pequeñas, con criterio verificable)

| Fase | Alcance | Criterio de aceptación |
|---|---|---|
| **F0** Línea base | Sólo evidencia: fixture del incidente real (5 turnos) + escenario `BIZ01` + evaluador de continuidad que **reporta** los defectos actuales sin cambiar comportamiento. | Reporte reproducible con 1 aclaración innecesaria, 1 indisponibilidad injustificada, 1 pérdida de período. Sin cambio de runtime. |
| **F1** Ámbito del resultado | `result_references.interpreter_context()` expone categoría, período, métrica, medida y moneda del resultado presentado; `handler` lo inyecta. | En el replay, Luna ya no necesita preguntar la categoría cuando el ranking previo está en contexto. Regresión: pruebas de `result_references` y `historical_ranking` PASS. |
| **F2** Colisión categoría/producto | Slot dedicado `/business_category` (código de `CATEGORIES`); `entity_mention` queda reservado a entidades comerciales; el motor **rechaza** un código de categoría en `entity_mention` y un código de producto en `entity_mention` si la capability lo exige. | El turno P1 (20/10) deja de degradar el estado: replay del incidente produce estado con categoría **y** producto. Test negativo: `entity_mention="L03281"` con métrica de ranking ⇒ `contract_error`. |
| **F3** Conjunto de períodos | `/periods` (lista de intervalos contiguos) o `comparison.mode ∈ {compare, union}`; el prompt distingue «julio y agosto» (unión) de «julio contra agosto» (comparación). | «de estos dos meses» produce un período `[2026-07-01, 2026-09-01)`; la reconciliación da Bs 586.227,06 idéntica a la suma de los dos meses del turno B. |
| **F4** Dimensión cliente | Slots `/group_by` y `/client`; el alcance de producto deja de estar atado al ranking; reader `commercial_line_amount_by` parametrizado por `group_by ∈ {sap_product, card_code}` con la misma `DEFINITION` y reconciliación contra el total del producto. | Turno C responde con el cliente facturado líder (Bs 115.044,44; Bs 72.383,99 en julio y Bs 42.660,45 en agosto) y declara la semántica (cliente facturado SAP, no comprador final). Test de reconciliación: suma por cliente = total del producto, tolerancia 0. |
| **F5** Taxonomía de cliente comercial | Acreditar `customer_business_type` con evidencia (actualmente 0 `COMMERCIAL_CUSTOMER`) o mantener el filtro bloqueado con diagnóstico. | O bien el ranking excluye `CONTROL TRIBUTARIO` con evidencia trazable, o bien el turno C declara explícitamente que el ranking es de clientes facturados y por qué no se depura. |
| **F6** BUSINESS ANSWER FIRST | Formatter de indisponibilidad en dos partes (resultado acreditado + faltante + siguiente paso); vocabulario de error con `DIMENSION_NOT_ACCREDITED`, `PERIOD_SET_UNSUPPORTED`, `SCOPE_NOT_TRANSFERABLE`; gate que rechaza indisponibilidad desnuda. | Ninguna indisponibilidad pierde un período del texto; el turno C incluye el total acreditado del producto en la unión de los dos meses. |
| **F7** Batería conversacional | `BIZ01` de 10 turnos en `run_battery.py` con aserciones de continuidad; reporte en `data/reports/telchi/`. | 10/10 turnos con continuidad de producto, categoría, cliente, período y métrica; 0 aclaraciones innecesarias; 0 indisponibilidades injustificadas; 0 pérdidas de período. |

Secuencia recomendada: **F0 → F1 → F2** (memoria, riesgo bajo, impacto alto) → **F3 → F4** (composición mínima) → **F5/F6** (semántica y forma de respuesta) → **F7** (gContinuidad). F1+F2 son, por sí solas, la solución del incidente del 21/10.

### 7.3 Riesgos de regresión

| Riesgo | Mitigación |
|---|---|
| Ruptura del prompt (≈200 líneas) al reescribirlo por dimensiones | Mantener el prompt actual y **añadir** reglas de dimensión de forma incremental; una regla por vez, con test por regla. |
| Prompt más largo ⇒ peor interpretación | Medir; el prompt ya codifica reglas por capability; la reescritura por dimensión debería **reducir** tamaño. |
| Slots nuevos rompen estados persistidos | V2 ya materializa por defecto los slots nuevos (`INTENT_V2 | PRODUCT_FIELDS`); los estados V1 siguen válidos. |
| Reader parametrizado cambia cifras | La `DEFINITION`, las guardas y la reconciliación con tolerancia 0 se conservan; los números del ranking actual deben ser **bit-idénticos** tras el refactor (gate de paridad). |
| Falsas respuestas del modelo al increases de expresividad | Plan cerrado y fail-closed; whitelist; el LLM no elige datasets ni columnas. |
| Regresión en las 6 garantías DEV y en los 323 tests | Re-ejecutar las focalizadas por fase; conservar evidencia por hash; no re-ejecutar suites generales sin invalidación. |
| Trabajo concurrente de otros agentes en el mismo worktree | Los archivos de `assistant/` están **untracked** y con cambios de hoy: son `MODULE_LOCAL` de otro actor. Coordinar antes de tocar `luna.py`, `state_engine.py`, `capabilities.py`, `handler.py`. |

## 8. Entrega final

### Incidente real

```
FIRST_DIVERGENCE_0907=El estado persistido por el turno P1 (20/10 17:33 UTC-3, evento 6b7b2b39) sobrescribió /entity_mention de LAB_FINISHED_PRODUCT a L03281 sin setear /ranking_target_item_code; el State Engine lo aceptó (committed=true) y lo persistió. El turno A heredó un estado sin categoría y no podía recuperarla: result_references.interpreter_context() no expone el ámbito del ranking previo. La aclaración no fue un fallo de Luna ni del prompt (luna.py, mtime 20/10 21:34, ya contenía el ejemplo L03281).

UNNECESSARY_CATEGORY_CLARIFICATION=YES

FIRST_DIVERGENCE_0909=No hubo ninguna divergencia de Luna ni del State Engine: el contrato no tiene slot para la dimensión cliente ni para la unión de dos meses. Luna proposals REFINE/DIRECT_UNAVAILABLE con /metric=null y /requested_metrics=[] conservando categoría, producto y ambos períodos, tal como ordena el prompt ("No hay capability de ventas por empresa/cliente"). La divergencia es de contrato: availability() cortó en "El producto objetivo corresponde únicamente al ranking monetario" (RANKING_UNAVAILABLE, etiqueta engañosa) y el texto lo produjo business_categories.unavailable_text(), que sólo conoce category_code + metric + period, por lo que julio desapareció y no hubo ninguna cifra parcial.

PRODUCT_CONTEXT=PASS        (L03281 se conservó en /ranking_target_item_code; el slot no es transferible a otras operaciones)
MULTIPERIOD_CONTEXT=FAIL    (julio y agosto se representaron como period+comparison = comparación, nunca como unión; y el texto final sólo mostró agosto)
CUSTOMER_INTENT=PASS        (Luna reconoció la dimensión cliente y no la mapeó a ventas, ranking ni búsqueda; la intención, eso sí, no quedó representable en el estado)
CAPABILITY_GAP=YES          (no existe capability ni dimensión cliente; el catálogo no puede expresar "agrupar por cliente")
UNAVAILABLE_RESPONSE=PARTIAL(el gap es real, pero la respuesta no es una respuesta empresarial: sin cifra parcial, sin faltante explained, sin siguiente paso, y con julio eliminado del texto)
```

### Datos y composición

```
PRODUCT_CUSTOMER_RELATION=VERIFIED   (atomic.sales_document.card_code ⋈ atomic.sales_line.doc_entry; 2.014 líneas, 2.012 docs, 468 clientes, Bs 586.227,06 en [2026-07-01,2026-09-01); reconcilia exacto con el ranking acreditado 271.255,49 + 314.971,57)
JULY_AUGUST_CUSTOMER_ANALYSIS=FEASIBLE (unión = un único período contiguo; desglose mensual y orden por importe acumulado son aritmética sobre la misma medida acreditada)
EXISTING_CAPABILITIES_REUSABLE=sales.product_line_amount_ranking.v1 (medida, guardas, reconciliación y excepciones), sales.category_line_amount.v1 (DEFINITION de línea comercial), sales.net_amount (cabecera/NC), sales.by_products + products.search (selección de producto), sales.latest_documents + DOCUMENT_REFERENCE (trazabilidad), RESULT_REFERENCE y MONETARY_COMPARISON (precedentes de composición ya en producción DEV)
COMPOSITION_GAPS=sin dimensión/group_by; sin slot de cliente; sin conjunto/unión de períodos; alcance de producto atado al ranking; result_context sin ámbito; sin BREAKDOWN/PERCENT sobre resultados previos; vocabulario de error sin "dimensión no acreditada"; formatter de indisponibilidad sin resultado parcial
BUSINESS_ANSWER_FIRST=PARTIAL (sostenido sólo en dos islas ad hoc: la vista histórica del ranking y MONETARY_COMPARISON; la ruta genérica produce indisponibilidad desnuda)
```

### Arquitectura

```
ARCHITECTURE_ROOT_CAUSE=El estado conversacional es una plantilla de consulta (métrica + período + comparación + un entity_mention genérico), no un contexto de negocio con entidades y dimensiones. No existe el concepto de dimensión comercial ni de conjunto de períodos; una misma ranura (entity_mention) representa la categoría acreditada o la entidad nombrada, y el alcance de producto (ranking_target_item_code) está atado a una sola métrica. Al cambiar de dimensión comercial el modelo no tiene dónde escribirlo: o sobrescribe un slot ocupado (y destruye el contexto previo, que el motor persiste sin observación) o anula la métrica y emite una indisponibilidad genérica. El catálogo enumera plantillas pregunta→consulta en lugar de primitivas acreditadas componibles.
RECOMMENDED_ALTERNATIVE=HYBRID (B+C acotado): readers acreditados parametrizados por dimensión de agrupación, sobre un plan explícito de vocabulario cerrado (dataset × group_by × measure × filtros × período), compilado y validado por Team360. LLM sin SQL; whitelist; fail-closed. Precedente ya en producción: MONETARY_COMPARISON.
MINIMAL_CHANGE_SET=(1) result_references.interpreter_context(): exponer ámbito del resultado (categoría, período, métrica, medida, moneda); (2) state_engine: slot dedicado de categoría + rechazo de la colisión con entity_mention + alcance de producto transferible; (3) state_engine: conjunto/unión de períodos; (4) state_engine: slots group_by y client; (5) datalake: reader de importe de línea parametrizado por group_by (card_code) con reconciliación contra el total del producto; (6) business_categories/handler: formatter de indisponibilidad en dos partes + vocabulario de error; (7) tests/runtime_http/run_battery.py: escenario BIZ01 + evaluador de continuidad. (1)+(2) resuelven el incidente del 21/10 sin tocar catálogo ni Foundation.
SECURITY_IMPACT=NEUTRO→POSITIVO si el plan es cerrado y compilado server-side (el LLM no emite SQL, tablas, columnas ni datasets; whitelist de combinaciones; guardas de moneda/clasificación/lineage; reconciliación con tolerancia 0; RBAC re-validado por capability; procedencia y auditoría completas; fail-closed cuando la dimensión o la taxonomía no están acreditadas). Riesgo a vigilar: un plan demasiado expresivo equivaldría a SQL libre; se acota a UNA dimensión de agrupación, UNA medida por familia y un período/contiguo.
IMPLEMENTATION_PHASES=F0 línea base (fixture del incidente + escenario BIZ01 + evaluador, sin cambio de comportamiento) → F1 ámbito del resultado → F2 colisión categoría/producto → F3 conjunto de períodos → F4 dimensión cliente → F5 taxonomía de cliente comercial → F6 BUSINESS ANSWER FIRST (respuesta en dos partes + gate) → F7 batería conversacional de 10 turnos con aserciones.
REGRESSION_RISKS=ALTO en el prompt de Luna (reescritura ⇒附录 cambios de comportamiento; mitigación: añadir reglas de forma incremental, una por vez, con test por regla); MEDIO en el esquema de estado (mitigación: materialización por defecto V2, estados V1 siguen válidos); MEDIO en el reader parametrizado (mitigación: gate de paridad bit a bit contra las cifras actuales del ranking); MEDIO en el formatter de indisponibilidad (mitigación: las 6 garantías DEV y los tests focalizados existentes); CONCURRENCIA: assistant/*.py está untracked y con cambios de hoy → scope MODULE_LOCAL de otro actor, coordinar antes de editar.
```

### Calidad conversacional

```
CONVERSATION_TURNS_ANALYZED=10 diseñados + 5 reales auditados (P0, P1, A, B, C)
CURRENTLY_ANSWERABLE=3 de 10 (turnos 1, 2, 3) → 4 de 10 tras F1+F2
COMPOSABLE=5 (turnos 5, 6, 7, 8, 10)
NEW_CONTRACT_REQUIRED=1 (taxonomía customer_business_type: 0 COMMERCIAL_CUSTOMER en la publicación vigente; necesaria sólo si se exige "cliente comercial" y no "cliente facturado en SAP")
NEW_CAPABILITY=1 mínimo bajo el híbrido (desglose por cliente por período, turno 9); 4 bajo la estrategia A
UNJUSTIFIED_CLARIFICATIONS=1 (turno A)
UNJUSTIFIED_UNAVAILABILITY=1 (turno C)
```

### Estado

```
CODE_MODIFIED=NO
GATES_MODIFIED=NO
RUNTIME_MODIFIED=NO
GIT_COMMIT=NO
GIT_PUSH=NO
```

Verificaciones ejecutadas: consultas PostgreSQL READ ONLY (`default_transaction_read_only=on`) sobre `team360`; lecturas DuckLake READ ONLY (`ATTACH … READ_ONLY`, `threads=2`, `memory_limit=512MB`) sobre `CURRENT 1408`; ninguna escritura; ningún proceso propio dejado corriendo; `lat check` PASS (línea base previa a este informe).

Nota de concurrencia: `modules/telchi/assistant/*.py` y `datalake/*.py` están **untracked** con cambios del 20/10 (otro actor). Este informe no los modificó.
