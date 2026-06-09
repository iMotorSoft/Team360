# Embedding Model Comparison Summary

**Date:** 2026-06-09 13:09 UTC
**Mode:** MOCK (synthetic embeddings)
**Dataset:** 18 chunks, 10 queries

## Models evaluated

| Provider | Model | Requested Dims | Actual Dims | Encoding | Compatible | Error |
|----------|-------|---------------|-------------|----------|------------|-------|
| openai | text-embedding-3-small | 1536 | 1536 | float | ✓ | — |
| openrouter | qwen/qwen3-embedding-8b | 1536 | 1536 | float | ✓ | — |
| perplexity | pplx-embed-v1-0.6b | — | 1536 | float | ✓ | — |

## Retrieval performance

| Provider | Model | Top-1 Hits | Top-3 Hits | Top-5 Hits | Total Queries |
|----------|-------|-----------|-----------|-----------|--------------|
| openai | text-embedding-3-small | 1 | 7 | 8 | 10 |
| openrouter | qwen/qwen3-embedding-8b | 1 | 7 | 8 | 10 |
| perplexity | pplx-embed-v1-0.6b | 1 | 7 | 8 | 10 |

## Latency

| Provider | Model | Chunks batch (ms) | Queries batch (ms) |
|----------|-------|-------------------|--------------------|
| openai | text-embedding-3-small | 0 | 0 |
| openrouter | qwen/qwen3-embedding-8b | 0 | 0 |
| perplexity | pplx-embed-v1-0.6b | 0 | 0 |

## Detailed retrieval by query

### openai / text-embedding-3-small

| Query | Top-1 | Top-1 Hit | Top-3 Hit | Top-5 Hit |
|-------|-------|----------|----------|----------|
| Como automatizar conversaciones de ventas en Team3 | chunk_012 | ✗ | ✓ | ✓ |
| Que metricas analiza el diagnostico de ventas | chunk_008 | ✗ | ✗ | ✗ |
| Como integrar Team360 con mi sistema via API | chunk_001 | ✗ | ✓ | ✓ |
| Team360 va a soportar WhatsApp | chunk_010 | ✓ | ✓ | ✓ |
| Cuando algo es automatico no significa que se vend | chunk_011 | ✗ | ✓ | ✓ |
| Configuracion minima para arrancar con Team360 | chunk_013 | ✗ | ✓ | ✓ |
| Team360 funciona en ingles y espanol | chunk_005 | ✗ | ✗ | ✗ |
| Que es Vera y como se relaciona con Team360 | chunk_006 | ✗ | ✓ | ✓ |
| Como funciona el scoring de diagnostico automatico | chunk_016 | ✗ | ✓ | ✓ |
| Integracion con Mercado Libre en Team360 | chunk_002 | ✗ | ✗ | ✓ |

### openrouter / qwen/qwen3-embedding-8b

| Query | Top-1 | Top-1 Hit | Top-3 Hit | Top-5 Hit |
|-------|-------|----------|----------|----------|
| Como automatizar conversaciones de ventas en Team3 | chunk_012 | ✗ | ✓ | ✓ |
| Que metricas analiza el diagnostico de ventas | chunk_008 | ✗ | ✗ | ✗ |
| Como integrar Team360 con mi sistema via API | chunk_001 | ✗ | ✓ | ✓ |
| Team360 va a soportar WhatsApp | chunk_010 | ✓ | ✓ | ✓ |
| Cuando algo es automatico no significa que se vend | chunk_011 | ✗ | ✓ | ✓ |
| Configuracion minima para arrancar con Team360 | chunk_013 | ✗ | ✓ | ✓ |
| Team360 funciona en ingles y espanol | chunk_005 | ✗ | ✗ | ✗ |
| Que es Vera y como se relaciona con Team360 | chunk_006 | ✗ | ✓ | ✓ |
| Como funciona el scoring de diagnostico automatico | chunk_016 | ✗ | ✓ | ✓ |
| Integracion con Mercado Libre en Team360 | chunk_002 | ✗ | ✗ | ✓ |

### perplexity / pplx-embed-v1-0.6b

| Query | Top-1 | Top-1 Hit | Top-3 Hit | Top-5 Hit |
|-------|-------|----------|----------|----------|
| Como automatizar conversaciones de ventas en Team3 | chunk_012 | ✗ | ✓ | ✓ |
| Que metricas analiza el diagnostico de ventas | chunk_008 | ✗ | ✗ | ✗ |
| Como integrar Team360 con mi sistema via API | chunk_001 | ✗ | ✓ | ✓ |
| Team360 va a soportar WhatsApp | chunk_010 | ✓ | ✓ | ✓ |
| Cuando algo es automatico no significa que se vend | chunk_011 | ✗ | ✓ | ✓ |
| Configuracion minima para arrancar con Team360 | chunk_013 | ✗ | ✓ | ✓ |
| Team360 funciona en ingles y espanol | chunk_005 | ✗ | ✗ | ✗ |
| Que es Vera y como se relaciona con Team360 | chunk_006 | ✗ | ✓ | ✓ |
| Como funciona el scoring de diagnostico automatico | chunk_016 | ✗ | ✓ | ✓ |
| Integracion con Mercado Libre en Team360 | chunk_002 | ✗ | ✗ | ✓ |

## Conclusión preliminar

**⚠️ Este resultado fue generado en modo mock.** Los embeddings son sintéticos deterministas, no representan calidad semántica real. Sirve exclusivamente para validar:

- Estructura del experimento (formato JSON, Markdown, HTML)
- Ranking y top-k retrieval funcionan correctamente
- Reporte y reproducibilidad del pipeline
- La decisión real requiere corrida con APIs auténticas.

**Preguntas que la corrida real debe responder:**

- ¿Conviene mantener text-embedding-3-small como default?
- ¿Qwen merece prueba ampliada?
- ¿Perplexity merece prueba ampliada o requiere validación de formato?
- ¿Algún modelo debe descartarse por error, dimensión, formato o latencia?
- ¿Hace falta re-embeddizar/reprocesar documentos si se cambia de modelo?
- ¿La dimensión vectorial actual (1536) queda afectada?
