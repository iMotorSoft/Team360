# Status actual - pkg_sales_diagnosis approved

Objetivo: `knowledge-documents-foundation`

Ultima actualizacion: 2026-06-08

## Estado general

`approved/` esta reservado para documentos fuente validados de
`pkg_sales_diagnosis`. Actualmente solo contiene estructura de areas y README;
no hay documentos aprobados para ingesta.

## Acciones realizadas

### 2026-06-08 - Status local de approved

- Se agrego status local para el directorio aprobado del paquete.
- No se agregaron documentos aprobados.
- No se activo ingestion.

## Validacion

- `git diff --check`: OK.
- `uv run pytest tests/test_knowledge_ingestion.py`: 65 passed.

## Pendientes recomendados

- Promover documentos por `area_key` solo despues de curaduria completa.
- Validar metadata contra `_metadata/access-tags.yaml` y
  `_metadata/knowledge-scope-mapping.yaml`.

## Notas de seguridad

- El contenido en `approved/` puede alimentar retrieval futuro; revisar riesgos,
  datos sensibles y limites comerciales antes de aprobar.
