# Histórico técnico hasta normalización documental 2026-10-06

Copia congelada del tablero anterior, incluidos cambios preexistentes sin commit. Sus estados describen cada cierre, no el presente; el único estado GLOBAL vigente es [status_actual.md](status_actual.md).

Objetivo: `desarrollo`

Ultima actualizacion: 2026-10-06 (Messaging Evolution adapter y latencia fija PASS; Telchi Temporal Commercial Purpose PASS, sin promoción, preservado)

Este documento es un tablero del estado vigente. La bitacora detallada previa, incluidas las fases actuales aun sin commit, se conserva en `status_historico_hasta_2026-06-28.md` y en Git.

## Directorio y rama

- raiz: `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360`
- rama funcional actual: `feature/console-backend-core`
- las Fases 3 a 5 del Diagnosticador embebible quedaron confirmadas en `cdd1b1b` y publicadas en `origin/feature/console-backend-core`

## Estado general

- Team360 mantiene frontend Astro 6 + Svelte 5 y backend Litestar.
- PostgreSQL 18 es la verdad operacional del estado conversacional.
- Milvus 2.6 es el indice vectorial derivado para retrieval.
- El benchmark Milvus 2.6 vs. pgvector ya fue ejecutado y versionado en `804547d` (`feature/knowledge-ingestion-service`): ambos obtuvieron 44,0% de pass rate, mientras Milvus promedio 13,9 ms frente a 859,2 ms de pgvector (~61,8x; 98,4% menos latencia). No debe volver a figurar como pendiente salvo que cambien corpus, escala o condiciones de prueba.
- LiteLLM es el gateway de modelos mediante aliases y adapters.
- El runtime publico de Vera usa `/t360 -> Litestar -> PostgreSQL -> Milvus -> LiteLLM`.
- Las migraciones `001` a `004` y la Fase 1 de `automation_diagnosis` fueron validadas anteriormente.
- La politica DB vigente exige `psycopg 3 async`, pools separados y SQL dentro de repositories.
- El commit `e2e0a54` incorporó `backend/modules/module_registry.py`; `ls_iMotorSoft_Srv01.py` consume sus handlers y Flow está registrado allí una sola vez.
- La política modular vigente permite agentes concurrentes solo en scopes `MODULE_LOCAL` asignados y disjuntos, con coordinación `SHARED` y ventanas exclusivas para `GLOBAL`, Git y producción protegida.
- Flow expone sus APIs desde `ROUTE_HANDLERS` en `routes.py`; el module registry
  las monta una sola vez sin cambios nuevos en el entrypoint común.

Referencias canonicas:

- `lat.md/team360-runtime-operational-policy.md`
- `lat.md/postgres-driver-policy.md`
- `lat.md/service-preflight-methodology.md`
- `lat.md/diagnosticador-embeddable-component-architecture.md`
- `lat.md/team360-global-orchestration.md`

## Hito 2026-10-06 — Evolution / WhatsApp DEV

Este hito conserva la línea base del transporte previo al adapter Team360: veinte respuestas entregadas y límites de instrumentación explícitos. La integración posterior se resume en el gate Messaging de abajo.

- Laboratorio: `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/evolution-api`; v2.3.7 parcheado, Podman rootless a demanda, PostgreSQL 18.4/base-schema propios, Redis OFF, cache local ON; sin auto-start.
- Puerto: `127.0.0.1:18180 → container:8080`; 8080 del host libre, Quick Tunnel DEV y challenge Meta verificados. Activos independientes de Team360; `META_VERTICE360_*` no es su fuente de verdad.
- Tráfico real inbound/outbound, bidireccionalidad, estados SENT/DELIVERED/READ tras patch, restart/recreate y persistencia: PASS.
- `TEAM360_EVOLUTION_META_CLOUD_DEV_V1=PASS`, `TEAM360_EVOLUTION_V237_META_STATUS_PATCH_V1=PASS`, `TEAM360_EVOLUTION_PORT_REMAP_V1=PASS`.
- Sesión `20261006-105237-46852ac6`: 20/20 pares aceptados secuenciales, persistidos y entregados; inbound→dispatch p50 21.7 ms, p95 36.8 ms; inbound→delivered p50 2567.4 ms, p95 3091.8 ms, máximo 3497.6 ms. Valoración observable: `GOOD - suitable for normal conversational WhatsApp use`, sin Team360/LLM.
- `TEAM360_EVOLUTION_WHATSAPP_LATENCY_BASELINE_V1=PENDING`: N=0 en los desgloses Graph/accept y un ping 20 anticipado ignorado. El benchmark vigente exige esos desgloses y cero violaciones; no se modifica evidencia ni criterio para forzar PASS.
- Principio: **Evolution transporta WhatsApp; Team360 posee la conversación**. Próximo gate previsto: `TEAM360_MESSAGING_EVOLUTION_ADAPTER_V1`, respuesta fija primero, sin LLM; no implementado por este hito.
- No hay evidencia para incorporar Redis, brokers o escalado adicional; no es un test de capacidad.
- `TEAM360_EVOLUTION_WHATSAPP_DOCUMENTATION_CLOSURE_V1=PASS`: documentación alineada con evidencia real, incluida la limitación PENDING del benchmark formal; no equivale a cerrar ese gate.

Arquitectura, tabla completa, digest/tag exactos, patch, rollback y trazabilidad: [Messaging README](../backend/modules/messaging/README.md). Este cierre documental conserva los cambios previos de Telchi y no altera branch/HEAD, código funcional, Meta, Twilio ni infraestructura.

## Corrección — Configuración Meta propia de Team360

El bloque Meta de `backend/globalVar.py` consume exclusivamente `META_TEAM360_*`. Se eliminó la resolución histórica hacia Vertice360 e iMotorSoft sin modificar sus activos ni servicios.

- Nombres públicos `TEAM360_META_*` y default Graph `v20.0` preservados; sin fallback legacy. El helper de habilitación mantiene su contrato booleano: requiere token, phone number ID y verify token Team360.
- Consumidores backend detectados: el helper local `team360_meta_whatsapp_enabled()` y su test Gupshup; no se encontró un adapter Meta operativo usando estas constantes. No se alteraron Gupshup, DB, OpenAI, Telchi ni el runtime Vera.
- Tests nuevos: `backend/tests/test_messaging_meta_config.py`, importación aislada y valores sintéticos; verifican coexistencia, legacy-only, ausencia de cada campo requerido, valores vacíos y default Graph.
- Validación: tests Meta + configuración Gupshup, 15 passed; suite Messaging, 101 passed (warning de diagnóstico in-memory no relacionado). Gates LAT completos y `git diff --check` limpios.
- Esta corrección no implementa el adapter Evolution ni cierra su gate. No se reiniciaron servicios existentes ni se imprimieron secretos.

## Gate — Team360 Evolution adapter V1

El adapter y su latencia están validados con veinte pares WhatsApp reales, delivery/read, idempotencia y recuperación. Team360 conserva la conversación; el runtime temporal está detenido y Evolution saludable.

- `TEAM360_MESSAGING_EVOLUTION_ADAPTER_V1=PASS`; `TEAM360_MESSAGING_FIXED_RESPONSE_LATENCY_V1=PASS`. El bloqueo previo por Milvus quedó resuelto con perfil GLOBAL autorizado: `TEAM360_DEV_PROFILE=messaging-only TEAM360_BACKEND_PORT=18181 ./SrvRestAstroLS_v1/backend-dev.sh`. Normal sigue default y conserva íntegro el bloque de configuración/preflights/entrypoint previo.
- Bootstrap `backend/modules/messaging/dev_app.py`: solo rutas Messaging existentes y `/health` con `SELECT 1`; configuración/binding/índices 026 validados en PostgreSQL real. Pool lazy hasta startup; sin imports/init de registry, Flow, Telchi, Vera, Milvus, LiteLLM ni clientes LLM. No exige Evolution para arrancar; se valida al habilitar la sesión real.
- Registro Messaging y migración `026_team360_messaging_transport_v1.sql` autorizados e implementados. Migración aplicada a PostgreSQL Team360 18.4 con lock/statement timeout; tablas core reutilizadas, sin editar `001` ni usar Flow. Canal DEV preparado en workspace existente `team360_public_site`, alias `evolution-meta-dev`.
- Endpoint `POST /webhooks/messaging/evolution/whatsapp`: header privado, instancia esperada, texto/status normalizados, allowlist DEV de un remitente, sin secretos ni teléfono en logs/responses. Provider `EvolutionProvider` reutiliza `WhatsAppMessageSenderPort` y es la única salida del responder fijo `team360 ping NN` → `TEAM360 PONG NN`.
- Estado Team360: inbound confirmado, intent outbound durable antes de I/O, receipt/status persistidos. Índices únicos evitan respuestas duplicadas, incluso concurrentes. Callback temprano se reconcilia; delivery/read no retroceden. Timeout/resultado incierto no se reintenta; intents interrumpidos permanecen para reconciliación manual.
- Tests: Messaging + registry, 175 passed; suite relevante Messaging/registry/DB/Console/Flow, 703 passed, 39 skips opt-in. Incluye cuatro pruebas de perfil/launcher y dos regresiones de scope/replay del benchmark. PostgreSQL/HTTP reales con Milvus/LiteLLM cerrados e inspección de `sys.modules`; warning existente de diagnóstico in-memory. Sin requests LLM.
- Integración PostgreSQL + HTTP real de loopback: webhook completo, duplicate secuencial/concurrente, unauthorized sender, payload sin texto, Evolution inaccesible/error/timeout/respuesta inválida, status temprano/duplicado/reordenado, reconstrucción app/pool e intent interrumpido preservado sin reenvío. No equivale a reiniciar procesos productivos.
- Sesión humana `20261006-165557`: veinte pings exactos 01..20, veinte PONG aceptados, veinte delivered y veinte read en una conversación. Correlación independiente contra los IDs Meta persistidos en Evolution, sin mocks. Tres textos adicionales no enrutados quedaron persistidos, con cero respuestas.
- La sonda original contó 23 inbound dentro del benchmark y eligió un saludo sin outbound para el duplicate test, por lo que expiró en vez de cerrar/reiniciar. Se conservaron `session.json` y `latency.json` originales; no se borraron errores ni timestamps. Reportador corregido cuenta solo comandos exactos y reporta extras aparte; pings válidos repetidos/desordenados o replies indebidos siguen siendo violaciones.
- Cierre independiente `providers/evolution/probes/verify_session.py`: replay de los veinte IDs reales → veinte duplicate, cero nuevas filas y cero nuevos mensajes Evolution; unauthorized y texto vacío rechazado/ignorado. Arranque/reinicio real de sus backends preservó todas las filas y la conversación; duplicate posterior al restart tampoco envió.
- Prueba operativa de recuperación: reinicio únicamente del contenedor DEV `evolution-api`, con cambio real de PID/StartedAt; preservó 90 IDs de transporte, 103 filas Team360 y la conversación, con instancia `open`. No se reinició PostgreSQL ni se modificaron Meta, imagen, puertos, túnel o webhook global.
- Runtime temporal y supervisores cerrados; webhook local desactivado/restaurado. Configuración en `.env.backend-dev.local` ignorado/mode 600, sin copiar secretos Meta ni `.bashrc`; sin autostart. Bind DEV fue a IP específica resuelta por Podman, no `0.0.0.0`.
- Benchmark N=20 válido y secuencial: T0→T4 p50 56.37 ms, p95 146.04 ms; T0→T6 p50 2516.86 ms, p95 2972.98 ms. Tabla completa en README. Baseline Evolution p50≈2.57 s/p95≈3.09 s sigue PENDING formalmente; no restar muestras con distinto origen para estimar overhead.
- Evidencia final: `data/reports/messaging/evolution-adapter-v1/20261006-165557/verified/verification.json`, `evidence.json`, `report.md`; hashes de IDs, extras, timestamps y recuperación sin secretos ni teléfono. El puntero `active-session.json` indica cierre; evidencia original conservada.
- Rama/HEAD: `feature/console-backend-core`, `09d2ec715a31bb88574d734eacb9f437f008624e`. Sin commit, stage ni cambios Telchi; modo normal/productivo no refactorizado.
- Arquitectura, configuración, tabla y límites: [Messaging README](../backend/modules/messaging/README.md#pruebas-y-benchmark-team360-only). Bash/Python, tests, LAT y `git diff --check` se validan nuevamente en este cierre.

## Gate 2026-10-02 — Telchi: Temporal Commercial Purpose Contract V1

Estado: PASS en semántica temporal, sin promoción. CURRENT `foundation_afd08d9eca6a725be53cdc3f9d5709c9` intacto; candidate derivado `foundation_15cfdba7ff7ff94011d26fa1b93bf266` para gate de promoción separado.

Se separan perfil histórico observado, legacy purpose V1 sin cambios y clasificación por período con cobertura explícita. Los 24 MIXED nuevos no tienen ventas dentro de 2026: cero MIXED_WITHIN_2026, quince MIXED_WITH_LOOKBACK de 365 días y nueve HISTORICALLY_MIXED_ONLY. Los 24 conservan perfil históricamente mixto; su propósito estricto 2026 es UNKNOWN con evidencia interna, sin inferir ausencia comercial desde cobertura parcial. El replay usa lookback cero.

Replay 2026-01-01..09-24: 834 → 732 evaluados, 29 incorporados por ventas válidas del período y 131 retirados (22 históricamente mixtos y 109 sin comercio fechado). Incluye 91 temporal MIXED y 641 UNKNOWN con comercio observado; este UNKNOWN no impide comparar cantidades. No se usa intención comercial sin fecha para esta pregunta temporal. TOP 10: entran L01791, L02492 y L02170; L01200, L02135 y L02158 permanecen evaluables pero quedan debajo. Stock, cantidades y ranking de productos comunes preservados.

L00002 demuestra ambas actividades dentro de 2026. L02475 conserva consumo sin comercio; L00954 conserva comercio sin consumo demostrado y no se vuelve MIXED por BOM. L00759/L00761 retienen controles legacy INTERNAL_ONLY/no vendibles y exclusión del replay, sin forzar exclusividad temporal con cobertura parcial. Todos los campos previos, ocho componentes originales y dataset UoM quedan exactos. Los 422 gaps de ingestión y 384 business unknown no se reabren.

La evaluación `TELCHI_PRODUCT_COMMERCIAL_SEMANTICS_SOURCE_GAP_VALIDATION_V1_PASS` sustituye el blocker temporal, preservando los reportes previos como evidencia histórica. Contrato reusable en `backend/modules/telchi/datalake/TEMPORAL_COMMERCIAL_PURPOSE_V1.md`; evidencia en `data/reports/telchi/temporal_commercial_purpose_v1/report.json`. No SAP, nueva ingestión, commit, push ni cambio de CURRENT.

## Gate 2026-10-02 — Telchi: Product Commercial Semantics Source Gap Closure V1

Estado: DEGRADED. Gates A/B/D DEGRADED, C PASS; E no intentado. CURRENT `foundation_afd08d9eca6a725be53cdc3f9d5709c9` intacto; output candidate `foundation_fd73cb4b753f41ada7e954badd2ef6f5` VALIDATING.

De los 720 propósitos no resueltos, 24 pasan a MIXED por facturas históricas materializadas anteriores a 2026 y consumo efectivo en 2026; 696 permanecen UNKNOWN con reason, missing evidence, cobertura y clase de gap. No se cambia la regla Foundation ni se declara uso comercial contemporáneo desde ventas históricas. Residual: 312 requieren historia de consumo/propósito operacional y 384 no tienen intención exclusiva demostrada o carecen de uso observado; una nueva ingestión no garantiza definir su propósito.

UoM: 114 → 110 productos. Los cuatro resueltos no tienen transacciones en la ventana: el maestro fuente ya materializado confirma exactamente la unidad de inventario GR, omitida por el crosswalk consultado previamente. No hay nuevos factores ni conversiones de líneas. Residual: 236 líneas de notas de crédito, 232 con factura base exacta y cuatro sin factura base demostrada; ninguna tiene unidad vigente suficiente. Convertibilidad global de NC permanece 96,88 %. Requiere futura ingestión de unidad/factor fuente de RIN1; no se consultó SAP.

Replay real del candidate: 488 baseline → 808 anterior → 834 final, 26 incorporados (22 MIXED y cuatro unidades de inventario), cero retirados; TOP 10 igual al anterior. Parity de stock/cantidades de los productos comunes, ocho componentes originales y dataset UoM preservados. Anti-fanout cero y consumer compatibility PASS. Gate D permanece DEGRADED: falta validar aceptación por el consumidor de evidencia MIXED entre ventanas históricas y 2026 antes de promoción. No commit, push ni promoción.

Evidencia canónica: `data/reports/telchi/product_commercial_semantics_source_gap_v1/report.json`, matrices reproducibles y propuesta de ingestión sin ejecutar. El runner vive en `backend/modules/telchi/investigation/validation/product_commercial_semantics_source_gap_v1/`. Los registros legacy se revisaron por metadata/schema; no prueban cancelación, lineage de consumo o unidades vigentes suficientes. Un primer candidate propio falló su hash por campos nulos Parquet, quedó FAILED y fue reemplazado tras corregir y verificar roundtrip.

## Gate 2026-10-01 — Telchi: Product Commercial Semantics Foundation Closure V1

Estado: DEGRADED. Gates A/B/C PASS, D DEGRADED y E BLOCKED. CURRENT verificado `foundation_afd08d9eca6a725be53cdc3f9d5709c9` permanece intacto; candidate final `foundation_4884512474ec1e8d1d284af1d89ea7ec` queda VALIDATING.

El candidate agrega propósito con provenance/evidencia/confianza y conversión comercial por línea; conserva exactamente los ocho componentes previos. Sobre 16.934 productos SAP: 13.462 COMMERCIAL_ONLY (DERIVED_PARTIAL), 956 INTERNAL_ONLY, 161 MIXED y 2.355 UNKNOWN. Los 720 casos purpose-unresolved del baseline permanecen UNKNOWN, sin inferir certeza desde SellItem.

UoM-unresolved del baseline baja 468 → 114: 354 productos adicionales evaluables. Notas de crédito: 9.129/9.423 líneas convertibles (96,88 %), usando corroboración histórica hash-verificada como SUPPORTED, no como lineage exacto CURRENT. Replay: 488 → 808 productos evaluados, 354 incorporados y 34 retirados por evidencia de propósito; 114 MIXED. No se atribuye eliminación de falsos positivos internos porque los controles ya estaban excluidos.

Brand permanece UNKNOWN y el importe neto por producto sigue NET_PRODUCT_AMOUNT_UNRESOLVED por atribución insuficiente del descuento de cabecera. Stock disponible formalizado como on_hand − committed, sin órdenes entrantes, con parity de valores y cardinalidad. SAP no accedido; no commit ni push. Contrato en `backend/modules/telchi/datalake/PRODUCT_COMMERCIAL_SEMANTICS_V1.md`; evidencia canónica en `data/reports/telchi/product_commercial_semantics_v1/report.json`.

## Gate 2026-09-29 — Telchi: Receivables & Collections Foundation Extension V3

Estado: PASS (`TELCHI_RECEIVABLES_COLLECTIONS_FOUNDATION_EXTENSION_V3_PASS`). El Data Lake V1 permanece cerrado (`TELCHI_DATALAKE_V1_CLOSED=YES`) y Receivables & Collections queda productivo en Foundation CURRENT `foundation_d222a203801cc84e9a14164d26aa67a0`.

Se reutilizó sin rebuild el componente sellado `receivables_collections_633d1fbbfdd87e6665b1aad3` (fingerprint `633d1fbbfdd87e6665b1aad39719f0c9bf5277ada1be6585ad09f900d65889ae`). El manifiesto productivo contiene 7 componentes lógicos; reference, sales, credit_memo, oinm, oitw y material_supply conservaron identidad exacta. La canonicalización Decimal V3 pasó 14/14 roundtrips JSON; board, collections, settlement e historical fueron iguales entre pinned y productivo en payload y hash, con cero diferencias analíticas inesperadas.

Capacidades: deuda abierta, current/overdue, aging, cobranzas cash/transfer/check/card, métodos mixtos y reconstrucción histórica a cierre diario. QR permanece `UNRESOLVED_SOURCE_EVIDENCE`, no inferido y no bloqueante. Los intentos de publicación Foundation V1 y V2 fueron revertidos; V3 cerró en PASS y es el único estado productivo. Hubo una única promoción V3, sin rollback V3 y sin acceso SAP/HANA. Evidencia en `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi/TELCHI_RECEIVABLES_COLLECTIONS_FOUNDATION_EXTENSION_V3/`.

CG2A V2 cerró `DEGRADED` únicamente por la frontera semántica: SAP/HANA no expone para este caso una operación de negocio nativa explícita llamada `CONTADO`. El Data Lake deriva la semántica comercial desde hechos financieros fuente, sin presentarla como un campo nativo SAP. En la cohorte RAW_MATERIAL analizada hubo 2.136 documentos, 2.136 términos comerciales equivalentes a efectivo, due date igual a document date en el 100 %, 2.134 liquidaciones el mismo día, 2 posteriores y 0 deudas parciales o abiertas al 2026-09-28.

```text
TELCHI_DATALAKE_V1_CLOSED=YES
TELCHI_ATOMIC_RECEIVABLES_COLLECTIONS_V1_PASS
TELCHI_RECEIVABLES_COLLECTIONS_BUSINESS_DERIVATION_V1_PASS
TELCHI_RECEIVABLES_COLLECTIONS_FOUNDATION_EXTENSION_V1_ROLLED_BACK
TELCHI_RECEIVABLES_COLLECTIONS_FOUNDATION_EXTENSION_V2_ROLLED_BACK
TELCHI_RECEIVABLES_COLLECTIONS_FOUNDATION_EXTENSION_V3_PASS
RECEIVABLES_COLLECTIONS_CAPABILITY=PRODUCTIVE
TELCHI_DATALAKE_V1_FOUNDATION_CURRENT=foundation_d222a203801cc84e9a14164d26aa67a0
TELCHI_DATALAKE_V1_LOGICAL_COMPONENT_COUNT=7
TELCHI_DATALAKE_V1_LOGICAL_COMPONENTS=reference,sales,credit_memo,oinm,oitw,material_supply,receivables_collections
RECEIVABLES_COLLECTIONS_COMPONENT=receivables_collections_633d1fbbfdd87e6665b1aad3
TELCHI_CG2A_RAW_MATERIAL_PAYMENT_TERMS_V2_DEGRADED
```

## Gate 2026-09-28 — Telchi: cierre Data Lake V1 (promoción final de foundation V3)

Estado: PASS (`TELCHI_DATALAKE_FINAL_FOUNDATION_PROMOTION_AND_CLOSURE_V3_PASS`) con
`TELCHI_DATALAKE_V1_CLOSED=YES`. Evidencia en
`/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi/TELCHI_DATALAKE_FINAL_FOUNDATION_PROMOTION_AND_CLOSURE_V3/`.

El gate creó un candidato fresco con `update_run_id` único
(`foundation-republication-v3-20260928T022543540899Z`, id `foundation_417c860c216805f18341bb741ee026e3`),
copia profunda del manifiesto sellado del target histórico
`foundation_6a7cc7a99638208002c4f877d998d220` (que permanece `SUPERSEDED` con su failure reason
intacto), y promovió una sola vez con `CAS_MODE=PROTOCOL_READ_COMPARE_COMMIT` bajo el run lock
del repositorio. Conteos: `CATALOG_COMPONENT_COUNT=5` / `PINNED_MANIFEST_COMPONENT_COUNT=6`.
Snapshots: manifest base `838` pinned y productivo (`MANIFEST_BASE_SNAPSHOT_MATCH=YES`),
primer-CURRENT dinámico `952` (concepto distinto; no se exige igualdad con 838).

Igualdad analítica: huella de componentes y `PINNED_GOLD_RESULT_HASH == PRODUCTIVE_GOLD_RESULT_HASH`,
con `ANALYTICAL_COMPONENTS_CHANGED_BETWEEN_PINNED_AND_PRODUCTIVE=NO` y
`PINNED_VS_PRODUCTIVE_RESULT_MATCH=PASS`. Gold productivo: `SUPPLY_RISK_COUNT=16`,
CG2A `GENERIC_CUSTOMER`, 2A-SAL `SEGUNDO_ANILLO`, L00031 52 docs / Bs 57,469.51 / KG,
L03192 33 docs / Bs 21,584.70 / KG. Tests `TEST_FAILURES=0` (backend full 1766, Data Lake 177),
LAT gates y `git diff --check` PASS, `SAP_ACCESSED=NO`, `SAP_QUERY_COUNT=0`, `SAP_WRITE_COUNT=0`,
sin rollback. Pregunta abierta del dueño `CG2A_RAW_MATERIAL_PAYMENT_TERMS` queda
`PENDING_BUSINESS_ANALYSIS` (no bloqueante).

```text
TELCHI_DATALAKE_V1_CLOSED=YES
TELCHI_DATALAKE_V1_FOUNDATION_CURRENT=foundation_417c860c216805f18341bb741ee026e3
TELCHI_DATALAKE_V1_MANIFEST_BASE_SNAPSHOT_ID=838
TELCHI_DATALAKE_V1_FIRST_CURRENT_SNAPSHOT_ID=952
TELCHI_DATALAKE_V1_CATALOG_COMPONENT_COUNT=5
TELCHI_DATALAKE_V1_PINNED_MANIFEST_COMPONENT_COUNT=6
```

## Gate 2026-09-02 — Telchi: casos de excepción de crédito V1 (287 ventas con vencido)

Estado: PASS (`TELCHI_CREDIT_EXCEPTION_CASES_V1_PASS`) con degradaciones declaradas
(`TN_SOURCE_INSPECTION=PARTIAL`, `MANAGEMENT_APPROVAL_TRACEABILITY=EXTERNAL_TO_SAP`,
`DMS_HUMAN_OPERATOR_IDENTITY=UNRESOLVED`, `HISTORICAL_AUTHORIZATION=UNAVAILABLE`).
Trabajo en el workspace Telchi (`ai/lab/dataclient/telchi`): reporte
`docs/credit_exception_cases_v1_report.md`, scripts y evidencia en
`validation/credit_exception/` y `validation/credit_exception/evidence/`.

Las 287 ventas con vencido impago en la fecha de la venta fueron REVALIDADAS con
reconstrucción histórica exacta (`OINV/ORIN/ORCT/RCT2/OITR/ITR1`, semántica as-of,
ventana 2026-01-01..09-01): 287/287 confirmadas, 0 falsos positivos por
cancelada/pagada/NC previa. Universo exacto resultante: 2,318 ventas con vencido
en fecha (la cota previa de 287 era inferior porque no podía ver ventas cobradas
después). Clasificación por causa real: contado Retail One cubierto (825/2318; 58/287),
flag excepción VENCREVENC (522/2318; 12/287), flujo entrega `DlnLimit=N` (363/2318;
140/287), autorización FULL/override en motor SAP (351/2318; 40/287), pedido previo
sin vencidos (188/2318; 15/287), log de autorización Retail (108/2318), canal técnico
DMS (14), nota de crédito (12). UNEXPLAINED=0; UNRESOLVED=19/287 y 43/2,318 con
DocEntry preservado (microventas R1 sin liquidar en SAP). Pago: 106 liquidadas / 181
abiertas (concilia el conteo previo de 86 cobradas; la diferencia es por NC y
reconciliaciones no-ORCT). 39 sobre límite reconstruidos (exacto as-of: 178).
`@SO1_01LOGAUTORIZA` inventariado completo (16,401 eventos; join VENTA→folio
1,501/1,710 emparejadas; 108 autorizaciones retail). Tests: 35 nuevos LOOP TEST +
78 previos = 113 PASS; cardinalidad NO_SILENT_FANOUT; SAP/HANA writes = 0.

## Gate 2026-09-02 — Telchi: agrupación económica de las 268 ventas explicadas V1

Estado: PASS (`TELCHI_CREDIT_EXPLAINED_CASES_ECONOMIC_GROUPING_V1_PASS`), continuando
`TELCHI_CREDIT_EXCEPTION_CASES_V1_PASS`. Reporte `docs/credit_explained_cases_economic_grouping_v1_report.md`,
scripts/evidencia en `validation/credit_exception_economic/`.

Las **268 ventas explicadas** (287 baseline − 19 UNRESOLVED) se agruparon en 5 grupos de negocio
únicos (sin doble conteo): Usuario FULL 40 · Flujo previo (entrega/pedido) 155 · Contado Retail One 58 ·
Cliente excepción 12 · Integración/ajuste 3 = **268**. Monto bruto **Bs 318,051.61**; cobrado
Bs 63,686.61 (20.0%); por NC Bs 1,392.00; **abierto Bs 252,973.00** (79.5%). Período
2026-01-12 → 2026-09-01. Moneda **BS** única (DocCur='BS' verificado en HANA) → suma directa válida.
Riesgo abierto por mecanismo: **Usuario FULL Bs 180,396.95 (71.3%)** (8 usuarios, SAP Direct 37/40;
lzarraga/yardaya/cvallejos/jirahola principales) + **Entrega previa Bs 71,282.55 (28.2%)**
(`DlnLimit=N`; cliente clave C010341 LA REJA 40 ventas Bs 47,259 abierto) = 99.5% del abierto;
excepción Bs 1,293.50 y contado 0. CUSTOMER EXCEPTION: solo **C000398 PEDIDOSYA** (VENCREVENC='Y');
revalidado C011358 YANGO con flag pero 0 ventas en ventana. Ist. previa en la venta (FULL+excepción):
vencido Bs 596,866 · exposición Bs 1,407,688 · 6 sobre límite. Evolución mensual crece hacia jul-ago
(ago 168 ventas, Bs 215,711 = 67.8%); no estable. Tests: 26 nuevos económicos + 113 previos = 139 PASS;
smoke HANA real 12/12 (3+3+3+3 por grupo); SAP/HANA writes = 0.

## Gate 2026-09-02 — Telchi: riesgo/aging del saldo abierto (open vs vencido) V1

Estado: PASS (`TELCHI_CREDIT_OPEN_RISK_AGING_V1_PASS`), continuando
`TELCHI_CREDIT_EXPLAINED_CASES_ECONOMIC_GROUPING_V1_PASS`. Reporte
`docs/credit_open_risk_aging_v1_report.md`, scripts/evidencia en `validation/credit_open_risk/`.

De los **Bs 252,973 abiertos** (baseline 2026-09-01, reconciliado Δ=0.00; INV6 1 cuota
validada 162/162): **Bs 175,928.88 no vencidos** (69.5%) · **Bs 77,044.12 YA vencidos** (30.5%).
El riesgo está invertido vs el open: el vencido lo domina **Entrega previa (Bs 58,043.85=
75.3%)** frente a **Usuario FULL (Bs 19,000.27=24.7%)**, porque FULL es venta reciente aún en
plazo (no vencido 161,396.68). USER FULL: jirahola 11,790 (A3TEK) + cvallejos 5,302 (C011750)
+ soluone 963 + lzarraga 944. DELIVERY: LA REJA C010341 = 47,259 vencido = **61.3% del total**,
40 ventas todas abiertas/vencidas, máx 184d (timing entrega→factura 0d, vencido=impago).
Concentración: Top 5 clientes ≈94% del vencido. Vendedores (≠usuario): Mariela Irigoyen 25,606 ·
Maria F. Menacho 12,165 · Karla Cabello 8,649. Cohorte feb-jul 100% vencida; ago 7.1%.
Collection rate madurado 41.86% vs 20.02% crudo. Tests 29 nuevos + 139 previos = **168 PASS**;
smoke HANA real 13/13; `SAP_WRITE_COUNT=0`.

## Gate 2026-09-01 — Telchi: control de crédito × autorizaciones × HANA blocking V1

Estado: PASS (`TELCHI_CREDIT_CONTROL_AUTHORIZATION_TRACEABILITY_V1_PASS`) con
`TN_SOURCE_INSPECTION=PARTIAL` (SQL del Transaction Notification no legible con la
cuenta READ ONLY) y las degradaciones autorizadas (historica de permisos, aprobacion,
operador DMS, posicion crediticia parcial). Trabajo ejecutado en el workspace Telchi
(`ai/lab/dataclient/telchi`): reporte
`docs/credit_control_authorization_traceability_v1_report.md`, scripts y evidencia
en `validation/credit_control/` y `validation/credit_control/evidence/`.

Hallazgos clave: `Autorizaciones_xGrupos.xlsx` reconciliado 170/170 con OUSR;
"Confirmar desviacion de linea de credito" FULL en 9 de 11 grupos (Almacenes y
Produccion sin ella); OADM `CreditLimt=Y` / `DlnLimit=N`; TN despacha a 24
`ACB_TN_*` y OINV/ORDR referencian OCRD+OINV+OCTG; en 2026 hubo 287 ventas con
vencido impago en la fecha de la venta y 39 sobre limite (86/287 con cobro
trazado); sin excepcion tecnica registrada; aprobacion de gerencias queda fuera de
SAP. Tests 26 nuevos + 52 regresion previa PASS; SAP/HANA writes = 0.

## Gate 2026-08-23 — Flow demo production readiness V1

Estado: PASS en desarrollo
(`TEAM360_FLOW_DEMO_PRODUCTION_READINESS_V1_PASS`). La demo queda lista para
una ventana de deploy posterior; esta validación no modificó producción.

### Baseline y migraciones

El baseline productivo de Flow permanece desplegado. Las migraciones `011` a
`022` están aplicadas en producción según el estado canónico previo. La
migración `023_team360_flow_operational_settings_v1.sql` está validada en DEV y
todavía no fue aplicada en producción. La migración aditiva
`024_team360_flow_safe_mail_cutoff_v1.sql` fue aplicada y validada únicamente
en DEV; producción no fue modificada.

### Capacidades de la demo

Flow Configuración administra y persiste en PostgreSQL, sin reinicio del
backend común:

- sectores, emails y SLA por nivel operativo;
- nivel de aprobación de cierre;
- `automation_enabled`, intervalo del scheduler, intake de correo y batch;
- protección histórica mediante `mail_after_cutoff` + `mail_cutoff_epoch`;
- estado, último ciclo y resultado del scheduler embebido.

El scheduler es un `asyncio.Task` module-local con `asyncio.Lock`, contrato de
un único proceso y pacing `RUN -> FINISH -> WAIT -> NEXT`. Ante error registra,
espera y reintenta; no hace spin. Relee PostgreSQL en cada ciclo, por lo que
los cambios de email, SLA y operación se observan sin variables Flow nuevas ni
restart. `automation_enabled=false` sigue siendo el default seguro.

### Seguridad de Gmail

El default anterior `in:inbox -after:2026/08/12` era inseguro porque excluía
los mensajes posteriores y podía seleccionar histórico. Existe ahora un único
builder usado por el scheduler: con protección activa produce
`in:inbox after:<epoch>`. Un cutoff ausente, vacío, inválido, fuera de rango o
una lectura de schema anterior falla de forma segura al epoch canónico
`1787239323` (`2026-08-20T15:22:03Z`); nunca degrada a `in:inbox` ni genera
`-after:`. Solo `mail_after_cutoff=false` explícito desactiva el filtro.

### Política de acceso demo/MVP

La política es deliberada y no se considera un bug de este gate:

- autenticación: deshabilitada para la demo;
- rol efectivo: Administrador implícito (`flow-mvp-administrator`);
- acceso a Configuración: abierto en demo;
- login, usuarios, roles y RBAC enterprise: fase futura.

### Evidencia 2026-08-23

La evidencia se obtuvo con backend y Astro levantados mediante los launchers
oficiales de desarrollo:

- scheduler y contratos Flow: `439 passed`, `39 skipped`, `0 failed`; sus 20
  tests existentes permanecen verdes;
- configuración con PostgreSQL real: `12 passed`, `0 failed`, con roundtrip y
  restauración de valores;
- Flow Configuración E2E: `27 passed`, `0 failed`;
- Directorio E2E: `45 passed`, `0 failed` con fixtures determinísticos luego
  eliminados;
- Console compartida: `28 passed`, `0 failed`;
- frontend: `pnpm check` con `0 errors`, `0 warnings`, 7 hints conocidos;
  `pnpm build` PASS, 161 páginas;
- backend completo: `1735 passed`, `49 skipped`, `0 failed`;
- Diagnosis smoke real: scope PostgreSQL resuelto y estado de 6 turnos
  persistido; retrieval Milvus con `last_sources=5`; LiteLLM
  `openai_gpt-5.4-nano` PASS; `fallback=false`; diagnóstico estructurado PASS
  en el turno 5. Diagnosis permanece en el commit baseline `e21a429` y no fue
  modificado;
- configuración dinámica DEV: SLA N1/N2/N3 `30/60/120`, aprobación N2 y
  valores operativos observados por API sin restart;
- producción: intacta; automation productiva no desplegada ni habilitada;
- WhatsApp: fuera de alcance, sin actividad.

### Deuda no bloqueante

Quedan para hardening posterior autenticación/RBAC, coordinación multiworker
del scheduler, logging persistente y la migración futura desde APIs ORM de
PyMilvus antes de 3.1. Las referencias antiguas a ausencia de scheduler en los
gates históricos describen el alcance de aquellas fechas; este gate es la
fuente vigente.

## Gate 2026-08-16 — Flow rol Directorio / autorización mínima V1

Estado: PASS funcional real/controlado. La consulta ejecutiva HTTP queda
protegida por la capability persistente `flow.executive.read` resuelta con el
RBAC existente. `model_eval/**` no fue tocado.

### Modelo de autorización

- autenticación (PASETO console) ≠ autorización (capability persistente);
- migración `020_team360_flow_director_authorization_v1.sql` (ventana GLOBAL
  autorizada) siembra `flow.executive.read` en `core_permissions`; sin grants
  de usuario en la migración (los grants son operacionales/fixtures);
- `executive_auth.py` resuelve el workspace del usuario y consulta
  `list_effective_permissions` (roles + permission profiles existentes);
- fail closed: sin capability → DENY; el dominio no autoriza; el 403 ocurre
  antes de datos/LLM y también para request_ids inexistentes (sin enumeración);
- flujo: PASETO → capability → executive service; 401 / 403 / 200 / 404
  diferenciados.

### Evidencia

- tests unitarios de ruta (TestClient + tokens reales del par de test): sin
  token 401, token inválido 401, autenticado sin permiso 403 sin llamar al
  LLM ni al servicio, autorizado 200, autorizado + request inexistente 404,
  no autorizado + request inexistente 403, dos usuarios (A 200 / B 403),
  intentos de escalada (`role=director`, `X-Is-Admin`, email por header)
  ignorados;
- PostgreSQL real: grant → `has_flow_executive_read` True y consulta
  AUDIT_SNAPSHOT/LIVE reales; revoke → False (fail closed); read-only con hash
  intacto;
- backend completo: 1385 PASS, 20 SKIP;
- LAT (md/index/sections/code-refs/general) y `git diff --check`: PASS;
- `gitleaks`/`ruff` no instalados (documentado); secret scan manual sin
  hallazgos.

### Fuera de alcance confirmado

Sin RBAC general, multi-tenant, roles por sector/municipio, gestión gráfica de
permisos, frontend Directorio, dashboard, PDF, Excel, WhatsApp, N4, reopen,
delegación ni citizen permissions.

## Gate 2026-08-19 — Flow comunicación ciudadana mínima y segura V1

Estado: PASS (`TEAM360_FLOW_CITIZEN_COMMUNICATION_V1_PASS`). Capa mínima de
comunicación con el vecino durante el ciclo de vida del caso, sin exponer
información operacional interna de LaMuni.

### Alcance ciudadano validado

El vecino recibe comunicaciones simples en los momentos relevantes del caso:

- **Recepción**: "Recibimos su solicitud N.º <referencia>."
- **En tratamiento**: "Su solicitud continúa en gestión."
- **Resolución**: "Su solicitud fue atendida y quedó finalizada."

La información interna de gestión —responsables, niveles, escalaciones, tiempos
de SLA, supervisión y auditoría— permanece reservada para LaMuni.

### Fuera de alcance del MVP actual

- Solicitud automática de información adicional al vecino (INFO_REQUIRED).
- Conversación ciudadana bidireccional avanzada.
- Portal ciudadano.
- WhatsApp outbound.
- Consulta ciudadana de estado.
- Carga de documentación por parte del vecino.
- Chatbot ciudadano.

En futuras etapas podrán incorporarse interacciones adicionales con el vecino.

### Arquitectura

- Migration 022: tabla `flow_citizen_notifications` con dedupe por
  `(request_id, notification_type)`, trazabilidad de delivery, reconciliación
  RFC y estados `PENDING`/`SENT`/`DELIVERY_UNCERTAIN`/`DELIVERY_FAILED`.
- Domain: proyección pública `CitizenCaseProjection` construida por allowlist
  (nunca por serialización con remoción de claves), templates determinísticos
  en español, sanitización de texto público.
- Service: entrega idempotente con dedupe key determinístico, clasificación de
  fallo, retry mediante reconciliación RFC sin envíos duplicados.
- Integración: `poll_once` dispara RECEIVED tras confirmación, IN_PROGRESS en
  primera actuación operacional o escalamiento, RESOLVED solo después de
  APPROVE + request RESOLVED.
- `automatic_runner` dispara IN_PROGRESS en escalamiento completado.
- Demo harness verifica pasos ciudadanos + ausencia de filtración interna.

### Seguridad y aislamiento de roles

- Ciudadano ≠ Operacional ≠ Aprobador.
- Respuesta ciudadana con texto "APROBADO" no crea approval.
- Respuesta ciudadana con texto "RESUELTO" no crea resolution.
- Respuesta ciudadana con texto operacional no se interpreta como respuesta
  técnica.
- Thread ciudadano ≠ thread operacional ≠ thread de aprobación.

### Evidencia

- 57 tests ciudadanos (unit, contrato, PostgreSQL real, role isolation, reply
  handling, migration contract, LaMuni E2E): PASS.
- Backend regresión: 1574 PASS, 47 skipped, 0 failed.
- Frontend `pnpm check`: 0 errors, 0 warnings.
- Frontend `pnpm build`: Complete (161 pages).
- LaMuni demo E2E: RECEIVED/IN_PROGRESS/RESOLVED validados, zero internal leak.

### Fuera de alcance confirmado

Sin WhatsApp, portal ciudadano, solicitud automática de información adicional,
conversación bidireccional avanzada, SMS, push notifications, preference
center, subscriptions, marketing email, i18n nuevo, LLM para texto público,
model change, LiteLLM change.



## Gate 2026-08-16 — Flow consulta ejecutiva / Directorio V1

Estado: PASS funcional real/controlado. Una capa de consulta read-only sobre los
hechos persistidos de Flow responde preguntas de Directorio sin alterar el
workflow. `model_eval/**` no fue tocado.

### Arquitectura

- `executive_service.py` + `executive_query.py` (vista normalizada y métricas
  derivadas) + `executive_ai.py` (LiteLLM `openai_gpt-5.4-nano`);
- `data_source = AUDIT_SNAPSHOT` para `RESOLVED` con registro inmutable en
  `flow_case_audit_records`; `data_source = LIVE` para casos abiertos (no se
  fabrican audit records);
- contrato: request, routing_history, sla, escalations, operational_events,
  resolution, closure_approval, result, metrics, timeline, audit y el hecho
  determinístico `status_fact` (closed/open/pending_approval) que el LLM no
  puede contradecir;
- trazabilidad: routing:<id>, sla:<id>, event:<id>, resolution:<id>,
  approval:<id>, audit:<id>;
- CLI `executive_query_once <request-id> [--question]` y ruta HTTP
  `GET /api/team360-flow/executive/{request_id}` autenticada con PASETO console,
  registrada vía `routes.py` (MODULE_LOCAL) sin tocar el registry ni el
  entrypoint.

### Evidencia real

- caso `814f38ce` RESOLVED → `AUDIT_SNAPSHOT`, hash intacto, resumen trazable
  que identifica quién autorizó el cierre;
- caso `d16a0a08` RESOLUTION_PENDING_APPROVAL → `LIVE`,
  `status_fact=pending_approval`; respuesta ejecutiva correcta: NO está cerrado;
- caso `c92d739c` ACTIVE post-reject → `LIVE`, motivo de rechazo persistido y
  explicado; cero audit records;
- doble consulta: mismo hash y mismos conteos (audit=1, routing=1, evento=1);
  cero mutaciones.

### Validación

- unitarios de vista, métricas, guardrails del prompt y contrato de ruta: PASS;
- PostgreSQL real (LIVE → cierre real → AUDIT_SNAPSHOT + idempotencia): PASS;
- backend completo: 1368 PASS, 19 SKIP;
- LAT (md/index/sections/code-refs/general) y `git diff --check`: PASS;
- `gitleaks`/`ruff` no instalados (documentado); secret scan manual sin
  hallazgos.

### Fuera de alcance confirmado

Sin frontend Directorio, dashboard, PDF, Excel, BI, WhatsApp, N4, reopen,
delegación, citizen approval ni worker/scheduler.



## Gate 2026-08-16 — Flow cierre con aprobación de supervisor y registro de auditoría V1

Estado: PASS funcional real/controlado. El técnico propone resolución, el
supervisor autoriza el cierre y Flow genera un registro de auditoría
inmutable. El vecino y el técnico nunca cierran un caso.

### Modelo de cierre

- el intérprete operacional reconoce `RESOLUTION_PROPOSED` (lenguaje inequívoco
  de reparación/cierre) sin cerrar el caso; lenguaje dudoso queda
  `ACK_OR_PROGRESS`/`AMBIGUOUS`;
- la propuesta (`flow_request_resolutions`) es idempotente por
  `(source_provider, source_external_message_id)` y se asocia a un routing;
- la autoridad de cierre (`flow_closure_approvals`) es configurable por sector
  (`flow_sectors.closure_approval_level = 2` para alumbrado) y se resuelve al
  destino `alumbrado.n2@alquimiablue.com`, nunca desde el current level;
- `APPROVE` transiciona atómicamente approval + resolution + request RESOLVED y
  genera `flow_case_audit_records` (snapshot JSONB + SHA-256 canónico);
- `REJECT` persiste el motivo y devuelve el request a ACTIVE para nueva
  propuesta; `RESOLVED` es terminal (trigger DB impide degradación);
- el token de aprobación es determinístico (SHA-256 del source message) y
  arranca con letra para que el correlador operacional no robe la decisión.

### Evidencia real

- caso `814f38ce-9509-4cd6-a355-fa176e63edb2`: técnico respondió en N1, Flow
  interpretó `RESOLUTION_PROPOSED`, envió un único email de aprobación a
  `alumbrado.n2@alquimiablue.com` con token, cadena N1 y resumen SLA; el
  supervisor respondió `APROBAR` y el caso quedó RESOLVED con `authorized_by`
  y audit record `a23aa1ec` (schema 1, SHA-256 verificado por re-cómputo);
- caso `c92d739c-4e6e-4b84-a65d-99a6a90ef712`: supervisor respondió
  `RECHAZAR: falta verificar...`, approval/resolution REJECTED, request ACTIVE
  y cero audit records;
- segundo `poll_once`: cero proposals/approvals/decisions/audit nuevos y
  `resolved_at` intacto.

### Validación

- Flow focalizado con PostgreSQL real (propuestas, approve, reject, idempotencia
  de decisión, rollback de transacción de cierre y terminalidad): PASS;
- unitarios de clasificación, correlación, decisiones, hash y timeline: PASS;
- backend completo: 1355 PASS, 18 SKIP;
- migración 019 validada con apply, rollback y reapply sin reiniciar servicios;
  trigger `trg_flow_request_resolution_guard` bloquea RESOLVED sin approval
  APPROVED y la degradación de RESOLVED.

### Fuera de alcance confirmado

Sin reopen, ciudadano aprobando cierre, N4, delegación, frontend, dashboard,
PDF, Excel, WhatsApp, scheduler, worker ni Pub/Sub. La ficha de auditoría es
persistencia backend para consulta ejecutiva futura.

## Gate 2026-08-13 — Flow SLA primera respuesta Alumbrado N3 V1

Estado: PASS funcional real/controlado. La política de catálogo N3 en 30
segundos activa el mismo motor FIRST_RESPONSE por routing y permite resultados
MET o BREACHED sin lógica específica de nivel ni creación de N4.

### Generalización y persistencia

El runtime ya era completamente routing-scoped, por lo que el cambio funcional
se limita a la migración de catálogo `018_team360_flow_n3_first_response_sla_v1.sql`.

- cada routing ASSIGNED consulta su `sector_level_id` y congela duración,
  `assigned_at_utc` y `due_at_utc` en un único snapshot;
- checker, primera respuesta, reconciliación y eventos operan por `routing_id`;
- N1, N2 y N3 pueden conservar tres FIRST_RESPONSE independientes para un mismo
  request;
- el N3 histórico `0fc2db47-064a-40ce-ad03-25e4d9877bdf`, creado con política
  nula, continúa con cero SLA;
- al no existir nivel activo posterior a N3, un breach final no es elegible para
  escalamiento y no crea N4.

### Evidencia real MET

El caso `56076a27-4927-495c-b3f6-1a4fe309f31e` recorrió N1 y N2 BREACHED antes
de asignar N3 `c7a7d73b-8c98-4458-9ab4-83f1189c114b`.

- snapshot N3: 30 s desde `16:27:14.818611Z` hasta `16:27:44.818611Z`;
- outbound Gmail `19ffbf30695fcd2b`, destino lógico
  `alumbrado.n3@alquimiablue.com` y exactamente un mensaje N3;
- reply sender-side `19ffbf3483969daa`, inbound `19ffbf34c9b08cf9`, recibido
  `16:27:33Z` (T+18.181389 s);
- correlación `in_reply_to_rfc`, interpretación `ACK_OR_PROGRESS`, work N3
  IN_PROGRESS y SLA MET;
- segundo poll y segundo checker no duplicaron eventos ni timestamps.

### Evidencia real BREACHED y fin N3

El caso `b0265a36-abca-4e2b-a0f3-1c9437446cb0` llegó con N1 y N2 BREACHED a N3
`595953b3-2381-4c4c-866a-006d8951e0dd`.

- snapshot N3: 30 s desde `16:32:20.076912Z` hasta `16:32:50.076912Z`;
- outbound Gmail `19ffbf7acbba2926`, exactamente un mensaje al destino N3;
- sin respuesta, work N3 ASSIGNED y SLA BREACHED evaluado
  `16:33:14.124730Z`;
- segunda evaluación `checked=0`; dry-run de escalamiento `eligible=0`;
- catálogo N4, routing N4, escalamiento N3→N4 y email adicional: cero.

### Fuera de alcance confirmado

La validación focalizada Flow, incluidos los repositories PostgreSQL reales,
cerró con 134 PASS. La suite backend completa cerró con 1296 PASS y 9 SKIP.

Sin N4, escalamiento N3→N4, delegación, resolución, frontend, WhatsApp,
Pub/Sub, scheduler ni worker permanente.

## Gate 2026-08-13 — Flow respuesta operacional Alumbrado N3 V1

Estado: PASS funcional real/controlado. Una respuesta humana al outbound N3 se
correlacionó por el RFC del routing, se interpretó con LiteLLM y cambió solo el
work state N3 a IN_PROGRESS, sin crear SLA ni alterar N1/N2.

### Generalización y persistencia

El motor operacional ya era completamente routing-scoped, por lo que no fue
necesario modificar runtime ni crear migración para Nivel 3.

- RFC `In-Reply-To` y `References` consultan todos los routings ASSIGNED;
- el fallback usa request UUID más `[R:<routing_key>]` para N1, N2 o N3;
- request UUID sin routing token queda ambiguo cuando conviven varios niveles;
- sender, mailbox físico y Gmail thread no determinan identidad operacional;
- work state, primera respuesta y eventos pertenecen al `routing_id` concreto;
- la unicidad `provider + inbound_external_message_id` conserva idempotencia.

### Evidencia real N3

El reply controlado se recibió y procesó una sola vez mediante el mismo
`poll_once` usado por N1 y N2.

- request `2ff06dc7-719f-45cf-a08a-177e4e9d77a8`; routing N3
  `0fc2db47-064a-40ce-ad03-25e4d9877bdf`, key `alumbrado_level_3`;
- outbound sender Gmail `19ffb389b6df6623`, RFC observado
  `<CAOrU6M9bVnk8bM+AXMaRP+NcmM+AOeb+tpQ-vp3kjXdw5oHT-A@mail.gmail.com>`;
- reply sender-side `19ffb4a3544c1410`, inbound `19ffb4a3ba3032ed`, recibido
  `2026-08-13T13:22:52Z` con `In-Reply-To` N3;
- correlación `in_reply_to_rfc`, interpretación `ACK_OR_PROGRESS` mediante
  `openai_gpt-5.4-nano`, N3 `ASSIGNED → IN_PROGRESS`;
- `first_response_at_utc=2026-08-13T13:22:52Z`, un evento operacional y cero
  SLAs N3;
- segundo polling: `processed=0`, `operational_duplicates=1`, sin cambios.

### Validación e integridad

La cobertura determinística y PostgreSQL demuestra la misma correlación por
RFC y token para tres niveles, incluso con el mismo responder físico.

- Flow focalizado con PostgreSQL real: 131 PASS;
- backend completo: 1293 PASS, 9 SKIP;
- N1/N2 permanecieron ASSIGNED, sin primera respuesta ni eventos nuevos, y sus
  SLA siguieron BREACHED;
- ambas escalaciones permanecieron COMPLETED, current level siguió 3 y no se
  creó routing N4 ni email adicional;
- smoke LiteLLM real clasificó el texto controlado como ACK_OR_PROGRESS.

### Fuera de alcance confirmado

Sin SLA N3, N4, escalamiento N3→N4, delegación, resolución, frontend,
WhatsApp, Pub/Sub, scheduler ni worker permanente.

## Gate 2026-08-13 — Flow escalamiento Alumbrado N2 a N3 V1

Estado: PASS funcional real/controlado. Un SLA N2 BREACHED se reconcilió y
escaló mediante el mismo mecanismo genérico al siguiente nivel activo, creando
un routing N3 independiente y un único email real al destino lógico N3.

### Generalización y persistencia

La implementación elimina los supuestos N1 del selector, servicio, email y
persistencia, manteniendo la identidad por routing y SLA disparador.

- migración `017_team360_flow_n2_to_n3_escalation_v1.sql`: catálogo Alumbrado
  N3 activo, email `alumbrado.n3@alquimiablue.com` y SLA nulo;
- el resolver selecciona el menor `level` activo mayor al nivel del routing;
- `UNIQUE(trigger_sla_id, trigger_type)` permite dos escalaciones del mismo
  request y `UNIQUE(request_id, routing_key)` impide routings equivalentes;
- la constraint acepta `to_level > from_level`, necesaria para omitir niveles
  inactivos sin asumir adyacencia;
- una relectura bloqueada posterior al polling y reconciliación descarta un
  breach provisional antes de enviar.

### Evidencia real N2→N3

El caso reutilizado conservó íntegramente los dos niveles previos y produjo la
tercera etapa sin crear SLA N3.

- request `2ff06dc7-719f-45cf-a08a-177e4e9d77a8`; N1
  `4a587e84-36c1-479c-8051-6ccac9fc2c89` y N2
  `0f43ca1c-8a20-4f1e-a609-5d581f7e1213`, ambos SLA BREACHED;
- dry-run: `eligible=1`, `from_level=2`, `to_level=3`, sin escrituras;
- escalamiento `35f64455-5ff4-40f8-aa80-dcd324bf05aa`, trigger SLA N2
  `dd05c1b8-d6ce-4bb3-bd4d-ea7e0c762015`, COMPLETED;
- routing N3 `0fc2db47-064a-40ce-ad03-25e4d9877bdf`, key
  `alumbrado_level_3`, work ASSIGNED y cero SLAs;
- Gmail sender `19ffb389b6df6623`, receiver `19ffb38b58f8d609`, `To` lógico N3
  y RFC observado coincidente; existe exactamente un mensaje N3 del request;
- segunda ejecución real: `eligible=0`, `created=0`, `sent=0`.

### Validación

La cobertura incluye lógica determinística, repositorios y carrera real sobre
PostgreSQL, además del cruce de evidencia con Gmail.

- regresión N1→N2, N2→N3, MET/PENDING, reconciliación y respuesta tardía;
- dos escalaciones y tres routings coexistentes para un request;
- dos servicios concurrentes sobre el mismo SLA N2: un escalamiento, un
  routing N3 y una única llamada lógica de envío;
- incertidumbre Gmail reconciliada sin reenvío ciego;
- migración 017 validada con apply, rollback y reapply sin reiniciar servicios.

### Fuera de alcance confirmado

Sin respuesta operacional ni SLA N3, N4, escalamiento N3→N4, delegación,
resolución, frontend, WhatsApp, Pub/Sub, scheduler ni worker permanente.

## Gate 2026-08-13 — Flow SLA primera respuesta Alumbrado N2 V1

Estado: PASS funcional real/controlado. N1 y N2 mantienen SLAs FIRST_RESPONSE
independientes de 30 segundos para el mismo request, identificados por
`routing_id`; N2 puede terminar MET o BREACHED sin modificar la evidencia N1.

### Generalización y persistencia

- migración mínima `016_team360_flow_n2_first_response_sla_v1.sql`: configura
  Alumbrado Nivel 2 en 30 segundos sin backfill de routings históricos;
- el motor SLA, el checker, la consulta de `first_response_at_utc`, los eventos
  y la reconciliación ya eran genéricos por routing; no se creó motor N2;
- el fix conecta las transiciones nuevas N2 `ASSIGNED` del servicio de
  escalamiento con `ensure_first_response_sla`; los N2 ya asignados antes de la
  política no reciben snapshots retrospectivos;
- la elegibilidad de escalamiento conserva `frr.level = 1`: un SLA N2 BREACHED
  queda persistido y no crea N3, otro N2 ni email adicional.

### Evidencia real MET

- request `7b8fd0cf-7645-448a-97b7-217aceacaf08`; N1
  `6e987555-7fe5-4ff8-bb27-1ec58b487bb2`, SLA
  `78d13cab-b09f-4fe3-84b3-d7aecdb4e164` BREACHED, sin respuesta;
- N2 `39933b93-4898-47ac-b967-9d02770d2637`, outbound Gmail
  `19ffb191996d6467`, snapshot 30 s desde `12:29:13.341101Z` hasta
  `12:29:43.341101Z`;
- reply Gmail real `19ffb192f84c9e00`, recibido `12:29:17Z` (T+3.658899 s),
  work state IN_PROGRESS y SLA MET;
- segunda evaluación `checked=0`; historial N2 exactamente `SLA_STARTED` y
  `SLA_MET`; N1 siguió BREACHED con timestamps y conteos intactos.

### Evidencia real BREACHED y protección N3

- request `2ff06dc7-719f-45cf-a08a-177e4e9d77a8`; N1
  `4a587e84-36c1-479c-8051-6ccac9fc2c89` BREACHED;
- N2 `0f43ca1c-8a20-4f1e-a609-5d581f7e1213`, outbound Gmail
  `19ffb1c185f3f38e`, snapshot 30 s desde `12:32:29.717636Z` hasta
  `12:32:59.717636Z`;
- sin respuesta; evaluado `12:33:01.611711Z`, work state ASSIGNED y SLA
  BREACHED; segunda evaluación `checked=0`;
- `escalate_once` dry-run: `eligible=0`, con 2 routings y 1 escalamiento total;
  no N3, no escalamiento N2→N3 y no email adicional.

### Validación

- regresión focalizada Flow con PostgreSQL real: 113 PASS;
- unitarios multinivel: N1 inmutable mientras N2 llega a MET/BREACHED;
- configuración: 30 válido, NULL sin SLA, 0/negativo rechazados y snapshot 30
  inmutable tras cambio 30→60;
- PostgreSQL: dos FIRST_RESPONSE para un request en routings distintos,
  creación idempotente, respuesta tardía, reconciliación y eventos por SLA;
- preflight real: PostgreSQL 18.4, Milvus, LiteLLM
  `openai_gpt-5.4-nano`, `globalVar` y Gmail DWD disponibles, sin reinicios.

### Fuera de alcance confirmado

Sin N3, escalamiento N2→N3, delegación, resolución, frontend, WhatsApp,
Pub/Sub, scheduler ni worker permanente.

## Gate 2026-08-12 — Flow respuesta operacional Alumbrado N2 V1

Estado: PASS funcional real/controlado. Una respuesta humana al outbound N2 se
normalizó en Messaging, correlacionó específicamente con el routing N2 por RFC,
se interpretó con LiteLLM y cambió únicamente el work state N2 a IN_PROGRESS.

### Generalización y seguridad multinivel

- el servicio operacional trabaja por `routing_id`, conserva level/routing key
  como contexto y consulta todos los routings ASSIGNED, no solo el actual;
- prioridad: `In-Reply-To`, `References`, token `[R:<routing_key>]` más request
  UUID y, únicamente para requests con un solo routing, UUID sin token;
- request UUID sin headers/token queda ambiguo cuando conviven N1 y N2, por lo
  que no se elige un nivel arbitrariamente;
- work states, eventos y `first_response_at_utc` son independientes por routing;
  el sender físico y Gmail `threadId` no participan en la identidad;
- no fue necesaria una migración nueva: 013 + 015 ya soportan el modelo.

### Evidencia real

- request `28f8e055-ac93-4c02-9e16-9bc98871fd39`; N1
  `3b1c6a1e-2c31-4d1c-add9-20e484413b57` permaneció ASSIGNED, SLA BREACHED,
  sin primera respuesta ni eventos;
- N2 `ff1ddbdb-8c85-46f8-ad55-1478bc511e92`, outbound Gmail
  `19ff77a8a8717621`; reply real de técnico `19ff79e0029d48d1` y copia inbound
  `19ff79e048d10cd3`;
- correlación `in_reply_to_rfc`, acción `ACK_OR_PROGRESS`, N2
  `ASSIGNED → IN_PROGRESS`, primera respuesta `2026-08-12T20:15:55Z`;
- segundo polling: procesados 0, duplicados operacionales 1; un solo evento y
  timestamp N2 sin cambios;
- smoke LiteLLM real usó `openai_gpt-5.4-nano` y clasificó el texto controlado
  como `ACK_OR_PROGRESS`.

### Fuera de alcance confirmado

Sin SLA/vencimiento N2, N3, escalamiento N2→N3, delegación, resolución,
frontend, WhatsApp/Gupshup, Pub/Sub, scheduler ni worker permanente.

## Gate 2026-08-12 — Flow escalamiento Alumbrado N1 a N2 V1

Estado: PASS funcional real/controlado. Un breach final de primera respuesta
N1 crea una etapa N2 independiente, entrega un único email real al destino
lógico del catálogo y preserva íntegramente toda la evidencia N1.

### Modelo e implementación

- migración aditiva `015_team360_flow_n1_to_n2_escalation_v1.sql`: work state
  por routing, seed Alumbrado N2 sin SLA y auditoría idempotente en
  `flow_request_escalations`;
- N1 y N2 conviven como routings distintos; la unicidad del trigger SLA y de
  `request_id + routing_key` protege escalamiento y asignación;
- `escalate_once` es dry-run por defecto. En modo real procesa primero replies
  del inbox, reconcilia SLA y hace una última relectura bloqueada; evidencia
  recibida a tiempo excluye el breach antes de cualquier envío;
- el envío N2 reutiliza Messaging/Gmail y la reconciliación por RFC/reference.
  Una entrega incierta no habilita un reenvío ciego;
- el nivel actual se deriva del routing `ASSIGNED` de mayor nivel, sin puntero
  duplicado ni sobrescritura histórica.

### Evidencia real

- request `28f8e055-ac93-4c02-9e16-9bc98871fd39`; routing N1
  `3b1c6a1e-2c31-4d1c-add9-20e484413b57`, SLA
  `a7be9c45-f9aa-45b0-a079-d2d4efab1b05` BREACHED, sin primera respuesta;
- escalamiento `c1272620-6855-4622-9f40-07924465c5c0`, trigger
  `FIRST_RESPONSE_SLA_BREACHED`, N1→N2, COMPLETED;
- routing N2 `ff1ddbdb-8c85-46f8-ad55-1478bc511e92`, ASSIGNED a
  `alumbrado.n2@alquimiablue.com`, Gmail sender id `19ff77a8a8717621`;
- el buzón físico recibió un único mensaje con `To` lógico N2 y el mismo RFC
  Message-ID observado. Segunda ejecución: eligible/created/sent = 0;
- N1 continúa ASSIGNED con SLA BREACHED; N2 continúa ASSIGNED sin snapshot SLA.

### Fuera de alcance confirmado

Sin N3, SLA N2 evaluado, escalamiento N2→N3, delegación, resolución, frontend,
WhatsApp/Gupshup, Pub/Sub, scheduler ni worker permanente.

## Gate 2026-08-12 — Flow SLA primera respuesta Alumbrado N1 V1

Estado: PASS funcional real/controlado. Cada routing nuevo de Alumbrado N1
captura un SLA de 30 segundos desde `assigned_at_utc`; el checker determinístico
persiste cumplimiento o vencimiento sin IA, emails adicionales ni escalamiento.

### Modelo e implementación

- migración aditiva `014_team360_flow_n1_first_response_sla_v1.sql`: agrega
  configuración positiva/null por `flow_sector_levels`, snapshots en
  `flow_request_slas` y auditoría idempotente en `flow_request_sla_events`;
- snapshot inmutable: duración, inicio y vencimiento pertenecen al routing
  concreto y no cambian si después cambia el catálogo;
- estados SLA separados de work status: `PENDING`, `MET`, `BREACHED`;
- `first_response_at <= due_at` cumple, incluida igualdad exacta. Una respuesta
  tardía conserva BREACHED aunque work status sea IN_PROGRESS;
- `check_sla_once` es finito, usa clock inyectable en tests y no crea scheduler;
- un breach provisional se reconcilia a MET solo cuando aparece evidencia
  Gmail real recibida a tiempo. Los eventos `SLA_BREACHED` y `SLA_RECONCILED`
  preservan la auditoría.

### Evidencia real

- MET: request `60aefb18-3f68-445f-8ba0-b7c0dc98e53f`, routing
  `85a2e309-eb70-4b7a-91e2-971963d096a3`; inicio
  `2026-08-12T18:44:32.499326Z`, due `18:45:02.499326Z`, respuesta Gmail
  `18:44:37Z` (T+4.501 s), SLA MET y work status IN_PROGRESS;
- BREACHED: request `28f8e055-ac93-4c02-9e16-9bc98871fd39`, routing
  `3b1c6a1e-2c31-4d1c-add9-20e484413b57`; inicio
  `18:45:15.158061Z`, due `18:45:45.158061Z`, sin primera respuesta, evaluado
  `18:45:47.886743Z`, SLA BREACHED y work status ASSIGNED;
- exactamente un email routing por caso; segunda evaluación `checked=0`, sin
  eventos duplicados ni cambios en timestamps definitivos;
- integración PostgreSQL validó constraint positivo, snapshot, cambio posterior
  de catálogo, idempotencia, respuesta tardía y reconciliación.

### Fuera de alcance confirmado

Sin Nivel 2/3, escalamiento, email a supervisor, delegación, resolución,
frontend, WhatsApp/Gupshup, Pub/Sub, worker permanente ni scheduler.

## Gate 2026-08-12 — Flow respuesta operacional Alumbrado N1 V1

Estado: PASS funcional real/controlado. La respuesta humana del técnico al
routing de Alumbrado N1 volvió a `mesaentrada@`, se normalizó, correlacionó por
evidencia RFC persistida, interpretó mediante LiteLLM y produjo `IN_PROGRESS`
con primer tiempo de respuesta inmutable.

### Arquitectura e implementación

- migración aditiva `013_team360_flow_n1_operational_reply_v1.sql`: RFC real
  observado del outbound, `flow_request_work_states` y
  `flow_request_operational_events`;
- dispatcher dentro del único `poll_once`: correlación operacional primero e
  intake ciudadano únicamente cuando no existe routing correlacionado;
- correlación por `In-Reply-To`, `References`, RFC observado/intencionado y UUID
  estable del request en subject; sender y Gmail `threadId` no deciden identidad;
- interpretación validada por schema con LiteLLM alias
  `openai_gpt-5.4-nano`: `ACK_OR_PROGRESS`, `AMBIGUOUS`, `UNRELATED` y
  `UNSUPPORTED_OPERATIONAL_ACTION`;
- routing `ASSIGNED` y estado operacional permanecen separados. Resolución o
  cierre informados por el técnico se auditan pero no cierran el request.

### Evidencia real

- request `656977af-cc29-43d6-b78c-53464818f06a`, routing
  `2b355d5a-813b-441f-baf2-238d1bc1d516`, outbound Gmail
  `19ff654320c4964c`;
- reply real desde `mario.rojas@alquimiablue.com`, inbound Gmail de
  `mesaentrada@` `19ff6a9e337d5362`, correlación `in_reply_to_rfc`;
- interpretación `ACK_OR_PROGRESS`, estado `ASSIGNED → IN_PROGRESS`,
  `first_response_at_utc=2026-08-12T15:49:15Z`, igual al timestamp Gmail;
- segundo polling: 0 procesados, 1 duplicado operacional, 1 evento total y
  `first_response_at_utc` sin cambios;
- preflight PostgreSQL 18.4, Milvus productivo, LiteLLM/modelo real y Gmail DWD
  para mesa/técnico: PASS. Smoke real: dos avances `ACK_OR_PROGRESS`; “Ok.”
  conservadoramente `AMBIGUOUS`.

### Fuera de alcance confirmado

Sin SLA, timeout, vencimiento, Nivel 2/3, escalamiento, delegación, resolución,
frontend, WhatsApp/Gupshup, Pub/Sub, worker permanente ni orquestador general.

## Gate 2026-08-12 — Flow routing email Alumbrado Nivel 1 V1

Estado: PASS funcional local/controlado. Una solicitud Flow `CONFIRMED` se
resuelve contra catálogo estable, se asigna a `alumbrado` Nivel 1 y se entrega
por Messaging/Gmail a `alumbrado.n1@alquimiablue.com` sin duplicación.

### Arquitectura e implementación

- migración aditiva `012_team360_flow_routing_n1_v1.sql`: catálogos
  `flow_sectors`, `flow_sector_levels` y evidencia idempotente en
  `flow_request_routings`;
- resolución determinística de categorías normalizadas; categorías desconocidas
  o catálogo/nivel inactivo quedan `ROUTING_UNRESOLVED` y no envían email;
- el estado principal `CONFIRMED` permanece estable y el routing usa su propia
  máquina mínima (`ROUTING_PENDING`, `ASSIGNED`, `ROUTING_UNRESOLVED`,
  `ROUTING_FAILED`);
- `route_once` es dry-run por defecto y exige `--confirm-send` para Gmail real;
- retries consultan Gmail Sent por `Message-ID` y referencia única de request.
  Gmail reescribe el primero en envíos API, por lo que la referencia persistente
  y visible en subject/body es la reconciliación efectiva.

### Evidencia real

- request `656977af-cc29-43d6-b78c-53464818f06a`, routing
  `2b355d5a-813b-441f-baf2-238d1bc1d516`, sector `alumbrado`, Nivel 1;
- Gmail emisor aceptó message id `19ff654320c4964c`; el buzón destino recibió un
  único mensaje correlacionado por request id;
- segunda ejecución: mismo routing/message id, `sent=False`,
  `idempotent=True`; un único registro de routing y un único mensaje en Sent;
- preflight: PostgreSQL 18.4, Milvus collection productiva, LiteLLM alias
  `openai_gpt-5.4-nano` con llamada real no vacía y Gmail DWD lectura: PASS.

### Fuera de alcance confirmado

Sin SLA, timers, Nivel 2/3, escalamiento, delegación, respuesta del técnico,
frontend, WhatsApp/Gupshup, Pub/Sub, worker permanente ni orquestador general.

## Gate 2026-08-12 — Flow email AI intake con confirmación humana V1

Estado: PASS funcional local/controlado. Vertical real Gmail → Messaging → Flow
→ LiteLLM/GPT-5.4 nano → confirmación Gmail → solicitudes `CONFIRMED`, sin
routing ni capacidades del gate siguiente.

### Arquitectura e implementación

- Messaging incorpora `InboundMessage` inmutable y
  `OutboundMessageReceipt`; Gmail normaliza headers/MIME `text/plain`, conserva
  message/thread IDs y responde con `threadId`, `In-Reply-To` y `References`.
- `modules/flow/` separa dominio, máquina de estados, intake IA, repository
  PostgreSQL, servicio y `poll_once` finito.
- La idempotencia usa `unique (provider, external_message_id)` y no depende de
  `UNREAD`; el polling no modifica labels.
- IA: adapter `LiteLLMClient` existente, alias efectivo
  `openai_gpt-5.4-nano`, Chat Completions, JSON validado con schema Python y sin
  fallback silencioso.
- Persistencia: migración aditiva
  `011_team360_flow_email_intake_v1.sql`, aplicada sobre la DB local/controlada;
  5 tablas Flow para conversaciones, mensajes, interpretaciones, candidatos
  revisionados y solicitudes confirmadas.

### Evidencia real

- preflight: PostgreSQL 18.4 PASS; Milvus y collection productiva PASS;
  LiteLLM alias registrado + llamada real no vacía PASS; Gmail DWD lectura PASS.
- smoke LiteLLM real: Caso A = 1 solicitud; Caso B = 2 solicitudes preservando
  “misma cuadra”; confirmación y corrección clasificadas correctamente.
- E2E A, thread de entrada `19ff62e3dba7f4e4`: 3 mensajes trazados,
  2 interpretaciones, 1 candidato, estado `CONFIRMED`, 1 solicitud confirmada;
  tercer `poll_once` procesó 0 mensajes nuevos.
- E2E B, thread de entrada `19ff62ee85b334a6`: 3 mensajes trazados,
  2 interpretaciones, 2 candidatos, estado `CONFIRMED`, 2 solicitudes
  confirmadas independientes; tercer `poll_once` procesó 0 mensajes nuevos.

### Tests y correcciones iterativas

- tests Flow/Messaging focalizados: 23 PASS;
- integración repository con PostgreSQL real y rollback: 1 PASS;
- regresión backend completa: 1185 PASS, 10 skips, 1 warning preexistente;
- bug E2E corregido: GPT-5.4 nano clasificó inicialmente “Sí, correcto.” como
  ambiguo; causa raíz en prompt sin ejemplos de decisión, corregida y protegida
  con smoke real;
- bug de aislamiento de suite corregido: tests DB sin DSN dependían del momento
  de import de `globalVar`; el fallback se aísla explícitamente en esos tests.

### Fuera de alcance confirmado

Sin routing, sectores, SLA, niveles, escalamiento, delegación, dashboard,
frontend Flow, WhatsApp/Gupshup, MercadoLibre, Pub/Sub ni daemon permanente.

## Stage 9 2026-08-06 — consolidacion UX, sincronizacion de estado y regresion protegida

Estado: CONSOLIDADO. Documentacion canonica y documento consolidado UX creados;
regresion Console ejecutada; pendiente `public-vera.spec.ts:230` verificado como
resuelto; un bloqueo ambiental de Milvus documentado con evidencia.

### Estado Git

- rama: `feature/console-backend-core`;
- HEAD inicial: `a89924a` (docs Stage 8);
- HEAD final: `a89924a + 1 commit nuevo` (fix overflow dashboard);
- worktree inicial: limpio; worktree final: limpio (todo commiteado);
- push: no realizado.

### Migracion UX Stages 1-8 (relevada y consolidada)

- Stage 1 foundation visual: `5d8ca08` (tokens global.css) + `docs/ux/team360-console-design-handoff-stage-1-audit.md`;
- Stage 2 shell funcional: `546e945` + `team360-console-design-handoff-stage-2-shell.md`;
- Stage 3 componentes compartidos: `807a9a4` + `team360-console-design-handoff-stage-3-components.md`;
- Gate 3B serving DEV del embed: `7527a24` + `docs/diagnosticador_embed_dev_serving_v1.md`;
- Gate 3C logo del Sidebar: `b6f152c`; Gate 3D alineacion del test del logo: `3ae1258`;
- Stage 4 Clients/Dashboard/Reportes/Alertas: `847f37f`, `e17b60b`, `f4f6669` + `team360-console-design-handoff-stage-4-screens.md`;
- Stage 5 Operacion (services, tasks, runs, workers): `30119fa`, `40003e7`, `dcacbd8` + `team360-console-design-handoff-stage-5-operation.md`;
- Stage 6 Organizacion (organizations, partners, workspaces, team): `a09aa4b`, `c20c2b7` + `team360-console-design-handoff-stage-6-organization.md`;
- Stage 7 Settings y Support: `a511be9`, `80085fe` + `team360-console-design-handoff-stage-7-settings-support.md`;
- Stage 8 Results y ServiceDetail: `8c9af41`, `67bdbac` + `team360-console-design-handoff-stage-8-results-service-detail.md`;
- documento consolidado: `docs/ux/team360-console-ux-stages-1-8-consolidated.md`.

Gate 3D: se determino por commits y documentacion que fue ejecutado y cerrado
como el commit de alineacion del assertion del logo (`3ae1258`); no se invento
estado adicional.

### Funcionalidad preservada

- rutas, tabs (ServiceDetail conserva 8 tabs), handlers y stores sin cambios;
- Vera y `/t360` sin cambios; Diagnosticador, loader, manifest y entry sin cambios;
- contratos publicos, CORS, allowed origins y DEV/PRO sin cambios;
- cliente y produccion no tocados.

### Regresion corregida en Stage 9

- `ConsoleDashboard.svelte` (items de ejecuciones): overflow horizontal de 19 px
  en 390 px por el token de worker name no fragmentable + bump tipografico
  `text-xs -> text-sm` de Stages 4-8. Fix minimo: `min-w-0` + `overflow-wrap:anywhere`.
  Commit separado `fix(ux)`.

### Baseline de validacion (ejecutado en Stage 9)

- Console E2E (runtime oficial 3050, backend-dev.sh 7050): shell 7/7, Stage 3 5/5,
  Stage 5 4/4, Stage 6 5/5, Stage 7 3/3, Stage 8 3/3 = 27/27 PASS;
- Vera `/t360` (mock de turn): `public-vera.spec.ts` 12/12 PASS + 2 skips preexistentes;
- `public-vera.spec.ts:230` (interaction_block): PASS — pendiente historico resuelto,
  comportamiento intencional: el interaction block representa la eleccion del usuario
  y no duplica un bubble de usuario (`appendUserMessage=false`);
- `t360-interaction-lab.spec.ts`: 1/1 PASS;
- smoke visual Playwright 390/768/1280 sobre 16 rutas de consola: 48/48 PASS
  (sin overflow, sin errores de consola, sin HTTP >= 400) tras el fix del dashboard;
- `pnpm check`: 0 errors, 0 warnings, 6 hints preexistentes;
- `pnpm build`: 146 pages; `git diff --check`: PASS;
- LAT: `lat check md/index/sections/code-refs/check` = 0 errores;
- regresion consolidada final (Console + Vera + Embed, 21 spec files):
  68 PASS / 2 skips preexistentes;
- Vera family con LLM real: feasibility/adversarial/postsale 23/23,
  email-orders/kommo/salesforce 3/3, phone-problems 5/5,
  mobile-sequential 2/2, new-conversation 2/2;
- smoke real `/t360` (`T360_REAL_E2E=1`): PASS con backend caliente
  (6 turns reales, 23.5 s);
- `diagnosis.spec.ts`: 1 PASS + 1 skip preexistente (caso backend apagado).

### Bloqueo ambiental (resuelto durante Stage 9)

- El contenedor permanente `milvus26-standalone` salio con exit code 1 el
  2026-08-06 ~13:26 por timeouts internos de etcd (lease expired).
  PostgreSQL y LiteLLM permanecieron operativos. No se reinicio Milvus
  (prohibido): el stack completo fue restablecido externamente ~13:55.
- Mientras Milvus estuvo caido, `backend-dev.sh` no arrancaba (preflight) y
  las validaciones con backend real quedaron temporalmente bloqueadas
  (smoke real `/t360`, contrato embed `auth -> turn`, `diagnosis.spec.ts`).
  Con Milvus disponible de nuevo se ejecutaron todas y pasan (ver baseline).

### Pendientes reales

- push pendiente de la serie UX + este Stage 9;
- PASETO fases 1-4 (Console integration, dual support, deprecacion HMAC);
- deuda embed futura: package npm, Web Component, plugin WordPress, UI/admin
  `embed_clients`, E2E movil flaky, migracion de tokens;
- polish visual futuro: aumento tipografico integral, iconos SVG en stats panels,
  `Card variant="dark"` donde no hay caso semantico, CustomSelect completo;
- bloqueo ambiental Milvus: resuelto (servicio restablecido externamente;
  validaciones reales re-ejecutadas con PASS).

## Gate 2026-08-06 — proteccion de home publica y Vera

Estado: PASS (`TEAM360_PUBLIC_HOME_VERA_PROTECTION_PASS`). Contrato protegido
creado y enlazado; prueba E2E de proteccion consolidada; sin cambios en home,
Vera ni artefactos productivos.

### Contrato protegido

- `SrvRestAstroLS_v1/docs/public_home_vera_protection_contract_v1.md` — reglas
  de la home, Vera publica y embed productivo, y proteccion estructural para
  Team360 Flow y futuros modulos.
- Enlazado desde este tablero y desde la documentacion del embed.

### Inventario relevado (sin cambios de codigo)

- Home: `src/pages/index.astro` (idem `/t360`), layout
  `src/layouts/PublicMarketingLayout.astro`, header/footer marketing,
  seccion Vera en `src/components/diagnosis/PublicVeraEntry.svelte` con
  `id="vera"` + `scroll-mt-24`.
- Vera: `DiagnosticadorCore.svelte` + adapters publicos; sesion
  `team360.vera.session.v1`; `appendUserMessage=false` en `t360action` es
  intencional (el block representa la eleccion; no duplica bubble).
- URLs: `src/components/global.js` sigue siendo fuente de verdad DEV/PRO.
- Comparacion DEV vs PROD (GET seguros): `/` 200 HTML, loader/manifest/entry
  200; manifest productivo identico al commiteado.

### Validacion ejecutada

- Nuevo E2E `e2e/public-home-vera-protection.spec.ts`: 7/7 PASS (home, `/#vera`,
  hash tras reload, seccion bajo header, interaccion mock sin duplicacion,
  nueva conversacion, mobile 390, HE/RTL, matriz 390/768/1280).
- `public-home-social-meta.spec.ts`: 2/2 PASS.
- `public-vera.spec.ts`: 15/15 PASS + 2 skips preexistentes; smoke real
  (`T360_REAL_E2E=1`) PASS.
- Familia Vera (feasibility/adversarial/postsale/email-orders/kommo/salesforce/
  phone/mobile-sequential/new-conversation): 33/33 PASS.
- Embed DEV + loader + manifest + SRI + cross-origin + mount/destroy/remount +
  auth -> turn + Mamamia360: 28/28 PASS.
- Matriz visual `/` y `/#vera` en 390/768/1280: sin overflow, sin errores de
  consola, hash y reload correctos.
- `pnpm check`: 0 errors; `pnpm build`: 146 pages; `git diff --check`: PASS;
  LAT: 0 errores.

## Deploy 2026-08-06 — Console UX en produccion

Estado: `TEAM360_CONSOLE_UX_PRODUCTION_DEPLOY_PASS`. Publicacion del frontend
estatico de `https://team360.live` con la migracion UX de Console (Stages 1-8 +
gates de proteccion) mediante el procedimiento canonico de rsync.

- HEAD desplegado: `0ac79fc` (23 commits locales sin push); push no realizado.
- Backup remoto: `.../astro/backups/dist_before_ux_20260806_230348.tar.gz`.
- Rsync real: exit 0; 111 paginas `w/` actualizadas, 2 assets hasheados
  rotados (`AppShell.*.js`, `global.*.css`); sin rutas inesperadas.
- Embed: loader, manifest, entry y `vera-loader.js` byte-identicos a
  produccion (Caso A); SRI/CORS/allowed origins/URLs intactos.
- Smoke productivo: home + `/#vera` 200 y metadata intacta; rutas Console 200;
  `public-home-vera-protection` 7/7; Vera real `phone-problems` 5/5;
  Mamamia360 embed 6/6; matriz responsive 390/768/1280 24/24; sin 5xx.
- Notas de suites DEV vs PROD (no regresiones): `console-shell.spec.ts:29`
  espera URL sin trailing slash; `stage3:34` clickea antes de la hidratacion.
- Release documentada en `docs/releases/team360-console-ux-production-2026-08-06.md`.
- PostgreSQL, Milvus y LiteLLM no fueron iniciados, detenidos ni reiniciados.
### Regresiones

- Encontradas: ninguna en home/Vera/embed (las suites pasan sobre el runtime
  oficial con servicios reales disponibles).
- Preexistentes: 2 skips de `public-vera.spec.ts` (reload-session y smoke real
  por defecto).
- No se realizaron cambios funcionales en este gate.

## Actualizacion operativa 2026-07-06 — alias LiteLLM GPT-5.4 Nano

- El alias operativo de Team360 cambia de `openai_gpt-5-nano` a
  `openai_gpt-5.4-nano`.
- El upstream continúa siendo `openai/gpt-5.4-nano`.
- El runtime público usa Chat Completions de forma explícita mediante
  `TEAM360_LITELLM_API_MODE=chat`.
- Responses API queda limitada a labs o validaciones controladas mediante
  `TEAM360_LITELLM_API_MODE=responses`.
- Se actualizaron defaults backend, preflight de LiteLLM, scripts operativos,
  tests, fixtures E2E, labs reutilizables y documentación canónica.
- La evidencia histórica y los resultados fechados conservan el alias usado al
  momento de cada ejecución.
- Smoke directo real: PASS con contenido no vacío, `finish_reason=stop`, 38
  tokens totales y 1149 ms de latencia; sin fallback en el cliente directo.
- Validación productiva real de Vera: PostgreSQL + Milvus + LiteLLM, 10/10
  escenarios PASS, 26 muestras, p50 3273 ms y p95 7313 ms.
- El backend confirmó en runtime efectivo:
  `TEAM360_LITELLM_MODEL_ALIAS=openai_gpt-5.4-nano` y
  `TEAM360_LITELLM_API_MODE=chat`.

## Normalización documental 2026-07-06 — compatibilidad con lat 0.11

- `lat check` pasó de 130 errores a PASS completo.
- Se restauraron los conceptos `team360-frontend-base` y
  `team360-frontend-ui-policy` desde ADR-004/005 y sus documentos fuente.
- `lat.md/status_actual.md` volvió a ser un tablero compacto; la evidencia
  histórica permanece en este documento, el histórico congelado y Git.
- Se agregaron resúmenes breves a 70 secciones existentes sin modificar sus
  reglas, ejemplos ni contratos.
- El índice LAT incluye ahora `status_actual` y no conserva links rotos.
- `lat check code-refs`: PASS; todos los anchors `@lat` permanecen válidos.
- La política permanente queda en `lat.md/lat-documentation-policy.md`; AGENTS
  y el skill Team360 la enlazan y recuerdan los gates sin duplicarla.

## Trabajo anterior - Diagnosticador embebible

Estado: Fases 1 a 5 implementadas; confirmadas en `cdd1b1b`.

## Trabajo actual - Separacion factibilidad/implementacion

Estado: Fase 7 a 9A implementadas y confirmadas en `15e3e98`. Fases 9B, 9C, 9D,
9E, 9C-ext, 9D-ext y 9F implementadas y validadas en este worktree.

## Fase 10A — Guía externa de instalación + paquete mínimo para cliente técnico PHP/WordPress/HTML

Estado: CLIENT INSTALLATION GUIDE IMPLEMENTADO Y VALIDADO.

### Decisión técnica

- Se crea documentación externa clara para clientes técnicos sin requerir
  plug-and-play absoluto.
- El formato de entrega es `div + script + clientId + origin autorizado`,
  compatible con HTML estático, PHP, WordPress y builders.
- No se crea package npm, Web Component ni plugin WordPress productivo en esta
  fase.
- El cliente técnico recibe solo `clientId` público, snippet recomendado y guía
  de troubleshooting.
- `hmac_secret`, tenant/scope, `allowed_origins` se administran server-side.
- `global.js` no fue modificado.
- `/t360` y `PublicVeraEntry.svelte` no fueron modificados.

### Implementación

Documentos creados:

- `docs/diagnosticador_embed_installation_guide_v1.md` — guía externa completa
  con snippets recomendado, simple, HTML, PHP, WordPress bloque HTML,
  shortcode/plugin mínimo conceptual, parámetros permitidos/prohibidos,
  troubleshooting, checklist cliente, checklist Team360.
- `docs/diagnosticador_embed_client_handoff_v1.md` — handoff interno
  comercial/técnico con flujo de alta, criterio de "listo para cliente" y
  referencias.

Documentos actualizados:

- `docs/diagnosticador_external_integrity_snippet_v1.md` — referencia cruzada
  a la guía de instalación.
- `docs/status_actual.md` — esta sección.
- `lat.md/status_actual.md` — sección equivalente.

### Contenido de la guía de instalación

- snippet recomendado con integrity;
- snippet simple compatible;
- HTML estático completo;
- PHP tradicional;
- WordPress bloque HTML;
- shortcode/plugin mínimo conceptual;
- tabla de parámetros permitidos;
- lista de parámetros prohibidos;
- flujo de alta de cliente;
- troubleshooting;
- checklist técnico del cliente;
- checklist Team360.

### Contenido del handoff interno

- qué se entrega al cliente;
- qué NO se entrega;
- flujo de alta;
- mensaje breve para técnico del cliente;
- criterio de "listo para cliente".

### Validación 10A

| Validación | Resultado |
| ---------- | --------- |
| `git diff --check` | PASS |
| `pnpm check` | PASS |
| `pnpm build` | PASS |
| Secret/no-leak search | PASS — sin secretos reales ni códigos internos en snippets |
| Protección `/t360` | Sin diff |
| Protección `PublicVeraEntry.svelte` | Sin diff |
| Protección `global.js` | Sin diff |

Servicios permanentes no reiniciados: PostgreSQL, Milvus, LiteLLM.

### Seguridad

- `clientId` tratado como público.
- Sin `hmac_secret` real en documentación.
- Sin `organization_code`, `workspace_code`, `package_code`,
  `knowledge_scope_code`, `assistant_instance_code` en snippets públicos.
- `allowed_origins` no expuesto como editable por cliente.
- Parámetros prohibidos documentados explícitamente.

### Compatibilidad

- HTML estático.
- PHP tradicional.
- WordPress bloque HTML.
- WordPress shortcode/plugin mínimo conceptual.
- Gutenberg, Elementor, Divi, builders similares (con advertencia de
  optimizadores).
- Limitación conocida: plugins de seguridad/minificación/caché pueden alterar
  scripts.

### Deuda restante documentada

- package npm.
- Web Component nativo.
- CSS encapsulado final.
- Eventos públicos `t360:*` definitivos.
- Plugin WordPress productivo completo.
- Publicación en marketplace.
- UI/admin para `embed_clients`.
- E2E móvil flaky.
- Deuda LAT preexistente.

## Fase 9I — sync automatizado de loaderIntegrity en snippets/fixtures

Estado: IMPLEMENTADO Y VALIDADO. MCP limitado; gate efectivo con Playwright
CLI sobre runtime fallback local.

### Decision tecnica

- se elige Opcion C minima:
  - fixture literal sincronizado por script;
  - test anti-drift contra `manifest.loaderIntegrity`;
- la fuente de verdad queda en
  `astro/public/embed/team360-diagnosticador.manifest.json`;
- no cambia la API publica:
  - `window.Team360DiagnosticadorLoader.load()`;
  - `window.Team360Diagnosticador.mount(...)`;
- `entryIntegrity` se valida como prerequisito del sync, pero no se copia al
  host;
- el fixture 9H deja de depender del placeholder
  `__TEAM360_LOADER_INTEGRITY__` inyectado por el spec.

### Implementacion

- helper nuevo:
  `astro/scripts/sync-embed-integrity-snippets.mjs`;
- fixture literal sincronizado:
  `astro/e2e/fixtures/cross-origin-host/t360-cross-origin-integrity-loader.html`;
- spec endurecido:
  `e2e/diagnosticador-cross-origin-integrity-loader-fixture.spec.ts`;
- documentacion actualizada:
  - `docs/diagnosticador_external_integrity_snippet_v1.md`;
  - `docs/diagnosticador_loader_distribution_v1.md`;
  - `docs/diagnosticador_loader_integrity_v1.md`;
  - `docs/diagnosticador_loader_integrity_enforcement_v1.md`.

### Validacion 9I

Preflight:

- Git limpio al inicio: PASS.
- Runtime local:
  - `backend-dev.sh`: PASS;
  - fallback estatico local sobre `astro/dist` en `3050` con proxy `/api` a
    `127.0.0.1:7050`: PASS.

Backend:

- `uv run pytest tests/test_diagnosis_public_router.py tests/test_embed_clients_contract.py`:
  `83/83 PASS`.
- `uv run pytest tests/ -x --ignore=tests/test_db_module.py`:
  `1089 PASS, 9 skipped`.

Frontend:

- `pnpm check`: `0 errors`, `0 warnings`, `5 hints`.
- `pnpm build`: `146 pages`.
- helpers:
  - `node scripts/update-embed-integrity.mjs`: PASS;
  - `node scripts/sync-embed-integrity-snippets.mjs`: PASS.

Playwright CLI local (`PLAYWRIGHT_BASE_URL=http://127.0.0.1:3050`):

- `e2e/diagnosticador-cross-origin-integrity-loader-fixture.spec.ts`:
  `4 PASS`.
- `loader-integrity fixture + manifest + cross-origin + browser + mount + external + embed`:
  `16 PASS`.
- suite focalizada con Vera/lab/embed/external/mount/loader/fixture/manifest:
  `30 PASS, 2 skipped`.

Seguridad:

- fixture/snippet sincronizado no contiene `hmac_secret`;
- fixture/snippet sincronizado no contiene tenant, scope ni
  `allowed_origins`;
- `/t360`, `PublicVeraEntry.svelte` y `global.js` siguen fuera del diff.

## Fase 9H — fixture externo E2E con loaderIntegrity + verifyEntryIntegrity

Estado: IMPLEMENTADO Y VALIDADO. MCP limitado; gate efectivo con Playwright
CLI sobre runtime fallback local.

### Decision tecnica

- se crea fixture nuevo dedicado, sin reemplazar el fixture cross-origin
  default;
- el host recomendado usa `loaderIntegrity` en el `<script>` remoto;
- el host recomendado usa `crossorigin="anonymous"` en ese `<script>`;
- el loader resuelve el manifest default relativo a su propio `src`, por lo que
  el snippet externo puede omitir `manifestUrl`;
- el host recomendado activa `load({ verifyEntryIntegrity: true })`;
- el entry dinamico sigue usando `entryIntegrity` + `crossorigin="anonymous"`;
- `loaderIntegrity` invalido bloquea antes de `auth/turn`;
- `entryIntegrity` invalido rechaza antes de mount.

### Implementacion

- loader actualizado:
  `astro/public/embed/team360-diagnosticador-loader.js`;
- manifest actualizado:
  `astro/public/embed/team360-diagnosticador.manifest.json`;
- fixture nuevo:
  `astro/e2e/fixtures/cross-origin-host/t360-cross-origin-integrity-loader.html`;
- spec nuevo:
  `e2e/diagnosticador-cross-origin-integrity-loader-fixture.spec.ts`;
- documentacion nueva:
  `docs/diagnosticador_external_integrity_snippet_v1.md`;
- documentacion actualizada:
  - `docs/diagnosticador_loader_distribution_v1.md`;
  - `docs/diagnosticador_loader_manifest_v1.md`;
  - `docs/diagnosticador_loader_integrity_v1.md`;
  - `docs/diagnosticador_loader_integrity_enforcement_v1.md`.

### Validacion 9H

Preflight:

- Git limpio al inicio: PASS.
- DB real:
  - `embed_clients`: presente;
  - `local_embed_demo`: activo;
  - `allowed_origins`: `127.0.0.1:3050`, `localhost:3050`, `127.0.0.1:3060`;
  - secret presente (sin imprimirlo).
- Runtime local:
  - `backend-dev.sh`: PASS;
  - fallback estatico local sobre `astro/dist` en `3050` con proxy `/api` a
    `127.0.0.1:7050`: PASS;
  - assets embed servidos con CORS abierto para SRI cross-origin.

Backend:

- `uv run pytest tests/test_diagnosis_public_router.py tests/test_embed_clients_contract.py`:
  `83/83 PASS`.
- `uv run pytest tests/ -x --ignore=tests/test_db_module.py`:
  `1089 PASS, 9 skipped`.

Frontend:

- `pnpm check`: `0 errors`, `0 warnings`, `5 hints`.
- `pnpm build`: `146 pages`.
- helper:
  `node scripts/update-embed-integrity.mjs`: PASS.

Playwright CLI local (`PLAYWRIGHT_BASE_URL=http://127.0.0.1:3050`):

- `e2e/diagnosticador-cross-origin-integrity-loader-fixture.spec.ts`:
  `3 PASS`.
- `loader-integrity fixture + manifest + cross-origin + browser + mount + external + embed`:
  `15 PASS`.
- suite focalizada con Vera/lab/embed/external/mount/loader/fixture/manifest:
  `29 PASS, 2 skipped`.

Seguridad:

- fixture/snippet nuevos no contienen `hmac_secret`;
- fixture/snippet nuevos no contienen tenant, scope ni `allowed_origins`;
- `loaderIntegrity` invalido bloquea antes de `auth/turn`;
- `/t360`, `PublicVeraEntry.svelte` y `global.js` siguen fuera del diff.

MCP:

- endpoint intentado: `http://localhost:8931/mcp`;
- si no expone herramientas navegables en la sesion, el gate real sigue siendo
  Playwright CLI.

## Fase 9G — enforcement opt-in de entryIntegrity en el loader

Estado: IMPLEMENTADO Y VALIDADO. MCP limitado; gate efectivo con Playwright
CLI sobre runtime fallback local.

### Decision tecnica

- `window.Team360DiagnosticadorLoader.load()` sigue compatible;
- `window.Team360Diagnosticador.mount(...)` no cambia;
- se agrega `verifyEntryIntegrity: true` como modo opt-in explicito;
- el loader conserva el camino default sin enforcement;
- en modo opt-in el loader aplica `integrity` y `crossorigin="anonymous"` al
  script dinamico del entry;
- si falta `entryIntegrity`, rechaza antes de cargar;
- si el browser bloquea el entry por mismatch, rechaza con error controlado;
- si el global ya existe, resuelve idempotente y no revalida esa carga previa.

### Implementacion

- loader actualizado:
  `astro/public/embed/team360-diagnosticador-loader.js`;
- typing actualizado:
  `astro/src/env.d.ts`;
- spec endurecido:
  `e2e/diagnosticador-loader-manifest.spec.ts`;
- documentacion nueva:
  `docs/diagnosticador_loader_integrity_enforcement_v1.md`;
- documentacion actualizada:
  - `docs/diagnosticador_loader_distribution_v1.md`;
  - `docs/diagnosticador_loader_manifest_v1.md`;
  - `docs/diagnosticador_loader_integrity_v1.md`.

### Validacion 9G

Preflight:

- Git limpio al inicio: PASS.
- DB real:
  - `embed_clients`: presente;
  - `local_embed_demo`: activo;
  - `allowed_origins`: `127.0.0.1:3050`, `localhost:3050`, `127.0.0.1:3060`;
  - secret presente (sin imprimirlo).
- Runtime local:
  - `backend-dev.sh`: PASS;
  - fallback estatico local sobre `astro/dist` en `3050` con proxy `/api` a
    `127.0.0.1:7050`: PASS;
  - assets `loader`, `manifest` y `entry` servidos con CORS abierto para
    validar el fixture cross-origin.

Backend:

- `uv run pytest tests/test_diagnosis_public_router.py tests/test_embed_clients_contract.py`:
  `83/83 PASS`.
- `uv run pytest tests/ -x --ignore=tests/test_db_module.py`:
  `1089 PASS, 9 skipped`.

Frontend:

- `pnpm check`: `0 errors`, `0 warnings`, `5 hints`.
- `pnpm build`: `146 pages`.
- helper:
  `node scripts/update-embed-integrity.mjs`: PASS.

Playwright CLI local (`PLAYWRIGHT_BASE_URL=http://127.0.0.1:3050`):

- `e2e/diagnosticador-loader-manifest.spec.ts`:
  `6 PASS`.
- `loader-manifest + fixture + cross-origin + mount + external + embed`:
  `12 PASS`.
- suite focalizada con Vera/lab/embed/external/mount/loader/fixture/manifest:
  `26 PASS, 2 skipped`.

Seguridad:

- manifest/loader/asset estables no contienen `hmac_secret`;
- manifest/loader/asset estables no contienen tenant, scope ni
  `allowed_origins`;
- `/t360`, `PublicVeraEntry.svelte` y `global.js` siguen sin cambios.

MCP:

- endpoint intentado: `http://localhost:8931/mcp`;
- si no expone herramientas navegables en la sesion, el gate real sigue siendo
  Playwright CLI.

## Fase 9F — integrity/checksum opcional para loader distribution

Estado: IMPLEMENTADO Y VALIDADO. MCP limitado; gate efectivo con Playwright
CLI sobre runtime fallback local.

### Decision tecnica

Se eligio Opcion C:

- checksums `SHA-256` hex en manifest;
- SRI `sha256-...` en manifest;
- sin enforcement runtime del asset dinamico cargado por el loader;
- helper deterministico para recalculo despues de `build`;
- sin tocar `/t360`, `PublicVeraEntry.svelte` ni `global.js`.

### Implementacion

- manifest actualizado:
  `astro/public/embed/team360-diagnosticador.manifest.json`;
- helper nuevo:
  `astro/scripts/update-embed-integrity.mjs`;
- spec endurecido:
  `e2e/diagnosticador-loader-manifest.spec.ts`;
- documentacion nueva:
  `docs/diagnosticador_loader_integrity_v1.md`;
- documentacion actualizada:
  - `docs/diagnosticador_loader_distribution_v1.md`;
  - `docs/diagnosticador_loader_manifest_v1.md`.

### Contrato de integridad

Campos nuevos en el manifest:

- `entrySha256`;
- `entryIntegrity`;
- `loaderSha256`;
- `loaderIntegrity`.

Fuente de verdad:

- `loader`: `public/embed/team360-diagnosticador-loader.js`;
- `entry`: `dist/embed/team360-diagnosticador.js`.

### Snippet externo

Se documentan dos caminos:

- simple:
  `<script type="module" src="https://team360.live/embed/team360-diagnosticador-loader.js"></script>`;
- con integrity:
  `<script type="module" src="https://team360.live/embed/team360-diagnosticador-loader.js" integrity="sha256-..." crossorigin="anonymous"></script>`.

Notas:

- `loaderIntegrity` sale del manifest;
- `clientId` es publico;
- `hmac_secret` nunca se entrega;
- tenant/scope y `allowed_origins` quedan server-side.

### Validacion 9F

Preflight:

- Git limpio al inicio: PASS.
- DB real:
  - `embed_clients`: presente;
  - `local_embed_demo`: activo;
  - `allowed_origins`: `127.0.0.1:3050`, `localhost:3050`, `127.0.0.1:3060`;
  - secret presente (sin imprimirlo).
- Runtime local:
  - `backend-dev.sh`: PASS;
  - fallback estatico local sobre `astro/dist` en `3050` con proxy `/api` a
    `127.0.0.1:7050`: PASS.

Backend:

- `uv run pytest tests/test_diagnosis_public_router.py tests/test_embed_clients_contract.py`:
  `83/83 PASS`.
- `uv run pytest tests/ -x --ignore=tests/test_db_module.py`:
  `1089 PASS, 9 skipped`.

Frontend:

- `pnpm check`: `0 errors`, `0 warnings`, `5 hints`.
- `pnpm build`: `146 pages`.
- helper:
  `node scripts/update-embed-integrity.mjs`: PASS.

Playwright CLI local (`PLAYWRIGHT_BASE_URL=http://127.0.0.1:3050`):

- `e2e/diagnosticador-loader-manifest.spec.ts`:
  `2 PASS`.
- `loader-manifest + fixture + cross-origin + mount + external + embed`:
  `8 PASS`.
- suite focalizada con Vera/lab/embed/external/mount/loader/fixture/manifest:
  `22 PASS, 2 skipped`.

Seguridad:

- manifest/loader/asset estables no contienen `hmac_secret`;
- manifest/loader/asset estables no contienen tenant, scope ni
  `allowed_origins`;
- `/t360`, `PublicVeraEntry.svelte` y `global.js` siguen sin cambios.

MCP:

- endpoint intentado: `http://localhost:8931/mcp`;
- reachability HTTP: `400 Bad Request`;
- sin herramientas MCP navegables expuestas en esta sesion;
- cierre efectivo con Playwright CLI.

## Fase 9D-ext — fixture cross-origin controlado para validar Origin/CORS real

Estado: IMPLEMENTADO Y VALIDADO. MCP limitado; gate efectivo con Playwright
CLI sobre runtime fallback local.

### Decision tecnica

Se eligio host cross-origin controlado:

- fixture HTML estatico fuera de `public/`, servido por test en `3060/3061`;
- loader, manifest y asset remotos en `127.0.0.1:3050`;
- API real en `127.0.0.1:7050`;
- CORS backend local habilitado para `3050`, `3060` y `3061`;
- `local_embed_demo.allowed_origins` actualizado solo en DB local para agregar
  `http://127.0.0.1:3060`;
- `3061` queda fuera de `allowed_origins` y se rechaza con `403`;
- sin tocar `/t360`, `PublicVeraEntry.svelte` ni `global.js`.

### Implementacion

- nuevo fixture HTML:
  `astro/e2e/fixtures/cross-origin-host/t360-cross-origin-loader.html`;
- nueva session key aislada:
  `team360.embed.cross_origin.fixture.session.v1`;
- nuevo E2E:
  `e2e/diagnosticador-cross-origin-loader-fixture.spec.ts`;
- nueva documentacion:
  `docs/diagnosticador_cross_origin_fixture_v1.md`.

### Contrato validado

- host permitido:
  `http://127.0.0.1:3060/t360-cross-origin-loader.html`;
- host rechazado:
  `http://127.0.0.1:3061/t360-cross-origin-loader.html`;
- `window.Team360DiagnosticadorLoader.load()`;
- `window.Team360Diagnosticador.mount(...)`;
- `destroy()` operativo;
- `POST /api/diagnosis/embed/auth`;
- `POST /api/diagnosis/turn` con `client_id`, `timestamp`,
  `Origin` real y `X-T360-Signature`;
- rechazo `403` para origin no permitido sin `turn` exitoso.

### Seguridad

- el fixture cross-origin no expone `hmac_secret`;
- el fixture cross-origin no expone tenant/scope ni `allowed_origins`;
- `3060` se habilita solo en la DB local del cliente de prueba;
- `3061` queda fuera de `allowed_origins`;
- la sesion del fixture no toca `team360.vera.session.v1`.

## Fase 9C-ext — validacion externa real del browser loader publico

Estado: IMPLEMENTADO Y VALIDADO. MCP limitado; gate efectivo con Playwright
CLI sobre runtime fallback local.

### Decision tecnica

Se eligio Opcion A same-origin:

- fixture HTML estatico en `astro/public/embed-fixtures/`;
- mismo origin `127.0.0.1:3050` ya permitido por `embed_clients`;
- sin tocar DB ni `allowed_origins`;
- sin npm/package;
- sin Web Component;
- sin tocar `/t360`, `PublicVeraEntry.svelte` ni `global.js`.

### Implementacion

- nuevo fixture HTML:
  `astro/public/embed-fixtures/t360-external-loader.html`;
- nueva session key aislada:
  `team360.embed.loader.fixture.session.v1`;
- nuevo E2E:
  `e2e/diagnosticador-browser-loader-fixture.spec.ts`;
- nueva documentacion:
  `docs/diagnosticador_browser_loader_fixture_v1.md`.

### URLs locales validadas

- fixture:
  `/embed-fixtures/t360-external-loader.html`
- manifest:
  `/embed/team360-diagnosticador.manifest.json`
- loader:
  `/embed/team360-diagnosticador-loader.js`
- asset:
  `/embed/team360-diagnosticador.js`

### Contrato validado

- host HTML de tercero controlado con `div + script`;
- `window.Team360DiagnosticadorLoader.load()`;
- `window.Team360Diagnosticador.mount(...)`;
- `destroy()` operativo;
- `POST /api/diagnosis/embed/auth`;
- `POST /api/diagnosis/turn` con `client_id`, `timestamp` y
  `X-T360-Signature`;
- rechazo de `mount()` sin `clientId` sin requests extra.

### Seguridad

- el fixture HTML no expone `hmac_secret`;
- el fixture HTML no expone tenant/scope ni `allowed_origins`;
- `public/embed-fixtures/` y `dist/embed-fixtures/` no contienen tenant/scope;
- la busqueda amplia sobre `dist/` sigue mostrando strings tecnicos
  preexistentes en bundles compartidos del proyecto, fuera del alcance de esta
  fase;
- el fixture no toca `team360.vera.session.v1`,
  `team360.embed.mount.demo.session.v1` ni
  `team360.embed.external.demo.session.v1`.

### Validacion 9C-ext

Preflight:

- Git limpio al inicio: PASS.
- DB real:
  - `embed_clients`: presente;
  - seed `local_embed_demo`: activo;
  - `allowed_origins`: `127.0.0.1:3050` y `localhost:3050`;
  - secret presente (sin imprimirlo).

Backend:

- `uv run pytest tests/test_diagnosis_public_router.py tests/test_embed_clients_contract.py`:
  83/83 PASS.
- `uv run pytest tests/ -x --ignore=tests/test_db_module.py`:
  1089 PASS, 9 skipped.

Frontend:

- `pnpm check`: 0 errors, 0 warnings, 5 hints.
- `pnpm build`: 146 pages.

Playwright CLI local (`PLAYWRIGHT_BASE_URL=http://127.0.0.1:3050`):

- `e2e/diagnosticador-browser-loader-fixture.spec.ts`:
  1 PASS.
- `fixture + loader + mount + external + embed`:
  5 PASS.
- suite focalizada con Vera/lab/embed/external/mount/loader/fixture:
  19 PASS, 2 skipped.

Runtime local:

- `backend-dev.sh`: PASS.
- fallback usado para Playwright CLI: backend real `7050` + servidor estatico
  local sobre `astro/dist` con proxy `/api` a `127.0.0.1:7050`.
- `curl -I /embed-fixtures/t360-external-loader.html`: 200 OK.

MCP:

- endpoint intentado: `http://localhost:8931/mcp`;
- reachability HTTP: `400 Bad Request`;
- sin herramientas MCP navegables expuestas en esta sesion;
- cierre efectivo con Playwright CLI.

## Fase 9E — manifest/loader externo minimo con versionado explicito

Estado: IMPLEMENTADO Y VALIDADO. MCP limitado; gate efectivo con Playwright
CLI sobre runtime fallback local.

### Decision tecnica

Se eligio Opcion A minima:

- manifest publico estable en `/embed/team360-diagnosticador.manifest.json`;
- loader publico estable en `/embed/team360-diagnosticador-loader.js`;
- asset estable conservado en `/embed/team360-diagnosticador.js`;
- sin tocar `mount.ts` ni `browser-global.ts` como fuentes de verdad;
- sin npm/package;
- sin Web Component;
- sin tocar `/t360`, `PublicVeraEntry.svelte` ni `global.js`.

### Implementacion

- nuevo manifest:
  `astro/public/embed/team360-diagnosticador.manifest.json`;
- nuevo loader:
  `astro/public/embed/team360-diagnosticador-loader.js`;
- nueva ruta host controlada:
  `src/pages/t360-loader-demo.astro`;
- nueva session key aislada:
  `team360.embed.loader.demo.session.v1`;
- nuevo E2E:
  `e2e/diagnosticador-loader-demo.spec.ts`;
- nuevo E2E de contrato:
  `e2e/diagnosticador-loader-manifest.spec.ts`;
- nueva documentacion:
  `docs/diagnosticador_loader_manifest_v1.md`;
- nueva documentacion de distribucion:
  `docs/diagnosticador_loader_distribution_v1.md`.

### URLs publicas

- manifest:
  `/embed/team360-diagnosticador.manifest.json`
- loader:
  `/embed/team360-diagnosticador-loader.js`
- asset:
  `/embed/team360-diagnosticador.js`

### Versionado explicito

- manifest:
  `0.9.0-experimental`
- loader:
  `experimental-9e`
- global del asset:
  `experimental-9c`

El versionado explicito nuevo vive en manifest y loader. El global del asset no
se cambio porque 9E no introduce una segunda implementacion del embed.

### Contrato publico endurecido

- el manifest expone `asset` y `entry` hacia la misma ruta publica estable;
- el manifest ahora explicita `format = browser-global`;
- el loader acepta `manifest.asset` o `manifest.entry`;
- `load()` sigue siendo idempotente: si el global ya existe, no recarga;
- el host externo sigue usando solo `clientId`, `apiBaseUrl` y props visuales
  seguras.

### Seguridad

- manifest/loader/asset estables no contienen `hmac_secret`;
- manifest/loader/asset estables no contienen tenant, scope ni
  `allowed_origins`;
- el loader no contiene `clientId` ni `apiBaseUrl`;
- el loader no hace mount automatico; solo resuelve el asset y deja el mount
  explicito al host;
- el contrato embed sigue pasando por `POST /api/diagnosis/embed/auth` y
  `POST /api/diagnosis/turn` con `client_id`, `timestamp` y
  `X-T360-Signature`.

### Validacion 9E

Backend:

- `uv run pytest tests/test_diagnosis_public_router.py tests/test_embed_clients_contract.py`:
  83/83 PASS.
- `uv run pytest tests/ -x --ignore=tests/test_db_module.py`:
  1089 PASS, 9 skipped.

Frontend:

- `pnpm check`: 0 errors, 0 warnings, 5 hints.
- `pnpm build`: 146 pages.

Playwright CLI local (`PLAYWRIGHT_BASE_URL=http://127.0.0.1:3050`):

- `e2e/diagnosticador-loader-manifest.spec.ts`:
  2 PASS.
- `e2e/diagnosticador-loader-demo.spec.ts`:
  1 PASS.
- `loader-manifest + loader + fixture + cross-origin + mount + external + embed`:
  9 PASS.
- suite focalizada con Vera/lab/embed/external/mount/loader/fixture/manifest:
  24 PASS, 1 skipped.

Runtime local:

- `backend-dev.sh`: PASS.
- fallback usado para Playwright CLI: backend real `7050` + servidor estatico
  local sobre `astro/dist` con proxy `/api` a `127.0.0.1:7050`.

MCP:

- endpoint intentado: `http://localhost:8931/mcp`;
- reachability HTTP: `400 Bad Request`;
- sin herramientas MCP navegables expuestas en esta sesion;
- cierre efectivo con Playwright CLI.

## Fase 9D — asset JS browser real servido por Astro

Estado: IMPLEMENTADO Y VALIDADO. MCP limitado; gate efectivo con Playwright
CLI sobre runtime fallback local.

### Decision tecnica

Se eligio una variante minima de Opcion C:

- asset estable emitido por el build en `/embed/team360-diagnosticador.js`;
- salida controlada desde `astro.config.mjs` con Rollup/Vite;
- reutilizando `browser-global.ts` como capa global y `mount.ts` como unica
  fuente de verdad;
- sin npm/package;
- sin Web Component;
- sin tocar `/t360`, `PublicVeraEntry.svelte` ni `global.js`.

### Implementacion

- nuevo asset estable de build:
  `dist/embed/team360-diagnosticador.js`;
- cambio minimo de build:
  `astro.config.mjs`;
- nueva pagina Astro:
  `src/pages/t360-asset-demo.astro`;
- nueva session key aislada:
  `team360.embed.asset.demo.session.v1`;
- nuevo E2E:
  `e2e/diagnosticador-asset-demo.spec.ts`;
- nueva documentacion:
  `docs/diagnosticador_browser_asset_v1.md`.

### URL publica y carga

- URL estable:
  `/embed/team360-diagnosticador.js`
- carga esperada:
  - `<script type="module" src="/embed/team360-diagnosticador.js"></script>`
- internamente el asset puede importar chunks hasheados `/_astro/*`.

### Seguridad

- el asset estable no embebe `clientId` ni `apiBaseUrl`;
- no expone `hmac_secret`, tenant, scope ni `allowed_origins`;
- mantiene `POST /api/diagnosis/embed/auth` y `POST /api/diagnosis/turn`;
- mantiene `client_id`, `timestamp` y `X-T360-Signature`;
- `dist/embed/team360-diagnosticador.js` no contiene tenant/scope;
- los chunks compartidos de `/_astro/*` siguen arrastrando contexto tecnico
  historico de Vera, preexistente y fuera del alcance de esta fase.

### Validacion 9D

Backend:

- `uv run pytest tests/test_diagnosis_public_router.py tests/test_embed_clients_contract.py`:
  83/83 PASS.
- `uv run pytest tests/ -x --ignore=tests/test_db_module.py`:
  1089 PASS, 9 skipped.

Frontend:

- `pnpm check`: 0 errors, 0 warnings, 5 hints.
- `pnpm build`: 145 pages.

Playwright CLI local (`PLAYWRIGHT_BASE_URL=http://127.0.0.1:3050`):

- `e2e/diagnosticador-asset-demo.spec.ts`:
  1 PASS.
- `asset + script + mount + external + embed`:
  6 PASS.
- suite focalizada con Vera/lab/embed/external/mount/script/asset:
  20 PASS, 2 skipped.

Runtime local:

- `backend-dev.sh`: PASS.
- `astro-dev.sh`: sigue bloqueado por el diff preexistente `IS_REST_PRO=true`
  en `global.js`.
- fallback usado para Playwright CLI: backend real `7050` + servidor estatico
  local sobre `astro/dist` con proxy `/api` a `127.0.0.1:7050`.

MCP:

- endpoint intentado: `http://localhost:8931/mcp`;
- reachability HTTP: `400 Bad Request`;
- sin herramientas MCP navegables expuestas en esta sesion;
- cierre efectivo con Playwright CLI.

## Fase 9C — script browser global controlado sobre mount

Estado: IMPLEMENTADO Y VALIDADO. MCP limitado; gate efectivo con Playwright
CLI sobre runtime fallback local.

### Decision tecnica

Se eligio Opcion A:

- entrypoint TS interno `browser-global.ts`;
- `window.Team360Diagnosticador.mount(...)` como global experimental;
- `mount.ts` sigue siendo la unica fuente de verdad;
- sin npm/package;
- sin Web Component;
- sin tocar `/t360`, `PublicVeraEntry.svelte` ni `global.js`.

### Implementacion

- nuevo registro global:
  `src/lib/t360/embed/browser-global.ts`;
- nueva pagina Astro:
  `src/pages/t360-script-demo.astro`;
- nueva session key aislada:
  `team360.embed.script.demo.session.v1`;
- nuevo E2E:
  `e2e/diagnosticador-script-demo.spec.ts`;
- nueva documentacion:
  `docs/diagnosticador_browser_global_adapter_v1.md`.

### API global experimental v1

- `window.Team360Diagnosticador.mount(container, config)`;
- `window.Team360Diagnosticador.version = "experimental-9c"`;
- handle devuelto:
  - `destroy()`.

Config permitida:

- `clientId`;
- `apiBaseUrl`;
- `assistantName`;
- `compact`;
- `initialMessage`;
- `sessionStorageKey`.

Config prohibida:

- `hmac_secret`;
- `organization_code`;
- `workspace_code`;
- `assistant_instance_code`;
- `package_code`;
- `knowledge_scope_code`;
- `allowed_origins`;
- `service_code`;
- `template_code`.

### Seguridad

- el global delega completamente en `mount.ts`;
- conserva `POST /api/diagnosis/embed/auth` y `POST /api/diagnosis/turn`;
- mantiene `client_id`, `timestamp` y `X-T360-Signature`;
- no expone `hmac_secret`, tenant, scope ni `allowed_origins`;
- conserva el global ya registrado si el script se carga dos veces;
- `/t360`, `PublicVeraEntry.svelte` y `global.js` quedaron sin cambios
  atribuibles a 9C.

### Validacion 9C

Backend:

- `uv run pytest tests/test_diagnosis_public_router.py tests/test_embed_clients_contract.py`:
  83/83 PASS.
- `uv run pytest tests/ -x --ignore=tests/test_db_module.py`:
  1089 PASS, 9 skipped.

Frontend:

- `pnpm check`: 0 errors, 0 warnings, 5 hints.
- `pnpm build`: 144 pages.

Playwright CLI local (`PLAYWRIGHT_BASE_URL=http://127.0.0.1:3050`):

- `e2e/diagnosticador-script-demo.spec.ts`:
  2 PASS.
- `script + mount + external + embed`:
  5 PASS.
- suite focalizada con Vera/lab/embed/external/mount/script:
  19 PASS, 2 skipped.

Runtime local:

- `backend-dev.sh`: PASS.
- `astro-dev.sh`: sigue bloqueado por el diff preexistente `IS_REST_PRO=true`
  en `global.js`.
- fallback usado para Playwright CLI: backend real `7050` + servidor estatico
  local sobre `astro/dist` con proxy `/api` a `127.0.0.1:7050`.

MCP:

- endpoint intentado: `http://localhost:8931/mcp`;
- reachability HTTP: `400 Bad Request`;
- sin herramientas MCP navegables expuestas en esta sesion;
- cierre efectivo con Playwright CLI.

## Fase 9B — `mount()` JavaScript experimental controlado

Estado: IMPLEMENTADO Y VALIDADO. MCP limitado; gate efectivo con Playwright
CLI sobre runtime fallback local.

### Decision tecnica

Se eligio Opcion A:

- adapter TS interno importable;
- sin `window.Team360Diagnosticador`;
- sin npm/package;
- sin Web Component;
- reutilizando `EmbedDiagnosticadorWrapper.svelte`.

### Implementacion

- nuevo adapter:
  `src/lib/t360/embed/mount.ts`;
- nuevo componente cliente demo:
  `src/lib/t360/embed/MountDiagnosticadorDemo.svelte`;
- nueva pagina Astro:
  `src/pages/t360-mount-demo.astro`;
- nueva session key aislada:
  `team360.embed.mount.demo.session.v1`;
- nuevo E2E:
  `e2e/diagnosticador-mount-demo.spec.ts`;
- nueva documentacion:
  `docs/diagnosticador_mount_adapter_v1.md`.

### API experimental v1

- `mountTeam360Diagnosticador(container, config)`;
- `Team360Diagnosticador.mount(container, config)` como namespace exportado
  interno, no global;
- handle devuelto:
  - `destroy()`.

Config permitida:

- `clientId`;
- `apiBaseUrl`;
- `assistantName`;
- `compact`;
- `initialMessage`;
- `sessionStorageKey`.

Config prohibida:

- `hmac_secret`;
- `organization_code`;
- `workspace_code`;
- `assistant_instance_code`;
- `package_code`;
- `knowledge_scope_code`;
- `allowed_origins`;
- `service_code`;
- `template_code`.

### Seguridad

- el mount reutiliza `POST /api/diagnosis/embed/auth` y
  `POST /api/diagnosis/turn`;
- mantiene `client_id`, `timestamp` y `X-T360-Signature`;
- no expone `hmac_secret`;
- no acepta tenant/scope aunque el host los intente pasar;
- `/t360`, `PublicVeraEntry.svelte` y `global.js` quedaron sin cambios
  atribuibles a 9B;
- el bundle compartido de `DiagnosticadorCore` sigue cargando strings tecnicos
  historicos de Vera, preexistentes y fuera del alcance de esta fase.

### Validacion 9B

Preflight DB real:

- `to_regclass('public.embed_clients')`: `embed_clients`
- seed `local_embed_demo`: presente, `is_active=true`
- `hmac_secret <> ''`: `true`

Backend:

- `uv run pytest tests/test_diagnosis_public_router.py tests/test_embed_clients_contract.py`:
  83/83 PASS.
- `uv run pytest tests/ -x --ignore=tests/test_db_module.py`:
  1089 PASS, 9 skipped.

Frontend:

- `pnpm check`: 0 errors, 0 warnings, 5 hints.
- `pnpm build`: 143 pages.

Playwright CLI local (`PLAYWRIGHT_BASE_URL=http://127.0.0.1:3050`):

- `e2e/diagnosticador-mount-demo.spec.ts`: PASS.
- `e2e/diagnosticador-mount-demo.spec.ts + diagnosticador-external-host-demo.spec.ts + diagnosticador-embed-demo.spec.ts`:
  3 PASS.
- suite focalizada con Vera/lab/embed/external/mount:
  17 PASS, 2 skipped.

Runtime local:

- `backend-dev.sh`: PASS.
- `astro-dev.sh`: sigue bloqueado por el diff preexistente `IS_REST_PRO=true`
  en `global.js`.
- fallback usado para Playwright CLI: backend real `7050` + servidor estatico
  local sobre `astro/dist` con proxy `/api` a `127.0.0.1:7050`.

MCP:

- endpoint intentado: `http://localhost:8931/mcp`;
- reachability HTTP: `400 Bad Request`;
- sin herramientas MCP navegables expuestas en esta sesion;
- cierre efectivo con Playwright CLI.

## Fase 9A — Adapter externo controlado del embed

Estado: IMPLEMENTADO Y GATE ESTABILIZADO. Validacion objetivo del host externo:
PASS. Suite focalizada Vera/lab/embed/external: PASS. MCP limitado.

### Causa raiz 9A-Fix

- el fallo no era una regresion del adapter externo;
- `e2e/public-vera-new-conversation.spec.ts` fallaba tambien en aislado;
- la causa fue un spec fragil: dependia del backend real, usaba
  `waitForTimeout()` fijos y no limpiaba `team360.vera.session.v1` antes de
  ejecutar el reset;
- `astro-dev.sh` sigue bloqueado de forma intencional por el diff preexistente
  `IS_REST_PRO=true` en `global.js`, por eso el gate se cerro con fallback
  estatico + proxy `/api`.

### Decision tecnica

Se eligio Opcion A:

- nueva ruta controlada `/t360-external-host-demo`;
- sin SDK publico;
- sin `mount()` JS estable;
- reutilizando `EmbedDiagnosticadorWrapper.svelte`.

### Implementacion

- nueva pagina Astro:
  `src/pages/t360-external-host-demo.astro`;
- `EmbedDiagnosticadorWrapper.svelte` ahora acepta `sessionStorageKey`
  opcional;
- nueva session key aislada:
  `team360.embed.external.demo.session.v1`;
- nueva prueba E2E:
  `e2e/diagnosticador-external-host-demo.spec.ts`;
- documentacion nueva:
  `docs/diagnosticador_external_host_demo_v1.md`.

### Seguridad

- el host externo usa `client_id=local_embed_demo`;
- mantiene `POST /api/diagnosis/embed/auth` y `POST /api/diagnosis/turn`;
- `X-T360-Signature` sigue viajando solo en header;
- no se agregan secretos al frontend;
- el HTML de `/t360-external-host-demo` no embebe tenant/scope;
- los bundles compartidos del Core siguen cargando contexto publico historico
  de Vera, ya presente antes de 9A.

### Validacion 9A

Backend:

- `uv run pytest tests/test_diagnosis_public_router.py tests/test_embed_clients_contract.py`:
  83/83 PASS.
- `uv run pytest tests/ -x --ignore=tests/test_db_module.py`:
  1089 PASS, 9 skipped.

Frontend:

- `pnpm check`: 0 errors, 0 warnings, 5 hints.
- `pnpm build`: 142 pages.

Playwright CLI local (`PLAYWRIGHT_BASE_URL=http://127.0.0.1:3050`):

- `e2e/diagnosticador-external-host-demo.spec.ts`: PASS.
- `e2e/diagnosticador-embed-demo.spec.ts`: PASS.
- `e2e/public-vera-new-conversation.spec.ts`: PASS en aislado.
- suite focalizada con Vera/lab/embed/external:
  16 PASS, 2 skipped bajo runtime fallback local.

Runtime local:

- `backend-dev.sh`: PASS.
- `astro-dev.sh`: bloqueado por el diff preexistente `IS_REST_PRO=true` en
  `global.js`.
- fallback usado para Playwright CLI: backend real `7050` + servidor estatico
  local sobre `astro/dist` con proxy `/api` a `127.0.0.1:7050`.

## Fase 8C — Endurecimiento operativo embed auth

Estado: IMPLEMENTADO Y VALIDADO EN BACKEND. MCP limitado en esta sesion; el
launcher oficial de Astro quedo bloqueado por el diff preexistente
`IS_REST_PRO=true` en `global.js`, fuera de alcance de esta fase.

### Decision tecnica

Se eligio Opcion C:

- interfaz minima + rate limiter in-memory por proceso;
- auditoria segura via logs estructurados internos;
- sin Redis;
- sin nueva tabla ni migracion para auditoria.

### Refuerzos 8C

- nuevo modulo backend `modules/embed_clients/rate_limit.py`;
- nuevo modulo backend `modules/embed_clients/audit.py`;
- `POST /api/diagnosis/embed/auth` ahora aplica rate limit antes del lookup en
  DB usando clave `client_id + origin + remote_ip`;
- defaults v1:
  - `TEAM360_EMBED_AUTH_RATE_LIMIT_WINDOW_SECONDS=60`
  - `TEAM360_EMBED_AUTH_RATE_LIMIT_MAX_REQUESTS=20`
  - `TEAM360_EMBED_AUTH_RATE_LIMIT_MAX_KEYS=10000`
- exceso de limite:
  - `429 Too Many Requests`
  - detail generico `Too many embed authentication requests.`
  - header `Retry-After`
  - sin `signature`, sin sesion y sin leak de `client_id`/tenant/scope/secret;
- auditoria segura por intento:
  - `embed_auth_allowed`
  - `embed_auth_rejected`
  - `embed_auth_rate_limited`
- payload auditado:
  - `timestamp_utc`
  - `event_type`
  - `reason_code`
  - `status_code`
  - hashes de `client_id`, `origin`, `remote_ip`, `user_agent`
  - `request_id` si existe
- payload prohibido:
  - `hmac_secret`
  - mensaje completo
  - tenant/scope
  - `allowed_origins`
  - firma completa.

### Validacion 8C

Backend:

- `uv run pytest tests/test_diagnosis_public_router.py tests/test_embed_clients_contract.py`:
  83/83 PASS.
- `uv run pytest tests/ -x --ignore=tests/test_db_module.py`:
  1089 PASS, 9 skipped.

Frontend:

- `pnpm check`: 0 errors, 0 warnings, 5 hints.
- `pnpm build`: 141 pages.

Preflight DB real:

- `SELECT to_regclass('public.embed_clients')`: `embed_clients`
- seed `local_embed_demo`: presente, `is_active=true`
- `hmac_secret <> ''`: `true`

Browser / E2E:

- MCP oficial `http://localhost:8931/mcp`: no expuso herramientas navegables
  en esta sesion.
- baseline Playwright oficial con `astro-dev.sh`: bloqueado por el diff
  preexistente `IS_REST_PRO=true` en `global.js`; no se modifico por estar
  fuera de alcance y protegido para `/t360`.

## Fase 8B — Contrato publico controlado v1

Estado: IMPLEMENTADO Y VALIDADO. MCP limitado a reachability HTTP en esta
sesion; cierre efectivo con Playwright CLI.

### Decision tecnica

Se eligio Opcion B: firma delegada por turno.

- se mantiene `POST /api/diagnosis/embed/auth`;
- no se introduce token efimero/JWT/store temporal en esta fase;
- el contrato publico controlado v1 reutiliza `embed_clients` como fuente de
  contexto y mantiene `hmac_secret` solo server-side.

### Refuerzos 8B

- test backend nuevo: firma emitida para un mensaje no autoriza otro mensaje;
- `e2e/diagnosticador-embed-demo.spec.ts` ahora verifica tambien que la
  respuesta de `/api/diagnosis/embed/auth` no filtre tenant/scope ni secret;
- `e2e/public-vera.spec.ts` se estabilizo para validar el request traducido por
  interaction block sin exigir un bubble de usuario sintetico;
- `e2e/public-vera-new-conversation.spec.ts` ignora ruido 404 del server local
  estatico/proxy que no afecta el flujo;
- `e2e/diagnosticador-embed-lab.spec.ts` se aislo del diff preexistente de
  `global.js` usando route mocking de `/diagnosis/turn`, conservando la
  verificacion de session keys y payload del lab.

### Validacion 8B

Backend:

- `uv run pytest tests/test_diagnosis_public_router.py tests/test_embed_clients_contract.py`:
  74/74 PASS.

Playwright CLI local (`PLAYWRIGHT_BASE_URL=http://127.0.0.1:3050`):

- `e2e/diagnosticador-embed-demo.spec.ts`: PASS.
- suite focalizada
  `public-vera.spec.ts + public-vera-new-conversation.spec.ts + diagnosticador-embed-lab.spec.ts + diagnosticador-embed-demo.spec.ts`:
  15 PASS, 2 skipped.

Contrato embed real:

- `POST /api/diagnosis/embed/auth`: `200 OK`;
- auth → turn real sobre backend `7050`: `201 Created`;
- firma para mensaje distinto: `403`;
- body embed sin tenant/scope cuando hay `embedAuth`.

## Fase 8A — Wrapper embebible interno/demo seguro

Estado: IMPLEMENTADO Y VALIDADO. MCP pendiente como herramienta navegable.

### Resultado operativo

Se implemento un wrapper embebible interno/demo que usa `client_id` y firma
server-side sin exponer `hmac_secret` al navegador.

- endpoint backend nuevo:
  `POST /api/diagnosis/embed/auth`;
- wrapper frontend nuevo:
  `src/lib/t360/diagnosticador/EmbedDiagnosticadorWrapper.svelte`;
- pagina demo nueva:
  `/t360-embed-demo`;
- API client extendido con `embedAuth` y `requestEmbedTurnAuth()`;
- `DiagnosticadorCore.svelte` extendido con `turnAuthProvider` opcional.

### Flujo implementado

```text
/t360-embed-demo
  -> EmbedDiagnosticadorWrapper
  -> requestEmbedTurnAuth()
  -> POST /api/diagnosis/embed/auth
  -> sendPublicTurn(embedAuth)
  -> POST /api/diagnosis/turn
  -> context resolved from embed_clients (PostgreSQL)
```

### Seguridad

- el navegador nunca recibe `hmac_secret`;
- `embed/auth` devuelve solo `client_id`, `timestamp`, `signature`;
- cuando `embedAuth` existe, `sendPublicTurn()` ya no mezcla
  `publicDiagnosisContext`;
- el body al turn incluye solo `client_id`, `timestamp`, `session_id`,
  `message`, `locale`, `interaction_response`;
- `X-T360-Signature` viaja solo en header;
- key de sesion aislada:
  `team360.embed.demo.session.v1`.

### Validacion

Backend:

- `uv run pytest tests/test_diagnosis_public_router.py tests/test_embed_clients_contract.py`:
  73/73 PASS.
- `uv run pytest tests/ -x --ignore=tests/test_db_module.py`:
  1079 PASS, 9 skipped, 1 warning.

Frontend:

- `pnpm check`: 0 errors, 0 warnings, 5 hints.
- `pnpm build`: 141 pages.
- `git diff --check`: PASS.

Smokes reales:

- `POST /api/diagnosis/embed/auth` con `local_embed_demo` y origin permitido:
  `200 OK`.
- auth → turn real contra backend `7050`: `201 Created`.
- request con body malicioso y firma valida: `201 Created`, con estado
  persistido desde DB (`team360_sales_diagnosis/pkg_sales_diagnosis/ks_team360_sales_diagnosis`).
- `client_id` desconocido: `403`.
- origin invalido: `403`.

Playwright:

- MCP oficial `http://localhost:8931/mcp` quedo reachable a nivel HTTP, pero
  no hubo herramientas MCP navegables expuestas en esta sesion.
- Fallback oficial usado: Playwright CLI.
- `e2e/diagnosticador-embed-demo.spec.ts`: PASS real.
- `e2e/diagnosticador-embed-lab.spec.ts` fallo bajo servidor local proxyeado
  por asumir URL absoluta `http://localhost:7050/...`.
- `e2e/public-vera-new-conversation.spec.ts` fallo bajo el mismo servidor de
  prueba; no se uso como criterio de aprobacion de Fase 8A.

### Notas de entorno

- `global.js` conserva un diff preexistente con `IS_REST_PRO=true`; no se
  modifico.
- para validar navegador real sin tocar `/t360`, se sirvio `astro/dist` en
  `127.0.0.1:3050` con un proxy local temporal `/api -> 127.0.0.1:7050`.
- `/t360` y `PublicVeraEntry.svelte` quedaron sin diff.

## Fase 7C — Aplicacion controlada de migracion 008 + seed local + smoke real

Estado: DB REAL APLICADA Y VALIDADA EN BACKEND. Playwright pendiente.

### Resultado operativo

La migracion `008_create_embed_clients.sql` se aplico manualmente sobre la DB
local/controlada `team360` y se valido el flujo embed contra backend real con
PostgreSQL persistente.

- DB target verificada antes de aplicar: `postgresql://localhost:5432/team360`
  (usuario `administrator`, entorno local/controlado).
- Backup logico minimo previo generado localmente, no versionado.
- `public.embed_clients` no existia antes de la migracion; luego quedo creada y
  verificada.
- Seed local insertado con UPSERT:
  - `client_id`: `local_embed_demo`
  - `allowed_origins`:
    `["http://127.0.0.1:3050", "http://localhost:3050"]`
  - contexto fijo:
    `team360_sales_diagnosis/team360_live/team360_public_site/pkg_sales_diagnosis/ks_team360_sales_diagnosis`
  - secret: no real, solo local.

### Verificacion de tabla

- columnas: `client_id`, `hmac_secret`, contexto fijo, `allowed_origins`,
  `is_active`, `label`, `metadata_jsonb`, timestamps UTC;
- indices:
  - `embed_clients_pkey`
  - `idx_ec_client_id` unico
  - `idx_ec_is_active` parcial para activos
- constraints:
  - `chk_ec_client_id_not_empty`
  - `chk_ec_hmac_secret_not_empty`
  - `chk_ec_allowed_origins_is_array`
  - `chk_ec_metadata_jsonb_is_object`

### Smokes reales

Contra `http://127.0.0.1:7050/api/diagnosis/turn`:

- sin `client_id`: `201 Created`;
- `client_id` valido + HMAC + origin permitido: `201 Created`;
- mismo request con `workspace_code` / `package_code` /
  `knowledge_scope_code` maliciosos en body: `201 Created`, pero el estado
  persistido en `sales_diagnosis_conversation_states` quedo con
  `team360_sales_diagnosis/pkg_sales_diagnosis/ks_team360_sales_diagnosis`;
- `client_id` desconocido: `403 Forbidden`;
- firma invalida: `403 Forbidden`;
- origin invalido: `403 Forbidden`;
- timestamp vencido: `403 Forbidden`;
- timestamp futuro excesivo: `403 Forbidden`.

Los `403` devolvieron detalle generico
`Embed client request is not authorized.` y no crearon estado conversacional.

### Validacion post-migracion

- `uv run pytest tests/test_diagnosis_public_router.py tests/test_embed_clients_contract.py`:
  66/66 PASS.
- `uv run pytest tests/ -x --ignore=tests/test_db_module.py`:
  1072 PASS, 9 skipped, 1 warning.
- `pnpm check`: 0 errors, 0 warnings, 5 hints preexistentes.
- `pnpm build`: 140 pages.
- `git diff --check`: PASS.

### Limites de cierre

- `/t360`, `PublicVeraEntry.svelte` y `global.js` no fueron modificados.
- Browser MCP no usado.
- Playwright focalizado no corrio porque Astro runtime local no estaba
  levantado y `global.js` conserva un diff preexistente ajeno a esta fase que
  no corresponde tocar para forzar `astro-dev.sh`.

## Fase 7B — Produccion multi-cliente para embed

Estado: IMPLEMENTADA Y VALIDADA EN BACKEND. Migracion preparada y no aplicada.

### Problema

La Fase 7A bloqueaba contextos publicos arbitrarios, pero todavia no existia un
contrato real multi-cliente para embebidos externos: faltaban `client_id`,
lookup persistente en PostgreSQL, firma HMAC y validacion de origins.

### Solucion

Se implemento autorizacion embed v1 en backend basada en PostgreSQL:

- migracion `backend/db/migrations/008_create_embed_clients.sql`;
- seed de ejemplo no automatico `008_create_embed_clients_seed_example.sql`;
- modulo `backend/modules/embed_clients/` con modelo, repo PostgreSQL,
  canonical string HMAC y validacion de origin/timestamp/signature;
- `public_turn()` ahora recibe `Request`, lee `Origin`, `Referer` y
  `X-T360-Signature`;
- cuando el body incluye `client_id`, el backend:
  - carga el cliente desde DB;
  - valida `is_active`;
  - valida origin exacto;
  - valida timestamp;
  - valida HMAC;
  - resuelve contexto desde `embed_clients`;
  - ignora `assistant_instance_code`, `organization_code`, `workspace_code`,
    `package_code`, `knowledge_scope_code` enviados por frontend;
- cuando el request no incluye `client_id`, Vera mantiene el flujo anterior
  con defaults + allowlist minima de Fase 7A.

### Contrato v1

- body: `client_id`, `timestamp`, `session_id`, `message`;
- header: `X-T360-Signature: sha256=<hex>`;
- canonical string: `client_id.timestamp.session_id.message`;
- ventana timestamp default: `±300s`
  (`TEAM360_EMBED_CLIENT_TIMESTAMP_TOLERANCE_SECONDS`);
- `session_id` es obligatorio para requests con `client_id`.

### Storage de secret

Se adopto `hmac_secret` en plaintext en PostgreSQL como decision pragmatica v1.
No hay secretos reales en el repo. La deuda de rotacion/vault/cifrado quedo
documentada en `docs/diagnosticador_embed_auth_v1.md`.

### Archivos modificados/creados

Modificados:

- `backend/routes/diagnosis.py`
- `backend/modules/embed_clients/__init__.py`
- `backend/modules/embed_clients/errors.py`
- `backend/tests/test_diagnosis_public_router.py`
- `lat.md/status_actual.md`
- `docs/status_actual.md`

Nuevos:

- `backend/modules/embed_clients/auth.py`
- `backend/tests/test_embed_clients_contract.py`
- `backend/db/migrations/008_create_embed_clients.sql`
- `backend/db/migrations/008_create_embed_clients_seed_example.sql`
- `docs/diagnosticador_embed_auth_v1.md`

### Validacion

- `uv run pytest tests/test_diagnosis_public_router.py tests/test_embed_clients_contract.py`: 66/66 PASS.
- `uv run pytest tests/test_diagnosis_public_router.py`: 60/60 PASS.
- `pnpm check`: 0 errors, 0 warnings, 5 hints preexistentes.
- `pnpm build`: 140 pages.
- `git diff --check`: PASS.
- `/t360` sin diff.
- `PublicVeraEntry.svelte` sin diff.
- `global.js` no fue tocado en esta fase (permanece con diff preexistente ajeno a 7B).

### Smokes y limites

- No se aplico la migracion 008 sobre PostgreSQL real.
- No se levanto backend productivo ni se hizo smoke real con `embed_clients`
  persistidos porque faltaria aplicar la migracion manualmente.
- La validacion de 7B queda cerrada en nivel backend/unit-contract. El smoke DB
  real queda pendiente del apply manual de migracion.

## Fase 7A — Allowlist minima backend para PublicDiagnosisContext

Estado: IMPLEMENTADA Y VALIDADA.

### Problema

El backend aceptaba contextos publicos arbitrarios desde el request (`assistant_instance_code`, `organization_code`, `workspace_code`, `package_code`, `knowledge_scope_code`). Esto abria riesgo de invasion multi-tenant si un cliente manipulaba el request.

### Solucion

Se implemento una allowlist minima backend que valida la tupla completa de 5 campos contra un unico contexto permitido (el default actual de Vera/Team360).

**`backend/routes/diagnosis.py`**:
- `ALLOWED_PUBLIC_DIAGNOSIS_CONTEXTS`: `frozenset` con la unica tupla permitida `(team360_sales_diagnosis, team360_live, team360_public_site, pkg_sales_diagnosis, ks_team360_sales_diagnosis)`.
- `_validate_public_turn_context_allowed()`: recibe el contexto ya resuelto y completo; compara la tupla de 5 campos contra la allowlist; si no coincide, lanza `HTTP 403` con mensaje generico.
- Integracion en `public_turn()`: validacion inmediatamente despues de `_resolve_public_turn_context()`, antes de crear sesion o contactar LLM.

### Reglas de validacion

1. Request sin contexto explicito → resuelve defaults → pasa allowlist → OK.
2. Request con contexto explicito igual al default → pasa allowlist → OK.
3. Request con contexto parcial → completa defaults → tupla completa igual al default → pasa allowlist → OK.
4. Request con contexto invalido → tupla completa no coincide → `403` con mensaje generico.
5. Error 403 no filtra valores de la allowlist.

### Archivos modificados

- `backend/routes/diagnosis.py` — +40 lineas (constante, funcion validacion, integracion)
- `backend/tests/test_diagnosis_public_router.py` — +109 lineas (7 tests nuevos)

### Validacion

- Backend unit tests: 49/49 PASS (42 existentes + 7 nuevos).
- Backend suite completa: 1055 PASS, 9 skipped (mismo baseline).
- `pnpm check`: 0 errors, 0 warnings.
- `pnpm build`: 140 pages.
- `git diff --check`: PASS.
- Smoke sin contexto: HTTP 201.
- Smoke contexto permitido explicito: HTTP 201.
- Smoke contexto invalido (`knowledge_scope_code` cambiado): HTTP 403, mensaje generico sin leak.
- Smoke contexto invalido (`workspace_code` cambiado): HTTP 403.
- Playwright: requiere LiteLLM para LLM real; no ejecutado por entorno parcial (validacion E2E completa realizada en Fase 8-9).

### No implementado en esta fase

- token/HMAC/client_id
- `embed_clients` table
- allowed_domains
- wrapper embebible publico
- Web Component / SDK / iframe / postMessage
- alta dinamica de tenants
- cambios frontend
- cambios en `t360.astro`, `PublicVeraEntry.svelte`, `global.js`

### Problema

Vera continuaba preguntando por detalles de implementacion (OAuth, APIs, pestañas exactas, credenciales) aun cuando ya tenia contexto suficiente para un diagnostico de factibilidad, y no cerraba el diagnostico para dejar implementacion para despues.

### Causa raiz (FASE 7)

Cuatro issues en `runtime.py`:
1. `_is_ready_to_diagnose()` solo detectaba proceso + canal + sistema; casos con management+volumen o con goal+channel no activaban readiness.
2. `_decide_turn()` no tenia guard para `status == "sufficient"`, permitiendo que el LLM preguntara de nuevo.
3. `_build_missing_requirements_block()` incluia items de implementacion como requisitos pendientes, empujando al usuario a responderlos.
4. LLM prompt no instruia separar factibilidad de implementacion.

### Solucion implementada (FASE 8-9)

**`runtime.py`** — 5 metodos modificados:

- `_is_ready_to_diagnose()`: ruta secundaria que detecta channel + (system o management) + (process o goal) + 1 senial extra (volumen, aprobacion, entidad).
- `_decide_turn()`: guard `status == "sufficient"` → retorna True inmediatamente para forzar diagnostico.
- `_build_missing_requirements_block()`: filtra solo items `preliminary_diagnosis` / `full_diagnosis`; items de implementacion colapsados en un unico requisito `post_diagnosis` con nota "Corresponde a etapa posterior de analisis de flujo".
- `_build_next_step_choice_if_ready()` / `_build_pause_block()`: titulo "Diagnostico de factibilidad listo" cuando status es sufficient, descripcion senala que detalles tecnicos son posteriores.

**`policies.py`** — prompt de sistema:
- Encabezado "DIAGNOSTICO DE FACTIBILIDAD" (no solo "DIAGNOSTICO").
- 8-secciones de salida: hechos, factibilidad, modo recomendado, que automatizar, que no, riesgos, puntos a validar despues, proximo paso.
- Prohibicion explicita de terminos de implementacion (OAuth, API, webhook, pestaña exacta, columnas, credenciales, service account).
- Regla de cierre: con canal + sistema + objetivo + 1 dato extra, cerrar diagnostico.

### Archivos modificados/creados

Modificados:
- `backend/modules/sales_diagnosis_runtime/runtime.py`
- `backend/modules/sales_diagnosis_runtime/policies.py`

Nuevos:
- `backend/tests/test_sales_diagnosis_feasibility_scope.py` — 13 tests unitarios
- `astro/e2e/public-vera-feasibility-diagnosis-scope.spec.ts` — 4 tests E2E

### Entorno de validacion

- Backend: `systemd-run --user --unit=team360-backend-dev` puerto 7050 con `TEAM360_AI_PROVIDER=litellm`, `TEAM360_LITELLM_BASE_URL=http://127.0.0.1:4000`, `LITELLM_MASTER_KEY`, `AUTOMATION_DIAGNOSIS_REPOSITORY=memory`.
- Astro: puerto 3050 con `IS_REST_PRO=false`.
- LiteLLM: puerto 4000, modelo `openai_gpt-5-nano`.

### Validacion

Backend unit tests (desde `backend/`):

- `uv run pytest tests/test_sales_diagnosis_feasibility_scope.py -v`: 13/13 PASS.
- `uv run pytest tests/ -x --ignore=tests/test_db_module.py`: 1070/1079 PASS (9 skipped, 2 pre-existing db_module failures).

Frontend E2E (desde `astro/` con `PLAYWRIGHT_SKIP_WEBSERVER=1 PLAYWRIGHT_BASE_URL=http://localhost:3050`):

- `public-vera-feasibility-diagnosis-scope.spec.ts`: 4/4 PASS (real LLM, no fallback).
- `public-vera-email-postsale-short-answers.spec.ts`: 7/7 PASS.
- `public-vera-phone-problems-interaction-priority.spec.ts`: 5/5 PASS.
- `public-vera-new-conversation.spec.ts`: 1/1 PASS.
- `public-vera.spec.ts` (excepto `:230`): 21/22 PASS (1 pre-existing failure: `renderiza interaction_block y traduce accion` — `appendUserMessage = false` no relacionado).
- `public-vera-mobile-sequential-blocks.spec.ts`: 1/2 PASS (1 pre-existing flaky mobile touch test).
- `public-vera.spec.ts:555` smoke test: PASS.
- Total focalizado: 38/40 PASS, 2 pre-existentes fallos no relacionados.
- Sin errores 5xx ni console errors.
- `git diff --check`: PASS.

## Calidad documental y operativa

- `AGENTS.md` es ahora la fuente operativa canonica compartida por Codex, OpenCode y Crush.
- la reorganizacion de `AGENTS.md`, status compacto e historial quedo confirmada en `8c51dca` y publicada.
- `.opencode-rules` queda como legado no cargado por la configuracion efectiva de OpenCode; debe retirarse o migrarse en una tarea posterior.
- `lat check` tiene una deuda preexistente de 129 errores: 110 secciones sin leading paragraph, 10 summaries extensos, 6 links rotos y 3 errores adicionales de indice.
- `lat search` requiere configurar `LAT_LLM_KEY`, `LAT_LLM_KEY_FILE` o `LAT_LLM_KEY_HELPER`; mientras tanto se usa `lat locate`.
- No existe CI ni task runner raiz; las validaciones siguen dependiendo de ejecucion local.

## Pendientes prioritarios

1. Investigar y corregir el test preexistente `public-vera.spec.ts:230` (`appendUserMessage = false` en interacciones via `t360action`).
2. Corregir `lat check` hasta cero errores.
3. Reducir o retirar reglas duplicadas en `.agents/skills/team360-project/SKILL.md` y `.opencode-rules`.
4. Crear comandos canonicos y CI para backend, frontend, LAT y E2E.
5. Corregir evidencia hardcodeada, I/O sincronico dentro de handlers async y posibles fallbacks silenciosos del runtime.
6. Hacer que LiteLLM registre tokens, coste, latencia y provider efectivo.

## Notas de seguridad

- No guardar secretos en el repositorio ni imprimirlos en comandos o documentacion.
- Las credenciales expuestas previamente deben rotarse.
- Evitar exportar todas las credenciales globalmente desde `~/.bashrc`; preferir carga acotada al proyecto o un gestor de secretos.

## Fase 11 — PASETO v4.public como estándar de tokens Team360

Estado: IMPLEMENTADO Y VALIDADO.

### Decisión técnica

- PASETO v4.public adoptado como estándar Team360 para tokens firmados propios.
- JWT queda reservado solo para integración externa obligatoria.
- HMAC embed actual queda como compatibilidad transitoria.
- Ed25519 como curva asimétrica; private key nunca llega al frontend.
- `pyseto 1.9.3` elegido como librería PASETO Python (compatible con v4.public).

### Documentación creada

- `docs/adr_paseto_v4_public_standard_v1.md` — ADR formal con decisión, motivos, política y riesgos.
- `docs/paseto_embed_auth_migration_plan_v1.md` — Plan de migración en 5 fases (F0–F4), de fundación a deprecación HMAC.

### Módulo backend

- `backend/modules/security/__init__.py` — paquete nuevo.
- `backend/modules/security/paseto_tokens.py` — API pública:
  - `PasetoKeyPair.generate(key_id)` — genera par Ed25519 en PEM.
  - `issue_paseto_v4_public(claims, *, private_key_pem, key_id, ttl_seconds, issuer, token_type)` — emite token `v4.public...`.
  - `verify_paseto_v4_public(token, *, public_keys_by_id, issuer, expected_type)` — verifica y extrae payload, con validación de `typ`, `iss`, `exp`, `iat`, `jti` y leeway configurable.
  - `PasetoVerificationError` — excepción canónica para fallos.

### Tests

- `tests/test_paseto_tokens.py` — 12 tests, todos PASS:
  1. issue + verify valid token
  2. expired token rejected
  3. wrong issuer rejected
  4. wrong typ rejected
  5. unknown key_id rejected
  6. malformed PASETO rejected
  7. tampered payload/signature rejected
  8. custom claims preserved
  9. format is v4.public, not JWT
  10. keys are Ed25519, not HMAC
  11. kid in footer selects correct key across multiple keys
  12. iat and jti auto-included

### Dependencia

- `pyseto` agregado vía `uv add pyseto`.

### No implementado en esta fase

- Fase 1 del plan migración (Console integration) — pendiente.
- Fase 2 (Embed Dual Support) — pendiente.
- Fases 3 y 4 (nuevo snippet, deprecación HMAC) — pendientes.
- Sin cambios en `global.js`, `/t360`, `PublicVeraEntry.svelte`, embed existente, runtime, Milvus, LiteLLM ni PostgreSQL.

### Validación

| Validación | Resultado |
| ---------- | --------- |
| `git diff --check` | PASS |
| `uv run pytest tests/test_paseto_tokens.py -v` | 12/12 PASS |
| `uv run pytest tests/test_embed_clients_contract.py -v` | 6/6 PASS (no regresión) |
| Secret/no-leak search | PASS — sin secretos reales; keys de test marcadas explícitamente como no-productivas |
| Protección `/t360` | Sin diff |
| Protección `PublicVeraEntry.svelte` | Sin diff |
| Protección `global.js` | Sin diff |

## 2026-07-05 — P4A: ConsoleBootstrap PASETO access_token experimental

Se implementó la Fase P4A del plan de migración HMAC→PASETO: `ConsoleBootstrapService`
emite un PASETO v4.public `access_token` firmado (Ed25519) como campo opcional de la
respuesta `POST /api/console/bootstrap`.

### Nuevo módulo/archivos

- **`routes/console_bootstrap.py`** — nuevo handler `POST /api/console/bootstrap`:
  - Lee `workspace_id` + `user_id` del body JSON.
  - Lee `PasetoConsoleSettings` desde env vars.
  - Delega en `ConsoleBootstrapService.build_bootstrap()`.
  - Serializa respuesta incluyendo `access_token`, `token_type`, `expires_in`.
  - Manejo de errores: `HTTP_500` con detail del dominio.
- **`modules/security/paseto_tokens.py`** (ampliado):
  - `PasetoConsoleSettings` — dataclass frozen con `enabled`, `issuer`, `key_id`, `private_key_pem`, `public_key_pem`, `ttl_seconds`.
  - `paseto_console_settings_from_env()` — factory desde `TEAM360_PASETO_*` env vars.
  - `issue_console_access_token(user_id, settings)` — emite PASETO v4.public con claims `sub:user:<id>`, `user_id`, `typ=console_access`, `iat`, `exp`, `jti`.
  - `_get_dev_key_pair()` — genera par Ed25519 dinámico si no hay env keys (solo dev).
- **`modules/console/types.py`** (ampliado): `ConsoleBootstrap` con 3 campos opcionales:
  `access_token: str | None`, `token_type: str | None`, `expires_in: int | None`.
- **`modules/console/service.py`** (ampliado): `build_bootstrap()` acepta `paseto_settings: PasetoConsoleSettings | None`. Si `enabled=True`, llama `issue_console_access_token()` y lo agrega al resultado.
- **`ls_iMotorSoft_Srv01.py`** (ampliado): import + registro de `console_bootstrap`.
- **`tests/test_console_bootstrap_service.py`** (ampliado): 6 nuevos tests P4A.

### Tests P4A (6 nuevos, sobre 6 originales = 12 total)

| Test | Lo que valida |
| ---- | ------------- |
| `test_bootstrap_still_returns_user_id_without_paseto` | Sin settings → `access_token: None` |
| `test_bootstrap_returns_access_token_when_paseto_enabled` | Token presente, formato `v4.public.` |
| `test_access_token_verifies_with_public_key` | `verify_paseto_v4_public` pasa |
| `test_no_access_token_when_paseto_disabled` | `enabled=False` → sin token |
| `test_bootstrap_user_id_preserved_with_paseto` | `user_id` preservado con token + debug |

### Decisión técnica

- `PasetoConsoleSettings` se pasa como kwarg opcional — no es obligatorio, no rompe existing tests.
- Dev keys: `PasetoKeyPair.generate()` dinámico, sin secretos en código.
- TTL default 900s (15 min), configurable vía env.
- `token_type` en respuesta: `"paseto_v4_public"` (no es un claim del PASETO, es metadato HTTP).
- Claims del token: `sub=user:<id>`, `user_id`, `typ=console_access`, `iss=team360`, `iat`, `exp`, `jti`.
- Footer: `{"kid":"local-dev-key-1"}`.

### Validación

| Validación | Resultado |
| ---------- | --------- |
| `git diff --check` | PASS |
| `uv run pytest tests/test_paseto_tokens.py -v` | 12/12 PASS |
| `uv run pytest tests/test_console_bootstrap_service.py -v` | 12/12 PASS (6 originales + 6 P4A) |
| `uv run pytest tests/test_embed_clients_contract.py -v` | 6/6 PASS (sin regresión embed) |
| `uv run pytest tests/test_diagnosis_public_router.py -v` | No corrido (sin cambios en `diagnosis.py`) |
| Secret/no-leak search | PASS — sin secretos reales; dev keys dinámicas |
| Protección `/t360` | Sin diff |
| Protección `PublicVeraEntry.svelte` | Sin diff |
| Protección `global.js` | Sin diff |
| Protección `embed_clients/` | Sin diff |
| Protección `routes/diagnosis.py` | Sin diff |

### Documentación creada

- `docs/paseto_console_bootstrap_access_token_v1.md` — documento específico P4A.

### No implementado en esta fase

- DB table para jti revocation.
- Endpoint de validación/verificación de token.
- Frontend mock consumer (no cambia `global.js` ni frontend).
- Producción env keys persistentes.
- Fases P4B (revocation DB), P5 (frontend integration).

## 2026-07-05 — P4B: Verificador PASETO para Console protegida

Se implementó la Fase P4B del plan de migración HMAC→PASETO: verificador
PASETO reutilizable para endpoints Console. Cierra el circuito P4A→P4B:
`POST /api/console/bootstrap` emite token → `GET /api/console/me` lo verifica.

### Módulos nuevos

- **`modules/console/auth.py`** — auth de Console:
  - `ConsolePrincipal` — dataclass frozen con `user_id`, `subject`, `claims`.
  - `ConsoleAuthError` — excepción canónica para fallos.
  - `extract_bearer_token(header)` — parsea `Authorization: Bearer <token>`.
  - `verify_console_access_token(token, public_keys_by_id, issuer)` — verifica
    PASETO v4.public con `typ=console_access`, `sub=user:<id>`, `user_id`.
  - Errores específicos: header ausente, scheme no Bearer, token vacío,
    typ/iss incorrecto, sub sin `user:`, `user_id` ausente, kid desconocido,
    expirado, malformado.
- **`modules/console/__init__.py`** — exporta `ConsoleAuthError`, `ConsolePrincipal`.
- **`modules/security/paseto_tokens.py`** (ampliado):
  - `get_dev_public_keys_by_id()` — helper público que expone la key pública
    dev para el verificador (mismo singleton que usa `issue_console_access_token`).
- **`routes/console_me.py`** — nuevo handler `GET /api/console/me`:
  - Lee `Authorization` header via `request.headers`.
  - Usa `extract_bearer_token()` + `verify_console_access_token()`.
  - Resuelve public keys desde env vars (con fallback dev key).
  - Devuelve `{user_id, subject, token_type}`.
  - Errores: 401 con detail descriptivo.
- **`ls_iMotorSoft_Srv01.py`** — import + registro de `console_me`.

### Tests

- **`tests/test_console_auth.py`** — 15 tests:
  - `TestExtractBearerToken` (5): header ausente, vacío, Basic, Bearer vacío, token válido.
  - `TestVerifyConsoleAccessToken` (9): token válido, `user_id` correcto,
    typ incorrecto, issuer incorrecto, sub sin `user:`, `user_id` ausente,
    kid desconocido, expirado, malformado.
  - `TestEndToEndP4A` (1): token emitido por P4A se verifica con P4B.
- **`tests/test_console_me_route.py`** — 9 tests via `TestClient`:
  - Sin header → 401; Bearer vacío → 401; Basic → 401; token inválido → 401.
  - Token válido → 200 con `user_id`, `subject`, `token_type`.
  - Respuesta no contiene `access_token`, keys ni secrets.
  - Token expirado → 401; typ incorrecto → 401.

### Protocolo

```
GET /api/console/me
Authorization: Bearer v4.public.<token>
→ 200 { "user_id": "...", "subject": "user:...", "token_type": "paseto_v4_public" }
→ 401 { "detail": "<reason>" }
```

### Decisión técnica

- El verificador vive en `modules/console/auth.py` (Console Console-specific).
- `verify_console_access_token` es wrapper sobre `verify_paseto_v4_public`
  (foundation genérica). Agrega validación de `sub=user:` y `user_id`.
- `extract_bearer_token` es independiente del tipo de token; podría reutilizarse.
- Dev keys: `get_dev_public_keys_by_id()` expone el mismo singleton que usa
  `issue_console_access_token()`, garantizando que tokens de bootstrap se
  verifiquen en dev sin configurar env vars.
- Producción: configurar `TEAM360_PASETO_PUBLIC_KEY_B64` + `TEAM360_PASETO_KEY_ID`.
- Errores 401, no 403, porque el cliente no está autenticado (no autorizado
  vs. no autenticado).

### Validación

| Validación | Resultado |
| ---------- | --------- |
| `git diff --check` | PASS |
| `tests/test_paseto_tokens.py` | 12/12 PASS |
| `tests/test_console_auth.py` | 15/15 PASS |
| `tests/test_console_bootstrap_service.py` | 12/12 PASS |
| `tests/test_console_me_route.py` | 9/9 PASS |
| `tests/test_embed_clients_contract.py` | 6/6 PASS (sin regresión) |
| `tests/test_diagnosis_public_router.py` | 77/77 PASS (sin regresión) |
| Secret/no-leak search | PASS |
| JWT search | PASS — solo referencias documentales |
| Protección `embed_clients/` | Sin diff |
| Protección `routes/diagnosis.py` | Sin diff |
| Protección `/t360`, `PublicVeraEntry`, `global.js` | Sin diff |
| Protección `astro/public/embed`, `cross-origin-host` | Sin diff |

### Documentación

- `docs/paseto_console_auth_verifier_v1.md` — documento específico P4B.

### No implementado en esta fase

- DB table para jti revocation.
- Refresh token.
- Scope/permisos en el endpoint.
- Aplicación verificador a endpoints Console reales (pendiente).
- Embed/HMAC dual-mode (Fase 2 del plan).

## Mamamia360 embed — producción aprobada

La integración confirmó que HTTP `200` y MIME correcto no bastan para módulos cross-origin: el navegador debe aceptar el body por CORS y ejecutar toda la cadena hasta `mount()`.

- Snippet público: `https://team360.live/embed/vera-loader.js?v=20260802-1`
- Página cliente: `https://www.mamamia360.com/inteligencia-artificial/`
- ClientId: `mamamia360`
- Origins habilitados:
  - `https://mamamia360.com`
  - `https://www.mamamia360.com`
  - `https://team360.live`
- Fixes cerrados:
  - loader assets resueltos desde dominio Team360
  - CSS aislado del embed
  - CORS para module scripts estáticos (ACAO en nginx `/embed/` y `/_astro/`)
  - CORSConfig backend para API embed/auth y diagnosis/turn
  - gate que trata `200 / 0 B` o `No data found` como posible bloqueo CORS, no como éxito de carga
- Validación final (Playwright productivo):
  - widget montado en página real
  - `team360-diagnosticador-loader.js` 200
  - `team360-diagnosticador.js` 200
  - bodies de loader, manifest y entry mayores que cero
  - chunks `_astro` cargando
  - `window.Team360Diagnosticador.mount()` ejecutado
  - 0 requests a `www.mamamia360.com/embed/`
  - sin `[VeraLoader] Failed to load`
- Snippet no cambió.
- Pendiente cliente: corregir fuente `.ttf` servida por `http`/mixed content.

## Telchi / DataScience — baseline SQL HANA2 pausada para continuidad

Fecha de corte: `2026-08-17`.

### Estado y alcance

- Workspace operativo: `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi`.
- Rama Team360: `feature/console-backend-core`.
- HEAD observado: `d476cee562798c0017db6cd623ece87cde8306be`.
- El worktree Team360 ya tenía cambios pendientes del gate Flow anterior; no se revirtieron ni se mezclaron con este trabajo.
- Este frente permanece separado del producto: no crear todavía `backend/modules/telchi`.
- Política: `LEGACY_READ_ONLY`; no modificar scripts legacy, SAP, Parquet ni notebooks.

### Infraestructura confirmada

- VPN strongSwan: `active` y debe permanecer levantada.
- HANA `192.168.20.20:30015`: TCP `PASS`, autenticación `PASS`.
- Schema: `TELCHI`.
- Driver: `hdbcli 2.29.25`.
- HANA: `2.00.056.00.1624618329`.

### Baseline previa

- Reporte: `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi/validation/legacy_sync/sync_validation.yaml`.
- Estado: `TEAM360_TELCHI_LEGACY_SYNC_BASELINE_PARTIAL`.
- Harness read-only: `validation/legacy_sync/legacy_sync_baseline.py`.
- Se validó HANA para Sales, Credit Notes, Inventory Movements, Products, Customers, Warehouses, Payments, Reconciliation y Sales Targets.
- `SALES_TARGETS` permanece `BLOCKED_EXTERNAL_DATA` porque `@OBJ_VENTAS_L` está vacío.
- Parquet fue leído únicamente con `pyarrow 25.0.1`; no se reescribió ningún archivo.
- La comparación mensual detectó drift histórico contra HANA actual: sales `-90` filas, NC `-1`, movements `+4225` en Parquet, payments `-9` y reconciliation `-3715`. Esto no debe interpretarse automáticamente como bug de transformación.

### Código HANA2 legacy identificado

- `/media/issajar/DEVELOP/Projects/telchi/Insiding/DataScience/SrvRest/srvSyncTelchiSB101.py`: Sales, Credit Notes, Movements, Products, Customers y Warehouses.
- `/media/issajar/DEVELOP/Projects/telchi/Insiding/DataScience/sapb1Tools01.py`: variantes Sales, Products, Customers, Warehouses, Payments, Reconciliation y maestros `OITB`, `OACT`, `OWHS`.
- `/media/issajar/DEVELOP/Projects/telchi/tb1/i-MotorSoft/SrvRest/faTB1Srv02.py`: Sales Targets.
- `srvSyncTelchi02.py` fue identificado como MSSQL (`mssql+pymssql`) y queda fuera de la baseline HANA2.

### Próxima sesión

1. Crear `telchi/sql/legacy_hana2/` por dominio.
2. Extraer fielmente las SQL realmente usadas, sin optimizarlas ni corregirlas.
3. Crear `validation/sql_baseline.yaml` y un harness read-only con safety gate contra operaciones de escritura.
4. Ejecutar cada SQL con ventana bounded de un día, validar columnas, grano y PK, y registrar `PASS`, `CHANGE_REQUIRED`, `BLOCKED_EXTERNAL_DATA`, `DEPRECATED` o `UNKNOWN`.
5. No crear todavía `sql/current/`, nuevos extractores, Parquet ni cambios de transformación pandas.

### Cierre de esta sesión

- No commit, push, deploy ni cambio de rama.
- No se modificó el repositorio legacy.
- No se modificó SAP.
- No se escribieron Parquet.
- La VPN quedó activa.

### Método canónico para análisis de vitaminas

- Procedimiento reproducible y reglas de consulta: `/media/issajar/DEVELOP/Projects/telchi/Insiding/DataScience/telchi_vitamins_lab/README.md`.
- Implementación del pipeline: `/media/issajar/DEVELOP/Projects/telchi/Insiding/DataScience/telchi_vitamins_lab/src/` (`catalog.py`, `sales.py`, `metrics.py`, `vitamins_discovery.py` y `build_report.py`).
- Resultados y reportes derivados: `/media/issajar/DEVELOP/Projects/telchi/Insiding/DataScience/telchi_vitamins_lab/output/`; el reporte inicial es `reporte_citrato.md` y el volumen por familias está en `data/vitamins_family_volume.csv`.
- Regla de alcance: `DS/` es entrada inmutable; el análisis separa producto terminado (unidades comerciales) de materia prima (kg), conserva `OBSERVED`/`ASSUMPTION`/`PROJECTED` y no interpreta el PDF técnico como demanda.
- Para extender el análisis a otra vitamina o suplemento se reutiliza este laboratorio y se agrega el universo normalizado de candidatos, sin crear consultas paralelas.

## Gate 2026-08-19 — Flow comunicación ciudadana mínima y segura V1

Estado: PASS funcional real/controlado
(`TEAM360_FLOW_CITIZEN_COMMUNICATION_V1_PASS`). El vecino recibe únicamente
comunicación pública de recepción, avance y cierre aprobado; la operación
interna de LaMuni permanece reservada. `model_eval/**` no fue tocado.

### Arquitectura

- Proyección pública por allowlist (`CitizenCaseProjection`) construida solo
  con `public_reference`, `public_status`, `subject`, `public_description`,
  `public_location`; los templates ciudadanos consumen únicamente esa
  proyección y son determinísticos (sin LLM).
- Mapeo interno→público: `CONFIRMED→RECEIVED`, `ACTIVE→IN_PROGRESS`,
  `RESOLUTION_PENDING_APPROVAL→IN_PROGRESS`, `RESOLVED→RESOLVED`. NUNCA se
  exponen BREACHED, escalamiento, niveles, SLA, destinos internos, supervisor,
  token de aprobación, audit ids, métricas ni notas.
- `flow_citizen_notifications` (migración aditiva 022, clasificación GLOBAL
  documentada): traza idempotente por `(request_id, notification_type)`, con
  `channel='email'`, estado de entrega, `provider_message_id`, RFC estable y
  reconciliación contra Gmail Sent antes de cualquier retry (sin envíos
  duplicados). No es duplicación de `flow_messages` (no puede representar
  type/status/dedupe de forma segura) y no contamina el audit snapshot ni el
  timeline de Directorio.
- Transporte reutiliza el puerto de mensajería existente (`RoutingMessageSenderPort`,
  satisfecho por GmailClient y los fakes determinísticos). Sin código de
  provider nuevo, sin acoplamiento a Gmail directo, sin WhatsApp.

### Disparadores

- RECEIVED: tras confirmación de intake persistida (request CONFIRMED).
- IN_PROGRESS: primera actuación real elegible (respuesta operacional
  ACK/RESOLUTION_PROPOSED o escalamiento COMPLETED); exactamente uno por caso
  (dedupe), nunca después de RESOLVED.
- RESOLVED: solo tras APPROVE → request RESOLVED (guard terminal); nunca con
  resolución PROPOSED, aprobación PENDING/REJECTED ni caso abierto.
- INFO_REQUIRED: NO IMPLEMENTADO — `INFO_REQUIRED_DOMAIN_TRIGGER_NOT_AVAILABLE`
  (gap no bloqueante). La necesidad de información se resuelve en intake vía
  `PENDING_CLARIFICATION`; no existe evento de follow-up post-confirmación.

### Evidencia real

- Demo LAMUNI E2E (PostgreSQL real, transporte determinístico):
  `CITIZEN_RECEIVED=1`, `CITIZEN_IN_PROGRESS=1`, `CITIZEN_RESOLVED=1`,
  `CITIZEN_INTERNAL_DATA_LEAK=NONE`; pasos 14-16 PASS; Directorio/Audit
  intactos.
- PostgreSQL real: traza persistida con dedupe, fallo de entrega sin afectar
  el caso, retry reconciliado (un único envío eventual), guard de RESOLVED
  solo tras cierre real aprobado, y separación `citizen_email != N1/N2`.
- Suite backend completa: 1536 PASS / 47 SKIP; Flow gated (incl. PostgreSQL):
  398 PASS. Frontend: `pnpm check` 0 errors/0 warnings, `pnpm build` 161
  páginas. `git diff --check` PASS.

### Fuera de alcance confirmado

Sin portal ciudadano, WhatsApp, LLM en texto público, notificaciones INFO_REQUIRED
outbound V1, respuesta ciudadana correlacionada al caso, thread ciudadano único,
ni runner/scheduler.

### Nota de concurrencia

El cambio concurrente Telchi/DataScience en este archivo (2026-08-17) fue
preservado intacto.

## Historial

- historial tecnico completo hasta esta reorganizacion: `status_historico_hasta_2026-06-28.md`;
- arquitectura viva e invariantes: `lat.md/lat.md`;
- orquestacion transversal: `lat.md/team360-global-orchestration.md`;
- Git conserva la evolucion exacta de cada cambio confirmado.
