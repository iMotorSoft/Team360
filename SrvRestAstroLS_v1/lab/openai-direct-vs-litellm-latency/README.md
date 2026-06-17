# OpenAI directo vs LiteLLM Proxy — Benchmark de Latencia

Mide el overhead de latencia que agrega LiteLLM como gateway para gpt-5.4-nano.

## Pregunta

?La llamada a gpt-5.4-nano a traves de LiteLLM mantiene una velocidad suficientemente cercana a OpenAI directo como para justificar usar LiteLLM como gateway multi-tenant de Team360?

## Diseno

- 2 warm-ups por ruta (descartados)
- 10 mediciones por ruta, alternando orden
- Streaming real con `stream_options: include_usage: true`
- Mismo payload: system + user prompt, temperature=0.2, max_completion_tokens=500

## Rutas

| Via | Endpoint | Modelo | Key |
|---|---|---|---|
| OpenAI directo | `https://api.openai.com/v1/chat/completions` | `gpt-5.4-nano` | `OpenAI_Key_JAI_query` |
| LiteLLM proxy | `http://localhost:4000/v1/chat/completions` | `openai_gpt-5-nano` | `LITELLM_MASTER_KEY` |

## Ejecucion

```bash
python3.12 SrvRestAstroLS_v1/lab/openai-direct-vs-litellm-latency/run_benchmark.py
```

## Output

`results/<timestamp>/`:
- `calls.jsonl` — cada llamada individual
- `calls.csv` — version CSV
- `summary.json` — metricas agregadas y overhead
- `report.md` — informe completo

## Dependencias

- Python >= 3.12
- `requests`
- LiteLLM local en `http://localhost:4000`
- `OpenAI_Key_JAI_query` y `LITELLM_MASTER_KEY` en entorno

## Seguridad

- Claves solo desde variables de entorno
- No se imprimen ni persisten
- `results/` en `.gitignore`
