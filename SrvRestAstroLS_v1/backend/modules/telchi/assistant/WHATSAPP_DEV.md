# Primera sesión WhatsApp DEV de TelchiAI

Este runbook conecta el webhook Evolution existente con la composición real Srv05/Telchi. No habilita producción ni sustituye [RBAC y límites comerciales](README.md) o [CONTEXT](../CONTEXT.md).

## Estado y alcance

La implementación está preparada para validación; el estado operativo es **BLOCKED** hasta acreditar aprobación y gates reales. Ningún test con dobles certifica conectividad, credenciales o conversación humana.

- `messaging-only`: transporte y respuesta fija; NO usar para esta sesión.
- `dev_runtime_http`: pipeline real sin salida WhatsApp; sirve como evidencia previa, no E2E WhatsApp.
- `whatsapp_dev start`: `create_telchi_app(policy=...)`, webhook Messaging real y Evolution externo. Un solo worker, sin reload, scheduler Flow ni endpoint HTTP conversacional alternativo.
- `READY_FOR_HUMAN_TEST`: sólo después de preflight, startup y prueba contenedor → webhook autenticado; NO significa conversación observada.
- `E2E_PASS`: declaración humana posterior a revisar intercambio real, resultado empresarial, duplicados/reintentos y salida. El launcher nunca la emite.

No se crean canales, grants, migraciones, servicios, contenedores, autostart ni implementaciones conversacionales nuevas. La frontera piloto restringe transporte a una línea; PostgreSQL, dispatcher y handler siguen resolviendo identidad y permisos en cada turno.

## Preparación privada del operador

Usar Ubuntu y la misma shell con configuración privada aprobada. No pegar secretos, teléfonos, DSN ni payloads en terminal compartida, argumentos, Git o reportes públicos. Desactivar shell tracing.

```bash
cd /media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/SrvRestAstroLS_v1/backend
set +x
umask 077
export TELCHI_PRIVATE=/media/issajar/DEVELOP/Projects/iMotorSoft/ai/private/telchi
export TELCHI_APPROVAL="$TELCHI_PRIVATE/whatsapp-dev-session-approval.json"
```

Cargar el environment privado existente mediante el mecanismo aprobado por el operador, sin imprimirlo. Conservar sus credenciales; migrar la habilitación únicamente con decisión explícita del owner, respaldo y publicación atómica `0600`. Requisitos no secretos:

```bash
export TEAM360_ENV=dev
export AUTOMATION_DIAGNOSIS_REPOSITORY=postgres
export TEAM360_SRV05_EVOLUTION_ENABLED=1
export TEAM360_MESSAGING_DEV_ENABLED=1
export TEAM360_MESSAGING_DISPATCH_MODE=horizontal_v1
export TEAM360_MESSAGING_WORKSPACE_SLUG=telchi_dev
export TEAM360_MESSAGING_CHANNEL_ALIAS=telchi_whatsapp_dev
export TEAM360_EVOLUTION_BASE_URL=http://127.0.0.1:18180
export TEAM360_EVOLUTION_INSTANCE=team360-meta-dev
unset TEAM360_DEV_PROFILE TEAM360_MESSAGING_DEV_SQL_TENANT
unset TEAM360_TELCHI_ASSISTANT_DEV_HTTP TEAM360_BUSINESS_SEMANTICS
```

El environment privado debe aportar `TEAM360_EVOLUTION_API_KEY`, `TEAM360_MESSAGING_WEBHOOK_TOKEN` (32 caracteres mínimo), `TEAM360_MESSAGING_DEV_AUTHORIZED_SENDER` (la única línea aprobada, formato numérico sin `+`), `META_TEAM360_PHONE_NUMBER_ID` (receiver existente), configuración PostgreSQL y la credencial Luna existente. No introducir otra línea ni confundir receiver con piloto.

Evolution debe estar iniciado manualmente por el operador y conectado. El launcher sólo usa su API local; nunca lo arranca/reinicia. Se rechaza un webhook habilitado y también una configuración previa sin URL restaurable o con campos desconocidos.

## Aprobación y gates obligatorios

El owner habilita al remitente verificado para acceder al asistente DEV en un workspace. Esta habilitación no concede permisos comerciales: cada capability consulta el RBAC efectivo de Team360 antes de acceder a Foundation.

Crear con editor privado el archivo `$TELCHI_APPROVAL`, modo `0600`, dentro de `PRIVATE_ROOT`. Su contrato JSON requiere:

- `environment: "dev"`, `tenant_id: "telchi"`.
- `workspace_id` y `user_id`: UUID existentes del workspace y piloto aprobados, no nuevos IDs.
- `sender_sha256`: hash SHA-256 de los dígitos de la única línea aprobada, sin `+` ni espacios. Verificarlo privadamente contra la aprobación humana; no publicar el número.
- `access: "assistant"`, `revoked: false`: habilitación explícita, sin lista de operaciones ni permiso base.
- `module_enabled: true`, `whole_workspace_scope_verified: true`: atestaciones explícitas del owner; delimitan el workspace, no conceden grants.
- `approved_by`: referencia del aprobador; `issued_at`: fecha ISO 8601 con zona, no futura. No existe vencimiento de acceso.
- El contrato anterior con `permission` o `expires_at` se rechaza: requiere migración explícita con respaldo, nunca extensión automática.
- `business_evidence_file`: archivo privado con aprobación y límites revisados; `business_evidence_sha256`: hash exacto.
- `gates_file`: path privado del registro de gates siguiente.

Para revocar, publicar atómicamente `revoked: true` con modo `0600`. La eliminación, corrupción o modificación del scope también bloquea acceso. Se comprueba en cada ingress y autorización, incluida la previa a ejecutar; el launcher cierra la sesión al detectar cambios. Un turno ya ejecutado no se deshace.

Los archivos referenciados deben estar dentro de `PRIVATE_ROOT` y sin permisos de grupo/otros. Mantener también su directorio privado. La herramienta valida integridad y scope, no firma digital: el registro es una atestación del operador basada en artefactos reales, no un productor automático de evidencia.

Antes de tráfico, ejecutar los gates HTTP existentes según su [runbook](tests/runtime_http/README.md), con preflight de recursos y servicios. Esas sondas pueden escribir eventos DEV y consumir modelo, pero no deben enviar WhatsApp. Sus reportes privados no se publican íntegros.

```bash
# Un runner por vez; paths nuevos y privados. No ejecutar sin preflight de servicios.
uv run python -m modules.telchi.assistant.tests.runtime_http.run_battery \
  --output "$TELCHI_PRIVATE/http-before-whatsapp-new"
uv run python -m modules.telchi.assistant.tests.runtime_http.security_probes \
  --output "$TELCHI_PRIVATE/security-before-whatsapp-new"
uv run python -m modules.telchi.assistant.tests.runtime_http.restart_continuity \
  --output "$TELCHI_PRIVATE/restart-before-whatsapp-new"
```

No tomar automáticamente esos comandos como todos los gates aprobados: el adapter HTTP tiene un claim distinto de Messaging. Idempotencia durable, concurrencia/reintentos y aislamiento del ingress requieren evidencia real del pipeline Messaging y PostgreSQL además de los contratos con dobles. Si falta una garantía, conservar **BLOCKED**; no editar código ni etiquetar un doble como real para desbloquear.

Registrar seis garantías con nombres exactos: `http_auth`, `identity_tenant_isolation`, `business_authorization`, `durable_idempotency`, `assistant_foundation`, `model_no_fallback`. Cada entrada exige `status: "PASS"`, `kind: "real"`, `artifact` privado y `sha256` exacto. El artefacto debe identificar comandos, runtime, fecha, inputs/scope y resultado revisado.

La evidencia de modelo debe demostrar el modelo y esfuerzo devueltos por Luna, credencial/proveedor efectivos y ausencia de fallback; evidencia Foundation debe demostrar capacidad disponible y resultado real. No se realiza una llamada al modelo en el preflight sin efectos. No agregar Milvus o SAP como requisitos de una consulta que no los consume.

El registro DEV versión 2 lleva `schema_version: 2`, `environment: "dev"`, `validity_policy: "change_based_v1"`, `issued_at` con zona y no futuro, `workspace_id`, `user_id`, `instance: "team360-meta-dev"`, `approval_sha256`, `source_sha256`, `configuration_sha256` y exactamente los seis `gates`. No admite `expires_at`. Obtener los fingerprints de aprobación/código sin iniciar servicios:

```bash
uv run python -m modules.telchi.assistant.whatsapp_dev fingerprint --approval "$TELCHI_APPROVAL"
```

DEV no caduca por tiempo: la evidencia permanece válida mientras no cambien sus condiciones. `configuration_digest()` identifica el environment privado permitido por el lifecycle, incluidas credenciales sin publicarlas; `source_digest()` incluye código, contratos Markdown/JSON/SQL, migraciones y dependencias. Cambiar aprobación, configuración, código, contratos o artefactos invalida el registro; se reacreditan las garantías afectadas. Ingress y autorización verifican aprobación e integridad; RBAC, identidad, binding, Foundation y modelo conservan sus controles dinámicos existentes. Una evidencia no garantiza disponibilidad externa futura.

Sólo `TEAM360_ENV=dev|development` del operador y aprobación/manifiesto DEV admiten esta política. Producción y entornos desconocidos rechazan manifiestos DEV versión 2; el contrato legacy conserva su `expires_at`. El usuario WhatsApp no selecciona la política. La duración manual del proceso sigue independiente de la acreditación.

Migrar exige preservar el manifiesto anterior, verificar sus fingerprints y artefactos originales, revisar el diff y registrar qué garantías se reutilizan y cuáles se revalidaron. Publicar la atestación versionada mediante reemplazo atómico con modo `0600`, conservar procedencia/fechas originales y ejecutar el preflight normal. Ni retirar una fecha ni actualizar un hash sin evidencia acredita garantías. Los contratos offline no sustituyen evidencia operacional.

## Preflight sin efectos externos

El comando siguiente hace lecturas PostgreSQL en transacción READ ONLY y GET autenticados a Evolution. No abre listener, cambia webhook, llama al modelo, ejecuta capability, envía mensajes ni escribe reportes.

```bash
uv run python -m modules.telchi.assistant.whatsapp_dev preflight \
  --approval "$TELCHI_APPROVAL"
```

Debe terminar en `PREFLIGHT_PASS`. Un fallo devuelve `BLOCKED` sin datos sensibles. Acredita binding DEV, receiver, teléfono verificado, usuario esperado activo, schema, habilitación/gates y Evolution abierto con webhook deshabilitado. Los permisos comerciales no son requisito de ingreso: se verifican dinámicamente por capability con el resolver Console y la conexión PostgreSQL del turno. La conectividad desde contenedor sigue pendiente hasta el inicio manual.

## Inicio manual y única pregunta

Este paso sí activa temporalmente el webhook; requiere una nueva acción explícita del operador. **No ejecutarlo durante la preparación de esta tarea.** Reservar Evolution y el puerto para esta sesión, sin otro writer de webhook.

Determinar privadamente la IPv4 específica del host que resuelve `host.containers.internal` en el contenedor. No usar `0.0.0.0` ni loopback; no cambiar firewall/red para forzar el gate. El directorio de salida debe ser nuevo, con padre existente dentro de `PRIVATE_ROOT`.

```bash
read -r -p 'IPv4 específica del host accesible desde Evolution: ' TELCHI_WEBHOOK_HOST
uv run python -m modules.telchi.assistant.whatsapp_dev start \
  --approval "$TELCHI_APPROVAL" \
  --host "$TELCHI_WEBHOOK_HOST" --port 18181 \
  --idle-timeout 900 --max-duration 14400 \
  --container evolution-api \
  --output "$TELCHI_PRIVATE/whatsapp-dev-session-new"
```

La sesión ya no cierra por una duración fija: permanece mientras haya actividad y se cierra por inactividad (`--idle-timeout`, 900 s por defecto) o por duración máxima (`--max-duration`, 14.400 s por defecto). Un turno en curso nunca se interrumpe. La actividad y el motivo del cierre quedan en `activity.json` y `closure.json` dentro del directorio privado de salida. Para extender una sesión activa, ajustar `idle_timeout` o `max_duration` en el control privado `whatsapp-dev-control.json`: el controlador relee esas claves sin tocar el entorno.

El launcher conserva backup privado antes de mutar, verifica su listener mediante nonce, prueba desde el contenedor token inválido y evento ignorado con token válido y sólo entonces configura el webhook. Ninguna prueba genera un mensaje WhatsApp. El proceso permanece foreground hasta Ctrl-C, expiración o error.

Esperar `READY_FOR_HUMAN_TEST`. Desde el teléfono piloto aprobado, abrir el chat con la línea de la instancia DEV y enviar **una sola vez**:

> Mostrame los 10 productos con mayor cantidad documental de ventas del 1 de enero al 15 de septiembre de 2026 inclusive, sin filtrar sucursal ni canal y sin comparación.

La capability de este ejemplo exige `[2026-01-01, 2026-09-16)` y cantidad documental; no certifica importe, facturación neta ni ventas físicas comparables. No es una limitación de la habilitación del piloto. Otras capabilities existentes, como últimas facturas, conservan su propio contrato y RBAC. Esperar la respuesta; no reenviar ante demora o timeout. Si pide aclaración, falla o declara no disponible, registrar ese resultado; no fabricar una cifra ni declarar E2E_PASS.

## Evidencia correlacionada

Los eventos privados existentes de Messaging y la auditoría `telchi_assistant_v1` son la fuente; no se copian payloads ni teléfonos. Un operador autorizado obtiene el UUID inbound desde PostgreSQL por su herramienta aprobada, sin publicarlo junto a datos personales.

Desde otra shell con la misma configuración, leer un único intercambio sin enviar nada:

```bash
read -r -p 'UUID del evento inbound a revisar: ' TELCHI_INBOUND_ID
uv run python -m modules.telchi.assistant.whatsapp_dev inspect \
  --approval "$TELCHI_APPROVAL" --inbound-id "$TELCHI_INBOUND_ID"
```

El resumen exige ingress Evolution (no adapter HTTP), owner tenant/workspace/usuario, ejecución TelchiHandler, contrato capability/permiso, auditoría RBAC y hash de habilitación, lineage Foundation, correlación y texto preparado igual al enviado; muestra sólo hashes y estados reducidos. Falta de ejecución autorizada bloquea el resumen.

Revisar además en la auditoría privada capacidad concreta, publicación/snapshot/actualización Foundation, período y límites, y contrastar el resultado con la lectura autorizada independiente. Conservar evidencia del fence/duplicados y reintentos sin reinvocar capability ni crear un segundo outbound. No reenviar una pregunta con otro ID como prueba de deduplicación: sería otra consulta legítima.

`provider_accepted` significa receipt/ID de Evolution, no entrega. `delivered_callback` y `read_callback` indican únicamente los callbacks correspondientes; lectura no se infiere de aceptación. El usuario debe confirmar qué respuesta vio en el teléfono. `EXCHANGE_OBSERVED_REVIEW_REQUIRED` nunca equivale automáticamente a `E2E_PASS`.

## Cierre y recuperación

Cerrar con Ctrl-C una sola vez o dejar expirar la ventana. Se restaura y verifica el webhook antes de terminar el hijo propio; un turno en curso dispone de hasta 100 segundos para cerrar. No se matan procesos ajenos ni se toca Evolution.

Revisar privadamente `closure.json`: exigir `webhook_restored=true` y `backend_stopped=true`; conservar `webhook-backup.json` con sus headers secretos fuera de Git. Nunca imprimirlo ni adjuntarlo a un reporte público. Verificar que el puerto propio ya no escucha, sin terminar listeners de ownership dudoso.

Tras SIGKILL, caída del host, API inaccesible o restauración fallida, no asumir rollback automático. El backup durable permite recuperación explícita:

```bash
uv run python -m modules.telchi.assistant.whatsapp_dev restore \
  --backup "$TELCHI_PRIVATE/whatsapp-dev-session-new/webhook-backup.json"
```

Exigir `RESTORATION_VERIFIED`; el comando también sirve para verificar el cierre normal. Si encuentra configuración distinta de la original o temporal, no la sobrescribe: **BLOCKED**, reconciliación manual de ownership. Un fallo de restore exige atención inmediata del operador; no reiniciar servicios ni repetir la conversación para ocultarlo.

## Validación local y límites

Los contratos locales usan dobles y no prueban disponibilidad de servicios. Ejecutarlos secuencialmente antes de reunir evidencia operacional nueva.

```bash
uv run pytest modules/telchi/assistant/tests/test_whatsapp_dev.py \
  tests/test_telchi_assistant_srv05.py tests/test_messaging_horizontal_runtime.py -q
```

El wrapper no implementa exactly-once universal. Reutiliza claim, intent y fence durable Messaging: una salida lógica por inbound; send incierto no se reintenta automáticamente y un crash entre resultado e intent puede dejar `execution_uncertain`. Escalar a reconciliación, no volver a ejecutar negocio.

La configuración de webhook no tiene compare-and-swap del proveedor: la reserva exclusiva y las verificaciones reducen carreras, pero no sustituyen coordinación. Los procesos propios son un único Uvicorn sin reload/workers y sus llamadas acotadas; no se deja un servicio permanente.
