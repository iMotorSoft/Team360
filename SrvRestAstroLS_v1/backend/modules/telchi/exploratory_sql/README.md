# Exploratory SQL — pilotos read-only DEV

Los pilotos locales no acreditan un servicio multiusuario ni habilitan WhatsApp/Web. Se conservan los cierres históricos sin convertir sus límites en garantías actuales.

## Consulta empresarial directa DEV

La [guía Direct Ask](DIRECT_ASK.md) describe el runner conversacional local, el catálogo sin filtro fijo de SKU/período, la verificación conservadora y los límites de identidad y recursos. No habilita Web ni WhatsApp.

## Investigación adaptativa DEV V1

El [cierre adaptativo](../../../../../data/reports/telchi/adaptive-business-research-v1/report.md) es **PARTIAL**: SQL real guiado por observaciones, conciliación independiente y límites semánticos pendientes. No hay causa raíz acreditada ni comparación ciega ejecutada.

- `adaptive_research.py` reutiliza Luna Medium, validación estructural, FoundationReader y la excepción DEV existente; no impone dos o tres consultas ni una ruta empresarial.
- `adaptive_sources.py` proyecta el mismo universo fijado de cuatro SKU/agosto de 2026, dimensiones documentales separadas y referencia de vendedores. No crea datasets físicos ni modifica Foundation.
- `adaptive_verifier.py` reconstruye filas y particiones con Decimal; relaciones nuevas siguen INVESTIGATIVE. Las afirmaciones con aliases no canónicos permanecen UNVERIFIED, sin normalización silenciosa.
- La [auditoría](../../../../../data/reports/telchi/adaptive-business-research-v1/audit.json) conserva diferencias, intentos, costes no disponibles, controles independientes y equivalencia de las observaciones con la guarda final de muestras.
- El modo sigue siendo CLI supervisado local: no usa el State Engine conversacional ni autentica usuarios Console. El enlace Web requiere trabajo autorizado posterior; WhatsApp permanece intacto.

## Alcance histórico sintético

El texto siguiente describe el piloto sintético anterior. Su afirmación de Foundation bloqueada pertenece a ese runner, no sustituye los experimentos Foundation DEV posteriores.

## Piloto simplificado autorizado

`TELCHIAI_EXPLORATORY_SQL_DIRECT_READONLY_V1` añade una ruta DEV explícita sin cambiar el ejecutor histórico, el validador, los contratos, V1 ni sus controles. No instala dependencias o servicios.

- `direct_readonly.py`: crea únicamente una fixture privada temporal; la reabre con `read_only=True`, external access/autoload/autoinstall desactivados, memoria DuckDB acotada, un thread y sin spill. Revalida cada propuesta y sólo ejecuta SQL regenerado y parámetros del validador existente.
- `research.py`: runner local; transiciones determinísticas PLAN/VALIDATE/EXECUTE/OBSERVE/VERIFY, máximo siete llamadas al modelo, cinco consultas, diez segundos acumulados de SQL y 180 segundos de investigación. No modifica ni conecta el State Engine conversacional V1.
- `test_direct_readonly.py`: ejecución DuckDB real con ficción, denegaciones previas a abrir la base, read-only, permisos, contexto, límites, deadline, protocolo Responses y fanout Bs 100 → Bs 500 rechazado.
- Modelo/proveedor/parámetros conservados: `gpt-5.6-luna`, medium, OpenAI Responses directo, credential env existente, store=false, 4096 output tokens, sin redirects/fallback. La primera llamada verificada precede a toda ejecución. No usa PostgreSQL, Milvus o LiteLLM; no son dependencias de este runner.
- El lock local por UID serializa invocaciones CLI; un lock del proceso serializa consultas. No equivale a control distribuido multiusuario. Las observaciones, catálogo e historia enviados al modelo no superan 32 KiB.
- Timeout mediante interrupt supervisado y deadline comprobado al terminar; no es preemption OS. Memoria DuckDB no limita RSS. CPU, memoria de proceso, bytes escaneados, aislamiento OS y confinamiento ante una vulnerabilidad del motor permanecen sin acreditar.

La ejecución genérica y la respuesta empresarial permanecen UNVERIFIED. Sólo la afirmación sintética explícitamente scoped de total global de cabeceras se contrasta con Decimal independiente. Ninguna etiqueta escrita por Luna eleva el estado del controlador.

## Evidencia y límites del piloto

La evidencia distingue éxitos funcionales de fallos del protocolo y del gate de datos reales. No se omiten intentos anteriores ni se transforma el aislamiento histórico en PASS.

[Conversación final reproducible](../../../../../data/reports/telchi/exploratory-sql-direct-readonly-v1/synthetic-luna-final-r3.json): dos consultas distintas generadas por Luna, observación y segunda consulta motivada por resultados, total declarado contrastado y respuesta final. Los JSON contienen SQL propuesto/regenerado, decisiones, filas ficticias, verificación, metadatos y recursos.

Los intentos r1–r5 detectaron concatenación de mensajes Responses, duplicados y commentary. Se selecciona sólo `final_answer` (o formato legacy sin phase), se admiten finales idénticos repetidos y se rechazan finales diferentes. La regresión cubre las tres situaciones. r6 completó el ciclo antes del hardening final.

`synthetic-luna-final.json` quedó vacío por un fallo funcional al convertir una afirmación no numérica a Decimal; se conserva como artefacto abortado. El fix mantiene esas afirmaciones UNVERIFIED sin abortar la auditoría, con regresiones para texto, null y NaN. `synthetic-luna-final-r2.json` bloqueó correctamente un JSON con clave duplicada. No se relajó el parser para aceptarlo.

Foundation no fue abierta. El reader canónico existente fija publicación/snapshot, pero el validador sigue sellado al catálogo sintético. **El binding autorizado Foundation → catálogo/lector no está implementado**: requiere composición de identidad/RBAC y proyección de fuentes, no reutilizar permisos de fixture. Tampoco se acreditó destino/alcance empresarial de OpenAI para datos reales; la presión sostenida de I/O desaconsejó scans. `foundation_gate()` es un bloqueo explícito sin I/O, no una inspección dinámica ni un conector completado.

Calenta agosto 2026, reconciliación, exportación de datos reales y canales: NOT_RUN. No se enviaron filas empresariales al modelo, no se tocó CURRENT, SAP, PostgreSQL, permisos, servicios o WhatsApp/Web.

## Reproducción y pregunta reservada

Ejecutar desde backend con la credencial ya autorizada en el entorno; no copiarla a código, argumentos o evidencia. El output debe ser nuevo y el runner no sobrescribe evidencia.

```bash
uv run --no-sync python -m modules.telchi.exploratory_sql.research --output ../../data/reports/telchi/exploratory-sql-direct-readonly-v1/nueva-corrida.json
uv run --no-sync pytest modules/telchi/exploratory_sql/test_direct_readonly.py -q
```

`--question-file PATH` permite recibir posteriormente la pregunta de Mario **sobre el catálogo sintético actualmente habilitado**. El runner registra el digest de todos los `.py` locales; congelarlo antes de la prueba reservada. No se inventó esa pregunta. No ofrece aún una pregunta reservada sobre Foundation.

Antes de integración WhatsApp/Web: cerrar autorización empresarial de egress, implementar binding Foundation autenticado/pinned con negativos entre tenants y permisos, verificar límites y cardinalidades reales, completar Calenta y ampliar verificación empresarial. Después acreditar integración durable/cancelación sin locks PG prolongados y gates de canal propios. El piloto no autoriza tocar los handlers.

## Histórico F0/F1 preservado

El texto siguiente describe exclusivamente la entrega anterior y sus gates de aislamiento, no el estado habilitado por el piloto DEV nuevo. `F1_EXECUTION_ISOLATION_FAIL` sigue sin acreditación.

Prototipo histórico interno opt-in, exclusivamente sintético. F0 implementado; F1 parcial y bloqueado por aislamiento. No era un ejecutor habilitado ni estaba listo para Foundation.

## Autoridad y frontera

El contexto es TELCHI / VENTAS y TRAZABILIDAD_DOCUMENTAL / DEVELOPMENT. [CONTEXT](../CONTEXT.md) permanece canónico. Los cambios preexistentes del worktree no pertenecen a esta entrega.

Identificador: `TELCHIAI_EXPLORATORY_SQL_EXECUTOR_V1`. Rama inspeccionada: `feature/console-backend-core`; HEAD: `09d2ec715a31bb88574d734eacb9f437f008624e`.

No se cambia el intérprete V1: `gpt-5.6-luna`, medium, OpenAI Responses y State Engine determinístico permanecen intactos. No hay imports desde V1, registro de herramientas, endpoint, listener, scheduler ni integración WhatsApp/Web.

`FEATURE_ENABLED_DEFAULT=False`; `ExploratoryExecutor(enabled=True)` es opt-in local, pero **también queda bloqueado**. Ninguna variable de entorno, resultado del probe ni SQL validado habilita ejecución.

## Arquitectura implementada

La propuesta no confiable entra a un validador estructural; la ejecución no cruza la frontera porque falta un sandbox acreditado. Las interfaces conservan el flujo futuro sin crear otro framework de agentes.

- `contracts.py`: contratos congelados y versionados `telchiai.exploratory_sql.v1`; propuesta, contexto autorizado, consulta validada, resultado, decisión y puertos de ejecución/verificación.
- `synthetic.py`: catálogo lógico sellado, permisos de fixture, columnas/tipos, grano, máximos de filas, restricciones semánticas y relaciones conocidas. No contiene rutas ni credenciales.
- `validator.py`: parser nativo DuckDB → visitante positivo completo del subconjunto → SQL regenerado y literales parametrizados → hash vinculado a contexto, parámetros, relaciones, presupuesto y grano.
- `executor.py`: frontera fail-closed, probe de namespaces y contabilidad local de presupuestos. No contiene un worker SQL ni una vía de ejecución alternativa.
- `verifier.py`: cálculos independientes con Decimal, perfilado de relaciones y bloqueo de afirmaciones sin acreditación.
- `evidence.py`: reproducción offline sin inferencia ni servicios; diferencia expresamente perfiles Python de resultados SQL.

`PLAN → VALIDATE → EXECUTE → OBSERVE → VERIFY → REPLAN` se detiene en EXECUTE. `ExecutionPort` y `VerificationPort` son interfaces mínimas, no un loop operativo ni un State Engine paralelo.

El contexto autorizado sólo lo construye composición confiable. F1 acepta únicamente el catálogo sintético sellado y organización/workspace/publicación/snapshot exactos. El permiso de fixture **no se registra ni asigna en Console**. No se admite autoridad desde campos libres de la propuesta.

## Inspección previa

La inspección fue read-only: dependencias, reader, autorización actual, recursos y namespaces. No se cargó DuckLake ni se abrió ninguna publicación real.

- DuckDB instalado y lock: `1.5.5`; parser nativo JSON disponible. El visitante fija esa versión y bloquea versiones no acreditadas.
- DuckLake instalado: versión de extensión `d8a1881e`, `loaded=False`, observado mediante `duckdb_extensions()` en conexión efímera. Compatibilidad con ejecución exploratoria NO acreditada.
- `sqlglot`, `sqlparse` y bindings Python seccomp ausentes. No se instaló ninguna dependencia ni se cambió pyproject/lock.
- FoundationReader fija publicación y snapshot coherentes; no sustituye identidad/RBAC. La autorización V1 vive en el handler y revalida permisos efectivos Console. No se importan ni modifican esos componentes aquí.
- Límites actuales V1: intérprete 45 s, lectura Foundation 30 s, turno 80 s; no se reutilizan sus procesos como sandbox. El guard existente se usa sólo para preflight de evidencia, sin tocar DATA_ROOT.
- Host: 8 CPU, aproximadamente 7–8 GiB disponibles, swap 0, load cercano a 1; I/O wait sostenido observado de 45–62 %. `BUSY_BUT_SAFE` únicamente para estos tests diminutos secuenciales; sin scans, browsers ni suites globales.

## SQL admitido y rechazado

ALLOW significa admisión estructural del subconjunto, no ejecución autorizada, corrección empresarial ni binder semántico completo. Las construcciones desconocidas se rechazan explícitamente.

Admite un SELECT sobre fuentes lógicas autorizadas; columnas explícitas, filtros, AND/OR, comparaciones, BETWEEN, IN de escalares, nulos, CASE, COALESCE, aritmética, DISTINCT simple, GROUP BY, HAVING, ORDER BY y LIMIT entero acotado.

Funciones: count/count_star, sum, min, max, avg, abs, round de un argumento, lower, upper y length. No admite funciones calificadas, filtros internos, orden interno ni funciones externas. Parámetros: INTEGER, VARCHAR, BOOLEAN y DECIMAL(18,2); literales SQL admitidos INTEGER/VARCHAR/BOOLEAN/NULL.

CTE no recursivas y subconsultas en FROM con alias están admitidas. Joins INNER/LEFT requieren igualdad obligatoria entre columnas de ambos lados, relación conocida o candidata declarada y presupuesto conservador del producto de máximos de filas. Una candidata no se convierte automáticamente en acreditada. Relaciones derivadas sin linaje suficiente quedan INSUFFICIENT.

Rechaza DDL/DML/COPY/ATTACH/DETACH/PRAGMA/SET/INSTALL/LOAD/CALL, múltiples statements, fuentes físicas o calificadas, table functions, archivos/red, catálogos de sistema, extensiones, funciones desconocidas y operaciones escondidas en CTE/expresiones/subconsultas.

También rechaza stars salvo count(*), windows, UNION/set operations, recursión, correlación, subconsultas escalares/EXISTS/IN-subquery, CAST solicitado por el modelo, lambdas/listas, sampling, time travel, OFFSET, GROUPING SETS, USING/NATURAL/CROSS JOIN, joins sin igualdad obligatoria y aliases fuera del subconjunto ASCII documentado en código.

Cada nodo admitido verifica exactamente sus campos y visita sus hijos. El SQL original sólo llega como **dato** al comando confiable `SELECT json_serialize_sql(?)`; nunca se ejecuta, explica ni bindea. El SQL regenerado no interpola literales del modelo. Los errores públicos son códigos fijos, sin diagnósticos del motor.

Límite pendiente: resolución de columnas/linaje y sintaxis no constituye inferencia completa de tipos, legalidad de agrupaciones ni equivalencia semántica de expresiones. El futuro worker deberá rechazar errores de binding sin revelar información. La versión actual no ejecuta ni siquiera el SQL regenerado.

## Aislamiento y recursos

El probe real falla; no se intentaron privilegios elevados, permisos nuevos ni flags alternativos para eludir la restricción. Esto bloquea F1, no demuestra un defecto funcional SQL.

La invocación de `/usr/bin/bwrap --unshare-all ... /usr/bin/true` falla al configurar loopback: `Failed RTM_NEWADDR: Operation not permitted`. El probe reproducible limpia el entorno a PATH/LANG, cierra FDs y sólo ejecuta `true`, sin SQL ni mounts de datos.

El probe NO es un sandbox acreditado: monta `/usr` para el binario de prueba, no constituye el diseño final de filesystem mínimo. Aun si devuelve éxito en otro host, el ejecutor sigue retornando `RESOURCE_BLOCKED/execution_isolation_not_accredited`.

Presupuestos configurables con techos conservadores: consulta 2 s, investigación 10 s, CPU 1 s, memoria de proceso 512 MiB, 1 thread, 100 filas, 64 KiB resultado, 64 KiB fuente, 5 consultas, concurrencia 1 y 10.000 pares de join. El presupuesto efectivo es la intersección del autorizado y el solicitado.

Demostrado: rechazo por tamaño SQL/profundidad AST/producto de joins, parámetros, intersección de presupuestos, contabilidad local de tiempo/cantidad/concurrencia y cancelación **antes** de ejecutar.

**No demostrado ni implementado como control OS:** memoria total, CPU, threads, bytes leídos, resultado materializado acotado, timeout y cancelación durante ejecución, filesystem/red y limpieza de un worker SQL. `bytes_read`, CPU y memoria consumida quedan null; no se confunde memory_limit de DuckDB con límite del proceso ni estimación con enforcement.

No se lanza ningún worker SQL. No hubo servicios propios temporales; los probes de `true` finalizaron bajo subprocess.run. No se terminaron procesos ajenos.

## Pruebas adversariales y regresiones

Las pruebas offline pasan, pero el gate adversarial completo de F1 permanece FAIL por ausencia de pruebas dentro de un sandbox operativo. No se transforma ese bloqueo en PASS.

`test_exploratory_sql.py`: 116 PASS. Cubre contratos, autoridad, permisos, resolución, CTE/subquery, funciones, parámetros/inyección, hash, AST desconocido, joins explosivos, propuestas válidas y ataques de lectura/escritura, red/archivos, otro tenant, configuración, extensiones y errores.

Los negativos espían cada comando DuckDB y prohíben cualquier lanzamiento de procesos. Sólo permiten la llamada al parser con SQL como dato, comprueban NOT_EXECUTED, fixtures sin cambios y canary intacto. Esto prueba no ejecución previa al rechazo; **no prueba confinamiento de un worker que ejecute SQL**.

Regresión focalizada V1: 103 PASS / 1 skip en test_assistant, test_safety, test_rejected_execution_guard, test_whatsapp_operational_contract y test_delivery_reliability_v1. El skip exige `TEAM360_LIVE_LUNA=1` para una sonda viva; no se ejecutó. No acredita entrega WhatsApp ni reacredita gates operacionales.

Desde backend, sin sincronizar ni instalar dependencias:

```bash
uv run --no-sync pytest modules/telchi/exploratory_sql/test_exploratory_sql.py -q
uv run --no-sync pytest modules/telchi/assistant/tests/test_assistant.py modules/telchi/assistant/tests/test_safety.py modules/telchi/assistant/tests/test_rejected_execution_guard.py modules/telchi/assistant/tests/test_whatsapp_operational_contract.py modules/telchi/assistant/tests/test_delivery_reliability_v1.py -q -rs
uv run --no-sync python -m modules.telchi.exploratory_sql.evidence --output ../../data/reports/telchi/exploratory-sql-executor-v1/evidence-new.json
```

El comando de evidencia exige archivo nuevo; no pisa reportes existentes. [Evidencia de esta entrega](../../../../../data/reports/telchi/exploratory-sql-executor-v1/evidence.json) y [JUnit de la corrida conjunta](../../../../../data/reports/telchi/exploratory-sql-executor-v1/tests.xml): 219 PASS / 1 skip. Los cinco gates LAT y git diff --check pasaron; LAT advierte configuración init/key ausente, sin impedir estos checks.

## Ejemplo investigador y verificador

No existe conversación Luna acreditada en esta entrega. La ejecución segura está bloqueada, por lo que no se fabricó una observación SQL ni se devolvieron perfiles Python al modelo como si fueran resultados del ejecutor.

El hold-out relacional, escrito después del visitante, agrupa movimientos por factura con min/max hora/count; une vendedores y facturas, selecciona canales nulos y calcula amplitud horaria. Está admitido y regenerado en evidencia, pero **NOT_EXECUTED**. Es SQL humano de prueba, no generación Luna.

Los datos sintéticos tienen facturas, líneas, productos, vendedores, canales, series y movimientos; incluyen canal nulo, cinco movimientos para una factura, clave documental/hora potencialmente duplicada, distintas horas, un huérfano, una clave nula y una factura sin movimiento. Cabeceras y líneas difieren deliberadamente.

El perfil independiente de fixtures detecta ONE_TO_MANY, 6 pares, 7 filas en LEFT JOIN, cobertura 2/3, huérfano y clave nula. La suma de cabeceras pasa de 200,00 a 600,00 en ese LEFT JOIN; no es nueva facturación. En INNER JOIN la suma incorrecta es 580,00.

Caso obligatorio: factura 1 vale 100,00 y tiene cinco movimientos; la afirmación 500,00 es REJECTED por suma Decimal independiente. El visitante admite técnicamente el join propuesto, pero el verificador marca riesgo de multiplicación y mantiene UNVERIFIED. Luna no puede omitir verificaciones ni acreditar una relación unilateralmente.

Interfaces implementadas: sumas Decimal, conteos, porcentajes, particiones disjuntas/completas, duplicados/cardinalidad/cobertura, integridad, procedencia y grano. Toda afirmación conserva evidencia/estado. El verificador genérico permanece UNVERIFIED: falta evidencia autenticada de ejecución y equivalencia entre alcance SQL y referencia independiente. No certifica arbitrariamente conclusiones empresariales.

## Estados finales

Los PASS siguientes tienen sólo el alcance offline descrito; el bloqueo de entorno impide cerrar F1. READY permanece NO aunque todos los tests unitarios pasen.

```text
F0_CONTRACTS_PASS
F1_SQL_VALIDATOR_PASS
F1_EXECUTION_ISOLATION_FAIL (RESOURCE_BLOCKED)
F1_SECURITY_NEGATIVE_TESTS_FAIL (gate OS incompleto; negativos offline PASS)
F1_SYNTHETIC_RESEARCH_FAIL (sin ejecución aislada ni ciclo Luna)
F1_VERIFIER_PASS (referencias sintéticas e interfaz fail-closed)
WHATSAPP_V1_REGRESSION_PASS (offline; entrega real NOT_RUN)
F1_SAFE_EXECUTOR_FAIL
READY_FOR_FOUNDATION_RESEARCH=NO
```

## Archivos y alcance

Toda implementación nueva vive en este subdirectorio del módulo existente. No se modificó ningún archivo preexistente ni estado GLOBAL, configuración, permisos, dependencia, reader o intérprete.

Archivos nuevos: `__init__.py`, `contracts.py`, `synthetic.py`, `validator.py`, `executor.py`, `verifier.py`, `test_exploratory_sql.py`, `evidence.py` y este `README.md`. Evidencia nueva: `data/reports/telchi/exploratory-sql-executor-v1/evidence.json` y `data/reports/telchi/exploratory-sql-executor-v1/tests.xml`.

## Riesgos y siguiente fase

Antes de Foundation debe completarse F1 en un entorno con aislamiento autorizado y demostrable. Esta entrega se detiene sin conexión real ni activación operacional.

Primero resolver con el owner el bloqueo de namespaces, sin cambiar permisos desde este prototipo. Implementar un worker propio con root mínimo, entorno sin secretos, red inaccesible, sin mounts empresariales, únicamente payload sintético sellado, límites OS de memoria/CPU/procesos y supervisión con deadline/cancelación y cleanup. Acreditar ataques reales, timeout, cancelación en curso y ausencia de remanentes. Repetir el ciclo sintético con Luna Medium y trazabilidad real.

Después, sólo con nueva autorización, diseñar el adapter de una publicación Foundation explícitamente autorizada y pinned: identidad/RBAC revalidados por Team360, manifest y snapshot fijados vía FoundationReader, proyección de fuentes/columnas por scope y materialización/export read-only mínima para el worker. Nunca pasar conexión PG, credenciales o acceso directo al catálogo físico al modelo o sandbox.

DuckLake puede requerir red/credenciales para metadata y no debe montarse ingenuamente dentro del sandbox. Quedan pendientes compatibilidad de tipos/extensiones, integridad del snapshot/export, límite exigible de lectura y presupuesto de scans, verificación independiente por grano y trazabilidad. Ninguna consulta exploratoria sobre Foundation real está autorizada por este código.
