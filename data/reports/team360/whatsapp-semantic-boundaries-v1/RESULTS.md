# Corrección semántica y siguiente prueba WhatsApp

Rama feature/console-backend-core; HEAD preservado: 09d2ec715a31bb88574d734eacb9f437f008624e. Telchi, Development; ventas/cobranzas/proveedores como contexto de compatibilidad, sin nuevos conceptos, grants, migraciones ni cambios de Foundation.

## Causa y corrección

La similitud recuperaba palabras presentes incluso en las limitaciones negativas de las definiciones. Score/margen no verificaban entidad, dominio ni dirección de la deuda.

Los [tests previos](before.log) reproducen entrega incorrecta de definiciones con score 0.99. La [segunda reproducción](direction-before.log) demuestra que reconocer la entidad sin su relación tampoco basta: venta a una sucursal no es venta en ella; deuda de clientes a terceros no es deuda hacia Telchi.

El resolver existente ahora comprueba compatibilidad conservadora contra las definiciones publicadas:

- Farmacia como sucursal de origen no equivale a producto farmacéutico ni farmacia destinataria/cliente. Alcance mixto o insuficiente solicita aclaración.
- Deuda de clientes hacia la empresa no equivale a obligaciones con proveedores, acreedores, terceros o deuda de la propia empresa hacia clientes.
- Un veto no reranquea al segundo candidato ni convierte deuda a proveedores en recomendación de importación. Las restricciones también cubren FTS y referencias heredadas; una contradicción explícita no desaparece si fallan embeddings o FTS no devuelve hits.
- El handler responde NEEDS_CLARIFICATION/ASK sin llamar Luna ni capabilities cuando el alcance está vetado. Conserva el estado anterior; no fabrica un plan pendiente ni autoridad de ejecución.
- Exact aliases completos ya aprobados conservan su contrato. No se tocaron definiciones, aliases, publicaciones, embeddings almacenados, thresholds ni el holdout.

Son checks léxicos conservadores de compatibilidad, no verificación de IDs comerciales ni un clasificador general. Pueden abstenerse ante negaciones, paráfrasis o alcances mixtos. No acreditan pertenencia real, saldos, disponibilidad de capabilities ni permisos.

## Evidencia ejecutada

El probe usa PostgreSQL y embeddings reales con el rol semántico restringido, en READ ONLY y sin impersonar usuarios.

- [Corrida verificada](real-pgvector-verified.json): 24 consultas contrastivas nuevas, escritas fuera del corpus congelado; 24 contratos de compatibilidad pasan, sin candidato numéricamente elegible en los negativos nuevos después del veto. Alias/modelo/dimensión concordantes con la medición previa; fallbacks vacíos y cero escrituras.
- Los dos casos conocidos pasan de candidato elegible a rechazado: medicamentos→farmacias y proveedores→cuentas por cobrar. El replay reutiliza scores reales previos contra el mismo catálogo/versiones, no inventa scores nuevos.
- Corpus 16+16 intacto: SHA256 db493536ca535b76ec4813adbab7dcd8550c628d1baef22a6229e6b4f7b1bdad. El replay es vectorial: no reemplaza el camino exacto aprobado. No se usó holdout para ajustar parámetros.
- Los dos negativos sobre oportunidades perdidas del holdout siguen fuera de esta corrección acotada. No se certifica calidad general ni se abre otra línea para resolverlos aquí.
- [Regresión focalizada](tests.log): 280 PASS / 0 FAIL, un warning heredado de Diagnosis in-memory. Contratos semánticos, estado/handler, autenticación HTTP, Evolution/Messaging, ASK/BLOCK/EXECUTE, correlación e idempotencia. Las pruebas de HTTP/auth/transporte con dobles son contratos, no evidencia de sesiones humanas ni WhatsApp entregado.

Una primera corrida del probe terminó con InsufficientPrivilege al consultar metadata de transporte desde el rol semántico. Se retiró esa lectura del probe; no se añadieron grants ni se elevó el rol. Las corridas posteriores separan correctamente evidencia semántica de evidencia de transporte.

## HTTP autenticado: preparado, todavía no acreditado

La ruta DEV existente ahora reutiliza ConsoleLoginService.verify_session cuando Business Semantics está habilitado. No hay endpoint de login nuevo ni emisión de tokens en HTTP.

Además del gate DEV existente, exige Bearer PASETO password vigente, workspace concordante y credential_version activa. Verifica en la conexión restringida; exige que el sujeto autenticado coincida con el binding telefónico aprobado antes de persistir el evento y vuelve a comprobarlo en dispatch. RBAC comercial sigue siendo el existente.

El audit ahora obtiene current_user/rolsuper/rolbypassrls de la misma conexión usada por retrieval, no del DSN. El probe HTTP exige esa evidencia, correlación y cero ejecución; un HTTP 200 solo no pasa.

La comprobación puntual real devuelve **0 credenciales password activadas**. En el directorio de la ceremonia no hay manifiesto autorizado ni archivos de sesión. No había listener Srv05/DEV HTTP activo observado. Por ello no se inició un servidor con identidad fija para simular este cierre ni se declaró HTTP autenticado PASS.

Tras consentimiento, ceremonia vigente y configuración DEV aprobada del listener existente, el comando de prueba es:

```bash
cd SrvRestAstroLS_v1/backend
export TEAM360_ENV=dev
AUTH_DIR=/media/issajar/DEVELOP/Projects/iMotorSoft/ai/private/telchi/console-auth-window-20261014T134648Z
AUTH_CONFIG="$AUTH_DIR/issuer.json"
export TEAM360_BUSINESS_SEMANTICS=1
export TEAM360_SEMANTICS_AUTH_CONFIG="$AUTH_CONFIG"
# El operador inicia dev_runtime_http con su configuración de canal/gate/phone
# ya aprobada; no se elige automáticamente otra identidad ni otro teléfono.
SESSION="$AUTH_DIR/http-$(date -u +%Y%m%dT%H%M%SZ).paseto"
uv run --no-sync python -m modules.console.login_cli login \
  --config "$AUTH_CONFIG" --workspace "$AUTHORIZED_WORKSPACE_SLUG" \
  --email "$AUTHORIZED_EMAIL" --token-output "$SESSION"
uv run --no-sync python -m modules.telchi.assistant.tests.runtime_http.authenticated_semantics_probe \
  --base-url http://127.0.0.1:7090 --session-file "$SESSION" \
  --dev-token-file "$DEV_TOKEN_FILE" --expect scope \
  --output ../../data/reports/team360/whatsapp-semantic-boundaries-v1/http-authorized.json
```

DEV_TOKEN_FILE es un archivo privado 0600 con el gate token del listener existente, no una contraseña ni un token generado para saltar auth. La sesión debe pertenecer al usuario del teléfono consentido y tener el permiso comercial existente. El probe usa una consulta controlada de proveedores que debe aclarar sin ejecutar negocio.

Repetir el probe con sesión legítima de otro tenant usando --expect deny y otro output. Para RBAC negativo, usar una identidad consentida sin el permiso requerido y su binding aprobado; no revocar permisos ajenos ni cambiar bindings sólo para fabricar el test. Esas sesiones/canales autorizados siguen pendientes.

## Ceremonia preservada

No se modificó authenticated_gate.py ni se ejecutó enrollment/login/reset. Se conserva el [ejecutor y procedimiento anterior](../whatsapp-progress-v1/RESULTS.md#una-ceremonia-humana).

SHA256 del ejecutor conservado: 307398c065dba17f11b09a6ae0f06fc555cafd5fc01ea3b5a32256835894592f. No activar sus flags de enrollment sin consentimiento y manifiesto. El gate CLI consume y elimina sus propios tokens; la prueba HTTP necesita un login fresco inmediatamente antes del probe, no recuperar tokens ya eliminados.

## Preparación de entrega WhatsApp real

Se reutilizan Messaging y Evolution sin crear un sender, callback ni catálogo paralelo. El probe de receipts sólo lee tres intercambios controlados seleccionados explícitamente.

Los contratos con dobles ahora incluyen EXECUTE con una única llamada de capability, además de ASK, BLOCK, duplicados concurrentes, único outbound y correlación. No hubo envíos reales en esta ventana.

Para la prueba real, preparar fuera de Git un manifiesto privado con workspace_slug, channel_alias, instance y tres cases. Cada case contiene kind (ASK/BLOCK/EXECUTE), inbound_id real y duplicate_receipt_file. No inventar IDs ni usar eventos del adapter HTTP.

El operador envía los tres mensajes desde teléfonos consentidos sobre el canal autorizado. EXECUTE sólo con consulta/capability comercial ya autorizada y revisión humana del resultado; no publicar conceptos ni escribir Foundation. Para cada evento controlado real, conservar su payload privado y repetir su webhook con el gate existente:

```bash
curl --fail --silent --show-error --config "$PRIVATE_REPLAY_CURL_CONFIG" \
  --data-binary @"$PRIVATE_CONTROLLED_PAYLOAD" "$APPROVED_LOCAL_INGRESS" \
  > "$PRIVATE_DUPLICATE_RECEIPT"
```

El config privado contiene el header ya autorizado; secretos fuera de argv/logs. La respuesta debe ser results duplicate=1, sin otro outbound ni ejecución. No se reenvían mensajes comerciales históricos.

Después, desde backend:

```bash
uv run --no-sync python -m modules.telchi.assistant.tests.runtime_http.whatsapp_delivery_probe \
  --auth-config "$AUTH_CONFIG" --manifest "$AUTH_DIR/whatsapp-receipts.json" \
  --output ../../data/reports/team360/whatsapp-semantic-boundaries-v1/whatsapp-receipts.json
```

Exige canal DEV Telchi, ingreso Evolution real, exactamente un outbound por inbound, texto preparado/dispatch/outbound concordante, correlación, número de ejecuciones correcto, replay duplicado y callback delivered/read del mismo provider_message_id. Acceptance/sent sin callback falla. Consulta acotada a tres IDs y máximo 100 filas, con conexión de operador pinneada READ ONLY; no amplía permisos del rol semántico a tablas de transporte.

El resultado máximo automático es DELIVERY_OBSERVED, nunca E2E. Aún exige confirmación visible de entrega en el dispositivo y revisión comercial autorizada. Sin esos registros no se ejecutó ni se declaró ese resultado aquí.

## Alcance, validación y paso mínimo

El blast radius cubre cinco archivos runtime existentes: resolver y repository semánticos, handler, adapter HTTP DEV y repository de conversación para evidencia acotada. El resto son regresiones/probes/evidencia, necesarios para demostrar causa, auth y entrega sin mocks ocultos.

Paths modificados bajo backend: modules/business_semantics/resolver.py y repository.py; modules/telchi/assistant/handler.py, dev_runtime_http.py y repository.py. Pruebas: test_operational_closure.py ajusta su paráfrasis a una entidad compatible; test_whatsapp_controlled_transport.py agrega EXECUTE/correlación. Nuevos: test_entity_boundaries.py y su fixture, validate_candidate_scopes.py, test_dev_http_session.py, test_live_probe_contracts.py y los dos probes runtime_http. Evidencia nueva sólo en este directorio.

Comando focalizado ejecutado desde backend:

```bash
uv run --no-sync pytest -q modules/business_semantics/tests modules/telchi/assistant/tests/test_assistant.py modules/telchi/assistant/tests/test_whatsapp_controlled_transport.py modules/telchi/assistant/tests/test_dev_http_session.py modules/telchi/assistant/tests/test_live_probe_contracts.py tests/test_messaging_evolution.py tests/test_messaging_horizontal_runtime.py tests/test_messaging_handlers.py tests/test_telchi_assistant_srv05.py
```

No se alteraron pool global, launchers, registry, producción, Foundation, L&S, frontend, dependencias ni Git. Se preservan cambios ajenos del worktree. Sólo se agregan un veto al camino actual, evidencia del rol y reutilización del verificador actual.

El camino mínimo sigue siendo: manifiesto/consentimiento → ceremonia existente → HTTP con sesión y teléfono concordantes + negativos tenant/RBAC → tres intercambios WhatsApp con callbacks/replay → confirmación humana y consulta comercial autorizada.

Validación final: git diff --check y lat check md/index/sections/code-refs/check terminaron con salida 0; logs conservados aquí. Revisión final de los cambios propios realizada; HEAD y SHA256 del ejecutor de ceremonia concordantes con los registrados arriba.

Host seguro: ~5.5–6 GiB disponibles, swap sin crecimiento/si-so observado, carga moderada en ocho cores. HOST_PREFLIGHT=SAFE, RESOURCE_GUARD=PASS, CONCURRENCY_USED=1; solicitudes embedding secuenciales. UNRELATED_PROCESSES_TERMINATED=0, ENVIRONMENTAL_ABORTS=0, OWN_PROCESSES_LEFT_RUNNING=0. No se crearon browsers, listeners ni workers persistentes.
