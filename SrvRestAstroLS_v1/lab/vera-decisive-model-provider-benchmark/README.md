# Vera Decisive Model Provider Benchmark

## Que se prueba

Comparacion de 4 combinaciones modelo+proveedor para Vera (diagnosticadora de automatizaciones):

| Proveedor | Modelo | Key |
|---|---|---|
| Gemini directo | `gemini-3.1-flash-lite` + `reasoning_effort=minimal` | `GEMINI_API_KEY` |
| OpenAI directo | `gpt-5-nano` | `OpenAI_Key_JAI_query` |
| Requesty | `deepseek/deepseek-v4-flash` | `REQUESTY_API_KEY` |
| Requesty | `alibaba/qwen3-30b-a3b-instruct-2507` | `REQUESTY_API_KEY` |

## Por que importa

Elegir el mejor modelo/proveedor para Vera publica impacta directamente en:

- velocidad de respuesta (UX)
- naturalidad conversacional
- costo por conversacion
- calidad del diagnostico final
- estabilidad entre sesiones

Este laboratorio ejecuta UN UNICO CASO DECISIVO disenado para estresar comprension contextual,
correccion de contradicciones, manejo multidioma, y diagnostico profesional.

## Decisivo

Unico caso disenado:

Pequena empresa en Israel que vende repuestos industriales, recibe consultas por WhatsApp y Gmail,
usa programa contable cerrado en Windows para emitir Kabala (recibo),
inicialmente dice que stock y precios estan en planilla, luego corrige: stock en sistema, precios en planilla.
Descuentos especiales requieren aprobacion humana.

8 turnos con accion controlada:

- Turnos 1-7: `reflect_and_ask` (una pregunta por turno, sin diagnostico)
- Turno 8: `diagnose` (diagnostico completo)

Ver `conversation.py` para detalle exacto de mensajes y acciones.

## Que NO toca

- backend productivo
- LiteLLM
- PostgreSQL, Milvus (solo verificacion de disponibilidad)
- prompts productivos de Vera
- Knowledge docs
- team360_orquestador

## Dependencias

- Python >= 3.12
- `requests` (libreria estandar HTTP)
- `GEMINI_API_KEY`, `REQUESTY_API_KEY` o `OpenAI_Key_JAI_query` en entorno

No se necesita `openai` SDK ni `pymilvus`.

## Como ejecutar

Desde la raiz del proyecto:

```bash
# Benchmark completo (5 repeticiones por combinacion configurada)
uv run python3.12 SrvRestAstroLS_v1/lab/vera-decisive-model-provider-benchmark/run_benchmark.py

# Smoke test (1 repeticion por proveedor, para validar config)
uv run python3.12 SrvRestAstroLS_v1/lab/vera-decisive-model-provider-benchmark/run_benchmark.py --smoke

# Solo un proveedor
uv run python3.12 SrvRestAstroLS_v1/lab/vera-decisive-model-provider-benchmark/run_benchmark.py --provider gemini

# Sin streaming
uv run python3.12 SrvRestAstroLS_v1/lab/vera-decisive-model-provider-benchmark/run_benchmark.py --no-stream
```

## Outputs

`results/YYYYMMDD_HHMMSS/`:

- `turns.jsonl` - cada turno individual con metricas
- `turns.csv` - version CSV
- `conversations.json` - metricas agregadas por conversacion
- `summary.json` - resumen plano por corrida
- `report.md` - informe completo con tablas, scores y recomendacion

## Modo RAG

`static_deterministic` - todos los modelos reciben exactamente los mismos chunks predefinidos.

Razon: `pymilvus` no esta instalado en el entorno de ejecucion. No se usa LiteLLM.
Los chunks representan conocimiento relevante para el caso de evaluacion (capacidades Team360,
enfoques de automatizacion, tipos documentales Israel, patrones PyME, marco de factibilidad,
limites de seguridad).

## Seguridad

- Las claves solo se leen desde variables de entorno.
- No se imprimen, guardan ni persisten.
- Errores sanitizados.
- `results/` y `model_prices.local.json` en `.gitignore`.
- No se crean `.env` ni se modifica `.bashrc`.

## Estado

- LiteLLM: no levantado durante este benchmark.
- PostgreSQL 18: disponible (Docker).
- Milvus 2.6: disponible (Docker), coleccion `team360_sales_diagnosis_knowledge_v1` existe.
- Retrieval: modo estatico.
