# Status actual - pkg_sales_diagnosis

Objetivo: `knowledge-documents-foundation`

Ultima actualizacion: 2026-06-08

## Estado general

`pkg_sales_diagnosis` es el primer knowledge package concreto de Team360.

El paquete conserva los identificadores tecnicos:

- `package_code`: `pkg_sales_diagnosis`
- `knowledge_scope_code`: `ks_team360_sales_diagnosis`
- `assistant_instance_code`: `team360_sales_diagnosis`
- `service_code`: `svc_sales_diagnosis`
- `template_code`: `team360_sales_automation_diagnosis`

`Vera / Asistente Inteligente Vera` queda limitado a nombre comercial visible.

## Acciones realizadas

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

- Completar curaduria de manual, slots/preguntas, scoring matrix, catalogo de
  automatizaciones, seguridad/HITL, objeciones, casos por industria y glosario.
- Promover documentos solo cuando cumplan metadata, evidencia y limites.

## Notas de seguridad

- No usar `vera_*` como identificador tecnico.
- No incluir credenciales ni datos reales de clientes sin anonimizar.
