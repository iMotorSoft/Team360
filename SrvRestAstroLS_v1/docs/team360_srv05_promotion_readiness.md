# Srv05 promotion readiness

Readiness técnica al 2026-10-09 después del fix de packaging y del E2E seguro. No autoriza deploy ni reemplazo de Srv01; el estado GLOBAL permanece en [status_actual.md](status_actual.md).

## Aislamiento Evolution y contrato source vigente

La ventana SRV05_EVOLUTION_ISOLATION agrega composición diferencial y validación segura, no promoción. Readiness sigue DEGRADED; packaging no vuelve a ser blocker ni define el deploy principal.

- [Contrato y evidencia](team360_srv05_evolution_isolation.md): Srv01 sin Evolution con cualquier env; Srv05 OFF 27 operaciones/404, ON DEV fixture 28 y binding/schema fail-closed antes del scheduler.
- Source deploy: checkout + `uv sync --locked` + `uv run uvicorn ls_iMotorSoft_Srv05:app`; sync y listener/lifespan memory/mock comprobados, coexistencia y cleanup propios. Wheel es control de calidad, no unidad principal de promoción.
- Full Gate Srv05 OFF Structural PASS / Operational DEGRADED; no cambio frontend, launcher normal ni configuración persistente. La retirada única de ruta Evolution DEV de Srv01 se documenta, no se declara OpenAPI previo íntegramente idéntico.
- Pendientes: identidad autorizada, segundo tenant, policy automation/delivery e ingress/config real Evolution si se habilita. Transporte principal previsto Evolution; Gupshup legacy/fallback deshabilitado no exige prueba outbound ni disponibilidad/ingress para promoción.
- No certifica Evolution productivo: guard DEV sigue cerrado en producción. Se necesita gate propio antes de ampliar ese contrato, no activar env por inferencia.

## Decisión vigente

La ventana GLOBAL / SECURITY_BOUNDARY_HARDENING cerró las exposiciones técnicas reproducidas sin promover ni desplegar Srv05. Readiness avanza de BLOCKED a DEGRADED: quedan fixtures/evidencia de destino, no un bypass demostrado en source.

- Resultado: `TEAM360_SRV05_PROMOTION_READINESS_DEGRADED`; Full Gate: `TEAM360_FULL_GATE_DEGRADED`.
- Adapter DEV: sólo `TEAM360_ENV=dev|development` explícito; production, ausente o desconocido → 404 antes de providers/estado.
- Bootstrap experimental: misma frontera DEV-only. El flujo permitido conserva PASETO `console_access`, claims, capacidades y TTL; production anónimo → 404 antes de DB/token. No se creó login ni se cambió criptografía.
- Gupshup: token existente `x-team360-webhook-token` obligatorio; configuración ausente → 503, inválido → 401, ambos antes de body/DB/Flow. El repo no documenta firma Gupshup utilizable, por lo que no se inventó HMAC incompatible. Sender/ingress real debe configurar esta credencial; esa compatibilidad externa sigue NOT_TESTED.
- Idempotencia Gupshup: PASS por claim PostgreSQL atómico y unique `(provider, external_message_id)`; duplicado no invoca Flow.
- Scan equivalente cerró además Evolution DEV con entorno ausente/desconocido fail-closed. Product adapter opt-in continúa CONDITIONAL y deshabilitado por default; no se reabrió Diagnosis funcional.
- Nueva validación: Structural PASS, 28 operaciones/OpenAPI sin cambios, Full Gate 961 PASS / 3 skips; PostgreSQL/Milvus/LiteLLM READY. Packaging aislado PASS. Browser vivo Srv05 2 PASS con persistencia/cleanup; regresión previa 39 PASS / 2 skips reutilizada sin cambios frontend.
- Evidencia faltante: `BLOCKED_BY_MISSING_AUTHORIZED_IDENTITY_FIXTURE`, `BLOCKED_BY_MISSING_SECOND_TENANT_FIXTURE`, compatibilidad/configuración ingress Gupshup y control de automatización destino; `AUTOMATION_DELIVERY_NOT_TESTED`.

## Reproducción y evidencia

El reporte fechado conserva matriz, comandos, intentos previos, límites y cleanup. No sustituye el estado GLOBAL ni modifica evidencia histórica.

- [Security boundary hardening vigente](../../data/reports/team360-security-boundary/20261009T182048Z/report.md), con inventario, matriz, probes ASGI/Uvicorn, Full Gate, packaging, browser y cleanup.
- [Reporte anterior de packaging/browser y reproducción before](../../data/reports/team360-promotion-readiness/20261009T130833Z/report.md).
- [Wheel instalado y origins](../../data/reports/team360-promotion-readiness/20261009T130833Z/packaging/final/report.json).
- [Full Gate](../../data/reports/team360-promotion-readiness/20261009T130833Z/full-gate/report.json), [lifecycle con conversación](../../data/reports/team360-promotion-readiness/20261009T130833Z/lifecycle.json), [auditoría de exposición](../../data/reports/team360-promotion-readiness/20261009T130833Z/surface-audit.json).
- [Cierre previo preservado](../../data/reports/team360-promotion-readiness/20261009T123839Z/report.md), [contrato Full Gate](team360_full_gate_v1.md).

```bash
cd SrvRestAstroLS_v1/backend
uv run python scripts/validate_srv05_wheel.py --output /tmp/srv05-wheel-evidence-new
```

El comando objetivo del artefacto instalado es `uvicorn ls_iMotorSoft_Srv05:app --host 127.0.0.1 --port 7050`, con configuración/dependencias privadas autorizadas. No ejecutar lifecycle con la DB compartida automation=true fuera del harness seguro.

## Harness seguro y siguiente paso

El perfil de prueba no cambia el launcher normal ni configura producción. Sólo admite loopback, prohíbe mutaciones de negocio y requiere IDs full_gate UUID nuevos para conversación sintética.

```bash
TEAM360_ENV=development TEAM360_DEV_PROFILE=srv05-e2e \
TEAM360_E2E_EVIDENCE=/tmp/srv05-lifecycle-new.json \
bash SrvRestAstroLS_v1/backend-dev.sh
```

Backend con [harness test-only](../backend/scripts/srv05_e2e_runtime.py), frontend con astro-dev.sh y Playwright con `PLAYWRIGHT_SKIP_WEBSERVER=1`. El E2E vivo [srv05-safe-runtime.spec.ts](../astro/e2e/srv05-safe-runtime.spec.ts) exige además `TEAM360_SRV05_SAFE_E2E=1`.

La siguiente acción humana mínima es designar identidad y segundo tenant oficiales de test existentes, y confirmar ingress/config Evolution autorizado si se habilita. Gupshup no es requisito mientras permanezca legacy/fallback deshabilitado. Luego definir política segura de automatización destino. No emitir tokens para usuarios reales ni enviar mensajes para completar evidencia.
