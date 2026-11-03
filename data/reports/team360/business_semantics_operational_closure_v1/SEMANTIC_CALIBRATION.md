# Calibración semántica

PARTIAL: corpus separado preparado, sin nueva calibración pgvector real ni umbrales ajustados. Los tests locales no miden calidad de embeddings.

## Dataset y metodología

SEMANTIC_DATASET.json separa 16 consultas de calibración y 16 holdout. Incluye aliases, paráfrasis, typo, modismo, entidades, métricas, abstenciones, tenant y contraejemplos L&S. Las etiquetas describen intención/limitación, no publicación empresarial.

Antes de ejecutar: preflight provider/alias/modelo/auth/cuota/fallback y destino DB aislado; usar retrieval read-only con identidad autorizada. No ejecutar el probe histórico que hace seed para medir lectura.

Registrar ruta exacta/alias/texto/vector, score/margen, abstención, falso positivo/negativo, ambigüedad, entidad/capability/dato/permiso separados y latencia. Ajustar sólo calibración; congelar parámetros antes del holdout. No imponer porcentaje arbitrario.

## Resultado local y limitaciones

Test nuevo reproduce nombre canónico sin alias: unknown antes, resolved después. Candidato textual y repregunta perdían related_evidence antes; después conservan PROVISIONAL, ownership UNKNOWN y limitaciones.

No se midieron nuevos falsos positivos/negativos vectoriales, precisión, recall ni latencias reales. Política previa mantiene vector como candidato, no verdad ni autorización; el pequeño baseline no basta para el gate amplio.
