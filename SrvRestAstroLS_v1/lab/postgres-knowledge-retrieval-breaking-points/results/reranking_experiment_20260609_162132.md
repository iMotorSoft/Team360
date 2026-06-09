# Reranking experiment — PostgreSQL retrieval breaking points

**Date:** 2026-06-09 16:22 UTC
**Candidate pool (top-N):** 20
**Evaluation (top-K):** 5
**Embedding version:** team360-openai-small-1536-v1
**Scope:** ks_team360_sales_diagnosis

## Resumen ejecutivo

- **Baseline strict (original):** 11/25 (44.0%)
- **Baseline normalizado:** 11/25 (44.0%)
- **Reranked (deterministic):** 17/25 (68.0%)
- **Delta (reranked - baseline norm):** +24.0%
- **High-risk baseline norm:** 9/11
- **High-risk reranked:** 10/11
- **Casos mejorados:** 6
- **Casos empeorados:** 0
- **Casos sin cambio:** 19
- **Correct candidate in top-N:** 17/25 (68.0%)
- **Conceptos prohibidos baseline (strict):** 0
- **Conceptos prohibidos reranked:** 0
- **Latencia promedio retrieval:** 719.7ms
- **Latencia promedio reranking:** 4.7ms

## Interpretación

### Fallos post-reranking

- **correct_not_in_candidates:** 8 casos (100.0%)

**Decisión recomendada:** B. pgvector + reranker experimental debe evaluarse en runtime.

### Arquitectura: ¿qué implica?

- El reranker determinístico mejora significativamente el pass rate.
- Esto sugiere que el problema principal es ranking, no recall ni backend vectorial.

- 📉 **No hay evidencia que justifique Milvus o ArangoDB** para resolver los fallos actuales.

## Casos donde reranking ayudó

- `bp_04` — ¿Qué puedo automatizar en ventas y CRM?
  - Baseline (norm): FAIL → Reranked: PASS
  - Expected: ['sales_diagnosis', 'concrete_orientation', 'automatable']

- `bp_11` — ¿Cuál es la diferencia entre knowledge scope y package?
  - Baseline (norm): FAIL → Reranked: PASS
  - Expected: ['knowledge_scope_sales_diagnosis', 'package_sales_diagnosis', 'cross_customer_isolation']

- `bp_13` — ¿Puedo usar conocimiento de otro cliente si es parecido?
  - Baseline (norm): FAIL → Reranked: PASS
  - Expected: ['cross_customer_isolation', 'knowledge_scope_sales_diagnosis', 'access_tags']

- `bp_14` — Dame el diagnóstico de ventas para Team360
  - Baseline (norm): FAIL → Reranked: PASS
  - Expected: ['sales_diagnosis', 'knowledge_scope_sales_diagnosis']

- `bp_21` — ¿Cómo integro WhatsApp con CRM para automatizar ventas?
  - Baseline (norm): FAIL → Reranked: PASS
  - Expected: ['whatsapp_handoff', 'planned_extension', 'commercial_limits']

- `bp_25` — Dame el paso a paso completo para implementar automatización
  - Baseline (norm): FAIL → Reranked: PASS
  - Expected: ['sales_diagnosis', 'minimum_slots', 'concrete_orientation']

## Casos donde reranking no ayudó

- `bp_10` — ¿Vera es el identificador del paquete o del asistente?
  - Motivo: correct_not_in_candidates
  - Candidato correcto en top-N: False

- `bp_12` — ¿embedding_status pending significa que algo está mal?
  - Motivo: correct_not_in_candidates
  - Candidato correcto en top-N: False

- `bp_15` — Configuración de runtime para el asistente de diagnóstico
  - Motivo: correct_not_in_candidates
  - Candidato correcto en top-N: False

- `bp_19` — Necesito automatización completa de redes sociales, email ma
  - Motivo: correct_not_in_candidates
  - Candidato correcto en top-N: False

- `bp_20` — ¿Qué preguntas tengo que hacer para diagnosticar bien una op
  - Motivo: correct_not_in_candidates
  - Candidato correcto en top-N: False

- `bp_22` — ¿Team360 tiene inteligencia artificial completa que hace tod
  - Motivo: correct_not_in_candidates
  - Candidato correcto en top-N: False

- `bp_23` — automation workflow diagnosis handoff lead capture scoring r
  - Motivo: correct_not_in_candidates
  - Candidato correcto en top-N: False

- `bp_24` — Seguro que se puede hacer todo en una semana, ¿no? ¿Cuánto c
  - Motivo: correct_not_in_candidates
  - Candidato correcto en top-N: False

## Casos donde el candidato correcto no estaba en top-N

- `bp_10` — ¿Vera es el identificador del paquete o del asistente?
  - Top-1 candidate: Cómo responder preguntas sobre identificadores
  - Expected: ['vera_commercial_name', 'technical_identifiers', 'package_sales_diagnosis']

- `bp_12` — ¿embedding_status pending significa que algo está mal?
  - Top-1 candidate: Regla 2: planned_extension ≠ ready_today
  - Expected: ['retrieval_chunk', 'approved_document']

- `bp_15` — Configuración de runtime para el asistente de diagnóstico
  - Top-1 candidate: Runtime/default target
  - Expected: ['runtime_target_team360_live', 'knowledge_scope_sales_diagnosis']

- `bp_19` — Necesito automatización completa de redes sociales, email ma
  - Top-1 candidate: Regla 1: automatable ≠ sellable_today
  - Expected: ['sales_diagnosis', 'concrete_orientation']

- `bp_20` — ¿Qué preguntas tengo que hacer para diagnosticar bien una op
  - Top-1 candidate: Diagnostic code
  - Expected: ['minimum_slots', 'useful_diagnosis', 'concrete_orientation']

- `bp_22` — ¿Team360 tiene inteligencia artificial completa que hace tod
  - Top-1 candidate: Regla 1: automatable ≠ sellable_today
  - Expected: ['concrete_orientation', 'sales_diagnosis']

- `bp_23` — automation workflow diagnosis handoff lead capture scoring r
  - Top-1 candidate: Lead capture productivo general
  - Expected: ['sales_diagnosis', 'concrete_orientation']

- `bp_24` — Seguro que se puede hacer todo en una semana, ¿no? ¿Cuánto c
  - Top-1 candidate: Regla 2: planned_extension ≠ ready_today
  - Expected: ['commercial_limits', 'concrete_orientation']

## Decisión arquitectónica

**B. pgvector + reranker experimental debe evaluarse en runtime.**

### Siguiente paso recomendado:
1. Implementar reranker controlado (cross-encoder ligero) en runtime sin cambiar backend vectorial.
2. Validar con los mismos golden cases que este experimento antes de pasar a producción.
3. No evaluar Milvus ni ArangoDB hasta que el reranker muestre límites de escala/latencia.

---

_Generated by Fase 1.6g — Reranking Experiment. Deterministic oracle-lite reranker. No LLM, no Milvus, no ArangoDB, no production changes._