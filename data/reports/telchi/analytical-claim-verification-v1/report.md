# TelchiAI Analytical Claim Verification V1

Cierre **PARTIAL** en `feature/console-backend-core`, DEV. Hay evidencia real de vinculación, rechazo y revisión de hipótesis; no se acredita todavía un investigador genérico listo para conectar a Web sin completar su contrato interno.

## Resultado empresarial primero

Para L02822, L02823, L03658 y L03649, agosto de 2026, la clasificación incompleta afecta una parte material del importe publicado; **su causa raíz no está demostrada**. No equivale a ausencia ni pérdida demostrada de ventas.

| Hecho | Valor | Condición y referencia original |
| --- | ---: | --- |
| Importe comercial del universo | Bs 180.400,81 | VERIFIED_WITH_LIMITATIONS; [r3](real-r3.json), `claim_verifications[2]` |
| Importe sin canal | Bs 47.340,13 | VERIFIED_WITH_LIMITATIONS; [r6](real-r6.json), `claim_verifications[0]` |
| Participación sin canal | 26,24 % | VERIFIED_WITH_LIMITATIONS; r3, `claim_verifications[4]`, dependencias numerador/denominador |
| Documentos sin clasificación | 93 | VERIFIED_WITH_LIMITATIONS; r6, `claim_verifications[2]` |
| Líneas sin clasificación | 154 | VERIFIED_WITH_LIMITATIONS; r6, `claim_verifications[1]` |

Las series 1260, 1261 y 1262 reúnen respectivamente Bs 38.097,31 / 67 líneas, Bs 6.858,22 / 66 líneas y Bs 2.384,60 / 21 líneas sin clasificación. Referencia: r6, `claim_verifications[3:9]`, con IDs de resultado, columna y grupo.

Esto localiza operaciones para investigar, no prueba que la serie cause el estado del canal. No se observaron reglas/versiones acreditadas del clasificador. Conviene contrastarlas con los documentos antes de reclasificar; no sustituir canal por serie, vendedor o almacén.

Son importes comerciales de líneas antes de notas de crédito y ajustes globales, no facturación neta, cobros ni totales de cabecera. El universo no es toda Calenta. La clasificación es la materializada en la publicación actual; no se certifica su estado histórico ni integridad completa del calendario.

Todas estas referencias se reconstruyeron con el verificador final: [auditoría final](final-audit-v4.json), r3 **13/13** y r6 **9/9**. Es replay de artefactos, sin nuevo I/O Foundation; conserva los IDs/digests originales y distingue los handles nuevos del replay.

## A. Diagnóstico reproducible

Las catorce afirmaciones se inspeccionaron individualmente. Comparten el rechazo inmediato `unsupported_filters`, pero sus agregaciones, poblaciones y límites semánticos no son equivalentes. El [diagnóstico JSON](diagnosis.json) contiene cada SQL y afirmación originales.

| Afirmación de r7 anterior | Turno de evidencia | Valor original | Expresión de medida | Límite semántico |
| --- | --- | ---: | --- | --- |
| 3 | 1 | 47340.130000 | SUM(line_total) | Importe publicado con valores NULL; no código oficial nuevo |
| 4 | 1 | 154 | COUNT(doc_entry) | Líneas con clave no nula, no documentos únicos |
| 5 | 2 | 19073.180000 | SUM(line_total) | Grupo NULL, L03658 |
| 6 | 2 | 43 | COUNT(line_num) | Líneas, L03658 |
| 7 | 2 | 18273.590000 | SUM(line_total) | Grupo NULL, L02822 |
| 8 | 2 | 52 | COUNT(line_num) | Líneas, L02822 |
| 9 | 2 | 5012.860000 | SUM(line_total) | Grupo NULL, L03649 |
| 10 | 2 | 31 | COUNT(line_num) | Líneas, L03649 |
| 11 | 2 | 4980.500000 | SUM(line_total) | Grupo NULL, L02823 |
| 12 | 2 | 28 | COUNT(line_num) | Líneas, L02823 |
| 13 | 1 | 85379.310000 | SUM(line_total) | HORIZONTAL / CONFIRMED publicado, no causalidad |
| 14 | 1 | 543 | COUNT(doc_entry) | Líneas HORIZONTAL, no documentos únicos |
| 15 | 1 | 47681.370000 | SUM(line_total) | SALON / SUPPORTED, no CONFIRMED |
| 16 | 1 | 837 | COUNT(doc_entry) | Líneas SALON; misma limitación de estado |

En los turnos 1–2, `channel_status`, `channel_code` y `currency_code` proyectaban respectivamente `sales_channel_semantic_status`, `sales_channel_code` y `currency`. El verificador aceptaba únicamente nombres canónicos y rechazaba los filtros completos antes de reconstruir valores.

Las catorce cifras coinciden con la reconstrucción independiente. COUNT es válido como conteo de líneas porque las claves están completas; no por el nombre del alias. La consulta del turno 2 seleccionaba filas con código **o** estado NULL: los grupos reclamados identificaban ambos NULL y se contrastaron expresamente.

La procedencia era además ambigua: en el turno 4, los mismos aliases representaban COALESCE con etiquetas calculadas. Por eso no basta sustituir aliases automáticamente. El turno 5 filtró la fuente por `UNCLASSIFIED`, etiqueta de presentación creada antes, y devolvió cero filas. No era un defecto Foundation.

Defecto adicional del bucle: sólo devolvía rechazos con `match=false`; los errores de forma/procedencia sin ese campo no llegaban a Luna. Ahora todo rechazo estructurado entra en la revisión, sin proporcionar una respuesta empresarial prefabricada.

## Contratos e implementación

Se reutilizan `ExploratoryQueryProposal`, `ValidatedExploratoryQuery`, `ExploratoryQueryResult`, catálogo, AST admitido, permisos, presupuesto, FoundationReader y ejecutor READ_ONLY. No se introdujeron aliases comerciales válidos ni reglas nuevas para Calenta.

`SQLColumnEvidence` y `SQLResultEvidence` añaden identidad emitida por el servidor, ejecución, publicación/snapshot, dataset lógico, tipo, expresión, campos, transformaciones, grano, predicado, agrupaciones, relaciones, métrica/unidad/moneda y limitaciones.

La identidad de columna depende de expresión/procedencia/tipo y versión Foundation, no de su alias; los resultados y grupos tienen handles propios. Una clasificación CASE/COALESCE conserva su carácter calculado. SOURCE significa campo de la publicación lógica materializada, no necesariamente campo comercial crudo de SAP ni regla oficial acreditada.

El registro enlaza cada afirmación con un resultado existente, columna existente y grupo divulgado. Revalida bindings, tipo numérico, definición de medida, moneda/unidad, grano, publicación/snapshot, período y población. Recalcula sumas con Decimal y conteos desde referencias reconstruidas, sin ejecutar el SQL del modelo para verificarlo.

Los porcentajes acreditados tienen dependencias explícitas y denominador de universo completo. Se valida su redondeo a la precisión declarada. Los joins con multiplicación se rechazan como evidencia; incluso un join sin multiplicación no adquiere significado empresarial automáticamente.

El ejecutor sigue admitiendo su SQL previo: la acreditación analítica es deliberadamente conservadora. CTE, subconsultas, agregaciones de expresiones no acreditadas, ciertos predicados y parámetros nombrados pueden ejecutarse y permanecer UNVERIFIED. No se infiere una métrica a partir de un alias convincente.

La prosa libre de Luna queda sólo en auditoría. La respuesta entregable se forma con hechos estructurados verificados y referencias, más límites explícitos. No se publica una causalidad sin mecanismo acreditado. Tampoco se certifica comprensión semántica arbitraria de lenguaje natural.

Los rechazos devuelven afirmación, razón, evidencia observada disponible y carencia que debe resolverse. Luna elige reformular, retirar o consultar. Hay máximo de revisiones, detección de rechazo repetido, detección de SQL repetido, presupuesto de intentos y cierre ante denegación de seguridad. No se reinician presupuestos de investigación.

El historial mantiene 32 KiB: deduplica descriptores y, si hace falta, reduce muestras con truncación explícita e IDs alineados. No amplía el límite ni presenta una muestra recortada como completa. Se declaró salida analítica de hasta 8.192 tokens por llamada y máximo 16 llamadas de investigación más un preflight; el adapter previo conserva 4.096 por defecto.

## B. Pruebas y revisión efectiva

Los casos sintéticos son aislados. Ninguna fila ficticia, error adversarial o regla experimental se introdujo en Foundation real.

| Caso | Evidencia permanente |
| --- | --- |
| Alias que imita fuente | `test_alias_cannot_impersonate_source_or_metric` |
| Clasificación calculada presentada como oficial | `test_calculated_classification_is_not_official` |
| Importe correcto, concepto equivocado | `test_correct_amount_wrong_business_concept` |
| Porcentaje con denominador incorrecto | `test_wrong_percentage_denominator` |
| Duplicación por join | `test_actual_readonly_synthetic_joins_cannot_multiply_invoice_facts[lines-300.00]` |
| Factura con varios movimientos | Mismo test, `[movements-600.00]`; cabeceras originales suman 200.00 |
| Unidad/moneda/grano incompatible | `test_incompatible_units_currency_grain` |
| Resultado, columna o grupo inexistente | `test_nonexistent_result_and_column_and_row` |
| Cambio de snapshot | `test_snapshot_change`, y versión de dependencias/ratio |
| Hipótesis contradicha después | `test_later_observation_contradicts_plausible_hypothesis` |

Los dos joins adversariales se ejecutan realmente sobre la fixture READ_ONLY existente, no sólo sobre un resultado inventado. Otras fixtures prueban repetición sin progreso, nueva consulta tras rechazo, respuesta incompleta del modelo, límites de tokens y exclusión de cálculos no verificados del texto final.

### Luna real sobre datos sintéticos

La [corrida viva sintética r2](synthetic-live-r2.json) usa GPT-5.6 Luna Medium, sin fallback. Es un escenario dirigido de falsación; no se atribuye a una investigación espontánea sobre Calenta.

1. A partir de una observación parcial, Luna formula la hipótesis OPEN de que todas las ventas carecen de canal y elige SQL para medir el universo completo.
2. El controlador compila el test de igualdad declarado por Luna en referencias concretas: 0,30 frente a 1,00. No inventa una afirmación factual ni le entrega una solución.
3. El verificador rechaza con `hypothesis_contradicted_by_observation` y devuelve ambas observaciones.
4. Luna elige dos consultas nuevas: por canal y luego por canal/estado. Reconsidera el alcance y termina con `hypothesis_state=CONTRADICTED`.
5. Cinco afirmaciones finales quedan verificadas: 0,70 / una línea con canal, 0,30 / dos líneas sin canal y 1,00 total. La igualdad falsa no se publica.

La prosa intermedia del modelo también contiene una inversión de conteos que luego corrige. No se convierte en hecho entregado: sólo los conteos finales vinculados a sus grupos pasan la verificación. Las pruebas deterministas adicionales demuestran que ignorar el rechazo termina en PARTIAL y nunca publica la explicación falsa.

### Repeticiones reales Foundation

Las corridas mantienen publicación `foundation_afd08d9eca6a725be53cdc3f9d5709c9`, snapshot `1408`, cuatro SKU y agosto de 2026. Los vendedores, series, facturas y respuestas previas no se suministraron a Luna.

| Corrida | Resultado | Duración | Evidencia y límite |
| --- | --- | ---: | --- |
| [r1](real-r1.json) | BLOCKED | 71,20 s | Cinco lecturas; historial superó 32 KiB antes del cierre |
| [r2](real-r2.json) | BLOCKED | 96,44 s | Siete lecturas; compresión inicial todavía insuficiente |
| [r3](real-r3.json) | VERIFIED_WITH_LIMITATIONS | 103,48 s | Seis consultas; trece afirmaciones verificadas, incluyendo total y participación |
| [r4](real-r4.json) | BLOCKED | 86,29 s | Cuatro lecturas; respuesta del modelo rechazada por contrato de finalización/razonamiento |
| [r5](real-r5.json) | BLOCKED | 142,50 s | Once intentos, nueve lecturas; devolución real de rechazos, seguida de nuevas consultas; historial agotado antes de una segunda revisión final |
| [r6](real-r6.json) | VERIFIED_WITH_LIMITATIONS | 121,16 s | Ocho intentos, siete lecturas, CROSS JOIN rechazado; nueve afirmaciones finales acreditadas, incluidos 93 documentos |

No se atribuye retrospectivamente a r4 un truncamiento confirmado: el adapter antiguo no guardó metadatos de la respuesta rechazada. El adapter ahora conserva status, diagnóstico de incompletitud y uso, con regresión que demuestra el rechazo sin ejecución ni fallback.

R3 y r6 no rechazaron afirmaciones finales: acreditan investigación real y respuesta verificada, **no** revisión viva de un error sobre Calenta. R5 acredita feedback real y nuevas consultas, pero su corrección final quedó pendiente. La revisión completa y efectiva se acredita separadamente con Luna viva sobre la fixture sintética.

Las trazas conservan SQL elegido por Luna, propuestas admitidas, rechazos, filas divulgadas, hipótesis y resultados. La auditoría final reproduce 22 afirmaciones con código posterior a las últimas guardas; no se afirma que todos los experimentos vivos se ejecutaron con el último digest.

## Validaciones y recursos

Se ejecutaron checks y suites secuenciales, sin servicios nuevos ni PostgreSQL compartido escrito. Las garantías y resultados permanecen separados de los bloqueos de calidad de las corridas.

- Suite exploratoria: [233 PASS](exploratory-final-v3-tests.xml).
- Tras los ajustes finales de precisión, metadata y conservación de limitaciones al comprimir: [54 PASS focalizados](final-focused-v2-tests.xml), incluidos los paths modificados; se reutiliza la suite ampliada para los paths no alterados.
- TelchiAI V1, State Engine, autorización, contratos empresariales, rechazo de ejecución, entrega y sesión DEV: [155 PASS / 1 skip](v1-regression-tests.xml). El skip es el probe live opt-in del intérprete, no WhatsApp E2E.
- Replay final: [r3 13/13 y r6 9/9](final-audit-v4.json), sin acceso nuevo a Foundation.
- Diagnóstico histórico: catorce rechazos individualizados y catorce coincidencias monetarias/de conteo independientes.
- Gates Markdown/LAT y whitespace: ejecución conservada en `documentation-final-gates.txt`; no sustituyen garantías funcionales.

El host permaneció BUSY_BUT_SAFE bajo la excepción DEV de I/O ya autorizada: ocho cores, aproximadamente 6,5–6,9 GiB disponibles, swap alrededor de 289–290 MiB estable. I/O wait elevado, sin ampliar guards ni ocultar errores de almacenamiento; journal de kernel sin entradas disponibles, salud física del disco no certificada.

Un thread DuckDB, concurrencia uno, límite DuckDB 512 MiB, sin spill y timeout SQL 120 s; SQL por fase 900 s, muro 1.200 s, doce intentos del modelo y cinco referencias independientes con presupuesto separado explícito. R6 registró 70.272 tokens incluido el preflight, pico RSS 291.060 KiB. No hay tarifa acreditada ni costo monetario calculado.

No hay sandbox OS, límite RSS/CPU/bytes leídos del proceso ni conexión preemptible por OS acreditados. Los números de uso de r4 no incluyen su respuesta final rechazada no registrada por el adapter anterior. No se presenta un costo total completo del ensayo.

`HOST_PREFLIGHT=BUSY_BUT_SAFE`; `RESOURCE_GUARD=PASS` en alcance observado; `CONCURRENCY_USED=1`; `UNRELATED_PROCESSES_TERMINATED=0`; `ENVIRONMENTAL_ABORTS=0`; `OWN_PROCESSES_LEFT_RUNNING=0`. Comandos síncronos terminaron y los executors cerraron sus hilos/conexiones. El proceso uv preexistente PID 11499, iniciado a las 09:59, quedó intacto.

## C. Gates

Los PASS se limitan a la garantía descrita. El resultado total continúa PARTIAL, no se promueve Foundation ni se autoriza implícitamente otra superficie.

| Gate | Estado | Evidencia / alcance |
| --- | --- | --- |
| CLAIM_EVIDENCE_BINDING | PASS | IDs emitidos por servidor y reconstrucción independiente; 22 afirmaciones reales en replay final |
| ALIAS_IDENTITY_VALIDATION | PASS | Identidad por expresión/procedencia, no alias; fixtures de suplantación y aliases nuevos |
| SOURCE_VS_DERIVED_SEMANTICS | PASS | CASE/COALESCE diferenciados; oficialidad no inferida; fixtures adversariales |
| HYPOTHESIS_CONTRADICTION_DETECTION | PASS | Desigualdad posterior 0,30 frente a 1,00 y rechazo estructurado |
| LUNA_HYPOTHESIS_REVISION | PASS | Sintético vivo r2: SQL nuevo elegido por Luna y descarte explícito; no extrapolar a revisión completa en Calenta |
| REAL_FOUNDATION_RESEARCH | PASS | R6: SQL Luna, publicación/snapshot fijados, siete lecturas READ_ONLY y un rechazo |
| CALENTA_RECONCILIATION | PASS | Total, subconjunto, porcentaje, 93 documentos y 154 líneas; referencias r3/r6 y reconstrucción final |
| INDEPENDENT_CLAIM_VERIFICATION | PARTIAL | Fuerte para medidas/grupos admitidos; no lineage semántico completo de CTE/subconsultas/joins ni verificación causal positiva |
| UNSUPPORTED_CAUSAL_CLAIM_REJECTION | PASS | Rechazo de mecanismo/regla no acreditados y exclusión de narrativa libre de los hechos |
| SECURITY_REGRESSION | PASS | 233 tests y focalizados finales; ejecutor/validador/guards originales preservados; no acredita sandbox OS |
| TELCHIAI_V1_REGRESSION | PASS | 155 tests, un skip live explícito; sin cambios al State Engine/capabilities |
| WHATSAPP_UNCHANGED | PASS | Sin edición, activación, mensajes, webhooks ni cambios en transportes por esta tarea |
| READY_FOR_WEB_INTEGRATION | PARTIAL | Núcleo invocable localmente, pero contexto aún UID supervisado y universo sellado; faltan contrato interno autenticable y cierre semántico |
| READY_FOR_BLIND_COMPARISON | BLOCKED | Sin integración Web ni freeze; pregunta inédita no elegida ni ejecutada |

## Preparación Web, sin implementación

La inspección actual distingue el adapter DEV existente del investigador. No se implementó un endpoint Web, login nuevo, streaming, persistencia nueva ni otro backend.

El punto visual sigue en `astro/src/components/telchiai/TelchiAIHome.svelte`, función `submitQuery`: usa timers, no fetch del investigador. `assistant/composition.py` compone `TelchiHandler` sin investigador; `handler.py` limita turnos a 80 s y mantiene transacción durante el procesamiento, frente a 121 s observados en r6.

`assistant/dev_runtime_http.py::_human_subject` ya reutiliza opcionalmente la verificación de sesión Console y vincula el sujeto al teléfono del piloto. Su `/turn` también exige token DEV y crea un mensaje WhatsApp lógico con teléfono configurado. Esto **no** es todavía una entrada Web genérica autorizada para el investigador; no debe exponerse el token ni reutilizarse un teléfono fijo como identidad empresarial Web.

Contrato interno mínimo propuesto: pregunta + contexto de autorización derivado por servidor + scope empresarial + Foundation fijada + presupuesto restante + cancelación + callback de eventos. Salida: estado, hechos verificados con referencias, hipótesis diferenciadas, limitaciones, presupuesto consumido y auditoría. Ningún permiso, snapshot o scope se acepta como autoridad desde Luna o desde el navegador.

Siguiente alcance mínimo, después de cerrar el gate interno:

1. Separar composición local UID del contexto empresarial autenticado, reutilizando Console y permisos efectivos; no ampliar aquí `authorize` ni el catálogo sellado.
2. Completar o delimitar explícitamente la cobertura semántica del servicio, incluyendo lineage de consultas admitidas necesarias; evitar que la falta de acreditación se confunda con fallo SQL.
3. Inyectar esa misma operación en el servicio Telchi/Srv05 existente, sin transacciones/locks largos ni reiniciar presupuestos; preservar State Engine y rutas WhatsApp.
4. Añadir entrada Web con identidad Console real, aislamiento de tenant/workspace, cancelación y eventos de progreso genuinos. Reutilizar las autoridades y repositorios existentes para resultado/auditoría, con autorización futura explícita para sus escrituras.
5. Conectar la UI a progreso y resultado verificados, sin mostrar la prosa audit-only como hechos. Ejecutar gate autenticado antes de congelar una comparación ciega.

Los paths Console/auth, composición compartida y eventual montaje de rutas requieren coordinar el ownership correspondiente en esa etapa. No fueron editados en esta ejecución.

## Archivos y alcance

Los cambios propios se limitan a `SrvRestAstroLS_v1/backend/modules/telchi/exploratory_sql/` y este directorio nuevo de evidencia. Los untracked anteriores no se consideran creados íntegramente por esta tarea.

- Modificados existentes: `contracts.py`, `adaptive_research.py`, `research.py`, `test_adaptive_research.py`.
- Nuevos: `claim_evidence.py`, `diagnose_claims.py`, `audit_claims.py`, `live_claim_revision.py`, `test_claim_evidence.py`, `test_claim_revision.py`, `test_claim_model_budget.py`.
- Evidencia nueva: diagnóstico, seis intentos reales, dos sintéticos vivos, auditorías por versión y JUnit. Los intentos fallidos se conservan; no se reemplazan por la mejor corrida.

El blast radius de once archivos queda justificado por separar contratos, verificación, bucle, adapter LLM, fixtures adversariales y harnesses de auditoría/reproducción. No se editó el validador SQL, executor, FoundationReader, controles globales, Foundation, SAP, PostgreSQL, Console, Web, WhatsApp, infraestructura o dependencias.

No hubo commit, push, cambio de rama ni operaciones de índice. Se preservaron los cambios concurrentes presentes en el worktree. No se rotaron credenciales ni se amplió el egreso más allá de las pruebas DEV autorizadas.

## D. Decisión

La evidencia permite contestar concretamente sin convertir una garantía acotada en una aprobación universal del producto.

1. **Sí**, Luna puede investigar libremente dentro del SQL, fuentes y presupuestos admitidos; las consultas reales son propias.
2. **Sí, en el contrato estructurado acreditado**: se detectan números mal atribuidos, clasificaciones calculadas como oficiales, scopes incompatibles y causalidad no acreditada. No se certifica comprensión semántica arbitraria de prosa libre ni causas positivas.
3. **Sí**, hay revisión efectiva con Luna real en el escenario sintético: recibe contradicción, consulta de nuevo y descarta la hipótesis inicial. La revisión completa de una afirmación errónea sobre Calenta sigue PARTIAL.
4. **Sí**, puede entregar los importes y poblaciones correctos y reconocer que no ha demostrado la causa.
5. **Todavía no como servicio genérico plenamente acreditado para Web**. El núcleo mejora sustancialmente, pero quedan cobertura semántica y composición de contexto autenticable; no se declara PASS global ni se congela el benchmark.

## Reproducción

Los comandos de modelo vivo tienen coste y requieren preflight/guard y autorización DEV vigente. Usar siempre un nombre de salida nuevo; los artefactos existentes no se sobrescriben.

Desde `SrvRestAstroLS_v1/backend`:

```bash
uv run --no-sync pytest modules/telchi/exploratory_sql -q
uv run --no-sync python -m modules.telchi.exploratory_sql.diagnose_claims ../../data/reports/telchi/adaptive-business-research-v1/real-r7.json
uv run --no-sync python -m modules.telchi.exploratory_sql.audit_claims --output NEW-AUDIT.json ../../data/reports/telchi/analytical-claim-verification-v1/real-r3.json ../../data/reports/telchi/analytical-claim-verification-v1/real-r6.json
uv run --no-sync python -m modules.telchi.exploratory_sql.live_claim_revision --output NEW-SYNTHETIC.json
uv run --no-sync python -m modules.telchi.exploratory_sql.adaptive_research --authorize-dev-io-exception --output NEW-REAL.json
```
