# PostgreSQL Knowledge Retrieval Breaking Points — Fase 1.6d

## 1. Objetivo del experimento

Construir un laboratorio ácido, reproducible y aislado que detecte los límites reales de PostgreSQL 18 + pgvector + JSONB + recursive CTE como primera etapa de knowledge retrieval y KnowledgeMap navegable de Team360, **antes** de introducir Milvus, ArangoDB u otra infraestructura como dependencias productivas.

Este laboratorio no busca probar que el sistema funciona bien en condiciones normales — eso ya está cubierto por los labs previos (Fase 1.6b retrieval quality, Fase 1.6c graph navigation). Este laboratorio busca **romper** el sistema deliberadamente para entender dónde, cómo y por qué falla, y si esos fallos se resuelven con mejor contenido, metadata, filtros o reranking, o si realmente requieren un cambio de base de datos vectorial o de grafo.

## 2. Hipótesis principal

**PostgreSQL 18 + pgvector + JSONB + recursive CTE puede alcanzar para la primera etapa de knowledge retrieval y KnowledgeMap navegable de Team360.**

Esto se considera cierto si el sistema falla únicamente en casos que se resuelven con mejor contenido, metadata, filtros o reranking — no por limitación de la base vectorial o relacional.

## 3. Hipótesis de ruptura

**El sistema se rompe en casos adversariales que requieren una arquitectura distinta (Milvus, ArangoDB, hybrid search).**

Esto se considera cierto si el sistema falla en casos donde:
- El backend vectorial no puede distinguir semánticamente conceptos cercanos aunque el contenido sea correcto.
- La latencia o calidad de pgvector es insuficiente incluso con contenido, metadata y filtros óptimos.
- La navegación relacional requiere más profundidad o ramificación de la que PostgreSQL recursive CTE puede entregar con performance aceptable.
- Hace falta hybrid search (BM25 + vectorial) para términos técnicos exactos.
- Hace falta reranking con LLM para casos borderline que pgvector no puede resolver.

## 4. ¿Qué significa "romperse" en este contexto?

El sistema se considera **roto** o **insuficiente** cuando ocurre cualquiera de estos casos:

| # | Síntoma | Severidad |
|---|---------|-----------|
| R1 | Recupera un chunk semánticamente parecido pero comercialmente incorrecto | **CRÍTICO** |
| R2 | Mezcla capacidades futuras con capacidades listas (overpromise) | **CRÍTICO** |
| R3 | No distingue "automatizable" de "vendible hoy" | **ALTO** |
| R4 | Trae conocimiento de otro scope, cliente, paquete o runtime | **CRÍTICO** |
| R5 | Recupera información vieja cuando existe una versión más nueva | **ALTO** |
| R6 | No encuentra el chunk correcto si la pregunta usa wording distinto (paráfrasis) | **MEDIO** |
| R7 | Requiere combinar dos o más conceptos y trae solo uno | **MEDIO** |
| R8 | Trae chunks correctos pero insuficientes para responder sin inventar | **ALTO** |
| R9 | La respuesta esperada requiere navegación conceptual que no aparece en top-k | **ALTO** |
| R10 | Aparece un concepto prohibido en top-3 | **CRÍTICO** |
| R11 | Falla en queries ambiguas de alto riesgo comercial | **CRÍTICO** |
| R12 | Recupera chunks con ruido semántico que contaminan el resultado | **MEDIO** |
| R13 | No puede aplicar filtro por metadata que existe pero no está indexada | **BAJO** |
| R14 | Falla por no tener graph traversal cuando el caso lo requiere | **ALTO** |

## 5. Familias de fallos (8 familias de pruebas adversariales)

### A. Confusión semántica
Chunks muy parecidos semánticamente pero con decisiones comerciales o técnicas distintas.

Problema típico: pgvector devuelve similitud coseno alta para conceptos relacionados pero no equivalentes.

Ejemplos:
- `automation` vs `workflow` vs `diagnosis` vs `action` vs `handoff` vs `lead capture`
- `automatizable` vs `vendible hoy` (son conceptos relacionados con peso comercial opuesto)
- `diagnostic_code` vs `diagnosis result` (misma raíz, significado distinto)

### B. Overpromise comercial
Capacidades futuras (planned_extension) que el retrieval puede confundir con capacidades listas.

Problema típico: el chunk describe una capacidad futura con detalle, y el ranking semántico la posiciona alto sin considerar el metadata de estado.

Casos:
- Step-to-Action → planned_extension
- WhatsApp handoff → planned_extension
- lead capture → planned_extension
- diagnostic_code → planned_extension

### C. Ambigüedad técnica
Términos del dominio que tienen significados distintos según contexto.

Ejemplos:
- `package_code` vs nombre comercial "Vera"
- `knowledge_scope` vs `package` como concepto
- `runtime target` vs `package context`
- `embedding_status`: `pending` vs `ready`
- `node_path` como referencia jerárquica vs ruta de archivo

### D. Multi-tenant / scope leakage
El mismo concepto aparece en contextos organizacionales distintos y el retrieval debe elegir correctamente.

Casos:
- Misma capacidad en dos paquetes distintos
- Misma pregunta con respuestas diferentes según scope
- Mismo chunk en dos scopes (no debería pasar, pero si ocurre, el retrieval debe escoger)

### E. Versionado / actualidad
Documentos con múltiples versiones donde la vigente debe ganarle a la obsoleta.

Casos:
- Documento v1 (obsoleto) vs v2 (vigente) con reglas distintas
- planned_extension que en un contexto futuro sí está lista
- Regla vieja vs regla actual después de un cambio comercial

### F. Contexto insuficiente
Queries que requieren más de lo que un solo chunk puede entregar.

Casos:
- Query que requiere combinar dos chunks de distintas secciones
- Query que requiere chunk + navegación de grafo (relación no capturada en embedding)
- Query que requiere metadata no incluida en texto chunkable
- Top-k trae partes correctas pero ninguna tiene la conclusión completa

### G. Ruido deliberado
Chunks con palabras similares pero irrelevantes que deberían ser filtrados.

Casos:
- Chunk con muchas ocurrencias de "WhatsApp" pero sin regla comercial
- Documento con términos atractivos ("automático", "inteligente", "full") pero sin sustento real
- Queries con mezcla de español e inglés técnico
- Queries vagas o incompletas

### H. Inducción al LLM
Queries que invitan a un LLM futuro a completar con conocimiento externo o prometer capacidades.

Casos:
- Preguntas que fuerzan respuesta aunque el knowledge no alcance
- Preguntas que piden prometer plazos, costos o capacidades no documentadas
- Preguntas que insinúan que "seguro se puede" sin evidencia

## 6. Casos adversariales

Ver `golden_cases/breaking_point_cases.json` con 25 casos distribuidos en las 8 familias.

## 7. Métricas

### Retrieval

| Métrica | Descripción |
|---------|-------------|
| `recall@k` | Fracción de conceptos esperados recuperados en top-k |
| `precision@k` | Fracción de resultados relevantes en top-k |
| `MRR` | Mean Reciprocal Rank del primer concepto esperado |
| `top1_expected` | ¿El concepto esperado está en rank 1? |
| `top3_expected` | ¿El concepto esperado está en rank 1-3? |
| `top5_expected` | ¿El concepto esperado está en rank 1-5? |
| `forbidden_concept_in_top3` | ¿Apareció algún concepto prohibido en top-3? |
| `concept_confusion_rate` | Cantidad de conceptos similares pero incorrectos en top-k |
| `scope_leak_rate` | Cantidad de resultados fuera del scope esperado |
| `version_conflict_rate` | ¿Apareció una versión obsoleta en vez de la vigente? |
| `no_result_rate` | ¿El retrieval devolvió 0 resultados? |
| `latency_ms` | Tiempo de retrieval por query |
| `estimated_cost` | Costo estimado de API de embeddings |

### Grounding (para futura evaluación con LLM)

| Métrica | Descripción |
|---------|-------------|
| `groundedness` | ¿La respuesta usa solo evidencia recuperada? |
| `hallucination_rate` | ¿La respuesta inventa información no soportada? |
| `answer_correctness` | ¿La respuesta es correcta según el knowledge? |
| `unsupported_claim_rate` | Claims sin chunk que los respalde |
| `required_evidence_coverage` | Fracción de evidencia necesaria presente en top-k |
| `answer_should_refuse_or_limit` | ¿La respuesta correcta sería negarse o limitar? |

## 8. Formato de golden answers

Cada caso en `golden_cases/breaking_point_cases.json` sigue esta estructura:

```json
{
  "case_id": "bp_01",
  "category": "overpromise_comercial",
  "query": "¿Ya podemos vender Step-to-Action como listo?",
  "risk_level": "high",
  "expected_chunk_ids": [],
  "expected_concepts": ["planned_extension", "commercial_limits", "step_to_action"],
  "acceptable_concepts": ["sales_diagnosis"],
  "forbidden_concepts": ["ready_today", "sellable_today", "disponible_productivamente"],
  "required_metadata_filters": [],
  "required_graph_nodes": ["step_to_action", "planned_extension", "commercial_limits"],
  "expected_behavior": "Debe indicar que Step-to-Action es planned_extension y limitar expectativas comerciales",
  "pass_criteria": "top3_contains_expected",
  "likely_failure_modes": ["overpromise_risk", "embedding_ranking_problem"],
  "recommended_fix_if_fails": "Mejorar contenido de chunk sobre Step-to-Action con forbidden concepts explícitos",
  "architecture_implication": "vector_backend_not_the_problem"
}
```

### Campos

| Campo | Descripción |
|-------|-------------|
| `case_id` | Identificador único del caso |
| `category` | Familia de fallo (A-H) |
| `query` | Texto de la query adversarial |
| `risk_level` | `low` / `medium` / `high` (impacto comercial si falla) |
| `expected_chunk_ids` | IDs de chunks exactos que deberían aparecer (opcional) |
| `expected_concepts` | Conceptos que deben estar presentes en los resultados |
| `acceptable_concepts` | Conceptos aceptables pero no obligatorios |
| `forbidden_concepts` | Conceptos que NUNCA deben aparecer |
| `required_metadata_filters` | Filtros de metadata que deberían aplicarse |
| `required_graph_nodes` | Nodos del grafo necesarios para responder completamente |
| `expected_behavior` | Descripción del comportamiento esperado |
| `pass_criteria` | `top1_contains_expected` / `top3_contains_expected` / `top5_contains_expected` |
| `likely_failure_modes` | Array de modos de fallo probables |
| `recommended_fix_if_fails` | Qué hacer si falla |
| `architecture_implication` | Qué implica este fallo para la arquitectura |

### Clasificación de `architecture_implication`

| Valor | Significado |
|-------|-------------|
| `vector_backend_not_the_problem` | El fallo se resuelve con mejor contenido, metadata o filtros |
| `content_gap` | Falta contenido en el corpus |
| `chunking_problem` | El chunking no captura la semántica necesaria |
| `embedding_ranking_problem` | El ranking de embeddings no logra diferenciar conceptos |
| `metadata_filter_needed` | Hace falta un filtro por metadata que no existe o no se aplica |
| `scope_filter_missing` | El scope filter no está correctamente implementado |
| `graph_navigation_needed` | Hace falta navegación de grafo para complementar retrieval |
| `reranker_needed` | El ranking coseno no alcanza, hace falta reranking (LLM o cross-encoder) |
| `hybrid_search_needed` | Hace falta combinar búsqueda lexical + vectorial |
| `versioning_needed` | El versionado de documentos no está siendo respetado |
| `llm_grounding_problem` | El fallo sería del LLM al generar respuesta, no del retrieval |
| `possible_milvus_case` | El caso sugiere que Milvus podría ser necesario por escala/calidad vectorial |
| `possible_arangodb_case` | El caso sugiere que ArangoDB podría ser necesario por complejidad de grafo |
| `requires_more_corpus` | El corpus actual no cubre el caso |

## 9. Dataset de prueba

25 casos en `golden_cases/breaking_point_cases.json`, distribuidos en:

| Familia | Casos | IDs |
|---------|-------|-----|
| A. Confusión semántica | 4 | bp_01 – bp_04 |
| B. Overpromise comercial | 5 | bp_05 – bp_09 |
| C. Ambigüedad técnica | 3 | bp_10 – bp_12 |
| D. Multi-tenant / scope leakage | 3 | bp_13 – bp_15 |
| E. Versionado / actualidad | 2 | bp_16 – bp_17 |
| F. Contexto insuficiente | 3 | bp_18 – bp_20 |
| G. Ruido deliberado | 3 | bp_21 – bp_23 |
| H. Inducción al LLM | 2 | bp_24 – bp_25 |

### Distribución de riesgo

- **Alto**: 12 casos (overpromise, scope leakage, versionado crítico)
- **Medio**: 10 casos (confusión semántica, contexto insuficiente, ruido)
- **Bajo**: 3 casos (ambigüedad técnica leve, inducción LLM controlada)

## 10. Diseño de corrida futura

Cuando se implemente la ejecución real:

```bash
cd SrvRestAstroLS_v1

# Corrida completa con retrieval real (requiere DB + embeddings)
uv run python lab/postgres-knowledge-retrieval-breaking-points/run_experiment.py \
  --golden golden_cases/breaking_point_cases.json \
  --limit 5 \
  --output-prefix breaking_points_20260609

# Modo offline (sin DB, solo validación del dataset)
uv run python lab/postgres-knowledge-retrieval-breaking-points/run_experiment.py \
  --dry-run

# Generar reporte
uv run python lab/postgres-knowledge-retrieval-breaking-points/scripts/generate_report.py \
  --results-file results/breaking_points_20260609_120000.json

# Generar infografía
uv run python lab/postgres-knowledge-retrieval-breaking-points/scripts/generate_infographics.py \
  --results-file results/breaking_points_20260609_120000.json
```

### Flujo de corrida

1. Cargar golden cases desde `golden_cases/breaking_point_cases.json`
2. Para cada caso:
   a. Ejecutar retrieval contra pgvector (top-10)
   b. Analizar resultados contra expected/forbidden concepts
   c. Clasificar modos de fallo
   d. Asignar architecture_implication
3. Generar matriz de ruptura
4. Generar JSON + Markdown + HTML
5. Documentar conclusión en README

### Modos de ejecución

| Modo | Descripción |
|------|-------------|
| `full` | Retrieval real contra DB con embeddings |
| `dry-run` | Solo valida el dataset, sin tocar DB |
| `offline-classify` | Clasifica resultados previos desde archivo JSON |

## 11. Resultados esperados

### Outputs

- `results/{prefix}.json`: resultados completos con scoring por caso
- `results/{prefix}.md`: reporte ejecutivo/técnico
- `results/{prefix}_breaking_matrix.md`: matriz de puntos de ruptura
- `infografias/{prefix}_infografia.html`: visualización HTML

### Matriz de ruptura

| case_id | category | pass/fail | likely_failure_mode | recommended_fix | architecture_implication |
|---------|----------|-----------|---------------------|-----------------|--------------------------|
| bp_01 | overpromise_comercial | fail | overpromise_risk | Mejorar contenido chunk | vector_backend_not_the_problem |
| bp_13 | scope_leakage | fail | scope_filter_missing | Filtro obligatorio por scope | metadata_filter_needed |
| bp_18 | contexto_insuficiente | fail | graph_navigation_needed | PostgreSQL recursive CTE | possible_arangodb_case |

### Criterio de aceptación

Se considera que PostgreSQL es suficiente si:
- ≥70% de casos pasan
- 0 casos de overpromise crítico fallan
- Los fallos se clasifican como `vector_backend_not_the_problem`, `content_gap`, `metadata_filter_needed` o `reranker_needed`
- Ningún fallo requiere forzosamente Milvus o ArangoDB

Se considera que PostgreSQL es insuficiente si:
- <60% de casos pasan
- Algún caso crítico de overpromise falla
- Los fallos se clasifican como `possible_milvus_case` o `possible_arangodb_case`
- Casos con metadata y contenido óptimos siguen fallando por límite del backend vectorial

## 12. Criterios de decisión

El laboratorio debe poder concluir una de estas opciones:

| Opción | Significado |
|--------|-------------|
| **A** | PostgreSQL 18 + pgvector alcanza para primera etapa sin cambios |
| **B** | PostgreSQL alcanza con mejoras de metadata filters / contenido / reranking |
| **C** | PostgreSQL alcanza para retrieval pero requiere tablas de grafo con recursive CTE |
| **D** | PostgreSQL necesita hybrid search (BM25 + vectorial) |
| **E** | PostgreSQL no alcanza por escala/latencia y Milvus debe evaluarse |
| **F** | PostgreSQL no alcanza por complejidad relacional y ArangoDB debe evaluarse |
| **G** | No decidir todavía; falta corpus mayor |

### Reglas de interpretación

| Si el fallo se resuelve con... | Entonces... |
|-------------------------------|-------------|
| mejorar el knowledge o agregar metadata | **NO** justifica Milvus/ArangoDB |
| filtros por scope/package/runtime | **NO** justifica Milvus/ArangoDB |
| reranking (cross-encoder o LLM) | **NO** justifica ArangoDB |
| tabla de grafo con recursive CTE | **NO** justifica ArangoDB hasta que escala o profundidad lo exijan |
| escala vectorial (>50k chunks o latencia) | **recién ahí** considerar Milvus |
| navegación relacional profunda (>5 niveles, >10 conexiones/nodo) | **recién ahí** considerar ArangoDB |
| hallucination del LLM en la respuesta | resolver con grounding/prompt/evidence, **no** con base de datos |

## 13. Riesgos y límites del laboratorio

### Riesgos conocidos

| Riesgo | Impacto | Mitigación |
|--------|---------|------------|
| Dataset pequeño (25 casos) puede no cubrir todos los bordes | Falsos positivos de suficiencia | Diseñado para expandirse; los casos son modulares |
| Sin ejecución real contra DB, las conclusiones son teóricas | No validación empírica | El diseño está listo para ejecutarse cuando haya DB + embeddings |
| Sin LLM en el loop, no se mide grounding real | No se puede evaluar hallucination_rate | Las métricas de grounding están documentadas para futura fase con LLM |
| Los casos asumen contenido existente en el corpus | Si el chunk no existe, el fallo es content_gap, no del retrieval | La clasificación architecture_implication distingue content_gap |
| No hay baseline de Milvus/ArangoDB para comparar | No se puede afirmar que Milvus resolvería el caso | Los casos possible_milvus_case / possible_arangodb_case son hipotéticos hasta tener benchmark real |

### Límites del laboratorio

- No ejecuta llamadas reales a OpenAI (solo simula retrievals contra embeddings existentes)
- No mide latencia de red, solo latencia de retrieval local
- No evalúa costos reales de API
- No incluye evaluación con LLM (hallucination, groundedness)
- No incluye comparación contra Milvus o ArangoDB (son objetivos de evaluación, no dependencias)

## 14. Próximos pasos recomendados

1. **Ejecutar corrida base** contra el corpus actual (40 chunks, 40 embeddings, pgvector) para obtener baseline de ruptura
2. **Ampliar corpus** con más documentos adversariales (documentos con ruido deliberado, versiones conflictivas, términos ambiguos)
3. **Implementar dry-run** del experimento sin DB para validar el dataset completo
4. **Implementar clasificación automática** de architecture_implication basada en resultados
5. **Agregar evaluación con LLM** para medir groundedness, hallucination_rate y answer_correctness
6. **Expandir golden cases** a 50+ casos cubriendo más bordes (cross-package, cross-scope, cross-customer)
7. **Migrar a script de ejecución real** contra pgvector cuando el corpus esté listo
8. **Comparar contra Milvus** si los resultados de pgvector muestran límites de escala vectorial
9. **Comparar contra ArangoDB** si los resultados muestran límites de navegación relacional

## 15. Relación con PostgreSQL, pgvector, Milvus y ArangoDB

```
                          ┌─────────────────────────────────┐
                          │      Team360 Knowledge Stack     │
                          └─────────────────────────────────┘
                                        │
                    ┌───────────────────┴───────────────────┐
                    │                                       │
            ┌───────▼───────┐                       ┌───────▼───────┐
            │  PostgreSQL 18 │                       │   Milvus /    │
            │  (transaccional│                       │   ArangoDB    │
            │   + pgvector)  │                       │ (evaluación)  │
            └───────┬───────┘                       └───────┬───────┘
                    │                                       │
        ┌───────────┼───────────┐                           │
        │           │           │                           │
  ┌─────▼─────┐ ┌──▼──┐ ┌──────▼──────┐                   │
  │   Fase     │ │Fase │ │   Fase     │                   │
  │   1.6b     │ │1.6c │ │   1.6d     │◄── este lab───────┘
  │ retrieval  │ │graph│ │ breaking   │
  │ quality    │ │nav  │ │ points     │
  └───────────┘ └─────┘ └─────┬───────┘
                              │
                    ┌─────────▼─────────┐
                    │  ¿Se rompe?       │
                    │  ¿Dónde?          │
                    │  ¿Se arregla con  │
                    │  metadata/filtros │
                    │  o requiere       │
                    │  Milvus/Arango?   │
                    └───────────────────┘
```

### Reglas de engagement con Milvus

**Milvus entra en la conversación solo si:**
- pgvector no puede mantener latencia <500ms con >50k chunks
- La calidad de ranking coseno es insuficiente incluso con metadata óptima
- El corpus supera 100k chunks y los índices IVF/IVFFlat de pgvector no escalan
- Hace falta hybrid search (BM25 + vectorial) para términos técnicos exactos

**Milvus NO entra en la conversación si:**
- El fallo se resuelve con mejor chunking o contenido
- El fallo se resuelve con filtros de metadata o scope
- El fallo se resuelve con reranking (cross-encoder o LLM)
- El fallo es por hallucination del LLM al generar respuesta

### Reglas de engagement con ArangoDB

**ArangoDB entra en la conversación solo si:**
- Se necesita navegación de grafo con >5 niveles de profundidad
- El grafo tiene >10 conexiones por nodo en promedio
- Se necesitan algoritmos de grafo nativos (shortest-path, PageRank, k-shortest-paths)
- La latencia de recursive CTE en PostgreSQL supera 2s para traversals frecuentes

**ArangoDB NO entra en la conversación si:**
- La navegación necesaria tiene <=4 niveles de profundidad
- El grafo es ralo (<5 conexiones/nodo)
- PostgreSQL recursive CTE con índices GIN cubre el caso
- La navegación se puede reemplazar con node_path + filtro por prefijo

## 16. Criterio para no sumar infraestructura

**Regla fundamental**: Si una falla se resuelve mejorando el knowledge, agregando metadata, aplicando filtros o incorporando reranking, **NO se debe justificar Milvus ni ArangoDB**.

### Árbol de decisión

```
¿Falló un caso?
│
├─ ¿Falta contenido? → content_gap → mejorar corpus
│
├─ ¿El chunking no captura la semántica? → chunking_problem → mejorar chunking
│
├─ ¿Falta metadata que existe en el documento? → metadata_filter_needed → agregar filtro
│
├─ ¿Falta filtro de scope? → scope_filter_missing → aplicar scope filter
│
├─ ¿El chunk correcto está en top-5 pero no en top-1? → reranker_needed → agregar reranking
│
├─ ¿El chunk correcto NO está en top-10? → embedding_ranking_problem → evaluar:
│   ├─ ¿Mejorando contenido/metadata se soluciona? → vector_backend_not_the_problem
│   ├─ ¿El corpus es pequeño (<10k)? → requires_more_corpus
│   └─ ¿El corpus es grande (>50k) y persiste? → possible_milvus_case
│
├─ ¿Hace falta combinar retrieval + navegación? → graph_navigation_needed → evaluar:
│   ├─ ¿PostgreSQL recursive CTE alcanza? → implementar tablas de grafo
│   └─ ¿Se necesita >5 niveles o algoritmos nativos? → possible_arangodb_case
│
├─ ¿Hace falta búsqueda lexical exacta? → hybrid_search_needed → evaluar pgvector + tsvector
│   └─ ¿pgvector + tsvector no alcanza? → possible_milvus_case
│
└─ ¿El LLM inventaría al responder? → llm_grounding_problem → mejorar prompts/evidence
```

## Outputs del laboratorio

| Archivo | Formato | Contenido |
|---------|---------|-----------|
| `results/{prefix}.json` | JSON | Resultados completos de todos los casos |
| `results/{prefix}.md` | Markdown | Reporte ejecutivo/técnico |
| `results/{prefix}_breaking_matrix.md` | Markdown | Matriz de puntos de ruptura |
| `infografias/{prefix}_infografia.html` | HTML | Visualización ejecutiva |

## No toca

- ❌ Pipeline productivo
- ❌ Frontend
- ❌ Routes / endpoints HTTP
- ❌ diagnosis / automation_diagnosis
- ❌ Milvus (es objeto de evaluación)
- ❌ ArangoDB (es objeto de evaluación)
- ❌ Documentos approved/drafts
- ❌ Migraciones
- ❌ Embeddings (usa los existentes)
- ❌ Llamadas reales a OpenAI (en esta fase)
- ❌ Secrets
- ❌ Configuración productiva

## Conclusión esperada

El laboratorio debería poder responder:

1. **¿PostgreSQL 18 + pgvector alcanza?** → Sí, con opciones A-D.
2. **¿Dónde se rompe exactamente?** → En casos específicos documentados en la matriz de ruptura.
3. **¿Se arregla con lo que ya tenemos (metadata, filtros, contenido)?** → Para la mayoría de los casos, sí.
4. **¿Cuándo considerar Milvus?** → Cuando el corpus supere 50k-100k chunks y pgvector no escale.
5. **¿Cuándo considerar ArangoDB?** → Cuando la navegación de grafo requiera >5 niveles profundos o algoritmos nativos.

---

_Experiment design: Fase 1.6d — PostgreSQL Knowledge Retrieval Breaking Points_
_Última actualización: 2026-06-09_
