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

## Evaluación — Fase 1.7b (refinada)

La lógica de evaluación se extrajo a `evaluator.py` con 5 capas independientes:

| Capa | Función | Propósito |
|------|---------|-----------|
| 1. Response shape | `evaluate_response_shape()` | Empty, too_long, too_many_questions |
| 2. Commercial usefulness | `evaluate_commercial_usefulness()` | Orientation, diagnosis, concrete steps |
| 3. Safety/anti-overpromise | `evaluate_safety()` + `evaluate_planned_extension()` | Real forbidden vs correctly declined; planned extension tracking |
| 4. Knowledge grounding | `evaluate_knowledge_grounding()` | Says_not_documented vs invents_detail |
| 5. Slot behavior | `evaluate_slots()` | Detected slots count |

### Mejoras respecto a Fase 1.7

- **Word boundaries** (`\b`) en lugar de substring — evita falso positivo "ars" dentro de otra palabra
- **Negación contextual** — detecta si un término prohibido aparece cerca de "no tenemos", "no está disponible", etc.
- **Correct decline vs hallucination** — separa `pricing_correctly_declined` de `unsupported_pricing_claim`
- **Planned extension tracking** — por capacidad individual (step_to_action, lead_capture, etc.)
- **Empty response** — clasificación separada, no como guardrail failure

### Taxonomía de fallos

| Categoría | Significa |
|-----------|-----------|
| `empty_response` | Respuesta vacía (error de LLM o sin contenido) |
| `response_too_long` | Excede 2000 caracteres |
| `too_many_questions` | Más de 3 preguntas en un turno |
| `real_forbidden_claim` | Término prohibido sin negación cercana |
| `no_orientation` | No orienta ni diagnostica |
| `planned_extension_misrepresented` | Capacidad futura vendida como lista |

### Reevaluación sin LLM

Para reevaluar resultados existentes sin re-ejecutar el lab:

```bash
# Reevaluar resultado más reciente:
uv run python lab/sales-diagnosis-assistant-conversation/scripts/reevaluate_results.py

# Reevaluar archivo específico:
uv run python lab/sales-diagnosis-assistant-conversation/scripts/reevaluate_results.py \
  --results-file results/conversation_lab_20260610_112024.json

# Reevaluar y guardar en ruta específica:
uv run python lab/sales-diagnosis-assistant-conversation/scripts/reevaluate_results.py \
  --results-file results/conversation_lab_20260610_112024.json \
  --output results/reevaluated.json
```

Esto agrega `refined_evaluation` por turno y `refined_scenario_evaluation` por escenario al JSON.

### Reporte e infografía con datos refinados

```bash
# Reporte detallado (usa refined_summary si existe):
uv run python lab/sales-diagnosis-assistant-conversation/scripts/generate_report.py

# Infografía HTML (usa refined_summary si existe):
uv run python lab/sales-diagnosis-assistant-conversation/scripts/generate_infographics.py
```

### Auditoría de fallos de guardrail

```bash
# Auditar fallos reales del último resultado reevaluado:
uv run python lab/sales-diagnosis-assistant-conversation/scripts/audit_guardrail_failures.py

# Auditar archivo específico:
uv run python lab/sales-diagnosis-assistant-conversation/scripts/audit_guardrail_failures.py \
  --results-file results/conversation_lab_20260610_112024_reevaluated.json
```

Genera `results/guardrail_failure_audit_<timestamp>.md` con detalle por turno, matched terms, negation status y probable cause.

### Guardrail fixes report (Fase 1.7c)

Tras aplicar correcciones en `evaluator.py`, generar reporte de fix:

```bash
# Reevaluar con evaluador corregido:
uv run python lab/sales-diagnosis-assistant-conversation/scripts/reevaluate_results.py

# Ver reporte de fix guardado:
cat lab/sales-diagnosis-assistant-conversation/results/guardrail_fix_latest.md
```

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

## Fase 1.7d — Progressive Response Simulation

Simula una experiencia progresiva tipo SSE/AG-UI sin implementar endpoints reales. Compara 3 estrategias de respuesta para medir latencia percibida, time-to-first-user-value y tradeoffs.

### Estrategias

| Estrategia | Quick answer | Final answer | LLM calls | Riesgo |
|------------|-------------|--------------|-----------|--------|
| `single-call` | — | LLM completa (500 tok) | 1 | Percepción lenta si >3s |
| `progressive-two-step` | LLM corta (120 tok) | LLM completa (500 tok) | 2 | Duplica costo/latencia total |
| `templated-quick-final-llm` | Template (0ms LLM) | LLM completa (500 tok) | 1 | Quick genérica |

### Eventos simulados

```
team360.status.retrieval_started → team360.sources.ready → team360.answer.quick_started
→ team360.answer.quick_ready → team360.status.final_started → team360.answer.final_ready
→ team360.metrics.ready → team360.done
```

### Ejecución

```bash
# Dry run:
uv run python lab/sales-diagnosis-assistant-conversation/run_progressive_response_lab.py --dry-run

# Sin LLM (solo validar flujo de eventos, casos 2):
uv run python lab/sales-diagnosis-assistant-conversation/run_progressive_response_lab.py \
  --no-llm --strategy templated-quick-final-llm --limit-cases 2

# Single-call baseline (casos 3):
uv run python lab/sales-diagnosis-assistant-conversation/run_progressive_response_lab.py \
  --strategy single-call --limit-cases 3

# Progressive two-step (casos 3):
uv run python lab/sales-diagnosis-assistant-conversation/run_progressive_response_lab.py \
  --strategy progressive-two-step --limit-cases 3

# Templated quick + final LLM (casos 3):
uv run python lab/sales-diagnosis-assistant-conversation/run_progressive_response_lab.py \
  --strategy templated-quick-final-llm --limit-cases 3

# Todos los casos y todas las estrategias (requiere LLM):
uv run python lab/sales-diagnosis-assistant-conversation/run_progressive_response_lab.py \
  --strategy single-call
uv run python lab/sales-diagnosis-assistant-conversation/run_progressive_response_lab.py \
  --strategy progressive-two-step
uv run python lab/sales-diagnosis-assistant-conversation/run_progressive_response_lab.py \
  --strategy templated-quick-final-llm
```

### Reportes

```bash
# Reporte detallado:
uv run python lab/sales-diagnosis-assistant-conversation/scripts/generate_progressive_report.py

# Infografía HTML:
uv run python lab/sales-diagnosis-assistant-conversation/scripts/generate_progressive_infographics.py
```

## Lab closure decision

Este lab ha completado su ciclo de experimentación. Las decisiones arquitectónicas validadas están documentadas en:

[decision_notes/20260610_sales_diagnosis_assistant_lab_closure.md](decision_notes/20260610_sales_diagnosis_assistant_lab_closure.md)

Resumen de cierre:

- **PostgreSQL 18**: source of truth
- **Milvus 2.6**: vector runtime derivado para conversación
- **pgvector**: baseline/dev/fallback
- **gpt-5-nano low**: primera respuesta inteligente
- **Template seguro**: solo acuse/progreso, no reemplaza LLM
- **AG-UI/SSE**: experiencia progresiva futura
- **ArangoDB**: fuera por ahora
- **Cross-encoder**: fuera por ahora
- **GPT-5.5**: judge/oracle offline, no runtime

Próximo paso recomendado: **Fase 1.8 — Runtime Design Handoff**.

El diseño runtime completo está documentado en:
[../../../docs/architecture/sales_diagnosis_assistant_runtime_design.md](../../../docs/architecture/sales_diagnosis_assistant_runtime_design.md)

### Archivos

```
run_progressive_response_lab.py       # Runner con 3 estrategias
scripts/generate_progressive_report.py      # Reporte detallado markdown
scripts/generate_progressive_infographics.py # Infografía HTML
results/progressive_response_*.json         # Resultados crudos
results/progressive_response_*_detailed_report.md  # Reporte detallado
infografias/progressive_response_*_infografia.html  # Infografía
```

### Métricas

- avg_time_to_first_status_ms / sources_ready_ms / quick_answer_ms / final_answer_ms
- p50/p95 quick answer and final answer
- Quick answer safe rate (0 forbidden claims)
- Final answer pass rate
- Guardrail failures count
- Perceived latency gain vs single-call baseline
- Additional LLM cost estimate (tokens and latency)
