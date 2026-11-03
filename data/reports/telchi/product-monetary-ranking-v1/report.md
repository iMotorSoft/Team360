# Product Monetary Ranking V1 — cierre DEV

Rama `feature/console-backend-core`, HEAD base `09d2ec7`. Implementación y gates DEV acreditados; aceptación funcional final pendiente de la prueba WhatsApp del owner. No se inició runtime ni se envió WhatsApp.

## Resultado empresarial real

Foundation snapshot 1408, septiembre de 2026, productos terminados. Datos disponibles del 1 al 24 de septiembre; no es un cierre mensual completo.

1. **L03281 · MINOXITEL 5% LOCION - HOMBRE x 100 mL. — Bs 259.922,61**
2. **L03402 · COLAGENO HIDROLIZADO GRANULADO PREMIUM SABOR ACAI x 300g — Bs 193.755,33**
3. **L01612 · LOCION POVIDINE LITEL 10% x 1L. — Bs 127.578,78**
4. **L01613 · LOCION POVIDINE LITEL 10% x 120mL. — Bs 102.772,04**
5. **L01001 · ALCOHOL 70% x 1L. — Bs 100.764,02**

Importes sin IVA, antes de notas de crédito. Descuentos propios de línea incluidos; sin ajustes globales. No son precios unitarios ni facturación neta documental.

## Conciliación y trazabilidad

El [resultado reproducible](results.json) conserva Top 5/10, materias primas, estados, semántica, cobertura y conciliación. El desglose completo permanece en la auditoría PostgreSQL y evidencia privada.

- Publicación: `foundation_afd08d9eca6a725be53cdc3f9d5709c9`, snapshot `1408`; actualización `2026-09-28T18:18:35.264000`.
- Universo terminado: **278 productos / 18.541 líneas / 10.694 facturas**. Desglose completo y agregado: **Bs 2.679.208,66** cada uno; diferencia **Bs 0,00**, tolerancia exacta cero.
- SHA-256 del desglose completo ordenado: `077975fab58572d1c8237932c103fd700a0b37750b56ceb32b960f9af8c1a53a`.
- Top 5: **Bs 784.792,78**. No debe sumar el total de los 278 productos. Límite aplicado después de conciliar y ordenar; desempate por código SAP ascendente.
- Materias primas: Top 10 real, universo conciliado **Bs 839.582,63**, diferencia cero; ordinal primero resuelve `L01772`, Bs 92.169,09.
- Categoría real vacía: `SEMI_FINISHED`, septiembre 2026, cero filas observadas; no acredita cero fuera de cobertura. `UNKNOWN` bloqueada antes de consultar. Una exploración inicial comprobó que `SERVICE` no estaba vacía (Bs 46.099,38); no se cambió código para ocultarlo.

## Contrato y corrección

El [contrato mínimo](../../../../SrvRestAstroLS_v1/backend/modules/telchi/assistant/PRODUCT_MONETARY_RANKING_V1.md) incorpora un discriminador inequívoco; no cambia el algoritmo del State Engine ni sobrecarga el agregado de categoría.

- Capability `sales.product_line_amount_ranking.v1`, permiso `telchi.sales.product_line_amount_ranking.read.v1`. Categoría obligatoria en V1: no se inventa un universo general acreditado.
- Operación ranking, producto SAP, importe comercial acumulado, orden descendente y desempate por código se publican explícitamente en el contrato interpretativo y resultado. El límite no determina la operación.
- Se reutilizan guardas de integridad, moneda, linaje y clasificación de la agregación acreditada. Catálogo único y nombres publicados; DECIMAL(38,6), sin joins multiplicadores, anuladas ni consumo productivo.
- Un fallo de conciliación conserva diagnóstico y desglose en auditoría interna y no entrega productos/importes comerciales sin verificar.
- Formatter de indisponibilidad distingue ranking de total y motivo de parámetros/período; deja de negar la existencia del agregado acreditado. Denegación continúa segura. Un EXPLAIN con métrica nula no se convierte indebidamente en explicación fiscal.
- Luna conserva septiembre/categoría, distingue cantidades y precio unitario, aclara ambigüedad material y utiliza las referencias ordinales autorizadas existentes.

## Validación real y fallos preservados

Se verificó en PostgreSQL el estado y la propuesta exactos del evento incidente del 20/10/2026 13:56 ART. Sólo se sembraron hilos nuevos de prueba; evento y metadata de la conversación original se cotejaron intactos al final.

- Auth HTTP real sobre ASGI en proceso → dispatcher → identidad y permisos Console/PG → handler → Luna Medium directo → Foundation real. No se usa un resultado mock en las pruebas reales.
- A → total terminado; B → Top 5 monetario; C → Top 10 conservando contexto; D → materias primas conservando ranking/período/límite; E → importe del primer producto de D, sin ejecutar otra consulta.
- Reload desde PostgreSQL en cada turno. Se validó además la formulación original exacta desde el estado auditado, no sólo EMPTY. La propuesta histórica se reprodujo aparte: no se la repara silenciosamente ni se ejecuta como ranking.
- Precio unitario explícito y cantidades no disparan ranking monetario. Consulta ambigua desde hilo sin contexto monetario pregunta importe acumulado versus precio unitario.
- FULL_ACCESS scoped funciona sin asignación individual adicional. Usuario ordinario sin grant, tenant/workspace/módulo ajenos y permiso inexistente denegados. Deshabilitación transaccional de capability revoca aun con identidad obsoleta; rollback verificado. FULL_ACCESS y resolver compartido intactos.
- PostgreSQL durable actual: claim confirmado, duplicado secuencial y dos solicitudes concurrentes rechazados, cache desde handler nuevo idéntico, una sola ejecución de capability. Intent outbound único probado dentro de rollback; no quedó entrega encolada.
- R1 falló funcionalmente por etiqueta de categoría en lugar de código: prompt aclarado y evidencia conservada. R2 detectó EXPLAIN genérico de precio unitario: formatter acotado y regresión añadida. R3 pasó conversación; corrida final pasó con código final y seis garantías actuales. No se atribuyeron a recursos ni se descartaron fallos.

## Evidencia y comandos

Todos los comandos se ejecutaron secuencialmente; registros privados contienen auditorías completas sin publicarlas junto a identidad, teléfono o credenciales.

Desde `SrvRestAstroLS_v1/backend`:

```bash
TEAM360_ENV=dev uv run python -m modules.telchi.provisioning.ranking_cli --apply
uv run python -m modules.telchi.assistant.tests.live_product_monetary_ranking --output "$TELCHI_PRIVATE/product-monetary-ranking-live-final.json"
uv run python -m modules.telchi.provisioning.tests.publish_ranking_gates --evidence "$TELCHI_PRIVATE/product-monetary-ranking-live-final.json" --validations "$TELCHI_PRIVATE/ranking-validations-v1/validations.json" --output "$TELCHI_PRIVATE/product-monetary-ranking-gates-publication.json"
```

Usar paths nuevos al reproducir; los runners rehúsan sobrescribir evidencia. El registro DEV creó permiso y vínculo de catálogo, con backup privado, ledger y doble aplicación idempotente. Run administrativo: `2b5377e7-64ad-4f5e-8a7e-7586397e423d`. Cero asignaciones individuales y cero cambios a FULL_ACCESS.

Evidencia privada bajo `PRIVATE_ROOT`:

- `product-monetary-ranking-live-final.json`, SHA-256 `8cc0b6c53ab8e46fb4065bebb3bbc4e9c6421f79023ea43b3b0bdcaa12df1301`.
- `ranking-validations-v1/validations.json`: comandos focalizados completos, logs, resultados y hashes de cada archivo propio.
- `ranking-gates-20261020T172544671278Z/report.json`, SHA-256 `b9ea0e9b88f06ce1cec5195ba84c3033cf71089a1c1e0ba6ee46f475fe20976b`; manifiesto anterior respaldado. Seis garantías reejecutadas con source `8792126ca470011f1af5fa15da2fd58795270cb2919fa22267ab05f7d0f2609f`, sin modificar change-based.
- `product-monetary-ranking-live-r1.json`, `-r2.json`, `-r3.json`: fallos y evolución preservados.

Validación local: **323 passed** en 14 archivos focalizados de reader, contrato, continuidad, referencias, seguridad y provisioning; sin skips. `lat check md`, `lat check index`, `lat check sections`, `lat check code-refs`, `lat check` y `git diff --check`: exit 0. LAT advierte configuración semántica opcional ausente, sin fallar gates.

## Archivos propios y alcance

Cambios limitados a Telchi y evidencia de esta entrega; trabajo previo preservado. No se modificó Foundation, SAP, clasificación, Messaging, Console/RBAC compartido, infraestructura, frontend ni Presidencia.

Bajo `SrvRestAstroLS_v1/backend/modules/telchi/`:

- `datalake/product_line_amount_ranking_query.py`; `datalake/tests/test_product_line_amount_ranking_query.py`.
- `assistant/capabilities.py`, `business_categories.py`, `luna.py`, `handler.py`, `result_references.py`, `state_engine.py` (sólo vocabulario/tipo de métrica).
- `assistant/PRODUCT_MONETARY_RANKING_V1.md`, `assistant/README.md`.
- `assistant/tests/test_product_monetary_ranking.py`, `live_product_monetary_ranking.py`, `fixtures/product_monetary_ranking_incident.json`.
- `provisioning/ranking_repository.py`, `ranking_cli.py`, `tests/test_ranking_registration.py`, `tests/publish_ranking_gates.py`.
- `status_actual.md`; este reporte y `results.json`.

## Matriz de entrega y pendiente humano

PASS describe el alcance DEV demostrado. El único criterio final pendiente es la comprobación del owner en la conversación persistida real de WhatsApp, no sustituida por el clon HTTP.

```text
RANKING_CAPABILITY=PASS
MONETARY_RANKING_CONTRACT=PASS
TOP_5_FINISHED_PRODUCTS=PASS
TOP_10_CONTINUITY=PASS
RAW_MATERIAL_RANKING=PASS
PRODUCT_GRAIN_RECONCILIATION=PASS
RANKING_INTENT_PRESERVED=PASS
UNIT_PRICE_DISTINCTION=PASS
UNAVAILABLE_FORMATTER=PASS
PERSISTED_CONVERSATION_E2E=PASS
REAL_LUNA=PASS
FULL_ACCESS=PASS
RBAC_ISOLATION=PASS
SIX_GATES=VALID
RUNTIME_CHANGE_REQUIRED=YES
READY_FOR_MANUAL_WHATSAPP=YES
TESTS=323 passed; real persisted HTTP sequence and six current-code gates PASS
```

`PERSISTED_CONVERSATION_E2E` es el recorrido autenticado del clon exacto persistido, no ingress/delivery WhatsApp. Runtime registrado STOPPED; requiere carga manual del código mediante el launcher existente. No se arranca automáticamente. El owner debe comprobar la pregunta original en su chat persistido para aceptación funcional.

Preflight de host `BUSY_BUT_SAFE`: 8 cores, ~4,4 GiB disponibles, swap estable sin entradas/salidas en las muestras focalizadas. Presupuesto: un pytest, DuckDB 2 threads/512 MB, pool PG máximo 2, sin suites paralelas, browsers ni benchmarks generales. `RESOURCE_GUARD=PASS`, procesos ajenos terminados 0, abortos ambientales 0, procesos propios pendientes 0; pools cerrados y workers acotados finalizados.
