# Embeddings y candidatos vectoriales

LiteLLM real responde embeddings de 1536 dimensiones. El servicio horizontal recibe alias/configuración; no selecciona un proveedor externo ni contiene credenciales.

## Configuración comprobada

La evidencia identifica el alias y upstream mediante model/info y prueba real de entrada. Revisión/configuración es un identificador operacional explícito, no una afirmación de versión interna del proveedor.

```bash
export TEAM360_SEMANTICS_EMBEDDING_ALIAS=openai_text_embedding_3_small
export TEAM360_SEMANTICS_EMBEDDING_DIMENSION=1536
export TEAM360_SEMANTICS_EMBEDDING_REVISION=text-embedding-3-small:1536:v1
```

Upstream registrado: `openai/text-embedding-3-small`. Preflight autenticado, dimensión y números finitos/no nulos comprobados. Router settings inspeccionados en `current_values`: fallbacks/context_window_fallbacks/content_policy_fallbacks sin configuración activa. No se consumió Milvus, no se añadió fallback.

El contenido embebido es JSON estable de nombre, definición, contexto y aliases. Hash SHA256; regeneración idempotente por concepto/version/alias/revisión/dimensión/hash. Una modificación significativa publica nueva versión y regenera explícitamente; no hay pipeline automático. Vectores anteriores permanecen auditables y no participan al recuperar otra versión vigente.

## Calibración provisional

La muestra DEV demuestra que similitud sola no basta: Calenta se parece tanto a menona como a farmacia. El margen evita entregar ambos como supuestas definiciones de producto.

- Parafraseo oportunidades: top 0.443, margen 0.063.
- Calenta: top 0.439, margen 0.006.
- Término desconocido: top 0.375, margen 0.013.
- Política de candidatos de esta muestra: score mínimo 0.4 y margen 0.05; no confirma automáticamente ningún concepto vectorial.
- Hard negatives farmacia-productos/clientes y deudas-proveedores conservan ambigüedad y restricciones de dimensión. No son coincidencias empresariales confirmadas.

Configuración explícita de la evaluación, no umbrales universales confiables:

```bash
export TEAM360_SEMANTICS_VECTOR_CALIBRATION=DEV-nine-concepts-evaluation
export TEAM360_SEMANTICS_VECTOR_MINIMUM_SCORE=0.4
export TEAM360_SEMANTICS_VECTOR_MINIMUM_MARGIN=0.05
```

Sin calibración configurada, se auditan candidatos pgvector pero no se entregan definiciones vectoriales a Luna. Sin embeddings, búsqueda exacta/FTS continúa y la degradación queda observable. Exact matches nunca llaman embeddings. Falta corpus más amplio e independiente antes de declarar calidad general o habilitar otros tenants.

## Reproducción

El probe reutiliza el seed publicado y administra embeddings sólo como bootstrap DEV aprobado. Sus pruebas de modificación adicional hacen rollback y no crean conocimiento aprobado nuevo permanente.

```bash
uv run python -m modules.business_semantics.live_evidence --output ../../data/reports/team360/business_semantics_pgvector_v1/postgres_embedding_evidence.json
```

Para administración normal: `cli embed --apply --payload <json>` recibe Console PASETO por stdin; JSON identifica concepto y versión. Requiere rol administrativo persistido y configuración previa. [Evidencia](postgres_embedding_evidence.json).
