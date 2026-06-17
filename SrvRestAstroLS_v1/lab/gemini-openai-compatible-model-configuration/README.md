# Gemini OpenAI-compatible model configuration

## Proposito

Este lab tecnico valida, de forma aislada, como configurar y ejecutar estos modelos Gemini mediante la API de Gemini compatible con OpenAI:

* `gemini-3.1-flash-lite`
* `gemini-3.5-flash`

No es un benchmark de Vera. No prueba conversacion completa, diagnostico, Milvus, PostgreSQL, LiteLLM, OpenRouter, Requesty, OpenAI, frontend ni `/t360`.

## Requisitos

Ejecutar desde la raiz del repo Team360.

La dependencia usada es el cliente Python de OpenAI ya declarado en `SrvRestAstroLS_v1/backend/pyproject.toml`:

```bash
cd SrvRestAstroLS_v1/backend
uv sync
```

## Variable GEMINI_API_KEY

El script lee la clave desde:

```bash
GEMINI_API_KEY
```

No crear `.env` con la clave y no imprimir su valor. Si la variable vive en `.bashrc`, cargarla en la shell antes de ejecutar.

## Endpoint OpenAI-compatible

El endpoint usado es:

```text
https://generativelanguage.googleapis.com/v1beta/openai/
```

Documentacion oficial revisada:

* OpenAI compatibility: https://ai.google.dev/gemini-api/docs/openai
* Gemini 3 developer guide: https://ai.google.dev/gemini-api/docs/gemini-3
* Gemini 3.5 Flash guide: https://ai.google.dev/gemini-api/docs/whats-new-gemini-3.5
* Gemini 3.1 Flash-Lite model page: https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flash-lite
* Gemini 3.5 Flash model page: https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash
* Troubleshooting and error codes: https://ai.google.dev/gemini-api/docs/troubleshooting

## Comandos exactos

Ejecucion puntual:

```bash
bash -lc 'source ~/.bashrc >/dev/null 2>&1 || true; cd SrvRestAstroLS_v1/backend && uv run python ../lab/gemini-openai-compatible-model-configuration/run_gemini_openai_compat.py --model gemini-3.1-flash-lite --reasoning-effort minimal --stream --max-tokens 48 --prompt "Respondé exactamente: OK"'
```

Matriz completa:

```bash
bash -lc 'source ~/.bashrc >/dev/null 2>&1 || true; cd SrvRestAstroLS_v1/backend && uv run python ../lab/gemini-openai-compatible-model-configuration/run_matrix.py'
```

Resultados:

```text
SrvRestAstroLS_v1/lab/gemini-openai-compatible-model-configuration/results/results.json
SrvRestAstroLS_v1/lab/gemini-openai-compatible-model-configuration/results/report.md
```

## Modelos verificados

La documentacion oficial declara estos model IDs:

* `gemini-3.1-flash-lite`
* `gemini-3.5-flash`

El script tambien usa `client.models.retrieve()` contra el endpoint compatible para confirmar el ID real devuelto por la API.

Resultado observado:

| Modelo solicitado | ID devuelto por retrieve | Estado |
|---|---|---|
| `gemini-3.1-flash-lite` | `models/gemini-3.1-flash-lite` | OK |
| `gemini-3.5-flash` | `models/gemini-3.5-flash` | OK |

## Niveles de thinking

La compatibilidad OpenAI usa:

```text
reasoning_effort
```

Google documenta el mapeo hacia `thinking_level` para Gemini 3.x:

| reasoning_effort | thinking_level |
|---|---|
| `minimal` | `minimal` para Gemini 3.1 Flash-Lite y Gemini 3.5 Flash |
| `low` | `low` |
| `medium` | `medium` |
| `high` | `high` |

Tambien se prueba la ejecucion sin `reasoning_effort`.

Defaults documentados usados como inferencia en `reasoning_effort_effective`:

| Modelo | Default documentado |
|---|---|
| `gemini-3.1-flash-lite` | `minimal` |
| `gemini-3.5-flash` | `medium` |

Resultado observado con `max_tokens=256` y prompt `Respondé exactamente: OK`:

| Modelo | Thinking | Exito | Finish | Latencia | Prompt tokens | Completion tokens | Total tokens | Reasoning tokens | Texto |
|---|---|---:|---|---:|---:|---:|---:|---:|---|
| `gemini-3.1-flash-lite` | default (`minimal` documentado) | True | `stop` | 1416 ms | 6 | 1 | 7 | - | `OK` |
| `gemini-3.1-flash-lite` | `minimal` | True | `stop` | 1498 ms | 6 | 1 | 7 | - | `OK` |
| `gemini-3.1-flash-lite` | `low` | True | `stop` | 1991 ms | 6 | 1 | 162 | - | `OK` |
| `gemini-3.1-flash-lite` | `medium` | True | `stop` | 1705 ms | 6 | 1 | 87 | - | `OK` |
| `gemini-3.1-flash-lite` | `high` | True | `stop` | 1579 ms | 6 | 1 | 90 | - | `OK` |
| `gemini-3.5-flash` | default (`medium` documentado) | True | `stop` | 11303 ms | 6 | 1 | 83 | - | `OK` |
| `gemini-3.5-flash` | `minimal` | True | `stop` | 967 ms | 6 | 1 | 7 | - | `OK` |
| `gemini-3.5-flash` | `low` | True | `stop` | 2117 ms | 6 | 1 | 92 | - | `OK` |
| `gemini-3.5-flash` | `medium` | True | `stop` | 2174 ms | 6 | 1 | 119 | - | `OK` |
| `gemini-3.5-flash` | `high` | True | `stop` | 2201 ms | 6 | 1 | 94 | - | `OK` |

## Streaming

El script usa `stream=True` y `stream_options={"include_usage": True}`.

Se miden dos tiempos:

* `time_to_first_event_ms`: primer evento recibido.
* `time_to_first_visible_text_ms`: primer fragmento visible de texto.

Para producto, el dato principal es `time_to_first_visible_text_ms`.

Resultado observado:

| Modelo | Thinking | Primer evento | Primer texto visible | Total | Chunks | Texto |
|---|---|---:|---:|---:|---:|---|
| `gemini-3.1-flash-lite` | default | 989 ms | 989 ms | 992 ms | 2 | `OK` |
| `gemini-3.1-flash-lite` | `minimal` | 1470 ms | 1470 ms | 1472 ms | 2 | `OK` |
| `gemini-3.1-flash-lite` | `medium` | 1170 ms | 1170 ms | 1173 ms | 2 | `OK` |
| `gemini-3.5-flash` | default | 2305 ms | 2305 ms | 2309 ms | 2 | `OK` |
| `gemini-3.5-flash` | `minimal` | 1677 ms | 1677 ms | 1679 ms | 2 | `OK` |
| `gemini-3.5-flash` | `medium` | 1379 ms | 1379 ms | 1381 ms | 2 | `OK` |

## Usage

El lab registra:

* `prompt_tokens`
* `completion_tokens`
* `total_tokens`
* `completion_tokens_details.reasoning_tokens` si existe

No inventa `reasoning_tokens` si la API no lo devuelve.

Resultado observado:

* La API devolvio `prompt_tokens`, `completion_tokens` y `total_tokens`.
* No devolvio `completion_tokens_details.reasoning_tokens`; el campo quedo `null`.
* En niveles distintos de `minimal`, `total_tokens` puede ser mayor que `prompt_tokens + completion_tokens`, pero la API compatible no separo esos tokens como `reasoning_tokens`.

## Errores detectados

Las pruebas negativas controladas cubren:

* modelo inexistente;
* `reasoning_effort` invalido;
* key ausente simulada;
* `max_tokens` invalido;
* parametro no soportado/ignorado;
* uso simultaneo de `reasoning_effort` y `thinking_budget` como prueba negativa documentada.

Los errores se guardan sanitizados y sin headers ni credenciales.

Resultado observado:

| Prueba | Resultado |
|---|---|
| Modelo inexistente | HTTP 404 `NotFoundError` |
| `reasoning_effort` invalido | HTTP 400 `BadRequestError`; valores reportados por API: `high`, `low`, `medium`, `minimal`, `none` |
| Key ausente simulada | Error local `configuration_error`, sin llamada externa |
| `max_tokens=-1` | HTTP 400; `max_tokens must be positive` |
| Parametro top-level desconocido | HTTP 400; unknown field |
| `reasoning_effort` + `thinking_budget` | HTTP 400; la API exige uno u otro, no ambos |

## Salida controlada

Resultado observado:

| Modelo | Prueba | Resultado |
|---|---|---|
| `gemini-3.1-flash-lite` | `max_tokens=1` | Exito HTTP, `finish_reason=length`, texto visible vacio |
| `gemini-3.1-flash-lite` | `max_tokens=64` | Exito, `finish_reason=stop`, texto `OK` |
| `gemini-3.1-flash-lite` | `temperature=0.1` | Aceptado, texto `OK` |
| `gemini-3.1-flash-lite` | temperature default | Aceptado, texto `OK` |
| `gemini-3.5-flash` | `max_tokens=1` | Exito HTTP, `finish_reason=length`, texto visible vacio |
| `gemini-3.5-flash` | `max_tokens=64` | Exito, `finish_reason=stop`, texto `OK` |
| `gemini-3.5-flash` | `temperature=0.1` | Aceptado, texto `OK` |
| `gemini-3.5-flash` | temperature default | Aceptado, texto `OK` |

## Conclusiones por modelo

Ambos modelos ejecutan correctamente mediante el cliente Python de OpenAI contra el endpoint compatible de Gemini.

`gemini-3.1-flash-lite` mostro ejecucion correcta en default, `minimal`, `low`, `medium` y `high`. Su default documentado es `minimal`; con el prompt de smoke, `minimal` y default tuvieron `total_tokens=7`.

`gemini-3.5-flash` mostro ejecucion correcta en default, `minimal`, `low`, `medium` y `high`. Su default documentado es `medium`; en esta corrida el default tuvo mas latencia que `medium` explicito, por lo que no debe usarse una sola muestra como benchmark de rendimiento.

La medicion real de streaming distingue primer evento y primer texto visible; en estos casos coincidieron porque el primer evento ya trajo texto.

## Configuracion recomendada para benchmark posterior

Punto de partida tecnico para el benchmark posterior:

* `gemini-3.1-flash-lite`: usar `reasoning_effort="minimal"` como configuracion inicial; comparar luego contra `medium` si el benchmark de Vera exige mas razonamiento.
* `gemini-3.5-flash`: usar `reasoning_effort="medium"` como configuracion inicial por ser el default documentado; incluir `minimal` como variante de baja latencia.
* Para flujos interactivos, activar `stream=True` y medir `time_to_first_visible_text_ms`, no solo latencia total.
* Evitar `thinking_budget` en Gemini 3.x; usar `reasoning_effort`.
* No tratar esta corrida unica como conclusion estadistica: el benchmark posterior debe repetir cada configuracion, reportar mediana, percentiles y dispersion, y separar latencia total de tiempo al primer texto visible.

No documentar precios en esta fase.
