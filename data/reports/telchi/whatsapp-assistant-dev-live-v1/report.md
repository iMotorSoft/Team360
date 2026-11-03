# Telchi WhatsApp DEV Live V1

Preflight operacional real del 11/10/2026. **END_TO_END=BLOCKED**: no se envió ni recibió un mensaje WhatsApp durante esta ejecución. Las sondas independientes no sustituyen el canal externo.

## 1. Repositorio y alcance

Se preservó el worktree compartido. No hubo cambios de código runtime, configuración privada, infraestructura, Git ni producción.

- Rama: `feature/console-backend-core`; HEAD inicial: `09d2ec7`, concordante con la continuidad recibida.
- Cambios tracked/untracked preexistentes en Flow, Diagnosis, Messaging, Srv05, Telchi, Console, frontend, launchers, migraciones y documentación: preservados, sin adopción ni limpieza.
- Contexto: TELCHI / VENTAS + USUARIOS_ROLES_Y_PERMISOS / INVESTIGATION operacional sobre capacidad DEV existente / DATA_LAKE / REPORT + CONVERSATIONAL_CONTEXT.
- Scope escrito: exclusivamente este directorio de evidencia. No benchmarks LlmFit, refactorizaciones ni ajustes preventivos del motor.
- SAP_ACCESS=0; DDL=0; DB_WRITES=0; WHATSAPP_SENDS=0; SUBSCRIPTION_CHANGES=0; COMMITS=0; PUSH=0.

## 2. Configuración DEV efectiva

Se inspeccionó la shell y se cargó el override privado existente solo en el proceso de preflight. No se modificó ni se imprimieron secretos.

Evidencia actual: [preflight-r2.json](preflight-r2.json), generado por [preflight.py](preflight.py), desde `SrvRestAstroLS_v1/backend` con `.venv/bin/python`.

- Override: `TEAM360_ENV=development`, Messaging DEV habilitado, workspace `team360_public_site`, canal `evolution-meta-dev`, instancia `team360-meta-dev`.
- `TEAM360_SRV05_EVOLUTION_ENABLED` ausente → OFF por default.
- `TEAM360_MESSAGING_DISPATCH_MODE` ausente → legacy por default, no `horizontal_v1`.
- `AUTOMATION_DIAGNOSIS_REPOSITORY` ausente en ese entorno; habilitar Evolution exige lifecycle PostgreSQL explícito.
- Telchi dispone de factory de composición con registro inyectado, pero no de una política empresarial aprobada configurada. El entrypoint Srv05 default no registra Telchi automáticamente.
- No se inició Srv05: hacerlo sin política, esquema y canal acreditados no completa la prueba. No se utilizó el perfil messaging-only, que no certifica Telchi/Srv05.
- Listener preexistente en 7008 preservado; no se asumió su identidad ni ownership, ni se reinició.

## 3. PostgreSQL, migración y reversión

PG18 real respondió mediante conexión administrativa de inspección con transacciones read-only y statement timeout de 5 s. Eso no acredita que la base sea DEV exclusiva.

- Destino efectivo: `localhost:5432/team360`; versión `18.4 (Debian 18.4-1.pgdg13+1)`; `transaction_read_only=on` comprobado.
- No hay atestación de que esta base no reciba tráfico productivo o sea compartida con PROD. **DDL bloqueado**; el nombre de base y `TEAM360_ENV` no prueban aislamiento.
- Los cuatro índices esperados por migración 026 están presentes.
- `messaging_phone_bindings` no existe en el esquema efectivo. Migración 027 no aplicada aquí.
- La búsqueda de tablas con nombre de migración devolvió `whatsapp_number_migration_history`; no se equipara a un ledger de migraciones SQL. No se acreditó un ledger global ni un respaldo DEV utilizable.
- Se revisó 027 completa: transacción explícita, tabla con cinco FK, unique del scope telefónico, checks de verificación/revocación, función y trigger de auditoría a `core_events`, scope inmutable y prohibición de DELETE, REVOKE PUBLIC.
- Rollback comentado: DROP TABLE + DROP FUNCTION en transacción. Es destructivo, no recupera bindings/auditoría; requiere respaldo y autorización independientes. No fue ejecutado.
- No se repitió el DDL descartable anterior ni se asumió su PASS como permiso para esta base.

## 4. Binding, identidad y permisos

El canal DEV existente se resolvió mediante MessagingRepository real, sin aprovisionar otro. Todavía es un canal legacy, no Telchi horizontal.

- `environment`, `module`, `tenant_id`, `receiver_context`: todos NULL en el binding devuelto.
- La allowlist histórica tiene remitente configurado, pero no prueba identidad ni consentimiento vigente y **no se usó como binding**.
- No se proporcionaron usuario Team360 verificado, actor administrativo, referencia de verificación ni destinatarios consentidos positivo/negativo.
- Búsqueda read-only de códigos comerciales con `telchi`, `sales` o `business`: cero coincidencias. No demuestra ausencia de equivalentes con otros nombres; hace falta selección del owner, no crear/asignar un permiso por inferencia.
- PermissionConsoleRepository se conserva como resolver. No se consultaron permisos efectivos de una identidad arbitraria ni se impersonaron usuarios reales.
- Falta acreditar tenant, workspace, módulo habilitado, permiso existente aplicable y scope de workspace completo para esta capability. No se pusieron flags de BusinessPolicy en true sin evidencia.
- No se encontró un enrolamiento automático autorizado en el adapter: PhoneIdentityRepository es read-only; migración preparada no equivale a procedimiento administrativo de verificación aprobado.

## 5. Evolution y Meta actuales

Las consultas actuales separan conectividad Evolution, suscripción WABA y callback de la app. No se extrapoló el problema histórico como estado presente.

- Evolution configurado en `http://127.0.0.1:18180`; GET de connectionState falló con `ConnectError`. Webhook local y estado de instancia: no verificables por esa ruta. No se usó POST ni se cambió configuración.
- `ss -ltnp`: no listener en 18180. `podman ps --format ...`: sin contenedores visibles en el contexto del usuario actual; no demuestra ausencia en otros contextos. No se iniciaron ni reiniciaron contenedores ajenos.
- Meta GET WABA `subscribed_apps`: HTTP 200, una entrada, app Team360 efectivamente suscrita, sin paginación pendiente.
- Meta GET app `subscriptions`, con credencial de app propia: HTTP 200, cero entradas, sin paginación pendiente. No hay suscripción webhook WhatsApp activa en la app consultada.
- Estos GET acreditan lectura/auth de configuración, **no ingress, envío, entrega ni vigencia del callback externo**.
- No se imprimieron IDs Meta, tokens, teléfono ni callback privado. No se restauró una suscripción histórica ni se activó PROD.

## 6. Pruebas WhatsApp A–F

Todos los casos externos están bloqueados antes del primer mensaje. No existe evidencia de conversación real, correlation ID inbound ni recepción visible en esta ventana.

| Caso | Solicitud prevista | Resultado real |
| --- | --- | --- |
| A | Saludo / respuesta Telchi | NOT_EXECUTED: canal, binding y autorización pendientes |
| B | Top 10 productos por cantidad documental, 01/01–15/09/2026, sin filtros | NOT_EXECUTED por teléfono; sonda Foundation independiente disponible |
| C | Seguimiento soportado al turno anterior | NOT_EXECUTED; no se acredita reload PG |
| D | ¿Cuánto facturamos en septiembre? | NOT_EXECUTED por teléfono; no se inventaron importes |
| E | ¿Por qué bajaron las ventas? | NOT_EXECUTED; no se iniciaron trabajos ficticios |
| F | Identidad no autorizada / número desconocido consentido | NOT_EXECUTED: falta segundo destinatario consentido |

Para **cada caso A–F**, correlation ID, identidad, autorización, decisión, commit, capability, publicación, comparación de resultado, outbound y evidencia de recepción son `NOT_OBSERVED`; latencias de etapas `NOT_MEASURED`. Ninguna salida de preflight se atribuye a estos mensajes.

En F no se declara la garantía negativa externa PASS: no hubo tráfico real. Los ceros de actividad de esta ejecución no sustituyen comprobar el rechazo de un evento autorizado para prueba.

## 7. Foundation y Luna independientes

Se ejecutaron solamente sondas mínimas de disponibilidad. Identidad, permiso, persistencia y transporte del runner son explícitamente simulados; no son resultados del teléfono.

Comandos desde backend:

```bash
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 uv run python -m modules.telchi.assistant.tests.live_probe --foundation --output ../../data/reports/telchi/whatsapp-assistant-dev-live-v1/foundation-preflight.json
uv run python -m modules.telchi.assistant.tests.live_probe --luna --preflight --output ../../data/reports/telchi/whatsapp-assistant-dev-live-v1/luna-preflight.json
```

- [Foundation](foundation-preflight.json): CURRENT coherente `foundation_afd08d9eca6a725be53cdc3f9d5709c9`, snapshot 1408, actualización `2026-09-28T18:18:35.264000`.
- Capability existente `telchi.sales_top_items.source_quantity.20260101_20260915.v1`: 10 filas, hash `cba2bd24f0fa00573343eebf3f31d3376a85a63f0a89da05fb82573adf8ea706`, igual al resultado independiente anterior. Sin filas sensibles en el reporte, sin SAP, sin modificar CURRENT.
- Cantidades documentales por producto, unidades no comparables; sin descuento de créditos/filtro de cancelación, no ventas netas ni facturación. Completitud histórica no certificada.
- [Luna](luna-preflight.json): una llamada real OpenAI directa, modelo devuelto `gpt-5.6-luna`, esfuerzo devuelto `medium`, sin fallback. ASK por año ante septiembre; committed=true en store simulado, cero capabilities. No es benchmark ni continuidad PG real.

## 8. Persistencia, deduplicación y recuperación

No se escribieron threads, eventos ni intents operacionales. Las garantías locales no se convierten en evidencia de recovery por WhatsApp.

- Regresión focalizada valida contratos de handler/estado, denegaciones, cache, permisos, composición Srv05 y dispatch horizontal con dobles controlados.
- Deduplicación live, handler único por mensaje, intent outbound único, persistencia real y recuperación: NOT_EXECUTED.
- Brecha conocida, no nueva: commit Telchi y commit del intent horizontal son transacciones distintas; crash puede quedar `execution_uncertain`. No se implementó recuperación ni reenvío ciego.
- No se introdujeron fallos sobre un canal real ni se declaró entrega exactamente una vez.

## 9. Latencias observadas

Se muestran solo mediciones de las sondas independientes. No existe muestra E2E ni callback de entrega en esta ejecución.

| Etapa solicitada | WhatsApp A–F | Sonda independiente |
| --- | --- | --- |
| evolution_ingress_ms | NOT_MEASURED | NOT_MEASURED |
| messaging_dispatch_ms | NOT_MEASURED | NOT_MEASURED |
| identity_resolution_ms | NOT_MEASURED | NOT_MEASURED |
| permission_resolution_ms | NOT_MEASURED | NOT_MEASURED |
| luna_interpretation_ms | NOT_MEASURED | 4568.08 ms |
| state_engine_ms | NOT_MEASURED | 0.45 ms |
| foundation_query_ms | NOT_MEASURED | NOT_MEASURED; capability completa independiente 14118.89 ms |
| response_preparation_ms | NOT_MEASURED | NOT_MEASURED; formatter no ejecutado en ASK |
| evolution_send_ms | NOT_MEASURED | NOT_MEASURED |
| total_processing_ms | NOT_MEASURED | 4568.70 ms, handler ASK con PG/auth simulados |

Aceptación Evolution, entrega por callback y recepción visible: las tres `NOT_OBSERVED`. No se extrapolaron benchmarks previos ni se calculó APD.

## 10. Defectos y clasificación

No se detectaron defectos conversacionales sobre WhatsApp porque no hubo conversación externa. Los bloqueos observados son operacionales, no fallos de Luna/State Engine.

| Categoría | Hallazgo / siguiente depuración |
| --- | --- |
| Interpretación | Sin defecto demostrado; ASK mínimo válido, no evidencia A–F |
| Estado | Persistencia PG no probada; sin defecto nuevo demostrado |
| Capabilities | Consulta documental disponible; monetaria y causal no disponibles por contrato, no nuevas regresiones |
| Datos | CURRENT/hash coherentes; cantidades no son facturación; cobertura conserva sus límites |
| Permisos | Identidad, scope y selección de permiso comercial pendientes; esquema telefónico ausente |
| Transporte | Evolution inaccesible por URL configurada; app Meta sin suscripción callback; canal legacy y Srv05 OFF |
| Latencia | Sin E2E medido; una lectura independiente duró 14.12 s, no se diagnostica degradación ni SLA |

La primera corrida del script de inspección tuvo un `ProgrammingError` por pasar parámetros vacíos a SQL con LIKE. Se corrigió únicamente el script de evidencia y se repitió read-only; [salida original](preflight.json) preservada. No es defecto runtime Telchi.

## 11. Acciones humanas exactas pendientes

Estos insumos desbloquean operaciones específicas; no requieren rediseñar Messaging ni repetir LlmFit.

1. Identificar y autorizar por nombre/host la base **exclusivamente DEV**, declarando que no sirve tráfico productivo; si `team360` es compartida, proporcionar DSN privado de base DEV separada. Confirmar respaldo restaurable y procedimiento/ventana de reversión de 027.
2. Designar teléfono de prueba consentido, usuario Team360 existente, workspace Telchi autorizado y actor administrativo; aportar referencia opaca de verificación de posesión/identidad. Aprobar el procedimiento administrativo de binding. No enviar esos datos personales en reportes públicos.
3. El owner debe seleccionar un permiso empresarial **existente** aplicable a la capability y acreditar scope completo del workspace y módulo habilitado. Si el usuario no tiene acceso, conservar DENIED; no ampliarlo para la prueba.
4. Confirmar ownership/configuración del canal DEV existente antes de migrarlo a horizontal/Telchi: entorno dev, tenant Telchi aprobado, workspace correcto, module telchi y receiver_context correspondiente. No adoptar el workspace público para Telchi por conveniencia.
5. El operador de Evolution debe proporcionar endpoint DEV accesible y confirmar instancia `team360-meta-dev`; validar su conexión y webhook local sin reemplazar callbacks ajenos.
6. El owner Meta debe aprobar/restablecer la suscripción webhook **DEV** de la app Team360 usando callback accesible y verificación existentes. La suscripción WABA ya existe; no crear otra app/número ni modificar activos productivos.
7. Con esos insumos, configurar solo el proceso Srv05 DEV con Evolution ON, horizontal_v1 y lifecycle PostgreSQL; componer mediante `create_telchi_app(policy=política aprobada)`. Iniciar y verificar el servicio únicamente cuando sus condiciones de seguridad estén satisfechas.
8. El usuario consentido enviará el mensaje A desde WhatsApp y confirmará visualmente la respuesta; luego B–E. Para F designar un segundo destinatario/identidad de prueba consentido. Capturar correlation IDs y callbacks sin teléfonos completos.

Mientras esos insumos faltan, no es seguro aplicar 027, crear binding, atestar permiso/scope, activar callback ni comenzar la conversación.

## 12. Archivos y validaciones

Solo se agregaron reportes, un script read-only y sus salidas en este directorio; ninguna implementación o configuración preexistente fue editada.

- Nuevos: `report.md`, `preflight.py`, `preflight.json`, `preflight-r2.json`, `foundation-preflight.json`, `luna-preflight.json`, `regression.txt`, `lat-md.txt`, `lat-index.txt`, `lat-sections.txt`, `lat-code-refs.txt`, `lat-all.txt`.
- Regresión: `env -u TEAM360_MESSAGING_ISOLATED_TEST_DSN -u TEAM360_MESSAGING_POSTGRES_TEST -u TEAM360_MESSAGING_TELCHI_SQL_TEST OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 uv run pytest modules/telchi/assistant/tests tests/test_telchi_assistant_srv05.py tests/test_messaging_handlers.py tests/test_messaging_horizontal_runtime.py -q --tb=short`.
- [Resultado](regression.txt): **126 PASS**, 1 warning de fixture Diagnosis in-memory, 1.54 s. No certifica base ni transporte real.
- Gates LAT `md`, `index`, `sections`, `code-refs`, completo: exit 0. `git diff --check`: exit 0. Repetidos tras escribir el reporte; no cambios LAT/GLOBAL para conseguir PASS.
- Host: BUSY_BUT_SAFE, 8 cores, load 2.31/2.76/2.35, MemAvailable 5783 MB, swap 4189 MB; dos muestras de vmstat sin swap-in/out, idle 79–82%. Trabajo secuencial, un request Luna, una capability, OMP/BLAS 2, sin suites amplias ni browsers.
- RESOURCE_GUARD=PASS en alcance observado; ENVIRONMENTAL_ABORTS=0; UNRELATED_PROCESSES_TERMINATED=0; OWN_PROCESSES_LEFT_RUNNING=0. No se crearon servidores ni workers persistentes; procesos de comandos esperados terminados.
- Impacto transversal: solo lecturas PG/Meta/Evolution y una sonda Luna/Foundation; sin cambios de contratos, grants, lifecycle, Flow, Diagnosis, Srv01 ni PROD.

## 13. Resultado y próximo paso

PARTIAL acredita disponibilidad independiente o contratos focalizados; BLOCKED significa que la garantía operacional por teléfono no se pudo ejecutar. No hay PASS E2E ni conversación real.

```text
TELCHI_DEV_PHONE_BINDING=BLOCKED
TELCHI_DEV_BUSINESS_AUTHORIZATION=BLOCKED
TELCHI_DEV_EVOLUTION_INGRESS=BLOCKED
TELCHI_DEV_MESSAGING_DISPATCH=PARTIAL
TELCHI_DEV_LUNA_STATE_ENGINE=PARTIAL
TELCHI_DEV_FOUNDATION_QUERY=PARTIAL
TELCHI_DEV_CONVERSATION_PERSISTENCE=BLOCKED
TELCHI_DEV_WHATSAPP_DELIVERY=BLOCKED
TELCHI_DEV_END_TO_END=BLOCKED
```

Próximo paso: recibir las aprobaciones/identidades y restablecer el canal DEV enumerados arriba, luego ejecutar A desde el teléfono. No depurar conversación preventivamente ni presentar este preflight como éxito WhatsApp.
