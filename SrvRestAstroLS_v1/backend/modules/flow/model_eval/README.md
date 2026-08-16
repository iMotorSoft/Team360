# Team360 Flow — Model Evaluation

Evaluación reproducible de modelos LLM para el análisis inteligente de
Team360 Flow. La salida es una **recomendación**, nunca un cambio automático
del modelo productivo.

## Scope

- **WRITE exclusivo de este agente**: `backend/modules/flow/model_eval/**`.
- El resto del módulo Flow es READ ONLY: contratos, prompts, dominio,
  clasificación y routing NO se modifican.
- Los modelos se invocan únicamente mediante **LiteLLM** con los aliases
  registrados. No hay SDKs de proveedor ni configuración LiteLLM propia.

## Modelos evaluados

| Alias | Rol |
| --- | --- |
| `openai_gpt-5.4-nano` | Baseline productivo actual de Flow |
| `openai_gpt-5.6-luna-medium` | Comparación principal |
| `deepseek_deepseek_4_flash` | Evaluación adicional (resultados separados) |
| `deepseek_deepseek_4_pro` | Evaluación adicional (resultados separados) |

## Reuso real de contratos

El benchmark NO duplica prompts ni schemas. Usa los adaptadores productivos:

- `LiteLLMFlowIntakeInterpreter` (`modules/flow/intake/ai.py`): contrato
  `_INITIAL_SCHEMA` — `requests[]` (description, tentative_category,
  location_text, missing_data, context_notes, confidence) y
  `clarification_question`. Temperatura 0.2, max_tokens 1800.
- `LiteLLMOperationalInterpreter` (`modules/flow/operational_ai.py`): contrato
  `_SCHEMA` — `action` (ACK_OR_PROGRESS, RESOLUTION_PROPOSED, AMBIGUOUS,
  UNRELATED, UNSUPPORTED_OPERATIONAL_ACTION) y `summary`. Temperatura 0.0,
  max_tokens 300.

Todos los modelos reciben exactamente el mismo dataset, mismo prompt, mismo
system prompt, mismo contrato y mismos parámetros (determinismo: no se cambian
parámetros entre modelos). La derivación usa la lógica productiva real
`resolve_sector_id` de `modules/flow/domain/routing.py`.

## Datasets

- `cases_intake.json` (20 casos): solicitud clara/ambigua/incompleta,
  prioridad normal, caso urgente, derivación evidente/menos evidente, texto
  informal, errores ortográficos, mensaje corto/largo, datos contradictorios,
  múltiples temas, información irrelevante, falta de responsable claro, caso
  fuera de alcance, pedir información adicional, evitar inventar información,
  categoría fuera de catálogo y solicitud formal. Sintéticos, inspirados en el
  dominio real (alumbrado) y en el E2E documentado de Flow.
- `cases_operational.json` (8 casos): decisiones críticas de respuestas
  operativas. En Flow el escalamiento por SLA es determinístico; la decisión IA
  con criticidad de escalamiento es `RESOLUTION_PROPOSED` (dispara el pedido de
  aprobación al supervisor). FP = afirmar resolución sin lenguaje inequívoco;
  FN = no detectar resolución inequívoca.

Nota de alcance: el contrato de intake no tiene campos de prioridad ni
escalamiento; no se inventan campos productivos. Los casos de prioridad miden
extracción correcta bajo contexto normal/urgente (sin distorsión de categoría
ni datos inventados).

## Ejecución

Desde `SrvRestAstroLS_v1/backend`:

```bash
# los cuatro modelos + una pasada de consistencia en el subconjunto
uv run python -m modules.flow.model_eval.benchmark --all --consistency 1

# solo la comparación principal
uv run python -m modules.flow.model_eval.benchmark

# un alias puntual
uv run python -m modules.flow.model_eval.benchmark --model openai_gpt-5.4-nano

# validar dataset y plan sin llamar modelos
uv run python -m modules.flow.model_eval.benchmark --dry-run
```

El runner hace un preflight real por alias (auth, cuota, endpoint, contenido no
vacío) antes del benchmark; si un alias falla el preflight se omite y queda
documentado en `summary.json`.

## Tests del harness (sin llamadas reales)

```bash
uv run pytest modules/flow/model_eval/tests -q
```

Cubren: carga/validación de dataset, scoring, clasificación de errores,
agregación de métricas, escalamiento FP/FN, JSON inválido, `N/A` de tokens/costo
y regla de recomendación. Nunca llaman a los modelos reales.

## Resultados

- `results/per_case.jsonl`: un JSON por `modelo × caso` con case_id, alias,
  timestamp, success/error, resultado estructurado, checks, score, latencia,
  usage de tokens y error type.
- `results/summary.json`: métricas por modelo, comparación Nano vs Luna,
  sección DeepSeek, tabla de fallos, consistencia, preflight y recomendación.
- Costo: `N/A` (no hay precios confiables disponibles desde la infraestructura
  actual; no se hardcodean precios dudosos).
- No se guardan secretos, headers, chain-of-thought ni contenido crudo del
  proveedor (DeepSeek consume tokens de razonamiento; solo se guarda el
  resultado estructurado validado).

## Decisión

El flujo es `benchmark → resultados → recomendación → decisión humana →
eventual cambio controlado`. Este módulo produce `FLOW_MODEL_RECOMMENDATION=<alias>`
y nunca modifica el alias productivo, la configuración LiteLLM, env vars ni
prompts de Flow.
