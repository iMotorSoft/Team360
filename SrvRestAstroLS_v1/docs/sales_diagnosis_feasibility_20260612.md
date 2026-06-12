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

## Evidencia

- Resultados comparativos:
  `lab/model-evaluation-sales-diagnosis/results/summary_20260612_milvus_models.json`
- Probes extremos:
  `lab/model-evaluation-sales-diagnosis/results/manual_probe_20260612_business_extremes.jsonl`
- Config de corrida:
  `lab/model-evaluation-sales-diagnosis/config/run_matrix.milvus.example.json`
