# Sales Diagnosis Assistant Conversation Lab — Fase 1.7

## Objetivo

Evaluar conversación multi-turn del asistente de diagnóstico comercial de Team360 con Milvus retrieval + gpt-5-nano low.

Validar si el asistente puede:

- Recibir texto libre y entender intención inicial
- Recuperar contexto relevante en Milvus
- Responder con gpt-5-nano low
- Hacer pocas preguntas útiles
- Completar slots mínimos
- Orientar comercialmente
- Generar un diagnóstico inicial útil
- Respetar límites anti-overpromise
- No vender capacidades futuras como listas

## Arquitectura

- **PostgreSQL 18**: source of truth (contiene los embeddings originales)
- **Milvus 2.6**: índice vectorial runtime derivado para baja latencia
- **Markdown chunks**: evidencia recuperada
- **gpt-5-nano low**: generador de respuesta con razonamiento comercial
- **Conversation state**: gestionado en memoria (slots, historial, turnos)
- **PGVector**: baseline/fallback/dev (no se usa en este lab)
- **No ArangoDB**: fuera de alcance
- **No cross-encoder**: fuera de alcance
- **No producción**: solo laboratorio

## Estructura

```
lab/sales-diagnosis-assistant-conversation/
  README.md
  run_conversation_lab.py
  cases/conversation_cases.json
  scripts/generate_report.py
  scripts/generate_infographics.py
  results/*.json / *.md
  infografias/*.html
```

## Escenarios

10 escenarios multi-turn (2 turnos cada uno) que cubren:

1. Consulta genérica sobre automatización
2. Leads perdidos por falta de seguimiento
3. WhatsApp inteligente con calificación
4. Overpromise — IA autónoma
5. Diagnóstico inicial — no sabe qué automatizar
6. Canal distribuidor
7. Capacidades futuras (Step-to-Action, lead capture, diagnostic_code, WhatsApp)
8. Pricing y SLA
9. Seguridad y aislamiento multi-tenant
10. Caso ambiguo — IA para empresa

## Dependencias

- `pymilvus>=3.0.0` (en `backend/pyproject.toml`)
- PostgreSQL 18 con datos de knowledge ingestion cargados
- Milvus 2.6 corriendo, con colección indexada
- `OPENAI_API_KEY` o `OpenAI_Key_JAI_query` en entorno

## Variables de entorno

- `OPENAI_API_KEY` o `OpenAI_Key_JAI_query`
- `DB_PG_V360_URL` o `TEAM360_DB_URL_PSQL`
- `MILVUS_URI` (opcional, default: `http://localhost:19530`)
- `TEAM360_LITELLM_BASE_URL` (opcional, para proxy LiteLLM)

## Ejecución

```bash
# Dry run (validar conectividad):
uv run python lab/sales-diagnosis-assistant-conversation/run_conversation_lab.py --dry-run

# Solo retrieval, sin LLM:
uv run python lab/sales-diagnosis-assistant-conversation/run_conversation_lab.py --no-llm --limit-cases 2

# Con LLM (completo), 2 escenarios:
uv run python lab/sales-diagnosis-assistant-conversation/run_conversation_lab.py --limit-cases 2

# Con LLM (completo), todos los escenarios:
uv run python lab/sales-diagnosis-assistant-conversation/run_conversation_lab.py

# Con modelo y reasoning effort específicos:
uv run python lab/sales-diagnosis-assistant-conversation/run_conversation_lab.py --model gpt-5-nano --reasoning-effort low

# Reporte detallado:
uv run python lab/sales-diagnosis-assistant-conversation/scripts/generate_report.py

# Infografía HTML:
uv run python lab/sales-diagnosis-assistant-conversation/scripts/generate_infographics.py
```

## Parámetros CLI

| Parámetro | Default | Descripción |
|-----------|---------|-------------|
| `--model` | `gpt-5-nano` | Modelo LLM |
| `--reasoning-effort` | `None` | `low`, `medium`, `high` |
| `--temperature` | `0.2` | Temperatura del modelo |
| `--max-output-tokens` | `500` | Tokens máximos de respuesta |
| `--max-context-chars` | `6000` | Caracteres máximos de contexto |
| `--top-k` | `5` | Chunks para contexto LLM |
| `--top-n` | `20` | Pool de recuperación |
| `--limit-cases` | `None` | Limitar escenarios |
| `--no-llm` | `False` | Solo retrieval, sin LLM |
| `--dry-run` | `False` | Validar conectividad |

## Evaluación

### Por turno

- Respuesta no vacía
- Respuesta breve (< 2000 chars)
- Máximo 3 preguntas
- Orientación concreta presente
- Sin forbidden claims
- Sin pricing/SLA inventado
- No promete Step-to-Action/lead_capture/diagnostic_code/WhatsApp handoff como listo
- Diferencia planned_extension vs listo cuando corresponde
- Usa contexto recuperado
- Si falta info, pide slot mínimo

### Por escenario

- Slots mínimos detectados
- Diagnóstico inicial generado o encaminado
- Límites respetados
- Conversación útil
- No exceso de preguntas
- No alucinación comercial

## Decision rules

- **A**: Asistente conversacional viable para siguiente fase controlada
- **B**: Viable con guardrails más fuertes
- **C**: Viable pero requiere respuesta progresiva/SSE
- **D**: Requiere modelo alternativo
- **E**: Requiere más knowledge coverage
- **F**: No avanzar todavía

## Qué NO hace este lab

- No toca frontend, routes, endpoints HTTP
- No toca diagnosis ni automation_diagnosis productivo
- No crea migraciones
- No modifica documents approved/drafts
- No re-embeddiza corpus
- No usa ArangoDB
- No usa cross-encoder
- No cambia runtime productivo
- No activa Step-to-Action
- No activa lead capture
- No activa diagnostic_code
- No activa WhatsApp handoff
- No usa CRM real
- No hardcodea API keys
