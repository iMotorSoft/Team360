# Retrieval Quality & Commercial Fit Test — Fase 1.6b

## Objetivo

Evaluar con criterio reproducible si el retrieval actual con PostgreSQL/pgvector
+ OpenAI text-embedding-3-small es suficientemente útil para la primera etapa
productiva de Team360, o si requiere migración a Milvus/ArangoDB.

## Preguntas que responde

1. ¿pgvector alcanza para la primera etapa productiva?
2. ¿Los chunks recuperados ayudan a vender y operar Team360?
3. ¿El retrieval distingue entre capacidad lista hoy y planned_extension?
4. ¿Evita vender humo (overpromise)?
5. ¿Recupera límites comerciales y técnicos correctamente?
6. ¿Sirve como base para un servicio de Knowledge Base gestionada?
7. ¿Hay alguna razón real para meter Milvus ahora?

## Dataset

`golden_answers/retrieval_quality_cases.json` contiene **25 queries** clasificadas:

| Categoría | Queries | Enfoque |
|-----------|---------|---------|
| A. Comercial / ventas | q_01–q_05 | Valor vendible, límites, oferta real |
| B. Producto / límites | q_06–q_10 | Step-to-Action, lead capture, WhatsApp handoff |
| C. Técnico | q_11–q_15 | Slots, scopes, embedding_status, runtime target |
| D. Knowledge Base as a Service | q_16–q_20 | Multi-tenant, aislamiento, auditoría |
| E. Ambiguas / anti-humo | q_21–q_25 | Preguntas trampa de cliente |

## Scoring

| Condición | Puntos |
|-----------|--------|
| Concepto esperado en top-1 | +3 |
| Concepto esperado en top-3 | +2 |
| Concepto esperado en top-5 | +1 |
| Concepto prohibido en top-3 | **-5** |
| High-risk sin concepto esperado | **-5** |
| Sin resultados | **-3** |

## Uso

```bash
cd SrvRestAstroLS_v1

OPENAI_API_KEY="sk-..." DB_PG_V360_URL="postgresql://..." python \
  lab/retrieval-quality-commercial-fit/run_retrieval_quality_test.py

# Con opciones:
python lab/retrieval-quality-commercial-fit/run_retrieval_quality_test.py \
  --limit 5 \
  --min-score 0.3 \
  --output-prefix my_test_run
```

## Requisitos

- Python 3.10+
- psycopg 3 (backend depende)
- Conexión a BD `team360` con migraciones 003+ aplicadas
- Embeddings generados (Fase 1.5)
- OPENAI_API_KEY en entorno

## Output

- `results/{prefix}.json` — resultados completos
- `results/{prefix}.md` — reporte Markdown
- `infografias/` — (opcional) visualizaciones generadas

## No toca

- ❌ Milvus
- ❌ ArangoDB
- ❌ LLM chat completion
- ❌ Endpoints HTTP
- ❌ Frontend
- ❌ diagnosis / automation_diagnosis
- ❌ Backend productivo
- ❌ Migraciones
