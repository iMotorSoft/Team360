# Embedding Model Comparison

## Objetivo

Comparar tres modelos candidatos de embeddings para retrieval semántico en Knowledge Ingestion de Team360:

| Provider | Modelo | Dimensión solicitada |
|---|---|---|
| OpenAI | text-embedding-3-small | 1536 |
| OpenRouter | qwen/qwen3-embedding-8b | 1536 (si soporta) |
| Perplexity | pplx-embed-v1-0.6b | auto-detectada |

## Por qué importa

El pipeline productivo actual usa `text-embedding-3-small` (1536d). Antes de decidir si mantenerlo, migrar o agregar un segundo modelo, necesitamos evidencia reproducible sobre:

- Calidad semántica (top-k retrieval contra golden answers)
- Latencia real por provider
- Dimensión real devuelta
- Formato de respuesta (float / base64 / int8)
- Costo estimado
- Facilidad de integración
- Errores o limitaciones

Este experimento NO modifica el pipeline productivo. Es laboratorio técnico reproducible dentro de producción incremental.

## Dataset

`golden_answers/embedding_retrieval_cases.json` contiene:

- **18 chunks** sobre dominio Team360 (automatización comercial, diagnóstico de ventas, integración técnica, WhatsApp, etc.)
- **10 queries** con expected y acceptable chunk IDs
- **8 temas** obligatorios del dominio

## Requisitos

- Python 3.10+
- Solo stdlib (`urllib.request`, `json`, `math`, `hashlib`)
- Sin dependencias externas

## Variables de entorno

| Variable | Obligatoria para | Provider |
|---|---|---|
| `OPENAI_API_KEY` | Modo real | OpenAI |
| `OPENROUTER_API_KEY` | Modo real | OpenRouter |
| `PERPLEXITY_API_KEY` | Modo real | Perplexity |

Las API keys solo se leen desde variables de entorno. No se guardan en archivos.

## Cómo ejecutar

### Modo mock (sin APIs externas)

```bash
cd SrvRestAstroLS_v1
python lab/embedding-model-comparison/run_experiment.py --mock
```

Genera embeddings sintéticos deterministas para validar estructura, ranking y reporte.

### Modo real (con APIs)

```bash
cd SrvRestAstroLS_v1
export OPENAI_API_KEY="sk-..."
export OPENROUTER_API_KEY="sk-..."
export PERPLEXITY_API_KEY="pplx-..."

python lab/embedding-model-comparison/run_experiment.py
```

### Filtrar por modelo

```bash
python lab/embedding-model-comparison/run_experiment.py --models openai perplexity
```

### Analizar resultados

```bash
python lab/embedding-model-comparison/scripts/compare_results.py
python lab/embedding-model-comparison/scripts/generate_infographics.py
```

## Resultados generados

- `results/{timestamp}_{mode}_embedding-comparison.json` — datos completos
- `results/{timestamp}_{mode}_embedding-comparison.md` — resumen Markdown
- `infografias/index.html` — infografía visual

## Criterios de cierre

Un modelo se considera viable si cumple:

1. **Top-3 hits ≥ 8/10** contra golden answers
2. **Latencia batch chunks < 2000 ms**
3. **Dimensión = 1536** (o documentar impacto de cambiar)
4. **Formato float** (compatible con pgvector)
5. **Sin errores** en la corrida real

La decisión final puede ser:
- Mantener text-embedding-3-small como default
- Agregar Qwen como alternativa para ciertos scopes
- Descartar modelo por error, dimensión, formato o latencia
- Repetir con cambios (batch size ajustado, parámetros diferentes)

## Aislamiento de producción

- Este experimento **no escribe en PostgreSQL**.
- **No modifica** Knowledge Ingestion productivo.
- **No genera** embeddings productivos.
- **No toca** `knowledge_chunk_embeddings`.
- **No toca** Milvus.
- **No toca** ArangoDB.
- **No modifica** documentos approved/drafts.
- **No cambia** configuración productiva.
- **No guarda** API keys ni secrets.
- Las API keys solo se leen desde **variables de entorno**.
- Los resultados se guardan únicamente en `lab/embedding-model-comparison/results/`.
- Las infografías se guardan únicamente en `lab/embedding-model-comparison/infografias/`.
- **No se importan** módulos del pipeline productivo (`backend/modules/knowledge_ingestion/`).
- **No se crean** migraciones de base de datos.
