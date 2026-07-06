# Model Selection & Routing

Politica de seleccion de modelos AI y ruteo de tareas para Team360.

## Principio

Extraer datos estructurados primero, analizar con modelos baratos despues. Vision solo como fallback cuando UI Automation, DOM o API no alcanzan.

## Tier de modelos

Esta sección define el modelo conceptual y las categorías utilizadas por las reglas posteriores.

| Tier | Rol | Modelo OpenAI | Costo input | Costo output |
|------|-----|---------------|-------------|--------------|
| nano | clasificacion masiva, extraccion, scoring simple, resumen corto | `gpt-5-nano` | USD 0.05 / 1M tok | USD 0.40 / 1M tok |
| mini | respuestas sugeridas, analisis de campanas, decisiones workflow simples | `gpt-5-mini` | USD 0.25 / 1M tok | USD 2.00 / 1M tok |
| medium | casos agentic complejos, computer use | `gpt-5.4-mini` | USD 0.75 / 1M tok | USD 4.50 / 1M tok |
| large | auditorias estrategicas, casos criticos | modelo segun necesidad | variable | variable |

Distribucion objetivo: 95% nano, 4% mini/medium, 1% large.

## Ruteo por proveedor

Si se usa OpenAI directo:
- vision economica: `gpt-5-nano`
- orquestador textual: `deepseek/deepseek-v4-flash` (USD 0.14 / USD 0.28 por 1M tok)

Si se centraliza en OpenRouter:
- vision economica: `google/gemini-2.5-flash-lite` (USD 0.10 input / USD 0.40 output)
- orquestador textual: `deepseek/deepseek-v4-flash`

DeepSeek V4 Flash no debe usarse como lector de capturas. Su rol es orquestador textual: interpretar estado, decidir proxima accion, construir argumentos para tools cerradas, revisar logs.

## Ruteo por tipo de automatizacion

Esta sección define cómo seleccionar modelos y providers según el tipo de automatización.

### SAP Business One Desktop Client

Esta sección resume el propósito y el alcance de «SAP Business One Desktop Client» dentro de Team360.

1. Microsoft UI Automation (fuente primaria de estado)
2. OCR local (Windows OCR, Tesseract, PaddleOCR, EasyOCR)
3. Modelo visual economico (`gpt-5-nano` o `gemini-2.5-flash-lite`)
4. Modelo visual superior o intervencion humana

### Browser automation (Meta, Mercado Libre, etc.)

Esta sección resume el propósito y el alcance de «Browser automation (Meta, Mercado Libre, etc.)» dentro de Team360.

1. Playwright extrae DOM, texto, tablas, metricas
2. Modelo barato clasifica y analiza sobre datos estructurados
3. Captura de pantalla solo como fallback o auditoria visual

Para OpenCode + `opencode-browser`, DeepSeek V4 Flash queda habilitado para
browser QA dirigido y validacion frontend/backend acotada solo si el prompt
fija herramientas `browsermcp_*`, snapshots antes/despues de cada cambio,
restricciones explicitas y punto de detencion. Ver
[[deepseek-v4-flash-opencode-browser]].

### Diagnosis assistant (Vera)

Esta sección resume el propósito y el alcance de «Diagnosis assistant (Vera)» dentro de Team360.

1. LiteLLM con alias `automation_diagnosis_text` para interpretacion
2. `automation_diagnosis_classifier` para clasificacion barata
3. `cheap_classifier` para extraccion y scoring simple
4. Ver [[ai-diagnosis-rag-runtime]] para modelo por defecto

## Aliases sobre slugs

Los modelos deben configurarse mediante aliases en LiteLLM, no hardcodearse como slugs:

```text
automation_diagnosis_text
automation_diagnosis_classifier
automation_diagnosis_recommender
sales_assistant_text
cheap_classifier
```

Esto permite cambiar de proveedor o modelo sin modificar codigo.

## Limites

Esta sección delimita responsabilidades y comportamientos que quedan fuera del alcance permitido.

- AI interpreta, Team360 decide (clasificacion final, scoring, acciones sensibles).
- No prometer bypass de MFA, anti-bot, hardware keys, biometria ni firma fuerte.
- Acciones sensibles (creacion documentos, pagos, publicacion, cambios de precio, movimientos stock) requieren aprobacion humana.
- Modelos baratos requieren validacion: schema JSON estricto, confidence score y escalacion ante baja confianza.

## Referencias

Esta sección reúne las referencias canónicas y fuentes relacionadas con la política.

- [[ai-litellm]] — gateway y adapter
- [[ai-diagnosis-rag-runtime]] — modelos por defecto para diagnosis
- [[deepseek-v4-flash-opencode-browser]] — uso validado de DeepSeek V4 Flash con OpenCode + `opencode-browser`
- `docs/analisis-tecnico/analisis_tecnico_browser_automation_modelos_ai_2026-05-08.md` — analisis browser automation
- `docs/analisis-tecnico/sap_b1_modelos_vision_costos_automatizacion.md` — analisis SAP B1 vision
- `docs/analisis-tecnico/team360_ai_diagnostico_stack_arango_milvus_litellm.md` — stack AI diagnostico
