# Avance funcional hacia WhatsApp

Rama: feature/console-backend-core. Alcance DEV: pgvector real, conexión semántica restringida, contratos de transporte y ejecutor humano. Sin deploy, cuentas activadas, grants, cambios del pool global ni acceso a Foundation/SAP.

## Resultados ejecutados

La evidencia nueva distingue servicios reales de dobles; no acredita consultas comerciales por WhatsApp.

- [pgvector real](pgvector.json): 16 calibración + 16 holdout, nueve conceptos publicados, embeddings vía LiteLLM, upstream openai/text-embedding-3-small, dimensión 1536 y fallbacks vacíos. Rol restringido, transacción READ ONLY, cero escrituras y sesiones humanas.
- Política provisional congelada antes de ambos splits: score 0.4, margen 0.05. Elegibles: 11/16 calibración y 4/16 holdout. No se ajustaron parámetros ni se usó holdout para tuning. Esto mide retrieval; no certifica respuestas ni exactitud comercial.
- Riesgos observados: medicamentos → sucursales farmacia y deudas con proveedores → cuentas por cobrar son candidatos elegibles incorrectos para esas restricciones. También elegibles los negativos sobre Top20/ventas perdidas y ausencia de datos/oportunidades. No habilitar ejecución por similitud. Los candidatos siguen sin auto-confirmarse; la política no queda certificada.
- [Antes](connections-before.json): la configuración base resolvía administrator/SUPERUSER/BYPASSRLS. [Después](connections-after.json): el puerto semántico real del handler usa team360_business_semantics_dev_runtime, sin esos privilegios; catálogo real leído, configuración global intacta. No se inició listener Srv05: prueba viva del puerto de conexión + composición cubierta por test, no petición HTTP autenticada.
- [Tests focalizados](focused-tests.log): 204 PASS / 0 FAIL, un warning heredado sobre repositorio in-memory de Diagnosis. Contratos Evolution HTTP/mapper, Messaging real, handler Telchi y respuestas ASK/bloqueo por identidad/plan inválido; duplicados concurrentes y reintentos generan un solo outbound. DB, identidad, intérprete y HTTP Evolution son dobles declarados; cero datos comerciales. No es E2E WhatsApp ni entrega real.
- No se envió WhatsApp real: no había listener Srv05 activo observado. No se modificaron callbacks/suscripciones ni destinos para forzar el canal.

## Cambio mínimo de conexión

La composición Telchi exige configuración privada cuando Business Semantics está habilitado; no cambia Srv01 ni el pool compartido.

Antes del próximo arranque DEV autorizado del runtime existente, añadir a su entorno:

```bash
export TEAM360_SEMANTICS_AUTH_CONFIG=/media/issajar/DEVELOP/Projects/iMotorSoft/ai/private/telchi/console-auth-window-20261014T134648Z/issuer.json
```

No activa Business Semantics por sí sola. Con TEAM360_BUSINESS_SEMANTICS=1 y sin esa configuración, la composición rechaza el arranque. Cada uso comprueba cluster/DB y privilegios reales; un rechazo no cae al pool global ni llama Luna. Conversación conserva su conexión anterior. Las observaciones semánticas tienen transacción propia; no se afirma atomicidad conjunta con conversación. RLS continúa ausente.

## Una ceremonia humana

Se reutilizan login_cli y el [runbook vigente](../../../../SrvRestAstroLS_v1/docs/team360_console_dev_password_login_v1.md). Cada login se consume inmediatamente; no se espera a reunir cuatro tokens dentro de los 900 segundos.

Desde la raíz, preparar el manifiesto privado con cuatro identidades existentes y consentidas: dos lectores Telchi distintos sin rol administrador, administrador Telchi distinto y cuenta de otra organización/workspace. No crear usuarios ni cambiar roles para satisfacer la prueba.

```bash
cd SrvRestAstroLS_v1/backend
export TEAM360_ENV=dev
AUTH_DIR=/media/issajar/DEVELOP/Projects/iMotorSoft/ai/private/telchi/console-auth-window-20261014T134648Z
AUTH_CONFIG="$AUTH_DIR/issuer.json"
MANIFEST="$AUTH_DIR/authorized-identities-whatsapp.json"
# No sobrescribir un manifiesto previo.
( set -C; umask 077; cp --no-clobber modules/business_semantics/authorized-identities.example.json "$MANIFEST" )
"${EDITOR:-nano}" "$MANIFEST"

uv run --no-sync python -m modules.business_semantics.authenticated_gate \
  --auth-config "$AUTH_CONFIG" --manifest "$MANIFEST" \
  --output ../../data/reports/team360/whatsapp-progress-v1/human-gate.json \
  --prepare-only
```

Completar solamente email, workspace slug, user_id y workspace_id reales en el editor. Sin passwords/tokens. El preflight valida identidades activas, tenant y roles antes de pedir contraseñas. Si falla, no se activa ninguna cuenta.

Con cuentas ya habilitadas y consentimiento explícito para cada login, ejecutar una vez. Esta ventana no autoriza enrollment, activación ni reset:

```bash
uv run --no-sync python -m modules.business_semantics.authenticated_gate \
  --auth-config "$AUTH_CONFIG" --manifest "$MANIFEST" \
  --output ../../data/reports/team360/whatsapp-progress-v1/human-gate.json
```

El flag histórico --enroll-authorized sigue disponible sólo para el gate completo bajo autorización independiente; no usarlo en esta ceremonia. El modo diagnóstico lo rechaza. El login CLI pide contraseña por TTY; tokens privados propios se borran al terminar cada identidad.

Valida sesión password/credential_version, sujeto esperado, lectura exacta autorizada, catálogo común entre dos usuarios distintos, denegación de sesión/retrieval/administración en otro tenant, denegación administrativa de lectores y administración del admin con rollback, incluida inmutabilidad de aliases publicados. Ejecuta además cli list existente y verifica su RBAC. No imprime catálogo ni tokens.

La prueba administrativa publica únicamente un concepto sintético dentro de una transacción que siempre hace rollback. No quedan conceptos, aliases, publicaciones ni eventos semánticos de prueba. Los eventos legítimos de enrollment/login sí permanecen. Ante fallo se detiene, conserva resultados parciales y no declara cierre.

## Diagnóstico explícito de tres identidades

El modo diagnostic-three usa un lector Telchi, un administrador Telchi distinto y una identidad consentida de otra organización. No selecciona cuentas ni modifica roles. El gate completo sigue siendo el default y exige cuatro sujetos distintos.

La excepción del [runbook previo](../business_semantics_security_unblock_v1/authenticated_validation/HUMAN_ACTION_REQUIRED.md) permite que el admin sea uno de los dos usuarios Telchi. Aquí sólo se aplica al diagnóstico: nunca sustituye al segundo lector no administrador del gate completo.

Según la evidencia de sólo lectura aportada por el operador, telchi_dev pertenece a telchi; team360_admin_dev a team360_platform y team360_public_site a team360_live. Estos últimos son candidatos, no identidades elegidas ni consentimiento concedido.

Desde Ubuntu, preparar un archivo nuevo privado y completar los tres sujetos autorizados manualmente. No pegar identificadores, passwords ni tokens en chat. El preflight no autentica: si faltan credenciales habilitadas, detenerse sin enrollment.

```bash
cd /media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/SrvRestAstroLS_v1/backend
export TEAM360_ENV=dev
AUTH_DIR=/media/issajar/DEVELOP/Projects/iMotorSoft/ai/private/telchi/console-auth-window-20261014T134648Z
AUTH_CONFIG="$AUTH_DIR/issuer.json"
MANIFEST="$AUTH_DIR/authorized-identities-diagnostic.json"
( set -C; umask 077; cp --no-clobber modules/business_semantics/authorized-identities.diagnostic.example.json "$MANIFEST" )
"${EDITOR:-nano}" "$MANIFEST"
REPORT="../../data/reports/team360/whatsapp-progress-v1/diagnostic-$(date -u +%Y%m%dT%H%M%SZ).json"
uv run --no-sync python -m modules.business_semantics.authenticated_gate \
  --mode diagnostic-three --auth-config "$AUTH_CONFIG" --manifest "$MANIFEST" \
  --output "$REPORT" --prepare-only
```

Sólo después de CEREMONY_READY y con los titulares presentes, ejecutar en la misma terminal:

```bash
uv run --no-sync python -m modules.business_semantics.authenticated_gate \
  --mode diagnostic-three --auth-config "$AUTH_CONFIG" --manifest "$MANIFEST" \
  --output "$REPORT"
```

Resultado exitoso limitado: AUTHENTICATED_GATE=PARTIAL, código de salida 2. FAIL sale 1; sólo el gate completo puede producir PASS y salida 0. No tratar el código 2 como PASS ni ignorarlo con un wrapper. El prepare-only no genera un resultado autenticado.

El diagnóstico conserva sesión activa/organización/workspace, lectura exacta, catálogo común lector/admin, rechazo entre tenants, denegación administrativa del lector, administración con rollback e inmutabilidad. El reporte identifica el modo y missing_coverage explícitamente.

Pendiente incluso con PARTIAL: segundo lector no administrador y equivalencia de catálogo entre dos lectores. El admin no pasa por la rama de denegación de lector. No se certifican HTTP, Console web ni WhatsApp por CLI/DB.

## Preparación del canal de una sola línea

Existe una única línea humana consentida comunicada privadamente por el operador; su número no se copia en este informe ni en ejemplos. Una conversación real no necesita cuatro teléfonos. El canal sigue NOT_TESTED en esta tarea.

Antes de enviar, usar el [preflight de servicios](../../../../lat.md/service-preflight-methodology.md) y el [contrato Evolution existente](../../../../SrvRestAstroLS_v1/backend/modules/messaging/README.md). Verificar en sólo lectura instancia DEV, estado, webhook y binding de workspace/canal.

Identificar por separado número/cuenta de la instancia Evolution y teléfono humano de prueba; no inferir que son el mismo. Verificar vínculo activo teléfono→usuario/workspace y consentimiento sin modificar bindings ni callback. Si faltan o son ambiguos, detener la prueba.

Con autorización específica del operador, éste inicia una consulta desde su teléfono. Correlacionar ID inbound, identidad/contexto Telchi autorizados, conversación/turno Srv05→TelchiAI, consulta a datos autorizados, ID outbound Evolution y delivered/read observable. Un HTTP 200 no demuestra entrega.

Comprobar un único intent/respuesta por inbound y deduplicación. Cualquier replay que pueda generar outbound exige autorización previa; no enviarlo automáticamente. Resguardar evidencia privada y publicar sólo IDs hash y resultados saneados, nunca teléfonos ni payloads personales.

RBAC y rechazo entre organizaciones se prueban por identidades autenticadas independientes; WhatsApp multirremitente y aislamiento multitenant E2E quedan NOT_TESTED hasta contar con más teléfonos reales autorizados. No inventar números ni reasignar la única línea entre tenants.

No se consultó el estado vivo de Evolution, no se envió tráfico ni se iniciaron listeners en este cambio. La preparación es procedural, no una certificación de disponibilidad del canal ni una habilitación productiva.

## Límite y siguiente prueba

El ejecutor está probado con dobles, no con sesiones humanas aún. Su PASS cerraría sólo su alcance CLI/DB/RBAC; no certifica HTTP, puente teléfono→identidad, respuesta de Luna ni transporte WhatsApp real.

Después de la ceremonia: validar bindings/consentimiento de teléfono y transporte real controlado; sólo con seguridad/RBAC acreditados, autorizar la consulta comercial final desde WhatsApp. No se tocaron L&S, interfaz web, producción ni Foundation.

## Validación de la corrección del ejecutor

La corrección del paso 14 sólo se validó con dobles explícitos. No hubo consultas DB vivas, login humano, enrollment, envío WhatsApp ni cambios de identidades, configuración global, Foundation o datos semánticos persistidos.

Desde backend se ejecutó:

```bash
uv run --no-sync pytest -q modules/business_semantics/tests modules/telchi/assistant/tests/test_whatsapp_controlled_transport.py
```

Resultado: 123 PASS; incluye manifiestos inválidos, obligatoriedad de modo explícito, PARTIAL/salida 2, FAIL/salida 1, full PASS/salida 0, rechazo de enrollment diagnóstico, roles/actividad/tenant incorrectos, rollback forzado y limpieza de tokens ante fallo.

Desde raíz: lat check md/index/sections/code-refs/check y git diff --check, salida 0. Advertencias LAT de init/search sin configurar; uv advierte dev-dependencies deprecado. Revisión limitada a los cinco archivos propios; cambios previos preservados.

Host: ocho cores, load descendió de 4.51 a 2.37, ~6.4 GiB disponibles y swap usada estable en 2 MiB. HOST_PREFLIGHT=SAFE; RESOURCE_GUARD=PASS; CONCURRENCY_USED=1 (pytest secuencial); sin browsers ni listeners creados.

UNRELATED_PROCESSES_TERMINATED=0; ENVIRONMENTAL_ABORTS=0; OWN_PROCESSES_LEFT_RUNNING=0. Pendientes: manifiesto privado y consentimiento, credenciales ya habilitadas, ceremonia real, HTTP autenticado y verificación viva del canal. No hay PASS autenticado declarado.

## Validaciones y recursos anteriores

La corrida anterior validó otros alcances; no sustituye la corrección ni la ceremonia pendiente.

Ejecutado desde backend:

```bash
uv run --no-sync pytest -q tests/test_messaging_evolution.py tests/test_messaging_horizontal_runtime.py tests/test_messaging_handlers.py modules/telchi/assistant/tests/test_assistant.py modules/telchi/assistant/tests/test_whatsapp_controlled_transport.py modules/business_semantics/tests tests/test_telchi_assistant_srv05.py
```

Desde raíz: git diff --check y lat check md/index/sections/code-refs/check, todos con salida 0. LAT avisa configuración de init/search ausente; ningún gate falló. Diff propio revisado, cambios previos preservados.

Recursos: HOST_PREFLIGHT=SAFE, RESOURCE_GUARD=PASS, CONCURRENCY_USED=1. Ocho cores, ~6 GiB disponibles, swap estable sin si/so durante observación. Un proceso de pruebas a la vez y embeddings secuenciales. UNRELATED_PROCESSES_TERMINATED=0, ENVIRONMENTAL_ABORTS=0, OWN_PROCESSES_LEFT_RUNNING=0; sin browsers/servidores/workers persistentes creados.
