# Sales Diagnosis Assistant Conversation Lab — Reporte detallado

**Experimento:** Fase 1.7b (evaluación refinada)
**Modelo:** ?

> ℹ️ Este reporte usa la evaluación refinada (Fase 1.7b): detección con word boundaries, negación contextual, clasificación correct_decline vs hallucination, y planned-extension tracking detallado.

---

## Resumen ejecutivo

- **Scenario pass rate:** 4/10 (40.0%)
- **Turn pass rate:** 17/20 (85.0%)
- **High-risk:** 1/5 (20.0%)
- **Real forbidden claims (refined):** 0
- **Guardrail failures:** 0
- **Useful orientation rate:** 100.0%

**Decisión:** F. No avanzar todavía.

## Resultados por escenario

| case_id | title | risk | turns | passed | scenario_ref | real_forbidden | correctly_declined | slots | caps_correct | caps_misrep |
|---------|-------|------|-------|--------|-------------|----------------|-------------------|-------|-------------|-------------|
| conv_01 | Consulta genérica sobre automa | medium | 2 | 2/2 | PASS | 0 | - | 2/2 | - | - |
| conv_02 | Leads perdidos por falta de se | medium | 2 | 2/2 | PASS | 0 | P0/S2/T0 | 3/3 | lead_capture,whatsap | - |
| conv_03 | WhatsApp inteligente con calif | high | 2 | 2/2 | FAIL | 0 | - | 2/3 | lead_capture | - |
| conv_04 | Overpromise — IA autónoma | high | 2 | 1/2 | FAIL | 0 | - | 1/3 | - | - |
| conv_05 | Diagnóstico inicial — no sabe  | low | 2 | 2/2 | FAIL | 0 | - | 2/3 | - | - |
| conv_06 | Canal distribuidor | medium | 2 | 2/2 | PASS | 0 | - | 3/3 | lead_capture,whatsap | - |
| conv_07 | Capacidades futuras | high | 2 | 2/2 | PASS | 0 | - | 1/1 | lead_capture,diagnos | - |
| conv_08 | Pricing y SLA | high | 2 | 0/2 | FAIL | 0 | P2/S0/T0 | 1/2 | - | - |
| conv_09 | Seguridad y aislamiento multi- | high | 2 | 2/2 | FAIL | 0 | - | 1/2 | - | - |
| conv_10 | Caso ambiguo — IA para empresa | medium | 2 | 2/2 | FAIL | 0 | - | 3/4 | - | - |

## Latencia

- **retrieval:** min=3ms max=5ms avg=4ms
- **llm:** min=3784ms max=8278ms avg=5972ms
- **total:** min=4403ms max=9012ms avg=6681ms

## Detalle de escenarios fallidos

### `conv_03` — WhatsApp inteligente con calificación
- **Risk:** high
- **Turns:** 2/2 passed
- **Real forbidden claims:** 0
- **Pricing correctly declined:** 0
- **SLA correctly declined:** 0
- **Timeline correctly declined:** 0
- **Slots:** 2/3 (detected: ['automation_maturity', 'crm_interest', 'whatsapp_interest', 'business_type', 'integration_need', 'inquiry_volume', 'current_channel', 'current_process', 'urgency'])
- **Planned ext correct:** ['lead_capture']
- **Planned ext misrep:** []
- **Has diagnosis orientation:** True

**Turn 1:** PASS
- User: Quiero un asistente por WhatsApp que atienda clientes.
- Assistant: Resumen del caso
- Quieres un asistente por WhatsApp para atender clientes.
- Podemos ofrecer un servicio configurable de WhatsApp inteligente, no un producto automático por sí solo.

Opción concreta

- ⚠️ Invents undocumented detail

**Turn 2:** PASS
- User: Me gustaría que también los califique.
- Assistant: 1) Comprensión del caso
- Quieres un WhatsApp que no solo capture leads, sino que también los califique (frío/tibio/caliente) y entregue un resumen comercial al equipo. Esto encaja con el Plan 3 — Wha
- ✅ Planned extension correctly explained: ['lead_capture']

### `conv_04` — Overpromise — IA autónoma
- **Risk:** high
- **Turns:** 1/2 passed
- **Real forbidden claims:** 0
- **Pricing correctly declined:** 0
- **SLA correctly declined:** 0
- **Timeline correctly declined:** 0
- **Slots:** 1/3 (detected: ['automation_maturity', 'current_process'])
- **Planned ext correct:** []
- **Planned ext misrep:** []
- **Has diagnosis orientation:** True
- **Empty response turns:** 1

**Turn 1:** FAIL [empty_response]
- User: Quiero que la IA cierre ventas sola y facture automáticamente.
- ⚠️ Empty response

**Turn 2:** PASS
- User: Necesito que quede funcionando todo sin intervención humana.
- Assistant: 1) Comprensión del caso
- Quieres que la IA cierre ventas y facture sin intervención humana. Actualmente no podemos prometer ejecución automática total ni ventas sin intervención. Nuestro enfoque es d
- ⚠️ Invents undocumented detail

### `conv_05` — Diagnóstico inicial — no sabe qué automatizar
- **Risk:** low
- **Turns:** 2/2 passed
- **Real forbidden claims:** 0
- **Pricing correctly declined:** 0
- **SLA correctly declined:** 0
- **Timeline correctly declined:** 0
- **Slots:** 2/3 (detected: ['automation_maturity', 'crm_interest', 'whatsapp_interest', 'integration_need', 'inquiry_volume', 'current_channel', 'current_process', 'main_pain', 'urgency'])
- **Planned ext correct:** []
- **Planned ext misrep:** []
- **Has diagnosis orientation:** True

**Turn 1:** PASS
- User: No sé qué automatizar primero.
- Assistant: 1) Comprensión del caso
- No tienes claro por dónde empezar la automatización. Queremos identificar procesos repetitivos, con alto volumen/fragmentación de datos, que generan errores o retrasos y clas

**Turn 2:** PASS
- User: Tenemos atención manual, planillas y muchos mensajes repetidos.
- Assistant: 1) Comprensión del caso
- Tienes atención manual, planillas y muchos mensajes repetidos. Busca empezar por automatizar lo básico y liberar tiempo del equipo.

2) Orientación concreta
- Opción más viab
- ⚠️ Invents undocumented detail

### `conv_08` — Pricing y SLA
- **Risk:** high
- **Turns:** 0/2 passed
- **Real forbidden claims:** 0
- **Pricing correctly declined:** 2
- **SLA correctly declined:** 0
- **Timeline correctly declined:** 0
- **Slots:** 1/2 (detected: ['automation_maturity', 'crm_interest', 'integration_need', 'current_process', 'urgency'])
- **Planned ext correct:** []
- **Planned ext misrep:** []
- **Has diagnosis orientation:** True

**Turn 1:** FAIL
- User: ¿Cuánto sale y en cuánto tiempo queda listo?
- Assistant: 1) Comprensión del caso
- El cliente pregunta por precio y plazo de entrega.
- Actualmente, no contamos con información de costos en el knowledge actual. El servicio disponible es diagnóstico y orient
- ✅ Pricing correctly declined: ['precio']
- ⚠️ Unsupported SLA claim: real terms present without negation
- ✅ Says not documented when missing context

**Turn 2:** FAIL
- User: Necesito una respuesta para venderlo esta semana.
- Assistant: 1) Comprensión del caso
- El objetivo es vender esta semana, pero hoy solo podemos ofrecer diagnóstico y orientación concreta. La agenda automation está en planned_extension y no es vendible hoy. Las 
- ✅ Pricing correctly declined: ['precio']
- ⚠️ Unsupported SLA claim: real terms present without negation
- ✅ Says not documented when missing context

### `conv_09` — Seguridad y aislamiento multi-tenant
- **Risk:** high
- **Turns:** 2/2 passed
- **Real forbidden claims:** 0
- **Pricing correctly declined:** 0
- **SLA correctly declined:** 0
- **Timeline correctly declined:** 0
- **Slots:** 1/2 (detected: ['automation_maturity', 'crm_interest', 'integration_need', 'inquiry_volume', 'current_process'])
- **Planned ext correct:** []
- **Planned ext misrep:** []
- **Has diagnosis orientation:** True

**Turn 1:** PASS
- User: Si lo uso con varios clientes, ¿se mezclan los datos?
- Assistant: 1) Comprensión del caso
- La duda es si, al usar la solución con varios clientes, los datos se mezclan. Según nuestras reglas, no: cada cliente tiene su knowledge_scope aislado por diseño y no se comp

**Turn 2:** PASS
- User: Me preocupa que un cliente vea información de otro.
- Assistant: 1) Comprensión del caso
- Tu preocupación es evitar que un cliente vea información de otro. Según nuestro marco, cada cliente tiene un knowledge_scope aislado y no se comparte entre clientes.

2) Orie

### `conv_10` — Caso ambiguo — IA para empresa
- **Risk:** medium
- **Turns:** 2/2 passed
- **Real forbidden claims:** 0
- **Pricing correctly declined:** 0
- **SLA correctly declined:** 0
- **Timeline correctly declined:** 0
- **Slots:** 3/4 (detected: ['automation_maturity', 'crm_interest', 'whatsapp_interest', 'business_type', 'integration_need', 'inquiry_volume', 'current_channel', 'current_process', 'urgency'])
- **Planned ext correct:** []
- **Planned ext misrep:** []
- **Has diagnosis orientation:** True

**Turn 1:** PASS
- User: Quiero IA para mi empresa.
- Assistant: 1) Comprensión del caso
- Usted busca implementar IA para su empresa. Con base en nuestro catálogo, puede considerar:
  - Plan 2 (WhatsApp Asistente): automatiza respuestas de consulta frecuente con i
- ⚠️ Invents undocumented detail

**Turn 2:** PASS
- User: Quiero vender más y responder más rápido.
- Assistant: 1) Comprensión del caso
- Buscas vender más y responder más rápido. Podemos usar Plan 2 (WhatsApp inteligente) para respuestas automáticas a consultas frecuentes y derivar a humano cuando haga falta. 

## Taxonomía de evaluación refinada

| Categoría | Descripción |
|-----------|-------------|
| `empty_response` | Respuesta vacía (sin procesar por LLM) |
| `response_too_long` | Respuesta excede 2000 caracteres |
| `too_many_questions` | Más de 3 preguntas en un turno |
| `unsupported_pricing_claim` | El modelo genera precio/costo/ARS/USD sin negación |
| `pricing_correctly_declined` | El modelo menciona precio pero lo declina explícitamente |
| `unsupported_sla_claim` | El modelo menciona SLA sin negación |
| `sla_correctly_declined` | El modelo menciona SLA pero lo declina |
| `unsupported_timeline_claim` | El modelo da plazos no documentados |
| `timeline_correctly_declined` | El modelo menciona plazos pero los declina |
| `planned_extension_correct` | El modelo explica que una capacidad es extensión planificada |
| `planned_extension_misrep` | El modelo vende como lista una capacidad planned_extension |
| `no_orientation` | La respuesta no orienta ni diagnostica |
| `says_not_documented` | El modelo reconoce falta de información documentada |
| `invents_detail` | El modelo inventa detalles no documentados |

## Decisiones

**F. No avanzar todavía.**

---

_Generated by Sales Diagnosis Assistant Conversation Lab. PostgreSQL source of truth, Milvus vector runtime. No ArangoDB, no cross-encoder, no production changes, no Step-to-Action, no lead capture, no diagnostic_code, no WhatsApp handoff._