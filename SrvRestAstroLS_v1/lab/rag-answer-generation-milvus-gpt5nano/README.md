# RAG Answer Generation Lab — Milvus + gpt-5-nano low — Fase 1.6k

## Objetivo

Evaluar el flujo RAG completo para el asistente de diagnóstico comercial de Team360:
consulta → embedding → Milvus retrieval → contexto Markdown → LLM → respuesta.

No busca máxima inteligencia. Busca viabilidad conversacional inicial con baja latencia.

## Hipótesis

Con Milvus rápido + buenos segmentos Markdown + gpt-5-nano low, se puede generar una
primera respuesta comercial útil, rápida y barata para el asistente de ventas/diagnóstico.

## Arquitectura

- **PostgreSQL 18**: source of truth (contiene los embeddings originales)
- **Milvus 2.6**: índice vectorial runtime derivado para baja latencia
- **PGVector**: baseline/fallback/dev (no se usa en este lab)
- **gpt-5-nano low**: generador de respuesta con reasoning_effort low
- **No ArangoDB**: fuera de alcance
- **No cross-encoder**: fuera de alcance
- **No producción**: solo laboratorio

## Dependencias

- `pymilvus>=3.0.0` (en `backend/pyproject.toml`)
- PostgreSQL 18 con datos de knowledge ingestion cargados
- Milvus 2.6 corriendo, con colección de Fase 1.6j indexada
- `OPENAI_API_KEY` en entorno (para embeddings y LLM)
- Opcional: `TEAM360_LITELLM_BASE_URL` para enrutar LLM a través de proxy LiteLLM

## Variables de entorno

- `OPENAI_API_KEY` o `OpenAI_Key_JAI_query`
- `DB_PG_V360_URL` o `TEAM360_DB_URL_PSQL`
- `MILVUS_URI` (opcional, default: `http://localhost:19530`)
- `TEAM360_LITELLM_BASE_URL` (opcional)

## Ejecución

```bash
# Dry run (validar conectividad):
uv run python lab/rag-answer-generation-milvus-gpt5nano/run_rag_answer_lab.py --dry-run

# Solo retrieval, sin LLM (validar que Milvus responde):
uv run python lab/rag-answer-generation-milvus-gpt5nano/run_rag_answer_lab.py --no-llm --limit-cases 3

# Con LLM (completo):
uv run python lab/rag-answer-generation-milvus-gpt5nano/run_rag_answer_lab.py

# Con modelo y reasoning effort específicos:
uv run python lab/rag-answer-generation-milvus-gpt5nano/run_rag_answer_lab.py --model gpt-5-nano --reasoning-effort low

# Reporte detallado:
uv run python lab/rag-answer-generation-milvus-gpt5nano/scripts/generate_report.py

# Infografía HTML:
uv run python lab/rag-answer-generation-milvus-gpt5nano/scripts/generate_infographics.py
```

## Estructura

```
lab/rag-answer-generation-milvus-gpt5nano/
  README.md
  run_rag_answer_lab.py
  cases/rag_answer_cases.json
  scripts/generate_report.py
  scripts/generate_infographics.py
  results/*.json / *.md
  infografias/*.html
```

## Casos de prueba

16 casos que cubren: comercial general, ventas/seguimiento, WhatsApp, diagnóstico,
anti-overpromise, límites comerciales, ambigüedad y seguridad/scope.

Cada caso tiene:
- `must_include`: términos/conceptos que deben estar en la respuesta
- `must_not_include`: términos prohibidos
- `risk_level`: high/medium/low

## Evaluación

Evaluación heurística automática (sin LLM juez):
- must_include presentes
- must_not_include ausentes
- Sin claims prohibidos (precios, plazos, SLA)
- Respuesta no vacía ni demasiado larga
- Hace preguntas mínimas (1-3)
- Dice "no documentado/no disponible" cuando corresponde
- Da orientación concreta

## Decision rules

- **A**: gpt-5-nano low viable para primera etapa (pass >= 70%, high-risk >= 90%)
- **B**: viable con guardrails adicionales (pass >= 60%)
- **C**: probar gpt-5-mini / medium en siguiente lab
- **D**: mejorar content coverage antes de modelo (pass < 30%)
- **F**: no avanzar a runtime todavía

## Qué no hace este lab

- No toca frontend, routes, endpoints HTTP
- No toca diagnosis ni automation_diagnosis productivo
- No usa ArangoDB
- No usa cross-encoder
- No cambia runtime productivo
- No re-embediza corpus
- No guarda secrets
