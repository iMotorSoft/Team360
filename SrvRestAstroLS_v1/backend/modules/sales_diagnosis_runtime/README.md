# Sales Diagnosis Runtime Module -- Fase 1.8a

## Objetivo

Modulo interno skeleton para el runtime del asistente de ventas/diagnostico de Team360.

Define contratos, interfaces y orquestador basico sin implementar:

* endpoints HTTP;
* SSE productivo;
* frontend;
* Milvus real;
* LLM real (gpt-5-nano low);
* persistencia real en PostgreSQL;
* Step-to-Action, lead_capture, diagnostic_code, WhatsApp handoff.

## Arquitectura

PostgreSQL 18 = source of truth
Milvus 2.6     = vector runtime derivado (provider futuro)
gpt-5-nano low = primera respuesta inteligente (provider futuro)
Template seguro = acuse/progreso, no reemplaza LLM

## Que hace este modulo

* Define 6 contratos de datos (dataclasses).
* Define 4 interfaces/protocols (RetrievalProvider, LLMProvider, StateRepository, MetricsRecorder).
* Implementa providers null para testeo y desarrollo.
* Implementa PromptPolicy y GuardrailPolicy con reglas de Fase 1.7c.
* Implementa AssistantConversationRuntime skeleton completo.
* Incluye errores controlados (6 clases).
* Incluye tests unitarios sin red.

## Que NO hace

* No expone endpoints HTTP.
* No implementa SSE.
* No llama LLM real.
* No llama Milvus.
* No toca DB.
* No modifica frontend.

## Archivos

| Archivo | Proposito |
|---------|-----------|
| `__init__.py` | Export publico |
| `contracts.py` | Dataclasses: TurnInput, TurnOutput, ConversationState, RetrievedChunk, GuardrailResult, ProgressiveEvent, RuntimeMetrics |
| `errors.py` | Excepciones controladas |
| `providers.py` | Interfaces y Null providers |
| `policies.py` | PromptPolicy y GuardrailPolicy |
| `runtime.py` | AssistantConversationRuntime orchestrator |

## Tests

```bash
cd SrvRestAstroLS_v1/backend
uv run pytest tests/test_sales_diagnosis_runtime_contracts.py -v
```

## Proximas fases sugeridas

1. 1.8b -- MilvusRetrievalProvider runtime con fallback pgvector.
2. 1.8c -- Prompt y GuardrailPolicy hardening con registry en PostgreSQL.
3. 1.8d -- ConversationState persistence en PostgreSQL.
4. 1.8e -- Progressive event contract interno completo.
5. 1.8f -- Endpoint backend-only controlado.
