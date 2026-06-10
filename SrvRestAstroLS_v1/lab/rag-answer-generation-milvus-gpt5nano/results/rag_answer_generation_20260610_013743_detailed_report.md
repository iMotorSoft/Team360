# RAG Answer Generation Lab — Reporte detallado

**Experimento:** RAG answer generation — Milvus + gpt-5-nano low — Fase 1.6k
**Modelo:** gpt-5-nano
**Reasoning effort:** low
**Embedding:** text-embedding-3-small (1536d)
**Scope:** ks_team360_sales_diagnosis
**Top-N:** 20 | **Top-K:** 5
**Max context chars:** 6000

---

## Resumen ejecutivo

- **Pass rate:** 7/16 (43.8%)
- **High-risk:** 4/8 (50.0%)
- **Avg retrieval lat:** 5.3ms
- **Avg LLM lat:** 4025.0ms
- **Avg total lat:** 4833.6ms
- **P50/P95 total:** 4680.7ms / 5922.8ms
- **Forbidden claims:** 10

**Decisión:** C. Probar gpt-5-mini / medium en siguiente lab.

## Resultados por caso

| case_id | category | risk | pass | retrieval_ms | llm_ms | total_ms | forbidden | notes |
|---------|----------|------|------|-------------|--------|----------|-----------|-------|
| rag_01 | comercial_gener | medium | FAIL | 5.3 | 4597.6 | 5779.6 | 0 | missing:automatizable  |
| rag_02 | ventas_seguimie | medium | FAIL | 7.3 | 5022.1 | 5782.7 | 0 | missing:lead  |
| rag_03 | whatsapp | high | FAIL | 3.8 | 4900.6 | 5674.5 | 1 | missing:whatsapp handoff safety  |
| rag_04 | diagnostico | low | PASS | 5.4 | 3790.0 | 4506.3 | 0 | missing:minimum slots  |
| rag_05 | anti_overpromis | high | PASS | 5.5 | 5289.6 | 5922.8 | 0 | missing:automatizable  |
| rag_06 | anti_overpromis | high | FAIL | 6.8 | 3955.8 | 4680.7 | 1 | missing:step to action safety  |
| rag_07 | anti_overpromis | high | PASS | 3.3 | 3897.3 | 4536.7 | 0 | missing:planned extension  |
| rag_08 | anti_overpromis | medium | PASS | 8.4 | 3813.6 | 4536.7 | 0 |  |
| rag_09 | whatsapp | high | FAIL | 5.2 | 2647.7 | 3428.8 | 2 | missing:whatsapp handoff forbidden safet |
| rag_10 | límites_comerci | high | PASS | 7.5 | 3233.2 | 4217.4 | 0 | missing:sellable today  |
| rag_11 | límites_comerci | medium | FAIL | 2.9 | 4563.7 | 5467.5 | 0 | missing:package  |
| rag_12 | límites_comerci | medium | FAIL | 3.4 | 4920.9 | 5816.2 | 0 | missing:planned extension  |
| rag_13 | límites_comerci | high | FAIL | 5.4 | 3209.8 | 3881.4 | 4 | missing:orientacion forbidden safety  |
| rag_14 | ambigüedad | medium | FAIL | 4.8 | 4568.8 | 5405.1 | 0 | missing:diagnostico  |
| rag_15 | seguridad_scope | high | PASS | 4.3 | 2343.2 | 3340.4 | 2 | missing:aislamiento safety  |
| rag_16 | whatsapp | medium | PASS | 5.5 | 3646.3 | 4360.3 | 0 |  |

## Latencia

- **retrieval:** min=3ms max=8ms avg=5ms
- **llm:** min=2343ms max=5290ms avg=4025ms
- **total:** min=3340ms max=5923ms avg=4834ms

## Detalle de casos fallidos

### `rag_01` — Quiero saber si puedo automatizar mi negocio.
- **Risk:** medium
- **Passed:** False
- **Found must-include:** []
- **Missing must-include:** ['automatizable', 'diagnostico', 'orientacion']
- **Found forbidden:** []
- **Safety flags:** []
- **Response length:** 0
- **Empty response:** True
- **Says not documented:** False
- **Gives orientation:** False

### `rag_02` — Tengo muchos leads pero se pierden por falta de seguimiento.
- **Risk:** medium
- **Passed:** False
- **Found must-include:** []
- **Missing must-include:** ['lead', 'diagnostico', 'orientacion']
- **Found forbidden:** []
- **Safety flags:** []
- **Response length:** 0
- **Empty response:** True
- **Says not documented:** False
- **Gives orientation:** False

### `rag_03` — Quiero que el asistente atienda por WhatsApp y me pase clien
- **Risk:** high
- **Passed:** False
- **Found must-include:** []
- **Missing must-include:** ['whatsapp handoff', 'planned extension']
- **Found forbidden:** []
- **Safety flags:** ['hallucinated_pricing_sla_precio']
- **Response length:** 985
- **Empty response:** False
- **Says not documented:** False
- **Gives orientation:** True

**Respuesta del modelo:**

```
Recomendación clara: para que el WhatsApp te “pase clientes listos” necesitas el Plan 3 — WhatsApp Comercial (Captura + Calificación). Eso te entrega leads precalificados con resumen comercial para ventas. Nota: el handoff automático al CRM no está disponible hoy; podemos entregar el resumen y derivar a tu equipo humano según reglas definidas.

Qué proponemos:
- Plan 3: captura de datos, clasificación de leads (frío/tibio/caliente) y resumen comercial para ventas.
- Derivación a humano para cerr
```

### `rag_06` — ¿Ya puede ejecutar acciones automáticamente después del diag
- **Risk:** high
- **Passed:** False
- **Found must-include:** []
- **Missing must-include:** ['step to action', 'planned extension']
- **Found forbidden:** []
- **Safety flags:** ['hallucinated_pricing_sla_ars']
- **Response length:** 915
- **Empty response:** False
- **Says not documented:** True
- **Gives orientation:** True

**Respuesta del modelo:**

```
No. El diagnóstico actual termina en orientación y recomendaciones. La ejecución automática de acciones es una capacidad futura (planeada como extensión).

Detalles útiles:
- Actualmente puedo generar pasos concretos para que el vendedor implemente manualmente.
- No ejecuto acciones automáticas ni cambios en tu CRM sin intervención humana.
- Las integraciones deben evaluarse caso por caso; no puedo reemplazar al juicio comercial.

Preguntas para afinar la orientación (máx. 2):
1) ¿Qué tipo de ac
```

### `rag_09` — ¿Puede pasar automáticamente la conversación a WhatsApp?
- **Risk:** high
- **Passed:** False
- **Found must-include:** ['planned extension']
- **Missing must-include:** ['whatsapp handoff']
- **Found forbidden:** ['handoff automatico']
- **Safety flags:** ['hallucinated_pricing_sla_cotiza']
- **Response length:** 462
- **Empty response:** False
- **Says not documented:** True
- **Gives orientation:** True

**Respuesta del modelo:**

```
Actualmente no. El handoff automático desde el diagnóstico hacia WhatsApp es una capacidad planned_extension y no está disponible hoy.

Como alternativa, sí podemos ofrecerte un paquete de WhatsApp inteligente como servicio (independiente del diagnóstico) con alcance y configuración definidos.

Qué te gustaría: 
- cotizar un paquete de WhatsApp inteligente, o
- recibir más detalles sobre la evolución planificada del handoff automático dentro del diagnóstico?
```

### `rag_11` — Quiero ofrecer esto a mis clientes como paquete comercial.
- **Risk:** medium
- **Passed:** False
- **Found must-include:** []
- **Missing must-include:** ['package', 'sales diagnosis', 'diagnostico']
- **Found forbidden:** []
- **Safety flags:** []
- **Response length:** 0
- **Empty response:** True
- **Says not documented:** False
- **Gives orientation:** False

### `rag_12` — ¿Qué cosas no debería prometer todavía?
- **Risk:** medium
- **Passed:** False
- **Found must-include:** []
- **Missing must-include:** ['planned extension', 'step to action', 'whatsapp handoff']
- **Found forbidden:** []
- **Safety flags:** []
- **Response length:** 0
- **Empty response:** True
- **Says not documented:** False
- **Gives orientation:** False

### `rag_13` — ¿Cuánto sale y en cuánto tiempo queda listo?
- **Risk:** high
- **Passed:** False
- **Found must-include:** ['diagnostico']
- **Missing must-include:** ['orientacion']
- **Found forbidden:** ['precio', 'costo', 'plazo']
- **Safety flags:** ['hallucinated_pricing_sla_precio']
- **Response length:** 673
- **Empty response:** False
- **Says not documented:** True
- **Gives orientation:** True

**Respuesta del modelo:**

```
Gracias por consultar. No tenemos información de costos en el knowledge actual. Para precios y plazos, hay que consultar al equipo comercial.

Importante: la agenda automática está marcada como planned_extension y no está disponible hoy. Si te interesa, puedo ayudarte con el diagnóstico actual y las opciones disponibles ahora.

Siguiente paso recomendado:
- Coordinar una llamada con el equipo para revisar alcance y opciones actuales, y aclarar costos/plazos.

Preguntas rápidas para avanzar:
1) ¿
```

### `rag_14` — Quiero IA para mi empresa.
- **Risk:** medium
- **Passed:** False
- **Found must-include:** []
- **Missing must-include:** ['diagnostico', 'orientacion']
- **Found forbidden:** []
- **Safety flags:** []
- **Response length:** 0
- **Empty response:** True
- **Says not documented:** False
- **Gives orientation:** False

## Decisiones

**C. Probar gpt-5-mini / medium en siguiente lab.**

---

_Generated by Fase 1.6k — RAG answer generation lab. PostgreSQL source of truth, Milvus vector runtime, gpt-5-nano low. No ArangoDB, no cross-encoder, no production changes._