# Status actual - pkg_sales_diagnosis drafts

Objetivo: `knowledge-documents-foundation`

Ultima actualizacion: 2026-06-08

## Estado general

`drafts/` contiene documentos en revision para `pkg_sales_diagnosis`. No son
fuente aprobada para ingesta.

## Acciones realizadas

### 2026-06-08 - Alineacion de template documental

- Se actualizo `document-template.md` para incluir `document_code`, `status` e
  `ingestion_status`.
- Se mantiene `team360_sales_diagnosis_package_manual.md` y
  `team360_sales_diagnosis_slots_questions.md` en estado draft.
- No se promovio contenido a `approved/`.

## Validacion

- `git diff --check`: OK.
- `uv run pytest tests/test_knowledge_ingestion.py`: 65 passed.

## Pendientes recomendados

- Completar metadata, evidencia y limites antes de promover documentos.
- Separar manual, slots, scoring, seguridad/HITL, objeciones, industrias y
  glosario en documentos aprobables por area.

## Notas de seguridad

- Drafts no deben alimentar respuestas activas ni ingestion automatica.
