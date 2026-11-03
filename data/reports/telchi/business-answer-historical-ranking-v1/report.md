# Business Answer First & Historical Ranking V1

Cierre DEV de Telchi en `feature/console-backend-core`, 20/10/2026. La aceptación WhatsApp sigue siendo manual del owner; no se envió ningún mensaje ni se inició/reinició el runtime.

## Resultado empresarial

L03281 — MINOXITEL 5% LOCION - HOMBRE x 100 mL., dentro de LAB_FINISHED_PRODUCT por importe comercial acumulado.

| Período | Puesto | Comparables | Importe BS | Líneas de categoría | Total de categoría BS |
| --- | ---: | ---: | ---: | ---: | ---: |
| Julio 2026 | 2 | 283 | 271.255,49 | 24.265 | 3.273.893,07 |
| Agosto 2026 | 1 | 289 | 314.971,57 | 23.885 | 3.480.448,89 |
| Septiembre 2026, regresión | 1 | 278 | 259.922,61 | 18.541 | 2.679.208,66 |

Importes de facturas activas, sin IVA de línea, antes de notas de crédito y ajustes globales. Clasificación actual, no histórica; no certifican cierre mensual completo. Diferencia agosto menos julio: Bs 43.716,08.

## Investigación antes del fix

La reproducción sobre Foundation read-only está en [audit-before.json](audit-before.json); [audit-final.json](audit-final.json) agrega la comprobación raw y la regresión posterior. Cada archivo contiene SQL, parámetros, publicación, snapshot y crosswalk.

```text
L01412_ENTRY_POINT=category.aggregate, joined global mensual, guard monetario previo a categoría
RANKING_CONTAMINATED=NO
CLASSIFICATION_ERROR=NO respecto del crosswalk acreditado
JOIN_DUPLICATION=NO
MONETARY_GUARD_SCOPE=TOO_BROAD antes del fix
JULY_RANK_VERIFIED=YES
AUGUST_RANK_VERIFIED=YES
```

Foundation → reader pinned → filtros SAP_B1_HANA/OINV/INV1 → comprobaciones de claves → join por fuente/documento y ItemCode → clasificación → guard → agregación por producto → conciliación contra categoría → importe DESC/código ASC → Top N o localización histórica.

- L01412: SABORIZANTE VAINILLA EXTRA x kg.; grupo SAP 129, INSUMO; RAW_MATERIAL / VALIDATED, regla PBT-006, evidencia BOM component/input-bulk, confianza 0,95. Crosswalk `v2_product_business_type_f9c1130d852ccb61`, hash `7fcfef912cc8ef46868e03b56f90b61da13c08e951c453abc0483690edc36e10`.
- Factura 260102290, DocEntry 11507272, línea 0, 26/08/2026. Cabecera BS, moneda de línea USD, LineTotal original 698.25, LineRate 11.57, TotalFrgn 0. Estos campos coinciden con raw; **no se acredita que LineTotal esté denominado en USD** ni que SAP tenga un error.
- El mismo ItemCode existe en catálogos SAP y legacy con distintos canonical IDs. No hay multiplicación: el catálogo del ranking usa exclusivamente SAP_HANA, y el crosswalk es único por ItemCode.
- L01412 no pertenece al agregado LAB_FINISHED_PRODUCT. El guard anterior lo alcanzaba porque validaba todas las categorías del mes. La reproducción anterior falla sólo en agosto por `category_currency_not_accredited`; julio y septiembre pasan.
- No hay duplicados de claves documento/fuente/tabla, línea/fuente/tabla ni crosswalk. Las 24.265 líneas de julio y 23.885 de agosto tienen clasificación VALIDATED y moneda BS en cabecera y línea, sin diferencias de lineage.
- Contraste raw: todas las líneas de categoría de julio/agosto coinciden por DocEntry/LineNum, ItemCode, monedas y LineTotal. Cero faltantes, diferencias o duplicados raw. Julio requiere ambas particiones 0000/0001 del mismo run; revisar sólo 0000 deja 25 filas aparentemente ausentes, resueltas al incluir 0001 sin alterar datos.
- La suma del ranking completo concilia exactamente con el total de categoría y sus conteos. El producto se localiza después del ordenamiento completo, no antes ni dentro del Top 5.

Clasificación causal: A (orden/alcance de consulta) VERIFIED; B (guard demasiado amplio) VERIFIED; C (clasificación errónea) sin evidencia, crosswalk compatible VERIFIED; D (join/duplicación) descartado en universo auditado; E (error documental SAP) UNRESOLVED, no demostrado. La diferencia de monedas raw es VERIFIED, su significado no se convierte en acusación al negocio.

## Implementación mínima

El [contrato local](../../../../SrvRestAstroLS_v1/backend/modules/telchi/assistant/PRODUCT_MONETARY_RANKING_V1.md) incorpora ANSWER_FIRST_WITH_EXCEPTIONS como principio Telchi, sin una reescritura general del asistente.

- Guard monetario posterior al establecimiento de pertenencia a la categoría. Controles de claves, joins, clasificación, lineage y conciliación conservados.
- Ranking: exclusiones monetarias internas explícitas, sólo cantidades BS compatibles agregadas; resultado y posiciones parciales, con impacto potencial y auditoría. No hay conversión ni demostración de invariancia de posiciones implementada.
- Excepciones externas separadas en `external_currency_anomalies`, nunca facturas excluidas del ranking solicitado. Se presentan cuando se pide detalle pertinente, no en la respuesta ordinaria.
- Producto objetivo opcional separado de categoría; `period`/`comparison` reutilizados como períodos independientes. Campos nuevos `ranking_target_item_code` y `ranking_detail`; sólo vocabulario, validación y limpieza NEW_QUERY, no cambio del algoritmo del engine.
- Un período fallido no borra el otro. Producto ausente no significa importe cero. Referencias ordinales simples no permiten perder advertencias de listas parciales.
- No se modifica Foundation, SAP, clasificación, FULL_ACCESS, resolver, servicios horizontales, transportes ni infraestructura. No se registran capabilities o grants nuevos.

## Validación reproducible

Las pruebas locales son fixtures, no acreditación de datos reales. La auditoría raw y las sondas autenticadas son evidencia separada.

```bash
cd SrvRestAstroLS_v1/backend
uv run python -m modules.telchi.investigation.validation.business_answer_historical_ranking_v1.audit --output /ruta/nueva/audit.json
uv run pytest modules/telchi/assistant/tests/test_historical_ranking.py modules/telchi/assistant/tests/test_product_monetary_ranking.py modules/telchi/datalake/tests/test_category_line_amount_query.py modules/telchi/datalake/tests/test_product_line_amount_ranking_query.py -q
uv run python -m modules.telchi.assistant.tests.live_historical_ranking --output /PRIVATE_ROOT/nuevo-historical.json
uv run python -m modules.telchi.assistant.tests.live_product_monetary_ranking --output /PRIVATE_ROOT/nuevo-six-gates.json
```

- Regresión específica observada FAIL antes del fix: moneda USD de materia prima dentro de factura mixta bloqueaba productos terminados. PASS después del fix, manteniendo rechazo estricto para la categoría afectada.
- 96 tests de ranking/categoría/histórico PASS. Ampliación focalizada: **256 PASS**, [salida y comando](tests.txt). Incluye estado, independencia V2, referencias, permisos, guard de ejecución rechazada y política de gates.
- Cobertura fixtures: moneda externa/interna, producto multimoneda, factura multicategoría, desconocido/código sin relación, duplicación de join, lineage, mes parcial/fallido, producto ausente, producto en puesto 7 fuera del Top 5 y posiciones potencialmente variables.
- Dos intentos iniciales del runner investigativo abortaron por serialización TIMESTAMPTZ sin pytz y un error local del script; resueltos usando JSON tipado en SQL sin cambiar dependencias. No fueron defectos Foundation. Una consulta exploratoria shell usó `python` inexistente; se repitió con `python3`.
- Sonda final: 7 turnos HTTP autenticados in-process, dispatcher/Console/PG/Foundation reales y Luna GPT-5.6 Medium directo, sin fallback. Estado previo del incidente copiado exclusivamente a un hilo nuevo; original intacto, reload por turno, no una prueba limitada a EMPTY.
- Secuencia: importe de categoría → Top 5 → L03281 → julio/agosto → diferencia → documentos/anomalías. Verificaciones exactas de puesto, universo, importe, conciliación y respuesta específica de L01412.
- Sonda separada de seis garantías: 11 turnos y pipeline durable real; denegación de token, usuario no autorizado, tenant/workspace/módulo, registro inexistente, revocación con rollback, claim duplicado/concurrente, replay y unicidad de intent con rollback. Cero delivery encolado, grants o cambios de seguridad persistidos.
- Prueba adicional real RAW_MATERIAL agosto: [internal-exception-real.json](internal-exception-real.json), 501 líneas BS verificadas por Bs 853.568,45; una línea L01412 excluida explícitamente por moneda incompatible, importe original conservado sin atribuirlo a USD, conciliación cero y ranking parcial con advertencia de cambio potencial. Demuestra el tratamiento interno, distinto de su aislamiento externo en LAB_FINISHED_PRODUCT.
- Seis gates publicados atómicamente con backup del manifest previo, mismo source fingerprint y preflight normal PASS; aprobación de acceso intacta, sin vencimientos o grants nuevos. [Resumen verificable](gate-publication.json) y [sondas públicas sanitizadas](live-summary.json). Fingerprint `bcff5e88b2de7fd238803e13103a011703c1a713af5b8c43a87eaab40fda9b03`.
- `lat check md`, `lat check index`, `lat check sections`, `lat check code-refs`, `lat check` y `git diff --check`: PASS. Advertencias LAT no bloqueantes: init/version y clave de búsqueda semántica ausentes; no se cambia configuración global.
- Septiembre conserva total y hash de desglose `077975fab58572d1c8237932c103fd700a0b37750b56ceb32b960f9af8c1a53a`.

## Matriz de entrega

PASS se limita al universo y contrato acreditados, no afirma cobertura histórica completa ni robustez universal del modelo.

```text
L01412_ROOT_CAUSE=VERIFIED guard monetario previo de alcance externo al universo
RANKING_UNIVERSE_INTEGRITY=PASS
CLASSIFICATION_INTEGRITY=PASS respecto del crosswalk acreditado
JOIN_INTEGRITY=PASS
MONETARY_GUARD_SCOPE=PASS
EXTERNAL_ANOMALY_ISOLATION=PASS
ANSWER_FIRST_POLICY=PASS en ranking y proyección histórica; principio documentado para Telchi
PARTIAL_RESULT_DELIVERY=PASS
CONCRETE_EXCEPTIONS=PASS
EXCEPTION_IMPACT=PASS
AUDIT_TRACEABILITY=PASS
FALSE_CERTAINTY_PREVENTION=PASS
HISTORICAL_RANK_CAPABILITY=PASS
JULY_L03281_RANK=2/283; BS 271255.49
AUGUST_L03281_RANK=1/289; BS 314971.57
MULTIPERIOD_CONVERSATION=PASS
PRODUCT_CATEGORY_SEPARATION=PASS
PERSISTED_CONVERSATION_E2E=PASS HTTP autenticado/PG, NO entrega WhatsApp
REAL_LUNA=PASS
FULL_ACCESS=PASS existente y preservado
RBAC_ISOLATION=PASS
SIX_GATES=VALID
RUNTIME_CHANGE_REQUIRED=YES cargar el código nuevo mediante operación manual; sin cambio de infraestructura
READY_FOR_MANUAL_WHATSAPP=YES; inicio/carga y aceptación final exclusivamente manual
TESTS=256 PASS; 7 turnos históricos + 11 turnos sonda seis garantías
```

## Archivos y límites

El trabajo previo del worktree se conserva. Sólo se modificaron archivos locales Telchi y evidencia propia; los archivos ya untracked no se atribuyen íntegramente a esta tarea.

- Data Lake readers existentes: `category_line_amount_query.py`, `product_line_amount_ranking_query.py`; test existente `test_product_line_amount_ranking_query.py`.
- Assistant existente: `state_engine.py`, `luna.py`, `capabilities.py`, `result_references.py`, `PRODUCT_MONETARY_RANKING_V1.md`; nuevo `historical_ranking.py`.
- Tests nuevos: `test_historical_ranking.py`, `live_historical_ranking.py`; auditoría nueva `investigation/validation/business_answer_historical_ranking_v1/audit.py`.
- Estado local: `modules/telchi/status_actual.md`. Evidencia pública de esta tarea en este directorio; payloads completos privados, nunca secretos/identidades del piloto en Git.
- La entrega parcial de anomalías monetarias se implementó en ranking, no una conversión masiva de todas las capabilities. Un fallo de claves/clasificación/procedencia no se oculta mediante filtros: puede impedir cifras de ese período y exige investigación; los otros períodos siguen respondiéndose.
- No se implementó detalle de todas las facturas contribuyentes del ranking; el detalle de excepciones sí identifica documentos conocidos. No se certifica cierre mensual ni clasificación histórica.
- Host BUSY_BUT_SAFE: 8 cores, carga observada cercana a 3, memoria disponible 4,5–5,2 GiB, swap estable en ventanas vmstat sin actividad sostenida. Pytest secuencial; un worker Foundation por vez, 2 threads y 512 MB, sin browser. Procesos ajenos terminados: 0; listeners creados: 0; pools propios cerrados.
- HOST_PREFLIGHT=BUSY_BUT_SAFE; RESOURCE_GUARD=PASS; CONCURRENCY_USED=1 worker / 2 threads DuckDB; UNRELATED_PROCESSES_TERMINATED=0; ENVIRONMENTAL_ABORTS=0; OWN_PROCESSES_LEFT_RUNNING=0. Inspecciones y scans secuenciales; sin modificaciones del host.
- Próximo paso: owner carga manualmente el runtime mediante su operación habitual y prueba WhatsApp en la conversación original. No commit, push, cambios de infraestructura ni aceptación productiva.
