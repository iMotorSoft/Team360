# Sales Diagnosis Assistant Runtime Design — Fase 1.8

## 1. Resumen ejecutivo

El asistente de ventas/diagnóstico de Team360 pasa de laboratorio a diseño runtime controlado. No se implementa producción todavía.

La arquitectura decidida por los labs (Fase 1.6j–1.7e) es:

| Componente | Decisión | Propósito |
|------------|----------|-----------|
| PostgreSQL 18 | Source of truth | Documentos, chunks, metadata, scopes, permisos, auditoría, embeddings registrados |
| Milvus 2.6 | Vector runtime derivado | Retrievel semántico de baja latencia para conversación |
| pgvector | Fallback/dev/baseline | Modo simple, desarrollo local, validación cruzada |
| Markdown chunks | Evidencia recuperada | Contexto para el LLM, no respuesta directa |
| gpt-5-nano low | Primera respuesta inteligente | Orientación comercial con base en contexto recuperado |
| Template seguro | Acuse/progreso | Señal inmediata, no reemplaza LLM |
| Guardrails | Política obligatoria | Anti-overpromise, límites comerciales, seguridad |
| AG-UI/SSE | Contrato futuro de eventos | Experiencia progresiva sin HTML generado por LLM |

Este documento define el diseño runtime: componentes, contratos de datos, flujo, guardrails, eventos progresivos, fallbacks, métricas y plan de implementación futuro. No implementa código productivo, no crea endpoints, no toca frontend.

## 2. Objetivo del runtime

El runtime debe soportar conversación de ventas/diagnóstico con las siguientes capacidades:

- **Entrada:** texto libre del usuario (primer mensaje y respuestas a preguntas del asistente).
- **Retrieval RAG:** embedding de consulta → Milvus → chunks Markdown relevantes.
- **Orientación concreta:** gpt-5-nano low genera respuesta útil, comercial, basada en contexto recuperado.
- **Preguntas mínimas:** el asistente hace preguntas para completar slots, pero máximo 3 por turno.
- **Slots mínimos:** identificar proceso a automatizar, canal, industria, objetivo, urgencia.
- **Guardrails anti-overpromise:** no vender capacidades futuras como listas, no inventar precios/SLA.
- **Diagnóstico inicial útil:** resumen de lo que el usuario necesita, clasificación de automatización posible, próximos pasos concretos.

### Excluye explícitamente

El runtime NO incluye:
- Step-to-Action
- lead_capture real
- diagnostic_code productivo
- WhatsApp handoff automático
- CRM real
- pricing/SLA inventado
- Cierre de ventas automático
- Facturación automática

## 3. Componentes propuestos

### 3.1 AssistantConversationRuntime

Componente orquestador principal. Recibe un mensaje de usuario, coordina retrieval, prompt, LLM, guardrails y emisión de eventos. No implementa HTTP, no conoce frontend.

Responsabilidades:
- Validar assistant_instance / package / knowledge_scope al inicio del turno.
- Mantener ciclo de vida del turno.
- Coordinar RetrievalProvider, PromptPolicy, LLMProvider, GuardrailPolicy.
- Emitir eventos progresivos a través de ProgressiveEventEmitter.
- Registrar métricas y auditoría.

### 3.2 ConversationState

Estado mutable de la conversación. Persistible (PostgreSQL) pero no necesariamente después de cada sub-operación.

Campos propuestos:
- `session_id`: UUID público.
- `assistant_instance_code`: identifica el asistente (p.ej. `team360_sales_diagnosis`).
- `package_code`: paquete de automatización (`pkg_sales_diagnosis`).
- `knowledge_scope_code`: scope de conocimiento (`ks_team360_sales_diagnosis`).
- `slots`: dict con slots detectados (`process_to_automate`, `channel`, `industry`, `goal`, `urgency`).
- `history_summary`: resumen comprimido de turnos anteriores (no el historial completo).
- `turn_count`: número de turnos transcurridos.
- `last_retrieved_chunks`: lista de chunk_ids del turno anterior (para auditoría).
- `guardrail_state`: registro de guardrails aplicados en el turno actual.
- `risk_flags`: banderas de riesgo detectadas.
- `pending_questions`: preguntas que el asistente hizo y están sin responder.

### 3.3 RetrievalProvider

Interfaz abstracta para retrieval vectorial. Permite intercambiar Milvus ↔ pgvector sin cambiar el orquestador.

```python
class RetrievalProvider(Protocol):
    async def retrieve(
        self,
        query: str,
        knowledge_scope_code: str,
        top_n: int = 20,
        top_k: int = 5,
    ) -> RetrievalResult:
        ...
```

Implementaciones:
- **MilvusRetrievalProvider:** runtime principal para conversación. Lee de colección Milvus 2.6 poblada desde PostgreSQL.
- **PgvectorRetrievalProvider:** fallback. Usa pgvector directamente sobre PostgreSQL.
- **NoOpRetrievalProvider:** para modo sin RAG (responde con disclaimer).

PostgreSQL es siempre el source of truth. Milvus es índice derivado reconstruible.

### 3.4 MilvusVectorIndex

No es un componente runtime activo, sino un estado del sistema: el índice Milvus debe poblarse desde PostgreSQL y puede reconstruirse en cualquier momento.

Reglas:
- El índice no contiene conocimiento original, solo vectores + metadata mínima (chunk_id, document_id, knowledge_scope_id, score).
- El contenido completo del chunk se obtiene de PostgreSQL (knowledge_chunks.content).
- Si Milvus se corrompe o necesita reindexación, se reconstruye desde `knowledge_chunk_embeddings` en PostgreSQL.

### 3.5 PromptPolicy

Define el sistema de prompts para el asistente. Debe ser configurable por assistant_instance / package / dominio.

Componentes de la policy:
- `system_prompt_template`: prompt base del asistente. Incluye contexto de conocimiento recuperado.
- `quick_prompt_template`: para respuesta rápida progresiva (template o LLM corto).
- `final_prompt_template`: para respuesta completa.
- `safe_ack_template`: template de acuse/progreso (sin LLM, seguro).
- `max_questions`: límite de preguntas por turno (default: 3).
- `forbidden_claims`: lista de términos prohibidos por dominio.
- `planned_extensions`: lista de capacidades futuras no disponibles.

### 3.6 GuardrailPolicy

Política de guardrails aplicada después de generar respuesta LLM. Evalúa la respuesta antes de devolverla al usuario.

Capas de guardrail (herederas de Fase 1.7b evaluator):
1. **Response shape:** respuesta vacía, demasiado larga, demasiadas preguntas.
2. **Commercial usefulness:** orientación presente, diagnóstico concreto.
3. **Forbidden claims:** términos prohibidos sin negación cercana.
4. **Planned extension:** capacidades futuras no vendidas como listas.
5. **Pricing/SLA:** precios, plazos o SLA no documentados.

Si un guardrail falla, el comportamiento depende de la severidad:
- **Warning:** respuesta entregada pero marcada en métricas.
- **Degraded:** respuesta reemplazada por fallback seguro.
- **Block:** respuesta bloqueada, se emite evento de error.

### 3.7 LLMProvider

Interfaz abstracta para llamadas LLM.

```python
class LLMProvider(Protocol):
    async def generate(
        self,
        messages: list[dict],
        max_tokens: int,
        temperature: float = 0.2,
    ) -> LLMResponse:
        ...
```

Decisión de labs: gpt-5-nano low como modelo base para primera respuesta inteligente.

Reglas:
- El modelo se configura por alias (`sales_assistant_text`), no por slug directo.
- GPT-5.5 no se usa como runtime. Puede ser judge/oracle offline para evaluación de calidad.
- Se respeta `reasoning_effort` configurable (low para latencia, high para análisis).
- El template seguro no pasa por LLM.

### 3.8 ProgressiveEventEmitter

Contrato futuro para emisión de eventos progresivos. No implementa SSE todavía.

Eventos semánticos definidos por Fase 1.7d:

```
team360.status.received
team360.status.retrieval_started
team360.sources.ready
team360.answer.quick_ack
team360.answer.final_ready
team360.guardrails.applied
team360.metrics.ready
team360.done
team360.error
```

Reglas:
- El LLM nunca genera HTML. Los eventos son semánticos.
- El frontend futuro (AG-UI) renderiza bloques según el tipo de evento.
- La emisión es interna al runtime; la conexión SSE es responsabilidad de la capa de transporte (futura).

### 3.9 MetricsRecorder

Registro de métricas por turno.

Métricas:
- `retrieval_latency_ms`
- `llm_latency_ms`
- `total_latency_ms`
- `time_to_first_ack_ms`
- `time_to_first_intelligent_answer_ms`
- `tokens_prompt`, `tokens_completion`, `tokens_total`
- `cost_estimate`
- `guardrail_failures` (por tipo)
- `guardrail_warnings`
- `slot_fill_rate`
- `useful_orientation` (booleano)
- `user_continuation_signal` (booleano: usuario siguió la conversación)

### 3.10 AuditTrail

Registro de auditoría por turno para transparencia y depuración.

Campos:
- `session_id`
- `turn_number`
- `assistant_instance_code`
- `prompt_policy_version`
- `guardrail_policy_version`
- `llm_model`, `llm_provider`
- `retrieval_provider`
- `chunks_used` (lista de chunk_ids)
- `guardrail_result`
- `response_type` (quick/final/degraded/fallback/blocked)
- `metrics_snapshot`
- `created_at_utc`

## 4. Flujo runtime propuesto

```
┌──────────────────────────────────────────────────────────┐
│ 1. Start turn                                            │
│    Validate assistant_instance / package / scope         │
│    Update ConversationState                              │
├──────────────────────────────────────────────────────────┤
│ 2. Emit safe progress event                              │
│    Template acknowledgement (no LLM)                     │
│    → team360.status.received                             │
├──────────────────────────────────────────────────────────┤
│ 3. Embed user turn or turn summary                       │
│    text-embedding-3-small (1536d)                        │
│    → team360.status.retrieval_started                    │
├──────────────────────────────────────────────────────────┤
│ 4. Retrieve chunks from Milvus                           │
│    MilvusRetrievalProvider.retrieve()                    │
│    → team360.sources.ready                               │
├──────────────────────────────────────────────────────────┤
│ 5. Fetch/verify metadata from PostgreSQL (si necesario)  │
│    Confirm chunk permissions, scope, status              │
├──────────────────────────────────────────────────────────┤
│ 6. Build grounded context                                │
│    Markdown chunks + slot state + history_summary        │
├──────────────────────────────────────────────────────────┤
│ 7. Apply prompt policy                                   │
│    Select template: quick or final según estrategia      │
│    Inject context, slots, guardrails instructions        │
├──────────────────────────────────────────────────────────┤
│ 8. Call gpt-5-nano low                                   │
│    LLMProvider.generate()                                │
│    → team360.answer.quick_ack (si progressive)           │
│    → team360.answer.final_ready                          │
├──────────────────────────────────────────────────────────┤
│ 9. Apply guardrail evaluation / post-check               │
│    GuardrailPolicy.evaluate(response)                    │
│    → team360.guardrails.applied                          │
├──────────────────────────────────────────────────────────┤
│ 10. If unsafe → downgrade/fallback response              │
│    Degrade: reemplazar partes inseguras                  │
│    Block: respuesta segura genérica                      │
├──────────────────────────────────────────────────────────┤
│ 11. Update slots and conversation_state                  │
│    Extraer slots de la respuesta                         │
│    Actualizar history_summary                            │
├──────────────────────────────────────────────────────────┤
│ 12. Emit final semantic response                         │
│    → team360.done                                        │
├──────────────────────────────────────────────────────────┤
│ 13. Record metrics / audit                               │
│    MetricsRecorder.record()                              │
│    AuditTrail.append()                                   │
│    → team360.metrics.ready                               │
└──────────────────────────────────────────────────────────┘
```

### Modos de respuesta (de Fase 1.7d)

| Estrategia | Quick answer | Final answer | LLM calls | Uso |
|------------|-------------|--------------|-----------|-----|
| `single-call` | — | LLM completa (500 tok) | 1 | Baseline |
| `progressive-two-step` | LLM corta (120 tok) | LLM completa (500 tok) | 2 | Máxima calidad progresiva |
| `templated-quick-final-llm` | Template (0ms LLM) | LLM completa (500 tok) | 1 | Balance latencia/calidad |

## 5. Contratos de datos

Todos los contratos se definen en formato Markdown. No son código obligatorio, son especificación para implementación futura.

### 5.1 AssistantTurnInput

```
{
  "session_id": "uuid",                    // Sesión existente o nueva
  "assistant_instance_code": "string",      // Ej: team360_sales_diagnosis
  "package_code": "string",                 // Ej: pkg_sales_diagnosis
  "knowledge_scope_code": "string",         // Ej: ks_team360_sales_diagnosis
  "user_message": "string",                 // Texto libre del usuario
  "channel": "string",                      // web, whatsapp, api
  "metadata": {                             // Opcional
    "locale": "es",
    "source_url": "string",
    "visitor": { ... }
  }
}
```

### 5.2 AssistantTurnOutput

```
{
  "response_text": "string",               // Respuesta al usuario
  "response_type": "string",               // ack | quick | final | degraded | fallback | blocked
  "asked_questions": ["string"],            // Preguntas hechas en este turno
  "slots_updated": {                        // Slots detectados/actualizados
    "process_to_automate": "string",
    "channel": "string",
    ...
  },
  "retrieved_sources": [                    // Chunks usados
    {
      "chunk_id": "uuid",
      "document_id": "uuid",
      "title": "string",
      "score": 0.85
    }
  ],
  "guardrail_result": {                     // Resultado de guardrail
    "passed": true,
    "warnings": [],
    "failures": []
  },
  "events": ["team360.done"],              // Eventos emitidos
  "metrics": {                              // Métricas del turno
    "retrieval_latency_ms": 12,
    "llm_latency_ms": 5200,
    "total_latency_ms": 5800,
    "tokens_total": 850
  },
  "next_state": {                           // Estado para próximo turno
    "turn_count": 3,
    "slots": { ... },
    "pending_questions": []
  }
}
```

### 5.3 ConversationState

```
{
  "session_id": "uuid",
  "assistant_instance_code": "string",
  "package_code": "string",
  "knowledge_scope_code": "string",
  "slots": {
    "process_to_automate": null | "string",
    "channel": null | "string",
    "industry": null | "string",
    "goal": null | "string",
    "urgency": null | "string"
  },
  "history_summary": "string",              // Resumen comprimido multi-turn
  "turn_count": 0,
  "last_retrieved_chunks": ["uuid"],
  "guardrail_state": {
    "current_turn_warnings": [],
    "current_turn_failures": [],
    "cumulative_warnings": 0,
    "cumulative_failures": 0
  },
  "risk_flags": [],
  "pending_questions": []
}
```

### 5.4 RetrievedChunk

```
{
  "chunk_id": "uuid",
  "document_id": "uuid",
  "knowledge_scope_id": "uuid",
  "source_uri": "string | null",
  "title": "string",
  "node_path": "string",
  "score": 0.0–1.0,
  "content_preview": "string",              // Primeros 200 caracteres
  "content": "string"                        // Contenido completo
}
```

### 5.5 GuardrailResult

```
{
  "passed": true | false,
  "forbidden_claims": [],                    // Términos prohibidos detectados
  "planned_extension_misrepresented": false,
  "pricing_sla_hallucination": false,
  "max_questions_exceeded": false,
  "empty_response": false,
  "fallback_applied": false,
  "details": "string"                        // Explicación del resultado
}
```

### 5.6 ProgressiveEvent

Eventos semánticos para el contrato futuro AG-UI/SSE:

| Evento | Momento | Payload sugerido |
|--------|---------|------------------|
| `team360.status.received` | Consulta recibida | `{ session_id, turn_number }` |
| `team360.status.retrieval_started` | Inicio retrieval | `{ session_id }` |
| `team360.sources.ready` | Chunks recuperados | `{ chunk_count, top_score }` |
| `team360.answer.quick_ack` | Acuse/progreso listo | `{ text }` |
| `team360.answer.final_ready` | Respuesta final lista | `{ text, slots_updated, response_type }` |
| `team360.guardrails.applied` | Guardrails evaluados | `{ passed, warnings, failures }` |
| `team360.metrics.ready` | Métricas listas | `{ retrieval_latency_ms, llm_latency_ms, total_latency_ms }` |
| `team360.done` | Turno completado | `{ session_id, turn_number }` |
| `team360.error` | Error | `{ code, message }` |

## 6. Guardrails obligatorios

### Regla 1: No vender como listo

Las siguientes capacidades NO deben presentarse como disponibles:
- Step-to-Action
- lead_capture
- diagnostic_code
- WhatsApp handoff automático
- CRM real
- Facturación automática
- Cierre de ventas automático

Si el usuario pregunta por alguna, el asistente debe decir que es una capacidad futura no disponible actualmente.

### Regla 2: No inventar

El asistente NO debe generar:
- Precios concretos
- Plazos de implementación
- SLA
- Integraciones con sistemas específicos no documentados
- Capacidades no documentadas en el knowledge scope

### Regla 3: Diferenciar

El asistente debe distinguir entre:
- **Automatizable:** lo que Team360 puede automatizar hoy.
- **Vendible hoy:** servicios y paquetes disponibles comercialmente.
- **Planned extension:** capacidades en desarrollo, no disponibles.
- **No documentado:** el knowledge scope no contiene información.

### Regla 4: Límite de preguntas

Máximo 3 preguntas por turno. Si el usuario no responde después de 2 turnos de preguntas, el asistente debe orientar con la información disponible.

### Regla 5: Empty response

Si el LLM devuelve respuesta vacía, se debe reintentar una vez con temperatura más alta. Si persiste, devolver fallback seguro.

## 7. Template seguro

### Propósito

El template seguro es un acuse de recibo inmediato. No es respuesta inteligente.

### Reglas

- No reemplaza al LLM. El LLM siempre genera la primera respuesta inteligente.
- No debe ser universal. Debe ser configurable por `assistant_instance` / `package` / `dominio`.
- Si no hay policy segura definida, no usar template (esperar a respuesta LLM).
- Para dominios no comerciales (desperfecto automotor, diagnósticos técnicos), no usar template comercial.

### Ejemplo base

> "Recibí tu consulta. Estoy revisando el contexto disponible para orientarte sin prometer capacidades no confirmadas."

### Ejemplo por dominio

- **Comercial:** "Gracias por tu consulta. Estoy revisando la información disponible sobre automatización para tu caso."
- **Soporte técnico:** "Recibí el diagnóstico del desperfecto. Estoy buscando información relevante."
- **Sin policy:** (no usar template, esperar respuesta LLM)

## 8. Progressive response / AG-UI / SSE

### Estado actual

- Fase 1.7d simuló eventos progresivos sin endpoints reales.
- `backend/modules/agui_stream/` existe como reserva estructural (README solo).
- `astro/src/lib/agui/` existe como reserva estructural (README solo).

### Contrato futuro

1. **Backend emite eventos semánticos** (no HTML). Los eventos siguen el esquema `ProgressiveEvent`.
2. **SSE transporta eventos** del backend al frontend.
3. **AG-UI frontend** recibe eventos y renderiza bloques UI según el tipo:
   - `status.received` → spinner / indicador
   - `sources.ready` → indicador de progreso
   - `answer.quick_ack` → texto de acuse
   - `answer.final_ready` → respuesta completa formateada
   - `guardrails.applied` → indicador de seguridad
   - `error` → mensaje de error controlado

### Regla crítica

El LLM nunca genera HTML. La generación de UI es responsabilidad exclusiva del frontend AG-UI.

## 9. Fallbacks

| Escenario | Comportamiento |
|-----------|---------------|
| Milvus falla (timeout/error) | Intentar pgvector. Si también falla, responder sin RAG con disclaimer: "No pude recuperar contexto específico. Consultá a nuestro equipo." |
| pgvector no disponible | Respuesta sin RAG con disclaimer. |
| LLM falla (timeout/error) | Respuesta de fallback segura: "Ocurrió un error al generar la respuesta. Por favor intentá de nuevo o contactanos directamente." |
| Guardrail bloquea respuesta | Respuesta degradada segura. No entregar respuesta que falle guardrails críticos. |
| Contexto insuficiente (top-K score bajo) | Pedir 1 pregunta mínima para refinar la consulta. No inventar respuesta. |
| Usuario pregunta por pricing/SLA | "No contamos con información de costos en el knowledge actual. Consultá con nuestro equipo comercial." |
| Empty response del LLM | Reintentar 1 vez con temperatura 0.4. Si persiste, fallback seguro. |
| Slot no detectable | Preguntar específicamente por el slot faltante (máximo 1 pregunta adicional). |

### Respuestas de fallback seguras

**Sin RAG:**
> "No pude recuperar información específica sobre tu consulta. Te recomiendo contactar a nuestro equipo para una atención personalizada."

**Error LLM:**
> "Ocurrió un error al procesar tu consulta. Por favor intentá de nuevo o escribinos directamente."

**Bloqueado por guardrail:**
> "No puedo proporcionar esa información porque excede los límites de lo que puedo confirmar. Consultá con nuestro equipo comercial."

## 10. Métricas

### Por turno

| Métrica | Tipo | Descripción |
|---------|------|-------------|
| `retrieval_latency_ms` | int | Tiempo total de retrieval (embedding + Milvus) |
| `llm_latency_ms` | int | Tiempo de generación LLM |
| `total_latency_ms` | int | Tiempo total del turno |
| `time_to_first_ack_ms` | int | Tiempo hasta primer evento (template) |
| `time_to_first_intelligent_answer_ms` | int | Tiempo hasta primera respuesta inteligente |
| `tokens_prompt` | int | Tokens del prompt |
| `tokens_completion` | int | Tokens generados |
| `tokens_total` | int | Tokens totales |
| `cost_estimate` | float | Costo estimado del turno |
| `guardrail_failures` | int | Fallos de guardrail en este turno |
| `guardrail_warnings` | int | Advertencias de guardrail |
| `slot_fill_rate` | float | Proporción de slots detectados vs posibles |
| `useful_orientation` | bool | ¿La respuesta orienta comercialmente? |
| `user_continuation` | bool | ¿El usuario continuó la conversación? |

### Por sesión

| Métrica | Descripción |
|---------|-------------|
| `turn_count` | Total de turnos |
| `avg_turn_latency_ms` | Latencia promedio por turno |
| `total_cost_estimate` | Costo total estimado |
| `guardrail_failure_rate` | Fallos de guardrail / total turnos |
| `completion_rate` | ¿La sesión llegó a diagnóstico útil? |
| `slot_completeness` | Slots llenados / slots totales al final |

## 11. Decisiones fuera de alcance

| Componente | Decisión | Explicación |
|------------|----------|-------------|
| ArangoDB | Fuera | No hay evidencia de que grafos mejoren el diagnóstico comercial actual. Re-evaluar si el modelo de conocimiento requiere relaciones jerárquicas complejas no modelables en PostgreSQL + Milvus. |
| Cross-encoder | Fuera | Content_gap es el limitante, no ranking. Re-evaluar después de mejorar cobertura de knowledge y si la precisión del top-K es insuficiente. |
| GPT-5.5 runtime | Fuera | Posible judge/oracle offline para evaluación de calidad. No como runtime conversacional por latencia y costo. |
| Step-to-Action | No implementar | Requiere orquestación de workers, permisos de ejecución, HITL y auditoría transaccional. Fase futura separada. |
| lead_capture real | No implementar | Requiere integración con CRM, formularios, verificación de contacto y políticas de datos. Fase futura separada. |
| diagnostic_code productivo | No implementar | Requiere motor de reglas, catálogo de diagnósticos, scoring determinístico y validación comercial. Separado del asistente conversacional. |
| WhatsApp handoff automático | No implementar | Requiere integración con API de WhatsApp, templates de mensajes, política de handoff y auditoría. Fase futura separada. |
| CRM real | No integrar | Dependencia externa. Definir interfaz de integración primero. |
| Frontend AG-UI/SSE | No implementar | Contrato definido. Implementación en fase separada después del backend runtime. |
| pricing/SLA | No generar | Prohibido por guardrails. Cualquier respuesta de pricing/SLA debe decir "no documentado" o delegar al equipo comercial. |

## 12. Riesgos abiertos

| Riesgo | Impacto | Mitigación propuesta |
|--------|---------|---------------------|
| Latencia LLM ~5-6s por turno | Experiencia de usuario lenta | Respuesta progresiva (quick ack → LLM). Reducir max_output_tokens. Evaluar gpt-5-nano sin reasoning si es configurable. |
| Empty response / token behavior | El LLM agota tokens de razonamiento y devuelve vacío | Reintentar con temperatura más alta. Aumentar max_tokens. Evaluar si el razonamiento es necesario para todos los turnos. |
| Dependencia de Milvus | Si Milvus no está disponible, el sistema degrada | pgvector como fallback implementado desde el inicio. Respuesta sin RAG como último recurso. |
| Necesidad de policy por dominio | Un solo template/prompt no sirve para todos los dominios futuros | PromptPolicy configurable por assistant_instance/package. Template seguro configurable. |
| Evaluación heurística no reemplaza humana | Falsos positivos/negativos en guardrails | Mantener heurística como primera línea. Agregar evaluación periódica con LLM-as-judge (offline) usando GPT-5.5. |
| Slot detection / coverage | El asistente necesita mejor cobertura de knowledge para detectar slots | Fase separada de knowledge gap patch. Por ahora, el asistente pregunta cuando no detecta. |
| Observabilidad y auditoría | Sin métricas no se puede mejorar | MetricsRecorder y AuditTrail definidos en este diseño. Implementar desde la Fase 1.8a. |
| Reconstrucción de índice Milvus | Si Milvus se pierde, hay que repoblar | PostgreSQL tiene los embeddings originales. Script de reconstrucción existente (Fase 1.6j). Automatizar como worker. |

## 13. Plan de implementación futuro sugerido

No implementar ahora. Solo orden propuesto para fases futuras.

### Fase 1.8a — Interfaces / Runtime Skeleton

- Definir interfaces Python (Protocols) para RetrievalProvider, LLMProvider, GuardrailPolicy, MetricsRecorder.
- Crear AssistantConversationRuntime skeleton sin dependencias externas.
- ConversationState en memoria con dataclass.
- Tests de contrato de interfaces.

### Fase 1.8b — MilvusRetrievalProvider con fallback pgvector

- Implementar MilvusRetrievalProvider real.
- Implementar PgvectorRetrievalProvider (reusar lógica de labs).
- Integration tests con Milvus real y pgvector real.
- Script de health check para Milvus.

### Fase 1.8c — PromptPolicy + GuardrailPolicy

- Implementar PromptPolicy configurable por assistant_instance.
- Implementar GuardrailPolicy (reusar lógica de evaluator.py de Fase 1.7b/1.7c).
- Tests de coverage de guardrails.
- Policy registry en PostgreSQL (tabla nueva o metadata JSON).

### Fase 1.8d — ConversationState persistence

- Persistir ConversationState en PostgreSQL.
- Cargar estado al iniciar turno.
- Tests de persistencia y recuperación.

### Fase 1.8e — Progressive event contract internal

- Implementar ProgressiveEventEmitter interno (sin SSE).
- Integrar eventos en AssistantConversationRuntime.
- Tests de emisión de eventos.

### Fase 1.8f — Endpoint controlado backend-only

- Endpoint HTTP único (POST /api/assistant/turn).
- Sin frontend, sin SSE.
- Tests de integración endpoint → runtime.
- Smoke real contra Milvus + LLM.

### Aclaración

La Fase 1.8 actual (este documento) solo diseña. Las subfases 1.8a–1.8f son propuestas para implementación futura, no compromiso de órden ni alcance.

## 14. Criterios para avanzar a implementación

La Fase 1.8a (skeleton/interfaces) puede comenzar cuando:

1. ✅ Esta decision note está aprobada.
2. ✅ No hay cambios pendientes de labs que invaliden las decisiones.
3. ✅ PostgreSQL se mantiene como source of truth (no se degrada a cache).
4. ✅ Milvus es reconstruible desde PostgreSQL en cualquier momento.
5. ✅ Los guardrails se incorporan antes del primer endpoint (no después).
6. ✅ Las métricas mínimas están definidas (este documento).
7. ✅ No se exponen capacidades futuras como listas en ningún contrato.
8. ✅ ArangoDB, cross-encoder, GPT-5.5 runtime quedan fuera.

---

*Documento de diseño runtime Fase 1.8 — Sales Diagnosis Assistant.*
*No implementa código productivo. No crea endpoints. No toca frontend.*
*Próximo paso sugerido: Fase 1.8a — Interfaces / Runtime Skeleton.*
