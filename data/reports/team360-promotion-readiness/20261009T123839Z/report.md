# Srv05 promotion readiness

Ventana GLOBAL / SRV05_PROMOTION_READINESS del 2026-10-09. Medición sin fixes productivos ni promoción. Resultado BLOCKED por defecto reproducible de packaging y garantías obligatorias sin evidencia segura.

## Autoridad y preflight

El estado GLOBAL sigue siendo la única autoridad técnica vigente; este reporte contiene evidencia fechada y clasificación, no un segundo tablero.

- Rama: `feature/console-backend-core`; HEAD: `09d2ec715a31bb88574d734eacb9f437f008624e`, con worktree preexistente preservado.
- Inicio: `git branch --show-current`, `git status --short`, `git diff --check`: rama correcta, cambios reconocidos, whitespace PASS.
- Lecturas: AGENTS, GLOBAL, Full Gate, LAT/ownership/preflight/runtime/DB/browser/embed/documentación; Srv05 arquitectura/resolver/entrypoint; estados Flow/Diagnosis/Console/Messaging; launchers DEV y comando productivo canónico Srv01.
- Host: load inicial 1.59/1.64/1.80, 5408 MiB disponibles, swap 1073 MiB. Antes de frontend: 5720 MiB disponibles, swap 1221 MiB; carga 1.31/1.66/1.77. Capacidad suficiente para tareas focalizadas secuenciales; no se atribuye swap de procesos compartidos a este gate.
- Matriz previa a servicios: [preflight-matrix.json](preflight-matrix.json). No se iniciaron servicios ni listeners.
- Cambio concurrente observado dentro del scope Telchi reconocido: nueva evidencia investigativa `response_verifier_false_simple_analysis/`, intacta. No se ejecutó investigación Telchi/SAP ni se adoptó su trabajo.

## Promotion Readiness Matrix

READY certifica exclusivamente la evidencia indicada. DEFECT es un fallo demostrado; NOT_TESTED no es defecto. Blocking refiere a esta revisión de promoción, no a disponibilidad del baseline productivo Srv01.

| Área | Clasificación actual | Evidencia / requisito restante | Impacto |
| --- | --- | --- | --- |
| Srv05 import/factory | READY | Source app/factory idénticos a Srv01; 93 tests Srv05 PASS | NON_BLOCKING_FOR_PROMOTION |
| Routing/OpenAPI | READY | 28 operaciones, 26 paths; registry, referencias, operation IDs, handlers sin colisiones; hooks únicos | NON_BLOCKING_FOR_PROMOTION |
| Lifecycle | READY controlado / NOT_TESTED productivo | Startup/pool/scheduler único/shutdown reales con fixture automation=false; falta condición destino que impida delivery no autorizado | BLOCKING_FOR_PROMOTION |
| Flow | READY | 242 PASS / 2 skips; fail-closed DEV/prod/auth; lecturas PG reales; no Milvus/Evolution | NON_BLOCKING_FOR_PROMOTION para seguridad/API probadas |
| Diagnosis | READY | Stack PG/Milvus/LiteLLM, tres turnos, persist/reload/post-close PASS; ampliada sin fallos de aislamiento | NON_BLOCKING_FOR_PROMOTION |
| Embed/Mamamia360 | READY API / NOT_TESTED browser | mamamia360 existente, HMAC request-bound, allow/deny, tamper, override ignorado, conversación distinta persistida; falta montaje browser | BLOCKING_FOR_PROMOTION en browser |
| Console/Auth | READY fixture / NOT_TESTED DB real | 51 tests; bootstrap 201, PASETO válido 200, ausente/manipulado 401; falta identidad de test autorizada y cadena DB completa | BLOCKING_FOR_PROMOTION |
| Messaging | READY coexistencia / CONDITIONAL transporte | 167 tests; Evolution deshabilitado 503, Gupshup vacío ignored/200; imports/registry/parser/config fallan controladamente | NON_BLOCKING_FOR_PROMOTION sin transporte habilitado |
| Browser/frontend | READY check/build DEV / NOT_TESTED E2E | check 0 errors/0 warnings/7 hints; build aislado PASS; no launcher seguro para Srv05 global | BLOCKING_FOR_PROMOTION |
| Identity/RBAC DB | NOT_TESTED | No identidad oficial designada para test identificada; seed 005 contiene administradores reales, no autorización para impersonarlos | BLOCKING_FOR_PROMOTION |
| Multi-tenant isolation | NOT_TESTED entre dos tenants reales | wrong-tenant inexistente/override PASS no equivale a dos tenants; Mamamia comparte contexto público; falta segundo tenant autorizado | BLOCKING_FOR_PROMOTION |
| LiteLLM | READY auditoría configuración/adapter | Model info activo confirma upstreams; router activo y config sin fallbacks configurados; falla real upstream no inyectada | NON_BLOCKING_FOR_PROMOTION con alcance auditado; fallo vivo NOT_TESTED |
| Scheduler | READY controlado / NOT_TESTED enabled | 10 lecturas PG, DB automation=true, una tarea, start idempotente, 0 ciclos; no dry-run en scheduler | BLOCKING_FOR_PROMOTION hasta control seguro del destino |
| Cleanup/processes | READY | 2 sesiones sintéticas eliminadas/0 restantes, pool cerrado, singleton eliminado, 0 tareas; sesiones de workers verificadas | NON_BLOCKING_FOR_PROMOTION |
| Packaging | DEFECT | Wheel construido omite Srv05/Srv01/globalVar; import aislado falla ModuleNotFoundError | BLOCKING_FOR_PROMOTION |

## Structural y ejecución operacional

Se reutilizó el harness existente sin modificar su agregación ni evidencia previa. La nueva corrida está bajo este reporte y no sobrescribe Full Gate evidence.

```bash
cd SrvRestAstroLS_v1/backend
TEAM360_ENV=development TEAM360_FLOW_ACCESS_MODE=default_admin \
  uv run python scripts/validate_team360_full_stack.py --safe-operational \
  --output ../../data/reports/team360-promotion-readiness/20261009T123839Z/full-gate
```

- Resultado: Structural PASS; Operational DEGRADED; exit 2 esperado para cobertura incompleta, no defecto operacional demostrado.
- Suite principal: 951 PASS / 3 skips. Srv05 93, Core 27, Flow 242/2, Diagnosis 362/1, Console 51, Messaging 167, harness 11.
- Evidencia: [report.json](full-gate/report.json), [routes.json](full-gate/routes.json), [openapi.json](full-gate/openapi.json).
- Diagnosis real: tres turnos 201, retrieval filtrado y embeddings dimensión 1536; required/completed persistidos, reload, acción final diagnose, sin reapertura/aprobación inventada. Mamamia conversación adicional 201 en sesión distinta.
- Suite ampliada y adapter: [runner](supplemental_runner.py), [comandos/resultados](supplemental-tests.json): 798 PASS / 10 skips = 785 Diagnosis ampliada + 13 adapter LiteLLM. No son tests únicos adicionales al Full Gate; hay solapamiento. Opt-ins externos removidos.
- El test PostgreSQL post-close opt-in separado no se repitió: esta corrida ya ejecutó persist/reload real en stack; se reutiliza el baseline focalizado 12 PASS fechado en Full Gate, no se cuenta como corrida nueva.

## Lifecycle, scheduler y browser

ASGI lifecycle controlled y real production automation enabled son garantías diferentes. El primero pasó; el segundo no fue ejecutado ni considerado automáticamente requisito de delivery real.

- Hooks reales: pool antes de scheduler, shutdown scheduler antes de pool. Pool PG read-only confirmado, una tarea en loop lifespan, segundo start no duplica, pool cerrado/singleton ausente/0 tareas finales.
- Fixture existente sólo proyecta settings leídos de PG a automation=false e intervalo 1 s y prohíbe `_execute_cycle`; DB permanece automation=true. 10 lecturas, 0 intentos de delivery.
- Scheduler arranca incondicionalmente en Srv01/Srv05. Lee `flow_operational_settings`; habilitado ejecuta ciclo inmediatamente y espera al finalizar. Usa mail cutoff/batch/account, poll Gmail si intake=true, sender Gmail y runner `confirm_send=True`; puede actualizar SLA/escalamiento/notificaciones y registrar ciclos PG.
- No existe override seguro de launcher normal ni dry-run del scheduler. Dry-run de runners CLI no deshabilita startup ASGI. messaging-only excluye Flow/Diagnosis y no es composición equivalente. No cambiar DB real para forzar E2E.
- Automatización activa/delivery: NOT_TESTED / BLOCKING_FOR_PROMOTION para esta configuración destino no delimitada. No es defecto. Puede pasar a CONDITIONAL/NON_BLOCKING sólo con destino explícitamente automation=false y control verificable o sandbox/fixtures de transporte autorizados; ninguno quedó autorizado como destino de promoción.
- Browser previsto: Playwright + Chromium, `/t360`, demos embed/loader, `/w/ws-team360-control/flow/`, Console/login. Auth: pública/embed HMAC; Flow authenticated PASETO salvo demo DEV explícita; Console requiere identidad autorizada.
- No se lanzó browser ni servidores: assets/CORS/mount/login browser NOT_TESTED, no errores observados atribuibles porque no hubo ejecución. API origin/HMAC PASS no prueba CORS estático ni mount.
- Primer intento de check abortó antes de ejecutar pnpm por redirección con path relativo incorrecto; corregido sólo el comando y reejecutado. No fallo frontend ni fix de código.
- `pnpm check` PASS; `pnpm build --outDir ../../data/reports/team360-promotion-readiness/20261009T123839Z/frontend-build` PASS. Logs [check](frontend-check.log), [build](frontend-build.log). IS_REST_PRO=false preservado: build DEV, no artefacto productivo aprobado. Salida aislada, sin sobrescribir dist compartido.

## Auth, tenants y exposición destino

Las fixtures oficiales prueban contratos, no identidad real. Existencia de un seed productivo no autoriza usar sus administradores como usuarios sintéticos ni emitir tokens en su nombre.

- Inspección de migraciones/seeds: 005 crea plataforma/contexto público y administradores reales; 008/009/010 configuran embed. No se aplicó ningún seed ni se identificó test user/token ni segundo tenant expresamente autorizado.
- Cadena pendiente: authenticated identity → tenant/workspace → module entitlement → permission/capability → access; rechazo fuera de scope. No bypass, claves productivas, nuevos usuarios ni tokens reales de administradores.
- Dos workspaces platform/public no demuestran dos tenants independientes. `mamamia360` es distribuidor hacia el mismo package/knowledge scope público, no segundo tenant. No se afirma que no existan otros tenants en DB; falta identificación/autorización de fixture de prueba.
- Superficies DEV físicamente montadas y Gupshup DEV sin firma requieren decisión de exposición/controles del destino. También bootstrap experimental recibe IDs y puede emitir token al habilitar PASETO: fixtures no certifican autenticación de entrada de un despliegue público. CONDITIONAL; resolución de exposición exigida antes de revisión, sin declarar exploit nuevo ni ejecutar impersonación.

## LiteLLM y servicios horizontales

La auditoría interna read-only agrega evidencia de configuración activa; no interrumpe providers ni demuestra escenarios de falla real mediante inyección al proxy compartido.

- [Auditoría sanitizada](litellm-audit.json), [script](litellm_audit.py): proceso existente/config canónica sólo lectura; GET autenticados `/model/info` y `/router/settings`. Secretos y cuerpos completos no se guardaron.
- Base efectiva del stack `http://127.0.0.1:4000/v1`, Chat Completions; alias `openai_gpt-5.4-nano` → `openai/gpt-5.4-nano`; embeddings `openai_text_embedding_3_small` → `openai/text-embedding-3-small`.
- Router activo simple-shuffle, fallbacks/context-window/content-policy vacíos; model_group_alias y fallback en default params vacíos. Config de proceso sin default fallback. No provider extra no declarado identificado para estos aliases.
- Client adapter falla con LiteLLMClientError ante HTTP/network/JSON inválidos, sin cambiar provider; router tests cubren 503 de auth y fallback transitorio explícito/metadata. Stack exitoso sin fallback runtime/adapter. Fallo upstream vivo NOT_TESTED / NON_BLOCKING_FOR_PROMOTION: no requiere dañar servicio compartido teniendo contratos de error y auditoría activa.
- El probe del router se ajustó sólo en harness para leer `current_values` (no el nivel superior de la respuesta); ausencia de un campo se conserva como no presente, no prueba global de ausencia de cualquier mecanismo de fallback.
- No se certifican todos los modelos del proxy, futuras reconfiguraciones ni un proxy del host productivo distinto. Auditar nuevamente en destino si cambia su configuración.

| Servicio | Estado medido | Consumidores / límite |
| --- | --- | --- |
| PostgreSQL | READY | Flow, contexto/estado/embed Diagnosis, pool; tablas Messaging. Console identidad real NOT_TESTED |
| Milvus | READY | Diagnosis únicamente; colección/version/scope/search real, no permiso autoritativo |
| LiteLLM | READY | Diagnosis generación/clasificador/embeddings; adapter compartido Flow condicional por capacidad |
| Evolution | NOT_REQUIRED | Messaging DEV consumer deshabilitado; CONDITIONAL al habilitar, transporte NOT_TESTED |
| Gmail/DWD | CONDITIONAL | Flow email/intake/delivery; probe y delivery NOT_TESTED / NON_BLOCKING sin alcance email activo |
| Gupshup | CONDITIONAL | Webhook/bridge Flow coexistente; outbound NOT_TESTED / NON_BLOCKING sin alcance transporte activo |
| SAP/HANA | NOT_REQUIRED | Sin API Telchi global; cero consultas |

## Packaging y defecto demostrado

Build exitoso no significa wheel deployable. El import source PASS depende del worktree; la distribución creada carece de los entrypoints ASGI que requiere el criterio de promoción.

```bash
cd SrvRestAstroLS_v1/backend
uv build --wheel --out-dir ../../data/reports/team360-promotion-readiness/20261009T123839Z/packaging
```

- [Reporte reproducible](packaging/report.json), [probe](packaging_probe.py), wheel en `packaging/`. SHA-256 del wheel registrado. 5522 miembros, arquitectura/resolver presentes, Srv05/Srv01/globalVar ausentes.
- Import aislado con `python -I -S` desde directorio temporal, wheel primero y site-packages para dependencias sin procesar `.pth`: exit 1, `ModuleNotFoundError: No module named 'ls_iMotorSoft_Srv05'`.
- Primera prueba sólo `-I` fue inválida: editable source se filtró por `.pth` y dio éxito. Se corrigió exclusivamente harness a `-S`; el resultado final preserva esta limitación. No se modificó pyproject, runtime ni packaging para pasar.
- Entry point source documentado: `ls_iMotorSoft_Srv05:app` o `ls_iMotorSoft_Srv05:create_app --factory`. Producción documentada conserva Srv01; DEV launcher también. No se reemplazaron.
- DEFECT / BLOCKING_FOR_PROMOTION con criterio packaging válido explícitamente solicitado, aunque baseline rsync use source. Una excepción source-only requiere decisión explícita futura, no se infiere aquí.

## Cleanup, límites y decisión

El cierre distingue blockers de cobertura incompleta y deuda condicional. No hay nuevos defectos Diagnosis/Flow; sí hay un defecto de distribución que impide declarar elegibilidad bajo el criterio pedido.

- Cleanup: 2 sesiones propias eliminadas, 0 restantes; pool cerrado, singleton eliminado, 0 tareas scheduler. Workers/hijos con sesiones propias cerrados; PIDs de Full Gate y supplemental ausentes en verificación final. Sin listeners propios 3050/7050.
- Side effects evitados: 0 email/WhatsApp/Gupshup/Evolution, 0 migraciones/provisioning/bindings/tenants/corpus/config writes, 0 lifecycle horizontal/deploy/Git mutante. Únicos writes de datos: dos sesiones sintéticas y su cleanup. LiteLLM consumió generación/embeddings mínimos del stack; auditoría sólo GET.
- Archivos propios: evidencia/harness validation-only en este directorio, más actualizaciones delimitadas en `SrvRestAstroLS_v1/docs/status_actual.md` y `SrvRestAstroLS_v1/docs/team360_full_gate_v1.md`. No fixes funcionales ni frontend edits.
- TECHNICALLY_ELIGIBLE_FOR_PROMOTION_REVIEW exige Structural PASS, lifecycle defendible según destino, Flow fail-closed, Diagnosis real PASS, fronteras auth/tenant suficientemente probadas, browser/API smoke, cero defectos bloqueantes, cleanup limpio, packaging válido y restantes pendientes no bloqueantes/condicionales.
- Criterios no satisfechos: packaging; identidad/RBAC DB y dos tenants autorizados; browser Srv05; control destino de automatización/exposición. NOT_TESTED no se transforma en DEFECT.
- NOT_TESTED no bloqueantes: upstream failure vivo con auditoría/contratos PASS; transportes Gmail/Gupshup/Evolution fuera del alcance activo; test PG focalizado no repetido con stack persist/reload revalidado. No se amplía el alcance a SAP/TelchiAI.
- Próximo paso: ventana separada de packaging para corregir/revalidar wheel; asignación explícita de test identity/segundo tenant y runtime DEV seguro oficial, seguida de E2E Chromium y decisión de exposición/automatización destino. No fixes automáticos en esta tarea.
- Validaciones finales documentales y Git: resultados en `final-validation.json` y `lat-gates.log`.

Srv05 no es técnicamente elegible para revisión de promoción con esta evidencia. Full Gate permanece DEGRADED; readiness específica BLOCKED. No desplegar ni reemplazar Srv01.

TEAM360_SRV05_PROMOTION_READINESS_BLOCKED
