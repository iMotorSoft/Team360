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

## Uso

### Requisitos

- Python 3.12+
- `OPENAI_API_KEY` o `OpenAI_Key_JAI_query` en entorno para embedding de query
- `DB_PG_V360_URL` o `TEAM360_DB_URL_PSQL` para conexión a BD
- Backend dependencies (`uv` en `backend/`)
- Migraciones 003+ aplicadas, embeddings generados (Fase 1.5)

### Ejecución

Ejecutar desde `SrvRestAstroLS_v1/backend/` (donde `uv` tiene las dependencias):

```bash
cd SrvRestAstroLS_v1/backend

# Dry run (solo validar golden cases, sin DB ni OpenAI)
uv run python ../lab/postgres-knowledge-retrieval-breaking-points/run_breaking_points.py --dry-run

# Run completo (25 casos, default limit=5)
uv run python ../lab/postgres-knowledge-retrieval-breaking-points/run_breaking_points.py

# Run con primeros 3 casos
uv run python ../lab/postgres-knowledge-retrieval-breaking-points/run_breaking_points.py --max-cases 3

# Run con opciones custom
uv run python ../lab/postgres-knowledge-retrieval-breaking-points/run_breaking_points.py \
  --limit 10 \
  --min-score 0.3 \
  --output-prefix my_breaking_run

# Generar reporte detallado
uv run python ../lab/postgres-knowledge-retrieval-breaking-points/scripts/generate_report.py

# Generar infografía HTML
uv run python ../lab/postgres-knowledge-retrieval-breaking-points/scripts/generate_infographics.py

# Con archivo específico
uv run python ../lab/postgres-knowledge-retrieval-breaking-points/scripts/generate_report.py \
  --results-file ../lab/postgres-knowledge-retrieval-breaking-points/results/breaking_points_20260609_150932.json
```

### Variables de entorno

| Variable | Requerida | Descripción |
|----------|-----------|-------------|
| `OPENAI_API_KEY` | Sí | API key de OpenAI para embedding de query |
| `OpenAI_Key_JAI_query` | Sí (fallback) | Fallback si `OPENAI_API_KEY` no está seteada |
| `DB_PG_V360_URL` | Sí | DSN PostgreSQL con base `team360` |
| `TEAM360_DB_URL_PSQL` | Sí (fallback) | Fallback si `DB_PG_V360_URL` no está seteada |

No hardcodear API keys. No loggearlas completas (solo preview 8 chars).

### Parámetros de `run_breaking_points.py`

| Parámetro | Default | Descripción |
|-----------|---------|-------------|
| `--limit` | `5` | Resultados por query (1–50) |
| `--min-score` | `None` | Score mínimo de similitud (0–1) |
| `--embedding-version` | `team360-openai-small-1536-v1` | Versión de embedding |
| `--organization-code` | `team360_live` | Código de organización |
| `--workspace-code` | `team360_public_site` | Código de workspace |
| `--knowledge-scope-code` | `ks_team360_sales_diagnosis` | Knowledge scope |
| `--output-prefix` | timestamp | Prefijo para archivos de output |
| `--max-cases` | `None` | Ejecutar solo primeros N casos |
| `--dry-run` | `False` | Validar golden cases sin DB ni OpenAI |

## Outputs del laboratorio

| Archivo | Formato | Contenido |
|---------|---------|-----------|
| `results/{prefix}.json` | JSON | Resultados completos de todos los casos |
| `results/{prefix}.md` | Markdown | Reporte ejecutivo con decisión |
| `results/{prefix}_detailed_report.md` | Markdown | Reporte detallado por caso |
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

## Ejecución real — Resultados baseline (2026-06-09)

### Resumen

| Métrica | Valor |
|---------|-------|
| Casos totales | 25 |
| Pasaron | 5 (20%) |
| Fallaron | 20 (80%) |
| Alto riesgo pasaron | 2/11 (18%) |
| Conceptos prohibidos top-3 | 0 |
| Latencia promedio | 823.5ms |
| Score total | -31 (rango -75 a 75) |

### Decisión algorítmica

**D. Evaluar Milvus/ArangoDB — pgvector muestra límites de escala/calidad.**

### Interpretación humana

La decisión algorítmica es "D" por el bajo pass rate (20%), pero el análisis real de los fallos indica que **20/20 fallos son `embedding_ranking_problem`**, lo que significa que el corpus actual (40 chunks) **no contiene el texto de los conceptos evaluados** en los golden cases adversariales.

Cuando los chunks SÍ contienen los conceptos (como `automatizable ≠ sellable_today`, `diagnostic_code`, `planned_extension`, `scope isolation`), el retrieval funciona correctamente (PASS en top-1 o top-3).

**Conclusión humana: el punto de ruptura actual es content_gap, no el backend vectorial.**

Esto valida exactamente el propósito del laboratorio: el sistema no "se rompe" por límite de pgvector, sino porque el corpus no cubre los conceptos adversariales. A medida que el corpus crezca con chunks que incluyan reglas comerciales, límites de alcance y descripciones de capacidades, el pass rate subirá sin cambiar de base de datos.

### Resultados por categoría

| Categoría | Pass/Fail |
|-----------|-----------|
| A. Confusión semántica | 2/4 pass (bp_01, bp_02 ok; bp_03, bp_04 fail) |
| B. Overpromise comercial | 2/5 pass (bp_08, bp_09 ok; bp_05, bp_06, bp_07 fail) |
| C. Ambigüedad técnica | 0/3 pass |
| D. Multi-tenant / scope | 1/3 pass (bp_14 ok; bp_13, bp_15 fail) |
| E. Versionado / actualidad | 0/2 pass |
| F. Contexto insuficiente | 0/3 pass |
| G. Ruido deliberado | 0/3 pass |
| H. Inducción al LLM | 0/2 pass |

### Casos críticos que PASARON

- `bp_01`: diferencia entre automatizable y vendible ✅ top-3
- `bp_02`: diagnostic_code vs diagnosis result ✅ top-1
- `bp_08`: diagnóstico asigna código de seguimiento → planned_extension ✅ top-1
- `bp_09`: automatable ≠ sellable_today ✅ top-1
- `bp_14`: diagnóstico de ventas para Team360 ✅ top-3 (scope filtering)

### Casos críticos que FALLARON (todos por content_gap / corpus insuficiente)

- `bp_03`: step_to_action no está en chunks
- `bp_05`: "Step-to-Action listo" — no hay chunk con planned_extension + step_to_action
- `bp_06`: "WhatsApp handoff" — no hay chunk que describa WhatsApp handoff
- `bp_07`: "lead capture" — no hay chunk sobre lead capture como planned_extension
- `bp_13`: "cross_customer_isolation" — concepto existe en modelo pero no en chunk text
- `bp_16/17`: versionado — no hay chunks con versión vigente vs obsoleta
- `bp_18`: contexto combinado — requiere múltiples chunks
- `bp_24`: inducción LLM — no hay chunk de "no prometer sin diagnóstico"

### Architecture implications detectadas

| Implicación | Casos | Interpretación |
|-------------|-------|----------------|
| `embedding_ranking_problem` | 20 | El concepto no está en el texto del chunk (content_gap) |
| `vector_backend_not_the_problem` | 4 | El retrieval funciona cuando el contenido existe |
| `metadata_filter_needed` | 1 | Scope filtering funciona correctamente |

---

## RAG failure audit extension — Fase 1.6e

### Objetivo

Construir un módulo de auditoría RAG dentro del laboratorio que clasifique fallos en 6 categorías precisas, sin culpar automáticamente al vector store. El objetivo es que *cada fallo* tenga un diagnóstico accionable: mejorar contenido, agregar metadata, aplicar filtros, incorporar reranking, o —solo en última instancia— evaluar Milvus/ArangoDB.

### Las 6 categorías de fallo

| Categoría | Clasificación | Significado |
|-----------|---------------|-------------|
| **CONTENT_GAP** | `content_gap` | El corpus no contiene el concepto o regla que la pregunta requiere. No es problema del vector store. |
| **EMBEDDING_RANKING_PROBLEM** | `reranker_needed` / `hybrid_search_needed` | El chunk correcto existe en el corpus pero está rankeado detrás de chunks semánticamente cercanos e incorrectos. |
| **SCOPE_LEAKAGE** | `scope_filter_missing` / `metadata_filter_needed` | La pregunta cruza cliente, workspace, package o dominio. El retrieval trae resultados fuera del scope autorizado. |
| **IMPOSSIBLE_FILTER** | `metadata_absent` | La pregunta requiere filtrar por metadata que no existe en el modelo de datos. No es problema de ranking ni de BD. |
| **DEEP_TRAVERSAL_UNSUPPORTED** | `graph_navigation_needed` | La pregunta requiere combinar 3+ piezas de información dispersas o navegar relaciones de grafo no capturadas en el embedding plano. |
| **LATENCY_TRAP** | `content_gap` / `reranker_needed` | La pregunta se responde rápido pero con contenido incompleto, genérico, incorrecto o peligroso. Latencia baja no es calidad. |

### ¿Por qué no culpar automáticamente al vector store?

El árbol de decisión del laboratorio (sección 16) ya establece que antes de culpar a pgvector, Milvus o ArangoDB, se debe descartar:

1. **Falta de contenido** (content_gap): El corpus no cubre el tema. Agregar chunk.
2. **Chunking insuficiente**: El chunk no captura la semántica necesaria. Re-chunking.
3. **Metadata ausente**: El campo metadata no existe. Agregar al modelo.
4. **Filtro de scope faltante**: El scope filter no se aplica. Agregar filtro.
5. **Ranking insuficiente**: El chunk correcto está en top-5 pero no en top-1. Reranking.

Solo si todas las anteriores fallan y el corpus supera 50k-100k chunks *entonces* considerar Milvus.
Solo si la navegación requiere >5 niveles de grafo o algoritmos nativos *entonces* considerar ArangoDB.

### Cómo interpretar fallos en la auditoría

Para cada caso en `golden_cases/rag_audit_failure_cases.json`, cuando se ejecute retrieval real:

1. Ejecutar query contra pgvector (top-5/10).
2. Comparar `expected_retrieval_evidence` contra chunks recuperados.
3. Si ningún chunk contiene `expected_retrieval_evidence` -> **CONTENT_GAP** (si el concepto no existe en el corpus) o **EMBEDDING_RANKING_PROBLEM** (si existe pero no rankeó).
4. Si algún chunk recuperado pertenece a otro scope -> **SCOPE_LEAKAGE**.
5. Si la query pide filtro que no existe en metadata -> **IMPOSSIBLE_FILTER** (diagnosticar sin correr retrieval).
6. Si la query requiere combinar 3+ chunks y top-k solo trae piezas aisladas -> **DEEP_TRAVERSAL_UNSUPPORTED**.
7. Si el contenido recuperado es genérico/insuficiente para responder -> **LATENCY_TRAP**.

### Cómo decidir entre fixes

| Fallo clasificado | Fix recomendado |
|-------------------|-----------------|
| CONTENT_GAP | Agregar chunk con el contenido faltante. Marcar `should_trigger_content_patch: true`. |
| EMBEDDING_RANKING_PROBLEM | Probar reranking cross-encoder. Si persiste, hybrid search. Marcar `should_trigger_reranker` o `should_trigger_hybrid_search`. |
| SCOPE_LEAKAGE | Agregar/forzar scope filter en retrieval. Agregar chunk restrictivo de alcance. |
| IMPOSSIBLE_FILTER | Agregar metadata field al modelo de datos. No tocar BD vectorial. |
| DEEP_TRAVERSAL_UNSUPPORTED | Chunk narrativo que describa la relación. Si no alcanza, grafo PostgreSQL recursive CTE. ArangoDB solo si >5 niveles. |
| LATENCY_TRAP | Agregar chunk con contenido específico. Reranker si el contenido existe pero rankea bajo. |

### Dataset de auditoría

Ver `golden_cases/rag_audit_failure_cases.json` con **36 casos** (6 por categoría). Cada caso incluye:

- `correct_human_answer`: Respuesta correcta que un humano experto daría.
- `expected_retrieval_evidence`: Conceptos que deben aparecer en los chunks recuperados.
- `forbidden_answer_patterns`: Patrones que el RAG no debe generar.
- `likely_pathological_rag_answer`: Lo que un RAG sin las defensas adecuadas probablemente respondería.
- `technical_diagnosis`: Por qué ocurre el fallo desde la perspectiva del sistema.
- `expected_failure_classification`: Categoría de fallo esperada.
- `architecture_implication`: Implicación arquitectónica concreta.
- `recommended_fix_if_fails`: Qué hacer si el caso falla.
- `should_trigger_*`: Banderas booleanas que indican qué acción recomienda el caso.

### Inventario de casos (generado)

Ejecutar para generar inventario estático sin DB ni APIs:

```bash
cd SrvRestAstroLS_v1/backend
uv run python ../lab/postgres-knowledge-retrieval-breaking-points/scripts/generate_failure_case_report.py
```

Output: `results/rag_failure_case_inventory.md`

### Próximos pasos (futura corrida)

Cuando se implemente la ejecución real de auditoría:

1. Para cada caso en `rag_audit_failure_cases.json`, ejecutar retrieval contra pgvector.
2. Comparar `expected_retrieval_evidence` contra top-k.
3. Clasificar el fallo real vs la clasificación esperada.
4. Si la clasificación real difiere de la esperada, el caso está mal diseñado o el sistema se comportó inesperadamente.
5. Acumular matriz de confusión de clasificaciones.
6. Decidir si el sistema necesita content_patch, reranker, hybrid, graph, Milvus o ArangoDB basado en evidencia empírica, no en teoría.

---

## Reranking experiment — Fase 1.6g

### Objetivo

Medir si un reranker determinístico (oracle-lite de laboratorio) mejora el pass rate de los casos adversariales sobre pgvector top-k antes de evaluar Milvus, ArangoDB, hybrid search o cambios de infraestructura.

### Hipótesis

Si los fallos restantes post-knowledge-coverage son `embedding_ranking_problem` (no recall ni content_gap), un reranker debería rescatar casos donde el chunk correcto existe en top-N pero está rankeado fuera de top-K.

### Estrategia

- **Candidates**: pgvector top-N (default: 20)
- **Baseline**: primeros K resultados sin rerank (default: 5)
- **Reranker**: determinístico, sin modelo externo, sin LLM
  - `rerank_score` = concept_match × 10 (expected) + acceptable_match × 3 — forbidden_match × 50 + title_boost × 2 + critical_terms × 1 + vector_score × 0.5
  - Normaliza términos (lowercase, `_`/`-` → espacio, colapsa whitespace, remueve acentos)
  - Términos críticos: planned_extension, no vender, automatable, sellable, whatsapp_handoff, lead_capture, diagnostic_code, vera, knowledge_scope, cross_customer_isolation, commercial_limits, concrete_orientation, step_to_action, offer_decision, minimum_slots, useful_diagnosis
- **Evaluación**: se corre `evaluate_normalized` (matching normalizado) tanto en baseline como en reranked
- **Referencia**: se conserva `evaluate_strict` (matching exacto de `run_breaking_points.py`) para comparabilidad

### Outputs

| Archivo | Contenido |
|---------|-----------|
| `results/reranking_experiment_{timestamp}.json` | Resultados completos con baseline, reranked y scores |
| `results/reranking_experiment_{timestamp}.md` | Reporte ejecutivo con decisión arquitectónica |

### Decision rules

- Si pass rate mejora significativamente (>15pp) y el candidato correcto está en top-N (>80%): **pgvector + reranker es el próximo paso**
- Si el candidato correcto no está en top-N (<60%): **el problema es recall/content_gap, no ranking**
- Si forbidden concepts persisten: **safety/commercial filtering necesario**
- Si fallan casos de grafo: **graph navigation necesario**
- No se recomienda Milvus/ArangoDB sin evidencia de que reranker no alcanza

### Ejecución

```bash
cd SrvRestAstroLS_v1/backend

# Experimento completo (25 casos, top-20 candidates, top-5 eval)
uv run python ../lab/postgres-knowledge-retrieval-breaking-points/run_reranking_experiment.py

# Primeros 3 casos
uv run python ../lab/postgres-knowledge-retrieval-breaking-points/run_reranking_experiment.py --max-cases 3

# Custom
uv run python ../lab/postgres-knowledge-retrieval-breaking-points/run_reranking_experiment.py \
  --top-n 20 --top-k 5

# Dry run (validación sin DB)
uv run python ../lab/postgres-knowledge-retrieval-breaking-points/run_reranking_experiment.py --dry-run

# Generar reporte detallado desde resultados existentes
uv run python ../lab/postgres-knowledge-retrieval-breaking-points/scripts/generate_reranking_report.py
```

### No toca

- ❌ Pipeline productivo
- ❌ Frontend / routes / endpoints HTTP
- ❌ diagnosis / automation_diagnosis
- ❌ Milvus / ArangoDB (son objetos de evaluación)
- ❌ Documentos approved/drafts
- ❌ Migraciones
- ❌ Re-embedding de chunks
- ❌ LLM / chat completions
- ❌ Secrets / API keys hardcodeadas

---

## Non-oracle reranking experiment — Fase 1.6h

### Objetivo

Validar si un reranker que **NO usa golden answers** (expected_concepts, acceptable_concepts, forbidden_concepts) puede mejorar el retrieval de pgvector. Es una simulación más cercana a producción que el oracle-lite de Fase 1.6g.

### Diferencia clave con oracle-lite (1.6g)

| Aspecto | Oracle-lite (1.6g) | Non-oracle (1.6h) |
|---------|-------------------|-------------------|
| Usa expected_concepts para reordenar? | **Sí** (oráculo) | **No** |
| Señales del reranker | concept_match, forbidden_penalty, critical_terms | lexical_overlap, phrase_match, domain_vocabulary, safety_signals, metadata_boost, vector_score |
| Producción-ready? | No (solo laboratorio) | Más cercano (solo query + candidates) |
| Techo teórico | Alto (conoce la respuesta) | Limitado por señales léxicas |

### Estrategia

- **Candidates**: pgvector top-N (default: 20)
- **Baseline**: top-K sin rerank (default: 5)
- **Non-oracle reranker** (6 señales, 0 oráculo):

  | Señal | Peso | Descripción |
  |-------|------|-------------|
  | `vector_score` | 0.40 | Similaridad coseno original de pgvector |
  | `lexical_overlap` | 0.20 | Jaccard + coverage de tokens query↔candidate |
  | `phrase_match` | 0.15 | N-gramas (2,3) de query en texto del candidate |
  | `domain_term_score` | 0.10 | Vocabulario de dominio compartido query↔candidate |
  | `safety_signal_score` | 0.10 | Si query es comercial → boost por términos de safety en candidate |
  | `metadata_boost` | 0.05 | Mapping node_path → intención de query |
  | `risk_penalty` | -0.15 | Penaliza candidates genéricos si query es específica |

- **Golden cases**: usados SOLO para evaluación post-reranking, nunca para reordenar

### Clasificación de fallos (nueva)

| Clasificación | Significado |
|--------------|-------------|
| `correct_not_in_candidates` | El concepto esperado no existe en ningún candidate top-N (content_gap) |
| `semantic_gap_or_paraphrase_problem` | El concepto existe pero el overlap léxico query↔chunk es bajo (<0.15) → necesita cross-encoder |
| `reranker_not_powerful_enough` | El concepto existe y tiene overlap léxico, pero el reranker no lo impulsó lo suficiente |
| `forbidden_concepts_still_present` | Conceptos prohibidos en top-3 del reranked |

### Oracle gap

Se mide la diferencia contra el techo oracle-lite (68%):

`gap_to_oracle = oracle_lite_pass_rate - non_oracle_pass_rate`

Esto indica cuánto margen queda para un cross-encoder real.

### Ejecución

```bash
cd SrvRestAstroLS_v1/backend

# Experimento completo
uv run python ../lab/postgres-knowledge-retrieval-breaking-points/run_non_oracle_reranking_experiment.py

# Dry run
uv run python ../lab/postgres-knowledge-retrieval-breaking-points/run_non_oracle_reranking_experiment.py --dry-run

# Generar reporte detallado
uv run python ../lab/postgres-knowledge-retrieval-breaking-points/scripts/generate_non_oracle_reranking_report.py
```

### No toca

- ❌ Pipeline productivo
- ❌ Frontend / routes / endpoints HTTP
- ❌ diagnosis / automation_diagnosis
- ❌ Milvus / ArangoDB
- ❌ Documentos approved/drafts
- ❌ Migraciones / re-embedding / corpus
- ❌ LLM / chat completions
- ❌ Secrets / API keys hardcodeadas

---

_Experiment design & run: Fase 1.6d — PostgreSQL Knowledge Retrieval Breaking Points_
_RAG Failure Audit Extension: Fase 1.6e_
_Reranking Experiment: Fase 1.6g_
_Non-oracle Reranking Experiment: Fase 1.6h_
_Última actualización: 2026-06-09_
