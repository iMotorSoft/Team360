# Status actual - Knowledge Standards

Objetivo: `knowledge-documents-foundation`

Ultima actualizacion: 2026-06-08

## Estado general

`_standards/` contiene reglas editoriales y de preparacion para documentos
knowledge fuente.

## Acciones realizadas

### 2026-06-08 - Estandares base

- Se agregaron reglas de authoring.
- Se declaro el frontmatter YAML comun.
- Se documentaron criterios L0/L1/L2 y preparacion para SemanticChunker.
- Se documento el ciclo de curaduria y promocion documental.

## Validacion

- `git diff --check`: OK.
- `uv run pytest tests/test_knowledge_ingestion.py`: 65 passed.

## Pendientes recomendados

- Agregar validadores automaticos cuando el servicio de ingesta avance de dry-run a ingestion real.

## Notas de seguridad

- Los estandares prohiben secretos, credenciales y datos sensibles sin anonimizar.
