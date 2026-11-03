# TelchiAI — Category Sales Monetary V1 DEV

Implementación autorizada en `feature/console-backend-core`, 20/10/2026. Código y cálculo real verificados; activación BLOCKED por registro scoped pendiente. Sin modificación de permisos, Foundation, SAP ni servicios.

## Resultado empresarial

Foundation real reproduce las cifras, no constantes runtime. La paridad SQL independiente tiene diferencia cero en importes y conteos de ambas categorías.

| Septiembre 2026 | Importe BS | Productos | Líneas | Facturas |
| --- | ---: | ---: | ---: | ---: |
| RAW_MATERIAL | 839.582,63 | 34 | 526 | 495 |
| LAB_FINISHED_PRODUCT | 2.679.208,66 | 278 | 18.541 | 10.694 |

Cobertura documental observada: 1–24/09/2026; no certifica cierre mensual. Foundation `foundation_afd08d9eca6a725be53cdc3f9d5709c9`, snapshot 1408. Clasificación actual VALIDATED en ambas consultas, no membresía histórica.

La métrica es **Importe registrado en líneas comerciales**: facturas comerciales activas, descuentos propios reflejados en LineTotal, sin IVA de línea. No resta notas de crédito ni incorpora ajustes globales u otros componentes de cabecera. No equivale a neto documental ni monto cobrado; no se convierte con 1,13/0,87 ni se atribuye todo residuo a IVA.

## Implementación y seguridad

La nueva operación conserva el motor, contratos comerciales previos y autorización del handler. No importa runners investigativos desde runtime.

- Capability `sales.category_line_amount.v1`, permiso específico `telchi.sales.category_line_amount.read.v1`; nunca reutiliza el permiso monetario global.
- Intención V2 existente: categoría canónica, sales.net_amount y período explícito. La categoría se resuelve antes que producto/búsqueda/global. El intérprete conserva 2026 acreditado, no usa el reloj.
- Reader resuelve una publicación/snapshot, crosswalk de su reference y hash acreditado. Otra publicación o crosswalk requiere revisión explícita; no hay fallback a latest.
- Claves únicas, huérfanos, integridad de join, monedas y linaje comprobados antes de sumar. Sólo OINV/INV1 de SAP_B1_HANA, N, DocDate semiabierto. Mixtas aportan únicamente líneas de la categoría, sin cabecera ni cantidades físicas agregadas.
- VALIDATED y SUPPORTED se distinguen; SUPPORTED se explica. PROVISIONAL/UNKNOWN, monedas incompatibles y datos inválidos bloquean explícitamente; no se descartan silenciosamente. Ausencia de filas no acredita cero comercial.
- Comparaciones reutilizan resultados auditados autorizados, misma moneda, período, cobertura documental, definición, clasificación y fuente; no ejecutan otra consulta. Persistencia retiene categorías distintas del mismo período. EXPLAIN describe semántica sin consultar otros importes.
- El acceso efectivo y revocación se verifican en cada turno/referencia mediante el resolver existente. No implementa Presidencia, grants, roles nuevos, RBAC alternativo ni privilegios por título.

## Evidencia real y limitaciones

Se distinguen garantía de datos/modelo, pruebas de autorización y activación real; ninguna fixture se presenta como acceso efectivo del piloto a la nueva capability.

- [Foundation](foundation-r1.json): las dos categorías reales, procedencia, calidad, cobertura y límites completos.
- [Paridad independiente](parity-r1.json): SQL separado de aggregate, diferencia cero en ambas categorías y todos los conteos.
- [Luna actual](luna-r3.json): seis turnos PASS, OpenAI directo/gpt-5.6-luna, medium verificado, sin fallback. Pregunta directa → terminados → comparación → agosto → consumo → búsqueda textual. Importes proceden de Foundation real. El owner de la comparación es una fixture explícita, NO identidad autenticada; no certifica AUTH_PASS.
- [Primer intento](luna-r1.json): FAIL en agosto; se preserva. Diagnóstico acotado identificó una fila con moneda documental/precio distinta de BS en agosto, sin otros faltantes/linaje inválido en ese control. No se modificó el dato ni se convirtió. [Segunda corrida](luna-r2.json) verifica continuidad con bloqueo monetario explícito; r3 añade comparación real.
- Agosto mantiene categoría/período pero no ofrece una cifra: `category_currency_not_accredited`. El contrato conservador rechaza todo el período incompatible, incluso antes de atribuir líneas por categoría. Esto no acredita ausencia de ventas ni un importe cero.
- [Inventario DEV READ ONLY](access-r1.json): FULL_ACCESS scoped del piloto activo, ocho permisos efectivos previos, cero capabilities de categoría registradas y workspace ajeno vacío. La nueva operación no está autorizada efectivamente para el piloto todavía.
- PostgreSQL real con tablas TEMP/rollback: resolver dinámico FULL_ACCESS, revocación y aislamiento verificados sin filas operacionales modificadas. Tests de handler verifican permiso específico, denegación/revocación y tenant/workspace con fixtures; no sustituyen la activación real.

## Validaciones y causa raíz corregida

Tests focalizados, secuenciales y sin iniciar servicios. Las ejecuciones preliminares fallidas se describen para no convertirlas en PASS retroactivo.

1. SQL nuevo: 24 PASS iniciales (mixtas, segunda categoría, cero, moneda, parcial, provisional/desconocida, anuladas, duplicados, huérfanos, linaje y tipos/fuentes).
2. Recorrido focalizado ampliado: 252 PASS / 1 skip PostgreSQL opt-in, antes de cuatro regresiones adicionales de historial sin resultado. Sin cambios en contratos previos monetarios/productos/documentos.
3. Ejecución PostgreSQL opt-in inicial: 19 PASS / 1 FAIL. Síntoma: segundo cálculo después de recargar historial respondía ERROR. Causa confirmada: el nuevo dispatcher de acreditación llamaba `.get` sobre `execution_result=None` de un evento sin ejecución. Reproducción mínima devolvió AttributeError. Fix: verificar dict antes del dispatch; no modificar DB ni relajar validación. Regresión para None/dict vacío/lista/string.
4. Revalidación PostgreSQL real más tests nuevos: **34 PASS**, incluyendo reload de cálculo y resolver FULL_ACCESS. Conexiones/pool cerrados y tablas temporales eliminadas al cerrar; sin cambios de permisos operacionales.
5. Resultado final: **256 PASS / 1 skip opt-in**, más PostgreSQL real **34 PASS**. Gates documentales y hashes: [validations-final.json](validations-final.json); la [corrida previa](validations.json) se conserva. No Browser/E2E: esta tarea es backend y no acredita entrega WhatsApp.

Comandos desde backend (credenciales sólo del env local en proceso hijo, nunca impresas):

```bash
uv run pytest modules/telchi/datalake/tests/test_category_line_amount_query.py -q
uv run python -m modules.telchi.assistant.tests.live_category_line_amount --output ../../data/reports/telchi/category-sales-monetary-v1/luna-r3.json
uv run python -m modules.telchi.investigation.validation.business_categories_sales_v1.access_audit --output ../../data/reports/telchi/category-sales-monetary-v1/access-r1.json
```

Los tests opt-in usan `TEAM360_RESULT_REFERENCE_POSTGRES_TEST=1` y `TEAM360_FULL_ACCESS_POSTGRES_TEST=1`. El inventario investigativo se ejecuta como herramienta READ ONLY; no es dependencia de la implementación DEVELOPMENT.

## Archivos y alcance

Cambios limitados al módulo Telchi y su evidencia. Los archivos preexistentes untracked/editados se preservan; no se atribuyen sus cambios anteriores a esta tarea.

- `backend/modules/telchi/datalake/category_line_amount_query.py` y `datalake/tests/test_category_line_amount_query.py`: nuevos worker/contrato y tests SQL.
- `backend/modules/telchi/assistant/capabilities.py`, `business_categories.py`, `luna.py`: catálogo, permisos, formatter y comprensión.
- `backend/modules/telchi/assistant/handler.py`, `monetary_comparison.py`, `repository.py`: limitaciones, explicación y comparación autorizada con historial persistido.
- `backend/modules/telchi/assistant/tests/test_category_line_amount.py`, `live_category_line_amount.py`: nuevos tests y sonda real. `tests/test_business_categories.py`: expectativas actualizadas sin eliminar barreras incompatibles.
- `backend/modules/telchi/datalake/CATEGORY_LINE_AMOUNT_V1.md`, `assistant/README.md`, `status_actual.md`: contrato y estado local actualizados.
- `data/reports/telchi/category-sales-monetary-v1/`: evidencia nueva. Paths backend anteriores relativos a `SrvRestAstroLS_v1/`.

## Entrega y próximo paso

No se publica un manifest PASS sin autorización efectiva de la operación nueva. La conciliación contable incompleta no es el bloqueo; falta activación scoped.

```text
CATEGORY_CAPABILITY=BLOCKED
RAW_MATERIAL_SEPTEMBER=839582.63
RAW_MATERIAL_CURRENCY=BS
SECOND_CATEGORY_TEST=PASS
MONETARY_SEMANTICS=VERIFIED
FOUNDATION_COVERAGE=2026-09-01..2026-09-24; partial
FULL_ACCESS=FAIL (new capability not registered; existing grant preserved)
RBAC_ISOLATION=PASS (fixtures + existing real resolver TEMP; activation not certified)
REAL_LUNA=PASS (interpreter + Foundation; not authenticated new-capability runtime)
SIX_GATES=STALE
READY_FOR_MANUAL_WHATSAPP=NO
```

Próximo paso: confirmar ventana para registrar permiso/capability habilitada sólo en `telchi_dev` mediante procedimiento existente con backup/auditoría, sin otro grant al piloto ni cambio del resolver. La restricción de no modificar permisos se respetó. Después ejecutar pregunta por pipeline autenticado real y reacreditar sólo garantías DEV afectadas, change-based y sin vencimientos nuevos. Presidencia y notas de crédito permanecen fuera de alcance.

## Recursos y cierre

Host compartido BUSY_BUT_SAFE: ocho cores, load inicial 4,72, ~5,3 GB disponibles, swap ~2,2 GB estable en vmstat sin swap-in/out sostenido; luego load 2,26 y ~4,8 GB disponibles. Un runner a la vez, DuckDB dos threads/512 MB, sin spill, cero browsers.

```text
HOST_PREFLIGHT=BUSY_BUT_SAFE
RESOURCE_GUARD=PASS
CONCURRENCY_USED=1 runner; DuckDB threads=2
UNRELATED_PROCESSES_TERMINATED=0
ENVIRONMENTAL_ABORTS=0
OWN_PROCESSES_LEFT_RUNNING=0
```

Sin servicios iniciados/reiniciados, infraestructura, SAP, Foundation, clasificaciones, Meta, Evolution, Cloudflare, WhatsApp, commit ni push. Sin ventanas GLOBAL/SHARED nuevas ni modificaciones fuera del scope Telchi. READ ONLY para inventario operacional PostgreSQL; tests PG usan sólo tablas temporales. Los procesos ajenos permanecen intactos.
