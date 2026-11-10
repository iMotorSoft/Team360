# Evolution / Meta — arranque DEV reproducible

Secuencia operativa PostgreSQL → LiteLLM → Evolution → Cloudflare → Meta → Team360 WhatsApp. Este runbook no habilita producción ni convierte la disponibilidad de transporte en gates funcionales aprobados.

## Operación habitual de un comando

El wrapper DEV reutiliza el lifecycle WhatsApp y los scripts del laboratorio; no instala servicios ni modifica Meta. Desde la raíz Team360, con las credenciales Meta habituales exportadas:

```bash
./whatsapp-dev.sh status
./whatsapp-dev.sh up
# Solo si cambió PUBLIC_URL, tras autorización explícita del responsable:
./meta-webhook-update.sh https://NUEVA-URL.trycloudflare.com --apply
./whatsapp-dev.sh up
# Conversación manual desde el teléfono habilitado; nunca la envía el launcher.
./whatsapp-dev.sh down
```

`up` comprueba PostgreSQL, identidad/binding, LiteLLM y manifiesto vigente antes de mutar servicios. Reutiliza Evolution adoptado y Cloudflare READY; solo inicia los ausentes mediante `start.sh` y `cloudflare-start.sh`. No crea contenedores ni ejecuta migraciones. PostgreSQL/LiteLLM ausentes bloquean: no los reinicia ni los inicia implícitamente.

La URL se lee de `../../lab/evolution-api/data/cloudflared.url`; el updater existente inspecciona app/WABA y challenges por GET. Callback distinto bloquea y muestra `AUTHORIZED_META_UPDATE_COMMAND`; `up` jamás ejecuta `--apply`. Credenciales ausentes o lectura no acreditada también bloquean, sin afirmar sincronización.

El controlador usa el JSON privado `PRIVATE_ROOT/whatsapp-dev-control.json` existente (modo `0600`), no sourcea shells ni crea credenciales. Conserva host específico, instancia, aprobación y configuración V1 canónicos. Operaciones simultáneas quedan excluidas por lock; runtime ya READY no se duplica.

`status` muestra POSTGRES, LITELLM, EVOLUTION, CLOUDFLARE, PUBLIC_URL, META_CALLBACK, SIX_GATES, WHATSAPP_RUNTIME, READY_FOR_DIALOGUE y BLOCKER. `LITELLM=READY` acredita liveliness; modelo/proveedor/sin fallback corresponden al gate real vigente, sin llamada al modelo durante el arranque.

`READY_FOR_DIALOGUE=YES` exige readiness del listener con nonce, procesos propios, gates, binding y callback actuales. No acredita recepción, respuesta de Luna, entrega ni lectura de mensajes. `down` señaliza solamente el launcher WhatsApp propio, verifica su cierre/restauración y deja PostgreSQL, LiteLLM, Evolution y Cloudflare intactos. No hay cierres por duración o inactividad.

Si SIX_GATES está DEGRADED, corregir/reacreditar por el procedimiento canónico; no se lanzan baterías ni se reemplazan hashes automáticamente. Los pasos detallados siguientes son diagnóstico/preparación inicial, no trabajo obligatorio en cada uso.

## Autoridades y responsables

El operador del proyecto coordina los servicios compartidos; el owner Messaging registra Meta DEV y el owner del piloto decide la activación WhatsApp. No se agregan aprobaciones administrativas.

| Paso | Responsable funcional | Autoridad y condición de avance |
| --- | --- | --- |
| PostgreSQL 18.4 | Operador de infraestructura | [POSTGRESQL18](POSTGRESQL18.md): red, autenticación y catálogo read-only; no conceder permisos por inferencia |
| LiteLLM | Operador del proxy / owner del modelo | [README LiteLLM](../../../../../../../../lab/litellm-server/README.md) y [preflight](../../../../../../lat.md/service-preflight-methodology.md): alias/auth/provider reales, sin fallback |
| Evolution | Owner Messaging | [README Messaging](../../README.md) y [laboratorio](../../../../../../../../lab/evolution-api/README.md): instancia `team360-meta-dev`, puerto 18180 |
| Cloudflare / Meta | Owner Messaging | Scripts existentes del laboratorio y updater DEV de este documento; ningún activo Vertice360 |
| Team360 WhatsApp | Owner del piloto Telchi | [WHATSAPP_DEV](../../../telchi/assistant/WHATSAPP_DEV.md): seis gates aplicables, preflight y arranque manual separados |

El alcance Telchi referenciado es integración conversacional DEV, sin cambios funcionales en dominios ni promoción de datos. [CONTEXT](../../../telchi/CONTEXT.md) conserva roots, etapas y políticas; este documento no sustituye sus autoridades.

## Preparación de la terminal

Usar una shell con las credenciales administradas ya exportadas. No copiar secretos a argumentos, scripts, reportes o archivos nuevos; no ejecutar `set -x`, `env`, `podman inspect` sin filtrar ni volcar `.bashrc`.

Desde la raíz Team360:

```bash
cd /media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360
TEAM360_ROOT="$PWD"
EVOLUTION_LAB="$(realpath ../../lab/evolution-api)"
LITELLM_LAB="$(realpath ../../lab/litellm-server)"
uptime
free -m
```

El updater requiere Python 3 estándar, HTTPS confiable y las variables existentes `META_TEAM360_APP_ID`, `META_TEAM360_APP_SECRET`, `META_TEAM360_WABA_ID`, `META_TEAM360_PHONE_NUMBER_ID`, `META_TEAM360_WABA_TOKEN`, `META_TEAM360_VERIFY_TOKEN`, `META_TEAM360_GRAPH_VERSION`.

No carga archivos privados ni ejecuta `.bashrc`: hereda el entorno habitual. Usa exclusivamente `META_TEAM360_*`; `TEAM360_ENV`, si está presente, debe ser `dev` o `development`. Ausencia de una credencial bloquea sin fallback ni rotación.

## 1. PostgreSQL

Primero consultar el contenedor compartido y aplicar el preflight read-only del [runbook PostgreSQL](POSTGRESQL18.md). No duplicar aquí SQL, privilegios o configuración de conexión.

```bash
podman container inspect --format '{{.State.Status}}' imotorsoft-postgres
```

Si está detenido, únicamente el operador en su ventana de arranque puede ejecutar `podman start imotorsoft-postgres` y repetir el preflight. Si está activo, no reiniciar. Errores de autenticación/catálogo se diagnostican con el runbook, no con grants ni migraciones improvisadas.

## 2. LiteLLM

Comprobar el proxy existente antes de iniciar otro. El health no acredita modelo, crédito o ausencia de fallback; esas garantías siguen en el preflight canónico y los gates del piloto.

```bash
curl --fail --silent --show-error --max-time 10 \
  http://127.0.0.1:4000/health/liveliness >/dev/null
```

Si no existe listener y corresponde arrancarlo, usar otra terminal con el entorno privado habitual:

```bash
cd /media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/litellm-server
./scripts/run.sh
```

No lanzar si el puerto ya pertenece a otro proceso, instalar dependencias o cambiar aliases para salvar un fallo. Antes del piloto, el owner valida el alias efectivo y proveedor real según [WHATSAPP_DEV](../../../telchi/assistant/WHATSAPP_DEV.md); este updater no llama al modelo.

## 3. Evolution

Reutilizar la instalación acreditada; no crear otro contenedor, base, Redis o runtime Team360. Estos comandos de arranque son para una ventana futura, no un preflight que deba iniciar servicios.

```bash
cd "$EVOLUTION_LAB"
./status.sh
# Solo si está detenido y el operador autorizó el arranque:
./start.sh
./status.sh
curl --fail --silent --show-error --max-time 10 http://127.0.0.1:18180/ >/dev/null
```

`start.sh` reutiliza el contenedor existente y no reinicia uno activo. Si falta, su instalación puede ejecutar migraciones: detenerse y seguir la autoridad del laboratorio, no tratarlo como una reparación automática.

## 4. Cloudflare

El túnel existente solo expone Evolution en 18180. Consultar primero su identidad/estado; no lanzar un segundo Quick Tunnel ni detener procesos por nombre.

```bash
cd "$EVOLUTION_LAB"
./cloudflare-status.sh
# Solo si no hay túnel activo y corresponde arrancarlo:
./cloudflare-start.sh
./cloudflare-status.sh
```

`data/cloudflared.url` en el laboratorio es la fuente de la URL vigente. El updater compara el argumento con ese archivo y rechaza divergencias; no modifica el archivo ni administra el túnel.

El laboratorio documenta `SERVER_URL` para configuración completa y URLs generadas por Evolution. El updater no lo cambia ni recrea Evolution. Para recibir Meta en `/webhook/meta`, exige challenge local y público con el token existente; no presupone que el hostname de `SERVER_URL` pruebe ingress.

Si otra función requiere sincronizar `SERVER_URL`, seguir la ventana explícita del laboratorio. No reiniciar Evolution por cambiar el túnel cuando el callback requerido responde correctamente; no afirmar que este updater sincroniza toda configuración Evolution.

## 5. Registrar el nuevo callback Meta

La integración acreditada usa la suscripción de aplicación, no un override WABA. El script inspecciona ambas superficies antes de decidir; un override presente bloquea y nunca se reemplaza automáticamente.

Desde la raíz Team360, inspección sin escrituras:

```bash
cd "$TEAM360_ROOT"
./meta-webhook-update.sh "$(<"$EVOLUTION_LAB/data/cloudflared.url")" --dry-run
```

Tras revisar el dry-run, **un único comando explícito** registra la URL vigente y verifica el resultado. No ejecutarlo durante tareas de preparación sin autorización para escribir Meta:

```bash
./meta-webhook-update.sh "$(<../../lab/evolution-api/data/cloudflared.url)" --apply
```

También admite URL directa: `./meta-webhook-update.sh https://NUEVA-URL.trycloudflare.com --apply`. Sin modo se comporta como `--dry-run`; ambos modos juntos se rechazan. Código de salida 0 indica éxito de su alcance; 2 indica bloqueo/error y no autoriza activar WhatsApp.

## Contrato Meta y límites de verificación

Se reutiliza el procedimiento anterior de [pre_sql_profile_session.py](../../pre_sql_profile_session.py), separando el cambio de callback de cualquier sesión, envío o restauración automática. No ejecutar esa sonda para actualizar Meta.

Referencias oficiales: [Application subscriptions](https://developers.facebook.com/docs/graph-api/reference/application/subscriptions/) y [WhatsApp webhooks](https://developers.facebook.com/docs/whatsapp/cloud-api/guides/set-up-webhooks/). Se usa la versión explícita `META_TEAM360_GRAPH_VERSION`, sin fallback de versión.

1. `GET /{APP_ID}/subscriptions`, con app access token compuesto en memoria desde app ID y App Secret. El token WABA no sustituye este permiso; puede devolver HTTP 400 aunque WABA sea legible.
2. `GET /{WABA_ID}/subscribed_apps`, con el token WABA existente, acredita que la app Team360 está suscrita y que no tiene `override_callback_uri`.
3. HTTP exitoso del origen público y challenges `GET /webhook/meta` local/público, con `hub.mode=subscribe`, verify token privado y nonce aleatorio. Exige respuesta idéntica, no solo HTTP 200; no es una verificación ejecutada por Meta.
4. Solo con `--apply` y callback distinto: `POST /{APP_ID}/subscriptions`, `object=whatsapp_business_account`, `callback_url=<origen>/webhook/meta`, `verify_token=<existente>`, `fields=messages`. Meta valida el callback durante su operación; el script exige `success=true`.
5. Después del POST: nuevos GET de ambas superficies, callback exacto, `active=true`, campo `messages`, app suscrita al WABA y sin override; repite challenge público. Si ya coincidía, no escribe ni reejecuta la validación de Meta.

El dry-run es exclusivamente GET: `META_VERIFICATION=NOT_EXECUTED`. Un apply aceptado y leído acredita registro activo aceptado por Meta, no prueba de entrega de eventos, inbound real, estados, suscripción nueva del WABA ni conversación WhatsApp.

Las identidades acreditadas están fijadas en el código: app `1595188049069929`, WABA `2641368569628887`, phone ID `1376913155505594`. Callback anterior y nuevo deben ser Quick Tunnel DEV y terminar en `/webhook/meta`; cualquier activo, entorno, campo o callback no esperado bloquea.

No crea suscripciones ausentes, no activa una inactiva, no borra campos, no modifica otros objetos de la app, no escribe `/subscribed_apps`, no registra teléfonos ni rota secretos. Rechaza inventarios paginados/incompletos y detecta cambios entre inventario y escritura; Graph no ofrece aquí un CAS transaccional.

Las peticiones son acotadas, sin redirects, proxies de entorno ni reintentos automáticos; errores no imprimen tokens, verify query ni cuerpos del proveedor. El verify token necesariamente viaja en el GET del protocolo: no volcar logs de Cloudflare/Evolution, que podrían contener esa URL.

## 6. Team360 WhatsApp

Meta actualizado solo desbloquea la dependencia de transporte. El estado vigente de los gates se consulta con `./whatsapp-dev.sh status`; no se actualizan hashes o resultados para forzar un arranque.

El owner usa el [preflight sin efectos externos](../../../telchi/assistant/WHATSAPP_DEV.md#preflight-sin-efectos-externos), con su aprobación privada existente:

```bash
cd "$TEAM360_ROOT/SrvRestAstroLS_v1/backend"
uv run python -m modules.telchi.assistant.whatsapp_dev preflight \
  --approval "$TELCHI_APPROVAL"
```

Solo con `PREFLIGHT_PASS`, gates válidos y decisión explícita del owner, seguir [inicio manual](../../../telchi/assistant/WHATSAPP_DEV.md#inicio-manual-y-única-pregunta). Allí viven el comando canónico, bind específico, output privado, parada y correlación E2E; no duplicarlos ni activar un segundo backend aquí.

## Recuperación sin investigación repetida

Ante un bloqueo conservar servicios y estado, resolver únicamente la causa indicada y repetir dry-run. Una actualización de callback nunca es una orden de arrancar el runtime ni enviar mensajes.

| Síntoma | Acción / responsable |
| --- | --- |
| `TUNNEL_STATE_UNAVAILABLE` / `TUNNEL_URL_MISMATCH` | Operador: `cloudflare-status.sh`, confirmar el único túnel y usar `data/cloudflared.url`; no editar el archivo para saltar la guarda |
| `PUBLIC_ROOT` / challenge falla | Messaging: comprobar Evolution local, túnel y verify token administrado; no rotarlo ni recrear servicios automáticamente |
| `MISSING_CREDENTIAL`, HTTP 400/401/403 | Owner credenciales: usar shell con las variables Team360 existentes; confirmar app secret vs token WABA y permisos de la operación; nunca copiar credenciales de otro proyecto |
| `IDENTITY_MISMATCH`, callback no DEV, campos/override inesperados | Detener: el scope dejó de coincidir con DEV acreditado; revisar con owner, sin ampliar allowlist ni modificar producción |
| App/WABA ausente o inactiva | Owner Meta revisa la suscripción oficial por separado; el updater no aprovisiona ni la presume válida |
| POST interrumpido, timeout o read-back fallido | Resultado remoto puede haber cambiado: ejecutar dry-run para leer Meta antes de repetir apply; no rollback automático a una URL antigua posiblemente muerta |
| Callback correcto pero WhatsApp bloqueado | Owner piloto: revisar gates/preflight canónicos; no usar sesiones históricas como atajo |

El rollback de un callback solo procede a otra URL DEV actualmente servida y verificada, con decisión del owner y estado del túnel concordante. No restaurar automáticamente un Quick Tunnel efímero desaparecido, causa de fallos históricos de restauración.

## Validación local del updater

Estas pruebas son offline y no arrancan servicios, leen credenciales reales ni modifican Meta. Los casos apply usan un transporte falso.

```bash
bash -n meta-webhook-update.sh
python3 -m unittest discover \
  -s SrvRestAstroLS_v1/backend/modules/messaging/providers/evolution \
  -p 'test_meta_webhook_update.py' -v
```

El dry-run real requiere únicamente Evolution, Cloudflare y acceso de lectura Meta. No necesita PostgreSQL administrativo, LiteLLM, Milvus, SAP, runtime Team360 ni una llamada al modelo; no es un smoke del pipeline completo.
