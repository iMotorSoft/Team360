# Rendimiento y costo

Mediciones DEV de un catálogo publicado de nueve conceptos. Muestra pequeña, sin benchmark de escala ni comparación controlada de calidad del modelo.

## Tiempos observados

[postgres_embedding_evidence.json](postgres_embedding_evidence.json) separa lookup lexical, SQL textual, llamada upstream y cosine pgvector. Los tiempos de autenticación/scope están en elapsed total, fuera del campo exact/catalog.

| Etapa | Mediana | Rango |
| --- | --- | --- |
| Catálogo/normalización | 1,847 ms | 1,426–2,325 ms |
| SQL FTS (6 consultas) | 1,481 ms | 1,146–3,604 ms |
| Embedding de query (6 consultas) | 602,592 ms | 490,384–742,450 ms |
| pgvector exacto + savepoint (6 consultas) | 7,258 ms | 6,300–12,783 ms |
| Resolver completo aliases (5 consultas) | 3,756 ms | 3,444–4,531 ms |

Los exactos no llaman embeddings. Las consultas no exactas todavía generan un embedding por turno; no hay cache/query batching. El costo temporal upstream domina y es una limitación explícita de esta V1, no una mejora de latencia.

HTTP completo mezcla Luna, persistencia, Foundation y resolver: aproximadamente 3,5–12 segundos en la corrida final; no restar muestras independientes para inferir impacto causal. Ninguna llamada adicional a Luna fue introducida. No se justifica HNSW para este catálogo.

## Uso y facturación

El preflight de embedding registró 10 tokens, dimensión 1536 y respuesta válida. La última regeneración del seed fue no-op: no se reporta uso anterior como si fuera de esa operación.

No se dispuso de factura/costo final por request ni benchmark de precio del alias. No se inventa costo monetario. Las sondas reales de versiones/paráfrasis sí consumieron embeddings; sus efectos y límites están documentados, no se declara cero costo global.

## Recursos y cleanup

Host compartido con 8 cores, load inicial 2,38/3,67/3,98 y memoria disponible ~6 GB. Swap usada preexistente ~1,85 GB, sin crecimiento en observación posterior.

`HOST_PREFLIGHT=BUSY_BUT_SAFE`; consultas y tests secuenciales, sin pytest workers; lecturas DuckDB focalizadas con 2 threads/512 MB y un servidor HTTP propio a la vez. Sin suites masivas concurrentes, browsers, reingestión o cambios del servidor PG.

`RESOURCE_GUARD=PASS`, `UNRELATED_PROCESSES_TERMINATED=0`, `ENVIRONMENTAL_ABORTS=1`, `OWN_PROCESSES_LEFT_RUNNING=0`. Una sonda inicial de Reference abortó por `pytz` opcional ausente al materializar timestamps; no se reutilizó su salida ni se instalaron dependencias. El probe definitivo lee JSON en SQL y completó evidencia real. El harness cerró sus servidores/reinicios propios; no se mató ningún proceso ajeno.
