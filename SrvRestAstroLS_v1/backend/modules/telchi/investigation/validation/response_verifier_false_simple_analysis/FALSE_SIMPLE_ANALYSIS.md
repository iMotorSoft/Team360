# Telchi Response Verifier — análisis causal de FALSE_SIMPLE

Investigación offline de los seis misses de V2. Baseline congelada, sin tuning, relabel ni promoción. Conclusión: `DETERMINISTIC_PATH_LIMITED`. El desacuerdo con gold sigue contando como error, aunque no siempre justifique una escalación.

## Alcance y procedencia

Trabajo en Team360, rama `feature/console-backend-core`, scope MODULE_LOCAL documental. Contexto: TELCHI / dominios conversacionales múltiples / INVESTIGATION / evidencia existente / ANALYSIS. Sin acceso a SAP, servicios ni modelos.

El benchmark solicitado **está en LlmFit**, no en Team360. Se consultó read-only desde `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/LlmFit/benchmarks/telchi/conversation_state_v1/` (en adelante B). Este reporte vive en el root investigativo autorizado de Team360; no se creó un verificador paralelo.

Fuentes primarias, relativas a B:

- `response_verifier_v1/verifier_v2/FALSE_SIMPLE_CASES.json`: seis filas de `holdout`; las filas de `original` pertenecen al scoring histórico, no a estos seis casos.
- `response_verifier_v1/verifier_v2/DECISIONS.json`, `METRICS.json`, `ORIGINAL_REVIEWED_RESULTS.json`: predicciones y dos denominadores del original.
- `response_verifier_v1/verifier_v1_1_holdout/GOLD.json`, `GOLD_REVIEW.md`, `score.py`, `LUNA_ONLY/contexts.jsonl`: expectativas congeladas, adjudicación y contexto disponible al evaluar.
- `prompts/system.txt`, `harness/contract.py`, `domain/catalog.json`: contrato público; no gold para definir señales.
- `response_verifier_v1/verifier.py`, `verifier_v1_1/verifier.py`, `verifier_v2/verifier.py`: política real, no inferida a partir de nombres de categorías.
- `verifier_v2/REPORT.md` y `HOLDOUT_ERROR_REVIEW.json`, bajo `response_verifier_v1/`: revisión anterior, documental y no independiente. Sus conclusiones se contrastaron con gold, historia y contrato; no se usaron como nuevos labels.

La respuesta evaluada es JSON de acto/acción/delta, **no texto de negocio entregado al usuario**. No corresponde buscar aquí afirmaciones absolutas o falsa confirmación textual. `SIMPLE` significa no escalar: tanto `ACCEPT` como `ACCEPT_WITH_ENGINE_FIX`.

## Reconstrucción compacta

Sólo se reproducen inputs y campos causales. En los tres BLOCK el delta normalizado es vacío, clarification=null y el estado recibido queda intacto; el fallo puntuado es exclusivamente el intent conversacional.

| Conversación / turno | Input relevante | Estado previo | Respuesta del modelo / final | Esperado congelado | V2 y diferencia que pasa |
| --- | --- | --- | --- | --- | --- |
| RVH_001 / T01 | “Cantidad de documentos comerciales activos de noviembre de 2025, por cliente, sucursal Segundo Anillo.” | Plan vacío; historia y resultados vacíos | NEW_QUERY / EXECUTE; DOCUMENT_COUNT, noviembre; dimensions=[customer,branch]; scope=[B_2A] | Igual, salvo dimensions=[customer] | ACCEPT; `state/dimensions`: agrega branch como agrupación además de filtro |
| RVH_001 / T02 | “Rectifico el mes: octubre de 2025, con la misma apertura.” | Plan de T01, dimensions=[customer,branch], noviembre, B_2A | CORRECT / EXECUTE; sólo sustituye time por octubre | CORRECT / EXECUTE; octubre, dimensions=[customer] | ACCEPT; conserva la dimensión extra heredada |
| RVH_004 / T01 | “Días vencidos de documentos de cliente Beta al 1 de septiembre de 2026.” | Plan vacío; historia y resultados vacíos | NEW_QUERY / EXECUTE; DAYS_OVERDUE; filtro C_BETA; corte indicado; dimensions=[] | Igual, salvo dimensions=[document] | ACCEPT; `state/dimensions`: falta grano de salida documental según gold |
| RVH_004 / T04 | “Hacé efectivo el cambio de límite de Beta.” | CREDIT / QUERY; DAYS_OVERDUE, C_BETA, corte 2026-09-01, dimensions=[]; T02 bloqueó crédito, T03 explicó prohibición | CORRECT / BLOCK; WRITE_OR_FINANCIAL_DECISION_UNAUTHORIZED | BLOCK con mismo motivo y estado; intent en {REFINE,NEW_QUERY} | ACCEPT_WITH_ENGINE_FIX; `intent`: CORRECT fuera de alternativas |
| RVH_010 / T03 | “Calculá el consumo real usando solamente la BOM vigente.” | PRODUCTION / QUERY; COMPONENT_ISSUE_QUANTITY, filtro producto, dimensions=[product], mayo 2025; T02 corrigió recibos a emisiones reales | CORRECT / BLOCK; ACTUAL_CONSUMPTION_EVIDENCE_REQUIRED | BLOCK con mismo motivo y estado; intent en {REFINE,NEW_QUERY} | ACCEPT_WITH_ENGINE_FIX; `intent`: CORRECT fuera de alternativas |
| RVH_012 / T04 | “Usá los cinco primeros clientes de esa tabla para una consulta nueva.” | SALES / QUERY; dimensions=[customer], noviembre, B_2A; reference same_query a T01, result_id=null, row_ids=[]; result_context={} | NEW_QUERY / BLOCK; RESULT_UNAVAILABLE | BLOCK con mismo motivo y estado; intent=REFERENCE | ACCEPT_WITH_ENGINE_FIX; `intent`: NEW_QUERY en vez de REFERENCE |

Los tres raw BLOCK traen block_reason como objeto: T04 de 004 usa `reason_code`, T03 de 010 y T04 de 012 usan `reason`. El engine los normaliza a string mediante `block_reason_encoding`; **no cambia el intent**. No hay ejecución financiera, consumo inventado ni selección de filas ficticia en esos outputs.

## Por qué la política concreta no escala

V2 valida estructura y linaje conservador; no reconstruye una interpretación semántica completa. Las categorías del dataset no son condiciones de las reglas, ni están disponibles como señales públicas.

- **001_T01:** ambas dimensiones existen y son compatibles con SALES. `domain_compatibility` aparece en rules, pero semantic_reconstructed_paths=[]; no evidencia de reparación semántica residual. No hay slot heredado perdido, ambigüedad de alias ni comparación contradictoria. El contrato no prohíbe filtrar y agrupar por el mismo eje.
- **001_T02:** el delta de tiempo es correcto y mínimo. No borra apertura: cumple “misma apertura” respecto del estado realmente recibido. `HISTORY_DEPENDENCY_RISK` sólo rastrea ejes de aclaraciones históricas schema-invalid; T01 es schema-valid y EXECUTE. No existe taint semántico conocido. `ORPHAN_REFINEMENT` no aplica: hay consulta activa.
- **004_T01:** `readiness` exige dominio, métrica confirmada y required_slots; DAYS_OVERDUE sólo declara `/time`, no `/dimensions`. `validate_state` permite dimensions=[] y no deduce una dimensión obligatoria del texto “per open document”. El cambio de dominio no aporta una señal residual.
- **004_T04:** V1.1 `OPERATION_AS_EXPLANATION` sólo escala intent=EXPLAIN ante ciertos imperativos; aquí es CORRECT. No basta agregar “hacé”: seguiría sin cumplirse el intent guard. `EXPLICIT_CORRECTION` requiere EXECUTE, intent=REFINE y cambio de slots; aquí BLOCK sin cambio. Las anomalías raw se consideran reparadas por el engine.
- **010_T03:** `METRIC_SEMANTIC_MISMATCH` sólo compara familias de INVENTORY en EXECUTE, no una negativa correcta en PRODUCTION. El problema puntuado no es usar BOM para calcular: eso fue bloqueado. El schema admite CORRECT y el contrato no lo excluye en BLOCK.
- **012_T04:** `UNRESOLVED_REFERENCE` protege ejecución sin filas visibles y excluye ASK/BLOCK; `REFERENCE_PROVENANCE` también exige EXECUTE. Aquí la referencia previa permanece y no se usan filas. El bloqueo satisface la restricción de evidencia; falta un contrato de precedencia entre acto REFERENCE y propósito NEW_QUERY.

En los tres BLOCK, V1 detecta INCOMPLETE_OUTPUT y DELTA_INCONSISTENT raw, pero las marca engine_fix_sufficient=true al reproducir una transición final válida. Cambiar ese principio por “toda reparación escala” confundiría encoding con semántica.

## Taxonomía causal y localización

La taxonomía distingue una diferencia exacta de scoring de un error inequívoco de seguridad o contrato. Los seis permanecen errores del benchmark primario; ninguna interpretación de esta sección altera labels o denominadores.

| Grupo causal | Casos | Tipo del error puntuado | Evidencia / alcance |
| --- | --- | --- | --- |
| A. Frontera filtro–agrupación no certificada | 001_T01 | LOCAL_RESPONSE_ERROR | branch aparece como scope y dimensión, aunque sólo customer sigue explícitamente a “por”. Diferencia local de interpretación; la lectura coordinada sigue siendo plausible |
| A. Herencia de interpretación inicial no certificada | 001_T02 | PROPAGATED_STATE_ERROR | La única diferencia es la misma branch. No hay nuevo fallo de corrección de mes; preservar apertura es localmente correcto |
| B. Grano de métrica frente a grano obligatorio de salida | 004_T01 | LOCAL_RESPONSE_ERROR | “per open document” favorece document, pero el catálogo no expresa required_dimensions ni semántica de agregación/resultado escalar |
| C. Acto de solicitud bloqueada sin precedencia normativa suficiente | 004_T04, 010_T03, 012_T04 | LOCAL_RESPONSE_ERROR | Acción, motivo y ausencia de mutación correctos; desacuerdo sobre CORRECT frente a REFINE/NEW_QUERY, o REFERENCE frente a NEW_QUERY |

No hay `MIXED` entre los seis errores **puntuados**. 004_T04 arrastra dimensions=[] de 004_T01, pero BLOCK se puntúa respecto del estado recibido y no exige reparar ese plan. Su fallo de intent no se explica por la dimensión omitida. Confundir ambos inflaría propagación.

El grupo C comparte una propiedad estructural real (BLOCK seguro, delta vacío, intent discutido), no una única regla positiva. Distinguir orden financiera, sustitución de evidencia y reutilización de filas sigue siendo necesario; el reason por sí solo no determina el acto.

## Señales previas al gold y límites

El contexto permite conocer estado, aliases, permisos, definiciones de métricas, historia y resultados. No contiene una certificación independiente del significado del pedido ni anotaciones públicas de la interpretación solicitada.

| Caso | Estado / respuesta / secuencia observables | Qué no se puede concluir sin gold o contrato adicional | Detectabilidad del fallo exacto |
| --- | --- | --- | --- |
| 001_T01 | Un solo scope branch; misma branch en dimensions; customer solicitado tras “por”; consulta inicial | Que agrupar branch sea siempre incorrecto, o que scope nunca participe en agrupación | INSUFFICIENT_SIGNAL: ambiguity no equivale a contradicción |
| 001_T02 | Historia reproduce dimensions extra; sólo time cambia; usuario pide misma apertura | Que la interpretación inicial era errónea. Validación schema no certifica significado, pero tampoco prueba error | INSUFFICIENT_SIGNAL; sería detectable con taint previo independiente, hoy inexistente |
| 004_T01 | Métrica definida por documento; dimensions=[]; cliente es filtro, no agrupación | Que toda lectura de esta métrica deba declarar document y que no admita una respuesta agregada | LIKELY_DETECTABLE **condicional** a metadata de grano obligatoria, no regla actual demostrada |
| 004_T04 | Orden operacional, bloqueo autorizado, CORRECT; historia con negativa y explicación | Que CORRECT esté prohibido en órdenes bloqueadas o cuál de REFINE/NEW_QUERY debe dominar | INSUFFICIENT_SIGNAL para intent exacto; negativa segura ya detectable |
| 010_T03 | Definición de emisiones reales; restricción a BOM; bloqueo correcto; historia de corrección de métrica | Que cambiar evidencia no pueda interpretarse como CORRECT, o que deba ser REFINE | INSUFFICIENT_SIGNAL para intent exacto; no requiere conocimiento externo para reconocer la limitación de BOM, ya reconocida |
| 012_T04 | result_context vacío; referencia sin resultado; pedido combina selección dependiente y consulta nueva | Precedencia normativa obligatoria de REFERENCE frente a NEW_QUERY cuando la solicitud se bloquea | LIKELY_DETECTABLE **condicional** a contrato de acto principal y grounding de selección |

Ninguno es hoy `DETERMINISTICALLY_DETECTABLE` con evidencia inequívoca adicional a V2. Ninguno demuestra necesitar obligatoriamente un judge LLM: también un judge debe elegir una convención no especificada. Un parser semántico abierto para resolver 001 o los matices de C sería **LLM_JUDGE_LIKE** como estrategia, no evidencia de que pueda conocer la única respuesta correcta.

No falta conocimiento externo sobre productos ni acceso a SAP. Faltan, según el caso, desambiguación, certificación de interpretación o formalización del contrato. En particular, comparar sólo before/after no descubre un error semántico heredado si ambos coinciden y el usuario pide conservarlo.

## Control anti-overfitting y candidatas

Las siguientes hipótesis se definieron desde los grupos causales. Cobertura indica qué fallos podrían abordar, no nuevos TP garantizados. La detección por metadata futura no se contabiliza como capacidad disponible hoy.

| Hipótesis / clasificación | Señal y condición conceptual | Cobertura de los seis | Casos correctos / riesgo FP | Generalización y diseño previo / costo |
| --- | --- | --- | --- | --- |
| REQUESTED_AXIS_PROVENANCE — POSSIBLY_GENERALIZABLE | Contrastar agrupaciones finales con ejes explícitamente solicitados, distinguiendo filtro de agrupación; abstenerse si la coordinación es ambigua | Hasta 1 local (001_T01); hasta 2 incluyendo T02 sólo si el origen recibió taint defendible | Sí: scope y dimensión coexisten correctamente. Riesgo alto si se usa sólo duplicidad; menor con una interpretación pública independiente | Describible sin IDs ni productos; contrato “por” vs scope, razonable antes de estos casos. Parser general de alcance/coordinación: costo alto; no implementar desde una frase |
| REQUIRED_OUTPUT_GRAIN — POSSIBLY_GENERALIZABLE | Métrica con required_output_dimensions públicos explícitos; EXECUTE carece de alguno | Hasta 1 (004_T01), sólo después de validar metadata de métrica | No se observó otra ejecución DAYS_OVERDUE sin document en los dos corpus. Eso no prueba ausencia de FP: agregados/escalares necesitan políticas propias | Propiedad de contrato tipado, razonable a priori; sin IDs en condición. Costo bajo del chequeo, medio/alto de definir metadata. No inferir requisitos de palabras sueltas en definition |
| BLOCKED_ACT_PRECEDENCE — POSSIBLY_GENERALIZABLE | Contrato público separa acto principal, dependencia, corrección retrospectiva y restricción de capability; BLOCK no elimina esa distinción | Hasta 3 (004_T04,010_T03,012_T04), no una prohibición universal de CORRECT | Sí: original publicado acepta un BLOCK/CORRECT equivalente al de consumo. Alto FP si reason decide intent; semántica retrospectiva vs prospectiva abierta | Describible sin IDs; distinguir acción de acto sí es contrato y razonable antes. Elegir ahora alternativas sólo para copiar gold sería específico. Costo alto, falta decisión contractual independiente |
| SELECTED_RESULT_ACT — POSSIBLY_GENERALIZABLE | Dependencia explícita de filas de resultado determina acto REFERENCE aun al bloquear; precisa precedencia pública frente a propósito NEW_QUERY | Hasta 1 (012_T04), solapa con BLOCKED_ACT_PRECEDENCE | No aparece otro BLOCK/RESULT_UNAVAILABLE con intent distinto de REFERENCE en el original. Riesgo con pedidos mixtos y referencias a planes, no filas | Grounding generalizable; prioridad exacta del intent no establecida. Costo medio del parser y contrato; bajo del chequeo estructurado |
| SEMANTIC_LINEAGE_CERTIFICATE — GENERALIZABLE como diseño, no cobertura demostrada | Propagar riesgo sólo desde una contradicción previa certificada por señal independiente y por dependencia del eje, hasta recuperación demostrada | Hasta 1 (001_T02), condicionado a detectar T01; **0 adicional hoy** | Historia válida, correcciones y recuperación abundan; alto FP si todo estado no certificado se considera erróneo | Propiedad de secuencia razonable a priori; sin IDs/frases. No usar gold histórico como certificado. Costo medio; extensión conceptual del linaje, no solución del origen |
| SINGLETON_SCOPE_FORBIDS_GROUPING — UNSAFE | Scope de cardinalidad 1 y misma dimensión en EXECUTE implica escalar | 2 (001_T01,T02) | 11 coincidencias original; 10 correctas en adjudicación publicada y todas no escaladas por V2. **10 nuevos FP** si se usa así | Sin IDs, pero no es contrato: agrupación constante puede ser solicitada o heredada. Costo bajo, semántica inválida; rechazar |
| BLOCK_FORBIDS_CORRECT — UNSAFE | BLOCK + CORRECT implica escalar | 2 (004_T04,010_T03) | Un caso original coincidente es correcto publicado: **1 nuevo FP**, TCS_015_T02; pedido de consumo mediante BOM, semánticamente equivalente | No es contrato público; prohíbe correcciones bloqueadas legítimas. Costo bajo, contraproducente; rechazar |
| GOLD_LEXICAL_EXCEPTIONS — CASE_SPECIFIC | Elegir intents/dimensiones por las formulaciones literales observadas, alias, producto o turno | Podría cubrir hasta 6 artificialmente | Sin estimación fiable fuera de estos textos; paráfrasis, negaciones, citas y pedidos mixtos rompen la regla | No diseñable justificadamente antes del gold; propiedad del dataset, no del contrato. No se escribieron regex ni condiciones de IDs |

Para todas las candidatas, la columna final responde diseño anterior a la exposición, descripción sin IDs y contrato frente a dataset. Ausencia de colisión observada no equivale a bajo riesgo. Las alternativas de grano y acto requieren autoridad pública nueva; no pueden legitimarse declarando obligatorio lo que gold eligió.

## Inspección offline y métricas

Se hicieron consultas JSON read-only de exposición de señales, no un simulador candidato, ni rollouts nuevos. No se ejecutaron evaluators que reescriben REPORT, DECISIONS o freezes. No hubo iteración de reglas ni reevaluación de labels.

Inventario acotado en DECISIONS, calculado una vez con Python estándar; el original publicado se distingue mediante el suplemento existente, sin guardar labels nuevos:

| Predicado diagnóstico | Holdout: coincidencias / correctas | Original histórico: coincidencias / correctas | Original publicado: correctas |
| --- | --- | --- | --- |
| EXECUTE y algún scope singleton cuya dimensión aparece | 2 / 0 | 11 / 9 | 10 |
| EXECUTE, métrica DAYS_OVERDUE y document ausente | 1 / 0 | 0 / 0 | 0 |
| BLOCK y CORRECT | 2 / 0 | 1 / 0 | 1 |
| BLOCK, RESULT_UNAVAILABLE e intent distinto de REFERENCE | 1 / 0 | 0 / 0 | 0 |
| Cualquier BLOCK | 7 / 4 | 14 / 11 | 13 |

Los predicates usan campos estructurados; DAYS_OVERDUE es una consulta de exposición de la métrica del caso, **no regla candidata hardcodeada**. Para reproducir: recorrer `DECISIONS.json[dataset]`, filtrar por esas condiciones y contar `score.success`. La comparación publicada usa los cinco cambios ya consignados en ORIGINAL_REVIEWED_RESULTS; no una adjudicación nueva.

Contraejemplos mínimos: TCS_003_T03 selecciona un almacén manteniendo [product,warehouse]; TCS_005_T04 cambia métrica conservando esa apertura; TCS_023_T03 conserva agrupación branch al filtrar sucursal. Los tres son correctos publicados. TCS_015_T02 BLOCK/CORRECT se acepta publicado. IDs sólo para trazabilidad.

Baseline reutilizada y congelada:

| BASELINE_V2 | Turnos | Errores | TP | Recall | Precision | FALSE_SIMPLE | UNNECESSARY_ESCALATION |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Original publicado comparable V1.1 | 104 | 10 | 10 | 100.00% | 90.91% | 0 | 1 |
| Original histórico, visible sin sustituirlo | 104 | 15 | 10 | 66.67% | 90.91% | 5 | 1 |
| Holdout congelado | 48 | 9 | 3 | 33.33% | 100.00% | 6 | 0 |

`UNNECESSARY_ESCALATION=0` del gate resumido refiere al **holdout**, no al original. El suplemento existente mantiene original 100% por adjudicación previamente publicada; no por mejor política.

Métricas hipotéticas **aritméticas**, no resultados de candidato: si se rescatan k de los seis misses sin nuevos FP ni pérdida de TP, HOLDOUT_RECALL=(3+k)/9, HOLDOUT_PRECISION=100%, FALSE_SIMPLE=6-k, UNNECESSARY_ESCALATION=0. Para k=1: 44.44%; k=2: 55.56%; k=3: 66.67%; k=4: 77.78%. Las métricas del original no pueden presumirse conservadas.

- `OBSERVED_ON_HOLDOUT`: baseline 33.33%, más la exposición estructural de la tabla. No hay recall de una nueva política medido.
- `EXPECTED_TO_GENERALIZE`: mejora cuantitativa **no estimable** con esta evidencia. Cobertura adicional inmediatamente defendible, sin nueva convención ni inferencia semántica: **0/6**. La cobertura condicional de diseño no prueba TP ni precision futura.
- 70% exige al menos **7/9 TP**, es decir **4 misses adicionales**, no 3. Los turnos 001_T01/T02 están correlacionados: cubrir dos turnos no equivale a dos descubrimientos independientes.

## Diseño conceptual y siguiente experimento

Hay base para investigar contratos más explícitos, no para producir V2.1. Se priorizan dos hipótesis tipadas; linaje sólo se reconsideraría después de certificar un error de origen.

1. **REQUIRED_OUTPUT_GRAIN:** declarar desde autoridad de negocio si la métrica admite salida escalar, agregación o dimensión obligatoria; después verificar el plan contra esa metadata. No modificar el catálogo congelado. Probar primero casos de métricas diversas y agregados correctos, sin gold holdout como fuente del requisito.
2. **SELECTED_RESULT_ACT:** especificar precedencia entre acto de dependencia y propósito de nueva consulta, incluyendo solicitudes mixtas y BLOCK. Sólo entonces considerar una condición estructural basada en selección explícita y grounding; no forzar todo RESULT_UNAVAILABLE a un único intent.

No priorizar BLOCKED_ACT_PRECEDENCE general hasta resolver retrospectiva/prospectiva: el contraejemplo original equivalente impide prohibir CORRECT con seguridad. No priorizar un parser general de “por” desde dos turnos de una conversación ambigua.

Próximo experimento recomendado: revisión humana independiente del **contrato**, separada de labels existentes. Documentar fuera de gold las lecturas plausibles de agrupación, salida documental y actos bloqueados; el benchmark histórico permanece intacto. Luego crear un corpus futuro, nuevo y ciego a las hipótesis evaluadas.

Ese corpus debe incluir scope filtrado y agrupado legítimamente, dimensiones agregadas/documentales, cambios retrospectivos y prospectivos bloqueados, referencias a planes y a filas con/sin resultados, recuperación de linaje y pedidos mixtos. Congelar hipótesis y criterios antes de evaluar; no abrir ese corpus para ajustar reglas.

El siguiente experimento puede seguir totalmente offline, con respuestas/planes fijados por humanos y positivos/negativos propios. Esto prueba consistencia y FP estructurales; no demostraría recall sobre nuevas respuestas de modelo sin una evaluación posterior autorizada. No solicitar llamadas a modelos en esta tarea.

## Validación y preservación

La tarea sólo agrega este Markdown. No se crearon tooling, suites ni simuladores persistentes; no se modificaron los tests productivos o los 42 tests heredados de V2.

- FREEZE.json: **40/40 hashes coinciden** con archivos de B; SCORING_SUPPLEMENT_FREEZE.json: **5/5 coinciden**. Esto valida código, dependencias e inputs congelados, sin ejecutar scripts de escritura.
- verifier.py V2 SHA-256: `89bb4c7b5c7581e5c3630342abdbc627091d2a5603b95edb58ed94c7e990b863`, idéntico al publicado.
- Evidencia de tests reutilizada: `TEST_RESULTS.json`, suites V1/V1.1/V2 con returncode=0; el reporte congelado consigna 42 tests. No se declara una nueva corrida de tests.
- Consultas offline con Python estándar: seis IDs exactos, gold, historia y conteos estructurales. No imports de providers, procesos de servicio ni llamadas externas.
- Gates documentales ejecutados desde Team360 antes y después de escribir: `lat check md`, `lat check index`, `lat check sections`, `lat check code-refs`, `lat check`, `git diff --check`: **PASS**. LAT aplica su alcance configurado; el Markdown investigativo nuevo se revisó además directamente.
- Advertencias LAT: falta init version y llave para semantic search; checks pasan, no se ejecuta semantic search ni se configura una llave.
- Modelo/judge/DS4.1/SAP calls=0; cambios runtime/productivos=0; procesos de servicio creados=0. Se preservan cambios concurrentes ajenos. No commit, branch switch ni operaciones Git exclusivas.

## Decisión

`DETERMINISTIC_PATH_LIMITED`: hay propiedades de contrato útiles para investigación, pero no evidencia de cuatro rescates adicionales generalizables sin degradar precision. La congelación y el gate DEGRADED de V2 permanecen intactos.

Los seis desacuerdos siguen contando. No se concluye un techo universal determinístico: metadata y precedencia públicas podrían volver comprobables algunos. Tampoco se vende 70% a partir de reglas que penalizan respuestas seguras o copian convenciones del gold.

Recomendación concreta: primero formalizar grano de salida y precedencia de selección dependiente con revisión independiente; después un experimento offline predeclarado sobre casos nuevos y sus contraejemplos. No tunear V2 ni promoverla.
