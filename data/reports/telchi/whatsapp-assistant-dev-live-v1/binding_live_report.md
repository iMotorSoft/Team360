# Telchi WhatsApp DEV Binding & Live V1

Ejecución DEV del 11/10/2026. A–H conservan el primer cierre; I registra la verificación humana y sesión live posterior. El binding ya está verificado, pero aún no hay conversación empresarial ni entrega E2E comprobadas.

## A. Estado inicial

Preflight focalizado sobre el destino DEV autorizado por el propietario, sin nuevas auditorías generales ni desarrollo de login.

- Rama `feature/console-backend-core`; HEAD `09d2ec7`. Worktree con cambios preexistentes reconocidos, preservados; sin commit, push ni cambio de rama.
- Contexto: TELCHI / VENTAS + USUARIOS_ROLES_Y_PERMISOS / DEVELOPMENT operacional DEV / DATA_LAKE + PG18 / REPORT + CONVERSATIONAL_CONTEXT. Sin SAP ni promoción productiva.
- PG18 `localhost:5432/team360`, versión 18.4. Organización y workspace Telchi activos/testing; identidades existentes.
- Evolution existente `team360-meta-dev`, `127.0.0.1:18180`, estado `open`, Meta CLOUD_API y receptor VERIFIED. Webhook local inicialmente deshabilitado.
- Canal Telchi ausente al inicio; canal legacy público existente preservado.
- Srv05: factory disponible, sin listener Telchi activo. Composición real comprobada sin ejecutar startup.
- Evidencia: [preflight](binding-preflight.json), [postcheck](binding-postcheck.json).

## B. Migración 027

Se aplicó el archivo existente sin modificarlo, con respaldo nuevo y ensayo transaccional previo sobre el destino autorizado.

- Archivo: `SrvRestAstroLS_v1/backend/db/migrations/027_team360_messaging_phone_bindings.sql`.
- SHA-256: `9ff78e59b5276e0158a774aaef70162770bc907fbe71cf81159a73ec036f1694`.
- Coincide con el hash consignado en [aprovisionamiento anterior](real_provisioning_report.md). Los tests PG18 históricos documentan restricciones y rollback, pero no conservan checksum de aquella corrida: no se inventó esa comparación.
- Dependencias existentes: `core_users`, `core_workspaces`, `core_events`, `communication_providers`. Tabla y función 027 ausentes al inicio; cuatro índices de transporte 026 presentes.
- Backup completo nuevo, privado owner-only: `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/private/telchi/backups/binding-027-20261011T232228Z/team360.dump`; 3.143.971 bytes.
- Backup SHA-256: `9be210ce43496e4bd95ebe3545574b57c31cbf978c6a46043eeced9bf6d6444f`. `pg_restore --list` y extracción SQL a `/dev/null`: exit 0. No se hizo restore completo descartable.
- Ejecutor administrativo controlado: conserva SQL exacto salvo retirar el wrapper BEGIN/COMMIT activo para que la conexión controle la transacción. Lock timeout 3 s; statement timeout 10 s; PG18 y DSN loopback pinneados.
- Ensayo CREATE + validación + rollback forzado: PASS; ausencia posterior de tabla comprobada. Aplicación y commit final: 23:22:33 UTC.
- Validados cuatro FK, PK, unique telefónico por scope, checks, dos índices y trigger BEFORE INSERT/UPDATE/DELETE habilitado. La migración prohíbe DELETE y mutación del scope, exige verificación para estado verified y audita sin teléfono. REVOKE PUBLIC permanece en el SQL aplicado.
- Un evento administrativo `telchi.dev.migration_027.applied` conserva checksum y hash del backup. No existe ledger oficial SQL demostrado: no se creó uno alternativo.
- No se ejecutó rollback destructivo postcommit. Antes de bindings reales, la reversión del DDL exige revisión/autorización; después de vínculos, usar revocación y conservar auditoría, nunca DROP ni restore ciego.
- Evidencia completa: [migración](binding-migration.json), ejecutor [binding_migration.py](binding_migration.py).

## C. Identidad

Identidad y permisos se verificaron en PG18 mediante el resolver Console real; la posesión telefónica continúa pendiente.

- Piloto `devfull@telchiai.com`: `5015a69d-eb86-4ac9-b97f-c31dc06e2b59`, active.
- Workspace `telchi_dev`: `3fb026a1-a4ba-44b3-b65b-fab452df7fc9`; organización Telchi `44b9b7ea-1c19-4a9f-a3d5-1f20622d2f99`.
- Actor administrativo designado `admin@telchiai.com`: `73d09264-8be2-4402-8023-0142a5f26730`, delegación previa reutilizada. No se fabricó una sesión Console de ese actor.
- `PermissionConsoleRepository`: exactamente `telchi.sales.source_quantity.read.v1`; descripción acredita TODO el workspace para la capability documental exacta, no acceso global, SAP, facturación, sucursales o canales.
- Permisos del piloto en workspace administrativo Team360: vacíos. El administrador Telchi tiene permisos Console efectivos vacíos; su delegación no se reinterpretó como acceso comercial.
- Política runtime aprobada explícitamente para Telchi y ese permiso; flags de habilitación/scope sólo en composición, sin grants nuevos ni catálogo paralelo de módulos.
- Línea candidata terminada en 6950. No se usa allowlist para autorizar negocio: únicamente filtró la observación de la prueba de posesión.
- Cero bindings en PG al cierre; `PhoneIdentityRepository.resolve` devuelve None para la línea candidata. No se llamó a `bind_verified_dev_phone` sin evidencia.
- El procedimiento existente requiere consentimiento, referencia opaca, actor Telchi autorizado, membresía, permiso y ausencia de conflictos. Continúa preservando multilínea, revocación individual y separación DEV/PROD.

## D. Canal

El registro horizontal está persistido, pero la sesión del asistente no se activó antes de verificar la línea.

- Canal `telchi_whatsapp_dev`: `489e6f2c-8bac-4805-99ba-7dbe4d48c10e`, testing, workspace Telchi real.
- Provider Evolution existente, instancia `team360-meta-dev`; `dispatcher=horizontal_v1`, environment dev, module/tenant telchi, dev_only true.
- Receiver context recuperado desde Meta y cotejado con la configuración real; no es el teléfono remitente. Receptor visible terminado en 4780; valores completos permanecen privados.
- `ProvisioningRepository.provision` creó exclusivamente una fila de canal y su auditoría; roles/grants anteriores reutilizados. Segunda ejecución en rollback: cero filas nuevas.
- `create_telchi_app` registra `TelchiHandler`; public capabilities vacías, permiso documental obligatorio, routing horizontal concordante. No se usó fallback legacy.
- **Limitación de arranque identificada:** la factory Srv05 conserva `_start_flow_scheduler` y PG tiene `automation_enabled=true`. No se arrancó ese hook ni se cambió Flow. Antes del listener live, la composición operacional debe excluir el scheduler ajeno de esta sesión, manteniendo pool y validación Evolution reales.
- Callback temporal Cloudflare único hacia Evolution `/webhook/meta`, no hacia PostgreSQL ni otras rutas Srv05. Challenge público correcto y suscripción Meta `messages` activa comprobada por readback.
- Ventana: 23:24:45–23:27:48 UTC. No se reutilizó URL histórica, no se creó app/WABA, no se modificó PROD ni se reinstaló Evolution.
- Al cerrar: suscripción restituida al estado inicial vacío; túnel propio reaped y lector cerrado. Callback NO activo al cierre; webhook local Evolution sigue deshabilitado.
- Evidencia: [canal](binding-channel.json), [callback](binding-callback.json), [log saneado](binding-tunnel.log).

## E. Pruebas reales

Ninguno de los seis tests WhatsApp pudo comenzar: no hubo ingreso nuevo durante la ventana de verificación y el teléfono no está vinculado.

| Prueba | Resultado actual |
| --- | --- |
| Verificación de posesión | Sin mensaje nuevo observado; pendiente envío humano y confirmación del operador |
| 1 Recepción/respuesta | NOT_EXECUTED; sin Srv05 live ni binding |
| 2 Consulta documental | NOT_EXECUTED por WhatsApp; preflight Foundation independiente correcto |
| 3 Continuidad PG | NOT_EXECUTED sobre conversación real |
| 4 Facturación septiembre | NOT_EXECUTED por WhatsApp; sin capability monetaria habilitada |
| 5 Causas de caída | NOT_EXECUTED por WhatsApp; no se creó diagnóstico causal ni jobs |
| 6 Rechazo externo | NOT_EXECUTED; falta segunda identidad telefónica consentida |

El postcheck contó **cero inbound nuevos de cualquier remitente** en esa instancia desde el inicio de la ventana: no depende sólo del filtro de JID piloto.

Preflight mínimo Luna: una llamada real, `gpt-5.6-luna`, medium, metadata/razonamiento devueltos correctos, sin fallback; ASK y `committed=true`, 4.787 s de procesamiento. Identidad/PG/transporte de esa sonda son simulados, no conversación WhatsApp ni benchmark.

Preflight Foundation read-only: capability `telchi.sales_top_items.source_quantity.20260101_20260915.v1`, publicación `foundation_afd08d9eca6a725be53cdc3f9d5709c9`, snapshot 1408, actualización 2026-09-28T18:18:35.264000. Diez filas, 15.593 s; hash de resultado `cba2bd24f0fa00573343eebf3f31d3376a85a63f0a89da05fb82573adf8ea706`. Sin exponer filas empresariales ni consultar SAP.

Las cantidades documentales originales por producto no son facturación monetaria ni venta neta; no descuentan créditos/anulaciones ni certifican comparabilidad de UoM o completitud histórica.

Evidencia: [Luna](binding-luna-preflight.json), [Foundation](binding-foundation-preflight.json). Correlation ID de la sonda Luna `probe-0`, NO de un mensaje externo. Correlación WhatsApp, intent outbound y latencias E2E: NOT_OBSERVED/NOT_MEASURED. `PROVIDER_ACCEPTED`, `DELIVERED`, `DEVICE_RECEIVED`: ninguno observado en esta ejecución; cero envíos.

## F. Seguridad y validaciones

Se preservaron límites de identidad, módulos y entorno. Tests locales no sustituyen rechazo o entrega por WhatsApp real.

- Sin números completos, secretos, verify tokens o datos empresariales innecesarios en evidencia nueva pública. Receptor completo privado con permisos 0600.
- No login/password, usuarios adicionales, permisos nuevos, Srv01/Flow/Diagnosis/State Engine/Foundation modificados, PROD, commit o push.
- Cuatro índices 026 de deduplicación presentes; contratos de aislamiento/dispatch/auditoría comprobados por tests. No se certifica deduplicación externa nueva ni entrega física exactly-once.
- Limitación conocida Evolution v2.3.7: challenge autentica configuración, pero `/webhook/meta` no valida HMAC. No presentar un POST público por sí solo como prueba criptográfica de posesión. Revisar origen persistido fresco y confirmación explícita del operador antes del binding.
- Tests focalizados secuenciales: **124 passed, 1 skipped**, 1.86 s; skip de integración descartable no apuntado a team360; warning preexistente de fixture Diagnosis in-memory. [Salida](binding-tests.txt).

Comando de tests desde backend; variables de suites destructivas/desarrolladas aparte removidas explícitamente:

```bash
env -u TEAM360_MESSAGING_ISOLATED_TEST_DSN -u TELCHI_PROVISIONING_TEST_DSN -u TEAM360_MESSAGING_POSTGRES_TEST -u TEAM360_MESSAGING_TELCHI_SQL_TEST OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 uv run --no-sync pytest modules/telchi/provisioning/tests/test_live_bootstrap.py modules/telchi/provisioning/tests/test_admin.py modules/telchi/assistant/tests/test_assistant.py tests/test_messaging_horizontal_runtime.py tests/test_srv05_horizontal_composition.py tests/test_telchi_assistant_srv05.py tests/test_messaging_meta_config.py -q --tb=short
```

Los scripts nuevos se ejecutaron desde backend con `.venv/bin/python ../../data/reports/telchi/whatsapp-assistant-dev-live-v1/binding_*.py`, individualmente: preflight, migration, channel y callback. No reejecutar migration/channel a ciegas: el ejecutor exige objetos ausentes y el canal exige creación única.

Validación documental y diff: [binding-validation.txt](binding-validation.txt). Revisión final restringida a archivos nuevos `binding*`; cambios preexistentes intactos. No se actualizaron documentos GLOBAL ni LAT.

Host BUSY_BUT_SAFE: ocho cores, load inicial 2.49/2.55/2.22, ~5.2 GB disponibles; antes de sondas ~5.6 GB y load 1.64/2.06/2.14. Dos intervalos vmstat iniciales sin swap-in/out; swap histórica no vaciada ni servicios reiniciados. Trabajo secuencial, una conexión por operación y un único túnel; sin browsers, suites generales o benchmarks.

```text
HOST_PREFLIGHT=BUSY_BUT_SAFE
RESOURCE_GUARD=PASS
CONCURRENCY_USED=1 sequential worker; OMP/BLAS budget 2
UNRELATED_PROCESSES_TERMINATED=0
ENVIRONMENTAL_ABORTS=0
OWN_PROCESSES_LEFT_RUNNING=0
```

## G. Pendientes

La próxima sesión requiere una acción humana concreta y conservar los componentes ya aprovisionados, sin reabrir arquitectura.

1. Coordinar nueva ventana: confirmar en el chat «listo con WhatsApp». **La URL temporal anterior ya está cerrada; no enviar ahora esperando una respuesta.** El agente reabrirá un único callback DEV y avisará cuando esté listo.
2. Desde la línea piloto terminada en 6950, al contacto Team360 DEV terminado en 4780, enviar exactamente: «TELCHI DEV: soy devfull@telchiai.com y autorizo vincular esta linea para la prueba.» Confirmar aquí que el operador lo envió. No compartir contraseñas ni códigos privados.
3. Cotejar mensaje fresco persistido/origen con confirmación humana; conservar referencia opaca privada y vincular mediante `bind_verified_dev_phone`. No usar mensajes históricos, booleanos inventados o allowlist como evidencia.
4. Arrancar sesión Srv05 Telchi con la factory existente y política aprobada, excluyendo scheduler Flow ajeno; configurar webhook local Evolution autenticado al endpoint Srv05 y mantener callback durante la conversación. Sin fallback legacy ni cambios de infraestructura alternativa.
5. Consulta inicial soportada: «Top 10 productos por cantidad documental del 1 de enero al 15 de septiembre de 2026, sin filtros». Después continuidad, facturación no disponible y análisis futuro. Registrar auditoría PG, correlaciones, outbound y confirmación de recepción real del teléfono.
6. Designar una segunda línea consentida para rechazo externo; no probar sobre teléfonos ajenos.

No se observó fallo funcional WhatsApp porque el flujo no comenzó. No hubo bloqueo de permisos Meta ni del proveedor Luna en los preflights. No se depuraron prompts, modelos, conversación o calidad LlmFit.

## H. Estados al cierre de la primera ventana

PASS se limita a garantías actuales comprobadas; PARTIAL no equivale a una conversación WhatsApp ni a callback actualmente activo.

```text
TELCHI_DEV_MIGRATION_027=PASS
TELCHI_DEV_PHONE_VERIFICATION=BLOCKED
TELCHI_DEV_PHONE_BINDING=BLOCKED
TELCHI_DEV_BUSINESS_AUTHORIZATION=PASS
TELCHI_DEV_HORIZONTAL_CHANNEL=PARTIAL
TELCHI_DEV_EVOLUTION_INGRESS=PARTIAL
TELCHI_DEV_LUNA_STATE_ENGINE=PARTIAL
TELCHI_DEV_FOUNDATION_QUERY=PARTIAL
TELCHI_DEV_CONVERSATION_PERSISTENCE=BLOCKED
TELCHI_DEV_WHATSAPP_DELIVERY=BLOCKED
TELCHI_DEV_END_TO_END=BLOCKED
```

Impacto transversal de la primera ventana: tabla/función/trigger 027, evento administrativo y canal Telchi DEV con auditoría en PG18; suscripción Meta temporal retirada. Sin mutar canales legacy, permisos previos, otros módulos o entornos.

## I. Verificación confirmada y sesión live posterior

La segunda ventana recibió el mensaje consentido fresco. El operador confirmó «enviado» en el chat; el vínculo fue aplicado mediante el procedimiento existente y Srv05 quedó activo para iniciar los tests empresariales.

- Segunda ventana: callback verificado desde 23:33:58 UTC. Mensaje originado desde la línea piloto, fromMe false, texto de identidad y consentimiento exacto, timestamp posterior a la apertura.
- SHA-256 del identificador proveedor: `75b4beb87226225e3f0bacfbe17ef2574d4df6594c0e6a40a0c5ee9a52375775`. Evidencia privada completa en PRIVATE_ROOT, permisos 0600; sin teléfonos en reportes.
- Se cotejó el comprobante privado con la fila original actual de Evolution, instancia `team360-meta-dev`, y la confirmación humana independiente. No se usó un log histórico ni un POST público aislado como prueba suficiente.
- `bind_verified_dev_phone` aplicado en transacción serializable: binding `c5b9f0b5-54fe-447c-bbfd-2d5131bb2b57`, DEV/Evolution/Telchi/piloto exactos. Referencia opaca `whatsapp-dev-proof:a589098c-118b-5be2-aeb2-be4eb26881ec`; actor administrativo designado y membresía validados.
- PhoneIdentityRepository devuelve la identidad piloto con exactamente `telchi.sales.source_quantity.read.v1`. Segunda llamada al procedimiento: mismo binding, sin duplicación. Auditoría `messaging.phone_binding.insert`, sin PII. Evidencia: [binding aplicado](binding-phone-applied.json).
- Se cerraron túnel/suscripción de la ventana de posesión. Para conversación se levantó una sesión distinta: [estado live](binding-live-20261011233901-session.json), READY desde 23:39:14 UTC, deadline 00:09:14 UTC del 12/10.
- Runtime operacional source de la factory existente `create_telchi_app` → Srv05; no harness E2E read-only, simulación de identidad o circuito messaging-only legacy. Un worker Uvicorn; lifecycle pool PG real y `_validate_evolution_binding` preservados. Pool baseline hasta cinco conexiones; sin pool alternativo.
- Selección temporal de hooks excluye únicamente `_start_flow_scheduler`/`_stop_flow_scheduler`. No se editaron Srv01, Flow o flags persistidos; automation_enabled sigue intacto. No se llama a ciclos Flow.
- Listener en dirección privada resuelta por el contenedor, puerto 18181, como el procedimiento histórico. Boundary operacional sólo admite health y POST del webhook Messaging autenticado; otras rutas 404 y token ausente 401 comprobados. No hay exposición pública del listener completo.
- Ruta real container → Srv05 comprobada con evento connection.update ignorado, sin mensaje ficticio ni consultas/WhatsApp salientes. Webhook Evolution habilitado, headers privados cotejados y events MESSAGES_UPSERT/MESSAGES_UPDATE.
- Quick Tunnel sólo expone Evolution; challenge público y suscripción Meta DEV messages activa comprobados. El supervisor conserva backend/túnel durante la ventana de conversación y al deadline/señal restaura sólo webhook/subscripción propios antes de cerrar hijos. No cerrar procesos ajenos.
- PIDs de sesión ongoing: supervisor 350350, backend 350416, túnel 350486. **Cleanup final pendiente de terminar la sesión humana**, no se declara OWN_PROCESSES_LEFT_RUNNING=0 para esta fase. Los estados READY son fechados y requieren revalidación si pasa el deadline.
- Dos defectos del runner operacional nuevo corregidos, sin tocar runtime: primer lanzamiento resolvía el symlink del intérprete fuera del venv; primer startup Srv05 escogía un wheel anterior por sys.path del script externo. Se usó el intérprete venv sin resolver symlink y el backend source explícito. Ambos procesos fallidos terminaron/reaped; no son fallos del asistente o proveedor.
- Tests actuales de composición/Meta: **18 PASS**, 1.53 s; [salida](binding-live-tests.txt). Script compilado y actual listener/auth/container/callback comprobados. Fuente propia: [sesión](binding_live_session.py), [binding](binding_phone_apply.py), [observador read-only](binding_live_observe.py).
- Observación PG de 23:39:59 UTC: cero eventos empresariales y cero conversaciones Telchi aún. [Última evidencia PG](binding-live-latest.json). La prueba de posesión anterior ocurrió antes del listener Telchi y no cuenta como turno empresarial.
- Próximo mensaje solicitado al humano: «Top 10 productos por cantidad documental del 1 de enero al 15 de septiembre de 2026, sin filtros». Confirmar recepción física de la respuesta; después continuidad y tests no disponible/futuro/seguridad.

Estados actuales de esta fase: PASS de canal certifica concordancia runtime/PG/handler, no ejecución de un turno. PASS de ingress acredita el mensaje real de posesión en Evolution; no se confunde con procesamiento Telchi.

```text
TELCHI_DEV_MIGRATION_027=PASS
TELCHI_DEV_PHONE_VERIFICATION=PASS
TELCHI_DEV_PHONE_BINDING=PASS
TELCHI_DEV_BUSINESS_AUTHORIZATION=PASS
TELCHI_DEV_HORIZONTAL_CHANNEL=PASS
TELCHI_DEV_EVOLUTION_INGRESS=PASS
TELCHI_DEV_LUNA_STATE_ENGINE=PARTIAL
TELCHI_DEV_FOUNDATION_QUERY=PARTIAL
TELCHI_DEV_CONVERSATION_PERSISTENCE=BLOCKED
TELCHI_DEV_WHATSAPP_DELIVERY=BLOCKED
TELCHI_DEV_END_TO_END=BLOCKED
```

Rama y HEAD intactos. Impacto adicional: binding telefónico verificado/auditado y configuración transitoria Evolution/Meta DEV. Sin cambios de permisos, otros módulos, producción, prompts o Foundation. Validación de esta actualización: `binding-live-validation.txt`; recepción real de la respuesta sigue pendiente.
