# Srv05 Evolution isolation

Ventana GLOBAL / SRV05_EVOLUTION_ISOLATION en feature/console-backend-core. Separación por composición, sin deploy ni reemplazo de Srv01; los datos y la configuración productivos no se modifican.

## Baseline y excepción explícita

El worktree previo montaba Evolution también en Srv01. Sí podía activarse accidentalmente con env DEV válido. Srv05 reexportaba exactamente su app/factory; dos nombres no proporcionaban aislamiento.

- Before: 28 operaciones / 26 paths de negocio/core, más OPTIONS y OpenAPI generado.
- After Srv01: 27 operaciones / 25 paths; única eliminación: POST `/webhooks/messaging/evolution/whatsapp`.
- Las otras 27 operaciones, handlers, OpenAPI legacy, CORS y hooks son idénticos. No se afirma igualdad del OpenAPI completo previo: se retira deliberadamente la capability DEV nueva.
- Fixture reproducible: [baseline legacy](../backend/tests/fixtures/srv01_legacy_composition.json). La evidencia before íntegra permanece en el reporte, no se normaliza retrospectivamente.
- Health sigue siendo estático: status/service/version, no readiness de proveedores.

## Composición y configuración

Srv01 conserva la base legacy; Srv05 construye una app distinta con el mismo factory y extensiones explícitas. No se copian Flow, Diagnosis, Console, health ni lifecycle.

- [Srv01](../backend/ls_iMotorSoft_Srv01.py) admite handlers adicionales como input explícito; su app/default no descubre Evolution desde env.
- [Registry](../backend/modules/module_registry.py) monta Flow, sin importar rutas Evolution. Gupshup legacy permanece directo, con sus guards existentes.
- [Srv05](../backend/ls_iMotorSoft_Srv05.py) usa [Srv05Settings](../backend/modules/srv05_settings.py), dataclass pequeña e inmutable, fuera de globalVar.
- `TEAM360_SRV05_EVOLUTION_ENABLED=0` por defecto: no montaje, 404, sin imports Evolution; ignora configuración provider inválida no seleccionada.
- ON: `TEAM360_SRV05_EVOLUTION_ENABLED=1`, provider `evolution` (default, o `TEAM360_SRV05_MESSAGING_PROVIDER=evolution`), PostgreSQL lifecycle y configuración DEV existente completa.
- Se reutilizan `TEAM360_EVOLUTION_*` y `TEAM360_MESSAGING_*`; secretos sólo desde environment privado. El flag Srv05 es adicional, no reemplaza el guard DEV.
- Flag desconocido o config ON inválida aborta construcción con error saneado. Binding/schema faltante aborta startup antes del scheduler.
- Config válida es configuración sintáctica; no certifica disponibilidad Evolution, suscripción Meta ni ingress. Producción permanece rechazada por el adapter actual.

## Binding, seguridad y lifecycle

Service + Binding + Module conserva aislamiento por workspace/canal/provider/instancia. Evolution sigue horizontal; el consumidor Telchi opcional existente no se convierte en cuenta global ni permiso de negocio.

- Un binding seleccionado por proceso, sin implementar múltiples números. Sender allowlist DEV no equivale a identidad/RBAC.
- Settings/provider/recipient se capturan por app; cambiar env de provider después de componer no redirige ese binding. El entorno y habilitación DEV se siguen verificando antes de procesar requests.
- Token privado `x-team360-webhook-token`, comparación constante; auth antes de body/DB. JSON inválido 400; token inválido 401; guard DEV cerrado 503; límite 1 MiB.
- No se inventa firma Meta/Evolution. TLS/ingress y autenticidad externa requieren evidencia de destino. Replay con ID estable se deduplica; no hay nonce ni promesa exactly-once para IDs nuevos.
- Persistencia/intent/idempotencia y status existentes se conservan. SQL de validación de índices 026 queda en repository, reutilizado por messaging-only.
- ON startup: pool base → validación read-only binding/schema → scheduler base. Shutdown: scheduler → pool. Litestar ejecuta shutdown también ante fallo de startup; no segundo lifecycle manager.
- Provider crea/cierra HTTP client por dispatch; no worker, pool ni task Evolution en import/startup. Logging Litestar por app es un efecto del framework, no un worker Evolution.
- Dos procesos con PG real NO quedan autorizados a ejecutar Flow contra los mismos destinos. La coexistencia medida usa memory/mock sin pool/delivery; la coexistencia ON ASGI usa hooks inertes.

## Source deploy, DEV y rollback

El contrato principal sigue siendo checkout + uv, no wheel. Los launchers y frontend se preservan; la prueba no modifica configuración persistente ni administra servicios existentes.

```bash
cd SrvRestAstroLS_v1/backend
uv sync --locked
uv run uvicorn ls_iMotorSoft_Srv05:app --host 127.0.0.1 --port 7050
```

El ejemplo exige configuración privada autorizada y política segura Flow antes de ejecutarse con PostgreSQL real. El smoke automatizado usa puertos loopback propios y memory/mock; no es deployment ni certificación de automatización activa.

- `backend-dev.sh` normal sigue Srv01. El perfil existente `srv05-e2e` sigue siendo test-only; no se añade otro launcher porque source target/factory ya permiten selección explícita.
- `messaging-only` continúa como laboratorio aislado del servidor global, no un tercer servidor Team360 productivo.
- No se toca `global.js`, proxy ni frontend. No se crea global5.js/globalVar5.py. No se declara browser nuevo: no hay cambio UI.
- Rollback mínimo: detener sólo Srv05 autorizado, iniciar Srv01 con checkout/uv.lock/config legacy compatibles y apuntar frontend/proxy al mismo backend baseline. Conservar DB; no down-migration ni secrets Evolution requeridos.
- Unidad recuperable: revisión de source (incluidos cambios aún sin commit), lock y configuración privada legacy. Git HEAD solo no recupera el trabajo preexistente sin commit; requiere snapshot/backup de source al promover.
- Smoke Srv01 source/health/schema y tests DB contracts pasan; rollback productivo no ejecutado.

## Auditoría globalVar

No se modifica globalVar en esta ventana. Su diff preexistente META_TEAM360 se preserva, sin restaurar credenciales históricas por intuición ni cambiar semántica legacy.

- Import-time: servicio/version/env, DB URLs/schema, Gupshup DEV/PROD, Meta Team360 y opciones futuras.
- Getters runtime: OpenAI key/model leen env; getters DB/Gupshup y helper Meta usan también valores capturados al importar.
- Consumidores baseline: DB settings, health y Gupshup; búsqueda Python de TEAM360_META/helper sólo encuentra globalVar/tests, no un consumidor Srv01 operativo directo.
- Cambio previo Meta puede afectar futuros callers/manuales del helper; no demuestra activación Srv01. No se copian secretos Vertice360/iMotorSoft.
- Nuevos valores diferenciales Srv05 quedan fuera de globalVar. No se migra el inventario completo.

## Validación y límites

Aislamiento PASS: Evolution is the first validated Srv05-only capability entre los entrypoints Team360. ON usa fixtures; Full Gate/Promotion Readiness siguen DEGRADED y no certifican transporte productivo.

- [Tests A–F](../backend/tests/test_srv05_evolution_isolation.py): snapshot Srv01 con/sin env, OFF sin imports, ON sin I/O/workers, config inválida, auth/JSON/guard, binding/schema fail-closed y cleanup, provider fake e idempotencia, coexistencia segura.
- [Source smoke](../backend/scripts/validate_srv05_source_isolation.py): uv sync locked, dos Uvicorn source simultáneos OFF, 27 operaciones cada uno, health, Evolution 404, shutdown y cleanup de grupos propios.
- 20 tests A–F PASS; focalizada final 103 PASS. Full Gate 981 PASS / 3 skips; adicionales 17 PASS / 2 skips (conteos solapados). Gates LAT y diff-check PASS.
- [Full Gate](team360_full_gate_v1.md): Srv05 OFF Structural PASS; Operational DEGRADED. PostgreSQL/Milvus/LiteLLM probes reales; no WhatsApp/Gmail/Gupshup, SAP/HANA, Meta/Cloudflare ni cambios persistentes.
- ON OpenAPI: 28 operaciones, extensión única; coverage/IDs/refs validados. Sin ingress/transporte real ni nueva prueba PG Messaging de escritura; esas integraciones opt-in quedan skipped.
- [Promotion readiness](team360_srv05_promotion_readiness.md) sigue DEGRADED por identidad/segundo tenant y automatización/destino; Evolution ingress/config real es condicional al habilitarlo.
- Evolution es transporte principal previsto; Gupshup se conserva como legacy/fallback no habilitado en esta medición. Su disponibilidad/outbound/ingress no es requisito de promoción cuando Evolution es principal.
- Evidencia: [directorio fechado](../../data/reports/team360-srv05-evolution-isolation/20261011T133928Z/), [comparación](../../data/reports/team360-srv05-evolution-isolation/20261011T133928Z/baseline-comparison.json), [Full Gate nuevo](../../data/reports/team360-srv05-evolution-isolation/20261011T133928Z/full-gate-r2/report.json). Intentos anteriores preservados.

## Siguiente paso

Preparar el asistente Telchi/WhatsApp mediante binding e identidades de prueba autorizadas, manteniendo servicio horizontal. No activar permisos de negocio por número ni promover las consultas SQL DEV existentes implícitamente.

Requiere ventana propia: contexto Telchi canónico, identidad/RBAC y segundo tenant, política de automation/delivery, ingress Evolution y fixture PostgreSQL de extremo a extremo. No deploy ni mensajes reales en este cierre.
