# Status actual - pkg_sales_diagnosis

Objetivo: `knowledge-documents-foundation`

Ultima actualizacion: 2026-06-14

## Estado general

`pkg_sales_diagnosis` es el primer knowledge package concreto de Team360.

El paquete conserva los identificadores tecnicos:

- `package_code`: `pkg_sales_diagnosis`
- `knowledge_scope_code`: `ks_team360_sales_diagnosis`
- `assistant_instance_code`: `team360_sales_diagnosis`
- `service_code`: `svc_sales_diagnosis`
- `template_code`: `team360_sales_automation_diagnosis`

`Vera / Asistente Inteligente Vera` queda limitado a nombre comercial visible.

El paquete tiene ocho documentos draft activos: package manual,
slots/questions, matriz de factibilidad, playbook de respuestas, politica de
seguridad, catalogo de automatizaciones, objeciones comerciales y
glosario/referencias cruzadas.

## Acciones realizadas

### 2026-06-14 - Correcciones pre-approved de los ocho drafts

- Se aplicaron correcciones de consistencia estrategica, editorial y de
  seguridad sobre los ocho drafts principales.
- Se normalizo metadata de los dos drafts base.
- Se agrego precedencia documental explicita y se reforzo que seguridad/HITL
  prevalece sobre factibilidad, respuesta comercial o ejemplos.
- Se neutralizo contenido futuro accionable de Step-to-Action, lead capture,
  diagnostic_code y WhatsApp handoff.
- Se alinearon categorias de disponibilidad y se reforzaron limites para
  finanzas, bancos, pagos y decisiones automaticas.
- No se movio contenido a `approved/`.

### 2026-06-14 - Creacion de glosario y referencias cruzadas

- Se creo `team360_sales_diagnosis_glossary_crossrefs.md` como documento draft.
- Define vocabulario estandar, categorias normalizadas, slots documentados,
  capacidades futuras con estado `planned_extension`, referencias cruzadas,
  matriz de precedencia documental y checklist de QA pre-approved.
- Step-to-Action, lead capture, diagnostic_code y WhatsApp handoff permanecen
  como capacidades futuras, no activas.

### 2026-06-14 - Creacion de objeciones comerciales responsables

- Se creo `team360_sales_diagnosis_commercial_objections.md` como documento
  draft.
- Documenta objeciones comerciales, respuestas responsables, preguntas por
  etapa, frases recomendadas/prohibidas y limites para no prometer precios,
  tiempos, garantias ni contacto prematuro.

### 2026-06-14 - Creacion de catalogo inicial de automatizaciones diagnosticables

- Se creo `team360_sales_diagnosis_automation_catalog.md` como documento draft.
- Documenta casos tipicos de automatizacion con factibilidad, disponibilidad,
  riesgo y patron de respuesta.
- Los casos no listados no deben cerrarse con "no tenemos ese servicio"; deben
  evaluarse con separacion entre factibilidad y disponibilidad.

### 2026-06-14 - Creacion de politica de seguridad, limites y revision humana

- Se creo `team360_sales_diagnosis_security_hitl_policy.md` como documento
  draft.
- Declara la seguridad nativa bajo control del usuario y prohibe pedir, guardar,
  interceptar o automatizar codigos, MFA, QR, Face ID, tokens o aprobaciones
  manuales.
- Define clasificacion de riesgo, condiciones de `human_review_required` y
  criterios de bloqueo o redireccion segura.

### 2026-06-14 - Creacion de playbook de respuestas conversacionales

- Se creo `team360_sales_diagnosis_response_playbook.md` como documento draft.
- Define patrones de respuesta para cada `diagnosis_category`, estructura base,
  frases prohibidas/recomendadas, preguntas por etapa y casos especiales.

### 2026-06-14 - Creacion de matriz de factibilidad tecnica y disponibilidad comercial

- Se creo `team360_sales_diagnosis_feasibility_availability_matrix.md` como
  documento draft.
- Define dimensiones de evaluacion: `technical_feasibility`,
  `operational_feasibility`, `availability_status`, `service_maturity`,
  `offer_decision` y `diagnosis_category`.
- Incluye criterios para activar `human_review_required` y separar factibilidad
  de disponibilidad comercial inmediata.

### 2026-06-13 - Diagnostico amplio de factibilidad tecnica y operativa

- Se actualizaron package manual y slots/questions con el principio de
  diagnostico amplio.
- Se agregaron slots de clasificacion y reglas conversacionales para separar
  preguntas tecnicas de comerciales, presupuesto tardio y contacto posterior al
  valor diagnostico.
- Se reemplazaron referencias operativas a "MVP" por produccion por etapas o
  produccion incremental.

### 2026-06-08 - Alineacion con fundacion knowledge

- Se aclaro en el README del paquete que `pkg_sales_diagnosis` es primer caso de
  validacion y no limite arquitectonico.
- Se enlazaron los estandares generales de `knowledge/_standards/`.
- Se agregaron status locales para `_metadata/`, `drafts/` y `approved/`.
- No se promovieron documentos a `approved/`.
- No se cambio runtime, ingestion service, embeddings ni backend.

## Validacion

- `git diff --check`: OK.
- `uv run pytest tests/test_knowledge_ingestion.py`: 65 passed.

## Pendientes recomendados

- Completar QA conversacional y validacion de retrieval de los ocho drafts.
- Promover documentos solo cuando cumplan metadata, evidencia y limites.

## Notas de seguridad

- No usar `vera_*` como identificador tecnico.
- No incluir credenciales ni datos reales de clientes sin anonimizar.
