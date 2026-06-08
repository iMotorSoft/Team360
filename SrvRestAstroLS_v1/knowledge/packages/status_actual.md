# Status actual - Knowledge Packages

Objetivo: `knowledge-documents-foundation`

Ultima actualizacion: 2026-06-08

## Estado general

`packages/` agrupa knowledge packages versionables. El unico paquete actual es
`pkg_sales_diagnosis`.

## Acciones realizadas

### 2026-06-08 - Indice de paquetes

- Se agrego `README.md` para declarar la convencion minima de paquetes.
- Se aclaro que `pkg_sales_diagnosis` es el primer caso, no el limite de la
  arquitectura documental.

## Validacion

- `git diff --check`: OK.
- `uv run pytest tests/test_knowledge_ingestion.py`: 65 passed.

## Pendientes recomendados

- Usar esta convencion al crear futuros paquetes knowledge.

## Notas de seguridad

- Cada paquete debe declarar access tags propios y no heredar permisos por
  convencion implicita.
