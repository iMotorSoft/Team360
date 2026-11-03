# Cierre comercial TelchiAI DEV

Rama `feature/console-backend-core`. Resultado del 19/10/2026: cinco respuestas reales y una comparación no soportada, explicada sin inventar cifras. No es cierre mensual certificado ni WhatsApp E2E.

## Conversación acreditada

Identidad del piloto y permisos Console reales, PostgreSQL persistente, Luna OpenAI directo y Foundation 1408 read-only. Cada turno crea un handler nuevo; no se usaron mocks de identidad, datos, modelo o persistencia.

| Pregunta | Respuesta comercial verificada / límite | Capability | Estado | Pendiente |
| --- | --- | --- | --- | --- |
| ¿Cuánto facturamos en septiembre de 2026? | Bs 8.891.439,79 de facturas activas BS, antes de NC. Actualización 28/09/2026; mes parcial, no cierre completo. | `sales.period_billed_amount.v1` | PASS | Cierre mensual completo no certificado. |
| ¿Y en agosto? | Bs 10.565.113,13, del 01 al 31/08/2026, misma métrica/moneda; actualización 28/09/2026. | `sales.period_billed_amount.v1` | PASS | Ninguno para esta lectura publicada. |
| ¿Cuál fue la diferencia? | Explica que no puede calcular automáticamente la diferencia; cero invocaciones de capability. No pide otro período para desbloquear una operación ausente. | Ninguna: comparación no soportada | BLOCKED | Comparador de resultados monetarios acreditados, con reautorización y compatibilidad de moneda, fuente y fechas. |
| Mostrame las últimas cinco facturas. | 260192728, 260192727, 260192726, 260192725 y 260739131; fecha documental 24/09/2026. | `sales.latest_documents.v1` | PASS | Ninguno para la lista publicada; no certifica actualidad SAP. |
| ¿Qué productos tiene la primera? | Factura 260192728: AGUA DESIONIZADA GRANEL x L., código L00003, cantidad documental 10. No se infiere unidad física desde el nombre. | `sales.invoice_lines.v1` | PASS | UoM nativa de línea no publicada; límite informado. |
| ¿Cuánto vale esa factura? | La misma factura 260192728 tiene total documental BS 25,00; no es cobrado ni saldo pendiente. | `sales.invoice_amount.v1` | PASS | Ninguno para el total documental publicado. |

La respuesta monetaria separa facturas activas, notas de crédito y neto documental. Septiembre: NC Bs 328.670,24 y neto Bs 8.562.769,55. Agosto: NC Bs 303.422,10 y neto Bs 10.261.691,03. No son cobros, ventas físicas ni saldo pendiente.

## Seguridad y activación DEV

La autorización no amplía otros usuarios, organizaciones, workspaces ni módulos. El resolver exige registro habilitado exacto; no interpreta comodines ni el nombre de un rol como autorización universal.

- Migración nueva `031_team360_scoped_full_access.sql`: registro por workspace/módulo y asignaciones FULL_ACCESS revocables por organización/workspace/módulo/usuario.
- Resolver Console conserva las dos ramas ordinarias de roles/perfiles y añade sólo la expansión de registros habilitados. Rechaza un permiso mal registrado con namespace de otro módulo; exige usuario, workspace y organización vigentes y tenant coincidente.
- Una asignación activa, exclusivamente al piloto existente de `telchi_dev`. Cero relaciones `core_user_roles` nuevas para el piloto; la lectura de importe individual aparece sólo mediante FULL_ACCESS. Catálogo futuro registrado/habilitado se reconoce sin otro grant individual.
- `telchi.sales.invoice_amount.read.v1` y su rol normal quedan registrados; ese rol no se asigna al piloto. Listar facturas o leer productos no concede importes individuales.
- Activación idempotente, backup privado previo y evento administrativo. Revocación real y su auditoría probadas dentro de transacción revertida; el permiso nuevo desaparece, los grants normales permanecen y la asignación se conserva activa al terminar.
- FULL_ACCESS no modifica autenticación, política de acceso al piloto, whole-workspace aprobado, validación de referencia original, source/snapshot, exclusión de anuladas, timeout ni límites de cada operación.
- Migración aplicada únicamente en DB local DEV. Un futuro despliegue del resolver requiere aplicar esa migración primero; no se desplegó ni cambió producción.

## Evidencia y comandos

Los JSON conservan preguntas, respuestas, auditorías, fuente y metadata del modelo. La prueba local autorizada no equivale a login humano ni a un mensaje recibido por WhatsApp.

- [Conversación final](conversation-release.json): seis turnos, estado durable y período ausente aclarado en preflight.
- [Paridad independiente](parity-release.json): otra consulta agrupada por fecha/moneda y suma Decimal independiente; diferencia cero en ambos períodos. Lista, relación documental y total individual contrastados separadamente.
- [FULL_ACCESS real](full-access-real.json): identidad existente, idempotencia, roles conservados y revocación/auditoría con rollback.
- [Gates finales](gates-release.json): puntero/hash del artefacto privado de reacreditación y manifest DEV. Conserva la política change-based existente; no añade vencimiento al piloto.
- [Primera reproducción](conversation-r1.json): comparación pedía aclaración de baseline pese a carecer de operación ejecutable. Corrección limitada al handler; [segunda comprobación](conversation-r2.json) y conversación final devuelven limitación explícita.

Desde `SrvRestAstroLS_v1/backend`, se ejecutaron secuencialmente estos comandos y las sondas de activación/revocación indicadas en sus módulos:

```bash
TEAM360_FULL_ACCESS_POSTGRES_TEST=1 TEAM360_RESULT_REFERENCE_POSTGRES_TEST=1 uv run --no-sync pytest tests/test_console_scoped_full_access_postgres.py tests/test_console_repositories_sql_safety.py tests/test_console_bootstrap_service.py tests/test_flow_executive_query.py modules/telchi/datalake/tests/test_invoice_amount_query.py modules/telchi/datalake/tests/test_invoice_lines_query.py modules/telchi/assistant/tests/test_invoice_amount.py modules/telchi/assistant/tests/test_invoice_continuity.py modules/telchi/assistant/tests/test_invoice_continuity_postgres.py modules/telchi/assistant/tests/test_sales_monetary.py modules/telchi/assistant/tests/test_result_references.py modules/telchi/assistant/tests/test_result_references_postgres.py -q
```

Resultado: **127 PASS**, sin skips. Regresión adicional del handler/provisioning: **78 PASS**; del evaluador de evidencia WhatsApp: **36 PASS**, sin skips; total focalizado **241 PASS**. No se ejecutó suite global ni browser: el cambio no incluye UI. Las pruebas unitarias usan fixtures explícitas; no sustituyen la conversación, paridad, revocación y gates reales descritos aquí.

```bash
.venv/bin/python -m modules.telchi.assistant.tests.live_business_close --output ../../data/reports/telchi/business-assistant-close-v1/conversation-release.json
.venv/bin/python -m modules.telchi.assistant.tests.verify_business_close --conversation ../../data/reports/telchi/business-assistant-close-v1/conversation-release.json --output ../../data/reports/telchi/business-assistant-close-v1/parity-release.json
.venv/bin/python -m modules.telchi.assistant.tests.gate_business_close --conversation ../../data/reports/telchi/business-assistant-close-v1/conversation-release.json --parity ../../data/reports/telchi/business-assistant-close-v1/parity-release.json --full-access ../../data/reports/telchi/business-assistant-close-v1/full-access-real.json --output ../../data/reports/telchi/business-assistant-close-v1/gates-release.json --publish
```

La regresión adicional se ejecutó con `uv run --no-sync pytest modules/telchi/assistant/tests/test_assistant.py modules/telchi/assistant/tests/test_sales_query_activation.py modules/telchi/provisioning/tests/test_monetary_admin.py -q` y `uv run --no-sync pytest modules/telchi/assistant/tests/test_whatsapp_dev.py -q`. Después se volvió a comprobar el admission normal: `FINAL_SIX_GATES=VALID`, fingerprint vigente y runtime `STOPPED`.

Las sondas rechazan sobrescribir evidencia: para repetir, utilizar paths nuevos y reacreditar el fingerprint correspondiente. La renovación verifica ASGI autenticado real, aislamiento real, revalidación ante revocación, claim PostgreSQL persistido y duplicados, respuesta cacheada y unicidad de intent outbound dentro de rollback. No hay sender simulado ni envío real; el intent de prueba no queda encolado. No certifica ingress externo ni entrega al dispositivo.

## Archivos e impacto

El scope es Telchi DEV más el resolver compartido autorizado y una migración aditiva. Todos los cambios preexistentes del worktree se preservaron; no se hizo commit ni push.

- `backend/modules/console/repositories.py` y `backend/db/migrations/031_team360_scoped_full_access.sql`.
- `backend/modules/telchi/datalake/sales_query.py`, `invoice_amount_query.py` y `tests/test_invoice_amount_query.py`.
- `backend/modules/telchi/assistant/capabilities.py`, `handler.py`, `whatsapp_dev_evidence.py`, `README.md` y pruebas `test_invoice_continuity.py`, `test_invoice_amount.py`, `test_sales_monetary.py`, `test_whatsapp_dev.py`, `live_business_close.py`, `verify_business_close.py`, `gate_business_close.py`.
- `backend/modules/telchi/provisioning/business_close_repository.py`, `business_close_cli.py` y `tests/live_full_access_close.py`.
- `backend/tests/test_console_scoped_full_access_postgres.py`, `backend/modules/telchi/status_actual.md` y este directorio de evidencia.
- Fuera de Git: backup privado, asignación/catalogación DEV y manifest/artefacto de gates. No se cambiaron secretos ni aprobación permanente del piloto.

El evaluador de intercambio manual reconoce ahora productos e importe individual con sus permisos específicos, sin declarar entrega por mera aceptación. Su regresión no envía mensajes; tras ese ajuste se repitieron conversación/paridad y gates con el fingerprint release.

El contrato monetario existente se reutiliza; sólo se exige fecha de actualización válida al validar su resultado y se mejora su presentación comercial. El total individual lee cabecera original, nunca líneas. El primer importe se sigue presentando como facturación registrada BS; no se convierte la métrica neta en ventas físicas.

## Gates documentales

Se ejecutaron `lat check md`, `lat check index`, `lat check sections`, `lat check code-refs`, `lat check` y `git diff --check`: todos PASS. Los warnings LAT de init/key y la deprecación uv existente no bloquearon la validación.

## Cierre y límites

Los estados se refieren al código y fingerprint acreditados en esta corrida. Una modificación relevante posterior exige reacreditación; no borra la autorización del piloto ni acredita despliegue.

```text
FULL_ACCESS=PASS
PILOT_FULL_ACCESS=PASS
PERIOD_BILLING=PASS
INVOICE_AMOUNT=PASS
CONVERSATIONAL_CONTINUITY=PASS
SIX_GATES=VALID
READY_FOR_MANUAL_WHATSAPP=YES
```

Sigue pendiente el comparador conversacional. El siguiente paso es el intercambio manual con el launcher existente: el runtime quedó detenido, no se activaron webhooks ni se enviaron mensajes. Preparado para prueba manual no significa WhatsApp E2E certificado.

Host observado: 8 CPU, load 2,22/2,86/4,30, unos 6,1 GiB disponibles y swap no creciente; muestra anterior sin actividad sostenida de swap. Ejecución secuencial, un worker pytest, una conexión PG por pool propio y dos threads DuckDB, sin browser.

```text
HOST_PREFLIGHT=BUSY_BUT_SAFE
RESOURCE_GUARD=PASS
CONCURRENCY_USED=1 worker; 2 DuckDB threads
UNRELATED_PROCESSES_TERMINATED=0
ENVIRONMENTAL_ABORTS=0
OWN_PROCESSES_LEFT_RUNNING=0
```
