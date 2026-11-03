# PostgreSQL operacional

Inspección real: base Team360 local DEV, PostgreSQL 18.4 y extensión vector 0.8.2. No se creó otra base ni se instaló/reinició PostgreSQL.

## Tablas y garantías

Las claves reutilizan `core_organizations`, `core_workspaces`, `core_users` y `core_events`. No se modifica el esquema Foundation ni se reescribe una migración histórica.

- `business_concepts`: scope organización/workspace/módulo, código estable, estado, versión publicada vigente.
- `business_concept_versions`: nombre, significado, tipo abierto, contexto operativo JSON, fuente, motivo, actor, aprobación y versión anterior.
- `business_concept_aliases`: forma original y normalizada, pertenecientes a una versión.
- `business_concept_embeddings`: alias, revisión declarada, dimensión, hash, vector y generación; CHECK `vector_dims=dimension`.
- `business_concept_capability_links`: referencias y madurez; nunca autorizaciones ni SQL.
- `business_concept_observations`: hash de expresión, scope, contador y revisión pendiente. Sin chat, teléfono o usuario adicional.
- `business_concept_entity_links`: entidad, namespace, clave real o NULL pendiente, relación, fuente, vigencia y evidencia.
- `business_concept_classification_rules`: reglas descriptivas/evidencia histórica, inputs, fuente y limitaciones. Ninguna regla operativa publicada.

Unique NULLS NOT DISTINCT evita duplicados en scopes opcionales. FK compuesto enlaza versiones/aliases/vectores. Triggers verifican workspace-organización y preservan definiciones/aliases publicados y evidencia estructurada. Actor/aprobación pertenecen a identidades Console existentes.

Índices B-tree de scope y aliases; GIN sobre nombre/definición con configuración española. Vectores sin índice aproximado: cosine exacto, filtrado por scope/versión/modelo/revisión/dimensión antes del ranking.

## Migraciones y seed DEV

Los comandos requieren destino cliente local, PG18, database `team360`, identidad de cluster explícita y `--apply`. El bootstrap local es sólo migración/seed autorizado; no es login Console ni impersonación.

Desde backend, con configuración privada DB ya disponible:

```bash
export TEAM360_ENV=dev
export TEAM360_SEMANTICS_DEV_SYSTEM_IDENTIFIER=7630993354699489317
uv run python -m modules.business_semantics.cli migrate --apply --local-owner-bootstrap
uv run python -m modules.business_semantics.cli migrate --migration 029_team360_business_semantics_relations_v1.sql --apply --local-owner-bootstrap
uv run python -m modules.business_semantics.channel_evidence --output ../../data/reports/team360/business_semantics_pgvector_v1/channel_foundation_evidence.json
uv run python -m modules.business_semantics.cli seed --apply --local-owner-bootstrap --actor-id "$APPROVED_ORGANIZATION_ADMIN_ID" --historical-proposals --foundation-evidence ../../data/reports/team360/business_semantics_pgvector_v1/channel_foundation_evidence.json
```

Migraciones aplicadas: [028](../../../../SrvRestAstroLS_v1/backend/db/migrations/028_team360_business_semantics_v1.sql) y [029](../../../../SrvRestAstroLS_v1/backend/db/migrations/029_team360_business_semantics_relations_v1.sql). El servidor reporta IP interna de contenedor; la conexión cliente es localhost y el cluster se verifica por system_identifier, no por IP interna.

El seed rechaza cambios incompatibles en significados y conceptos retirados/propuestos; no los sobrescribe. Una nueva aprobación se hace mediante propuesta/versionado explícito. Corporativo tiene versiones 1 y 2 reales: la segunda agrega comparación sin escoger sólo horizontal. Dos candidatos históricos quedan propuestos, fuera de recuperación publicada.
