# Status actual - Global Knowledge

Objetivo: `knowledge-documents-foundation`

Ultima actualizacion: 2026-06-08

## Estado general

`global/` queda reservado para knowledge transversal reusable por multiples
paquetes. No contiene documentos aprobados todavia.

## Acciones realizadas

### 2026-06-08 - Espacio global inicial

- Se creo la estructura `drafts/`, `approved/`, `exports/` y `archive/`.
- Se documento que este nivel no debe recibir contenido especifico de ventas ni
  del paquete `pkg_sales_diagnosis`.

## Validacion

- `git diff --check`: OK.
- `uv run pytest tests/test_knowledge_ingestion.py`: 65 passed.

## Pendientes recomendados

- Identificar politicas transversales candidatas, como seguridad/HITL o glosario
  base, antes de crear documentos globales aprobados.

## Notas de seguridad

- Los documentos globales pueden impactar multiples paquetes; deben revisarse con
  especial cuidado antes de aprobarse.
