# Team360 security boundary hardening

Ventana `GLOBAL / SECURITY_BOUNDARY_HARDENING`, rama `feature/console-backend-core`, 2026-10-09. No deploy, promoción, reemplazo Srv01, envío externo ni cambio de secretos.

## 1. Estado inicial

Readiness era `TEAM360_SRV05_PROMOTION_READINESS_BLOCKED` aunque packaging, Structural Gate, runtime seguro, Flow, Diagnosis, embed, browser y coexistencia estaban cerrados. La reproducción anterior demostró DEV adapter 201 y bootstrap anónimo 201/token usable bajo `TEAM360_ENV=production`; Gupshup aceptaba unsigned sin control previo. Worktree ya contenía numerosos cambios tracked/untracked; se preservaron.

## 2–4. Contratos reconstruidos

Detalle completo: [inventario](inventory.md) y [matriz](surface-matrix.md).

- **DEV adapter:** `POST /api/dev/sales-diagnosis-runtime/turn`, montado directo por Srv01/Srv05. Fake/memoria default, pero PG/Milvus/LiteLLM opt-in; sin auth ni guard original. Clasificación `DEV_ONLY`.
- **Bootstrap:** `POST /api/console/bootstrap`, caller elegía workspace/user. PostgreSQL derivaba permisos/entitlements y PASETO opcional emitía sólo identidad (`typ`, `iss`, `sub`, `user_id`, `iat`, `exp`, `jti`; default 900 s). No caller frontend real encontrado ni sesión previa dentro de app. Clasificación `bootstrap de desarrollo`; inseguro si production.
- **Gupshup:** webhook público legítimo. Normaliza, reclama inbound en PG y llama Flow sólo para ID nuevo. El repo no documenta firma Gupshup utilizable; el control anterior era sólo tunnel DEV.

## 5–6. Riesgos confirmados y falsos positivos

Confirmados:

1. DEV adapter ejecutable en production.
2. Bootstrap experimental podía convertir IDs arbitrarios en token válido al habilitar PASETO.
3. Mensaje Gupshup podía llegar a persistencia/Flow sin autenticidad.
4. Scan adicional: Evolution DEV aceptaba `TEAM360_ENV` ausente como development si enable estaba activo.

Matices/falsos positivos:

- Un empty Gupshup 200 no generaba side effect; el riesgo se confirmó por source del camino message, no por ese 200 aislado.
- Gupshup ya tenía idempotencia durable; no era `MISSING`. Clasificación `IDEMPOTENT` por unique `(provider, external_message_id)` y `ON CONFLICT DO NOTHING`; duplicado no invoca Flow.
- Ausencia de firma visible no autorizó inventar HMAC provider-specific. Se usa la frontera precompartida existente; compatibilidad del sender/ingress queda evidencia externa.
- Emitir token no es por sí solo vulnerabilidad; lo era la combinación production + identidad elegida por caller + ausencia de principal previo.

## 7–11. Fixes y fronteras

- Helper fail-closed `is_explicit_development_environment()` sin default implícito.
- Adapter DEV y bootstrap: sólo `TEAM360_ENV=dev|development`; production, ausente, vacío o desconocido → 404 antes de provider/DB/token.
- Bootstrap DEV conserva capabilities, claims y TTL; PASETO no cambió.
- Gupshup exige `TEAM360_MESSAGING_WEBHOOK_TOKEN` (mínimo 32) vía `x-team360-webhook-token`, comparación constante. Config ausente → 503; credencial inválida/ausente → 401; ambos antes de leer JSON, claim o Flow. Body máximo 1 MiB.
- Token válido permite el webhook en DEV/PROD. No es firma request-bound; TLS/ingress protege integridad de transporte. Sender/ingress confiable debe aportar el header.
- Idempotencia existente preservada y revalidada; status/unknown no tienen side effect de negocio.

## 12. Scan de superficies similares

[Resultado](source-scan.md): Evolution DEV quedó fail-closed ante entorno ausente/desconocido. Flow y launchers ya eran explícitos. Product adapter continúa opt-in/deshabilitado por default (`CONDITIONAL`), sin declaración production-ready. Vera/Automation Diagnosis no se reabrieron. `globalVar.DEFAULT_ENV` no se usa como autoridad de estos guards.

## 13. Archivos modificados

Implementación/harness:

- `backend/modules/security/environment.py`
- `backend/routes/sales_diagnosis_runtime_dev.py`
- `backend/routes/console_bootstrap.py`
- `backend/modules/messaging/settings.py`
- `backend/modules/messaging/webhooks/gupshup_whatsapp.py`
- `backend/scripts/validate_team360_full_stack.py`

Tests:

- `backend/tests/test_sales_diagnosis_runtime_dev_route.py`
- `backend/tests/test_security_boundary_bootstrap.py`
- `backend/tests/test_messaging_gupshup_webhook.py`
- `backend/tests/test_messaging_evolution.py`

Documentación:

- `backend/modules/{sales_diagnosis_runtime/README.md,messaging/README.md,console/status_actual.md}`
- `docs/{console_bootstrap_contract.md,paseto_console_bootstrap_access_token_v1.md,status_actual.md,team360_full_gate_v1.md,team360_srv05_promotion_readiness.md}`
- evidencia nueva bajo este directorio.

## 14–16. Tests, Structural Gate, browser y runtime

- Focal boundaries: 129 PASS.
- Console/Auth + Messaging + registry: 250 PASS / 4 skips.
- Srv05 structural focal: 107 PASS.
- Packaging/launcher harness: 14 PASS.
- Full Gate nuevo: Structural PASS / Operational DEGRADED; 961 PASS / 3 skips; PostgreSQL, Milvus y LiteLLM READY. Flow 242/2 y Diagnosis 367/1 PASS. HTTP Gupshup fail-closed 503; cleanup PASS.
- OpenAPI: [diff](openapi-diff.json) `IDENTICAL`, 28→28, sin operaciones agregadas/removidas ni cambios de schema.
- Packaging: PASS; wheel instalado desde site-packages, 5526 miembros, 28 operaciones, health/listener/cleanup PASS, SHA-256 `2ea19b8c9c4ca62c8d774d53470b9b872ef987a1254fcf505c75f1a557110453`.
- ASGI production-like: [PASS](production-like-probe.json): DEV 404, bootstrap 404, Gupshup 503/401/valid ignored 200, Flow 401, Console me 401, health 200.
- Uvicorn Srv05 loopback production-like/lifespan off: [PASS](network-probe.json), shutdown/listener cleanup PASS. Lifespan off evitó scheduler/delivery compartidos.
- Browser vivo `srv05-safe-runtime.spec.ts`: 2 PASS, dos turnos por Home/Mamamia, PG reload. Harness lifecycle startup/shutdown, pool read-only, scheduler único, cero ciclos; dos sesiones eliminadas. Regresión frontend previa 39 PASS / 2 skips reutilizada porque no hubo cambios frontend.

## 17–18. Side effects y cleanup

Evitados: cero Gmail, WhatsApp, Gupshup/Evolution real, cambios de webhook, SAP/HANA, migraciones, tenants, bindings, corpus, configuración persistente, servicios administrados o deploy. LiteLLM consumió cuota sintética sólo en Full Gate/browser ya autorizados. Full Gate limpió sus sesiones; browser eliminó 2/2. PIDs propios restantes 0; puertos 3050/7050/17055/48081 libres; pool/scheduler cerrados; temporales de wheel eliminados. [Cleanup](cleanup.json).

## 19–20. Blockers restantes

Técnicos dentro del scope: **ninguno demostrado**. El product adapter opt-in y schema/health siguen `CONDITIONAL`, no defectos nuevos.

Evidencia/fixtures:

- `BLOCKED_BY_MISSING_AUTHORIZED_IDENTITY_FIXTURE`.
- `BLOCKED_BY_MISSING_SECOND_TENANT_FIXTURE`.
- Compatibilidad/configuración real de Gupshup o ingress para aportar el header: `NOT_TESTED / EXTERNAL_EVIDENCE`.
- Automation delivery destino: `NOT_TESTED / policy pending`.
- Gmail/Gupshup outbound condicionales; Evolution no requerido mientras esté deshabilitado.

## 21–23. Gate, readiness y acción humana mínima

- Full Team360 Gate: `TEAM360_FULL_GATE_DEGRADED`; Structural PASS. La degradación conserva política del harness y evidencia externa, no exposición técnica.
- Promotion Readiness: `TEAM360_SRV05_PROMOTION_READINESS_DEGRADED`; no PASS, no promoción.
- Acción humana mínima: designar identidad y segundo tenant oficiales de test, y confirmar/configurar sender o ingress Gupshup autorizado con el header privado existente. Después definir control seguro de automatización destino; no enviar mensajes para fabricar evidencia.

Gates documentales `lat check md/index/sections/code-refs/full` y `git diff --check`: PASS. Warnings LAT opcionales de init/key solamente.

TEAM360_SECURITY_BOUNDARY_HARDENING_DEGRADED
