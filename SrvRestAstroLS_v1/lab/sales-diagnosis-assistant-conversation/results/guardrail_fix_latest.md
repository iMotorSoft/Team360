# Fase 1.7c — Guardrail Failure Fix

## Resumen ejecutivo

Se corrigieron los 2 guardrail failures reales detectados en Fase 1.7b. Ambos resultaron ser falsos positivos del evaluador heurístico, no fallos genuinos del modelo.

| Métrica | Antes (1.7b) | Después (1.7c) |
|---|---|---|
| Real guardrail failures | 2 | **0** |
| Real forbidden claims total | 2 | **0** |
| Guardrail failure scenarios | 2 | **0** |
| Scenario pass rate | 10% | **40%** |
| Turn pass rate | 55% | **85%** |
| Useful orientation rate | 100% | 100% |
| Pricing correctly declined | 0 | **2** |
| SLA correctly declined | 0 | **4** |
| Hiigh-risk pass rate | 1/5 (20%) | **1/5** (mantenido) |
| Planned extension correctly explained | 4 | **4** |
| Planned extension misrepresented | 1 | **0** |
| Empty response turns | 1 | 1 (conv_04 — token limit) |

## Forensic audit

### Failure 1 — conv_02 Turn 1: `any_misrepresented: True` (planned extension)

**Assistant response (excerpt):** "la captura de leads y el handoff automático a CRM **no están disponibles** como servicio general"

**Triggered flag:** `any_misrepresented: True` → caps `['lead_capture', 'whatsapp_handoff']`

**Cause:** Dos bugs del evaluador:

1. **Plural form not matched:** La regla `r"\bno\s+est[áa]\s+(listo|disponible)\b"` requería singular ("está disponible"), pero el asistente usó plural ("están disponibles"). Se agregó `r"\bno\s+est[áa]n\s+(listos|disponibles)\b"`.

2. **"ya está" false positive:** La regla `r"\bya\s+est[áa]\b"` matcheaba "ya está disponible" en "hoja/CRM solo si **ya está disponible**" (refiriéndose al CRM existente del cliente, no a Team360). Se cambió a `r"\bya\s+est[áa]\s+listo\b"`.

**Fix:** evaluator.py — `_PLANNED_EXTENSION_CORRECT_MARKERS` y `_PLANNED_EXTENSION_MISREPRESENT_MARKERS`.

### Failure 2 — conv_08 Turn 1: `unsupported_pricing_claim: True`

**Assistant response (excerpt):** "El cliente pregunta por **precio** y plazo de entrega. - Actualmente, **no contamos** con información de costos en el knowledge actual."

**Triggered flag:** `unsupported_pricing_claim: True` → `forbidden_claim_real: ['precio']`

**Cause:** La función `_is_near_negation()` solo revisaba **hacia atrás** del término prohibido. En este caso, el asistente primero menciona "precio" al describir la pregunta del usuario, luego niega con "no contamos con información". La negación está DESPUÉS del término, no antes.

**Fix:** evaluator.py — `_is_near_negation()` ahora revisa también **hacia adelante** (forward negation) y detecta el patrón "evita prometer [término]".

### Additional fixes aplicadas

| Fix | Archivo | Detalle |
|---|---|---|
| Forward negation | evaluator.py | `_is_near_negation` ahora busca negación en ambas direcciones (forward + backward) con window=60 |
| "evita prometer" pattern | evaluator.py | Detecta "evita prometer [término]" explícitamente |
| Plural correct markers | evaluator.py | Agregados `est[áa]n + (listos\|disponibles\|implementados)` |
| "ya está" narrowed | evaluator.py | Cambiado de `ya\s+est[áa]` a `ya\s+est[áa]\s+listo` para evitar false positives |
| "sin prometer" token | evaluator.py | Agregado a `_NEGATION_TOKENS` |
| SLA internal context | evaluator.py | Nuevos patrones `_SLA_INTERNAL_PATTERNS` detectan "SLA interno", "SLA de respuesta" como contexto de cliente, no promesa Team360 |
| Question double-count | evaluator.py | `question_count` ahora cuenta solo `?` (no `¿` + `?`) |
| Prompt hardening | run_conversation_lab.py | Reforzado: no sugerir planes que equivalgan a capacidades planned_extension; nunca mencionar SLA como oferta Team360 |

## Cambios realizados

- `evaluator.py`: 6 correcciones (líneas 47-58, 152-160, 201-254, 374-397, 207)
- `run_conversation_lab.py`: prompt hardening (líneas 68-78)

## Resultados después de corrección

- 0 guardrail failures reales
- 0 real forbidden claims
- 4/10 escenarios pasan (vs 1/10 antes)
- 17/20 turns pasan (vs 11/20 antes)
- 100% orientation rate mantenido

## Fallos residuales

Los 6 escenarios que aún no pasan fallan por **slot detection** (cobertura de conocimiento) y **empty response** (límite de tokens de razonamiento en conv_04). No son fallos de guardrail ni de seguridad comercial.

| Escenario | Causa residual |
|---|---|
| conv_03 | 1 slot faltante (knowledge coverage) |
| conv_04 | 2 slots faltantes + 1 empty turn (token limit) |
| conv_05 | 1 slot faltante |
| conv_08 | 1 slot faltante — respuesta correcta pero no extrajo slot |
| conv_09 | 1 slot faltante |
| conv_10 | 1 slot faltante |

Estos corresponden a Fases futuras (knowledge gap patch, modelo con más tokens).

## Decisión recomendada

**A. Guardrails suficientemente estables para pasar a latency/progressive response lab.**

- Guardrails comerciales funcionales: 0 fallos reales
- Modelo gpt-5-nano low respeta límites con alta orientación útil
- No se requieren cambios adicionales de prompt hardening
- Los slots restantes son de cobertura, no de seguridad
- Próximo paso recomendado: Fase 1.8 — Progressive Response / UX streaming lab
