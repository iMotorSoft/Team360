# Status actual - pkg_sales_diagnosis drafts

Objetivo: `knowledge-documents-foundation`

Ultima actualizacion: 2026-06-14

## Estado general

`drafts/` contiene documentos en revision para `pkg_sales_diagnosis`. No son
fuente aprobada para ingesta.

## Acciones realizadas

### 2026-06-14 - Correcciones pre-approved de consistencia

- Se normalizo metadata de package manual y slots/questions al modelo
  documental de los otros drafts.
- Se neutralizaron bloques futuros de Step-to-Action, lead capture,
  diagnostic_code y WhatsApp handoff para que no funcionen como copy activo.
- Se agrego precedencia documental explicita en los ocho drafts principales.
- Se alineo `available_with_validation` para que no se confunda con
  `feasible_not_packaged`.
- Se reforzaron limites para finanzas, bancos, pagos, decisiones automaticas y
  revision humana.
- Los ocho documentos permanecen en `drafts/` con `ingestion_status: not_ready`.
- No se movio contenido a `approved/`.

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

- Completar revision editorial final, QA conversacional y validacion de
  retrieval antes de promover documentos.
- Separar aprobacion por area: seguridad/HITL, matriz de factibilidad,
  respuestas, objeciones, catalogo, slots, manual y glosario.

## Notas de seguridad

- Drafts no deben alimentar respuestas activas ni ingestion automatica.
