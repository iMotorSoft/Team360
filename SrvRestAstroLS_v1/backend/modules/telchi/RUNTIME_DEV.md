# TelchiAI — runtime independiente DEV

TelchiAI tiene un proceso ASGI propio. Esta separación es Development; no despliega producción ni acredita por sí sola consultas empresariales reales.

## Composición y fronteras

El patrón reutiliza la aplicación independiente de Messaging, no el factory central ni un administrador de procesos.

- [dev_app.py](dev_app.py) monta exclusivamente health y las [rutas Telchi](routes.py). Importarlo no abre conexiones ni importa registry, Flow o transportes Messaging.
- Startup crea un pool psycopg async propio de 1–3 conexiones, comprueba PostgreSQL/schema de autorización, CURRENT acreditado y el proveedor Luna existente. Shutdown cierra únicamente ese pool.
- Srv01/Srv05 conservan el factory y lifecycle centrales. El registry ya no importa Telchi; actualizar endpoints Telchi no requiere reiniciar esos servidores.
- El bridge existente usa **OpenAI Responses directo** con modelo y reasoning verificados, sin fallback. No se migra a LiteLLM en esta tarea. El preflight reutiliza ese contrato y hace una llamada mínima real por arranque.
- PostgreSQL 18, LiteLLM, Evolution y Cloudflare siguen siendo servicios externos del responsable. El launcher no los inicia ni detiene; Milvus no es dependencia Telchi.
- Evolution externo no equivale al adapter Messaging: Srv05 lo monta opt-in y valida binding/schema antes del scheduler central. Telchi independiente no carga ese adapter ni duplica sus listeners.
- El resolver Srv05 sigue siendo declarativo; no administra el nuevo proceso. No se añade un orquestador general.

## Inicio y configuración

El puerto loopback 7060 estaba libre al inspeccionar el host. El perfil aislado rechaza puertos ocupados sin intentar recuperarlos; el preflight forma parte del startup ASGI.

Desde la raíz del repositorio, con configuración privada real previamente preparada:

```bash
TEAM360_ENV=dev TEAM360_DEV_PROFILE=telchiai-only \
TEAM360_TELCHI_CONSOLE_ENABLED=1 \
TEAM360_TELCHI_CONSOLE_CONFIG="$PRIVATE_CONFIG_REAL" \
bash SrvRestAstroLS_v1/backend-dev.sh
```

`PRIVATE_CONFIG_REAL` debe contener la ruta efectiva autorizada, no un valor inventado. El JSON owner-only conserva el contrato de [console_http.py](console_http.py): organization, workspace, issuer, public_keys_by_id, policies SourcePolicy y evidence_directory privado fuera del repositorio.

El campo servidor opcional `foundation_publication_id` fija la publicación acreditada esperada; si se omite se conserva la acreditación anterior del bridge. El reader siempre selecciona CURRENT y rechaza diferencias: configurar un ID no selecciona una publicación histórica ni concede permisos.

Las credenciales del proveedor existente y de PostgreSQL se suministran por sus mecanismos privados actuales. No se crean usuarios, grants ni sesiones. Falta de configuración, schema, CURRENT o proveedor aborta el arranque con motivo saneado; nunca se intenta reparar servicios externos.

Para ejecutar solamente el preflight, desde `SrvRestAstroLS_v1/backend` con esas mismas variables:

```bash
uv run --no-sync python -m modules.telchi.dev_app --preflight
```

## HTTP, proxy y conversación

La URL del navegador es estable y del mismo origen; la configuración del backend central en global.js permanece intacta.

- Página `/telchiai`; API `/api/telchiai/session`, `/api/telchiai/ask` y liveness `/api/telchiai/health`.
- Los aliases `/api/telchi/luna/session` y `/api/telchi/luna/ask` permanecen sólo en el proceso independiente para consumidores previos. Srv01/Srv05 no los montan.
- [Proxy Astro DEV](../../../astro/astro.config.dev.mjs): prefijos Telchi antes del `/api` general; destino loopback 7060. `TEAM360_TELCHIAI_PORT` permite elegir otro puerto, usando el mismo valor en los procesos Astro y Telchi.
- El cliente Telchi usa rutas relativas del mismo origen. Alta inicial: actualizar configuración y reiniciar Astro DEV si ya estaba abierto. Cambios posteriores internos de Telchi: reiniciar sólo Telchi; Srv05 y Astro continúan con el mismo routing.
- SSE sin buffering añadido ni timeout de transporte que trunque heartbeats; el investigador conserva su presupuesto analítico. Cerrar el navegador destruye la respuesta upstream y cancela la investigación con cleanup del bridge.
- No hay replay automático de POST ni reanudación durable: una reconexión/reintento es una operación nueva. El cliente conserva los mensajes y muestra errores sin inventar respuestas.
- El contexto entre turnos sigue siendo el del bridge existente, acotado en memoria y separado por identidad/organización/workspace/conversación. **Reiniciar Telchi pierde ese contexto del servidor**; conservarlo entre reinicios requeriría otro alcance de persistencia.
- PASETO de sesión password, sesión activa, permisos efectivos y SourcePolicy se verifican en backend; el navegador no suministra organización, roles ni autoridad.

## Política de duración y cierre empresarial de /telchiai

Decisión explícita del responsable: la duración la decide el usuario, no un temporizador arbitrario. Esta política aplica sólo a TelchiAI y debe preservarse en el cierre empresarial de `/telchiai`.

- El backend permanece funcionando hasta una detención manual autorizada. No detenerlo para facilitar pruebas ni cerrar conversaciones o sesiones con ese propósito.
- Luna no tiene límite de duración ni cierre automático por inactividad. La sesión empresarial permanece abierta hasta el cierre explícito del usuario, una revocación de seguridad o una decisión administrativa.
- No imponer 900 segundos, 15 minutos, 4 horas ni otro límite arbitrario a la experiencia. Las investigaciones largas no tienen un timeout global artificial; los límites técnicos necesarios deben manejarse sin finalizar la sesión empresarial ni la conversación.
- Conservar la expiración criptográfica del PASETO, el rechazo de tokens vencidos, los controles de revocación y la comprobación de permisos. Expiración del token no equivale a una decisión de cierre empresarial.
- Evaluar renovación segura y transparente con los mecanismos existentes, sin exigir un login cada 15 minutos. No ampliar por extensión políticas de Vera, Flow, Evolution, Console u otros módulos o servicios externos.

**Continuidad de autenticación: PENDING, no demostrada.** El [login existente](../console/login_service.py) limita el PASETO a 900 segundos y verifica sesión activa y versión de credencial; no ofrece renovación en ese servicio. El [estado Console](../console/status_actual.md) tampoco declara refresh completado.

El cierre empresarial debe mantener pendiente la implementación y validación de renovación segura hasta demostrar continuidad más allá del vencimiento del token, rechazo de tokens vencidos y respeto del cierre explícito, revocación y permisos vigentes. Esta decisión documental no cambia el runtime ni acredita continuidad ilimitada.

## Validación y límites

Las pruebas de proceso y proxy usan fixtures explícitas: demuestran separación operativa del código, no una consulta Luna ni una sesión empresarial viva.

```bash
cd SrvRestAstroLS_v1/backend
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 uv run --no-sync pytest -q \
  modules/telchi/test_dev_app.py modules/telchi/test_console_http.py \
  modules/telchi/exploratory_sql/test_console_bridge.py \
  tests/test_module_registry.py tests/test_srv05_evolution_isolation.py
```

Desde `SrvRestAstroLS_v1`, `node --test backend/modules/telchi/test_dev_proxy.mjs` verifica el proxy Vite real, HTTP, SSE incremental, desconexión upstream y reconexión con upstream sintético. No inicia un browser ni modifica servicios del responsable.

La evidencia de esta ventana queda en [report.json](../../../../data/reports/telchi/independent-runtime-v1/report.json). El test TCP reinicia exclusivamente procesos propios Telchi y conserva el PID Srv05 controlado, con lifecycle central inerte para no disparar automatizaciones.

CURRENT se confirmó read-only como `foundation_c0b08df908d3485c8668788933826f7c`; la documentación anterior no sustituye esa lectura. No se consultó SAP ni se modificó Data Lake.

Sin configuración HTTP privada y sesión empresarial suministradas a esta ejecución, startup operacional completo, consultas comerciales, continuidad con datos reales y E2E desde la página quedan PENDING. No se declara el criterio integral cerrado con fixtures.

## Cloudflare, Meta y producción

Esta etapa no cambia túneles, callbacks ni dominios productivos. La operación externa requiere una instrucción posterior y URL DEV efectiva.

El endpoint Team360 existente `/webhooks/messaging/evolution/whatsapp` recibe eventos normalizados desde Evolution y exige su token privado; no es `/api/telchiai`. No se infiere que sea el callback Graph de Meta: el destino externo efectivo debe comprobarse en la integración seleccionada antes de configurarlo.
