# Status actual - Knowledge Documents

Objetivo: `knowledge-documents-foundation`

Ultima actualizacion: 2026-06-08

## Estado general

`knowledge/` es la raiz de documentos fuente para knowledge de Team360.

La estructura separa:

- estandares editoriales y metadata en `_standards/`;
- knowledge global reusable en `global/`;
- knowledge de paquetes concretos en `packages/{package_code}/`;
- el primer paquete validable `pkg_sales_diagnosis` como caso particular, sin convertir ventas en limite arquitectonico.

## Acciones realizadas

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
