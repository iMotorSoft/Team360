# Recuperación e interpretación

La batería separa contratos unitarios, SQL/vector real y HTTP natural. [validation_results.json](validation_results.json) evalúa contenido, métricas, fuente y llamadas, no sólo HTTP 200.

## Casos S01–S13

Los casos pendientes se señalan explícitamente. Un significado conocido sin operación habilitada no recibe BUSINESS_RUNTIME_PASS analítico.

| Caso | Evidencia y resultado |
| --- | --- |
| S01 farmacia | Alias exacto, dimensión sucursal, refs persistidas, cero Foundation. |
| S02 menona | Segmento cliente, no producto/inferencia sensible; cero Foundation. |
| S03 importar | Intención analítica y factores potenciales; ninguna recomendación/OC inventada. |
| S04 deudas | Incluye vencida/corriente, mismo corte, sin saldos. |
| S05 perdidas | Definición y estados comerciales; ninguna cotización sin factura se declara pérdida definitiva. |
| S06 parafraseo | Vector real top lost_opportunities; política provisional lo entrega sólo como candidato. HTTP explica no-conversión vs pérdida confirmada. |
| S07 Calenta | Pregunta genérica pide aclaración; latest/search/ventas desde selección producen datos Foundation reales. No se impone concepto abstracto. |
| S08 desconocido | Sin definición elegible en contexto Luna; pregunta aclaración, cero ejecución, hash de observación pendiente. |
| S09 aislamiento | SQL organización distinta devuelve cero; mismatch organización/workspace denegado antes de buscar. Fixture HTTP real segundo tenant pendiente. |
| S10 versión | SQL real versiones 1/2 y dos embeddings en test rollback; corporativo también tiene versiones 1/2 permanentes. Mutation publicada rechazada. |
| S11 reinicio | Nueva conversación antes/después de reiniciar servidor propio recupera misma versión publicada sin configuración por sesión. |
| S12 embeddings caídos | Exacto sin llamada; FTS lexical devuelve farmacia; degradación observable y ningún vector ficticio. |
| S13 cercanos | Calenta/menona/farmacia sin margen suficiente; candidatos no se auto-confirman. Hard negatives conservan límites. Calibración general pendiente. |

La búsqueda FTS usa websearch AND en español, no es un detector universal de paráfrasis. “sucursales clasificadas como farmacias” no coincide lexicalmente en este corpus; queda registrada esa limitación en `offline_text_miss`.

## Regresión reproducible

Las suites existentes se ejecutan junto con nuevos tests, secuencialmente y sin workers automáticos. Se preserva la advertencia preexistente sobre repositorio Diagnosis in-memory en el test de composición.

```bash
cd SrvRestAstroLS_v1/backend
uv run pytest modules/business_semantics/tests modules/telchi/assistant/tests tests/test_telchi_assistant_srv05.py -q
uv run python -m modules.business_semantics.evaluate_evidence --root ../../data/reports/team360/business_semantics_pgvector_v1
```

Incluye guard committed falso, publicación/aliases, modelo/dimensión, ambigüedad, rol administrativo, referencias pendientes/retiradas/resolver desactivado, preservación de Product Search y métricas documentales. El caso fecha con limit 1 tiene regresión específica y HTTP correctivo separado.
