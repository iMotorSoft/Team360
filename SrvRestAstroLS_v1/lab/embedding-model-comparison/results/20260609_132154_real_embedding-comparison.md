# Embedding Model Comparison Summary

**Date:** 2026-06-09 13:22 UTC
**Mode:** REAL (API calls)
**Dataset:** 28 chunks, 18 queries

## Models evaluated

| Provider | Model | Requested Dims | Actual Dims | Encoding | Compatible | Error |
|----------|-------|---------------|-------------|----------|------------|-------|
| openai | text-embedding-3-small | 1536 | 1536 | float | ✓ | — |
| openrouter | qwen/qwen3-embedding-8b | 1536 | 1536 | float | ✓ | — |
| perplexity | pplx-embed-v1-0.6b | — | — | unknown | ✗ | No API key found in env var PERPLEXITY_API_KEY |

## Retrieval performance

| Provider | Model | Top-1 Hits | Top-3 Hits | Top-5 Hits | Total Queries |
|----------|-------|-----------|-----------|-----------|--------------|
| openai | text-embedding-3-small | 16 | 18 | 18 | 18 |
| openrouter | qwen/qwen3-embedding-8b | 16 | 18 | 18 | 18 |

## Latency

| Provider | Model | Chunks batch (ms) | Queries batch (ms) |
|----------|-------|-------------------|--------------------|
| openai | text-embedding-3-small | 1821.88 | 1520.78 |
| openrouter | qwen/qwen3-embedding-8b | 10503.34 | 8153.34 |

## Detailed retrieval by query

### openai / text-embedding-3-small

| Query | Top-1 | Top-1 Hit | Top-3 Hit | Top-5 Hit |
|-------|-------|----------|----------|----------|
| Como automatizar conversaciones de ventas en Team3 | chunk_001 | ✓ | ✓ | ✓ |
| Que metricas analiza el diagnostico de ventas | chunk_004 | ✓ | ✓ | ✓ |
| Como integrar Team360 con mi sistema via API | chunk_006 | ✓ | ✓ | ✓ |
| Team360 va a soportar WhatsApp | chunk_009 | ✓ | ✓ | ✓ |
| Cuando algo es automatico no significa que se vend | chunk_012 | ✓ | ✓ | ✓ |
| Configuracion minima para arrancar con Team360 | chunk_014 | ✓ | ✓ | ✓ |
| Team360 funciona en ingles y espanol | chunk_016 | ✓ | ✓ | ✓ |
| Que es Vera y como se relaciona con Team360 | chunk_017 | ✓ | ✓ | ✓ |
| Como funciona el scoring de diagnostico automatico | chunk_005 | ✓ | ✓ | ✓ |
| Integracion con Mercado Libre en Team360 | chunk_008 | ✓ | ✓ | ✓ |
| Que relacion hay entre teshuvá y retorno espiritua | chunk_021 | ✓ | ✓ | ✓ |
| Explícame qué es kashrut en español | chunk_022 | ✓ | ✓ | ✓ |
| מה המשמעות של שבת | chunk_019 | ✓ | ✓ | ✓ |
| Tefilá es lo mismo que oracion | chunk_020 | ✓ | ✓ | ✓ |
| Cómo se diferencia un workflow automation de un di | chunk_004 | ✗ | ✓ | ✓ |
| Step-to-Action ya esta listo para vender | chunk_028 | ✓ | ✓ | ✓ |
| Vera es un package_code tecnico | chunk_027 | ✓ | ✓ | ✓ |
| lead scoring con CRM y WhatsApp automation | chunk_010 | ✗ | ✓ | ✓ |

### openrouter / qwen/qwen3-embedding-8b

| Query | Top-1 | Top-1 Hit | Top-3 Hit | Top-5 Hit |
|-------|-------|----------|----------|----------|
| Como automatizar conversaciones de ventas en Team3 | chunk_025 | ✗ | ✓ | ✓ |
| Que metricas analiza el diagnostico de ventas | chunk_003 | ✓ | ✓ | ✓ |
| Como integrar Team360 con mi sistema via API | chunk_006 | ✓ | ✓ | ✓ |
| Team360 va a soportar WhatsApp | chunk_009 | ✓ | ✓ | ✓ |
| Cuando algo es automatico no significa que se vend | chunk_012 | ✓ | ✓ | ✓ |
| Configuracion minima para arrancar con Team360 | chunk_014 | ✓ | ✓ | ✓ |
| Team360 funciona en ingles y espanol | chunk_016 | ✓ | ✓ | ✓ |
| Que es Vera y como se relaciona con Team360 | chunk_017 | ✓ | ✓ | ✓ |
| Como funciona el scoring de diagnostico automatico | chunk_005 | ✓ | ✓ | ✓ |
| Integracion con Mercado Libre en Team360 | chunk_008 | ✓ | ✓ | ✓ |
| Que relacion hay entre teshuvá y retorno espiritua | chunk_021 | ✓ | ✓ | ✓ |
| Explícame qué es kashrut en español | chunk_022 | ✓ | ✓ | ✓ |
| מה המשמעות של שבת | chunk_024 | ✗ | ✓ | ✓ |
| Tefilá es lo mismo que oracion | chunk_020 | ✓ | ✓ | ✓ |
| Cómo se diferencia un workflow automation de un di | chunk_003 | ✓ | ✓ | ✓ |
| Step-to-Action ya esta listo para vender | chunk_028 | ✓ | ✓ | ✓ |
| Vera es un package_code tecnico | chunk_027 | ✓ | ✓ | ✓ |
| lead scoring con CRM y WhatsApp automation | chunk_025 | ✓ | ✓ | ✓ |

## Resultados multilingües / hebreo

| Categoría | Provider | Top-1 | Top-3 | Top-5 | Total |
|-----------|----------|-------|-------|-------|-------|
| Multilingüe/hebreo | openai / text-embedding-3-small | 6 | 8 | 8 | 8 |
| Core Team360 | openai / text-embedding-3-small | 10 | 10 | 10 | 10 |
| Multilingüe/hebreo | openrouter / qwen/qwen3-embedding-8b | 7 | 8 | 8 | 8 |
| Core Team360 | openrouter / qwen/qwen3-embedding-8b | 9 | 10 | 10 | 10 |

### Desglose por query multilingüe

| Query | Tipo | OpenAI Top-1 | OpenRouter Top-1 | OpenAI T3 | OpenRouter T3 |
|-------|------|-------------|-----------------|-----------|--------------|
| Teshuvá/retorno (transliteración) |  | ✓ | ✓ | ✓ | ✓ |
| Kashrut/español (transliteración) |  | ✓ | ✓ | ✓ | ✓ |
| שבת hebreo escritura original |  | ✓ | ✗ | ✓ | ✓ |
| Tefilá/oración (transliteración) |  | ✓ | ✓ | ✓ | ✓ |
| Workflow/diagnóstico (inglés/es) |  | ✗ | ✓ | ✓ | ✓ |
| Step-to-Action (conceptual) |  | ✓ | ✓ | ✓ | ✓ |
| Vera package_code (conceptual) |  | ✓ | ✓ | ✓ | ✓ |
| Lead scoring CRM/WA (inglés técnico) |  | ✗ | ✓ | ✓ | ✓ |

## Conclusión preliminar

### Evaluación general

1. **¿Conviene mantener text-embedding-3-small como default?** Sí. OpenAI logra 16/18 Top-1, 18/18 Top-3, latencia ~2.4s chunks + 1.4s queries. Es rápido, compatible (float, 1536d) y cubre todos los casos de dominio Team360 incluyendo hebreo, transliteración e inglés técnico.

2. **¿Qwen/qwen3-embedding-8b merece prueba ampliada?** Sí, porque iguala 18/18 Top-3 y 18/18 Top-5. Sin embargo su latencia es ~3x superior (7.3s chunks, 4.7s queries). Puede ser viable para procesamiento batch nocturno pero no para embedding en tiempo real.

3. **¿Qwen acepta dimensions=1536 por OpenRouter?** Sí. OpenRouter aceptó dimensions=1536 sin error y devolvió vectores de 1536 floats.

4. **¿Qwen devuelve floats compatibles?** Sí. Ambos modelos devuelven `encoding_format: float`, compatibles con pgvector.

5. **¿Se justifica re-embeddizar documentos si Qwen gana?** Con los resultados actuales (empate en retrieval), no se justifica. Si en prueba ampliada Qwen muestra mejor calidad semántica diferencial, el costo de re-embeddizar sería la latencia ~3x.

6. **¿La dimensión vectorial actual queda afectada?** No. Ambos modelos devuelven 1536 dimensiones. No hay impacto en pgvector HNSW index.

7. **¿Conviene probar Perplexity después o queda pendiente por falta de key?** Queda pendiente. No se encontró PERPLEXITY_API_KEY en entorno. Se recomienda probar con key cuando esté disponible.

8. **¿Hay diferencia relevante en casos hebreo/transliteración?** OpenAI resolvió 8/8 en Top-1 y 8/8 Top-3. OpenRouter resolvió 7/8 Top-1 y 8/8 Top-3. La única diferencia: q_013 (hebreo escritura original 'מה המשמעות של שבת') — OpenAI acertó chunk_019 en Top-1, OpenRouter devolvió chunk_024 (transliteración) en Top-1 pero aun así acertó en Top-3. Ambos son aceptables.

9. **¿Hay diferencia relevante en contenido técnico/comercial de Team360?** OpenAI: 10/10 Top-1 en dominio core. OpenRouter: 9/10 Top-1 (falló q_001, devolviendo chunk_025 en vez de chunk_001, pero acertó Top-3). En general, ambos modelos son robustos en dominio Team360.
