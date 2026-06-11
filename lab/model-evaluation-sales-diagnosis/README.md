# Model Evaluation — Sales Diagnosis

Laboratorio reproducible para comparar modelos LLM sobre el dataset headless del
diagnosticador Team360.

## Diferencia con backend/headless validation

| Aspecto | Backend (`backend/scripts/`) | Este lab (`lab/model-evaluation-sales-diagnosis/`) |
|---------|------------------------------|----------------------------------------------------|
| Propósito | Validar comportamiento funcional del runtime | Comparar calidad, latencia, costos entre modelos |
| Dataset | `sales_diagnosis_headless_questions_v1.json` (el mismo) | Mismo dataset, reutilizado |
| Modelos | Un modelo a la vez según env vars | Múltiples modelos secuenciales |
| Métricas | PASS/WARN/FAIL/SKIP por caso | Idem, más duración, fallbacks, provider, promedio |
| Salida | Tabla en stdout | JSONL/JSON sanitizado en `results/` |
| Reutilización | El evaluador backend se invoca como subproceso | No duplica lógica de evaluación |

El evaluador backend original (`evaluate_sales_diagnosis_headless_responses.py`)
sigue siendo la fuente de verdad para la evaluación semántica. Este laboratorio
lo invoca como subproceso para cada modelo y agrega metadatos de corrida.

## Objetivo

- Comparar calidad de respuestas (PASS/WARN/FAIL) entre modelos.
- Detectar fallback silencioso.
- Medir latencia por modelo y por caso.
- Estimar diferencias de provider (OpenAI directo vs LiteLLM).
- Documentar retrieval mode y dataset version en cada corrida.
- No modificar el runtime productivo.

## Modelos incluidos

| ID | Provider | Modo | Modelo |
|----|----------|------|--------|
| `openai_direct_gpt-5-nano` | OpenAI directo | `openai` | `gpt-5-nano` |
| `openai_gpt-5-nano` | LiteLLM → OpenAI | `litellm` | `openai_gpt-5-nano` |
| `openai_gpt_4o_mini_2024_07_18` | LiteLLM → OpenAI | `litellm` | `openai_gpt_4o_mini_2024_07_18` |
| `openrouter_qwen3_30b_a3b_thinking_2507` | LiteLLM → OpenRouter | `litellm` | `openrouter_qwen3_30b_a3b_thinking_2507` |
| `openrouter_deepseek_4_flash` | LiteLLM → OpenRouter | `litellm` | `openrouter_deepseek_4_flash` |

Los IDs legacy `litellm_*` y `openai_direct_gpt_5_nano` se aceptan como
aliases de CLI para no romper corridas existentes, pero los IDs canonicos son
los de la tabla.

## Modelos excluidos

- `gpt5.5-nano`, `gpt5.4-nano`, `openai_gpt-5.4-nano` — no existen en config.
- `whisper` — audio, no aplica.
- `flux`/image models — no aplican.

## Prerrequisitos

1. **Backend levantado** con product route habilitado (ver comandos abajo).
2. **LiteLLM proxy** corriendo en `http://localhost:4000` si se prueban aliases LiteLLM.
3. **Milvus** corriendo si `retrieval=milvus`.
4. **Env vars** requeridas según provider:
   - OpenAI directo: `TEAM360_OPENAI_KEY` o `OPENAI_API_KEY`.
   - LiteLLM: `TEAM360_LITELLM_BASE_URL` y `TEAM360_LITELLM_API_KEY`.

### Backend con product adapter + fake retrieval

```bash
cd SrvRestAstroLS_v1/backend

TEAM360_SALES_DIAGNOSIS_PRODUCT_ROUTE_ENABLED=1 \
TEAM360_SALES_DIAGNOSIS_PRODUCT_STATE_REPOSITORY=inmemory_test \
TEAM360_SALES_DIAGNOSIS_PRODUCT_RETRIEVAL_PROVIDER=fake \
  uv run litestar --app app:app run --host 127.0.0.1 --port 8018
```

### Backend con Milvus

```bash
cd SrvRestAstroLS_v1/backend

TEAM360_SALES_DIAGNOSIS_PRODUCT_ROUTE_ENABLED=1 \
TEAM360_SALES_DIAGNOSIS_PRODUCT_STATE_REPOSITORY=inmemory_test \
TEAM360_SALES_DIAGNOSIS_PRODUCT_RETRIEVAL_PROVIDER=milvus \
TEAM360_MILVUS_HOST=127.0.0.1 \
TEAM360_MILVUS_COLLECTION=team360_lab_pgvector_benchmark_openai_small_1536 \
TEAM360_KNOWLEDGE_SCOPE_ID=8b071443-5bd6-4fe4-bbc3-fc2dca179a5b \
TEAM360_EMBEDDING_VERSION=team360-openai-small-1536-v1 \
  uv run litestar --app app:app run --host 127.0.0.1 --port 8018
```

### Backend con OpenAI directo

```bash
cd SrvRestAstroLS_v1/backend

TEAM360_SALES_DIAGNOSIS_PRODUCT_ROUTE_ENABLED=1 \
TEAM360_SALES_DIAGNOSIS_PRODUCT_STATE_REPOSITORY=inmemory_test \
TEAM360_SALES_DIAGNOSIS_PRODUCT_LLM_PROVIDER=openai \
  uv run litestar --app app:app run --host 127.0.0.1 --port 8018
```

### Backend con LiteLLM

```bash
cd SrvRestAstroLS_v1/backend

TEAM360_SALES_DIAGNOSIS_PRODUCT_ROUTE_ENABLED=1 \
TEAM360_SALES_DIAGNOSIS_PRODUCT_STATE_REPOSITORY=inmemory_test \
TEAM360_SALES_DIAGNOSIS_PRODUCT_LLM_PROVIDER=litellm \
TEAM360_LITELLM_BASE_URL=http://localhost:4000 \
TEAM360_LITELLM_MODEL_ALIAS=openai_gpt-5-nano \
  uv run litestar --app app:app run --host 127.0.0.1 --port 8018
```

**Importante sobre provider mode**: El backend resuelve el provider de LLM al
inicio del proceso. No asumir que cambiar envs del runner cambia el backend ya
levantado. Para probar OpenAI directo y LiteLLM, se necesitan dos instancias de
backend separadas (puertos distintos) o dos corridas secuenciales.

## Comandos

Todos los comandos desde la raíz del proyecto.

### Dry-run (sin ejecutar modelos)

```bash
uv run python lab/model-evaluation-sales-diagnosis/scripts/run_model_evaluation.py \
  --dry-run --list-models
```

### Listar modelos disponibles

```bash
uv run python lab/model-evaluation-sales-diagnosis/scripts/run_model_evaluation.py \
  --list-models
```

### Correr todos los modelos LiteLLM (sin guardar resultados)

Requiere backend levantado con `TEAM360_SALES_DIAGNOSIS_PRODUCT_LLM_PROVIDER=litellm`.

```bash
uv run python lab/model-evaluation-sales-diagnosis/scripts/run_model_evaluation.py \
  --models openai_gpt-5-nano,openai_gpt_4o_mini_2024_07_18,openrouter_qwen3_30b_a3b_thinking_2507,openrouter_deepseek_4_flash \
  --no-write-results
```

### Correr un subconjunto

```bash
uv run python lab/model-evaluation-sales-diagnosis/scripts/run_model_evaluation.py \
  --models openrouter_deepseek_4_flash,openrouter_qwen3_30b_a3b_thinking_2507
```

### Correr con configuración custom

```bash
uv run python lab/model-evaluation-sales-diagnosis/scripts/run_model_evaluation.py \
  --config lab/model-evaluation-sales-diagnosis/config/run_matrix.example.json \
  --models openai_gpt-5-nano \
  --output lab/model-evaluation-sales-diagnosis/results/custom_run.jsonl
```

### Resumir resultados

```bash
uv run python lab/model-evaluation-sales-diagnosis/scripts/summarize_results.py \
  lab/model-evaluation-sales-diagnosis/results/run_20260611_120000.jsonl
```

### Resumir múltiples archivos

```bash
uv run python lab/model-evaluation-sales-diagnosis/scripts/summarize_results.py \
  lab/model-evaluation-sales-diagnosis/results/run_*.jsonl
```

### Resumen en JSON (para procesamiento)

```bash
uv run python lab/model-evaluation-sales-diagnosis/scripts/summarize_results.py \
  lab/model-evaluation-sales-diagnosis/results/run_20260611_120000.jsonl --json
```

## Estructura del laboratorio

```
lab/model-evaluation-sales-diagnosis/
├── README.md                          # Este archivo
├── config/
│   ├── models.json                    # Catálogo de modelos candidatos
│   └── run_matrix.example.json        # Configuración de corrida
├── datasets/
│   └── README.md                      # Cómo referenciar el dataset
├── results/
│   └── .gitkeep                       # Resultados sanitizados (git-ignored opcional)
└── scripts/
    ├── run_model_evaluation.py        # Runner principal
    └── summarize_results.py           # Resumen de resultados
```

## Seguridad

- No se guardan API keys, tokens ni DSN en resultados.
- Los resultados solo contienen metadatos de corrida (modelo, duración, counts).
- No se imprime la response_text de los casos evaluados (el evaluador sí lo hace,
  pero el lab solo captura el summary).
- Las env vars sensibles (`TEAM360_OPENAI_KEY`, `LITELLM_API_KEY`, etc.) se usan
  del entorno; no se hardcodean ni se loguean.
- Usar `--no-write-results` para evitar escritura a disco en entornos compartidos.

## Patrones tomados como referencia de JudaismoEnVivo

Se revisaron los laboratorios `reels_automation/labs/model_benchmark/` y
`SrvRestAstro_v2/lab/model-candidates-rag/` del proyecto JudaismoEnVivo. Los
patrones reutilizables para Team360 son:

- CLI con listado de modelos, filtros por modelo y modo dry-run.
- Catalogo de modelos separado de los scripts.
- Resultados auditables en JSON/JSONL y resumen tabular posterior.
- Medicion explicita de duracion/latencia por corrida.
- Manejo de errores como metadato de resultado, sin abortar toda la matriz.
- Comparacion agregada por modelo: totales, mejor pass-rate, mas rapido,
  modelos con fallas y modelos con fallback.
- Documentacion clara de estructura, prerequisitos, comandos y significado de
  columnas.

No se trajeron:

- Datasets, prompts, golden answers ni resultados de JudaismoEnVivo.
- Secrets, nombres de bases, credenciales locales, URLs internas de servicios
  ajenos o configuracion productiva de otro proyecto.
- Modelos ajenos al diagnostico de Team360, por ejemplo `gpt5.5-nano`,
  `gpt5.4-nano`, Whisper, Flux o modelos de imagen/audio.
- Logica de dominio de reels, halaja, DaisyUI o RAG de JudaismoEnVivo.
- Llamadas directas nuevas a proveedores desde el lab; Team360 sigue usando el
  evaluador backend como fuente de verdad.

## Notas

- Este laboratorio **no modifica** el runtime productivo.
- Este laboratorio **no activa** capacidades futuras por default.
- Este laboratorio **no toca** frontend, Console, WhatsApp, CRM, Step-to-Action,
  lead_capture ni diagnostic_code.
- La rama activa para este trabajo es `feature/console-backend-core`.
- No se debe cambiar a `feature/sales-diagnosis-runtime-skeleton`.
- Resultados reales deben ser sanitizados antes de commitear.
- Si se generan resultados reales (con LLM real), revisar que no contengan
  información sensible, tokens, DSN, nombres de clientes ni datos internos.

## Preflight: puerta de evidencia

**No correr ni aceptar un benchmark comparativo hasta que el preflight pase.**

El preflight valida dos capas antes de permitir la comparación:

### A. LiteLLM directo

Para cada alias, llama al proxy LiteLLM directamente y verifica:

- HTTP OK
- Content no vacío
- `finish_reason` disponible
- Latencia registrada

```bash
uv run python lab/model-evaluation-sales-diagnosis/scripts/preflight_model_evaluation.py \
  --check-litellm-direct \
  --models openai_gpt_4o_mini_2024_07_18,openrouter_qwen3_30b_a3b_thinking_2507
```

### B. Backend product adapter

Verifica que el backend levantado esté usando realmente el alias esperado y que
`provider_result` contenga evidencia de respuesta real.

```bash
uv run python lab/model-evaluation-sales-diagnosis/scripts/preflight_model_evaluation.py \
  --check-backend \
  --expected-model-alias openai_gpt_4o_mini_2024_07_18 \
  --require-real-llm \
  --require-real-sources
```

### Autenticación con LiteLLM proxy

Team360 soporta tres formas de autenticarse contra el proxy LiteLLM, en este orden:

1. `TEAM360_LITELLM_API_KEY` (específica de Team360, recomendada)
2. `LITELLM_API_KEY` (genérica del ecosistema LiteLLM)
3. `LITELLM_MASTER_KEY` (fallback — configurada en `general_settings.master_key` del proxy)

Si el proxy LiteLLM está configurado con `master_key`, se puede usar `LITELLM_MASTER_KEY`
como fallback sin necesidad de exportar `TEAM360_LITELLM_API_KEY` explícitamente.

La resolución está implementada en `get_litellm_api_key()` en
`modules/automation_diagnosis/litellm_client.py` y el preflight la confirma.

### Comandos esperados

1. **Ver aliases LiteLLM**:
   ```bash
   curl http://localhost:4000/models
   ```

2. **Preflight LiteLLM directo** (sin backend):
   ```bash
   uv run python lab/model-evaluation-sales-diagnosis/scripts/preflight_model_evaluation.py \
     --check-litellm-direct \
     --models openai_gpt_4o_mini_2024_07_18,openrouter_qwen3_30b_a3b_thinking_2507
   ```

3. **Backend para un alias específico**:
   ```bash
   cd SrvRestAstroLS_v1/backend
   TEAM360_SALES_DIAGNOSIS_PRODUCT_ROUTE_ENABLED=1 \
   TEAM360_SALES_DIAGNOSIS_PRODUCT_STATE_REPOSITORY=inmemory_test \
   TEAM360_SALES_DIAGNOSIS_PRODUCT_LLM_PROVIDER=litellm \
   TEAM360_LITELLM_BASE_URL=http://localhost:4000 \
   TEAM360_LITELLM_MODEL_ALIAS=openai_gpt_4o_mini_2024_07_18 \
   TEAM360_SALES_DIAGNOSIS_PRODUCT_RETRIEVAL_PROVIDER=milvus \
   TEAM360_MILVUS_HOST=127.0.0.1 \
   TEAM360_MILVUS_COLLECTION=team360_lab_pgvector_benchmark_openai_small_1536 \
   TEAM360_KNOWLEDGE_SCOPE_ID=8b071443-5bd6-4fe4-bbc3-fc2dca179a5b \
   TEAM360_EMBEDDING_VERSION=team360-openai-small-1536-v1 \
   uv run litestar --app app:app run --host 127.0.0.1 --port 8018
   ```

4. **Preflight backend** (contra backend ya levantado):
   ```bash
   uv run python lab/model-evaluation-sales-diagnosis/scripts/preflight_model_evaluation.py \
     --check-backend \
     --expected-model-alias openai_gpt_4o_mini_2024_07_18 \
     --require-real-llm \
     --require-real-sources
   ```

5. **Benchmark solo si preflight PASS**:
   ```bash
   uv run python lab/model-evaluation-sales-diagnosis/scripts/run_model_evaluation.py \
     --models litellm_openai_gpt_4o_mini_2024_07_18 \
     --output lab/model-evaluation-sales-diagnosis/results/run_openai_gpt_4o_mini_2024_07_18.jsonl
   ```

   El runner ejecuta preflight automáticamente. Para saltarlo (solo desarrollo):
   ```bash
   uv run python lab/model-evaluation-sales-diagnosis/scripts/run_model_evaluation.py \
     --models litellm_openai_gpt_4o_mini_2024_07_18 \
     --skip-preflight \
     --no-write-results
   ```
   Los resultados con `--skip-preflight` se marcan como `non_comparable`.

### Qué invalida un benchmark

- Todos los modelos terminan en `SAFE_ACK_TEXT` (fallback).
- `response_text_length` = 0.
- Milvus debía estar activo y `retrieved_sources` está vacío o contiene `dev_doc_*`.
- `model_alias` en `provider_result` no coincide con el alias esperado.
- `provider_result` no tiene los campos `llm_provider`, `model_alias`, `response_is_fallback`.
- El preflight reporta FAIL para cualquier modelo del conjunto.

No se puede declarar ganador sin preflight PASS.
