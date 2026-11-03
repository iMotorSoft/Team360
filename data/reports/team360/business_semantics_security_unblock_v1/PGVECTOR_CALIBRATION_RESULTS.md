# Calibración pgvector

PGVECTOR_REAL_CALIBRATION=BLOCKED. PostgreSQL/pgvector están disponibles, pero no se ejecutó calibración con identidad autenticada; no hay métricas nuevas de calidad o rendimiento.

## Baseline conservado

Se reutiliza el corpus separado sin reetiquetarlo, modificar umbrales ni publicar semántica provisional.

[SEMANTIC_DATASET.json](../business_semantics_operational_closure_v1/SEMANTIC_DATASET.json): 16 consultas de calibración y 16 de validation_holdout. Hash conservado en [provenance.json](provenance.json). El cierre previo [SEMANTIC_CALIBRATION.md](../business_semantics_operational_closure_v1/SEMANTIC_CALIBRATION.md) ya distingue corpus preparado de validación real.

vector 0.8.2 en PG18.4 confirmado read-only. No se generaron embeddings ni se llamó LiteLLM para sustituir las identidades faltantes. No se ejecutó live_evidence.py: hace escrituras/seed/commit y no representa los contratos de login humano.

## Resultados

NOT_MEASURED es ausencia de evidencia, no cero errores ni mala calidad del resolver.

| Métrica | Resultado nuevo |
| --- | --- |
| Precisión / errores FP-FN | NOT_MEASURED |
| Ambigüedad / abstención | NOT_MEASURED |
| Latencia exacta / FTS / embeddings / vector | NOT_MEASURED |
| Holdout independiente | NOT_EXECUTED |

Después de desbloquear: preflight real provider/alias/modelo/auth/cuota y fallback, retrieval sin observe_unknown ni mutación de catálogo; calibrar sólo en calibration, congelar parámetros y evaluar holdout una vez. Registrar scores/márgenes, intención/entidad/capability/dato/permiso por separado, errores y latencias por etapa.

Los contratos L&S permanecen como tests/propuestas. Aproximación vectorial sigue siendo candidato, no verdad, publicación automática ni autorización para ejecutar.
