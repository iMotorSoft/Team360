# Status actual - Team360

Único estado técnico GLOBAL vigente. Este tablero resume decisiones y límites; las autoridades locales conservan el detalle y los históricos conservan los cierres, incluidos cambios aún sin commit.

Objetivo: `desarrollo` · Rama: `feature/console-backend-core` · Corte documental: security boundary hardening y follow-up Console/Auth DEV autorizado hasta 2026-10-14.

## Navegación y autoridad

Leer [AGENTS](../../AGENTS.md) para trabajo y ownership; [LAT](../../lat.md/lat.md) para invariantes. Cada frente mantiene su autoridad local, sin crear otro estado GLOBAL.

| Frente | Autoridad local / detalle | Estado vigente y límite |
| --- | --- | --- |
| Flow | [README y runbook](../backend/modules/flow/README.md), [demo](team360_flow_lamuni_demo_v1.md) | Baseline productivo desplegado; demo readiness PASS en DEV. Configuración/scheduler nuevos no declarados desplegados. |
| Diagnosis / Vera / embed | [estado local](../backend/modules/sales_diagnosis_runtime/status_actual.md), [política runtime](../../lat.md/team360-runtime-operational-policy.md), [arquitectura embed](../../lat.md/diagnosticador-embeddable-component-architecture.md) | Runtime público validado y protegido; no confundirlo con skeletons dev/product adapter históricos. |
| Messaging / Evolution | [README canónico](../backend/modules/messaging/README.md) | Adapter/latencia fija PASS en DEV; integración Telchi SQL en desarrollo y profiling investigativo del 08/10 reconocidos. Benchmark Evolution PENDING; sin habilitación productiva. |
| Telchi | [estado local](../backend/modules/telchi/status_actual.md), [CONTEXT](../backend/modules/telchi/CONTEXT.md) | Data Lake V1 cerrado; contratos comerciales candidatos sin promoción. CONTEXT sigue siendo autoridad de arquitectura, roots y etapas. |
| TelchiAI conversacional | [evidencia BIZ01](../../data/reports/telchi/biz01-conversation-v1/report.md), [fiabilidad de entrega V1](../../data/reports/telchi/delivery-reliability-v1/report.md), [README del asistente](../backend/modules/telchi/assistant/README.md) | Conversación empresarial de Presidencia en DEV: 10/10 turnos en el pipeline autenticado y persistido, alcance de negocio explícito en el estado y primera familia analítica por producto y cliente facturado. Corrección del 21/10: entrega con guarda determinística (Meta 4.096), rechazo del proveedor como fallo confirmado, falla técnica del intérprete auditada y reintentable una vez, límite por familia analítica, presentación business-first (participación acreditada 19,62 %; 35,7 % es incorrecto) y sesión DEV por inactividad/duración máxima en vez de duración fija. Implementación DEV; [reacreditación final de gates](../../data/reports/telchi/six-gates-reaccreditation-20261021/report.md) del 22/10: `SIX_GATES=VALID` sobre el digest final `283418ac…` en la política DEV `change_based_v1` (sin caducidad artificial) y `READY_FOR_MANUAL_START=YES`; la entrega WhatsApp real sigue siendo manual del owner. |
| Console / Auth | [estado local](../backend/modules/console/status_actual.md), [contrato bootstrap](console_bootstrap_contract.md), [login CLI DEV](team360_console_dev_password_login_v1.md) | PASETO vigente; enrollment/login password CLI preparado en DEV el 14/10 con rol dedicado no privilegiado. Cero passwords humanas activadas; no login web, promoción, RLS ni cambio del pool global. |
| Srv05 | [Fase 1](team360_srv05_phase1.md), [Fase 2](team360_srv05_phase2.md), [resolver estático](../backend/modules/srv05_runtime.py), [tests Fase 3](../backend/tests/test_srv05_runtime.py) | Fases 1/2/3 PASS; [Full Gate](team360_full_gate_v1.md#security-boundary-hardening-2026-10-09): Structural PASS / Operational DEGRADED. Fronteras técnicas cerradas; readiness DEGRADED por fixtures/evidencia, sin promoción. |

## Base técnica y coordinación

Las reglas arquitectónicas viven en LAT; este resumen no redefine sus contratos ni demuestra disponibilidad actual de servicios.

- Frontend Astro 6 + Svelte 5; backend Litestar.
- PostgreSQL 18 es verdad operacional; Milvus 2.6 es índice derivado y nunca decide permisos.
- DB: `psycopg 3 async`, pools separados y SQL en repositories, según [política DB](../../lat.md/postgres-driver-policy.md).
- LiteLLM mediante aliases/adapters; Vera usa `openai_gpt-5.4-nano` y Chat Completions. URLs `/t360`: únicamente `astro/src/components/global.js`.
- Benchmark Milvus vs pgvector ejecutado/versionado en `804547d`: no pendiente salvo cambio de corpus, escala o condiciones. [Cierre preservado](status_historico_hasta_normalizacion_2026-10-06.md#estado-general).
- Flow expone `ROUTE_HANDLERS` desde `routes.py`, montados una sola vez por el registry.
- GLOBAL: lectura para todos, un solo writer coordinado. Los scopes locales disjuntos pueden continuar sin alterar GLOBAL; una ventana documental no autoriza código, infraestructura, Git ni producción. [Ownership canónico](../../lat.md/team360-global-orchestration.md).

## Srv05 y cobertura real

El PASS de las fases describe compatibilidad y modelado estático; no certifica todo Team360 ni una migración productiva. No se ejecutaron nuevamente esos gates en esta tarea documental.

- Fase 1 histórica PASS: Srv05 reexportaba Srv01. Ahora [aislamiento Evolution](team360_srv05_evolution_isolation.md): app distinta, base legacy compartida y extensión Srv05 opt-in; sin lifecycle manager nuevo. Srv01 no importa/monta Evolution con ningún env. Evolution = primera capability Srv05-only validada (ON con fixtures, sin transporte productivo).
- Fase 2 PASS: inventario declarativo, bindings y dependencias; no sustituye el registry HTTP ni el bootstrap baseline.
- Fase 3 PASS según baseline confirmado: perfiles, resolución determinística pura y validación estática de configuración. [Implementación](../backend/modules/srv05_runtime.py) y [contratos de test](../backend/tests/test_srv05_runtime.py); no hay cierre documental separado de Fase 3 en el worktree al normalizar.
- `resolve_runtime_profile("full") != Full Team360 Gate`: `full` cubre solo el inventario registrado de Srv05, no todos los módulos, rutas y servicios de Team360.
- Sin lifecycle selectivo ni preflight operacional en el resolver: sus declaraciones no prueban credenciales, conectividad, contexto DB, permisos efectivos ni health. El Full Gate separado sí aporta preflight real fechado.
- Srv05 sigue delegando baseline Srv01 donde corresponde. Producción no se declara migrada mientras continúe usando Srv01; el último comando productivo documentado usa Srv01.
- Full Gate vigente: `TEAM360_FULL_GATE_DEGRADED`; [corrida de aislamiento](../../data/reports/team360-srv05-evolution-isolation/20261011T133928Z/full-gate-r2/report.json) Structural Srv05 OFF PASS (27 operaciones); ON fixture añade sólo Evolution (28). Revalidación del 09/10: 951 PASS / 3 skips en suite principal; backend operacional controlado PASS en garantías ejecutadas, incluidos post-close, lifespan con fixture segura y conversación/embed API. PostgreSQL/Milvus/LiteLLM READY en esa corrida, no disponibilidad actual inferida. [Gate y límites](team360_full_gate_v1.md#revalidación-2026-10-09).
- Srv05 promoción: **NO REALIZADA**; readiness del 09/10 avanza a **DEGRADED** (`TEAM360_SRV05_PROMOTION_READINESS_DEGRADED`) después de cerrar adapter DEV/bootstrap/Gupshup en source. Packaging aislado/install/import/listener PASS; Structural 28 operaciones y backend controlado PASS. Browser vivo Home/Mamamia PASS con harness opt-in, persistencia PG y cleanup. Auth DB/segundo tenant siguen sin fixtures autorizadas; ingress Gupshup real y automatización destino no certificados. [Readiness vigente](team360_srv05_promotion_readiness.md), [hardening y evidencia](../../data/reports/team360-security-boundary/20261009T182048Z/report.md). Flow/Diagnosis funcionales intactos; Full Gate DEGRADED, sin deploy ni reemplazo Srv01.

### Evidencia pendiente de promoción Srv05

La clasificación vigente incorpora la ventana de packaging y E2E seguro del 09/10. Separa garantías no ejecutadas, límites de fixture y fronteras técnicas; falta de evidencia no significa fallo funcional.

| Garantía / condición | Clasificación vigente | Evidencia pendiente / límite |
| --- | --- | --- |
| Browser/frontend E2E | PASS en alcance seguro | 41 PASS / 2 skips; Home/Mamamia con API real/HMAC y PG reload, loader/assets, Flow read-only y Console fixture. check/build DEV PASS; no certifica sitio externo productivo ni login DB |
| Identidad/RBAC real contra DB | EVIDENCE_BLOCKED_BY_MISSING_FIXTURE | BLOCKED_BY_MISSING_AUTHORIZED_IDENTITY_FIXTURE y BLOCKED_BY_MISSING_SECOND_TENANT_FIXTURE; seeds reales no autorizan impersonación. Contratos fixture PASS no sustituyen cadena DB |
| LiteLLM upstream/fallback interno | READY en alcance auditado | GET autenticados model/info y router/settings: upstreams OpenAI generación/embeddings, fallbacks activos vacíos y config read-only concordante. Falla upstream viva NOT_TESTED / NON_BLOCKING con contratos adapter PASS; no audita un proxy destino distinto |
| Lifecycle con automatización activa | PASS listener controlado / destino pendiente | Uvicorn Srv05 con hooks/pool PG/scheduler único/shutdown PASS; harness suprime ciclos, DB conserva automation=true. AUTOMATION_DELIVERY_NOT_TESTED; falta control destino o sandbox autorizado |
| Gmail/DWD y outbound Gupshup/Flow | CONDITIONAL | probe y delivery NOT_TESTED; sólo con cuenta/sandbox/target autorizados y si el alcance los exige |
| Evolution | SRV05_ONLY / NOT_REQUIRED OFF | Srv01 404 incondicional; Srv05 montaje explícito DEV-only y fail-closed. Transporte/ingress real NOT_TESTED en aislamiento, CONDITIONAL si se habilita |
| Superficies DEV/bootstrap/webhook | TECHNICAL_DEFECT CLOSED / EVIDENCE DEGRADED | Production: adapter DEV y bootstrap → 404 antes de side effects. Gupshup config ausente 503 e inválida 401 antes de body/DB/Flow; token válido requerido. Idempotencia PG PASS. Firma proveedor no documentada; compatibilidad/configuración sender/ingress real NOT_TESTED |
| SAP/HANA y API Telchi | NOT_REQUIRED | no forman parte del servidor global medido; sin promoción implícita |
| Packaging wheel | PASS / defecto cerrado | force-include de Srv05/Srv01/globalVar; venv limpio, cwd temporal, sin editable/PYTHONPATH, origins site-packages, app/OpenAPI/health/listener instalado PASS; build repetido idéntico |

No queda un **DEFECT** Diagnosis abierto por post-close ni por los 14 fallos. El packaging quedó cerrado; en cambio, la exposición DEV/bootstrap se reprodujo como frontera técnica bloqueante. Falta de identidad/segundo tenant y delivery destino son evidencia externa, no defectos demostrados.

## Messaging y Evolution

Evolution transporta WhatsApp; Team360 posee conversación, routing y auditoría. El README conserva configuración, seguridad, tabla de métricas y evidencia original de las sondas.

- `TEAM360_MESSAGING_EVOLUTION_ADAPTER_V1=PASS` y `TEAM360_MESSAGING_FIXED_RESPONSE_LATENCY_V1=PASS`: 20 pares reales, delivered/read, deduplicación y recuperación; respuesta fija, sin requests LLM.
- Overhead Team360 T0→T4: p50 56.37 ms / p95 146.04 ms; total observable T0→T6: p50 2516.86 ms / p95 2972.98 ms. No restar muestras distintas para inferir overhead.
- Perfil DEV `messaging-only` validado, PostgreSQL real y migración 026; modo normal conserva baseline/preflights. Runtime temporal cerrado y webhook local desactivado/restaurado según el cierre.
- `TEAM360_EVOLUTION_WHATSAPP_LATENCY_BASELINE_V1=PENDING`: faltan desgloses Graph/accept y hubo intento fuera de orden. La valoración observable GOOD no cierra ese benchmark ni es prueba de capacidad.
- Meta Team360 consume exclusivamente `META_TEAM360_*`, sin fallback a otros proyectos; Evolution y Team360 conservan activos propios.
- Evidencia: [reporte verificado](../../data/reports/messaging/evolution-adapter-v1/20261006-165557/verified/report.md), [README](../backend/modules/messaging/README.md#pruebas-y-benchmark-team360-only). Errores, extras y timestamps originales preservados.

Trabajo posterior válido, sin atribución de autoría: integración Messaging → Telchi SQL en desarrollo; profiling del 2026-10-08 en INVESTIGATION (`TEAM360_TELCHI_DATALAKE_PRE_SQL_PROFILE_V1=PASS`). Consulta fija DuckDB sobre Foundation read-only; PostgreSQL conserva catálogo/persistencia. Sin LLM, SAP ni promoción. [Reporte y cleanup](../../data/reports/messaging/telchi-datalake-pre-sql-profile-v1/report.md).

Condición operativa documentada al cierre del 08/10: se retiró la suscripción Meta temporal, falló restaurar el callback anterior y no quedó suscripción Meta Team360 activa. No es una inspección actual ni se corrige en esta ventana.

## Telchi

El estado local distingue Foundation productiva de candidatos semánticos. Este tablero no cambia CURRENT, consulta SAP ni promueve capacidades.

- `TELCHI_DATALAKE_V1_CLOSED=YES`; Receivables & Collections Extension V3 PASS productivo. V1/V2 permanecen como rollbacks históricos.
- CURRENT vigente tras la promoción de ventas del 30/10/2026: `foundation_38680850adc058b1bb11887632b7b681`, Reference `v2_sales_e02883116f4b4991c396010a`; anterior `foundation_afd08d9eca6a725be53cdc3f9d5709c9` retenido e inspeccionable. La transición se hizo con el wrapper previo; el mecanismo corregido revalidó la publicación de forma idempotente con CAS, journal y reader verificado, sin autorización nominal obligatoria. [Estado local](../backend/modules/telchi/status_actual.md).
- Temporal Commercial Purpose V1 PASS semántico, sin promoción; candidate `foundation_15cfdba7ff7ff94011d26fa1b93bf266`. Validación temporal sustituye ese blocker, no convierte todo el cierre source-gap en PASS.
- Source Gap Closure y Product Commercial Semantics siguen con degradaciones documentadas, UNKNOWN y gaps explícitos; brand e importe neto por producto no resueltos. [Estado y evidencia local](../backend/modules/telchi/status_actual.md).
- Frontend TelchiAI aparece como trabajo local untracked: no gate/deploy declarado. CONTEXT no se sustituye por un status y investigation permanece intacta.
- TelchiAI conversacional: implementación DEV del 21/10/2026 con alcance empresarial explícito (categoría, producto, cliente, dimensión, conjunto de períodos y foco de servicio), plan de negocio de vocabulario cerrado y la familia `sales.commercial_line_amount_by.v1` (importe de líneas comerciales BS por producto o por cliente facturado, reconciliación de tolerancia cero). Permiso propio registrado en DEV por el mecanismo local idempotente, sin asignaciones ni cambio de FULL_ACCESS. `BIZ01_CONVERSATION_PASS=YES` sobre el pipeline autenticado y persistido; sin entrega WhatsApp, sin promoción y sin cambios en Foundation, SAP, RBAC de otros módulos ni servicios compartidos.
- TelchiAI — [fiabilidad de entrega WhatsApp V1](../../data/reports/telchi/delivery-reliability-v1/report.md): corregidas las causas demostradas de respuestas perdidas (límite de 4.096 caracteres del canal, rechazo del proveedor, falla técnica del intérprete, límite heredado entre familias, listados no solicitados y cierre por duración fija de la sesión DEV). Validación: BIZ01 real 10/10 con respuestas de 446–1.451 caracteres, 633 tests del asistente PASS y sonda live del intérprete con lenguaje informal PASS. Reacreditación final del 22/10: `SIX_GATES=VALID` (seis garantías `PASS`/`real` reejecutadas contra el digest final `283418ac…`, registro DEV v2 `change_based_v1`) y `READY_FOR_MANUAL_START=YES`; 753 tests PASS. Se corrigió además un bloqueo independiente: el control privado conservaba la duración fija legacy de 600 s, que hacía fallar el arranque con `idle_timeout_exceeds_max_duration`; ahora aplica 15 min de inactividad y 4 h máximas. `WHATSAPP_E2E=NOT_RUN`: no se enviaron mensajes, no se activaron webhooks, no se reiniciaron servicios compartidos y **no se rotaron credenciales** (rotación coordinable pero fuera de esta ventana).

## Flow, Diagnosis y Console

Los cierres previos siguen siendo evidencia fechada, no garantías de una nueva corrida ni autorización para tocar producción.

- Flow demo readiness V1 PASS en DEV: configuración persistida, scheduler de proceso único, pacing y cutoff seguro. Migraciones 011–022 productivas según baseline; 023/024 solo DEV. Automatización nueva no declarada desplegada/habilitada en producción.
- Flow: `TEAM360_FLOW_DEFAULT_ADMIN_HARDENING_PASS`. Sólo `TEAM360_ENV=development|dev` + `default_admin` explícito permite administrador demo. PROD/entorno ausente o no DEV + `default_admin`, y modo inválido/vacío/whitespace → 503; modo ausente → `authenticated`; sin token/capability → 401/403. [Política local](../backend/modules/flow/README.md#política-de-acceso-de-la-demo). Baseline confirmado: 940 PASS / 2 skips, Structural PASS, 28 operaciones y rutas/OpenAPI sin cambios; no reejecutado aquí.
- Flow comunica RECEIVED/IN_PROGRESS/RESOLVED sin datos internos; cierre exige supervisor y auditoría inmutable. WhatsApp, portal, INFO_REQUIRED outbound, conversación ciudadana avanzada y coordinación multiworker fuera del MVP.
- Vera pública: `/t360 → Litestar → PostgreSQL → Milvus → LiteLLM`; factibilidad separada de implementación. Embed externo con loader/manifest/integrity, CORS y autoridad backend por cliente/origin/contexto. Mamamia360 aprobado según cierre previo.
- Diagnosis post-close: `TEAM360_DIAGNOSIS_POST_CLOSE_STATE_FIX_PASS`, revalidado en Full Gate del 09/10. No hubo pérdida de persistencia: required es política y completed es cierre; solicitud explícita puede renderizar diagnóstico sin reapertura ni approved. [Estado local](../backend/modules/sales_diagnosis_runtime/status_actual.md#fix-post-cierre).
- Diagnosis test isolation: **PASS** (`TEAM360_DIAGNOSIS_TEST_ISOLATION_PASS`); Classification: `TEST_ISOLATION_ONLY`; Runtime defect demonstrated: **NO**. Un test borraba incorrectamente la `LITELLM_MASTER_KEY` heredada, contaminando el entorno del router posterior. Corrección sólo de infraestructura de test con `monkeypatch` reversible; ampliada 785 PASS / 0 FAIL / 10 skips, repetida e invertida. No se demostró bug productivo ni defecto de estado global runtime. [Autoridad local](../backend/modules/sales_diagnosis_runtime/status_actual.md#aislamiento-de-tests-diagnosis), [evidencia](../../data/reports/diagnosis/test-isolation-20261009/report.json).
- Console UX publicada según release 2026-08-06; PASETO v4.public foundation/bootstrap/verificador implementados. HMAC embed sigue vigente; revocación, refresh y migración dual/deprecación no se declaran completados por esos gates.
- El fallo histórico `public-vera.spec.ts:230` y la deuda LAT de 129/130 errores fueron resueltos en cierres posteriores; no volver a listarlos como pendientes actuales.

## Próximos pasos y límites de validación

Antes de una corrida real consultar el [preflight](../../lat.md/service-preflight-methodology.md). La normalización previa fue documental; readiness del 09/10 aporta medición controlada nueva, no deployment ni capacidades nuevas.

- Srv05: separación Evolution opt-in, source+uv y Structural OFF validados; [contrato y excepción baseline](team360_srv05_evolution_isolation.md). Readiness DEGRADED: designar identidad/segundo tenant, política de automatización e ingress Evolution si se habilita. Gupshup legacy/fallback no es requisito mientras Evolution sea transporte principal. No reabrir Diagnosis funcional ni inferir promoción del perfil `full`.
- Telchi: promoción de ventas completada el 30/10/2026 sobre `foundation_38680850…`; próximas promociones requieren instrucción del owner sobre la candidata exacta, sin autorización nominal adicional. Gaps fuente/UoM y business unknown conservan sus límites.
- Messaging: cerrar baseline formal Evolution con sesión conforme; producción exige hardening y autorización propios.
- Flow/Console: RBAC enterprise, scheduler multiworker y migraciones/despliegue pendientes mediante ventanas específicas; hardening `default_admin` ya cerrado.
- Embed: package npm, Web Component, plugin WordPress, administración de clientes y migración de tokens siguen como deuda futura, no capacidades vendibles actuales.
- No hay CI/task runner raíz declarado por esta tarea; evidencia diaria y matrices extensas van a reports/fases, no a este tablero.

## Worktree y scopes reconocidos

Esta ventana GLOBAL / DOCUMENTATION_RECONCILIATION no limpia Git ni reserva ownership de código. Los cambios existentes se preservan; untracked no significa inválido ni promovido.

- Implementación en worktree: Srv05 entrypoint/arquitectura/resolver y Full Gate harness/repository/tests; Messaging adapter/SQL/profiling y migración 026; Telchi Data Lake readers/semántica/query. Sus límites se consultan en autoridades y evidencia enlazadas.
- Documentación: fases Srv05, contrato Full Gate, estados locales, contratos Telchi e histórico de normalización. Evidencia: `data/reports/team360-full-gate/`, `data/reports/messaging/`, `data/reports/telchi/`.
- Fixture: gold JSON de semántica comercial Telchi. Investigación: validaciones bajo Telchi `investigation/`; frontend TelchiAI es trabajo local sin gate/deploy declarado.
- Scopes presentes reconocidos: Flow, Srv05/Full Gate, Messaging↔Telchi y documentación transversal; no se modifican sus implementaciones ni se atribuye autoría. Nuevos writers deben coordinar asignación explícita, no inferirla de este inventario.

## Historia preservada

Los documentos históricos no son estados alternativos. La copia de normalización preserva todo el cuerpo del tablero previo, incluidos cierres preexistentes sin commit y sus contradicciones cronológicas.

- [Histórico hasta 2026-06-28](status_historico_hasta_2026-06-28.md): congelado, sin cambios.
- [Histórico hasta esta normalización](status_historico_hasta_normalizacion_2026-10-06.md): bitácora anterior preservada; fases, reports y runbooks existentes permanecen en sus ubicaciones.
- [Índice documental](README.md), [índice LAT](../../lat.md/lat.md) y [mantenimiento LAT](../../lat.md/status_actual.md).
