# Retrieval Quality & Commercial Fit Test — Fase 1.6b

**Date:** 2026-06-09 14:17 UTC
**Embedding model:** text-embedding-3-small (1536d)
**Embedding version:** team360-openai-small-1536-v1
**Knowledge scope:** ks_team360_sales_diagnosis
**Results per query:** 5

## Resumen ejecutivo

- **21/25** queries pasaron criterio de aceptación (84.0%)
- **0** queries con conceptos prohibidos en top-3
- **Score total:** 37 (rango posible: -75 a 75)
- **Latencia promedio:** 0.88s por query

### ¿pgvector alcanza para primera etapa productiva?

- Casos de alto riesgo: 10/13 pasaron criterio
- Casos de alto riesgo con conceptos prohibidos: 0

**Conclusión: pgvector suficiente para primera etapa productiva.**

### ¿Hay razones para meter Milvus ahora?

- Milvus sería necesario si la calidad semántica fuera insuficiente (>20% fallos en alto riesgo)
- Milvus sería necesario si la latencia fuera crítica (>5s promedio)
- Milvus sería necesario si el corpus superara 100k chunks y pgvector escalara mal

Con 25 queries evaluadas, latencia promedio 0.88s:
**No hay razón urgente para Milvus. Continuar con pgvector.**

### ¿Qué riesgos comerciales detecta el retrieval?

Los conceptos prohibidos en retrievals de alto riesgo indican:
- Si `planned_extension` aparece como capacidad lista → riesgo de overpromise
- Si `automatizable` se confunde con `vendible` → riesgo de venta incorrecta
- Si `Vera` se usa como identificador técnico → riesgo de rebranding forzado

## Resultados por categoría

### E. Ambiguas / anti-humo

- 4/5 passed (80.0%)
- Score acumulado: 6

  - ✅ `q_21` (score=+3)
    _Quiero automatizar todo, ¿qué vendemos ya?..._
  - ❌ `q_22` (score=-5)
    _¿Vera puede capturar leads y mandar WhatsApp?..._
  - ✅ `q_23` (score=+3)
    _¿Todo lo automatizable es producto vendible?..._
  - ✅ `q_24` (score=+3)
    _¿Podemos vender Step-to-Action como listo?..._
  - ✅ `q_25` (score=+2)
    _¿Qué le digo a un cliente que pide IA para ventas?..._

### A. Comercial / ventas

- 4/5 passed (80.0%)
- Score acumulado: 9

  - ✅ `q_01` (score=+3)
    _¿Qué valor real se puede vender en la primera etapa?..._
  - ✅ `q_02` (score=+2)
    _¿Qué NO debe venderse todavía?..._
  - ❌ `q_03` (score=+0)
    _¿Qué significa diagnóstico útil?..._
  - ✅ `q_04` (score=+1)
    _¿Qué significa orientación concreta?..._
  - ✅ `q_05` (score=+3)
    _¿Qué diferencia hay entre automatizable y vendible hoy?..._

### D. Knowledge Base as a Service

- 4/5 passed (80.0%)
- Score acumulado: 5

  - ✅ `q_16` (score=+3)
    _¿Este sistema sirve para ofrecer knowledge base a clientes?..._
  - ✅ `q_17` (score=+3)
    _¿Qué necesita una knowledge base de cliente para ser confiable?..._
  - ✅ `q_18` (score=+2)
    _¿Qué riesgo hay si se mezclan scopes o clientes?..._
  - ❌ `q_19` (score=-5)
    _¿Cómo se evita knowledge cross-customer?..._
  - ✅ `q_20` (score=+2)
    _¿Qué metadata ayuda a auditar conocimiento?..._

### B. Producto / límites

- 4/5 passed (80.0%)
- Score acumulado: 5

  - ✅ `q_06` (score=+3)
    _¿Step-to-Action está listo para vender?..._
  - ❌ `q_07` (score=-5)
    _¿lead capture está listo?..._
  - ✅ `q_08` (score=+3)
    _¿WhatsApp handoff está listo?..._
  - ✅ `q_09` (score=+2)
    _¿diagnostic_code está listo?..._
  - ✅ `q_10` (score=+2)
    _¿Qué capacidades son planned_extension?..._

### C. Técnico

- 5/5 passed (100.0%)
- Score acumulado: 12

  - ✅ `q_11` (score=+3)
    _¿Qué son slots mínimos?..._
  - ✅ `q_12` (score=+2)
    _¿Cómo se conecta knowledge_scope con package?..._
  - ✅ `q_13` (score=+2)
    _¿Qué rol tiene embedding_status pending/ready?..._
  - ✅ `q_14` (score=+2)
    _¿Qué implica runtime target Team360.live?..._
  - ✅ `q_15` (score=+3)
    _¿Qué diferencia hay entre package context y runtime target?..._

## Casos críticos

### `q_06` — ¿Step-to-Action está listo para vender?

- **Estado:** ✅ PASÓ
- **Score:** +3
- **Conceptos esperados en top-1:** True
- **Conceptos esperados en top-3:** True
- **Conceptos esperados en top-5:** True
- **Conceptos prohibidos en top-3:** False
- **Resultados recuperados:** 5
  - Rank 1: `6f1bae41...` (Step-to-Action como extensión futura) score=0.584204
  - Rank 2: `b5d2e54a...` (Offer Decision) score=0.485488
  - Rank 3: `62cba66d...` (Límite comercial) score=0.464061

### `q_07` — ¿lead capture está listo?

- **Estado:** ❌ FALLÓ
- **Score:** -5
- **Conceptos esperados en top-1:** False
- **Conceptos esperados en top-3:** False
- **Conceptos esperados en top-5:** False
- **Conceptos prohibidos en top-3:** False
- **Resultados recuperados:** 5
  - Rank 1: `890b069e...` (Primer contexto de validación: Team360.live) score=0.426891
  - Rank 2: `bb477574...` (Trigger) score=0.394809
  - Rank 3: `28c3e497...` (Recommended Next Steps) score=0.391902

### `q_08` — ¿WhatsApp handoff está listo?

- **Estado:** ✅ PASÓ
- **Score:** +3
- **Conceptos esperados en top-1:** True
- **Conceptos esperados en top-3:** True
- **Conceptos esperados en top-5:** True
- **Conceptos prohibidos en top-3:** False
- **Resultados recuperados:** 5
  - Rank 1: `0d61b419...` (Diagnostic Code y WhatsApp Handoff futuro) score=0.557886
  - Rank 2: `843860a0...` (Human Handoff) score=0.455078
  - Rank 3: `b53847c0...` (Referencias cruzadas silenciosas) score=0.440053

### `q_09` — ¿diagnostic_code está listo?

- **Estado:** ✅ PASÓ
- **Score:** +2
- **Conceptos esperados en top-1:** False
- **Conceptos esperados en top-3:** True
- **Conceptos esperados en top-5:** True
- **Conceptos prohibidos en top-3:** False
- **Resultados recuperados:** 5
  - Rank 1: `22c70939...` (Manual del paquete de diagnóstico de automatización) score=0.512866
  - Rank 2: `0d61b419...` (Diagnostic Code y WhatsApp Handoff futuro) score=0.506543
  - Rank 3: `186826e0...` (Suggested Assistant Message futuro) score=0.431697

### `q_22` — ¿Vera puede capturar leads y mandar WhatsApp?

- **Estado:** ❌ FALLÓ
- **Score:** -5
- **Conceptos esperados en top-1:** False
- **Conceptos esperados en top-3:** False
- **Conceptos esperados en top-5:** False
- **Conceptos prohibidos en top-3:** False
- **Resultados recuperados:** 5
  - Rank 1: `890b069e...` (Primer contexto de validación: Team360.live) score=0.49847
  - Rank 2: `b53847c0...` (Referencias cruzadas silenciosas) score=0.496274
  - Rank 3: `e9f2eca1...` (Flujo conceptual de Vera) score=0.47307

### `q_23` — ¿Todo lo automatizable es producto vendible?

- **Estado:** ✅ PASÓ
- **Score:** +3
- **Conceptos esperados en top-1:** True
- **Conceptos esperados en top-3:** True
- **Conceptos esperados en top-5:** True
- **Conceptos prohibidos en top-3:** False
- **Resultados recuperados:** 5
  - Rank 1: `b5d2e54a...` (Offer Decision) score=0.602115
  - Rank 2: `62cba66d...` (Límite comercial) score=0.580968
  - Rank 3: `e32144bd...` (Impacto) score=0.489261

### `q_24` — ¿Podemos vender Step-to-Action como listo?

- **Estado:** ✅ PASÓ
- **Score:** +3
- **Conceptos esperados en top-1:** True
- **Conceptos esperados en top-3:** True
- **Conceptos esperados en top-5:** True
- **Conceptos prohibidos en top-3:** False
- **Resultados recuperados:** 5
  - Rank 1: `6f1bae41...` (Step-to-Action como extensión futura) score=0.58343
  - Rank 2: `b5d2e54a...` (Offer Decision) score=0.531345
  - Rank 3: `62cba66d...` (Límite comercial) score=0.469505

## Decisión recomendada

### Criterios

1. **Calidad general:** 21/25 pasan (84.0%)
2. **Riesgo comercial alto:** 3 fallos en 13 casos críticos
3. **Conceptos prohibidos:** 0 queries con contenido de riesgo en top-3
4. **Latencia:** 0.88s promedio

### Recomendación: **B. pgvector suficiente para ahora, Milvus queda como comparativa de escala.**

Hay casos aislados donde el retrieval podría mejorar, pero el porcentaje general
es aceptable para una primera etapa. Milvus debe evaluarse cuando el volumen de
chunks o la latencia lo justifiquen, no por calidad de retrieval.

---

_Generated by Fase 1.6b — Retrieval Quality & Commercial Fit Test_