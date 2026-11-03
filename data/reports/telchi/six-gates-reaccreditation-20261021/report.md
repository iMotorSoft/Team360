# Reacreditación final de los seis gates DEV — TelchiAI

Cierre de gates sobre el código final de *WhatsApp Reliability & UX V1* en
`feature/console-backend-core`. No inicia sesión, no envía WhatsApp, no muta
webhook, grants, bindings, credenciales, aprobación ni Foundation.

- Runner: [reaccredit.py](reaccredit.py) · Cierre: [closure.json](closure.json)
- Evidencia privada: `PRIVATE_ROOT/six-gates-20261022T010320757066Z/` (0600, no secretos aquí)
- Primeiro intento bloqueado: [first-attempt-blocked.json](first-attempt-blocked.json) y
  [focused-tests-first-attempt-umask.txt](focused-tests-first-attempt-umask.txt)

## Resultado

```text
SIX_GATES=VALID
CURRENT_CODE_FINGERPRINT=VALID
CURRENT_PILOT_CONTRACT=VALID
REAL_SECURITY_BOUNDARIES=PASS
DEV_GATE_POLICY=change_based_v1
READY_FOR_MANUAL_START=YES
WHATSAPP_E2E=NOT_RUN
SOURCE_DIGEST=283418ac5df5e5bd4ef67ae8c27d2538c8b92e9f69cb4e5b11b78e2db6583f8f
```

Las seis garantías son `PASS` y `kind=real`, con artefacto privado y hash exacto:

| Gate | Observación real | Evidencia |
| --- | --- | --- |
| `http_auth` | HTTP inerte real sobre `PilotBoundary` + alcance desde el contenedor Evolution | 401 / 401 / 400 / 200 y sonda de contenedor `PASS`; sin lifespan ni eventos de mensaje |
| `identity_tenant_isolation` | PG real de solo lectura: binding y usuario aprobados | Tenant y workspace ajenos ausentes y denegados; identidad `revoked`/`inactive` rechazada; sin mutar fixtures |
| `business_authorization` | Concesión efectiva real de Console | Caché vacía admite el piloto pero deniega la operación; caché forjada denegada por el resolver vivo; revocación del piloto denegada; 0 grants cambiados |
| `durable_idempotency` | PG real: dos reclamos concurrentes y reintento secuencial | `execution_uncertain` / `accepted` / `duplicate`; 1 handler, 1 capability, 1 outbound durable; egreso de grabación, no entrega |
| `model_no_fallback` | Una petición Luna real | `gpt-5.6-luna`, `medium`, `OpenAI direct`, `reasoning_echo_verified`, 1 intento; sin provocar caída de proveedor |
| `assistant_foundation` | Una ejecución real de capability con consulta Foundation de solo lectura | `foundation_afd08d9eca6a725be53cdc3f9d5709c9`, snapshot `1408`, 10 filas, sin mutar publicación |

## Causas reales de `SIX_GATES=INVALID` y su corrección

ElINVALID no provenía de un fallo de negocio sino de dos defectos de acreditación,
ambos demostrados y corregidos sin tocar la arquitectura que ya funcionaba.

**1. Fingerprint de código obsoleto.** El manifiesto publicado fijaba
`source_sha256=15fb1eef…` y el código final da `283418ac…`: los cambios de
*WhatsApp Reliability & UX V1* (14:54–15:16 del 21/10) caen dentro del alcance
del digest, que incluye código, contratos, migraciones y dependencias. El
lanzador rechazaba el arranque con `gate_scope_mismatch`. La reacreditación
reejecuta las seis garantías contra el código actual y publica el digest final.

**2. Formato de registro DEV regresionado.** El manifiesto publicado estaba en la
forma **legacy** con vigencia artificial de cuatro horas (`expires_at`), y ya
había expirado a las 17:48Z del 21/10. La política DEV aprobada por el owner
es `change_based_v1` (migración `dev-gate-policy-v1` del 19/10 y
`modules/telchi/assistant/WHATSAPP_DEV.md`): versión 2, sin `expires_at`, con
`issued_at` y `configuration_sha256`. Las publicaciones del 21/10 a las 13:35 y
13:48 reintrodujeron la forma legacy. El registro nuevo vuelve a la forma
aprobada y queda **sin caducidad artificial**: se invalida por cambio de código,
aprobación o configuración, no por reloj.

## Segundo bloqueo, independiente de los gates

Los gates no eran el único obstáculo. El control privado
`whatsapp-dev-control.json` conservaba la clave legacy `duration: 600`, de modo
que `launch()` resolvía `--idle-timeout 900 --max-duration 600` y
`session_timing()` lanzaba `idle_timeout_exceeds_max_duration`: **el arranque
manual habría fallado aunque los gates fueran válidos**.

Corrección: el control privado pasa a `idle_timeout: 900` y `max_duration: 14400`
—la política de 15 min de inactividad y 4 h máximas de la V1— y se retira la
clave legacy. El bloque `env` (credenciales) queda **byte a byte idéntico**
(`f713b1a1…` antes y después); el fichero conserva modo `0600` y se guardó
respaldo en `PRIVATE_ROOT/backups/control-20261022T003533662784Z/`.

Verificación posterior a la corrección, con el mismo código que usa el lanzador:

```text
launch() argv -> ['--idle-timeout', '900', '--max-duration', '14400']
session_timing -> (900, 14400)
session_policy(control) -> (900, 14400)
idle 900 alcanzado              -> idle_timeout_reached
idle 900 con turno en curso     -> None            (el turno no se interrumpe)
max 14400 alcanzado             -> max_duration_reached
dentro de ambos límites         -> None
```

## Primer intento: bloqueado y preservado

El primer intento.blocks en `publish()`, **sin publicar manifiesto**
(`manifest_changed=false`). La causa fue la suite focalizada, no los gates:
el subproceso heredaba el `umask 077` del runner, y la prueba
`test_insecure_state_directory_is_not_repaired` crea un directorio deliberadamente
inseguro (`0755`) para comprobar que **no** se repara; con `umask 077` ese
`mkdir` produce `0700`, la fixture negativa nunca llega a ser insegura y la
prueba falla.

Es un artefacto de la fixture, no un defecto del producto: la misma prueba pasa
con `umask 022` y falla con `umask 077`. La corrección es la ya sanctioned en
`dev-gate-policy-v1/migrate.py` —las pruebas de permisos usan el umask normal de
test, mientras el runner y sus artefactos siguen en `077`/`0600`—. Se corrige el
runner y se preservan ambos logs.

## Validación

```bash
cd SrvRestAstroLS_v1/backend
pytest modules/telchi/assistant/tests tests/test_messaging_evolution.py \
       tests/test_messaging_horizontal_runtime.py tests/test_messaging_handlers.py -q
# 753 passed, 4 skipped in 41.19s
```

Comprobaciones posteriores e independientes del runner:

- `d.gate_evidence(approval)` → `PASS`
- `d.preflight(approval)` en la vía normal, gates requeridos → `PREFLIGHT_PASS`
- `telchiai-dev.sh status` → `gates: VALID`, `state: STOPPED`, `webhook: INTERNAL`
- Los seis artefactos resuelven a fichero privado y su hash coincide con el manifiesto
- 322 ficheros del alcance del digest: **ninguno** cambiado ni añadido desde la
  instantánea tomada antes de la corrección, luego no hubo cambios concurrentes
  que invalidaran el resultado

## Límites y estado

- `WHATSAPP_E2E=NOT_RUN`: no se envió ningún mensaje. Los dos únicos outbound
  generados en esta ventana son filas `duridem-` de egreso de grabación; el
  último outbound real por WhatsApp es del 21/10 a las 14:03Z, de la sesión
  previa del owner.
- Sin sesión: `state=STOPPED`, `webhook_restored=true`, `backend_stopped=true`,
  `review_reasons=[]`, sin listener en 18181 y sin procesos propios vivos.
- 0 cambios en grants, bindings, credenciales, aprobación, webhook o
  Foundation; 0 servicios compartidos iniciados o detenidos; 0 procesos ajenos
  terminados.
- La egreso de grabación acredita intención lógica, **no** entrega por WhatsApp.
- El inicio manual de la sesión y la conversación de Presidencia siguen siendo
  del owner; no se inició ninguna sesión automáticamente.

## Pendiente que queda al owner

La rotación de credenciales DEV potencialmente expuestas no se ejecutó: exige
coordinación con servicios compartidos (Evolution, webhook y PostgreSQL) y una
ventana propia, fuera de esta ventana. La lista de variables y su impacto están
en el informe de fiabilidad de entrega; ningún valor se copió aquí.
