# TelchiAI Direct Ask V1 — cierre DEV

CLI implementada y conversación real demostrada. Resultado global **PARTIAL**: cifras y continuidad acreditadas en casos concretos; no se declara preparado un benchmark empresarial general sin reservas.

## Arranque y uso

Ejecutar desde Ubuntu con la credencial OpenAI DEV existente en el entorno, sin mostrar ni copiar su valor. No requiere iniciar servidores ni servicios adicionales.

```bash
cd /media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/SrvRestAstroLS_v1/backend
TEAM360_ENV=development uv run --no-sync python -m modules.telchi.exploratory_sql.ask --authorize-dev-io-exception
```

Escribir preguntas sucesivas y aclaraciones con Enter. `/salir` o Ctrl+D cierran; Ctrl+C cancela durante investigación o sale desde el prompt. Las conexiones, tareas HTTP y threads propios se cierran. La [guía operativa](../../../../SrvRestAstroLS_v1/backend/modules/telchi/exploratory_sql/DIRECT_ASK.md) detalla controles y límites.

## Configuración y alcance

Rama `feature/console-backend-core`; HEAD `09d2ec715a31bb88574d734eacb9f437f008624e`. El worktree ya tenía cambios extensos: no se hicieron commits, operaciones de index, push, cambios de rama ni limpieza.

- Modelo efectivo: OpenAI Responses directo `gpt-5.6-luna`, reasoning `medium`, sin fallback, `store=false`, 8192 tokens de salida investigativa. Identidad **local DEV DE PRUEBA**, ligada al UID, no autenticación Console ni acceso productivo.
- Publicación: `foundation_afd08d9eca6a725be53cdc3f9d5709c9`; snapshot `1408`. Binding comprobado antes de consultas. Fuentes de facturación activa publicada, metadatos, productos y vendedores; sin universo de SKU/período preprogramado.
- Digest Python final: `2401355d3330a3e21e5071fb0529370ead444fc370c197f7504f37547d24bc18`. Las corridas finales y tests corresponden a ese código. Dependencias y árbol se registran en `freeze.json` y `worktree-status.txt`.
- Sin nueva persistencia PG. Evidencia JSON privada local; ninguna modificación Foundation/SAP/PG compartido, Web, WhatsApp, Srv05 o configuración global.

## Conversación real final

Los resultados pertenecen a filas publicadas y a la medida de líneas comerciales BS, no a facturación neta, cobros o un año completo. Se separa estado de cifras de completitud de respuesta.

| Turno real | Resultado acreditado | Estado y evidencia |
| --- | --- | --- |
| Cuatro SKU L02822/L02823/L03658/L03649, agosto 2026 | 180.400,81 BS | Cifra VERIFIED_WITH_LIMITATIONS; turno PARTIAL porque Luna no conservó cobertura completa después de reparar afirmaciones. [Turno 1](20261028T022942.104848Z/turn-001.json) |
| «Ahora solo L02822, manteniendo el mismo período y medida. ¿Cuánto representa en importe y documentos únicos?» | 59.456,05 BS; 444 documentos únicos | VERIFIED_WITH_LIMITATIONS, contexto heredado y SQL nuevo. [Turno 2](20261028T022942.104848Z/turn-002.json) |
| «¿Cuánto vendimos de vitamina C este año?» | 9.556,50 BS; 37 documentos/líneas para el subconjunto descubierto M01966/M04196/M04301 | PARTIAL. **No acredita el universo completo de vitamina C**, combinaciones/ácido ascórbico ni cobertura anual. No usarlo como total de vitamina C. [Turno libre](20261028T023251.428814Z/turn-001.json) |

Ejemplo abreviado de salida real del segundo turno: «Importe de líneas comerciales: 59.456,05 BS. Documentos únicos: 444. Alcance consultado: agosto de 2026 y item_code=L02822. Cifras verificadas con limitaciones».

La prueba libre expone un límite de producto: el motor puede descubrir e investigar, pero aún no resuelve de modo fiable el universo conceptual ni solicita siempre la aclaración empresarial necesaria. La salida queda parcial; no se disfraza como cobertura semántica completa.

## Latencia y consumo

Valores observados del código final, no benchmark sorpresa. Los tokens excluyen el pequeño preflight separado; no se estiman dólares sin precios acreditados.

| Corrida / turno | Pared | Propuestas SQL | Llamadas investigativas | Tokens totales |
| --- | --- | --- | --- | --- |
| Cuatro SKU | 131,20 s | 5 | 8 | 48.362 |
| Aclaración L02822 | 32,42 s | 1 | 2 | 9.064 |
| Vitamina C libre | 70,45 s | 4 | 5 | 27.493 |

Los tres preflights reales devolvieron `ready=true`; cada respuesta aceptada verifica modelo/medium y ausencia de fallback. Foundation, no PostgreSQL/Milvus/LiteLLM, es dependencia de lectura de este runner autorizado directo.

## Verificación, fallos conservados y correcciones

Cada afirmación está vinculada a IDs de resultado/columna/fila, publicación/snapshot, unidad, moneda, grano y población. Los controles sin agregar no se envían a Luna; el cálculo independiente usa Decimal y claves crudas.

- Reconstrucción de cabeceras/líneas por claves; cobertura del subconjunto, duplicados/fanout, moneda y procedencia compatibles. Las referencias incompletas no acreditan cifras.
- CTE, subconsultas, joins o expresiones sin significado acreditado siguen UNVERIFIED. Ratio entre resultados no acredita denominador global. Ningún label de Luna eleva un estado del controlador.
- La corrida final del primer turno registra tres revisiones y dos afirmaciones rechazadas antes de conservar el total acreditado. La interpretación de causalidad no se verifica mediante sumas.
- `20261028T004906.087894Z`: intentos iniciales PARTIAL. Causa reproducida: pasar cientos de claves independientes por IN excedía los límites de AST/SQL. Fix: claves como datos en tablas temporales privadas, sin relajar el SQL del modelo. Regresión de más de 31 claves.
- `20261028T005410.659319Z`: evidencia intermedia anterior a la normalización de fecha. No es el congelamiento final.
- `20261028T005903.500154Z`: **invalidada como respuesta mensual**. Comparar fecha timestamp textual con `<= '2026-08-31'` omitía el último día; el importe 174.839,77 BS y 57.794,35 BS NO son los totales mensuales acreditados. Causa reproducida; fix de proyección lógica a DATE ISO; regresión que compara límite inclusivo y semiabierto incluyendo timestamp del 31.

El verificador no es universal: acredita hechos de una consulta y su filtro explícito, no equivalencia automática de ese filtro con cualquier intención empresarial. La normalización documental corrige el defecto temporal demostrado; no se promete resolver toda ambigüedad lingüística.

## Matriz de aceptación

PASS se limita a la evidencia indicada. PARTIAL no equivale a readiness global ni producción. Las pruebas con fixtures se distinguen de la conversación real.

| Gate | Estado | Evidencia / límite |
| --- | --- | --- |
| DIRECT_ASK_CLI | PASS DEV | Arranque real, dos turnos y /salir en las corridas finales |
| NATURAL_LANGUAGE_QUERY | PASS mecanismo / PARTIAL negocio general | Preguntas españolas reales; vitamina C no acredita universo completo |
| FOUNDATION_READONLY | PASS DEV | Binding real 1408, catálogo readonly, FoundationReader y tests negativos |
| LUNA_ADAPTIVE_RESEARCH | PASS DEV | SQL elegido por Luna, observaciones sucesivas; 5/1/4 propuestas en corridas finales |
| CONVERSATION_CONTINUITY | PASS | «Ahora solo L02822» hereda agosto, BS y medida; [turno 2](20261028T022942.104848Z/turn-002.json) |
| USER_CLARIFICATION | PASS contrato / PARTIAL real | Test de action=clarify y contexto; la pregunta libre real no solicitó la aclaración necesaria |
| EVIDENCE_BINDING | PASS | Manifests/claims/referencias crudas; negativos IDs, snapshot, moneda, grano y contexto |
| INDEPENDENT_VERIFICATION | PASS subconjunto / PARTIAL universal | Decimal y reconstrucción cruda reales; no verificador universal ni cobertura semántica completa |
| UNSUPPORTED_SQL_SEMANTICS_HANDLING | PASS | CTE/subquery/aritmética no acreditadas; joins y grano desconocido no reciben VERIFIED; fixtures adversariales |
| HYPOTHESIS_REVISION | PASS acotado | Tres revisiones finales, dos rechazos; regresiones de contradicción y corrección; causalidad sigue no acreditada |
| BUSINESS_ANSWER_FIRST | PARTIAL | Cifras y límites primero, sin prosa técnica libre; interpretación/universo empresarial no resueltos de forma general |
| RESOURCE_LIMITS | PARTIAL | Límites de motor/consultas, concurrencia 1, guardian y sin spill; CPU/RSS/scan bytes OS no acreditados |
| SECURITY_REGRESSION | PASS DEV / no sandbox OS | Suite focalizada; sin shell/filesystem del modelo, identidad/publicación/permisos fail-closed; no acceso multiusuario |
| TELCHIAI_V1_REGRESSION | PASS offline | [JUnit final](tests-final.xml): 355 PASS / 1 skip; skip de sonda opcional Luna del intérprete de canal |
| WHATSAPP_UNCHANGED | PASS alcance | Ninguna edición ni activación de canal; no E2E WhatsApp ejecutado |
| READY_FOR_BLIND_PI_COMPARISON | NO — PARTIAL | Existe comando funcional; faltan acreditación de experiencia empresarial general y configuración equivalente del lado Pi |

## Validaciones y host

Las pruebas se ejecutaron secuencialmente con memoria disponible cercana a 6 GiB, ocho CPU, carga aproximada 1–2,5 y espera de I/O sostenida. Se usó la excepción DEV I/O-only existente, nunca un cambio de guard global.

```bash
cd SrvRestAstroLS_v1/backend
uv run --no-sync pytest modules/telchi/exploratory_sql modules/telchi/assistant/tests/test_assistant.py modules/telchi/assistant/tests/test_safety.py modules/telchi/assistant/tests/test_rejected_execution_guard.py modules/telchi/assistant/tests/test_whatsapp_operational_contract.py modules/telchi/assistant/tests/test_delivery_reliability_v1.py -q -rs --junitxml=../../data/reports/telchi/direct-ask-v1/tests-final.xml
```

Resultado: 355 PASS / 1 skip, 106,46 s. Sin browsers, nuevos servidores o suites globales. Comandos LAT y diff se registran al cierre en `validation.txt`; cualquier fallo impide declarar PASS documental.

`HOST_PREFLIGHT=BUSY_BUT_SAFE` solo bajo excepción DEV existente; baseline de I/O registra `safe=false`. `CONCURRENCY_USED=1` consulta, un thread DuckDB más monitores y worker acotado. No se terminaron procesos ajenos; las sesiones finalizaron y cerraron sus workers propios. El crecimiento de swap observado entre muestras fue pequeño, no presión sostenida de RAM.

## Archivos y alcance de cambios

Todos los cambios de implementación pertenecen a exploratory_sql. Los demás paths del worktree eran preexistentes y se preservan; no se atribuyen a esta tarea.

- Nuevos: `ask.py`, `ask_sources.py`, `ask_verifier.py`, `test_ask.py`, `DIRECT_ASK.md`.
- Modificados: `adaptive_research.py` (parametrización del loop, aclaración, progreso, cancelación y parciales), `foundation_dev.py` (combinar cancelación propia/usuario), `validator.py` (catálogo DEV sellado y contains puro opt-in), `claim_evidence.py` (evaluación independiente de strings) y `README.md` (enlace).
- Evidencia nueva: este directorio. Ningún cambio en WhatsApp, Web, Foundation, SAP, PostgreSQL, dependencias, lockfiles, servicios o documentos GLOBAL.

## Congelamiento candidato y siguiente paso

Se detiene el desarrollo con un runner utilizable y límites explícitos. Se registra el candidato y no se ejecuta la pregunta sorpresa; **no se declara congelamiento de un piloto plenamente aceptado**.

Antes de un benchmark ciego empresarial general: resolver o aceptar expresamente la limitación de universo conceptual/aclaración, mantener la identidad local DEV dentro del scope autorizado, registrar configuración/herramientas de Pi y un protocolo de verificación independiente sobre la misma publicación/snapshot. No cambiar lógica después de recibir la pregunta inédita.

La integración posterior de TelchiHandler se describe en la guía: invocar el mismo investigador con autorización real y lifecycle del canal, sin duplicar el motor. Srv05/Evolution/Messaging/Dispatcher/bindings/estado determinístico/envío durable/auditoría permanecen intactos.
