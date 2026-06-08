# Status actual - pkg_sales_diagnosis metadata

Objetivo: `knowledge-documents-foundation`

Ultima actualizacion: 2026-06-08

## Estado general

`_metadata/` contiene el perfil del paquete, el mapeo de scope y el catalogo de
access tags para `pkg_sales_diagnosis`.

## Acciones realizadas

### 2026-06-08 - Status local de metadata

- Se agrego status local para cumplir la convencion documental por directorio.
- No se modificaron `package-profile.yaml`, `knowledge-scope-mapping.yaml` ni
  `access-tags.yaml`.

## Validacion

- `git diff --check`: OK.
- `uv run pytest tests/test_knowledge_ingestion.py`: 65 passed.

## Pendientes recomendados

- Mantener sincronizados los tags y areas permitidas con los documentos que se
  promuevan a `approved/`.

## Notas de seguridad

- Los access tags son parte de la frontera de permisos documental; no asumir
  permisos implicitos fuera del catalogo.
