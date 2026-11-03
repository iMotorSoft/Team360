# Continuidad documental y productos de factura V1

Cierre de implementación DEV en `feature/console-backend-core`, autorizado por el owner. No declara activación del proceso WhatsApp existente ni promoción productiva. Evidencia del 18/10/2026 local y 19/10 UTC.

## Resultado

Los PASS siguientes describen las garantías efectivamente ejecutadas, no una conversación WhatsApp ni una nueva certificación integral del runtime.

```text
DOCUMENT_CONTINUITY=PASS
INVOICE_LINES_CAPABILITY=PASS
FOUNDATION_DOCUMENT_LINEAGE=PASS
REAL_INVOICE_LINES=FOUND
LUNA_REAL_INTERPRETATION=PASS
RBAC=PASS
TENANT_ISOLATION=PASS
PRODUCT_REFERENCES=PASS
TESTS=422 passed / 2 skipped / 1 warning
SIX_GATES=STALE
READY_FOR_WHATSAPP=NO
```

La factura N.º **260192728**, del **24/09/2026**, contiene una línea publicada: **L00003 — AGUA DESIONIZADA GRANEL x L. — cantidad documental 10**. La UoM nativa de INV1 **no está publicada**. No se afirma que sean diez litros: el nombre del producto y su UoM de catálogo no acreditan la unidad de esa línea.

## Causa y solución

La selección anterior existía, pero el contrato sólo proyectaba campos de una lista. No podía expresar una nueva operación sobre el documento identificado y convertía esa carencia en ambigüedad.

Se agrega `DOCUMENT_REFERENCE` al resolvedor independiente, sin modificar el State Engine. `READ_LINES` obtiene productos; `SELECT_DOCUMENT` responde con campos conservados o explica los ausentes. Los IDs nacen de la fila auditada, no de Luna. `document_reference`, `result_reference` y `reference_focus` separan factura, línea y foco; volver a la factura conserva la selección del producto. Una nueva consulta independiente abandona el foco documental sin borrar auditorías.

Se reutiliza el contrato ordinal V1 para las líneas. Una lista de un elemento es inequívoca; una lista con varios y sin selección requiere aclaración. Un fallo de lectura conserva el número de factura y no ejecuta otra lista como sustituto. Cliente o importe ausentes no se convierten en filtros, totales globales ni una solicitud de identificar nuevamente la factura.

## Foundation y semántica

La [evidencia de linaje y paridad SQL independiente](foundation-lineage.json) acredita datos reales, lectura read-only y ausencia de cambios a Foundation.

- Publicación `foundation_afd08d9eca6a725be53cdc3f9d5709c9`, snapshot `1408`, fecha publicada `2026-09-28T18:18:35.264000`.
- Productor `create_initial._sales_candidate`: fuente `SAP_B1_HANA`, cabecera `OINV`, líneas `INV1`. Se valida el DocEntry interno `11532517` junto con tipo, fuente, publicación/snapshot, número y fecha; no se usa DocEntry aislado.
- Cabecera activa `N` única, líneas únicas ordenadas por LineNum ascendente, misma extracción y source_as_of. Colisiones de fuentes/tipos incompatibles quedan excluidas, no resueltas mediante joins aproximados. Líneas cerradas no se confunden con facturas anuladas.
- La descripción es la del catálogo SAP_HANA/OITM de esa misma publicación, no el texto histórico de INV1. Descripción faltante se muestra como no disponible. No se sustituyen líneas por resultados de búsqueda.
- No se consultó SAP, no se modificó CURRENT ni sus datos. No se devuelven importes, conversiones, agregados físicos ni stock/precios/cobranza. La respuesta comercial no expone DocEntry ni nombres de tablas.
- Se conservan los límites originales del contrato ordinal V1; no se agregan vencimientos ni nuevas restricciones del piloto. Una publicación cambiada/incompatible bloquea la operación concreta, conservando la identificación documental.

## Permisos y persistencia

El [plan previo](rbac-plan.json) documentó el incremento antes de aplicarlo. La [verificación real posterior](rbac-verification.json) acredita resolver Console, delta exacto e idempotencia.

Se ejecutó el procedimiento existente `provisioning.live_cli --invoice-activation`: plan read-only y aplicación local-owner DEV con manifest, hashes de fuentes, snapshot privado recuperable y transacción SERIALIZABLE. Cambios exactos: un permiso `telchi.sales.invoice_lines.read.v1`, un rol local `telchi_sales_invoice_lines_reader_v1`, una relación rol-permiso, una asignación a `devfull@telchiai.com` en `telchi_dev` y dos eventos administrativos. Identidades, perfiles y seis permisos anteriores permanecen iguales. No se otorgaron grants globales ni se editaron permisos comerciales en la habilitación WhatsApp.

El ensayo previo verificó idempotencia y rollback por igualdad del snapshot antes de aplicar. La escritura inicial del archivo de reporte falló después de esas comprobaciones por un path relativo incorrecto; no dejó cambios DB. El backup/manifest privado se preservó y el CLI validó su integridad antes de aplicar. La verificación final volvió a comprobar el delta y una reaplicación no-op en transacción revertida.

Cada lectura de documento/producto revalida el permiso comercial actual; una selección histórica no otorga acceso. Los tests negativos cubren revocación entre turnos, durante interpretación y en respuesta cacheada. Tenant/workspace/identidad/conversación siguen validados por el repositorio y el resolvedor. PostgreSQL temporal valida commits entre turnos, recuperación de ambos punteros y exclusión de otra conversación sin tocar filas Messaging operacionales.

## Pruebas y evidencia

Las pruebas distinguen datos reales, interpretación real, persistencia real y fixtures; ninguna sonda envió WhatsApp ni inició un servidor.

- [Suite final](pytest-final-r3.txt): `TEAM360_RESULT_REFERENCE_POSTGRES_TEST=1 uv run pytest modules/telchi/assistant/tests modules/telchi/provisioning/tests modules/telchi/datalake/tests/test_invoice_lines_query.py tests/test_telchi_assistant_srv05.py -q` → **422 PASS / 2 skips**. Los skips corresponden a suites PostgreSQL de provisioning opt-in ajenas; warning preexistente del repositorio Diagnosis in-memory durante import del test Srv05.
- [Conversación completa real focalizada](luna-full-conversation.json): `uv run python -m modules.telchi.assistant.tests.live_invoice_continuity --full-conversation --output <path-nuevo>` → **9 turnos PASS**. Secuencia original 5 → 3 → segunda → primera → productos, seguida por cantidad, primero, regreso a factura y su número. Exactamente tres llamadas a capabilities: dos listas y una lectura de líneas. Ninguna lectura adicional para seguimientos ordinales.
- OpenAI directo, `gpt-5.6-luna`, esfuerzo `medium`, modelo/esfuerzo devueltos verificados, `store=false`, sin proxy ni fallback. Preflight real mínimo registrado antes de la secuencia; no usa Milvus ni LiteLLM. Sólo se envían descriptores, no filas de facturas/productos.
- La sonda utiliza identidad/RBAC fixture y puerto SQL en memoria declarado, con el repositorio real y Foundation real. No es evidencia de HTTP autenticado ni de binding/ingress WhatsApp. La prueba PostgreSQL temporal y el resolver RBAC real se acreditan por separado, no se presentan como una misma cadena operacional.
- La factura real tiene **una** línea. La interpretación de «¿Cuánto tiene del segundo producto?» se probó aparte con un descriptor de dos filas; los tests deterministas ejecutan la continuidad sobre dos líneas de fixture. No se inventó un segundo producto en la factura real.
- Negativos SQL: documento inexistente/anulado/duplicado, tipo o fuente diferente con el mismo DocEntry, duplicación de líneas, linaje incompatible, publicación cambiada, factura sin líneas, descripción ausente y unidad no acreditada. Negativos conversacionales: ambigüedad, referencia fabricada, usuario/tenant/workspace/conversación distintos, revocación, auditoría invalidada, nueva consulta y operación no verificable sin perder el documento.
- La revisión de presentación detectó cinco fallos en la corrida conservada `pytest-final-r2.txt`: el formatter pasó a exigir `updated_at` en fixtures/resultados legados cuyo contrato no lo exigía. Se corrigió la dependencia: cuando falta la fecha, la respuesta lo explica sin inventarla. Regresión focalizada: **71 PASS**; la suite final R3 sustituye esa corrida fallida, no la elimina.
- [Redacción comercial final](natural-responses.json): reutiliza los resultados Foundation acreditados de la conversación completa para probar el formatter final, sin repetir modelo ni consultas. La lista de facturas también oculta DocEntry/tablas y conserva identidad interna para pedidos explícitos; cambia únicamente presentación, no SQL, orden o permisos. La sonda completa conserva su texto anterior como evidencia histórica; su interpretación usa estados/descriptores, nunca ese texto formateado, por lo que la garantía semántica sigue vigente.
- [Sonda focalizada inicial](luna-foundation.json) y [revalidación intermedia](luna-foundation-final.json) se preservan como evidencia fechada, no se sobrescriben ni sustituyen el resultado final completo.

## Archivos del incremento

Todos los cambios de software son Telchi locales. Se preservó el worktree preexistente, incluidos archivos untracked; no se modificaron State Engine, Messaging, Foundation, configuración global, infraestructura ni frontend.

Bajo `SrvRestAstroLS_v1/backend/modules/telchi/`:

- `assistant/capabilities.py`, `handler.py`, `luna.py`, `repository.py`, `result_references.py`, `README.md`.
- `assistant/tests/test_invoice_continuity.py`, `test_invoice_continuity_postgres.py`, `live_invoice_continuity.py`.
- `datalake/invoice_lines_query.py`, `datalake/tests/test_invoice_lines_query.py`.
- `provisioning/invoice_repository.py`, `live_cli.py`, `sales_cli.py`, `provisioning/tests/test_invoice_admin.py`.
- `status_actual.md`; evidencia nueva en este directorio, sin editar registros anteriores.

El blast radius supera cinco archivos porque el objetivo autorizado cruza contrato, persistencia, interpretación, lectura, RBAC y sus regresiones; no añade capas preventivas ni otro framework de memoria. La [huella final de fuentes](source-manifest-final.json) identifica los archivos evaluados.

## Recursos y próximo paso

El host compartido conservó capacidad disponible. Se usó pytest secuencial y como máximo dos threads por conexión DuckDB, sin suites simultáneas, browsers ni servidores temporales.

```text
HOST_PREFLIGHT=SAFE
RESOURCE_GUARD=PASS
CONCURRENCY_USED=1 pytest worker / 2 DuckDB threads maximum
UNRELATED_PROCESSES_TERMINATED=0
ENVIRONMENTAL_ABORTS=0
OWN_PROCESSES_LEFT_RUNNING=0
```

El proceso WhatsApp activo **no se sustituyó ni reinició**; tampoco se editaron sus aprobaciones o registros de gates. El cambio de fuentes invalida la evidencia previa asociada al runtime: `SIX_GATES=STALE`, no un fallo funcional ni una nueva restricción del piloto.

Próximo paso: coordinar la carga controlada de esta versión y reacreditar únicamente las garantías operacionales afectadas mediante el procedimiento vigente. No declarar READY ni enviar WhatsApp automáticamente. La UoM nativa sigue como carencia concreta de Foundation, sin modificar sus datos ni inferir conversiones. No hubo commit, push ni operaciones Git de escritura.
