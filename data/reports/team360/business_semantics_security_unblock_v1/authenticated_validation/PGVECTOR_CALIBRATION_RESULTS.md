# Calibración pgvector y holdout

CALIBRATION=BLOCKED; HOLDOUT=BLOCKED; TENANT_FILTER=BLOCKED operacional. Sólo auditoría independiente del corpus/configuración y disponibilidad PG/vector comprobadas; no se publicaron datos ni ajustaron umbrales.

## Corpus reutilizado e intacto

[corpus_audit.json](corpus_audit.json) acredita 16 calibration + 16 validation_holdout, queries únicas y ningún solapamiento literal; hash coincide con evidencia histórica.

SHA256 SEMANTIC_DATASET.json: db493536ca535b76ec4813adbab7dcd8550c628d1baef22a6229e6b4f7b1bdad. [Corpus original](../../business_semantics_operational_closure_v1/SEMANTIC_DATASET.json) permanece sin editar. No hay otro benchmark.

Calibración: farmacia, Menona, cobranza/deudas, importación prospectiva, horizontal/corporativa/online, Calenta, ventas recientes, repregunta temporal/métrica, Top20, typo y modismo. Holdout: ownership, uso mixto, ranking/ventas perdidas, período no soportado, múltiples métricas, asignación histórica, medicamentos/proveedores, tenant/rol, ausencia vs cero, facturación, alcance, unknown y publicación admin.

Holdout contiene restricciones esperadas, NO IDs canónicos o etiquetas intent; sus 16 casos son contratos de respuesta/seguridad, no un gold de top-1 vector. Requiere adjudicación operacional según estas etiquetas congeladas, no reetiquetar ni inventar accuracy. Productos fraccionados/materias primas/oportunidad provisional no son categorías separadas explícitas: cobertura empresarial completa del prompt no está demostrada por este corpus de 32.

## Configuración y recuperación

PG18.4/vector0.8.2 reales; inventario agregado 9 conceptos publicados, 2 propuestas, 10 embeddings totales. No se infiere scope/versión publicada de ese agregado.

Embeddings existentes: openai_text_embedding_3_small, revision text-embedding-3-small:1536:v1, dimensión 1536. En shell/override actuales faltan alias/revision/dimension explícitos y configuración vector calibration/score/margin; VectorCandidatePolicy.from_env() no acredita política activa. El test sintético usa 0.4/0.05 del pequeño baseline: NO se adoptaron como calibración nueva.

Resolver: code→canonical exact→alias; luego FTS y vector sólo candidatos. Necesita ≥2 hits, score y margin calibrados para incluir candidato vector en interpretación; permanece candidate/ambiguous, nunca verdad ni permiso. observe_unknown=False es requerido en evaluación read-only; el handler normal usa True y escribe observaciones.

## Resultados medidos

No se llamó LiteLLM ni se realizó retrieval suplantando actor. Falta identidad legítima, configuración operacional y preflight provider/modelo/auth/cuota/fallback; servicio escuchando no los acredita.

| Etapa / métrica | Resultado |
| --- | --- |
| Baseline real 32 casos | NOT_EXECUTED |
| Calibración real 16 casos | NOT_EXECUTED |
| FP / FN / precisión / recall / abstención | NOT_MEASURED |
| Ajuste de parámetros | NONE |
| Holdout independiente 16 casos | NOT_EXECUTED |
| Latencia exact/alias/FTS/embedding/vector | NOT_MEASURED |
| Tenant safety vector operacional | NOT_EXECUTED |

Después de sesión: preflight del alias real sin fallback; retrieval autorizado read-only; registrar método, score/margen, abstención, FP/FN y tiempos por etapa; ajustar sólo calibration con justificación, congelar y evaluar holdout sin tuning. No ejecutar live_evidence.py, que seed/commit no equivale a lectura autenticada.

## Contratos empresariales preservados

Tests focalizados conservan límites como datos estructurados; esto no es calidad pgvector ni clasificación empresarial aprobada.

SEMANTIC_RESOLVED != CAPABILITY_AVAILABLE; SEMANTIC_SIMILARITY != BUSINESS_TRUTH. «Nuestro» requiere identidad/ámbito/evidencia, L00003 admite consumo y venta, fuera del Top20 no implica venta perdida, provisional no certificado. No se promovió ownership ni clasificaciones comerciales.
