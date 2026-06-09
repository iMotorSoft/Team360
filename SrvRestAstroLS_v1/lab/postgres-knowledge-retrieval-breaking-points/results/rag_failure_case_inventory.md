# RAG Failure Audit — Inventario de casos

**Experimento:** Team360 RAG Failure Audit — Fase 1.6e
**Total de casos:** 36
**Generado:** 2026-06-09 15:36 UTC

---

## Resumen

- **Total de casos:** 36
- **Categorías:** 6
- **Distribución por riesgo:** {'high': 15, 'medium': 17, 'low': 4}

## Distribución por categoría

| Categoría | Total | High | Medium | Low |
|-----------|-------|------|--------|-----|
| CONTENT_GAP | 6 | 4 | 2 | 0 |
| EMBEDDING_RANKING_PROBLEM | 6 | 3 | 3 | 0 |
| SCOPE_LEAKAGE | 6 | 3 | 3 | 0 |
| IMPOSSIBLE_FILTER | 6 | 0 | 2 | 4 |
| DEEP_TRAVERSAL_UNSUPPORTED | 6 | 3 | 3 | 0 |
| LATENCY_TRAP | 6 | 2 | 4 | 0 |

## Distribución por recommended_fix

| Fix | Casos | % del total |
|-----|-------|-------------|
| content_patch | 24 | 66.7% |
| reranker | 8 | 22.2% |
| hybrid_search | 0 | 0.0% |
| Milvus | 0 | 0.0% |
| ArangoDB | 0 | 0.0% |

## Architecture implications

| Implicación | Casos |
|-------------|-------|
| `content_gap` | 10 |
| `graph_navigation_needed` | 6 |
| `metadata_absent` | 6 |
| `reranker_needed` | 8 |
| `scope_filter_missing` | 6 |

## Casos que NO justifican Milvus/ArangoDB

- **36/36** casos (100.0%) no requieren Milvus ni ArangoDB.
- **0/36** casos (0.0%) sugieren Milvus o ArangoDB.

Esto valida que el problema actual NO es la base de datos vectorial/grafo, 
sino calidad y cobertura del contenido, metadata, filtros y reranking.

## Casos por categoría con recommended_fix

### CONTENT_GAP

- Content patch: 6/6
- Reranker: 0/6
- Milvus: 0/6
- ArangoDB: 0/6

  - ⚠️ `cg_01` [high] ¿Cuál es el SLA garantizado del diagnóstico Team360?
    → arch: `content_gap` fix: content_patch=True reranker=False
  - 📌 `cg_02` [medium] ¿Cuántos mensajes por segundo soporta el handoff de WhatsApp
    → arch: `content_gap` fix: content_patch=True reranker=False
  - ⚠️ `cg_03` [high] ¿Lead capture ya guarda leads en CRM productivo?
    → arch: `content_gap` fix: content_patch=True reranker=False
  - ⚠️ `cg_04` [high] ¿Step-to-Action ejecuta acciones reales hoy?
    → arch: `content_gap` fix: content_patch=True reranker=False
  - ⚠️ `cg_05` [high] ¿Hay garantía de integración con cualquier CRM?
    → arch: `content_gap` fix: content_patch=True reranker=False
  - 📌 `cg_06` [medium] ¿Vera puede cerrar ventas automáticamente?
    → arch: `content_gap` fix: content_patch=True reranker=False

### EMBEDDING_RANKING_PROBLEM

- Content patch: 0/6
- Reranker: 6/6
- Milvus: 0/6
- ArangoDB: 0/6

  - ⚠️ `er_01` [high] ¿Cuál es la diferencia entre WhatsApp como canal futuro y Wh
    → arch: `reranker_needed` fix: content_patch=False reranker=True
  - 📌 `er_02` [medium] ¿Qué diferencia hay entre follow-up automático y orientación
    → arch: `reranker_needed` fix: content_patch=False reranker=True
  - ⚠️ `er_03` [high] ¿diagnostic_code es resultado visible o identificador futuro
    → arch: `reranker_needed` fix: content_patch=False reranker=True
  - ⚠️ `er_04` [high] ¿Step-to-Action es lo mismo que una recomendación concreta?
    → arch: `reranker_needed` fix: content_patch=False reranker=True
  - 📌 `er_05` [medium] ¿Vera es marca visible o identificador técnico?
    → arch: `reranker_needed` fix: content_patch=False reranker=True
  - 📌 `er_06` [medium] ¿El análisis de alcance es lo mismo que un diagnóstico vendi
    → arch: `reranker_needed` fix: content_patch=False reranker=True

### SCOPE_LEAKAGE

- Content patch: 6/6
- Reranker: 0/6
- Milvus: 0/6
- ArangoDB: 0/6

  - ⚠️ `sl_01` [high] ¿Puedo usar knowledge de otro cliente si la automatización e
    → arch: `scope_filter_missing` fix: content_patch=True reranker=False
  - ⚠️ `sl_02` [high] ¿El paquete de ventas puede responder sobre educación judía?
    → arch: `scope_filter_missing` fix: content_patch=True reranker=False
  - 📌 `sl_03` [medium] ¿Team360.live puede usar knowledge de otro workspace?
    → arch: `scope_filter_missing` fix: content_patch=True reranker=False
  - 📌 `sl_04` [medium] ¿Este asistente sirve para automatizar flotas de camiones?
    → arch: `scope_filter_missing` fix: content_patch=True reranker=False
  - ⚠️ `sl_05` [high] ¿Vera puede responder sobre documentación interna de otro cl
    → arch: `scope_filter_missing` fix: content_patch=True reranker=False
  - 📌 `sl_06` [medium] ¿Puedo mezclar knowledge de diagnóstico de ventas con automa
    → arch: `scope_filter_missing` fix: content_patch=True reranker=False

### IMPOSSIBLE_FILTER

- Content patch: 0/6
- Reranker: 0/6
- Milvus: 0/6
- ArangoDB: 0/6

  - 📌 `imf_01` [low] Mostrame solo chunks aprobados en enero 2025.
    → arch: `metadata_absent` fix: content_patch=False reranker=False
  - 📌 `imf_02` [low] Dame solo ejemplos con provider Gupshup.
    → arch: `metadata_absent` fix: content_patch=False reranker=False
  - 📌 `imf_03` [medium] Filtrá capacidades por estado comercial exacto y fecha de re
    → arch: `metadata_absent` fix: content_patch=False reranker=False
  - 📌 `imf_04` [low] Mostrame solo respuestas de industrias inmobiliarias.
    → arch: `metadata_absent` fix: content_patch=False reranker=False
  - 📌 `imf_05` [low] Dame solo documentos revisados por un auditor específico.
    → arch: `metadata_absent` fix: content_patch=False reranker=False
  - 📌 `imf_06` [medium] Filtrá chunks por versión exacta 2.1.0 y estado approved_202
    → arch: `metadata_absent` fix: content_patch=False reranker=False

### DEEP_TRAVERSAL_UNSUPPORTED

- Content patch: 6/6
- Reranker: 0/6
- Milvus: 0/6
- ArangoDB: 0/6

  - ⚠️ `dt_01` [high] Relacioná Step-to-Action, planned_extension, límites comerci
    → arch: `graph_navigation_needed` fix: content_patch=True reranker=False
  - ⚠️ `dt_02` [high] Explicá cómo runtime target, package context y knowledge_sco
    → arch: `graph_navigation_needed` fix: content_patch=True reranker=False
  - 📌 `dt_03` [medium] Mostrá la cadena desde una pregunta mínima hasta una recomen
    → arch: `graph_navigation_needed` fix: content_patch=True reranker=False
  - ⚠️ `dt_04` [high] Conectá lead capture, WhatsApp handoff y CRM como futuras ca
    → arch: `graph_navigation_needed` fix: content_patch=True reranker=False
  - 📌 `dt_05` [medium] ¿Qué patrón común conecta diagnóstico, slots, scoring, orien
    → arch: `graph_navigation_needed` fix: content_patch=True reranker=False
  - 📌 `dt_06` [medium] Explicá cómo una pregunta detecta oportunidad, clasifica slo
    → arch: `graph_navigation_needed` fix: content_patch=True reranker=False

### LATENCY_TRAP

- Content patch: 6/6
- Reranker: 2/6
- Milvus: 0/6
- ArangoDB: 0/6

  - 📌 `lt_01` [medium] ¿Cómo empiezo a usar el diagnóstico de automatización?
    → arch: `content_gap` fix: content_patch=True reranker=False
  - ⚠️ `lt_02` [high] ¿Qué puede vender Team360 hoy?
    → arch: `reranker_needed` fix: content_patch=True reranker=True
  - 📌 `lt_03` [medium] ¿Qué hace Vera?
    → arch: `content_gap` fix: content_patch=True reranker=False
  - ⚠️ `lt_04` [high] ¿Qué automatizaciones están listas?
    → arch: `reranker_needed` fix: content_patch=True reranker=True
  - 📌 `lt_05` [medium] ¿Cómo preparo una propuesta para un cliente?
    → arch: `content_gap` fix: content_patch=True reranker=False
  - 📌 `lt_06` [medium] ¿El diagnóstico de Team360 es gratis?
    → arch: `content_gap` fix: content_patch=True reranker=False

## Listado completo de casos

| ID | Categoría | Riesgo | Query | Arch implication | Milvus? | ArangoDB? | Reranker? | Content patch? |
|----|-----------|--------|-------|------------------|---------|-----------|-----------|----------------|
| cg_01 | CONTENT_GAP | high | ¿Cuál es el SLA garantizado del diagnóstico Team360? | `content_gap` | ❌ | ❌ | ❌ | ✅ |
| cg_02 | CONTENT_GAP | medium | ¿Cuántos mensajes por segundo soporta el handoff de WhatsApp | `content_gap` | ❌ | ❌ | ❌ | ✅ |
| cg_03 | CONTENT_GAP | high | ¿Lead capture ya guarda leads en CRM productivo? | `content_gap` | ❌ | ❌ | ❌ | ✅ |
| cg_04 | CONTENT_GAP | high | ¿Step-to-Action ejecuta acciones reales hoy? | `content_gap` | ❌ | ❌ | ❌ | ✅ |
| cg_05 | CONTENT_GAP | high | ¿Hay garantía de integración con cualquier CRM? | `content_gap` | ❌ | ❌ | ❌ | ✅ |
| cg_06 | CONTENT_GAP | medium | ¿Vera puede cerrar ventas automáticamente? | `content_gap` | ❌ | ❌ | ❌ | ✅ |
| er_01 | EMBEDDING_RANKING_PROBLEM | high | ¿Cuál es la diferencia entre WhatsApp como canal futuro y Wh | `reranker_needed` | ❌ | ❌ | ✅ | ❌ |
| er_02 | EMBEDDING_RANKING_PROBLEM | medium | ¿Qué diferencia hay entre follow-up automático y orientación | `reranker_needed` | ❌ | ❌ | ✅ | ❌ |
| er_03 | EMBEDDING_RANKING_PROBLEM | high | ¿diagnostic_code es resultado visible o identificador futuro | `reranker_needed` | ❌ | ❌ | ✅ | ❌ |
| er_04 | EMBEDDING_RANKING_PROBLEM | high | ¿Step-to-Action es lo mismo que una recomendación concreta? | `reranker_needed` | ❌ | ❌ | ✅ | ❌ |
| er_05 | EMBEDDING_RANKING_PROBLEM | medium | ¿Vera es marca visible o identificador técnico? | `reranker_needed` | ❌ | ❌ | ✅ | ❌ |
| er_06 | EMBEDDING_RANKING_PROBLEM | medium | ¿El análisis de alcance es lo mismo que un diagnóstico vendi | `reranker_needed` | ❌ | ❌ | ✅ | ❌ |
| sl_01 | SCOPE_LEAKAGE | high | ¿Puedo usar knowledge de otro cliente si la automatización e | `scope_filter_missing` | ❌ | ❌ | ❌ | ✅ |
| sl_02 | SCOPE_LEAKAGE | high | ¿El paquete de ventas puede responder sobre educación judía? | `scope_filter_missing` | ❌ | ❌ | ❌ | ✅ |
| sl_03 | SCOPE_LEAKAGE | medium | ¿Team360.live puede usar knowledge de otro workspace? | `scope_filter_missing` | ❌ | ❌ | ❌ | ✅ |
| sl_04 | SCOPE_LEAKAGE | medium | ¿Este asistente sirve para automatizar flotas de camiones? | `scope_filter_missing` | ❌ | ❌ | ❌ | ✅ |
| sl_05 | SCOPE_LEAKAGE | high | ¿Vera puede responder sobre documentación interna de otro cl | `scope_filter_missing` | ❌ | ❌ | ❌ | ✅ |
| sl_06 | SCOPE_LEAKAGE | medium | ¿Puedo mezclar knowledge de diagnóstico de ventas con automa | `scope_filter_missing` | ❌ | ❌ | ❌ | ✅ |
| imf_01 | IMPOSSIBLE_FILTER | low | Mostrame solo chunks aprobados en enero 2025. | `metadata_absent` | ❌ | ❌ | ❌ | ❌ |
| imf_02 | IMPOSSIBLE_FILTER | low | Dame solo ejemplos con provider Gupshup. | `metadata_absent` | ❌ | ❌ | ❌ | ❌ |
| imf_03 | IMPOSSIBLE_FILTER | medium | Filtrá capacidades por estado comercial exacto y fecha de re | `metadata_absent` | ❌ | ❌ | ❌ | ❌ |
| imf_04 | IMPOSSIBLE_FILTER | low | Mostrame solo respuestas de industrias inmobiliarias. | `metadata_absent` | ❌ | ❌ | ❌ | ❌ |
| imf_05 | IMPOSSIBLE_FILTER | low | Dame solo documentos revisados por un auditor específico. | `metadata_absent` | ❌ | ❌ | ❌ | ❌ |
| imf_06 | IMPOSSIBLE_FILTER | medium | Filtrá chunks por versión exacta 2.1.0 y estado approved_202 | `metadata_absent` | ❌ | ❌ | ❌ | ❌ |
| dt_01 | DEEP_TRAVERSAL_UNSUPPORTED | high | Relacioná Step-to-Action, planned_extension, límites comerci | `graph_navigation_needed` | ❌ | ❌ | ❌ | ✅ |
| dt_02 | DEEP_TRAVERSAL_UNSUPPORTED | high | Explicá cómo runtime target, package context y knowledge_sco | `graph_navigation_needed` | ❌ | ❌ | ❌ | ✅ |
| dt_03 | DEEP_TRAVERSAL_UNSUPPORTED | medium | Mostrá la cadena desde una pregunta mínima hasta una recomen | `graph_navigation_needed` | ❌ | ❌ | ❌ | ✅ |
| dt_04 | DEEP_TRAVERSAL_UNSUPPORTED | high | Conectá lead capture, WhatsApp handoff y CRM como futuras ca | `graph_navigation_needed` | ❌ | ❌ | ❌ | ✅ |
| dt_05 | DEEP_TRAVERSAL_UNSUPPORTED | medium | ¿Qué patrón común conecta diagnóstico, slots, scoring, orien | `graph_navigation_needed` | ❌ | ❌ | ❌ | ✅ |
| dt_06 | DEEP_TRAVERSAL_UNSUPPORTED | medium | Explicá cómo una pregunta detecta oportunidad, clasifica slo | `graph_navigation_needed` | ❌ | ❌ | ❌ | ✅ |
| lt_01 | LATENCY_TRAP | medium | ¿Cómo empiezo a usar el diagnóstico de automatización? | `content_gap` | ❌ | ❌ | ❌ | ✅ |
| lt_02 | LATENCY_TRAP | high | ¿Qué puede vender Team360 hoy? | `reranker_needed` | ❌ | ❌ | ✅ | ✅ |
| lt_03 | LATENCY_TRAP | medium | ¿Qué hace Vera? | `content_gap` | ❌ | ❌ | ❌ | ✅ |
| lt_04 | LATENCY_TRAP | high | ¿Qué automatizaciones están listas? | `reranker_needed` | ❌ | ❌ | ✅ | ✅ |
| lt_05 | LATENCY_TRAP | medium | ¿Cómo preparo una propuesta para un cliente? | `content_gap` | ❌ | ❌ | ❌ | ✅ |
| lt_06 | LATENCY_TRAP | medium | ¿El diagnóstico de Team360 es gratis? | `content_gap` | ❌ | ❌ | ❌ | ✅ |

## Notas

- Este inventario es puramente estático. No ejecuta retrieval, no llama APIs, no consulta DB.
- Los casos están diseñados para una futura corrida donde se ejecute retrieval real y se valide cada clasificación.
- Ninguna clasificación debe cambiarse porque el retrieval falle; al contrario, el retrieval debe validar la clasificación esperada.

---

_Generado por RAG Failure Audit — Fase 1.6e. Sin LLM, sin DB, sin retrieval._
_2026-06-09 15:36 UTC_