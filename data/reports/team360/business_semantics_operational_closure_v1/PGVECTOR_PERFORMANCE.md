# Performance pgvector

BLOCKED para medición nueva representativa. No se ejecutaron embeddings ni EXPLAIN ANALYZE con identidades auténticas; no se reportan latencias históricas como nuevas.

## Plan de medición focalizada

Medir código/canónico/alias, vector positivo, miss, ambiguo, otro tenant, varios conceptos y post-reinicio. Registrar candidatos, estrategia, abstención, p50/p95, configuración y plan con filtros tenant/workspace/version/modelo.

El SQL actual calcula cosine exacto tras filtros y no certifica uso de HNSW. Con nueve conceptos no justificar índice aproximado por microdiferencias.

El fix de evidencia añade lecturas acotadas para candidatos/contexto; memo por id/versión evita duplicados en una llamada. Impacto real de latencia pendiente. No existe cache intertenant nuevo.
