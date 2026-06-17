# Vera Gemini Conversation Benchmark

## Que se prueba

Comparacion de tres configuraciones Gemini para conversaciones tipo Vera (diagnosticadora de automatizaciones):

1. `gemini-3.1-flash-lite` + `reasoning_effort="minimal"`
2. `gemini-3.5-flash` + `reasoning_effort="minimal"`
3. `gemini-3.5-flash` + `reasoning_effort="medium"`

## Por que importa

Elegir el modelo y nivel de reasoning adecuado impacta directamente en:

- velocidad de respuesta (UX)
- naturalidad conversacional
- costo por conversacion
- calidad del diagnostico final
- estabilidad entre sesiones

Este laboratorio genera evidencia reproducible para decidir sin afectar produccion.

## Conversacion

8 turnos exactos:

1. "quiero responder a mensajes de venta"
2. "web"
3. "chat en vivo"
4. "correo electronico"
5. "100"
6. "gmail"
7. "informacion de productos"
8. "no"

## Que NO toca

- /t360
- backend productivo
- PostgreSQL, Milvus, LiteLLM
- Requesty, OpenRouter, Qwen, DeepSeek, GPT
- prompts productivos
- Knowledge docs
- Vera runtime

## Dependencias

- Python >= 3.12
- `openai >= 1.14.0`
- `GEMINI_API_KEY` en entorno

## Como ejecutar

Desde la raiz del proyecto:

```bash
uv run python SrvRestAstroLS_v1/lab/vera-gemini-conversation-benchmark/run_benchmark.py \
    --repeat 3 \
    --stream \
    --temperature 0.2 \
    --prices-file SrvRestAstroLS_v1/lab/vera-gemini-conversation-benchmark/model_prices.example.json
```

### Filtros

```bash
# Solo un modelo
--model gemini-3.1-flash-lite

# Solo un reasoning effort
--reasoning-effort minimal

# Sin streaming
--no-stream

# Ruta de salida custom
--output-dir /tmp/mi-resultado
```

## Outputs

`results/YYYYMMDD_HHMMSS/`:

- `turns.jsonl` — cada turno individual con metricas
- `turns.csv` — version CSV
- `conversations.json` — metricas agregadas por conversacion
- `summary.json` — resumen plano por corrida
- `report.md` — informe completo con tablas, scores y recomendacion

## Metricas principales

| Metrica | Por turno | Por conversacion |
|---|---|---|
| Time to first event | si | - |
| Time to first visible text | si | p50, p95, avg |
| Latencia total | si | p50, p95, avg |
| Tokens input/output/total | si | si |
| Preguntas por turno | si | si |
| Preguntas repetidas | si | si |
| Costo estimado | si | si |
| Diagnosis generada | si | si |
| Brevedad | si | - |
| Score de calidad | - | si |

## Seguridad

- `GEMINI_API_KEY` solo desde variable de entorno
- No se imprime, guarda ni persiste la clave
- Errores sanitizados
- `results/` en `.gitignore`
- No se crean `.env` ni se modifica `.bashrc`

## Estado

- Ultima actualizacion: 2026-06-16
- Proxima comparacion incluira: GPT, DeepSeek, Qwen, Requesty, OpenRouter
