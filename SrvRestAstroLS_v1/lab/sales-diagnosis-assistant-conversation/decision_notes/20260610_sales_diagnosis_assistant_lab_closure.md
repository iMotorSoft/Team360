# Fase 1.7e — Sales Diagnosis Assistant Lab Closure and Architecture Decision Note

## 1. Resumen ejecutivo

El ciclo de labs del asistente conversacional de ventas/diagnóstico de Team360 ha concluido. Los resultados validan que Team360 puede avanzar hacia un asistente conversacional basado en:

- **PostgreSQL 18** como source of truth.
- **Milvus 2.6** como vector runtime derivado.
- **Markdown chunks** como evidencia recuperada.
- **gpt-5-nano low** como primera respuesta inteligente.
- **Template seguro** solo como acuse/progreso inmediato.
- **AG-UI/SSE** como patrón futuro de experiencia progresiva.

Se cierran Fase 1.6j (Milvus vs pgvector benchmark), Fase 1.6k (RAG answer generation), Fase 1.7 (Conversation lab), Fase 1.7b (Evaluación heurística refinada), Fase 1.7c (Guardrail forensic fix) y Fase 1.7d (Progressive response simulation).

No se avanza a runtime productivo. Se documentan decisiones arquitectónicas, riesgos abiertos y próximo paso recomendado.

## 2. Decisión principal

**Decisión:** Adoptar Milvus 2.6 como vector runtime derivado para el asistente conversacional, manteniendo PostgreSQL 18 como source of truth.

### Justificación

- Milvus no mejora calidad de retrieval frente a pgvector en corpus chico (44% pass rate ambos, 11/25 casos idénticos).
- Milvus sí mejora latencia de retrieval significativamente: ~13.9ms vs ~859.2ms promedio (~62x más rápido).
- En conversación multi-turn, la latencia de retrieval importa porque se suma a la latencia del LLM (~5-6s por turno).
- PostgreSQL permite reconstruir el índice Milvus en cualquier momento sin pérdida de datos.
- pgvector se mantiene como baseline de desarrollo y fallback ante indisponibilidad de Milvus.

## 3. Modelo LLM base

**Decisión:** Mantener gpt-5-nano low como candidato base para primera respuesta inteligente.

### Aclaraciones

- El template seguro NO reemplaza a gpt-5-nano como generador de respuesta inteligente.
- El template no entiende errores tipográficos, frases incompletas, audios transcritos mal, rubros raros ni información subida por browser.
- El template sirve solo como señal inmediata segura (acuse de recibo, indicación de progreso).
- gpt-5-nano low debe interpretar el mensaje real y generar orientación comercial con base en el contexto recuperado.
- Latencia del LLM (~5-6s por turno con 800 tokens de output) es el cuello de botella principal. Reducir max_output_tokens ayuda marginalmente.

### Evaluaciones del lab

| Fase | Objetivo | Resultado |
|------|----------|-----------|
| 1.6k | RAG single-turn Milvus + gpt-5-nano low | Viabilidad validada (Decisión B: guardrails adicionales) |
| 1.7 | Conversación multi-turn | 90% orientation rate; 32 forbidden claims iniciales |
| 1.7b | Evaluación heurística refinada | Taxonomía clara; reducción de falsos positivos |
| 1.7c | Guardrail forensic fix | 0 real failures; 6 escenarios con slots faltantes (cobertura) |

## 4. Respuesta progresiva

**Decisión:** Adoptar conceptualmente el patrón de respuesta progresiva para el asistente conversacional, pero no implementar runtime todavía.

### Patrón definido

1. **Evento de recepción:** señal inmediata al usuario (template seguro).
2. **Retrieval Milvus:** recuperación de chunks relevantes.
3. **Primera respuesta inteligente:** gpt-5-nano low genera orientación inicial.
4. **Respuesta final / diagnóstico estructurado:** respuesta más completa (mismo LLM o respuesta enriquecida).
5. **Futuro AG-UI/SSE:** experiencia progresiva real con streaming server-sent events.

### Estado actual

- Fase 1.7d simuló este patrón con 3 estrategias (single-call, progressive-two-step, templated-quick-final-llm) pero sin endpoints reales, sin SSE, sin frontend.
- No existe runtime productivo de respuesta progresiva.
- No existe contrato formal de eventos para SSE.

## 5. Guardrails

**Decisión:** Los guardrails críticos quedan estables para el cierre del lab.

### Estado documentado

- **0** real forbidden claims después de Fase 1.7c.
- **0** planned_extension misrepresented.
- **0** pricing/SLA hallucination después de correcciones.
- Evaluador heurístico con 5 capas independientes: response shape, commercial usefulness, safety/anti-overpromise, knowledge grounding, slot behavior.
- Limitación: la evaluación es heurística, no reemplaza evaluación humana ni LLM-as-judge sistemático.

### Capacidades no expuestas

Step-to-Action, lead_capture, diagnostic_code y WhatsApp handoff no se venden como listos en ninguna respuesta del asistente.

## 6. Qué queda fuera de alcance

| Componente | Estado |
|------------|--------|
| ArangoDB | Fuera. No justificado para esta etapa. |
| Cross-encoder | Fuera. No justificado ahora (content_gap es el limitante, no ranking). |
| GPT-5.5 runtime | Fuera. Posible judge/oracle offline, no runtime. |
| Step-to-Action | No implementado. No se expone como listo. |
| Lead capture real | No implementado. No se expone como listo. |
| diagnostic_code productivo | No implementado. No se expone como listo. |
| WhatsApp handoff automático | No implementado. No se expone como listo. |
| CRM real | No integrado. |
| Frontend AG-UI/SSE productivo | No implementado. |
| Pricing/SLA inventado | Prohibido por guardrails. 0 ocurrencias después de 1.7c. |

## 7. Riesgos abiertos

| Riesgo | Impacto | Estado |
|--------|---------|--------|
| Latencia LLM ~5-6s por turno | Experiencia de usuario lenta en single-call | Mitigación parcial: patrón progresivo definido |
| Empty turn / token config observado | gpt-5-nano low con razonamiento agota tokens en ciertos casos | Observado en conv_04 (overpromise). Requiere ajuste de max_tokens o modelo |
| Slot detection / coverage mejorable | 6/10 escenarios no pasan por slots faltantes | No es fallo de guardrail. Requiere mejor cobertura de knowledge |
| Evaluación heurística no reemplaza evaluación humana | Falsos positivos/negativos no detectados | Mitigado en 1.7c con forward negation y plural markers |
| Template universal no sirve para dominios futuros | Dominios nuevos (desperfecto automotor, diagnósticos no comerciales) requieren adaptación | Decisión: template por dominio como señal de progreso; interpretación siempre con LLM |
| Necesidad de policy por assistant_instance / package | El mismo runtime debe soportar múltiples asistentes con reglas diferentes | Pendiente para Fase 1.8 (Runtime Design) |

## 8. Decisiones por componente

| Componente | Decisión | Estado | Detalle |
|------------|----------|--------|---------|
| PostgreSQL 18 | Source of truth | **Adoptado** | Transaccional, documentos, chunks, metadata, permisos, auditoría, embeddings registrados, reconstrucción de índices derivados. |
| Milvus 2.6 | Vector runtime derivado | **Adoptado para conversación** | Menor latencia que pgvector. Misma calidad de retrieval. Reconstruible desde PostgreSQL. |
| pgvector | Baseline/dev/fallback | **Mantener** | Útil para desarrollo local, despliegues sin Milvus, y validación cruzada. |
| gpt-5-nano low | Primera respuesta inteligente | **Candidato base** | Buen balance calidad/costo. Latencia ~5-6s es el cuello de botella principal. |
| Template seguro | Acuse/progreso inmediato | **No reemplaza LLM** | No entiende typos, texto incompleto ni dominios variables. Solo señal de progreso. |
| AG-UI/SSE | Experiencia progresiva | **Futuro** | Patrón conceptual adoptado. No implementado. Requiere contrato de eventos formal. |
| ArangoDB | Fuera | **No justificado ahora** | No hay evidencia de que grafos mejoren el diagnóstico para el alcance actual. |
| Cross-encoder | Fuera | **No justificado ahora** | Content_gap es el limitante, no ranking. Re-evaluar después de mejorar cobertura. |
| GPT-5.5 | Judge/oracle offline | **No runtime** | Posible uso para evaluación fuera de línea de calidad de respuestas. |

## 9. Próximo paso recomendado

**Recomendación:** Fase 1.8 — Runtime Design Handoff.

### Objetivo

Diseñar el contrato runtime controlado para el asistente conversacional, **sin implementar todavía**. El diseño debe cubrir:

- **Conversation state**: esquema, ciclo de vida, persistencia.
- **Retrieval provider interface**: abstracción para intercambiar proveedores vectoriales (Milvus, pgvector).
- **Milvus vector provider**: implementación del provider para Milvus 2.6.
- **Prompt/guardrail policy**: política centralizada de prompts y reglas por assistant_instance / package.
- **Event contract**: modelo de eventos para respuesta progresiva (SSE futuro).
- **Fallback behavior**: comportamiento ante caída de Milvus, LLM, o timeout.
- **Metrics**: telemetría de latencia, costos, calidad y errores.

### Excluye explícitamente

No incluir en Fase 1.8:
- Step-to-Action
- lead_capture
- diagnostic_code
- WhatsApp handoff
- Implementación productiva de endpoints
- Frontend
- SSE productivo

### Alternativa

Si el equipo considera que falta evidencia operativa antes de diseñar el runtime:

**Fase 1.7f** — Ejecutar el lab progresivo end-to-end con dependencias reales (Milvus + PostgreSQL + LLM) midiendo latencia real con simulación de SSE en consola.

Pero la recomendación primaria es cerrar labs y pasar a diseño runtime.

## 10. Criterio de avance a runtime

Avanzar a implementación runtime solo si:

1. PostgreSQL se mantiene como source of truth (no se convierte en cache de Milvus).
2. Milvus queda como índice derivado reconstruible desde PostgreSQL en cualquier momento.
3. gpt-5-nano low se usa con guardrails activos y policy configurable por assistant_instance.
4. La respuesta progresiva se implementa como contrato de eventos (SSE), no como HTML generado por LLM.
5. Capacidades futuras (Step-to-Action, lead_capture, diagnostic_code, WhatsApp handoff) no se exponen como listas ni se venden como disponibles.

---

*Documento de cierre de labs del asistente conversacional de ventas/diagnóstico de Team360.*
*Fases cubiertas: 1.6j, 1.6k, 1.7, 1.7b, 1.7c, 1.7d — Cerradas.*
*Próximo paso: Fase 1.8 — Runtime Design Handoff.*
