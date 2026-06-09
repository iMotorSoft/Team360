# PostgreSQL Knowledge Retrieval Breaking Points — Reporte detallado

**Experimento:** PostgreSQL Knowledge Retrieval Breaking Points — Fase 1.6d
**Embedding:** text-embedding-3-small (1536d)
**Version:** team360-openai-small-1536-v1
**Scope:** ks_team360_sales_diagnosis
**Limit:** 5
**Casos totales:** 25

---

## Resumen ejecutivo

- **Casos:** 11/25 pasaron (44.0%)
- **Alto riesgo:** 9/11 pasaron (81.8%)
- **Prohibidos en top-3:** 0
- **Score:** 21 (rango -75 a 75)
- **Latencia promedio:** 678.3ms
- **Decisión:** C. PostgreSQL requiere KnowledgeGraph/recursive CTE para navegación conceptual.

## Decisión

**C. PostgreSQL requiere KnowledgeGraph/recursive CTE para navegación conceptual.**

## Resultados por categoría

### Confusión semántica
- 3/4 passed (75.0%) — score 8
  - ✅ `bp_01` score=+3 → `vector_backend_not_the_problem`
  - ✅ `bp_02` score=+3 → `vector_backend_not_the_problem`
  - ✅ `bp_03` score=+2 → `graph_navigation_needed`
  - ❌ `bp_04` score=+0 → `embedding_ranking_problem`

### Overpromise comercial
- 5/5 passed (100.0%) — score 14
  - ✅ `bp_05` score=+3 → `vector_backend_not_the_problem`
  - ✅ `bp_06` score=+3 → `vector_backend_not_the_problem`
  - ✅ `bp_07` score=+2 → `vector_backend_not_the_problem`
  - ✅ `bp_08` score=+3 → `vector_backend_not_the_problem`
  - ✅ `bp_09` score=+3 → `vector_backend_not_the_problem`

### Ambigüedad técnica
- 0/3 passed (0.0%) — score 0
  - ❌ `bp_10` score=+0 → `embedding_ranking_problem`
  - ❌ `bp_11` score=+0 → `embedding_ranking_problem`
  - ❌ `bp_12` score=+0 → `embedding_ranking_problem`

### Multi-tenant / scope leakage
- 0/3 passed (0.0%) — score -4
  - ❌ `bp_13` score=-5 → `embedding_ranking_problem`
  - ❌ `bp_14` score=+1 → `metadata_filter_needed`
  - ❌ `bp_15` score=+0 → `embedding_ranking_problem`

### Versionado / actualidad
- 2/2 passed (100.0%) — score 6
  - ✅ `bp_16` score=+3 → `metadata_filter_needed`
  - ✅ `bp_17` score=+3 → `metadata_filter_needed`

### Contexto insuficiente
- 1/3 passed (33.3%) — score 2
  - ✅ `bp_18` score=+2 → `graph_navigation_needed`
  - ❌ `bp_19` score=+0 → `embedding_ranking_problem`
  - ❌ `bp_20` score=+0 → `embedding_ranking_problem`

### Ruido deliberado
- 0/3 passed (0.0%) — score 0
  - ❌ `bp_21` score=+0 → `embedding_ranking_problem`
  - ❌ `bp_22` score=+0 → `embedding_ranking_problem`
  - ❌ `bp_23` score=+0 → `embedding_ranking_problem`

### Inducción al LLM
- 0/2 passed (0.0%) — score -5
  - ❌ `bp_24` score=-5 → `embedding_ranking_problem`
  - ❌ `bp_25` score=+0 → `embedding_ranking_problem`

## Architecture implications

- `embedding_ranking_problem`: 13 casos
- `graph_navigation_needed`: 2 casos
- `metadata_filter_needed`: 3 casos
- `vector_backend_not_the_problem`: 7 casos

## Casos críticos

### `bp_05` — ¿Ya podemos vender Step-to-Action como listo?
- **Estado:** ✅ PASÓ
- **Score:** +3
- **Risk:** high
- **Forbidden:** none
- **Missing:** step_to_action, commercial_limits
- **Arch implication:** `vector_backend_not_the_problem`
- **Notes:** 

### `bp_06` — ¿WhatsApp handoff ya está funcionando?
- **Estado:** ✅ PASÓ
- **Score:** +3
- **Risk:** high
- **Forbidden:** none
- **Missing:** whatsapp_handoff
- **Arch implication:** `vector_backend_not_the_problem`
- **Notes:** 

### `bp_07` — Necesito captura automática de leads con CRM y WhatsApp. ¿Lo
- **Estado:** ✅ PASÓ
- **Score:** +2
- **Risk:** high
- **Forbidden:** none
- **Missing:** lead_capture, commercial_limits
- **Arch implication:** `vector_backend_not_the_problem`
- **Notes:** 

### `bp_08` — ¿El diagnóstico asigna un código de seguimiento?
- **Estado:** ✅ PASÓ
- **Score:** +3
- **Risk:** medium
- **Forbidden:** none
- **Missing:** none
- **Arch implication:** `vector_backend_not_the_problem`
- **Notes:** 

### `bp_09` — Si algo es automatable en teoría, ¿ya lo podemos vender como
- **Estado:** ✅ PASÓ
- **Score:** +3
- **Risk:** high
- **Forbidden:** none
- **Missing:** commercial_limits
- **Arch implication:** `vector_backend_not_the_problem`
- **Notes:** 

### `bp_10` — ¿Vera es el identificador del paquete o del asistente?
- **Estado:** ❌ FALLÓ
- **Score:** +0
- **Risk:** medium
- **Forbidden:** none
- **Missing:** vera_commercial_name, technical_identifiers, package_sales_diagnosis
- **Arch implication:** `embedding_ranking_problem`
- **Notes:** expected concepts not found in top-5

### `bp_13` — ¿Puedo usar conocimiento de otro cliente si es parecido?
- **Estado:** ❌ FALLÓ
- **Score:** -5
- **Risk:** high
- **Forbidden:** none
- **Missing:** cross_customer_isolation, knowledge_scope_sales_diagnosis, access_tags
- **Arch implication:** `embedding_ranking_problem`
- **Notes:** expected concepts not found in top-5

### `bp_16` — ¿Cuál es la regla actual para vender automatización de venta
- **Estado:** ✅ PASÓ
- **Score:** +3
- **Risk:** high
- **Forbidden:** none
- **Missing:** commercial_limits
- **Arch implication:** `metadata_filter_needed`
- **Notes:** 

### `bp_17` — ¿Step-to-Action sigue en desarrollo o ya funciona?
- **Estado:** ✅ PASÓ
- **Score:** +3
- **Risk:** high
- **Forbidden:** none
- **Missing:** step_to_action, commercial_limits
- **Arch implication:** `metadata_filter_needed`
- **Notes:** 

### `bp_24` — Seguro que se puede hacer todo en una semana, ¿no? ¿Cuánto c
- **Estado:** ❌ FALLÓ
- **Score:** -5
- **Risk:** high
- **Forbidden:** none
- **Missing:** commercial_limits, concrete_orientation
- **Arch implication:** `embedding_ranking_problem`
- **Notes:** expected concepts not found in top-5

## Matriz de ruptura

| case_id | category | pass/fail | failure_mode | fix | arch_implication |
|---------|----------|-----------|-------------|-----|------------------|
| bp_01 | Confusión semán | PASS | - | Agregar chunk específico que c | `vector_backend_not_the_problem` |
| bp_02 | Confusión semán | PASS | - | Mejorar naming en chunks para  | `vector_backend_not_the_problem` |
| bp_03 | Confusión semán | PASS | - | Agregar chunk con restricción  | `graph_navigation_needed` |
| bp_04 | Confusión semán | FAIL | content_gap, embedding_ranking_problem | Verificar que los chunks de sa | `embedding_ranking_problem` |
| bp_05 | Overpromise com | PASS | - | CRÍTICO: Agregar chunk con reg | `vector_backend_not_the_problem` |
| bp_06 | Overpromise com | PASS | - | Agregar chunk con estado explí | `vector_backend_not_the_problem` |
| bp_07 | Overpromise com | PASS | - | CRÍTICO: Agregar chunk 'Lead c | `vector_backend_not_the_problem` |
| bp_08 | Overpromise com | PASS | - | Mejorar chunk de diagnostic_co | `vector_backend_not_the_problem` |
| bp_09 | Overpromise com | PASS | - | CRÍTICO: Agregar chunk que con | `vector_backend_not_the_problem` |
| bp_10 | Ambigüedad técn | FAIL | concept_confusion_rate, content_gap | Agregar chunk con tabla de equ | `embedding_ranking_problem` |
| bp_11 | Ambigüedad técn | FAIL | content_gap, embedding_ranking_problem | Mejorar chunk que compare scop | `embedding_ranking_problem` |
| bp_12 | Ambigüedad técn | FAIL | content_gap | Agregar chunk sobre estados de | `embedding_ranking_problem` |
| bp_13 | Multi-tenant /  | FAIL | scope_filter_missing, overpromise_risk | CRÍTICO: Reforzar chunk con re | `embedding_ranking_problem` |
| bp_14 | Multi-tenant /  | FAIL | scope_filter_missing | Verificar que el scope filter  | `metadata_filter_needed` |
| bp_15 | Multi-tenant /  | FAIL | scope_filter_missing, embedding_ranking_problem | Verificar filtros de organizac | `embedding_ranking_problem` |
| bp_16 | Versionado / ac | PASS | - | Agregar filtro por version en  | `metadata_filter_needed` |
| bp_17 | Versionado / ac | PASS | - | CRÍTICO: Agregar metadato de v | `metadata_filter_needed` |
| bp_18 | Contexto insufi | PASS | - | Este caso puede requerir combi | `graph_navigation_needed` |
| bp_19 | Contexto insufi | FAIL | content_gap, llm_grounding_problem | Agregar chunk sobre alcance ac | `embedding_ranking_problem` |
| bp_20 | Contexto insufi | FAIL | content_gap, embedding_ranking_problem | Este caso combina 3 conceptos; | `embedding_ranking_problem` |
| bp_21 | Ruido deliberad | FAIL | overpromise_risk, embedding_ranking_problem | Este caso prueba si chunks con | `embedding_ranking_problem` |
| bp_22 | Ruido deliberad | FAIL | overpromise_risk, embedding_ranking_problem | Reforzar chunks con lenguaje h | `embedding_ranking_problem` |
| bp_23 | Ruido deliberad | FAIL | embedding_ranking_problem, concept_confusion_rate | Evaluar si hace falta hybrid s | `embedding_ranking_problem` |
| bp_24 | Inducción al LL | FAIL | overpromise_risk, llm_grounding_problem | Agregar chunk con regla: 'Team | `embedding_ranking_problem` |
| bp_25 | Inducción al LL | FAIL | llm_grounding_problem, content_gap | Agregar chunk sobre el proceso | `embedding_ranking_problem` |

_Generated by Fase 1.6d report generator · 2026-06-09 16:07 UTC_