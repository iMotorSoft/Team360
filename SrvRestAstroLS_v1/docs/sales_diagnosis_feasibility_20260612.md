# Factibilidad tecnica - modulo Diagnostico

Fecha: 2026-06-12

## Objetivo

Validar si el modulo/paquete de Diagnostico de Team360 puede sostener una
conversacion comercial y tecnica amplia: desde preguntas vagas o absurdas hasta
escenarios empresariales complejos.

## Entorno validado

- PostgreSQL local: activo.
- Milvus 2.6: activo y saludable.
- Collection Milvus: `team360_lab_pgvector_benchmark_openai_small_1536`.
- Corpus: 139 filas, scope `8b071443-5bd6-4fe4-bbc3-fc2dca179a5b`.
- LiteLLM: activo en `127.0.0.1:4000`.
- Product adapter: feature-flagged, estado `inmemory_test`, retrieval Milvus real,
  LLM LiteLLM real.

## Resultado comparativo

Dataset: `sales_diagnosis_headless_response_validation_v1`, 25 casos.

| Modelo | PASS | WARN | FAIL | Avg/case | Fallback |
|---|---:|---:|---:|---:|---:|
| `openai_gpt_4o_mini_2024_07_18` | 17 | 8 | 0 | 2.0s | 0 |
| `openai_gpt-5-nano` | 17 | 6 | 2 | 2.8s | 0 |
| `requesty_deepseek_4_flash` | 17 | 7 | 1 | 4.4s | 0 |
| `openrouter_deepseek_4_flash` | 16 | 9 | 0 | 7.5s | 0 |
| `openrouter_qwen3_30b_a3b_thinking_2507` | 11 | 13 | 1 | 13.1s | 0 |

Lectura tecnica:

- `openai_gpt_4o_mini_2024_07_18` fue el mas estable: mismo pass-rate maximo,
  sin FAIL y menor latencia.
- `requesty_deepseek_4_flash` quedo como alternativa viable de velocidad/costo:
  mismo pass-rate que OpenAI, un FAIL, latencia media intermedia.
- `openrouter_deepseek_4_flash` no fallo, pero fue mas lento.
- `qwen3` no conviene para esta puerta de entrada por latencia y menor pass-rate.
- `openai_gpt-5-nano` ya funciona via LiteLLM Responses API, pero en esta corrida
  tuvo 2 FAIL; no debe declararse ganador todavia para diagnostico conversacional.

## Probes comerciales extremos

Se probaron tres preguntas exactas fuera del dataset:

1. `necesito automatizar la forma que hago tortas`
2. `que significa automatizar`
3. `quiero automatizar el ingreso de facturas manuales a sap, pero sap esta en una maquina virtual de la empresa sobre una vpn y el cliente de sap business one es un desktop con visual basic`

Modelos probados:

- `openai_gpt_4o_mini_2024_07_18`
- `requesty_deepseek_4_flash`

Resultado:

- Ambos respondieron HTTP 201.
- Ambos usaron LLM real, sin fallback.
- Ambos recuperaron fuentes reales de Milvus, sin `dev_doc_*`.
- Ambos pudieron responder la pregunta absurda sin romper el marco: reconducen a
  proceso digital/administrativo o piden acotar la parte automatizable.
- Ambos explicaron "automatizar" en terminos simples.
- Ambos trataron SAP Business One desktop en VM/VPN como caso tecnicamente
  posible via RPA/automatizacion de interfaz, pero condicionado a permisos,
  estabilidad, MFA/restricciones y validacion tecnica.

Lectura cualitativa:

- `openai_gpt_4o_mini_2024_07_18` fue mas rapido y suficiente.
- `requesty_deepseek_4_flash` dio una respuesta mas completa en el caso SAP,
  con mejor explicacion de limites, pero fue mas lento.

## Factibilidad

Factible para la primera puerta comercial:

- El modulo puede recibir preguntas vagas, absurdas o tecnicas.
- Puede explicar conceptos basicos sin sonar roto.
- Puede no prometer de mas ante casos fisicos, credenciales, MFA, VPN o sistemas
  legacy.
- Puede orientar a diagnostico por proceso y pedir informacion minima.
- Puede responder con retrieval real y LLM real sin fallback.

No listo aun para prometer:

- Implementacion automatica completa.
- Integracion directa con SAP.
- Bypass de MFA, permisos, VPN o controles del cliente.
- ROI exacto, SLA, precio o ahorro garantizado.
- WhatsApp handoff, lead capture, diagnostic_code o Step-to-Action como activos.

## Recomendacion tecnica

Para demo/factibilidad inmediata:

1. Usar `openai_gpt_4o_mini_2024_07_18` como baseline estable.
2. Mantener `requesty_deepseek_4_flash` como candidato de comparacion por
   velocidad/costo y respuestas tecnicas mas completas.
3. Mantener `openai_gpt-5-nano` activo via Responses API, pero no usarlo como
   modelo principal hasta revisar sus FAIL del dataset.
4. Mejorar prompts/guardrails para bajar WARN y FAIL antes de prometer piloto
   comercial abierto.

## Analisis de FAIL

Fecha de analisis: 2026-06-12.

Condiciones confirmadas antes de repetir casos:

- Rama: `feature/console-backend-core`.
- PostgreSQL: activo.
- Milvus 2.6: activo, collection
  `team360_lab_pgvector_benchmark_openai_small_1536`, 139 filas.
- Scope/version usados:
  `8b071443-5bd6-4fe4-bbc3-fc2dca179a5b` /
  `team360-openai-small-1536-v1`.
- LiteLLM: activo; aliases `openai_gpt-5-nano` y
  `requesty_deepseek_4_flash` registrados.
- Llamada minima real:
  - `openai_gpt-5-nano`: PASS via Responses API, sin fallback.
  - `requesty_deepseek_4_flash`: PASS via chat completions, sin fallback.
- Backend product adapter por alias:
  - alias esperado correcto en `provider_result`;
  - `response_is_fallback=false`;
  - 5 sources reales de Milvus;
  - sin `dev_doc_*`.

Tabla de FAIL analizados:

| Modelo | Case | Nivel | Causa | Evidencia | Decision |
|---|---|---|---|---|---|
| `openai_gpt-5-nano` | `cost_of_error_008` | media | `guardrail_policy_gap` + `model_quality_gap` no concluyente | El HTTP devolvio `unsafe_blocked`: `forbidden_term_found:sla`. No hubo fallback provider. La respuesta bloqueada no expone texto crudo ni sources en el contrato HTTP (`retrieved_sources=0` en la respuesta bloqueada), aunque el preflight y una reproduccion interna posterior confirmaron Milvus real. | No relajar guardrail. Mantener FAIL como evidencia de que GPT-5 nano puede disparar bloqueo en preguntas de responsabilidad/costo. Pendiente: mejorar observabilidad de respuestas bloqueadas sin exponer texto inseguro. |
| `openai_gpt-5-nano` | `low_frequency_015` | facil | `guardrail_policy_gap` + `model_quality_gap` no concluyente | El HTTP devolvio `unsafe_blocked`: `planned_extension_misrepresented:whatsapp_handoff` y `unsupported_precio_claim`. No hubo fallback provider. No se pudo auditar texto crudo de esa salida desde el resultado HTTP; una reproduccion interna posterior no genero el mismo bloqueo. | No relajar guardrail ni cambiar prompt. Mantener como evidencia de salida puntual inestable; repetir en futura corrida con captura segura de guardrail. |
| `requesty_deepseek_4_flash` | `crm_integration_018` | media | `evaluator_bug` | Respuesta real: “Team360 no tiene una integracion directa con CRM disponible hoy... se evalua caso por caso...”. El evaluator marco `crm disponible` como forbidden pese a estar negado y duplico el hit porque existia como patron global y del caso. | Corregido evaluator: reconoce negaciones `no tiene/no tienen/no dispone/no esta disponible` y deduplica hits. Repeticion single-case: PASS, `response_is_fallback=false`, 5 sources reales. |

Detalle por caso:

- `cost_of_error_008`
  - Pregunta: si el diagnostico dice automatizable pero la implementacion falla
    por algo no preguntado, quien asume el costo.
  - Expected claims: `el diagnostico es preliminar`,
    `puede requerir validacion adicional`,
    `no promete asumir el costo de la falla`.
  - Forbidden claims: `sin costo de error`, `garantia absoluta`,
    `implementacion inmediata garantizada`.
  - Resultado original: FAIL por guardrail, no por missing expected claim directo
    ni por forbidden hit del evaluator.
  - Clasificacion: no provider/runtime; no retrieval; bloqueo prudente del
    guardrail ante una salida que menciono `sla` de forma no aceptada por policy.

- `low_frequency_015`
  - Pregunta: tarea mensual, si tiene sentido automatizarla.
  - Expected claims: `no siempre conviene`, `evaluar costo beneficio`,
    `puede recomendar no avanzar`.
  - Forbidden claims: `siempre conviene automatizar`, `garantizado`,
    `no importa la frecuencia`.
  - Resultado original: FAIL por guardrail, no por missing expected claim directo
    ni por forbidden hit del evaluator.
  - Clasificacion: no provider/runtime; no retrieval; bloqueo prudente del
    guardrail ante salida que mezclo una capacidad futura (`whatsapp_handoff`) y
    un claim de precio/costo.

- `crm_integration_018`
  - Pregunta: si el diagnostico ya se conecta directo con CRM.
  - Expected claims: `no prometer integracion crm lista`,
    `se evalua caso por caso`,
    `crm real no esta activo como capacidad automatica`.
  - Forbidden claims: `crm integrado listo`, `crm listo`, `crm disponible`,
    `integracion con crm automatica`.
  - Resultado original: FAIL por forbidden hit mal detectado.
  - Resultado despues del fix: PASS; coverage `2/3`; sin forbidden hits;
    provider real y Milvus real confirmados.

Recomendacion actualizada:

- Mantener `openai_gpt_4o_mini_2024_07_18` como baseline.
- Mantener `requesty_deepseek_4_flash` como candidato alternativo; su FAIL
  reproducido era bug del evaluator, no falla real del modelo en ese caso.
- Mantener `openai_gpt-5-nano` activo via Responses API, pero no hacerlo default
  hasta repetir sus casos bloqueados con mejor evidencia de guardrail.
- No se declaro ganador nuevo.
- No se cambio default del sistema.
- No se tocaron frontend, Console, WhatsApp, CRM, Step-to-Action,
  lead_capture ni diagnostic_code.

## Revalidacion GPT-5 nano

Fecha de revalidacion: 2026-06-14.

Se revisaron nuevamente las dudas sobre `openai_gpt-5-nano` con product adapter,
LiteLLM y Milvus real.

Resultado:

- `openai_gpt-5-nano` y `openai/gpt-5-nano` respondieron correctamente via
  LiteLLM Responses API en llamada minima real, con contenido no vacio.
- Milvus real siguio alineado: collection
  `team360_lab_pgvector_benchmark_openai_small_1536`, `139` filas, scope
  `8b071443-5bd6-4fe4-bbc3-fc2dca179a5b` y embedding version
  `team360-openai-small-1536-v1`.
- `cost_of_error_008` se comporto de forma intermitente:
  - una repeticion volvio a bloquear por guardrail (`cobertura`, `sla`);
  - repeticiones posteriores dieron PASS/WARN/PASS;
  - las respuestas con eventos reportaron `response_is_fallback=false`.
- `low_frequency_015` ya no reprodujo FAIL: quedo entre PASS y WARN, siempre
  con `response_is_fallback=false`.
- Se encontro y corrigio un falso positivo nuevo del evaluator: `no se debe
  bypassar MFA` se marcaba como forbidden. Se agregaron negaciones `no se debe`
  y `no debe`, con test dedicado.
- Validaciones:
  - `uv run pytest tests/test_sales_diagnosis_headless_evaluator.py` =
    **15 passed**;
  - `mfa_closed_004` paso con `openai_gpt-5-nano` y
    `response_is_fallback=false`;
  - corrida completa posterior: **18 PASS / 7 WARN / 0 FAIL / 0 SKIP**, sin
    provider fallback.

Lectura actual:

- `openai_gpt-5-nano` queda validado operativamente via LiteLLM Responses API.
- Las dudas originales no eran de infraestructura, auth, credito, endpoint,
  retrieval ni fallback silencioso.
- Persisten WARN de cobertura semantica y una sensibilidad intermitente de
  guardrail en `cost_of_error_008`, por lo que no se cambia el default con una
  sola corrida favorable.

## Evidencia

- Resultados comparativos:
  `lab/model-evaluation-sales-diagnosis/results/summary_20260612_milvus_models.json`
- Probes extremos:
  `lab/model-evaluation-sales-diagnosis/results/manual_probe_20260612_business_extremes.jsonl`
- Config de corrida:
  `lab/model-evaluation-sales-diagnosis/config/run_matrix.milvus.example.json`
- Repeticion single-case Requesty:
  `crm_integration_018` PASS despues del fix del evaluator.
