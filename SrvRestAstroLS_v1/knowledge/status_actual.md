# Status actual - Knowledge Documents

Objetivo: `knowledge-documents-foundation`

Ultima actualizacion: 2026-06-14

## Estado general

`knowledge/` es la raiz de documentos fuente para knowledge de Team360.

La estructura separa:

- estandares editoriales y metadata en `_standards/`;
- knowledge global reusable en `global/`;
- knowledge de paquetes concretos en `packages/{package_code}/`;
- el primer paquete validable `pkg_sales_diagnosis` como caso particular, sin convertir ventas en limite arquitectonico.

`pkg_sales_diagnosis` mantiene ocho documentos draft activos: package manual,
slots/questions, matriz de factibilidad, playbook de respuestas, politica de
seguridad, catalogo de automatizaciones, objeciones comerciales y
glosario/referencias cruzadas.

## Acciones realizadas

### 2026-06-14 - Correcciones pre-approved en pkg_sales_diagnosis

- Se corrigieron inconsistencias estrategicas, editoriales y de seguridad en
  los ocho drafts principales de `pkg_sales_diagnosis`.
- Se mantuvo todo el contenido en `drafts/` con `ingestion_status: not_ready`.
- Se reforzo que diagnosticar factibilidad no implica prometer
  implementacion, cotizar, pedir contacto ni activar capacidades futuras.
- No se toco backend, runtime, ingestion service, embeddings, Milvus, ArangoDB,
  pgvector, endpoints ni UI.

### 2026-06-14 - Ocho drafts activos en pkg_sales_diagnosis

- Se incorporaron los documentos draft de matriz de factibilidad, playbook de
  respuestas, politica de seguridad, catalogo de automatizaciones, objeciones
  comerciales y glosario/referencias cruzadas.
- Se actualizaron package manual y slots/questions con el principio de
  diagnostico amplio de factibilidad tecnica y operativa.
- Los documentos permanecen en `drafts/` con `status: draft` e
  `ingestion_status: not_ready`.
- No se movio contenido a `approved/`.
- No se toco backend, runtime, ingestion service, embeddings, Milvus, ArangoDB,
  pgvector, endpoints ni UI.

### 2026-06-14 - Standard global de factibilidad diagnostica

- Se agrego el standard `_standards/diagnostic-feasibility-principle.md` para
  que los asistentes diagnosticos de Team360 evalúen casos fuera y dentro del
  catalogo inmediato sin convertir factibilidad en promesa comercial.
- El documento queda como `status: draft` e `ingestion_status: not_ready`.
- No se promovio contenido a `approved/`.
- No se activo ingestion service, embeddings, Milvus, ArangoDB, pgvector,
  endpoints, UI, Step-to-Action, lead capture, diagnostic_code ni WhatsApp
  handoff.

### 2026-06-08 - Fundacion documental knowledge

- Se formalizo `knowledge/` como base documental general para multiples paquetes futuros.
- Se agrego `_standards/` para authoring, metadata YAML, L0/L1/L2, SemanticChunker y curaduria.
- Se agrego `global/` como espacio para knowledge transversal no pegado a un paquete.
- Se agrego `packages/README.md` para declarar la convencion de paquetes.
- Se mantuvo `pkg_sales_diagnosis` como primer paquete de validacion.
- No se implemento ingesta runtime, embeddings, ArangoDB, Milvus, pgvector, endpoints ni UI de administracion.

## Validacion

- `git diff --check`: OK.
- `uv run pytest tests/test_knowledge_ingestion.py`: 65 passed.

## Pendientes recomendados

- Promover documentos reales a `approved/` solo despues de completar metadata y curaduria.
- Agregar golden questions por paquete antes de activar ingestion real con embeddings.
- Mantener `Vera` como nombre comercial visible, no como identificador tecnico core.

## Notas de seguridad

- No incluir secretos, credenciales, tokens ni datos de clientes reales sin anonimizar en documentos fuente.
