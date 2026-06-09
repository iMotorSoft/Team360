# Milvus 2.6 vs PostgreSQL/pgvector Benchmark — Fase 1.6j

## ¿Qué se prueba?

Compara pgvector (baseline) contra Milvus 2.6 como índice vectorial derivado para los mismos 25 breaking-point cases de Fase 1.6d.

## ¿Por qué importa?

Evaluar si Milvus 2.6 mejora calidad de retrieval (pass rate) o latencia respecto a pgvector puro, usando los mismos embeddings de OpenAI (text-embedding-3-small, 1536d). Si Milvus no mejora, se descarta como complejidad innecesaria en runtime.

## Arquitectura

- **PostgreSQL 18**: source of truth, contiene los embeddings originales.
- **pgvector**: baseline de retrieval vectorial.
- **Milvus 2.6**: índice derivado experimental, poblado desde PostgreSQL sin re-embedding.
- **No LLM**: no se usa LLM para responder ni evaluar.
- **No ArangoDB**: fuera de alcance.
- **OpenAI text-embedding-3-small**: solo para embedding de queries (mismo para ambos sistemas).

## Dependencias

- `pymilvus>=3.0.0` (en `backend/pyproject.toml`)
- PostgreSQL 18 con pgvector y datos de knowledge ingestion cargados
- Milvus 2.6 corriendo en `localhost:19530`
- `OPENAI_API_KEY` en entorno

## Entorno

- Milvus: `http://localhost:19530` (por defecto)
- PostgreSQL: `DB_PG_V360_URL` o `TEAM360_DB_URL_PSQL`
- Scope: `ks_team360_sales_diagnosis` / `team360_live` / `team360_public_site`

## Ejecución

```bash
# Desde raíz del proyecto (SrvRestAstroLS_v1/):
uv run python lab/milvus-pgvector-benchmark/run_milvus_benchmark.py --reset-collection --top-n 20 --top-k 5

# Solo indexar (si ya se ejecutó benchmark antes):
uv run python lab/milvus-pgvector-benchmark/run_milvus_benchmark.py --index-only

# Solo benchmark (si ya hay datos indexados):
uv run python lab/milvus-pgvector-benchmark/run_milvus_benchmark.py --benchmark-only

# Dry run (validar conectividad):
uv run python lab/milvus-pgvector-benchmark/run_milvus_benchmark.py --dry-run

# Generar reporte detallado desde resultados:
uv run python lab/milvus-pgvector-benchmark/scripts/generate_report.py

# Generar infografía HTML:
uv run python lab/milvus-pgvector-benchmark/scripts/generate_infographics.py
```

## Resultados

- `results/milvus_pgvector_benchmark_<timestamp>.json` — datos completos
- `results/milvus_pgvector_benchmark_<timestamp>.md` — resumen Markdown
- `results/milvus_pgvector_benchmark_<timestamp>_detailed_report.md` — reporte detallado
- `infografias/milvus_pgvector_benchmark_<timestamp>_infografia.html` — infografía HTML

## ¿Qué resultado se considera OK?

- Si Milvus mejora pass rate en >= 5 puntos porcentuales respecto a pgvector, se evalúa como índice derivado complementario.
- Si Milvus es más rápido (latencia < 70% de pgvector), se evalúa por latencia.
- Si Milvus no mejora ni calidad ni latencia, se descarta como complejidad adicional.

## Decisión

**D. Evaluar Milvus como índice derivado por latencia — significativamente más rápido.**

- Milvus y pgvector tienen calidad idéntica (44.0% pass rate, 11/25 casos).
- Milvus es ~62x más rápido en retrieval (13.9ms vs 859.2ms promedio).
- Milvus no mejora calidad de retrieval: los mismos 11 casos pasan y los mismos 14 fallan.
- Los fallos son principalmente content_gap (8 casos sin candidato correcto en ambos sistemas) y ranking insuficiente.
- Milvus puede justificarse como índice derivado si la latencia de pgvector es problemática en runtime.
- PostgreSQL 18 sigue siendo source of truth. Milvus no reemplaza PostgreSQL.
- No se recomienda invertir en Milvus antes de resolver content_gap y/o implementar reranking.

**Ejecutado:** 2026-06-09 · 25 casos · top-N 20 · top-K 5 · OpenAI text-embedding-3-small 1536d
