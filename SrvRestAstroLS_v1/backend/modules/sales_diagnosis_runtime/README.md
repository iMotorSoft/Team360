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
* Define 5 interfaces/protocols (QueryEmbeddingProvider, RetrievalProvider, LLMProvider, StateRepository, MetricsRecorder).
* Implementa providers null para testeo y desarrollo.
* Implementa MilvusRetrievalProvider con config por env.
* Implementa PromptPolicy y GuardrailPolicy con reglas de Fase 1.7c.
* Implementa AssistantConversationRuntime skeleton completo.
* Incluye errores controlados (8 clases).
* Incluye tests unitarios sin red.

## Que NO hace

* No expone endpoints HTTP.
* No implementa SSE.
* No llama LLM real.
* No toca DB.
* No modifica frontend.
* No modifica corpus knowledge.
* No re-embeddiza.

## Archivos

| Archivo | Proposito |
|---------|-----------|
| `__init__.py` | Export publico |
| `contracts.py` | Dataclasses: TurnInput, TurnOutput, ConversationState, RetrievedChunk, GuardrailResult, ProgressiveEvent, RuntimeMetrics |
| `errors.py` | Excepciones controladas |
| `milvus_provider.py` | MilvusRetrievalProvider + MilvusRuntimeConfig |
| `providers.py` | Interfaces, Null providers y QueryEmbeddingProvider |
| `policies.py` | PromptPolicy y GuardrailPolicy |
| `runtime.py` | AssistantConversationRuntime orchestrator |

## MilvusRetrievalProvider — Fase 1.8b

Implementa `RetrievalProvider` contra Milvus 2.6 como indice vectorial derivado.

### Dependencia

Requiere `pymilvus>=3.0.0`. No instalado por defecto en pyproject.toml.
Instalar con: `uv add pymilvus>=3.0.0`

### Env vars

| Variable | Default | Descripcion |
|----------|---------|-------------|
| `TEAM360_MILVUS_URI` | — | URI completa de conexion |
| `TEAM360_MILVUS_HOST` | — | Host (alternativa a URI) |
| `TEAM360_MILVUS_PORT` | 19530 | Puerto |
| `TEAM360_MILVUS_TOKEN` | — | Token de autenticacion |
| `TEAM360_MILVUS_COLLECTION` | `knowledge_chunks` | Nombre de coleccion |
| `TEAM360_EMBEDDING_VERSION` | — | Version de embedding para filtrar |
| `TEAM360_KNOWLEDGE_SCOPE_ID` | — | Knowledge scope ID para filtrar |

### Contrato

Requiere `QueryEmbeddingProvider` para convertir texto a vector de query.
Sin embedding provider configurado, lanza `RetrievalUnavailableError`.

### No implementa

* pgvector fallback (futuro).
* Cross-encoder reranking (fuera de alcance).
* ArangoDB (fuera de alcance).
* LLM (modelo separado).

## Tests

```bash
cd SrvRestAstroLS_v1/backend
uv run pytest tests/test_sales_diagnosis_runtime_contracts.py -v
uv run pytest tests/test_sales_diagnosis_milvus_provider.py -v
```

## Proximas fases sugeridas

1. ~~1.8b -- MilvusRetrievalProvider runtime con fallback pgvector.~~ **(Completado)**
2. 1.8c -- Prompt y GuardrailPolicy hardening con registry en PostgreSQL.
3. 1.8d -- ConversationState persistence en PostgreSQL.
4. 1.8e -- Progressive event contract interno completo.
5. 1.8f -- Endpoint backend-only controlado.
