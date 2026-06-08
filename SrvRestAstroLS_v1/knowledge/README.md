# Knowledge — Documentos Fuente Team360

Raiz de documentos fuente para knowledge en Team360.

Esta carpeta define la fundacion documental reusable para multiples
knowledge packages. No pertenece a ventas ni a un asistente particular:
`pkg_sales_diagnosis` es solo el primer paquete concreto usado para validar
la estructura.

## Estructura

```
knowledge/
├── README.md
├── status_actual.md
├── _standards/
│   ├── README.md
│   ├── authoring-standard.md
│   ├── metadata-frontmatter.md
│   ├── semantic-chunking-l0-l1-l2.md
│   └── curation-lifecycle.md
├── global/
│   ├── README.md
│   ├── drafts/
│   ├── approved/
│   ├── exports/
│   └── archive/
└── packages/
    ├── README.md
    └── {package_code}/
        ├── README.md
        ├── status_actual.md
        ├── _metadata/
        ├── drafts/
        ├── approved/
        ├── exports/
        └── archive/
```

## Capas

| Capa | Uso |
|---|---|
| `knowledge/_standards/` | Reglas editoriales, metadata, curaduria, L0/L1/L2 y preparacion para chunking. |
| `knowledge/global/` | Knowledge transversal de Team360, reusable por varios paquetes si la politica de acceso lo permite. |
| `knowledge/packages/{package_code}/` | Knowledge de un paquete concreto, con metadata y ciclo documental propio. |

## Separacion global, paquete y caso

- Global: conceptos, politicas, glosarios o reglas que pueden aplicar a mas
  de un paquete.
- Paquete: corpus versionable asociado a un `package_code` y a uno o mas
  `knowledge_scope_code`.
- Caso particular: instalacion, cliente, canal, asistente o validacion
  concreta que usa un paquete. No debe redefinir la arquitectura documental.

`pkg_sales_diagnosis` pertenece a la capa de paquetes. El nombre comercial
`Vera / Asistente Inteligente Vera` pertenece a la experiencia visible, no a
los identificadores tecnicos core.

## Ciclo documental

- Cada paquete tiene su propio árbol bajo `packages/{package_code}/`.
- `drafts/` contiene documentos en revisión; el worker de ingesta NO lee de aquí.
- `approved/` contiene documentos validados listos para ser ingeridos.
- `exports/` contiene formatos derivados (PDF). No son fuente canónica.
- `archive/` contiene documentos reemplazados o deprecated. No se ingieren.
- Los archivos `_metadata/` definen el perfil del paquete, el mapeo de scope y el catálogo de tags de acceso.
- No mezclar knowledge global, knowledge de paquete y conocimiento de un caso particular.
- No mezclar drafts con approved.
- Los documentos fuente no reemplazan la documentación técnica del sistema; eso pertenece a `SrvRestAstroLS_v1/docs/`.

## Estándares

Antes de crear o promover documentos fuente, revisar:

- `_standards/authoring-standard.md`
- `_standards/metadata-frontmatter.md`
- `_standards/semantic-chunking-l0-l1-l2.md`
- `_standards/curation-lifecycle.md`

## Relación con runtime

Esta carpeta prepara documentos fuente para futura ingesta. No ejecuta por si
misma embeddings, RAG, GraphRAG, ArangoDB, Milvus, pgvector ni SemanticChunker.

La frontera runtime se define en:

- `../docs/knowledge_ingestion_multiscope_design_20260607.md`
- `../../lat.md/knowledge-documents-foundation.md`
- `../../lat.md/knowledge-scope-contract.md`

## Paquetes actuales

| package_code | knowledge_scope_code | Asistente |
|---|---|---|
| `pkg_sales_diagnosis` | `ks_team360_sales_diagnosis` | Asistente Inteligente Vera (comercial) |
