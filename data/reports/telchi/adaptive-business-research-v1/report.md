# TelchiAI Adaptive Business Research V1

Cierre **PARTIAL** en `feature/console-backend-core`, TELCHI / VENTAS y TRAZABILIDAD_DOCUMENTAL / DEVELOPMENT. Investigación DEV local; sin promoción, comparación sorpresa ni congelación del sistema.

## Resultado empresarial verificable

El verificador reconstruyó las líneas y cabeceras independientemente del SQL de Luna. El universo son únicamente L02822, L02823, L03658 y L03649, agosto de 2026: no toda la marca Calenta.

| Canal materializado | Estado publicado | Importe BS | Documentos únicos | Líneas |
| --- | --- | ---: | ---: | ---: |
| HORIZONTAL | CONFIRMED | 85.379,31 | 371 | 543 |
| SALON | SUPPORTED, no CONFIRMED | 47.681,37 | 797 | 837 |
| Sin código ni estado | NULL | 47.340,13 | 93 | 154 |
| Total | Universo fijado | 180.400,81 | 1.261 | 1.534 |

Sin canal: **26,24 % del importe**, no pérdida demostrada de ventas ni una categoría comercial nueva. Grupos disjuntos por canal y suma exacta al total; las cuentas documentales por SKU/almacén pueden solaparse y no deben sumarse como documentos únicos.

Son importes comerciales de líneas BS, antes de notas de crédito y ajustes globales; no facturación neta, cobros ni DocTotal de cabecera. La clasificación es la publicada, no una clasificación histórica certificada. Ver extremos del mes no acredita integridad mensual.

**No se acreditó la causa raíz.** La asociación con series, almacenes o vendedores no demuestra captura incorrecta ni habilita reclasificar el canal. La recomendación empresarial segura es revisar la regla y los documentos afectados sin sustituir una dimensión por otra.

## Traza real y calidad investigadora

La [corrida r7](real-r7.json) conserva pregunta, prompt, catálogo, propuestas, SQL autorizado/parametrizado, observaciones, hipótesis, interpretaciones, decisiones, resultados y cierre raw. La [auditoría](audit.json) añade comprobaciones independientes.

| Paso r7 | Decisión de Luna y evidencia observada | Evaluación independiente |
| --- | --- | --- |
| 1 | Medir canal/estado/moneda, importes y documentos; descubre 154 líneas / 93 documentos sin canal | Nueve cifras reconstruidas; total y particiones exactos |
| 2 | Profundiza el grupo nulo por SKU: afecta las cuatro referencias | Doce cifras reconstruidas; no es exclusivo de un producto |
| 3 | Investiga vendedor/serie/almacén/SKU; observa concentración y una muestra agregada truncada | 118 valores del resultado completo contrastados; Luna sólo recibe hasta 30 grupos, con truncación explícita |
| 4 | Reexpresa grupos con COALESCE; confirma los importes | Nueve cifras contrastadas; no es una verificación independiente por repetir SQL |
| 5 | Filtra la fuente por `UNCLASSIFIED`, etiqueta creada por COALESCE en el paso anterior | Cero filas correcto para ese predicado incorrecto: la fuente contiene NULL. No es anomalía de Foundation |
| 6 | Propone unir vendedores para contrastar categoría con canal | Rechazado por `join_pair_budget` antes de ejecución. No se eleva el presupuesto ni se ejecuta otra ruta |
| Cierre | Resume resultados previos y admite que no acredita la causa | Sólo resumen terminal tras el rechazo; ninguna consulta posterior permitida |

Se demuestra elección de SQL y profundización dependiente de observaciones, no sólo producción de varios SQL. **No** se demuestra revisión completa de hipótesis: los estados de investigación permanecieron OPEN y Luna no corrigió el filtro de presentación frente a fuente.

La relación propuesta `sales_operation.slp_code → salesperson.slp_code` fue perfilada independientemente: 1.534/1.534 filas cubiertas, 64 claves derechas únicas, sin nulos, huérfanos ni multiplicación. Es validación técnica; su significado comercial permanece INVESTIGATIVE y no convierte categoría de vendedor en canal.

El verificador runtime dejó **2 afirmaciones VERIFIED y 14 UNVERIFIED** por filtros con aliases (`channel_status`, `channel_code`, `currency_code`) en vez de campos canónicos. La evaluación posterior resolvió explícitamente esos aliases desde los SQL y contrastó las 16 cifras. No modifica el resultado PARTIAL del runtime ni certifica su narrativa.

## Evidencia técnica y rendimiento

Publicación `foundation_afd08d9eca6a725be53cdc3f9d5709c9`, snapshot `1408`. Sólo `gpt-5.6-luna`, reasoning medium, Responses directo, store=false y sin fallback. Preflight real mínimo del modelo antes de leer Foundation.

- R7: cinco consultas completadas y una rechazada; cinco consultas privadas de referencia, no enviadas a Luna. Siete llamadas de investigación más una de preflight.
- Duración r7: 97,23 s; primer resultado útil: 27,61 s, incluyendo preflight y construcción independiente de referencia.
- Tokens r7: 26.230 input / 5.446 output / 31.676 total, incluido preflight. Coste monetario no disponible: no se inventó una tarifa.
- Pico RSS del proceso: 300.564 KiB. Un thread DuckDB, una consulta a la vez, memory_limit 512 MiB, sin spill, timeout SQL 120 s, máximo 12 consultas del modelo y cinco de referencia, techo SQL 900 s por fase y muro de investigación 1.200 s.
- FoundationReader fija publicación/snapshot y verifica catálogo adjunto READ_ONLY. Las únicas vistas nuevas son temporales. No se exportan datasets físicos.
- Se preservan límites: no sandbox OS, no límite RSS/CPU/bytes escaneados del proceso y establecimiento de conexión no preemptible por OS. No se desarrolló infraestructura de aislamiento.
- La excepción DEV sólo permite I/O-wait elevado con guard de memoria/swap y cancelación; no modifica guards globales. Journal accesible sin errores; logs completos del kernel no disponibles, salud del dispositivo no certificada.
- HOST_PREFLIGHT=BUSY_BUT_SAFE bajo excepción I/O explícita; memoria disponible aproximadamente 6,6–7,0 GiB y swap estable alrededor de 286 MiB. Sin servicios reiniciados ni procesos ajenos terminados; PIDs propios de las siete corridas comprobados ausentes al cierre.

El digest de arranque de r7 y el digest final están en `audit.json`. Durante la corrida se endureció únicamente la detección de muestras documentales en CTE/aliases y sus fixtures. Todas las observaciones reales fueron reproducidas idénticamente bajo la guarda final; no se afirma una corrida viva exacta del último digest.

## Errores y correcciones preservados

Todos los intentos permanecen separados e inmutables. No se sustituyen oráculos ni se presenta la mejor corrida como un éxito universal.

| Intento | Resultado y motivo |
| --- | --- |
| [r1](real-r1.json) | PARTIAL. Defecto nuevo de proyección: referencia usa SAP_HANA/source_native_id, no el namespace de facturas. Vendedores vacíos; corregido con fixture DuckDB |
| [r2](real-r2.json) | PARTIAL. Binding de vendedores corregido; Luna finaliza sin emitir SQL ejecutable |
| [r3](real-r3.json) | PARTIAL. Aclaración genérica no basta; mensajes commentary preceden al cierre sin observaciones. No se ejecuta commentary |
| [r4](real-r4.json) | PARTIAL. Protocolo de una acción por final_answer funciona. Cuatro consultas; el verificador detecta Bs 2.000 de diferencia en el total declarado y la revisión detecta series nombradas como vendedores |
| [r5](real-r5.json) | Cifras finales VERIFIED_WITH_LIMITATIONS: 24/24. Siete rechazos de CASE/GROUP BY impiden acreditar grano documental; no demuestra una investigación completa |
| [r6](real-r6.json) | BLOCKED por join_pair_budget tras cuatro consultas. La normalización de parámetros ya está corregida; falta resumen terminal tras el rechazo |
| [r7](real-r7.json) | PARTIAL: cinco lecturas y resumen terminal, nuevo perfil relacional técnico, error de predicado y aliases de afirmaciones sin resolver |

La causa de CASE/GROUP BY se reprodujo con fixture: el SQL original funciona, pero los mismos literales SELECT/GROUP BY se convertían en parámetros distintos. Se reutiliza ahora la identidad de parámetros iguales de igual tipo, sin interpolar literales ni ampliar SQL o permisos. Regresión real DuckDB permanente.

Se incorporó devolución acotada de discrepancias numéricas al modelo, sin valor esperado ni oráculos históricos. La recuperación está cubierta con fixtures; **no** se atribuye a r7 una corrección numérica que no ocurrió. Los aliases no canónicos siguen rechazados como alcance no soportado.

## Matriz de cierre

Los PASS tienen únicamente el alcance especificado. El estado global del experimento es PARTIAL; no se certifica la causa ni preparación operacional de producto.

| Gate | Estado | Evidencia / límite |
| --- | --- | --- |
| FOUNDATION_REAL_READONLY | PASS | r7, referencias pinned 1408 y READ_ONLY; ningún write a Foundation |
| LUNA_ADAPTIVE_SQL | PASS | r7, SQL elegido por Luna y ejecutado a través del validador existente |
| OBSERVATION_DRIVEN_REPLANNING | PASS | pasos 1→2→3; grupo nulo descubierto y desgloses elegidos después |
| HYPOTHESIS_REVISION | PARTIAL | Reconoce alcance de incertidumbre; no corrige el predicado ni acredita descarte formal de hipótesis |
| RELATIONSHIP_VALIDATION | PASS | Perfil 1.534/1.534, 64 claves únicas, sin fanout; significado INVESTIGATIVE, join no ejecutado |
| INDEPENDENT_CLAIM_VERIFICATION | PARTIAL | Reconstrucción numérica completa offline; contrato runtime 2 VERIFIED / 14 UNVERIFIED; narrativa no certificada |
| CALENTA_BUSINESS_RECONCILIATION | PASS | Total, particiones, moneda, grano, documentos, período y cinco importes históricos exactos; causa no acreditada |
| SECURITY_REGRESSION | PASS | 206 tests locales; denegación antes de ejecución, pinning, muestras y cierre sin nueva ruta SQL. No acredita sandbox OS |
| TELCHIAI_V1_REGRESSION | PASS | 103 PASS / 1 skip de probe live opt-in; no certifica WhatsApp E2E |
| WHATSAPP_UNCHANGED | PASS | Sin cambios a transportes, handlers, activación, webhooks, grants ni mensajes |
| WEB_COMPARISON_READINESS | BLOCKED | UI de demostración con timers, sin llamada al investigador ni identidad empresarial Web conectada |
| BLIND_PI_COMPARISON_READINESS | BLOCKED | No freeze; investigador todavía scoped a Calenta y contrato de afirmaciones incompleto. Pregunta no elegida ni ejecutada |

## A. Capacidad actual de TelchiAI

Luna puede investigar datos reales con SQL elegido según observaciones y producir información numérica útil. **Todavía no demuestra el objetivo completo** de descubrir y verificar autónomamente la causa de esta anomalía.

El resultado material no se oculta: Bs 47.340,13 sin canal, 26,24 % del universo. La explicación causal sigue INVESTIGATIVE. El investigador es aún un modo CLI supervisado DEV, no una función autenticada del producto ni una ruta del State Engine V1.

## B. Preparación mínima de la comparación

No se implementó Web ni se ejecutó una pregunta comparativa. Los pasos siguientes deben completarse antes de conocer la pregunta sorpresa y antes de congelar ambos entornos.

1. Cerrar fiabilidad del investigador: campos canónicos de afirmaciones, devolución de rechazos semánticos/aliases y distinción entre etiquetas calculadas y valores fuente; acreditar revisión de hipótesis con datos reales sin codificar una ruta Calenta.
2. Exponer el mismo investigador como operación del servicio Telchi existente, con contexto derivado de identidad Console y permisos efectivos, alcance empresarial read-only genérico autorizado y publicación fijada. El CLI local/UID no es autorización Web. No mantener transacciones/locks de conversación durante investigación larga: `TelchiHandler` tiene hoy timeout de 80 s y la investigación puede durar más.
3. Conectar la UI actual al servicio compartido en Srv05 existente, con login/sesión real y cancelación/resultado persistido. No enviar token DEV al navegador ni suplantar al usuario por un teléfono fijo. Mantener WhatsApp intacto; no duplicar motor ni crear backend.
4. Tras gate autenticado Web, congelar código/configuración/modelos/herramientas y el mismo scope, período, publicación/snapshots y métricas para ambos sistemas. Entregar la pregunta nueva independientemente, sin respuestas ni artefactos del otro; comparar exactitud, exhaustividad, autonomía, verificación y rendimiento, declarando las herramientas más amplias de Pi.

Brecha exacta inspeccionada: `TelchiAIHome.svelte` usa timers y no hace fetch. `assistant/dev_runtime_http.py` ofrece un adapter loopback DEV hacia dispatcher/handler V1, no el investigador exploratorio; su token DEV/teléfono piloto no sustituye autenticación Web. `assistant/composition.py` no inyecta un investigador en `TelchiHandler`.

## Validación y reproducción

Las pruebas se ejecutaron secuencialmente con capacidad observada y sin servidores nuevos. Los artefactos JUnit conservan los resultados; ninguna evidencia previa se usa como prueba de un entorno actual.

Desde `SrvRestAstroLS_v1/backend`:

```bash
uv run --no-sync pytest modules/telchi/exploratory_sql -q
uv run --no-sync pytest modules/telchi/assistant/tests/test_assistant.py modules/telchi/assistant/tests/test_safety.py modules/telchi/assistant/tests/test_rejected_execution_guard.py modules/telchi/assistant/tests/test_whatsapp_operational_contract.py modules/telchi/assistant/tests/test_delivery_reliability_v1.py -q -rs
uv run --no-sync python -m modules.telchi.exploratory_sql.adaptive_research --authorize-dev-io-exception --output ../../data/reports/telchi/adaptive-business-research-v1/NEW.json
```

La última orden incurre en coste del modelo y requiere repetir preflight/guard y mantener autorización DEV. No sobrescribe evidencias. Resultado de tests: [206 PASS](exploratory-final-tests.xml) y [103 PASS / 1 skip](v1-final-tests.xml). Auditoría sin nuevo I/O: `adaptive_verifier.reconstruct` sobre las referencias de r7 y Decimal sobre las filas conservadas.

`lat check md`, `lat check index`, `lat check sections`, `lat check code-refs`, `lat check` y `git diff --check`: PASS. LAT advierte falta de init/key para búsqueda semántica; no bloquea estos checks ni sustituye gates de producto.

## Archivos e impacto

Todos los cambios de implementación se concentran en `backend/modules/telchi/exploratory_sql/`; los informes viven en este directorio de evidencia. No se editó infraestructura compartida ni código de otro módulo.

Nuevos: `adaptive_sources.py`, `adaptive_verifier.py`, `adaptive_research.py`, `test_adaptive_sources.py`, `test_adaptive_research.py`. Cambios pequeños: `foundation.py` permite su catálogo sellado en la subclase; `validator.py` admite sólo ese catálogo y reutiliza parámetros iguales; `research.py` admite prompt por instancia y registra commentary no ejecutable; README enlaza este cierre preservando el histórico.

Foundation, SAP, PostgreSQL compartido, State Engine, Console, Web y WhatsApp permanecen sin modificación por esta tarea. No se hicieron commits, push ni operaciones Git sobre el índice. Los cambios concurrentes se preservan. Próximo paso: aceptación del cierre PARTIAL y resolver la fiabilidad semántica antes de autorizar integración Web o freeze.
