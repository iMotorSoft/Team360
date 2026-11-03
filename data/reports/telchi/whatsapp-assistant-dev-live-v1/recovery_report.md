# Telchi WhatsApp DEV — Recovery V1

Recuperación operacional del 11/10/2026 sobre infraestructura existente. Evolution local recuperado; callback DEV comprobado temporalmente. Primera conversación Telchi todavía BLOCKED por destino DDL, identidad y autorización empresarial.

## 1. Rama, objetivo y límites

Se trabajó en `feature/console-backend-core`, HEAD `09d2ec7`, preservando el worktree preexistente. Objetivo: recuperar DEV, no instalar otra integración ni cambiar conversación/modelos.

Contexto: TELCHI / VENTAS + USUARIOS_ROLES_Y_PERMISOS / DEVELOPMENT operacional de capacidad DEV existente / DATA_LAKE / REPORT + CONVERSATIONAL_CONTEXT. Sin promoción productiva.

Scope escrito: archivos `recovery-*`, `recovery_*.py` y este reporte, exclusivamente en este directorio. Sin cambios de runtime, `.env`, launchers, migraciones, prompts, grants, Foundation CURRENT, Srv01, Flow, Diagnosis, frontend ni PROD. Sin commit/push. No se ejecutaron LlmFit, Luna ni nuevas consultas Foundation independientes.

## 2. Evidencia histórica recuperada

La instalación no estaba en `Team360/lab/evolution-api`: el laboratorio real es `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/evolution-api`. Se encontró el contenedor y su persistencia originales.

| Evidencia | Clasificación | Garantía histórica |
| --- | --- | --- |
| Lab `README.md`, `start.sh`, `image.ref`, `data/store` | HISTORICALLY_VALIDATED | v2.3.7 parcheada, Podman rootless, red `evolution-api-net`, PG18 propio, Redis OFF |
| Lab `data/statusfix-real-evidence.json` | HISTORICALLY_VALIDATED | Inbound real y respuesta al remitente autorizado; SENT/DELIVERED/READ persistidos |
| Lab `data/port-remap-evidence.json` | HISTORICALLY_VALIDATED | 20 pares reales después del remapeo a 18180; misma instancia y challenge público |
| [Messaging canónico](../../../../SrvRestAstroLS_v1/backend/modules/messaging/README.md) y `data/reports/messaging/evolution-adapter-v1/20261006-165557/verified/` | HISTORICALLY_VALIDATED | 20 PONG, delivery/read, deduplicación y recovery; sin LLM |
| [Cierre del 08/10](../../messaging/telchi-datalake-pre-sql-profile-v1/report.md) | HISTORICALLY_VALIDATED | `hola` WhatsApp real con SQL fijo Foundation; no handler conversacional actual |
| [Cleanup Meta del 08/10](../../messaging/telchi-datalake-pre-sql-profile-v1/human-20261008T172521188606/subscription-cleanup.json) | HISTORICALLY_VALIDATED | Restauración anterior fallida; eliminación temporal HTTP 200 y readback sin suscripción |

La integración validada era **Meta Cloud API → Evolution WHATSAPP-BUSINESS → Messaging**, no Baileys ni Meta directa desde el asistente. La app histórica era `Team360 Messaging Hub`; hashes actuales de app/WABA están en las sondas, sin secretos ni teléfonos completos.

## 3. Evolution actual y recuperación

[Antes](recovery-before.json), [después](recovery-after.json), [final](recovery-final.json) y [operaciones](recovery-operations.json) prueban recuperación del mismo contenedor y conservación de datos.

- Contenedor existente `evolution-api`: inicialmente exited(1), terminado el 08/10 a las 17:27:07 UTC; `restart=no`, sin autostart.
- Imagen local fijada por digest `sha256:ffe2a98adcfd2575e71f90041747b023cf1bc22696684a7589fdd7155b38be00`; no rebuild/pull/recreate.
- Bind persistido y actual: `127.0.0.1:18180 → 8080/tcp`. La referencia a host 8080 era histórica; el endpoint de Srv05 ya apuntaba correctamente a 18180.
- Base/rol/schema `evolution_api`, PostgreSQL 18.4, 57 migraciones terminadas, cero incompletas; rol no superuser/create DB/create role. Redis false y cache local true.
- Instancia única `team360-meta-dev`, `WHATSAPP-BUSINESS`, mismo UUID histórico comprobado por hash, estado API actual `open`.
- Conteos antes/final: **116 mensajes y 159 actualizaciones**, sin cambios. Bind mount original `data/store` conservado; sin borrado de sesiones/volúmenes.
- Estado final **CURRENTLY_RUNNING**, Podman healthy; GET raíz HTTP 200 versión 2.3.7 y GET connectionState HTTP 200/open.
- Webhook local Team360 **CURRENTLY_CONFIGURED pero deshabilitado**: enabled=false, events=[], sin header privado configurado. No se activó un responder legacy para conseguir un PASS.

Se ejecutó primero el helper existente `start.sh`. Rechazó el contenedor detenido porque `podman port` devolvió vacío, aunque `HostConfig.PortBindings` conservaba el mapping correcto. Tras verificar ID, estado y mapping, se ejecutó únicamente **`podman start evolution-api`**. No se modificó el helper ni se recreó el contenedor.

Evolution existente queda deliberadamente **running**, como servicio DEV recuperado solicitado, no como servidor temporal de test. No hay túnel ni backend temporal pendiente.

## 4. Causa real de inaccesibilidad

Los logs del contenedor contienen Prisma **P1001: Can't reach database server at host.containers.internal:5432**. El endpoint estaba ausente porque el contenedor quedó detenido, no por una URL incorrecta ni por falta de instalación.

El cierre del 08/10 también documenta ese P1001. Actualmente `imotorsoft-postgres` está running; las sondas read-only acceden a `evolution_api` y el arranque reestableció conectividad desde Podman. No fue necesario reiniciar PostgreSQL ni modificar red/credenciales.

No se determina retrospectivamente quién apagó PG ni la causa de su indisponibilidad entonces: **NOT_VERIFIED**. Con `restart=no`, recuperar PG por sí solo no arrancaba Evolution. El fallo del guard de `start.sh` para un contenedor detenido es un impedimento operacional adicional observado, no la causa original del P1001.

## 5. Meta, WABA y credenciales

Los GET actuales confirman la misma app histórica y activos Team360; no se usaron activos de otros proyectos ni se generaron tokens nuevos.

- App `Team360 Messaging Hub`: HTTP 200, ID coincide con configuración/historia.
- WABA subscribed_apps: HTTP 200, una entrada, la app configurada presente y sin paginación.
- Número: HTTP 200, `VERIFIED`, `CLOUD_API`; sin registro nuevo, PIN nuevo ni compra de número.
- debug_token: HTTP 200, `is_valid=true`, app correcta; expires_at=0 y data_access_expires_at=0, scopes WhatsApp management/messaging/manage_events. Esto no garantiza vigencia futura ni entrega.
- App subscriptions al inicio y cierre: HTTP 200, cero entradas. La ausencia concuerda con la eliminación documentada del 08/10; no se atribuye a expiración de token.
- Verify token del contenedor coincide con el actual de Team360. No se imprimieron sus valores.

[Prueba actual de callback](recovery-callback.json): POST de suscripción DEV HTTP 200, `success=true`; GET posterior confirma object WhatsApp, URL exacta del túnel propio, active=true y único field `messages`. Esto demuestra permisos actuales para reconfigurar el callback DEV: **no hace falta intervención humana en Meta para esta operación probada**.

No hubo evento real de WhatsApp durante esa ventana. Antes de cerrar, se verificó ownership exacto de URL/fields, DELETE temporal HTTP 200 y GET final vacío. La app no quedó apuntando a un túnel muerto ni a un handler sin autorización.

## 6. Cloudflare y seguridad del callback

No había proceso cloudflared ni archivos PID/URL activos del helper. `SERVER_URL` persistido apunta a un Quick Tunnel histórico, no a una URL acreditada hoy.

Se reutilizó el binario y procedimiento de Quick Tunnel existentes, creando **un solo túnel temporal** hacia `http://127.0.0.1:18180`. No expuso PG ni Srv05. Se reutilizó la sanitización histórica del log antes de escritura para evitar verify tokens en query strings.

- Challenge local: HTTP 200 y respuesta exacta.
- Challenge público: primer intento HTTP 530 durante propagación; segundo HTTP 200 y respuesta exacta.
- Meta aceptó la suscripción y la devolvió activa; no fue solo un health 200.
- Túnel propio reaped y lector cerrado; suscripción restaurada al estado inicial vacío.
- `SERVER_URL` no coincide con el túnel temporal; no se editó `.env` ni se recreó el contenedor para una prueba transitoria. No se declara circuito permanente sincronizado.

**CURRENTLY_BROKEN para ingress permanente**, con recuperación temporal comprobada. Para la sesión Telchi final se debe levantar una única URL vigente, sincronizar configuración mediante el procedimiento existente si corresponde y registrar el callback DEV. No reutilizar el hostname histórico.

Limitación histórica preservada: Evolution v2.3.7 no valida HMAC en `/webhook/meta`. El challenge autentica configuración, no cada POST. Exposición fue DEV acotada y ya cerrada; no autoriza PROD ni permite declarar seguridad productiva PASS.

## 7. PG18 DEV y migración 027

PG18 responde, pero su disponibilidad y los documentos de uso local no acreditan exclusividad DEV ni autorización de DDL sobre la base efectiva.

- Servidor existente `imotorsoft-postgres`, versión 18.4, puerto 5432; no se instaló otra instancia.
- Destino efectivo del entorno para un Srv05 DEV futuro: **localhost:5432/team360**, schema public. No hay Srv05 Team360 vivo que permita afirmar conexión efectiva de proceso.
- Inventario real: no existe `team360_dev`. El [setup vivo histórico](../../../../SrvRestAstroLS_v1/docs/postgresql_live_team360_setup.md) documenta que fue eliminada y se eligió `team360`; el setup antiguo que la proponía no demuestra disponibilidad actual.
- `team360_telchi_ducklake` es catálogo analítico separado, **no sustituto autorizado de la DB core** para Messaging/RBAC.
- Snapshot pg_stat_activity: no otros clientes Team360 en ese instante. No demuestra ausencia de uso productivo anterior/futuro.
- No se encontró rol core DEV dedicado ni ledger de migraciones SQL en las tablas efectivas. `whatsapp_number_migration_history` no es ese ledger. Evolution sí tiene ledger Prisma propio, ajeno a 027.
- `messaging_phone_bindings` ausente. **027 NO aplicada**. Se revisaron el SQL y su rollback comentado; ninguno se ejecutó. No se repitió DDL descartable.
- 027 requiere binding verificado, actor, scope inmutable y auditoría `core_events`; rollback DROP no recupera datos. No se acreditó respaldo restaurable ni ventana de reversión del destino core.

DDL bloqueado únicamente para este destino no acreditado. Consultas de inspección con default_transaction_read_only=on y statement_timeout=5000; cero escrituras Team360. No se asume que migraciones 026/027 probadas previamente autorizan tocar esta base.

## 8. Identidad y permisos

[Inspección de fixture](recovery-runtime-fixtures.json): cuatro usuarios existentes activos, sin referencia al remitente allowlisted ni claves de teléfono/consentimiento/verificación en sus metadatos. No se encontró fixture empresarial verificable.

No existen bindings telefónicos porque falta la tabla. La allowlist histórica acredita destinatario consentido para aquellos pings, no binding a core_users ni permiso comercial actual. Cero workspaces cuyo slug/display_name identifique Telchi; no prueba ausencia de un equivalente con otro nombre, que debe designar el owner.

Se enumeraron códigos de permisos existentes, no permisos efectivos de un usuario arbitrario. No hay código Telchi/sales/business explícito; los generales `knowledge.view`, `dashboard.view`, etc. **no se reinterpretan automáticamente** como lectura comercial global.

Se conserva el recorrido PhoneIdentityRepository → PermissionConsoleRepository → BusinessAuthorization. Sin usuarios ficticios, impersonación, auto-enrollment ni grants para conseguir PASS.

## 9. Canal horizontal Telchi

El canal existente `evolution-meta-dev` permanece legacy, sin mutación de configuración o fallback usado durante esta ejecución.

Binding real: environment/module/tenant_id/receiver_context NULL; workspace configurado `team360_public_site`. Entorno privado development, Evolution Srv05 flag ausente/OFF, dispatch mode ausente/legacy, lifecycle PostgreSQL ausente.

Existe `create_telchi_app(policy=...)` sobre la inyección horizontal de Srv05. No se activó sin tenant/workspace/permiso/scope aprobados ni schema de identidad. No se puso BusinessPolicy en true por conveniencia. No se modificaron Flow, Diagnosis ni compatibilidad legacy.

El listener preexistente 7008 pertenece a **TebaAI**, cwd y entrypoint comprobados read-only; no era Srv05 Team360 y se preservó. La indisponibilidad Team360 no exige reiniciarlo.

## 10. WhatsApp real, Foundation y continuidad

No hubo teléfono empresarial autorizado listo ni circuito horizontal seguro. Todos los casos están NOT_EXECUTED; no se sustituyeron por simulaciones o nuevas sondas Luna/Foundation.

| Test | Estado | Evidencia actual pendiente |
| --- | --- | --- |
| 1 Recepción/respuesta | BLOCKED | Inbound real, identidad/permisos, handler, outbound, recepción visible |
| 2 Foundation CURRENT | BLOCKED | Respuesta por teléfono y comparación con CURRENT/pin reales |
| 3 Continuidad | BLOCKED | Segundo turno y recuperación durable PG, no memoria del proceso |
| 4 Facturación general | BLOCKED | Rechazo honesto por capability no aprobada observado por WhatsApp |
| 5 Análisis causal futuro | BLOCKED | Respuesta futura sin diagnóstico/APD ficticio observada por WhatsApp |
| 6 Seguridad | BLOCKED | Segundo teléfono consentido sin acceso; rechazo externo real |

El `hola` SQL del 08/10 y [Foundation del preflight anterior](foundation-preflight.json) son HISTORICALLY_VALIDATED, no resultados de esta recuperación. Ese preflight consignó CURRENT `foundation_afd08d9eca6a725be53cdc3f9d5709c9`, snapshot 1408 y hash documental; no se asume que siguen CURRENT sin revalidación al test real.

Cantidades documentales no son facturación monetaria. Persistencia del asistente, correlación inbound/outbound, aceptación proveedor, delivery y recepción visible actuales: **NOT_OBSERVED**. Conteos Evolution sin cambio prueban conservación, no continuidad conversacional Telchi.

## 11. Latencias

No existe muestra WhatsApp E2E ni tiempos medidos de sus etapas durante esta ventana. No se extrapolan benchmarks históricos ni se inventan ceros.

Webhook real, resolución de identidad, permisos, Luna, State Engine, Foundation, preparación, envío Evolution, confirmación proveedor y recepción visible: **NOT_MEASURED**. Los timestamps de las sondas describen la inspección, no latencia conversacional.

## 12. Acciones humanas estrictamente necesarias

La recuperación local y la operación Meta de callback ya no dependen de descubrir otra plataforma ni de obtener nuevos tokens; faltan decisiones de identidad y destino empresarial.

1. **Destino DDL:** acreditar explícitamente si localhost:5432/team360 es exclusivamente DEV y no sirve PROD. Autorizar 027 en ese destino, indicar respaldo restaurable y ventana/procedimiento de reversión. Si no es exclusivo, designar una base core DEV existente válida; no usar DuckLake ni instalar otro PG por defecto.
2. **Fixture:** designar usuario core_users existente, workspace Telchi autorizado, tenant, teléfono consentido y actor administrativo; aportar referencia opaca de verificación de posesión/identidad y aprobación del binding. Mantener datos personales en configuración privada. Designar segundo teléfono consentido para test negativo.
3. **Política/canal:** seleccionar permiso empresarial existente aplicable y acreditar alcance completo del workspace y módulo Telchi habilitado. Aprobar conversión DEV del canal existente con environment=dev, module=telchi, tenant/workspace/receiver_context explícitos. Si no hay permiso aplicable, conservar DENIED; no ampliarlo automáticamente.
4. **Tráfico humano:** con esos insumos y Srv05 horizontal disponible, enviar mensajes reales y confirmar recepción visible. Ninguna API de envío sustituye al remitente humano solicitado.

Pasos operacionales posteriores ejecutables por el agente: aplicar 027 solo tras cumplir condiciones, crear binding mediante procedimiento aprobado, componer Telchi en registro existente, configurar solo proceso Srv05 DEV con Evolution ON/horizontal_v1/PG, activar webhook local autenticado y único callback DEV vigente, ejecutar tests 1–6. No hace falta otra app/WABA/número/Evolution/modelo.

## 13. Validaciones, recursos e impacto

Los checks locales son regresión de composición y aislamiento Meta; no acreditan WhatsApp real. Los gates documentales se guardan separados de la evidencia de transporte.

Comandos desde backend:

```bash
.venv/bin/python ../../data/reports/telchi/whatsapp-assistant-dev-live-v1/recovery_probe.py recovery-before.json
.venv/bin/python ../../data/reports/telchi/whatsapp-assistant-dev-live-v1/recovery_probe.py recovery-after.json
.venv/bin/python ../../data/reports/telchi/whatsapp-assistant-dev-live-v1/recovery_callback.py
.venv/bin/python ../../data/reports/telchi/whatsapp-assistant-dev-live-v1/recovery_probe.py recovery-final.json
env -u TEAM360_MESSAGING_ISOLATED_TEST_DSN -u TEAM360_MESSAGING_POSTGRES_TEST -u TEAM360_MESSAGING_TELCHI_SQL_TEST OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 uv run --no-sync pytest tests/test_messaging_meta_config.py tests/test_telchi_assistant_srv05.py -q --tb=short
```

[Regresión](recovery-regression.txt): **8 PASS**, 1.62 s; warning existente del fixture Diagnosis in-memory y deprecación uv. Sin benchmark ni LLM. La primera sonda falló al pasar el parámetro Prisma `schema` a libpq; se corrigió únicamente el script de evidencia para filtrarlo, luego lectura PG correcta. No es defecto runtime.

Gates ejecutados: `lat check md`, `lat check index`, `lat check sections`, `lat check code-refs`, `lat check`, `git diff --check`: **todos exit 0**; resultados en `recovery-validation.json` y `recovery-lat-*.txt`. Revisión del diff final y scripts de evidencia sin secretos, separada de los cambios preexistentes.

Host BUSY_BUT_SAFE: ocho cores, load 2.42/2.30/2.32, MemAvailable 5348 MB, swap 3799 MB; dos intervalos vmstat sin swap-in/out, idle 78–82%. Trabajo secuencial, una sonda/conexión a la vez, un único túnel temporal, OMP/BLAS 2 para ocho tests; sin browsers/suites amplias/scans analíticos.

Impacto transversal acotado: arranque del contenedor DEV preexistente y una suscripción Meta temporal seguida de su retirada verificada. PG compartido no se reinició; Team360 no recibió DDL/DML. SERVICIO_EXISTENTE_RECUPERADO_RUNNING=1; OWN_TEMPORARY_PROCESSES_LEFT_RUNNING=0; UNRELATED_PROCESSES_TERMINATED=0; ENVIRONMENTAL_ABORTS=0. No se alteró LAT/GLOBAL para conseguir checks verdes.

## 14. Estado final

PASS local de Evolution se limita a disponibilidad y conservación comprobadas ahora; no implica ingreso Meta ni conversación Telchi. PARTIAL callback significa validación temporal cerrada, no canal live permanente.

```text
EVOLUTION_DEV_RECOVERY=PASS
META_DEV_WEBHOOK=PARTIAL
CLOUDFLARE_DEV_CALLBACK=PARTIAL
PG18_DEV_IDENTITY=BLOCKED
TELCHI_HORIZONTAL_CHANNEL=BLOCKED
TELCHI_FIRST_REAL_WHATSAPP_MESSAGE=BLOCKED
TELCHI_DEV_END_TO_END=BLOCKED
```

Próximo paso: resolver las tres decisiones administrativas de destino/fixture/política y abrir una sesión horizontal Telchi real. Evolution queda recuperado; no se requiere reinstalación. No se declara conversación ni entrega que no ocurrieron.
